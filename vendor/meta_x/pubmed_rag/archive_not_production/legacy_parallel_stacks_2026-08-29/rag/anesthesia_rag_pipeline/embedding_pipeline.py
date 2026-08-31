"""
Embedding Pipeline for Anesthesia RAG
Best practices implemented:
- PubMedBERT domain-tuned embeddings (clinically better than general)
- Sentence-boundary chunking at 512 tokens, 64 overlap (preserves clinical context)
- Hybrid retrieval ready (dense + BM25)
- Normalized embeddings for cosine
- FAISS IVF for scale
"""
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Iterable
import logging

logger = logging.getLogger(__name__)

# Sentence splitter without external deps - regex based fallback
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9])')

def sentence_aware_chunk(text: str, chunk_size_tokens: int = 512, overlap_tokens: int = 64) -> List[Dict[str, Any]]:
    """
    Chunk at sentence boundaries, approximate tokens via words *1.3 heuristic.
    For production, replace with tiktoken if available.
    """
    if not text:
        return []
    
    sentences = SENTENCE_SPLIT_RE.split(text)
    if len(sentences) == 1:
        # No sentence splits found, fallback to word chunking
        words = text.split()
        approx_tokens = lambda w: int(len(w) * 1.3) # rough
        chunks = []
        current_words = []
        current_tok = 0
        for w in words:
            current_words.append(w)
            current_tok += approx_tokens([w])
            if current_tok >= chunk_size_tokens:
                chunks.append({
                    "text": " ".join(current_words),
                    "token_estimate": current_tok,
                    "char_count": len(" ".join(current_words))
                })
                # overlap
                overlap_word_count = int(overlap_tokens / 1.3)
                current_words = current_words[-overlap_word_count:] if overlap_word_count >0 else []
                current_tok = sum(approx_tokens([x]) for x in current_words)
        if current_words:
            chunks.append({
                "text": " ".join(current_words),
                "token_estimate": current_tok,
                "char_count": len(" ".join(current_words))
            })
        return chunks
    
    chunks = []
    current_sents = []
    current_tok_est = 0
    
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        # Estimate tokens: ~0.75 words per token? Use words
        words_in_sent = len(sent.split())
        tok_est = int(words_in_sent * 1.33)
        
        if current_tok_est + tok_est > chunk_size_tokens and current_sents:
            # Emit chunk
            chunk_text = " ".join(current_sents)
            chunks.append({
                "text": chunk_text,
                "token_estimate": current_tok_est,
                "char_count": len(chunk_text),
                "sentence_count": len(current_sents)
            })
            # Overlap: keep last N sentences that approx overlap_tokens
            # Simple: keep sentences until overlap budget
            overlap_sents = []
            overlap_tok = 0
            for s in reversed(current_sents):
                s_tok = int(len(s.split())*1.33)
                if overlap_tok + s_tok <= overlap_tokens:
                    overlap_sents.insert(0, s)
                    overlap_tok += s_tok
                else:
                    break
            current_sents = overlap_sents + [sent]
            current_tok_est = overlap_tok + tok_est
        else:
            current_sents.append(sent)
            current_tok_est += tok_est
    
    if current_sents:
        chunk_text = " ".join(current_sents)
        chunks.append({
            "text": chunk_text,
            "token_estimate": current_tok_est,
            "char_count": len(chunk_text),
            "sentence_count": len(current_sents)
        })
    
    return chunks

