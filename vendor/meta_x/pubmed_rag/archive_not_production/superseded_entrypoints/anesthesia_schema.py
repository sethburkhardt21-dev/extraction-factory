"""
Anesthesia PubMed Corpus - Full Metadata Schema
Production-ready Pydantic models with validation and MedlineDate fallback
Fixes audit issue: missing MedlineDate fallback, incomplete metadata
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
import re

# Full metadata schema with all PubMed fields
class AuthorInfo(BaseModel):
    last_name: Optional[str] = None
    fore_name: Optional[str] = None
    initials: Optional[str] = None
    full_name: str
    affiliation: Optional[str] = None
    affiliation_list: List[str] = Field(default_factory=list)
    is_first: bool = False
    is_last: bool = False
    identifier_orcid: Optional[str] = None

class JournalInfo(BaseModel):
    title: Optional[str] = None
    iso_abbreviation: Optional[str] = None
    issn: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None

class PublicationDate(BaseModel):
    year: Optional[int] = None
    month: Optional[str] = None
    day: Optional[str] = None
    medline_date: Optional[str] = None  # AUDIT FIX: fallback field
    parsed_date: Optional[datetime] = None
    season: Optional[str] = None
    
    @classmethod
    def from_pubmed_article(cls, pub_date_elem, medline_date_elem=None):
        """AUDIT FIX: Implement MedlineDate fallback parsing"""
        year = None
        month = None
        day = None
        medline_date = None
        parsed_date = None
        
        if pub_date_elem is not None:
            year_text = pub_date_elem.findtext("Year")
            if year_text and year_text.isdigit():
                year = int(year_text)
            month = pub_date_elem.findtext("Month")
            day = pub_date_elem.findtext("Day")
            season = pub_date_elem.findtext("Season")
            
            # Try to build datetime
            if year:
                try:
                    m = 1
                    if month:
                        if month.isdigit():
                            m = int(month)
                        else:
                            # Month abbrev
                            month_map = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                                         "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
                            m = month_map.get(month[:3], 1)
                    d = int(day) if day and day.isdigit() else 1
                    parsed_date = datetime(year, m, d)
                except:
                    pass
            return cls(year=year, month=month, day=day, parsed_date=parsed_date)
        
        # FALLBACK: MedlineDate parsing - CRITICAL AUDIT FIX
        if medline_date_elem is not None and medline_date_elem.text:
            medline_date = medline_date_elem.text.strip()
            # Examples: "2023 Jan-Feb", "2022 Dec", "2021", "2020 Spring"
            # Extract year via regex
            year_match = re.search(r'(19|20)\d{2}', medline_date)
            if year_match:
                year = int(year_match.group(0))
            # Try to parse full date
            try:
                # Handle "2023 Jan-Feb" etc
                parts = medline_date.split()
                if len(parts) >= 1:
                    # Extract month from string
                    month_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', medline_date, re.I)
                    if month_match:
                        month = month_match.group(0)
            except:
                pass
            
            return cls(year=year, month=month, medline_date=medline_date, parsed_date=datetime(year,1,1) if year else None)
        
        return cls()

class MeSHHeading(BaseModel):
    descriptor_name: str
    descriptor_ui: Optional[str] = None
    qualifier_name: Optional[str] = None
    qualifier_ui: Optional[str] = None
    major_topic: bool = False

class Chemical(BaseModel):
    name: str
    ui: Optional[str] = None
    registry_number: Optional[str] = None

class AnesthesiaClassification(BaseModel):
    """AUDIT FIX: Reduced FP classification with ontology"""
    is_anesthesia_core: bool = False
    is_anesthesia_related: bool = False
    confidence: float = 0.0
    subfields: List[str] = Field(default_factory=list)  # e.g., "general", "regional", "pediatric", "obstetric", "pain", "critical_care", "airway"
    evidence_terms: List[str] = Field(default_factory=list)
    exclusion_reason: Optional[str] = None

    # Ontology-based subfields
    SUBFIELD_KEYWORDS = {
        "general": ["general anesthesia", "inhaled anesthetic", "propofol", "sevoflurane", "desflurane", "induction"],
        "regional": ["regional anesthesia", "spinal anesthesia", "epidural", "nerve block", "brachial plexus", "ultrasound-guided"],
        "pediatric": ["pediatric anesthesia", "neonatal anesthesia", "children"],
        "obstetric": ["obstetric anesthesia", "labor analgesia", "cesarean"],
        "pain": ["postoperative pain", "acute pain", "chronic pain", "analgesia", "opioid"],
        "critical_care": ["critical care", "ICU", "mechanical ventilation", "hemodynamic"],
        "airway": ["airway management", "intubation", "laryngoscopy", "supraglottic airway", "difficult airway"],
        "neuroanesthesia": ["neuroanesthesia", "craniotomy", "neurosurgery"],
        "cardiac": ["cardiac anesthesia", "cardiopulmonary bypass", "TEE"],
        "pharmacology": ["pharmacokinetics", "pharmacodynamics", "anesthetic agents"],
        "safety": ["anesthesia safety", "adverse events", "malignant hyperthermia", "awareness"],
        "monitoring": ["BIS", "bispectral index", "depth of anesthesia", "neuromonitoring"]
    }

class AnesthesiaRecord(BaseModel):
    """Full production schema - max extraction"""
    pmid: str = Field(..., description="Primary stable ID for deduplication")
    pmc_id: Optional[str] = None
    doi: Optional[str] = None
    title: str
    abstract: Optional[str] = None
    abstract_sections: Dict[str, str] = Field(default_factory=dict)  # BACKGROUND, METHODS etc
    
    authors: List[AuthorInfo] = Field(default_factory=list)
    journal: JournalInfo = Field(default_factory=JournalInfo)
    pub_date: PublicationDate = Field(default_factory=PublicationDate)
    
    # MeSH and keywords
    mesh_headings: List[MeSHHeading] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    chemicals: List[Chemical] = Field(default_factory=list)
    publication_types: List[str] = Field(default_factory=list)
    
    # Classification
    classification: AnesthesiaClassification = Field(default_factory=AnesthesiaClassification)
    
    # Enrichment
    language: str = "eng"
    citation_count: Optional[int] = None
    references: List[str] = Field(default_factory=list)  # PMIDs
    grant_list: List[Dict[str,str]] = Field(default_factory=list)
    
    # Embeddings (populated later)
    embedding: Optional[List[float]] = None
    embedding_model: Optional[str] = None
    title_hash: str = ""  # For dedup
    doi_normalized: Optional[str] = None
    
    # Provenance
    retrieval_date: datetime = Field(default_factory=datetime.utcnow)
    esearch_query: Optional[str] = None
    version: str = "2.0-fixed"
    
    @validator('title_hash', pre=True, always=True)
    def compute_title_hash(cls, v, values):
        title = values.get('title','')
        import hashlib
        return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]
    
    @validator('doi_normalized', pre=True, always=True)
    def normalize_doi(cls, v, values):
        doi = values.get('doi')
        if doi:
            return doi.lower().strip().replace('https://doi.org/','').replace('http://dx.doi.org/','')
        return None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Example of full metadata extraction mapping
PUBMED_XML_FIELDS = {
    "PMID": "pmid",
    "DOI": "doi",
    "Title": "title",
    "Abstract": "abstract",
    "Authors": "authors",
    "Journal": "journal.title",
    "Year": "pub_date.year",
    "MeSH": "mesh_headings",
    "Keywords": "keywords",
    "PublicationType": "publication_types"
}
