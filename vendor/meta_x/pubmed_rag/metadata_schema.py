"""
Canonical PubMed source metadata schema.

This module contains source-derived fields only. Classification, duplicate-work
heuristics, embeddings, and RAG state belong to downstream enrichment tables.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator, ConfigDict
import re
from enum import Enum

class PublicationType(str, Enum):
    JOURNAL_ARTICLE = "Journal Article"
    REVIEW = "Review"
    RANDOMIZED_CONTROLLED_TRIAL = "Randomized Controlled Trial"
    META_ANALYSIS = "Meta-Analysis"
    CASE_REPORT = "Case Reports"
    CLINICAL_TRIAL = "Clinical Trial"
    GUIDELINE = "Guideline"
    LETTER = "Letter"
    EDITORIAL = "Editorial"

class PubDateModel(BaseModel):
    """Robust date handling with MedlineDate fallback chain"""
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    medline_date_str: Optional[str] = None  # e.g. "2020 Jan-Feb", "2019 Fall", "2021"
    raw_pubdate: Optional[Dict] = None
    parsed_date: Optional[date] = None
    date_source: str = Field(description="source of date: PubDate|ArticleDate|MedlineDate|PubMedPubDate|Fallback")

    @classmethod
    def parse_medline_date(cls, medline_date: str) -> Optional[date]:
        """
        CRITICAL FIX: MedlineDate fallback parsing
        MedlineDate formats: "2020", "2020 Jan", "2020 Jan-Feb", "2019 Fall", "2020 Dec 12"
        """
        if not medline_date:
            return None
        
        # Try to extract year/month/day with regex - handles all weird MedlineDate cases
        patterns = [
            # 2020 Dec 12, 2020 Dec
            r'(?P<year>\d{4})\s+(?P<mon>[A-Za-z]{3,9})(?:\s+(?P<day>\d{1,2}))?',
            # 2020
            r'(?P<year>\d{4})',
        ]
        month_map = {
            'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,
            'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'september':9,
            'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12,
            'fall':10,'winter':1,'spring':4,'summer':7
        }
        for pat in patterns:
            m = re.search(pat, medline_date, re.IGNORECASE)
            if m:
                try:
                    year = int(m.groupdict().get('year') or 0)
                    mon_str = (m.groupdict().get('mon') or '').lower()
                    month = month_map.get(mon_str[:3], None) if mon_str else None
                    # Also try full name match
                    if not month and mon_str:
                        month = month_map.get(mon_str, 1)
                    day_str = m.groupdict().get('day')
                    day = int(day_str) if day_str else 1
                    if year:
                        return date(year, month or 1, day)
                except Exception:
                    continue
        return None

    @classmethod
    def from_pubmed_article(cls, article: Dict) -> 'PubDateModel':
        """
        PubDate fallback chain (audit fix):
        1. Article/ Journal/ JournalIssue/ PubDate (structured)
        2. Article/ ArticleDate
        3. MedlineDate (JournalIssue)
        4. PubMedPubDate - pubmed, entrez, medline
        """
        # Parser-populated convenience factory.
        # Actual parsing done in extraction pipeline
        return cls(date_source="unknown")

class AuthorModel(BaseModel):
    last_name: Optional[str] = None
    fore_name: Optional[str] = None
    initials: Optional[str] = None
    collective_name: Optional[str] = None
    affiliation: Optional[str] = None  # first affiliation, retained for compatibility
    affiliations: List[str] = Field(default_factory=list)
    identifiers: Dict[str, str] = Field(default_factory=dict)
    email: Optional[str] = None

class MeshHeadingModel(BaseModel):
    descriptor_name: str
    descriptor_ui: Optional[str] = None
    qualifier_name: Optional[str] = None  # first qualifier, retained for compatibility
    qualifier_ui: Optional[str] = None
    qualifiers: List[Dict[str, Any]] = Field(default_factory=list)
    major_topic: bool = False

class PubMedRecordFull(BaseModel):
    """
    Full metadata schema for max anesthesia extraction
    Includes all PubMed EFetch fields
    """
    # Core IDs - source identity
    record_type: str = "journal_article"  # journal_article | book_article
    pmid: str = Field(..., description="Primary PubMed source identity")
    doi: Optional[str] = Field(None, description="Secondary dedup key")
    pmc_id: Optional[str] = None
    version: Optional[str] = None

    # Title / Abstract - embedding inputs
    title: str
    abstract: str = ""
    abstract_sections: List[Dict[str, str]] = Field(default_factory=list)  # e.g. BACKGROUND, METHODS
    title_truncated: bool = False

    # Authors & Journal
    authors: List[AuthorModel] = Field(default_factory=list)
    journal: Optional[str] = None
    journal_abbrev: Optional[str] = None
    journal_issn: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None

    # Dates - critical with MedlineDate fallback
    pub_date: PubDateModel
    article_date: Optional[PubDateModel] = None
    pubmed_pub_dates: Dict[str, PubDateModel] = Field(default_factory=dict)  # pubmed, entrez, medline
    date_created: Optional[datetime] = None
    date_completed: Optional[datetime] = None
    date_revised: Optional[datetime] = None

    # MeSH & Keywords - for classification FP fix
    mesh_headings: List[MeshHeadingModel] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    publication_types: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    chemicals: List[Dict[str, Any]] = Field(default_factory=list)
    grants: List[Dict[str, Any]] = Field(default_factory=list)
    article_ids: Dict[str, str] = Field(default_factory=dict)
    references: List[Dict[str, Any]] = Field(default_factory=list)
    publication_status: Optional[str] = None
    book_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Retrieval provenance. Cross-record duplicate/work inference is downstream.
    retrieval_query: Optional[str] = None
    retrieval_queries: List[str] = Field(default_factory=list)
    retrieval_source: str = "pubmed_esearch_efetch"
    source_url: Optional[str] = None
    run_id: Optional[str] = None
    parser_version: str = "pubmed-canonical-3.0"
    canonical_schema_version: str = "pubmed-record-3.0"
    source_record_sha256: Optional[str] = None
    retrieved_at: Optional[datetime] = None

    # Full raw for audit / deterministic reparsing
    raw_xml: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator('pmid')
    @classmethod
    def pmid_must_be_digits(cls, v):
        if not re.match(r'^\d+$', v):
            raise ValueError(f"PMID must be digits, got {v}")
        return v
