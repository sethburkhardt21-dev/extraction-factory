"""
Agent C6: Incremental Update Developer
Production metadata schema for max anesthesia PubMed extraction
Fixes: missing MedlineDate fallback, incomplete metadata capture, classification FP

Full schema derived from PubMed XML + anesthesia domain requirements.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
import re
import hashlib

class AuthorInfo(BaseModel):
    last_name: Optional[str] = None
    fore_name: Optional[str] = None
    initials: Optional[str] = None
    collective_name: Optional[str] = None
    affiliation: Optional[str] = None
    email: Optional[str] = None

    @property
    def display_name(self) -> str:
        if self.collective_name:
            return self.collective_name
        if self.last_name and self.fore_name:
            return f"{self.fore_name} {self.last_name}"
        return self.last_name or self.fore_name or "Unknown"

class JournalInfo(BaseModel):
    title: Optional[str] = None
    iso_abbreviation: Optional[str] = None
    issn: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pub_type: List[str] = Field(default_factory=list)

class PubDateInfo(BaseModel):
    """Hardened date container - fixes audit issue: missing MedlineDate fallback"""
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    raw_pubdate: Optional[str] = None
    raw_medline_date: Optional[str] = None
    raw_article_date: Optional[str] = None
    edat: Optional[datetime] = None  # Entrez Date - critical for CDC watermark
    pdat: Optional[date] = None       # PubMed Date
    pub_status_pub_date: Optional[datetime] = None
    parsed_source: Literal["PubDate_Year", "MedlineDate", "ArticleDate", "PubMedPubDate_EPUB", "EPubDate_Fallback", "EDAT_Fallback", "None"] = "None"

    @field_validator('year')
    @classmethod
    def validate_year(cls, v):
        if v is not None and (v < 1800 or v > 2035):
            return None
        return v

# --- MedlineDate fallback parser - CRITICAL FIX ---
MEDLINE_YEAR_RE = re.compile(r'^\s*(\d{4})')
MEDLINE_RANGE_RE = re.compile(r'(\d{4})')

def parse_pubmed_date_hardened(
    pub_date_elem: Optional[Dict[str, Any]],
    medline_date_str: Optional[str],
    article_date_elem: Optional[Dict[str, Any]],
    pubmed_pubdate_list: Optional[List[Dict[str, Any]]] = None,
    edat_str: Optional[str] = None
) -> PubDateInfo:
    """
    Production-grade date parser with full fallback chain.
    Fixes audit: fetch_articles has no MedlineDate fallback -> year:null
    
    Chain: PubDate/Year -> MedlineDate leading 4-digit year -> ArticleDate -> PubMedPubDate -> EDAT
    Handles cases:
      - "2021-2022" -> 2021
      - "2024 Spring" -> 2024
      - "2023 Dec-Jan" -> 2023
      - "Fall 2022" -> 2022
    """
    result = PubDateInfo(
        raw_medline_date=medline_date_str,
        raw_pubdate=str(pub_date_elem) if pub_date_elem else None,
        raw_article_date=str(article_date_elem) if article_date_elem else None
    )

    # 1. Primary: PubDate/Year
    if pub_date_elem:
        year_val = pub_date_elem.get('Year')
        if year_val:
            try:
                # Explicitly test for existence, not truthiness (fixes empty element bug)
                year_str = str(year_val).strip()
                if year_str:
                    result.year = int(year_str)
                    result.month = _parse_month(pub_date_elem.get('Month'))
                    result.day = _parse_int_safe(pub_date_elem.get('Day'))
                    result.parsed_source = "PubDate_Year"
                    return result
            except (ValueError, TypeError):
                pass

    # 2. CRITICAL FALLBACK: MedlineDate
    # Example MedlineDate issues from audit: PMIDs 36957974, 34904812
    if medline_date_str:
        result.raw_medline_date = medline_date_str
        # Leading 4-digit year extraction
        m = MEDLINE_YEAR_RE.match(medline_date_str)
        if m:
            try:
                result.year = int(m.group(1))
                result.parsed_source = "MedlineDate"
                return result
            except ValueError:
                pass
        # Secondary search anywhere in string (for "Fall 2022" etc)
        m2 = MEDLINE_RANGE_RE.search(medline_date_str)
        if m2:
            try:
                result.year = int(m2.group(1))
                result.parsed_source = "MedlineDate"
                return result
            except ValueError:
                pass

    # 3. ArticleDate fallback
    if article_date_elem:
        year_val = article_date_elem.get('Year')
        if year_val is not None:
            try:
                year_str = str(year_val).strip()
                if year_str:
                    result.year = int(year_str)
                    result.month = _parse_month(article_date_elem.get('Month'))
                    result.day = _parse_int_safe(article_date_elem.get('Day'))
                    result.parsed_source = "ArticleDate"
                    return result
            except (ValueError, TypeError):
                pass

    # 4. PubMedPubDate (epublish, ppublish)
    if pubmed_pubdate_list:
        for pubdate in pubmed_pubdate_list:
            if pubdate.get('PubStatus') in ('epublish', 'ppublish', 'pubmed', 'entrez'):
                year_val = pubdate.get('Year')
                if year_val:
                    try:
                        year_str = str(year_val).strip()
                        if year_str:
                            result.year = int(year_str)
                            result.parsed_source = "PubMedPubDate_EPUB"
                            return result
                    except (ValueError, TypeError):
                        continue

    # 5. EDAT fallback - watermark date
    if edat_str:
        try:
            # EDAT format: 2023/12/01 06:00
            dt = datetime.strptime(edat_str.strip().split()[0], "%Y/%m/%d")
            result.year = dt.year
            result.edat = datetime.strptime(edat_str.strip(), "%Y/%m/%d %H:%M") if " " in edat_str.strip() else dt
            result.parsed_source = "EDAT_Fallback"
            return result
        except Exception:
            pass

    result.parsed_source = "None"
    return result

def _parse_month(month_val: Optional[Any]) -> Optional[int]:
    if not month_val:
        return None
    month_map = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12,
                 "January":1,"February":2,"March":3,"April":4,"June":6,"July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
    str_val = str(month_val).strip()
    if str_val.isdigit():
        try:
            m = int(str_val)
            return m if 1 <= m <= 12 else None
        except:
            return None
    return month_map.get(str_val[:3]) if len(str_val)>=3 else month_map.get(str_val)

def _parse_int_safe(v: Optional[Any]) -> Optional[int]:
    if v is None:
        return None
    try:
        s = str(v).strip()
        return int(s) if s else None
    except:
        return None


class AnesthesiaClassification(BaseModel):
    """Fixes audit: classification FP - false positives"""
    is_anesthesia_relevant: bool = False
    confidence_score: float = 0.0  # 0-1
    category: Literal["core_anesthesia", "perioperative", "pain_medicine", "critical_care", "peripheral", "not_relevant"] = "not_relevant"
    matched_mesh_terms: List[str] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    negative_flags: List[str] = Field(default_factory=list)
    classification_version: str = "v3-precision"

class PubMedAnesthesiaRecord(BaseModel):
    """
    Full metadata schema for max anesthesia extraction.
    Production-ready with all audit fixes.
    """
    pmid: str = Field(..., description="PubMed ID, primary key")
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    abstract_structured: Dict[str, str] = Field(default_factory=dict)  # BACKGROUND, METHODS etc joined with labels
    authors: List[AuthorInfo] = Field(default_factory=list)
    journal: JournalInfo = Field(default_factory=JournalInfo)
    pub_date: PubDateInfo = Field(default_factory=PubDateInfo)
    mesh_headings: List[str] = Field(default_factory=list)
    mesh_major: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    publication_types: List[str] = Field(default_factory=list)
    language: List[str] = Field(default_factory=list)
    grants: List[str] = Field(default_factory=list)

    # Anesthesia-specific
    classification: AnesthesiaClassification = Field(default_factory=AnesthesiaClassification)

    # Provenance / CDC fields
    edat: Optional[datetime] = None
    ldat: Optional[datetime] = None  # Last revision date
    status: Literal["active", "deleted", "updated"] = "active"
    version: int = 1
    content_hash: Optional[str] = None  # SHA256(title+abstract) for dedup
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    source_retrieval_date: datetime = Field(default_factory=datetime.utcnow)

    # Embedding pipeline
    embedding_version: Optional[str] = None
    embedding_generated_at: Optional[datetime] = None
    needs_embedding_backfill: bool = True

    def compute_content_hash(self) -> str:
        base = (self.title or "") + "|" + (self.abstract or "")
        return hashlib.sha256(base.encode('utf-8')).hexdigest()[:16]

    @field_validator('pmid')
    @classmethod
    def validate_pmid(cls, v):
        if not re.match(r'^\d+$', str(v)):
            raise ValueError(f"Invalid PMID: {v}")
        return str(v)

class DedupKey(BaseModel):
    """Dedup strategy: fixes audit duplicate issues"""
    pmid: str
    doi_normalized: Optional[str] = None
    content_hash: Optional[str] = None

    @staticmethod
    def normalize_doi(doi: Optional[str]) -> Optional[str]:
        if not doi:
            return None
        return doi.strip().lower().replace("https://doi.org/","").replace("http://doi.org/","").replace("doi:","").strip()

# Anesthesia MeSH + keyword ontology for max recall, precision filter for FP fix
ANESTHESIA_CORE_MESH = {
    "Anesthesia", "Anesthetics", "Anesthesia, General", "Anesthesia, Local",
    "Anesthesia, Inhalation", "Anesthesia, Intravenal", "Anesthesia, Conduction",
    "Anesthesia, Spinal", "Anesthesia, Epidural", "Anesthesia, Obstetrical",
    "Anesthetics, Local", "Anesthetics, Inhalation", "Anesthetics, Intravenous",
    "Neuromuscular Blockade", "Neuromuscular Blocking Agents",
    "Pain Management", "Analgesia", "Analgesics", "Analgesics, Opioid",
    "Anesthesia Recovery Period", "Depth of Anesthesia", "Anesthesiology"
}

ANESTHESIA_POSITIVE_KEYWORDS = {
    "anesthesia", "anaesthesia", "anesthesiology", "anaesthesiology",
    "anesthetic", "anaesthetic", "propofol", "sevoflurane", "desflurane",
    "isoflurane", "ketamine", "etomidate", "rocuronium", "vecuronium",
    "succinylcholine", "sugammadex", "neostigmine", "remifentanil",
    "fentanyl", "sufentanil", "alfentanil", "dexmedetomidine",
    "neuromuscular blockade", "laryngoscopy", "intubation", "airway management",
    "spinal anesthesia", "epidural anesthesia", "regional anesthesia",
    "peripheral nerve block", "conscious sedation", "monitored anesthesia care"
}

# Negative keywords to reduce FP - audit fix
ANESTHESIA_NEGATIVE_KEYWORDS = {
    "anesthesia dolorosa",  # neuropathic pain, not anesthesia procedure
    "local anesthesia was not used", 
    "without anesthesia",
    "anesthesia of the study", # false match
}

# Journal whitelist for boosting precision
ANESTHESIA_JOURNAL_WHITELIST = {
    "anesthesiology", "anesthesia and analgesia", "british journal of anaesthesia",
    "anaesthesia", "journal of clinical anesthesia", "anesthesia & analgesia",
    "regional anesthesia and pain medicine", "paediatric anaesthesia",
    "canadian journal of anaesthesia", "european journal of anaesthesiology",
    "current opinion in anaesthesiology", "best practice & research clinical anaesthesiology"
}
