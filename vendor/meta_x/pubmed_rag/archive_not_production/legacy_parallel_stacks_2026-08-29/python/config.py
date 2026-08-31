"""
Production Configuration - Anesthesia Semantic Search
Fixes audit issues: rate limits, env-driven keys, caching
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional
import os
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")
    # NCBI / PubMed - fixes rate limit audit
    ncbi_email: str = os.getenv("NCBI_EMAIL", "")
    ncbi_api_key: Optional[str] = os.getenv("NCBI_API_KEY", None)
    # Rate limits: 3/s without key, 10/s with key; we enforce 0.35s and 0.12s gaps respectively
    pubmed_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    pubmed_tool: str = "AnesthesiaSemanticSearch"
    request_timeout: int = 30
    max_retries: int = 5
    backoff_base: float = 1.5
    # Backoff for 429/503 - exponential jitter

    # Embedding
    embedding_provider: Literal["sentence_transformers", "openai", "titan"] = "sentence_transformers"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"  # 384 dim fast local; prod alternative: e5-large-v2 or text-embedding-3-small
    embedding_dim: int = 384
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_embedding_model: str = "text-embedding-3-small"

    # Vector store
    vector_store_type: Literal["memory", "faiss", "pinecone"] = "memory"
    faiss_index_path: str = str(Path(__file__).resolve().parent / "data" / "faiss_anesthesia.index")
    metadata_path: str = str(Path(__file__).resolve().parent / "data" / "anesthesia_metadata.jsonl")
    pinecone_index: str = "anesthesia-papers"

    # Search defaults
    default_top_k: int = 10
    max_top_k: int = 100
    similarity_threshold: float = 0.2
    rerank_enabled: bool = True
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # for cross-encoder reranking

    # Classification thresholds - fixes FP audit
    anesthesia_similarity_threshold: float = 0.35  # minimum embedding similarity to anesthesia centroid
    fp_negative_keywords: list = []  # populated below

    # Caching
    embedding_cache_size: int = 10000
    embedding_cache_ttl: int = 3600 * 24  # 1 day

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]

settings = Settings()

# Anesthesia Subdomain Taxonomy - full metadata schema
ANESTHESIA_SUBDOMAINS = [
    "general",           # general anesthesia
    "regional",          # regional anesthesia, spinal, epidural, peripheral blocks
    "pediatric",         # pediatric anesthesia
    "obstetric",         # obstetric anesthesia
    "cardiac",           # cardiac anesthesia, cardiothoracic
    "pain",              # pain medicine, chronic pain, acute pain
    "critical_care",     # critical care, ICU
    "neuroanesthesia",   # neuroanesthesia
    "ambulatory",        # ambulatory / outpatient
    "airway",            # airway management
    "pharmacology",      # anesthesia pharmacology, pharmacokinetics
    "other"
]

STUDY_TYPES = [
    "randomized_controlled_trial",
    "systematic_review",
    "meta_analysis",
    "clinical_trial",
    "observational_cohort",
    "comparative_study",
    "case_report",
    "case_series",
    "guideline",
    "review",
    "editorial",
    "other"
]

# MeSH terms that are HIGH precision for anesthesia - fixes classification FP audit
ANESTHESIA_MESH_WHITELIST = {
    "Anesthesia",
    "Anesthesia, General",
    "Anesthesia, Inhalation",
    "Anesthesia, Intravenous",
    "Anesthesia, Epidural",
    "Anesthesia, Spinal",
    "Anesthesia, Conduction",
    "Anesthesia, Local",
    "Anesthetics",
    "Anesthetics, Inhalation",
    "Anesthetics, Intravenous",
    "Anesthetics, Local",
    "Analgesia",
    "Analgesia, Epidural",
    "Nerve Block",
    "Pain Management",
    "Intensive Care",
    "Critical Care",
    "Airway Management",
    "Anesthesiology",
}

# Subdomain MeSH mapping for classification
SUBDOMAIN_MESH_MAP = {
    "regional": {"Anesthesia, Epidural", "Anesthesia, Spinal", "Nerve Block", "Anesthesia, Conduction", "Anesthesia, Local", "Brachial Plexus Block"},
    "pediatric": {"Anesthesia", "Pediatrics", "Child", "Infant"},
    "obstetric": {"Anesthesia, Obstetrical", "Pregnancy", "Obstetrics"},
    "cardiac": {"Cardiac Surgical Procedures", "Thoracic Surgery", "Cardiopulmonary Bypass", "Anesthesia, Cardiac"},
    "pain": {"Pain", "Pain Management", "Analgesia", "Chronic Pain", "Acute Pain"},
    "critical_care": {"Critical Care", "Intensive Care Units", "Critical Illness", "Respiration, Artificial"},
    "neuroanesthesia": {"Neurosurgical Procedures", "Brain", "Craniotomy", "Anesthesia, Neurosurgical"},
    "airway": {"Airway Management", "Intubation, Intratracheal", "Laryngoscopy"},
    "pharmacology": {"Anesthetics", "Anesthetics, Inhalation", "Propofol", "Sevoflurane", "Pharmacokinetics"},
}

# Negative keywords to reduce FP - e.g., anesthesia mentioned only in passing
NEGATIVE_PATTERNS = [
    r"\bdental anesthesia not\b",  # not directly related filter could be tuned
]
# FP fix: papers that only mention anesthesia in methods section but main topic is not anesthesia
# We use: require MeSH whitelist OR title/abstract contains anesthesia AND embedding similarity > threshold