def build_documents_for_embedding(articles: List[Dict[str, Any]], chunk_config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Converts PubMed articles to chunked docs with full metadata schema preserved for retrieval.
    Each chunk retains parent metadata for citation.
    """
    chunk_size = (chunk_config or {}).get('chunk_size_tokens', 512)
    overlap = (chunk_config or {}).get('chunk_overlap_tokens', 64)
    
    docs = []
    doc_id = 0
    for art in articles:
        pmid = art.get('pmid')
        doi = art.get('doi')
        title = art.get('title','')
        abstract = art.get('abstract','') or ''
        journal = art.get('journal','')
        year = art.get('year')
        mesh = [m['descriptor'] for m in art.get('mesh_terms', [])[:5]]
        
        # Combine title + abstract for embedding - critical for retrieval relevance
        full_text = f"Title: {title}\n\nAbstract: {abstract}" if abstract else title
        if not full_text.strip():
            continue
        
        chunks = sentence_aware_chunk(full_text, chunk_size_tokens=chunk_size, overlap_tokens=overlap)
        
        for idx, chunk in enumerate(chunks):
            doc_id += 1
            docs.append({
                "id": f"PMID:{pmid}_chunk{idx}" if pmid else f"DOI:{doi}_chunk{idx}" if doi else f"doc{doc_id}",
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "text": chunk['text'],
                "metadata": {
                    "pmid": pmid,
                    "doi": doi,
                    "title": title,
                    "journal": journal,
                    "year": year,
                    "mesh_terms": mesh,
                    "publication_types": art.get('publication_types', []),
                    "authors": [a.get('full_name') for a in art.get('authors', [])[:3]],
                    "citation": f"{journal} {year}; PMID:{pmid}" + (f" DOI:{doi}" if doi else ""),
                    "tier": art.get('anesthesia_classification', {}).get('tier', 'unknown'),
                    "anesthesia_score": art.get('anesthesia_classification', {}).get('score', 0)
                },
                "parent_article": art  # keep reference for rerank
            })
    logger.info(f"Built {len(docs)} chunks from {len(articles)} articles")
    return docs

class EmbeddingPipeline:
    """
    Production embedding pipeline - model agnostic.
    Supports PubMedBERT, fallback to MiniLM.
    Can run offline with sentence-transformers, or online via API.
    """
    def __init__(self, config=None):
        from .config import EmbeddingConfig
        self.config = config or EmbeddingConfig()
        self._model = None
        self._tokenizer = None
    
    def _load_model(self):
        if self._model is not None:
            return
        try:
            # Try sentence-transformers first
            from sentence_transformers import SentenceTransformer
            model_names_to_try = [self.config.model_name, self.config.fallback_model]
            last_err = None
            for mname in model_names_to_try:
                try:
                    logger.info(f"Loading embedding model {mname}")
                    self._model = SentenceTransformer(mname)
                    logger.info(f"Loaded {mname} dim={self._model.get_sentence_embedding_dimension()}")
                    break
                except Exception as e:
                    last_err = e
                    logger.warning(f"Failed to load {mname}: {e}")
            if self._model is None:
                raise last_err
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is required; dummy embeddings are forbidden in production") from exc
    
    def embed_texts(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        self._load_model()
        batch_size = batch_size or self.config.batch_size
        
        if self._model is None:
            raise RuntimeError("embedding model unavailable; refusing synthetic vectors")
        
        # Real embeddings
        all_embeds = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=True
        )
        return [emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in all_embeds]
    
    def embed_documents(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        texts = [d['text'] for d in docs]
        embeds = self.embed_texts(texts)
        for doc, emb in zip(docs, embeds):
            doc['embedding'] = emb
        return docs
    
    def build_faiss_index(self, docs: List[Dict[str, Any]], index_path: str = None):
        """
        Build FAISS index for production scale.
        Fallback to simple JSONL if faiss not installed.
        """
        index_path = index_path or self.config.index_path
        Path(index_path).mkdir(parents=True, exist_ok=True)
        
        try:
            import faiss
            import numpy as np
            
            embeddings = np.array([d['embedding'] for d in docs]).astype('float32')
            dim = embeddings.shape[1]
            # Use IVF for scale if >10k, else Flat
            if len(docs) > 10000:
                nlist = min(100, len(docs)//10)
                quantizer = faiss.IndexFlatIP(dim)  # cosine via normalized
                index = faiss.IndexIVFFlat(quantizer, dim, nlist)
                index.train(embeddings)
                index.add(embeddings)
                index.nprobe = 10
            else:
                index = faiss.IndexFlatIP(dim)
                index.add(embeddings)
            
            faiss.write_index(index, str(Path(index_path)/"faiss.index"))
            # Save metadata mapping
            with open(Path(index_path)/"metadata.jsonl", 'w') as f:
                for d in docs:
                    # Don't save embedding twice
                    meta = {k: v for k, v in d.items() if k != 'embedding'}
                    f.write(json.dumps(meta) + "\n")
            logger.info(f"FAISS index built: {index.ntotal} vectors, dim={dim}")
            return str(Path(index_path)/"faiss.index")
        except ImportError:
            logger.warning("faiss not installed, saving as JSONL for later indexing")
            with open(Path(index_path)/"embeddings.jsonl", 'w') as f:
                for d in docs:
                    f.write(json.dumps(d) + "\n")
            return str(Path(index_path)/"embeddings.jsonl")
    
    def full_pipeline(self, articles: List[Dict[str, Any]]) -> str:
        """
        End-to-end: chunk → embed → index
        Returns index path.
        """
        docs = build_documents_for_embedding(articles, {
            "chunk_size_tokens": self.config.chunk_size_tokens,
            "chunk_overlap_tokens": self.config.chunk_overlap_tokens
        })
        docs = self.embed_documents(docs)
        index_file = self.build_faiss_index(docs)
        return index_file
