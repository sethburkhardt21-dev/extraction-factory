"""
Anesthesia RAG Pipeline - Central Configuration
Production-grade config for max PubMed extraction with audit fixes.
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

@dataclass
class PubMedConfig:
    # Rate limiting - FIX: audit critical issue #1
    api_key: str = field(default_factory=lambda: os.getenv("NCBI_API_KEY", ""))
    # NCBI: 10 req/s with key, 3 req/s without. Use conservative sleeps.
    delay_with_key: float = 0.11  # 9 req/s safe margin
    delay_without_key: float = 0.34  # 2.9 req/s safe margin
    max_retries: int = 5
    backoff_factor: float = 2.0
    initial_backoff: float = 1.0
    timeout: int = 30
    
    # Pagination - FIX: use history server for >500
    batch_size: int = 200  # EFetch max 10000 but 200 is safe
    use_history_server: bool = True
    history_threshold: int = 500
    max_results: int = 100000
    
    # Cache - FIX: local cache to avoid re-calls
    cache_dir: str = str(DATA_DIR / "cache")
    enable_cache: bool = True
    cache_ttl_hours: int = 72
    
    # Anesthesia query - max recall
    base_query: str = (
        '(anesthesia[MeSH Terms] OR anesthesiology[MeSH Terms] OR anesthesia[Title/Abstract] '
        'OR anaesthesia[Title/Abstract] OR anesthesi*[Title/Abstract] OR anaesthesi*[Title/Abstract] '
        'OR "general anesthesia" OR "regional anesthesia" OR "local anesthesia" OR '
        'propofol OR sevoflurane OR desflurane OR rocuronium OR ketamine[Title/Abstract]) '
        'AND (humans[MeSH Terms])'
    )
    # Exclude obvious FP - FIX: classification FP reduction
    exclude_query: str = 'NOT (dental anesthesia[Title] AND case report[Publication Type])'
    
    email: str = field(default_factory=lambda: os.getenv("NCBI_EMAIL", ""))
    tool_name: str = "AnesthesiaRAGPipeline"

@dataclass
class EmbeddingConfig:
    model_name: str = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"
    fallback_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 768
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64  # ~12.5% overlap - preserves clinical phrases
    chunk_strategy: str = "sentence"  # sentence-boundary preservation - critical for clinical
    batch_size: int = 32
    normalize_embeddings: bool = True
    
    # Hybrid retrieval
    use_hybrid: bool = True
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    dense_weight: float = 0.7
    sparse_weight: float = 0.3
    
    vector_store: str = "faiss"  # faiss or chroma
    index_path: str = str(DATA_DIR / "index")

@dataclass
class AnesthesiaClassificationConfig:
    # FIX: audit classification FP - need allowlist + blocklist + MeSH grounding
    min_score: float = 0.65
    
    # High-precision MeSH terms that guarantee anesthesia relevance
    core_mesh_terms: List[str] = field(default_factory=lambda: [
        "Anesthesia", "Anesthesiology", "Anesthetics", "Analgesia",
        "Anesthesia, General", "Anesthesia, Local", "Anesthesia, Conduction",
        "Anesthesia, Inhalation", "Anesthesia, Intravenous", "Anesthesia, Spinal",
        "Anesthesia, Epidural", "Neuromuscular Blocking Agents", "Hypnotics and Sedatives"
    ])
    
    # Title/Abstract keywords with weights
    positive_keywords_weighted: Dict[str, float] = field(default_factory=lambda: {
        "general anesthesia": 3.0, "regional anesthesia": 3.0, "spinal anesthesia": 2.5,
        "epidural anesthesia": 2.5, "propofol": 2.0, "sevoflurane": 2.0, "desflurane": 2.0,
        "rocuronium": 1.5, "anesthetic management": 2.5, "anesthesia induction": 2.5,
        "anesthesia maintenance": 2.5, "perioperative": 1.0, "airway management": 1.5,
        "neuromuscular blockade": 2.0, "anesthetic technique": 2.0
    })
    
    # Negative / FP indicators - FIX: reduces false positives from adjacent fields
    negative_patterns: List[str] = field(default_factory=lambda: [
        r"\bdental caries\b", r"\banesthesia dolorosa\b", # pain condition not anesthesia procedure
        r"\blocal anesthesia\b.*\bDrosophila\b", # model organism
        r"\bplant anesthesia\b", r"\bcell anesthesia\b",
        r"^\s*Re: " # letters that mention anesthesia in passing
    ])
    
    # Journals that are strong anesthesia signal
    core_journals: List[str] = field(default_factory=lambda: [
        "Anesthesiology", "Anesthesia and Analgesia", "British Journal of Anaesthesia",
        "Anesthesia", "Acta Anaesthesiologica Scandinavica", "Canadian Journal of Anaesthesia",
        "Journal of Clinical Anesthesia", "Regional Anesthesia and Pain Medicine"
    ])

@dataclass
class RAGConfig:
    llm_model: str = ""  # no generation backend is configured by default
    temperature: float = 0.0  # deterministic for clinical
    max_context_docs: int = 8
    rerank: bool = True
    citation_required: bool = True
    max_tokens_answer: int = 1024
    # Safety
    include_disclaimer: bool = True
    require_grounding: bool = True
    refusal_if_no_evidence: bool = True

config = {
    "pubmed": PubMedConfig(),
    "embedding": EmbeddingConfig(),
    "classification": AnesthesiaClassificationConfig(),
    "rag": RAGConfig()
}
