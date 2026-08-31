"""
Full Metadata Schema - Anesthesia PubMed Extraction
Fixes audit: missing MedlineDate fallback, structured abstract, author CollectiveName, DOI fallback
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum

class Subdomain(str, Enum):
    general = "general"
    regional = "regional"
    pediatric = "pediatric"
    obstetric = "obstetric"
    cardiac = "cardiac"
    pain = "pain"
    critical_care = "critical_care"
    neuroanesthesia = "neuroanesthesia"
    ambulatory = "ambulatory"
    airway = "airway"
    pharmacology = "pharmacology"
    other = "other"

class StudyType(str, Enum):
    randomized_controlled_trial = "randomized_controlled_trial"
    systematic_review = "systematic_review"
    meta_analysis = "meta_analysis"
    clinical_trial = "clinical_trial"
    observational_cohort = "observational_cohort"
    comparative_study = "comparative_study"
    case_report = "case_report"
    case_series = "case_series"
    guideline = "guideline"
    review = "review"
    editorial = "editorial"
    other = "other"

class Author(BaseModel):
    last_name: Optional[str] = None
    fore_name: Optional[str] = None
    initials: Optional[str] = None
    collective_name: Optional[str] = None  # FIX: audit missing CollectiveName
    affiliation: Optional[str] = None

    @property
    def full_name(self) -> str:
        if self.collective_name:
            return self.collective_name
        parts = [self.fore_name, self.last_name]
        return " ".join(p for p in parts if p).strip() or self.last_name or "Unknown"

class AbstractSection(BaseModel):
    label: Optional[str] = None  # e.g., BACKGROUND, METHODS, RESULTS
    text: str

class PubMedArticle(BaseModel):
    """Full metadata schema extracted from PubMed XML with audit fixes"""
    pmid: str = Field(..., description="PubMed ID")
    pmcid: Optional[str] = None
    doi: Optional[str] = None
    title: str
    abstract: str  # concatenated
    abstract_sections: List[AbstractSection] = Field(default_factory=list)  # FIX: preserve structured labels
    authors: List[Author] = Field(default_factory=list)
    journal: Optional[str] = None
    journal_abbrev: Optional[str] = None
    issn: Optional[str] = None
    pub_year: Optional[int] = None  # FIX: MedlineDate fallback ensures not null
    pub_month: Optional[int] = None
    pub_day: Optional[int] = None
    pub_date_raw: Optional[str] = None  # original string for debugging
    medline_date_raw: Optional[str] = None  # FIX: store MedlineDate raw for audit trace
    article_date: Optional[str] = None  # Electronic publication date
    pub_types: List[str] = Field(default_factory=list)  # e.g., Journal Article, RCT
    mesh_terms: List[str] = Field(default_factory=list)
    mesh_descriptors: List[Dict[str, str]] = Field(default_factory=list)  # with UI and qualifiers
    keywords: List[str] = Field(default_factory=list)
    # Classification - FIX: reduces FP by multi-signal
    subdomain: Subdomain = Subdomain.other
    subdomain_confidence: float = 0.0
    subdomain_all_scores: Dict[str, float] = Field(default_factory=dict)
    study_type: StudyType = StudyType.other
    study_type_confidence: float = 0.0
    is_anesthesia_core: bool = True  # False if marginal, filtered
    anesthesia_relevance_score: float = 0.0
    classification_reasons: List[str] = Field(default_factory=list)  # explainability for FP debugging
    # Embeddings
    embedding: Optional[List[float]] = None  # populated after embedding
    embedding_model: Optional[str] = None
    # Deduplication signals
    title_normalized: Optional[str] = None
    doi_normalized: Optional[str] = None
    hash_dedup: Optional[str] = None  # hash of normalized title + first author last name + year

class SearchFilter(BaseModel):
    subdomain: Optional[Subdomain] = None
    subdomains: Optional[List[Subdomain]] = None  # allow multiple
    study_type: Optional[StudyType] = None
    study_types: Optional[List[StudyType]] = None
    year_from: Optional[int] = Field(None, ge=1900, le=2030)
    year_to: Optional[int] = Field(None, ge=1900, le=2030)
    journal: Optional[str] = None
    min_relevance: Optional[float] = Field(None, ge=0, le=1)

class SearchQuery(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Natural language query")
    top_k: int = Field(10, ge=1, le=100, description="Number of results")
    filters: Optional[SearchFilter] = None
    min_similarity: float = Field(0.2, ge=0, le=1, description="Minimum cosine similarity")
    include_abstract: bool = True
    rerank: bool = True

class SearchResultItem(BaseModel):
    pmid: str
    title: str
    abstract: Optional[str] = None
    abstract_sections: Optional[List[AbstractSection]] = None
    authors: List[Author]
    journal: Optional[str] = None
    pub_year: Optional[int] = None
    doi: Optional[str] = None
    subdomain: Subdomain
    subdomain_confidence: float
    study_type: StudyType
    study_type_confidence: float
    anesthesia_relevance_score: float
    mesh_terms: List[str]
    pub_types: List[str]
    similarity: float  # cosine similarity to query
    rerank_score: Optional[float] = None

class SearchResponse(BaseModel):
    query: str
    query_embedding_model: str
    top_k: int
    filters: Optional[SearchFilter]
    results: List[SearchResultItem]
    total_candidates: int
    search_time_ms: float
    cached: bool = False

class IngestRequest(BaseModel):
    pmids: Optional[List[str]] = None
    query: Optional[str] = None  # e.g., "anesthesia AND general"
    retmax: int = Field(100, ge=1, le=10000)
    generate_embeddings: bool = True

class HealthResponse(BaseModel):
    status: str
    total_papers: int
    embedding_model: str
    embedding_dim: int
    index_type: str
    uptime_seconds: float
