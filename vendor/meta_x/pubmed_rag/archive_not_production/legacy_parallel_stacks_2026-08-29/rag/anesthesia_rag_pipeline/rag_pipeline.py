"""
RAG Pipeline - Retrieval Augmented Generation for Anesthesia
Implements:
- Hybrid retrieval (dense + BM25) with reranking
- Query transformation (HyDE concept, multi-query)
- Grounded generation with citation checks
- Evaluation metrics (grounding rate, citation precision)
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re

from .config import RAGConfig, EmbeddingConfig
from .prompt_templates import (
    RAG_SYSTEM_PROMPT,
    build_context_string,
    get_prompt_for_intent,
    ANESTHESIA_PROMPT_LIBRARY
)
from .embedding_pipeline import EmbeddingPipeline, build_documents_for_embedding

logger = logging.getLogger(__name__)

# Simple intent classifier for anesthesia queries
INTENT_PATTERNS = {
    "comparative": re.compile(r'\bvs\.?\b|\bversus\b|\bcompare\b|\bbetter\b|\bdifference\b', re.I),
    "complication": re.compile(r'\bcomplication\b|\brisk\b|\badverse\b|\bside effect\b|\bmalignant hyperthermia\b|\baware', re.I),
    "drug_info": re.compile(r'\bdose\b|\bdosage\b|\bpharmacology\b|\bmechanism\b|\bpropofol\b|\bsevoflurane\b|\brocuronium\b|\bketamine\b', re.I),
    "technique": re.compile(r'\btechnique\b|\bhow to\b|\bapproach\b|\bblock\b|\bspinal\b|\bepidural\b|\bintubation\b|\bairway\b', re.I),
    "pediatric": re.compile(r'\bpediatric\b|\bchild\b|\bneonate\b|\binfant\b', re.I),
    "obstetric": re.compile(r'\bpregnan\b|\bobstetric\b|\blabor\b|\bfetal\b', re.I),
}

def classify_intent(question: str) -> str:
    q_lower = question.lower()
    scores = {}
    for intent, pat in INTENT_PATTERNS.items():
        scores[intent] = len(pat.findall(q_lower))
    # Return highest, default drug_info
    if not any(scores.values()):
        return "drug_info"
    return max(scores, key=lambda k: scores[k])

class HybridRetriever:
    def __init__(self, embedding_config: EmbeddingConfig = None, index_path: str = None):
        self.config = embedding_config or EmbeddingConfig()
        self.index_path = Path(index_path or self.config.index_path)
        self.embedding_pipeline = EmbeddingPipeline(self.config)
        self.bm25_index = None
        self.metadata_store: List[Dict[str, Any]] = []
        self.faiss_index = None
        self._load_index()
    
    def _load_index(self):
        # Load metadata
        meta_file = self.index_path / "metadata.jsonl"
        embed_file = self.index_path / "embeddings.jsonl"
        faiss_file = self.index_path / "faiss.index"
        
        if meta_file.exists():
            with open(meta_file) as f:
                self.metadata_store = [json.loads(line) for line in f]
            logger.info(f"Loaded {len(self.metadata_store)} metadata records")
        elif embed_file.exists():
            with open(embed_file) as f:
                self.metadata_store = [json.loads(line) for line in f]
            logger.info(f"Loaded {len(self.metadata_store)} embedded docs (JSONL fallback)")
        
        # Try FAISS
        if faiss_file.exists():
            try:
                import faiss
                self.faiss_index = faiss.read_index(str(faiss_file))
                logger.info(f"Loaded FAISS index with {self.faiss_index.ntotal} vectors")
            except Exception as e:
                logger.warning(f"Failed to load FAISS: {e}")
        
        # Build BM25 if possible (rank_bm25)
        if self.metadata_store:
            try:
                from rank_bm25 import BM25Okapi
                corpus_tokens = [doc.get('text','').lower().split() for doc in self.metadata_store]
                self.bm25_index = BM25Okapi(corpus_tokens)
                logger.info("Built BM25 index")
            except ImportError:
                logger.warning("rank_bm25 not installed - sparse retrieval disabled")
    
    def dense_search(self, query_emb: List[float], top_k: int = 10) -> List[Tuple[int, float]]:
        if self.faiss_index is not None:
            import numpy as np
            q = np.array([query_emb]).astype('float32')
            scores, indices = self.faiss_index.search(q, top_k)
            return [(int(idx), float(score)) for idx, score in zip(indices[0], scores[0]) if idx != -1]
        else:
            # Brute-force cosine over stored embeddings
            import math
            results = []
            for i, doc in enumerate(self.metadata_store):
                emb = doc.get('embedding')
                if not emb:
                    continue
                # Cosine (embeddings normalized)
                dot = sum(a*b for a,b in zip(query_emb, emb))
                results.append((i, dot))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
    
    def sparse_search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        if self.bm25_index is None:
            return []
        tokens = query.lower().split()
        scores = self.bm25_index.get_scores(tokens)
        # Get top k indices
        scored = list(enumerate(scores))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
    
    def hybrid_search(self, query: str, query_emb: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        dense_hits = self.dense_search(query_emb, top_k=top_k*2)
        sparse_hits = self.sparse_search(query, top_k=top_k*2)
        
        # Normalize and fuse with weighted RRF or linear combination
        # Simple weighted fusion
        score_map: Dict[int, float] = {}
        
        # Normalize dense scores 0-1 (they are cosine similarity if normalized)
        if dense_hits:
            max_d = max(s for _, s in dense_hits) if dense_hits else 1
            min_d = min(s for _, s in dense_hits) if dense_hits else 0
            rng = max_d - min_d or 1
            for idx, sc in dense_hits:
                norm = (sc - min_d) / rng
                score_map[idx] = score_map.get(idx, 0) + norm * self.config.dense_weight
        
        if sparse_hits:
            max_s = max(s for _, s in sparse_hits) if sparse_hits else 1
            min_s = min(s for _, s in sparse_hits) if sparse_hits else 0
            rng = max_s - min_s or 1
            for idx, sc in sparse_hits:
                norm = (sc - min_s) / rng
                score_map[idx] = score_map.get(idx, 0) + norm * self.config.sparse_weight
        
        # Sort fused
        fused_sorted = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, _ in fused_sorted[:top_k]]
        
        results = []
        for rank, idx in enumerate(top_indices):
            if idx < len(self.metadata_store):
                doc = dict(self.metadata_store[idx])
                doc['retrieval_score'] = score_map[idx]
                doc['retrieval_rank'] = rank
                results.append(doc)
        return results
    
    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        # Embed query
        q_embs = self.embedding_pipeline.embed_texts([query])
        q_emb = q_embs[0]
        return self.hybrid_search(query, q_emb, top_k=top_k)

class RAGPipeline:
    def __init__(self, rag_config: RAGConfig = None, embedding_config: EmbeddingConfig = None, index_path: str = None):
        self.rag_config = rag_config or RAGConfig()
        self.embedding_config = embedding_config or EmbeddingConfig()
        self.retriever = HybridRetriever(self.embedding_config, index_path=index_path)
        self.embedding_pipeline = EmbeddingPipeline(self.embedding_config)
    
    def query_transform(self, question: str) -> Dict[str, Any]:
        """
        Simple query transform - expands anesthesia synonyms.
        Production: call LLM with QUERY_TRANSFORM_PROMPT.
        """
        # Synonym expansion for anesthesia terms
        synonyms = {
            "general anesthesia": "general anesthesia OR total intravenous anesthesia OR TIVA",
            "propofol": "propofol OR 2,6-diisopropylphenol OR Diprivan",
            "sevoflurane": "sevoflurane OR fluoromethyl",
            "regional anesthesia": "regional anesthesia OR nerve block OR neuraxial anesthesia",
        }
        primary = question
        expanded = question
        for k, v in synonyms.items():
            if k.lower() in question.lower():
                expanded = expanded + f" ({v})"
        
        step_back = f"Principles and evidence for {question} in perioperative medicine"
        
        intent = classify_intent(question)
        
        # No clinical NER backend is certified in this package. Return no entities rather
        # than presenting capitalization heuristics as clinical entity extraction.
        entities: List[str] = []
        
        return {
            "primary": primary,
            "expanded": expanded,
            "step_back": step_back,
            "intent": intent,
            "clinical_entities": entities
        }
    
    def retrieve_with_transform(self, question: str, top_k: int = None) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        top_k = top_k or self.rag_config.max_context_docs
        transform = self.query_transform(question)
        
        # Retrieve for primary + expanded, fuse
        primary_docs = self.retriever.retrieve(transform['primary'], top_k=top_k)
        expanded_docs = self.retriever.retrieve(transform['expanded'], top_k=top_k)
        
        # Merge dedup by id
        seen = set()
        merged = []
        for doc in primary_docs + expanded_docs:
            did = doc.get('id')
            if did not in seen:
                seen.add(did)
                merged.append(doc)
        # Sort by retrieval_score
        merged.sort(key=lambda x: x.get('retrieval_score', 0), reverse=True)
        return merged[:top_k], transform
    
    def rerank(self, question: str, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Simple cross-encoder rerank - boost core tier and high anesthesia_score.
        Production: replace with cross-encoder model.
        """
        if not self.rag_config.rerank:
            return docs
        
        for doc in docs:
            base = doc.get('retrieval_score', 0)
            tier_bonus = {"core": 0.3, "relevant": 0.15, "peripheral": 0.0}.get(doc.get('metadata', {}).get('tier','peripheral'), 0)
            anest_score = doc.get('metadata', {}).get('anesthesia_score', 0) / 20.0  # normalize
            # Recency bonus
            year = doc.get('metadata', {}).get('year') or 0
            recency = max(0, (year - 2015) * 0.01) if year else 0
            doc['rerank_score'] = base + tier_bonus + anest_score + recency
        
        docs.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)
        return docs
    
    def build_prompt(self, question: str, docs: List[Dict[str, Any]], transform: Dict[str, str], patient_context: str = "None") -> str:
        context_str = build_context_string(docs, max_chars=12000)
        prompt = get_prompt_for_intent(
            intent=transform['intent'],
            question=question,
            context_str=context_str,
            patient_context=patient_context
        )
        # Prepend system prompt
        full_prompt = f"{RAG_SYSTEM_PROMPT}\n\n{prompt}"
        return full_prompt
    
    def generate_answer(self, prompt: str) -> str:
        """Fail closed until a real generation backend is configured.

        Earlier Meta code synthesized a plausible clinical answer and fake citation
        prose without calling an LLM. That behavior is forbidden in the repaired
        production tree. Retrieval remains usable independently.
        """
        raise RuntimeError("RAG generation backend is not configured; refusing to fabricate an answer")

    def answer_question(self, question: str, top_k: int = None, patient_context: str = "None") -> Dict[str, Any]:
        """
        Full RAG pipeline: transform → retrieve → rerank → prompt → generate + citation check.
        """
        retrieved, transform = self.retrieve_with_transform(question, top_k=top_k)
        reranked = self.rerank(question, retrieved)
        prompt = self.build_prompt(question, reranked, transform, patient_context=patient_context)
        answer = self.generate_answer(prompt)
        
        # Citation verification - FIX: ensure citations present
        citations_in_answer = re.findall(r'\[PMID:\d+\]', answer)
        citations_in_context = set(re.findall(r'\[PMID:\d+\]', prompt))
        
        # Grounding metrics
        grounding_rate = len(citations_in_answer) / max(1, len(answer.split('.')))  # rough
        citation_precision = len([c for c in citations_in_answer if c in citations_in_context]) / max(1, len(citations_in_answer)) if citations_in_answer else 0
        
        # Refusal check
        if self.rag_config.require_grounding and not citations_in_answer:
            if self.rag_config.refusal_if_no_evidence:
                if "No relevant evidence" not in answer:
                    answer = "No relevant evidence found in the provided PubMed corpus for this query. " + answer
        
        return {
            "question": question,
            "transform": transform,
            "retrieved_docs": reranked,
            "prompt": prompt,
            "answer": answer,
            "metrics": {
                "num_retrieved": len(reranked),
                "num_citations": len(citations_in_answer),
                "citation_precision": round(citation_precision, 3),
                "grounding_rate": round(grounding_rate, 3) if isinstance(grounding_rate, float) else grounding_rate
            }
        }
