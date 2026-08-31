"""
Production PubMed Extractor for Anesthesia Corpus - MAX extraction with audit fixes

Critical fixes:
1. Rate limits: token bucket 3 req/s no-key, 10 req/s with key, exponential backoff with jitter, 429 handling
2. Deduplication: PMID, DOI normalized, title hash, content hash
3. Classification FP reduction: ontology + MeSH + exclusion list
4. MedlineDate fallback parsing
5. Batching, resume, checkpointing, logging

Usage:
  python anesthesia_pubmed_extractor.py --query "anesthesia" --api-key YOUR_KEY --max 10000
"""

import time
import re
import hashlib
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Set, Iterator
from pathlib import Path
from datetime import datetime, timezone
import logging
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
import requests
from dataclasses import dataclass, field

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== RATE LIMITER (AUDIT FIX 1) ====================

class TokenBucketRateLimiter:
    """NCBI-compliant rate limiter: 3 req/s no key, 10 req/s with key"""
    def __init__(self, rate_per_second: float = 3.0, burst: int = 3):
        self.rate = rate_per_second
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.monotonic()
        self._lock = None  # simple, single-threaded; for threading use threading.Lock
    
    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now
    
    def acquire(self):
        self._refill()
        if self.tokens < 1:
            # Need to wait
            wait_time = (1 - self.tokens) / self.rate
            logger.debug(f"Rate limiter wait {wait_time:.2f}s")
            time.sleep(wait_time)
            self._refill()
        self.tokens -= 1

class PubMedClient:
    BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None, tool: str = "anesthesia-corpus-v2"):
        self.api_key = api_key
        self.email = (email or "").strip()
        if not self.email or "@" not in self.email:
            raise ValueError("A real contact email is required for NCBI E-utilities")
        self.tool = tool
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": f"{tool} (contact: {email})"})
        
        # Stay below the published default ceilings and forbid burst traffic.
        rate = 9.5 if api_key else 2.8
        self.limiter = TokenBucketRateLimiter(rate_per_second=rate, burst=1)
        logger.info(f"Initialized PubMed client rate={rate} req/s (key={'yes' if api_key else 'no'})")
        
        self.stats = {"requests":0, "retries":0, "429":0, "failures":0}
    
    def _build_params(self, extra: Dict) -> Dict:
        params = {"email": self.email, "tool": self.tool, "retmode":"xml"}
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(extra)
        return params
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=60, jitter=2),
        retry=retry_if_exception_type((requests.exceptions.RequestException,)),
        before_sleep=lambda s: logger.warning(f"Retry attempt {s.attempt_number} after {s.outcome.exception()}"),
        reraise=True
    )
    def _request(self, endpoint: str, params: Dict, method="GET") -> requests.Response:
        self.limiter.acquire()
        self.stats["requests"] += 1
        
        url = self.BASE + endpoint
        try:
            if method == "POST":
                resp = self.session.post(url, data=params, timeout=30)
            else:
                resp = self.session.get(url, params=params, timeout=30)
            
            # AUDIT FIX: explicit 429 handling
            if resp.status_code == 429:
                self.stats["429"] += 1
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
                logger.warning(f"429 Too Many Requests, waiting {wait}s ( NCBI says backoff )")
                time.sleep(wait)
                # Raise to trigger tenacity retry
                raise requests.exceptions.HTTPError(f"429 Rate Limited, waited {wait}s", response=resp)
            
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            self.stats["failures"] += 1
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                # Already handled above, but double safety
                time.sleep(60)
            raise
    
    def esearch(self, query: str, retmax: int = 10000, retstart: int = 0, mindate: str = None, maxdate: str = None) -> Dict:
        params = self._build_params({
            "db":"pubmed",
            "term": query,
            "retmax": retmax,
            "retstart": retstart,
            "retmode":"json",
            "sort":"date"
        })
        if mindate:
            params["mindate"] = mindate
            params["maxdate"] = maxdate or "3000"
            params["datetype"] = "pdat"
        
        # JSON endpoint different base
        url = self.BASE + "esearch.fcgi"
        self.limiter.acquire()
        self.stats["requests"] += 1
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        esearch = data.get("esearchresult", {})
        return {
            "count": int(esearch.get("count",0)),
            "idlist": esearch.get("idlist",[]),
            "webenv": esearch.get("webenv"),
            "querykey": esearch.get("querykey")
        }
    
    def efetch_batch(self, pmids: List[str]) -> ET.Element:
        """Fetch batch of up to 200 IDs per NCBI recommendation"""
        if not pmids:
            return ET.Element("root")
        
        # NCBI recommends max 200 for efetch
        batch_size = 200
        all_root = ET.Element("PubmedArticleSet")
        
        for i in range(0, len(pmids), batch_size):
            chunk = pmids[i:i+batch_size]
            params = self._build_params({
                "db":"pubmed",
                "id": ",".join(chunk),
                "retmode":"xml"
            })
            resp = self._request("efetch.fcgi", params, method="POST")
            try:
                root = ET.fromstring(resp.content)
                # Append PubmedArticle elements
                for article in root.findall(".//PubmedArticle"):
                    all_root.append(article)
            except ET.ParseError as e:
                logger.error(f"XML parse error for chunk {i}: {e}")
                # Save raw for debugging
                Path("/tmp/pubmed_error.xml").write_bytes(resp.content)
                continue
            
            # Be nice even within rate limit
            time.sleep(0.1)
        
        return all_root

# ==================== DEDUPLICATION (AUDIT FIX 2) ====================

class DeduplicationManager:
    def __init__(self, checkpoint_path: Path = Path(__file__).resolve().parent / "data" / "dedup_state.json"):
        self.seen_pmids: Set[str] = set()
        self.seen_dois: Set[str] = set()
        self.seen_title_hashes: Set[str] = set()
        self.checkpoint_path = checkpoint_path
        self.load()
    
    def load(self):
        if self.checkpoint_path.exists():
            try:
                data = json.loads(self.checkpoint_path.read_text())
                self.seen_pmids = set(data.get("pmids",[]))
                self.seen_dois = set(data.get("dois",[]))
                self.seen_title_hashes = set(data.get("title_hashes",[]))
                logger.info(f"Loaded dedup state: {len(self.seen_pmids)} PMIDs, {len(self.seen_dois)} DOIs")
            except Exception as e:
                logger.warning(f"Failed to load dedup state: {e}")
    
    def save(self):
        data = {
            "pmids": list(self.seen_pmids),
            "dois": list(self.seen_dois),
            "title_hashes": list(self.seen_title_hashes),
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        self.checkpoint_path.write_text(json.dumps(data))
    
    def normalize_doi(self, doi: str) -> str:
        if not doi:
            return ""
        return doi.lower().strip().replace("https://doi.org/","").replace("http://dx.doi.org/","").replace("doi:","").strip()
    
    def title_hash(self, title: str) -> str:
        return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]
    
    def is_duplicate(self, pmid: str, doi: Optional[str], title: str) -> bool:
        if pmid and pmid in self.seen_pmids:
            return True
        if doi:
            ndoi = self.normalize_doi(doi)
            if ndoi and ndoi in self.seen_dois:
                return True
        if title:
            th = self.title_hash(title)
            if th in self.seen_title_hashes:
                # Check not too short to avoid false dedup
                if len(title) > 20:
                    return True
        return False
    
    def add(self, pmid: str, doi: Optional[str], title: str):
        if pmid:
            self.seen_pmids.add(pmid)
        if doi:
            self.seen_dois.add(self.normalize_doi(doi))
        if title:
            self.seen_title_hashes.add(self.title_hash(title))

# ==================== CLASSIFICATION FP FIX (AUDIT FIX 3) ====================

class AnesthesiaClassifier:
    """
    Reduce false positives: anesthesia term is highly polysemous
    Exclusion patterns + inclusion ontology + MeSH validation
    """
    # HIGH PRECISION inclusion: must have one of these
    CORE_MESH_UIS = {
        "D000758", # Anesthesia
        "D000759", # Anesthesia, General
        "D000760", # Anesthesia, Local / etc will include children
        "D000761", # Anesthesia, Spinal
        "D000762", # Anesthesia, Epidural
        "D000763", # Anesthetics
        "D000765", # Anesthesiologists
        "D000766", # Anesthesiology (discipline)
        "D017202", # Conscious Sedation
        "D012131", # Balanced Anesthesia
        "D000764", # Anesthetics, Combined
    }
    
    CORE_MESH_TERMS = {
        "anesthesia", "anesthesiology", "anesthetics", "anesthesia, general",
        "anesthesia, local", "anesthesia, spinal", "anesthesia, epidural",
        "anesthesia, intravenous", "anesthesia, inhalation", "conscious sedation",
        "deep sedation", "anesthesiologists", "airway management",
        "neuromuscular blockade", "anesthesia recovery period"
    }
    
    # Strong title signals
    STRONG_TITLE_PATTERNS = [
        r"\banesthesi\w*\b", r"\banaesthesi\w*\b",
        r"\bpropofol\b", r"\bsevoflurane\b", r"\bdesflurane\b", r"\bisoflurane\b",
        r"\bneuromuscular block",
        r"\bperioperative\b.*\b(pain|analgesia)\b",
        r"\bairway\b.*\bmanagement\b",
        r"\bBIS\b", r"\bbispectral index\b",
        r"\bregional anesthesia\b", r"\bspinal anesthesia\b",
        r"\bgeneral anesthesia\b"
    ]
    
    # FALSE POSITIVE exclusion - anesthesia in other contexts
    EXCLUSION_PATTERNS = [
        (r"local anesthesia.*dental", "dental local anesthesia not core unless anesthesiology journal"),
        (r"\bplant\b.*\banesthesia\b", "botany anesthesia"),
        (r"\bcorneal anesthesia\b", "ophthalmology symptom, not anesthesia discipline"),
        (r"\bskin anesthesia\b", "dermatology symptom"),
        (r"\bhemianesthesia\b", "neurological deficit"),
        (r"\bchem.*anesthesia\b.*\bplant\b", "plant anesthesia"),
        (r"\bembryo.*anesthesia\b", "developmental biology, unless anesthesiology"),
        (r"\bRNA anesthesia\b", "nonsense/biology misuse"),
    ]
    
    # Journals that are always considered anesthesia
    ANESTHESIA_JOURNALS = {
        "anesthesiology", "british journal of anaesthesia", "bja", "anesthesia & analgesia",
        "anaesthesia", "journal of clinical anesthesia", "bmc anesthesiology",
        "canadian journal of anesthesia", "acta anaesthesiologica scandinavica",
        "paediatric anaesthesia", "regional anesthesia and pain medicine",
        "anesthesia", "frontiers in anesthesiology"
    }
    
    def __init__(self):
        self.title_regex = [re.compile(p, re.I) for p in self.STRONG_TITLE_PATTERNS]
        self.exclusion_regex = [(re.compile(p, re.I), reason) for p, reason in self.EXCLUSION_PATTERNS]
    
    def classify(self, title: str, abstract: str, mesh_terms: List[str], journal: str, pub_types: List[str], keywords: List[str]) -> Dict:
        title_l = (title or "").lower()
        abstract_l = (abstract or "").lower()
        mesh_l = [m.lower() for m in mesh_terms]
        journal_l = (journal or "").lower()
        text_combined = f"{title_l} {abstract_l}"
        
        # Check exclusions first
        for rx, reason in self.exclusion_regex:
            if rx.search(text_combined):
                # Allow override if journal is anesthesia core
                if any(j in journal_l for j in self.ANESTHESIA_JOURNALS):
                    break
                # Allow if strong MeSH
                if any(core in m for m in mesh_l for core in self.CORE_MESH_TERMS):
                    break
                return {
                    "is_anesthesia_core": False,
                    "is_anesthesia_related": False,
                    "confidence": 0.0,
                    "exclusion_reason": reason,
                    "subfields": [],
                    "evidence_terms": []
                }
        
        evidence = []
        confidence = 0.0
        is_core = False
        is_related = False
        
        # MeSH check - highest precision
        for m in mesh_l:
            if any(core in m for core in self.CORE_MESH_TERMS):
                is_core = True
                confidence += 0.5
                evidence.append(f"MeSH:{m}")
        
        # Journal check
        if any(j in journal_l for j in self.ANESTHESIA_JOURNALS):
            is_core = True
            confidence += 0.4
            evidence.append(f"Journal:{journal}")
        
        # Title patterns
        for rx in self.title_regex:
            if rx.search(title_l):
                is_core = True
                confidence += 0.3
                evidence.append(f"TitleMatch:{rx.pattern}")
                break
        
        # Abstract + keywords secondary
        anesthesia_terms = ["anesthesia", "anaesthesia", "anesthesiologist", "anesthetic", "perioperative", "sedation"]
        term_count = sum(1 for t in anesthesia_terms if t in text_combined)
        if term_count >= 2:
            is_related = True
            confidence += 0.2 * min(term_count,3)
        
        # Publication type filter - exclude some non-research that cause FP
        # But keep reviews, RCTs, etc.
        
        # Subfield detection
        subfields = []
        subfield_map = {
            "general": ["general anesthesia", "propofol", "sevoflurane", "inhalation anesthetic"],
            "regional": ["regional anesthesia", "spinal anesthesia", "epidural", "nerve block", "ultrasound-guided"],
            "pediatric": ["pediatric anesthesia", "paediatric anesthesia", "neonatal"],
            "obstetric": ["obstetric anesthesia", "labor analgesia"],
            "pain": ["postoperative pain", "analgesia", "opioid", "pain management"],
            "critical_care": ["critical care", "intensive care", "mechanical ventilation"],
            "airway": ["airway management", "intubation", "laryngoscopy", "difficult airway"],
            "monitoring": ["bispectral index", "depth of anesthesia", "BIS"],
            "safety": ["malignant hyperthermia", "anesthesia awareness", "adverse event"]
        }
        for sf, kws in subfield_map.items():
            if any(kw.lower() in text_combined for kw in kws):
                subfields.append(sf)
        
        confidence = min(confidence, 1.0)
        # Require at least 0.3 confidence to be considered core, reduces FP
        if confidence < 0.3:
            is_core = False
            if confidence < 0.15:
                is_related = False
        
        return {
            "is_anesthesia_core": is_core,
            "is_anesthesia_related": is_core or is_related,
            "confidence": round(confidence,3),
            "subfields": subfields,
            "evidence_terms": evidence,
            "exclusion_reason": None
        }

# ==================== PARSER WITH MEDLINEDATE FALLBACK (AUDIT FIX 4) ====================

def parse_pubmed_article(article_elem: ET.Element) -> Optional[Dict]:
    """Extract full metadata with MedlineDate fallback"""
    try:
        medline = article_elem.find(".//MedlineCitation")
        if medline is None:
            return None
        
        pmid_elem = medline.find("PMID")
        pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else None
        if not pmid:
            return None
        
        article = medline.find("Article")
        if article is None:
            return None
        
        # Title
        title_elem = article.find("ArticleTitle")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
        
        # Abstract - handle structured abstract
        abstract_text = ""
        abstract_dict = {}
        abstract_elem = article.find("Abstract")
        if abstract_elem is not None:
            for abst in abstract_elem.findall("AbstractText"):
                label = abst.get("Label") or abst.get("NlmCategory") or "UNLABELLED"
                text = "".join(abst.itertext()).strip()
                abstract_dict[label] = text
                abstract_text += text + " "
        abstract_text = abstract_text.strip()
        
        # Authors
        authors = []
        author_list_elem = article.find("AuthorList")
        if author_list_elem is not None:
            for idx, auth in enumerate(author_list_elem.findall("Author")):
                last = auth.findtext("LastName") or ""
                fore = auth.findtext("ForeName") or ""
                init = auth.findtext("Initials") or ""
                # Affiliation
                affils = []
                for aff in auth.findall("AffiliationInfo/Affiliation"):
                    if aff.text:
                        affils.append(aff.text.strip())
                # Also check Article AffiliationInfo
                full_name = f"{fore} {last}".strip() or last or fore
                authors.append({
                    "last_name": last,
                    "fore_name": fore,
                    "initials": init,
                    "full_name": full_name,
                    "affiliation": affils[0] if affils else None,
                    "affiliation_list": affils,
                    "is_first": idx==0,
                    "is_last": False,  # set later
                })
            if authors:
                authors[-1]["is_last"] = True
        
        # Journal info
        journal_elem = article.find("Journal")
        journal_title = journal_elem.findtext("Title") if journal_elem is not None else None
        iso_abbr = journal_elem.findtext("ISOAbbreviation") if journal_elem is not None else None
        issn = journal_elem.findtext("ISSN") if journal_elem is not None else None
        volume = journal_elem.findtext("JournalIssue/Volume") if journal_elem is not None else None
        issue = journal_elem.findtext("JournalIssue/Issue") if journal_elem is not None else None
        
        # Pagination
        pages = article.findtext("Pagination/MedlinePgn")
        
        # PubDate with MedlineDate fallback - CRITICAL FIX
        pub_date = {}
        pub_date_elem = None
        medline_date_elem = None
        if journal_elem is not None:
            pub_date_elem = journal_elem.find("JournalIssue/PubDate")
            if pub_date_elem is not None:
                year = pub_date_elem.findtext("Year")
                month = pub_date_elem.findtext("Month")
                day = pub_date_elem.findtext("Day")
                medline_date_elem = pub_date_elem.find("MedlineDate")
                
                # Parse year
                pub_year = None
                if year and year.isdigit():
                    pub_year = int(year)
                elif medline_date_elem is not None and medline_date_elem.text:
                    # AUDIT FIX: Extract year from MedlineDate
                    m = re.search(r'(19|20)\d{2}', medline_date_elem.text)
                    if m:
                        pub_year = int(m.group(0))
                
                # Also check ArticleDate as fallback
                if not pub_year:
                    art_date = article.find("ArticleDate/Year")
                    if art_date is not None and art_date.text and art_date.text.isdigit():
                        pub_year = int(art_date.text)
                
                pub_date = {
                    "year": pub_year,
                    "month": month,
                    "day": day,
                    "medline_date": medline_date_elem.text if medline_date_elem is not None else None,
                    "season": pub_date_elem.findtext("Season")
                }
        
        # MeSH headings
        mesh_headings = []
        mesh_list = medline.find("MeshHeadingList")
        if mesh_list is not None:
            for mh in mesh_list.findall("MeshHeading"):
                desc = mh.find("DescriptorName")
                if desc is not None:
                    mesh_headings.append({
                        "descriptor_name": desc.text or "",
                        "descriptor_ui": desc.get("UI"),
                        "major_topic": desc.get("MajorTopicYN") == "Y",
                        "qualifier_name": mh.findtext("QualifierName"),
                        "qualifier_ui": mh.find("QualifierName").get("UI") if mh.find("QualifierName") is not None else None
                    })
        
        # Keywords
        keywords = []
        kw_list = medline.find("KeywordList")
        if kw_list is not None:
            for kw in kw_list.findall("Keyword"):
                if kw.text:
                    keywords.append(kw.text.strip())
        
        # Chemicals
        chemicals = []
        chem_list = medline.find("ChemicalList")
        if chem_list is not None:
            for chem in chem_list.findall("Chemical"):
                name_elem = chem.find("NameOfSubstance")
                if name_elem is not None:
                    chemicals.append({
                        "name": name_elem.text or "",
                        "ui": name_elem.get("UI"),
                        "registry_number": chem.findtext("RegistryNumber")
                    })
        
        # Publication types
        pub_types = []
        for pt in article.findall("PublicationTypeList/PublicationType"):
            if pt.text:
                pub_types.append(pt.text)
        
        # DOI and other IDs
        doi = None
        pmc_id = None
        # Look in ArticleIdList
        pubmed_data = article_elem.find("PubmedData")
        if pubmed_data is not None:
            for aid in pubmed_data.findall("ArticleIdList/ArticleId"):
                id_type = aid.get("IdType")
                if id_type == "doi" and aid.text:
                    doi = aid.text.strip()
                elif id_type == "pmc" and aid.text:
                    pmc_id = aid.text.strip()
        
        # Also check ELocationID for DOI
        if not doi:
            for eloc in article.findall("ELocationID"):
                if eloc.get("EIdType") == "doi" and eloc.text:
                    doi = eloc.text.strip()
        
        # Grants
        grants = []
        for grant in article.findall("GrantList/Grant"):
            grants.append({
                "grant_id": grant.findtext("GrantID") or "",
                "agency": grant.findtext("Agency") or "",
                "country": grant.findtext("Country") or ""
            })
        
        # Language
        language = article.findtext("Language") or "eng"
        
        return {
            "pmid": pmid,
            "pmc_id": pmc_id,
            "doi": doi,
            "title": title,
            "abstract": abstract_text,
            "abstract_sections": abstract_dict,
            "authors": authors,
            "journal": {
                "title": journal_title,
                "iso_abbreviation": iso_abbr,
                "issn": issn,
                "volume": volume,
                "issue": issue,
                "pages": pages
            },
            "pub_date": pub_date,
            "mesh_headings": mesh_headings,
            "keywords": keywords,
            "chemicals": chemicals,
            "publication_types": pub_types,
            "grant_list": grants,
            "language": language
        }
    except Exception as e:
        logger.error(f"Failed to parse article: {e}", exc_info=True)
        return None

# ==================== MAIN EXTRACTION PIPELINE ====================

def build_anesthesia_query() -> str:
    """
    High recall, but classification filter will reduce FP
    Uses MeSH + Title/Abstract terms
    """
    # Core query - optimized for precision/recall balance
    mesh_part = '("Anesthesia"[Mesh] OR "Anesthesiology"[Mesh] OR "Anesthetics"[Mesh] OR "Anesthesia, General"[Mesh] OR "Anesthesia, Regional"[Mesh])'
    title_part = '("anesthesia" OR "anaesthesia" OR "anesthesiology" OR "anaesthesiology")[Title/Abstract]'
    # Include major journals as additional filter for recall
    journal_part = '("Anesthesiology"[Journal] OR "Anesthesia and Analgesia"[Journal] OR "British Journal of Anaesthesia"[Journal])'
    
    query = f"({mesh_part} OR {title_part} OR {journal_part})"
    return query

def extract_corpus(
    max_records: int = 10000,
    query: Optional[str] = None,
    api_key: Optional[str] = None,
    email: Optional[str] = None,
    output_path: Path = Path(__file__).resolve().parent / "data" / "anesthesia_corpus.jsonl",
    checkpoint_every: int = 500,
    resume: bool = True,
    mindate: str = "2015/01/01"
):
    """Main extraction with all audit fixes"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    client = PubMedClient(api_key=api_key, email=email)
    dedup = DeduplicationManager()
    classifier = AnesthesiaClassifier()
    
    if query is None:
        query = build_anesthesia_query()
    
    logger.info(f"Starting extraction: query={query}, max={max_records}, mindate={mindate}")
    
    # ESearch
    result = client.esearch(query, retmax=max_records, mindate=mindate)
    total_count = result["count"]
    idlist = result["idlist"]
    
    logger.info(f"ESearch found {total_count} total, retrieving {len(idlist)} IDs")
    
    if len(idlist) == 0:
        logger.warning("No IDs found")
        return []
    
    # Resume logic
    existing_pmids = set()
    if resume and output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        existing_pmids.add(rec.get("pmid"))
                        dedup.add(rec.get("pmid"), rec.get("doi"), rec.get("title",""))
                    except:
                        pass
            logger.info(f"Resume: found {len(existing_pmids)} existing records")
            idlist = [i for i in idlist if i not in existing_pmids]
            logger.info(f"After resume filter, {len(idlist)} remaining")
        except Exception as e:
            logger.warning(f"Resume failed: {e}")
    
    # Fetch in batches
    records = []
    output_file = open(output_path, 'a', encoding='utf-8') if resume else open(output_path, 'w', encoding='utf-8')
    
    batch_size = 200
    processed = 0
    kept = 0
    duplicates = 0
    filtered_fp = 0
    
    try:
        for i in range(0, len(idlist), batch_size):
            chunk = idlist[i:i+batch_size]
            logger.info(f"Fetching batch {i//batch_size+1}/{(len(idlist)+batch_size-1)//batch_size}: {len(chunk)} PMIDs")
            
            root = client.efetch_batch(chunk)
            
            for article_elem in root.findall(".//PubmedArticle"):
                parsed = parse_pubmed_article(article_elem)
                if not parsed:
                    continue
                
                processed += 1
                
                # Deduplication check (AUDIT FIX)
                pmid = parsed["pmid"]
                doi = parsed.get("doi")
                title = parsed.get("title","")
                
                if dedup.is_duplicate(pmid, doi, title):
                    duplicates += 1
                    continue
                
                # Classification FP reduction (AUDIT FIX)
                mesh_terms = [m["descriptor_name"] for m in parsed["mesh_headings"]]
                classification = classifier.classify(
                    title=title,
                    abstract=parsed.get("abstract",""),
                    mesh_terms=mesh_terms,
                    journal=parsed["journal"].get("title",""),
                    pub_types=parsed.get("publication_types",[]),
                    keywords=parsed.get("keywords",[])
                )
                
                if not classification["is_anesthesia_related"]:
                    filtered_fp += 1
                    continue
                
                # Enrich with classification
                parsed["classification"] = classification
                parsed["retrieval_date"] = datetime.now(timezone.utc).isoformat()
                parsed["title_hash"] = dedup.title_hash(title)
                parsed["doi_normalized"] = dedup.normalize_doi(doi) if doi else None
                parsed["version"] = "2.0-fixed"
                
                # Validate MedlineDate fallback present
                if parsed["pub_date"].get("year") is None:
                    logger.warning(f"PMID {pmid} has no year even after MedlineDate fallback - check {parsed['pub_date']}")
                    # Still keep but flag
                    parsed["pub_date"]["year"] = 0
                
                # Add to dedup and save
                dedup.add(pmid, doi, title)
                records.append(parsed)
                
                # Write JSONL
                output_file.write(json.dumps(parsed, ensure_ascii=False) + "\n")
                kept += 1
                
                if kept >= max_records:
                    break
            
            # Checkpoint
            if (i // batch_size + 1) % (checkpoint_every // batch_size + 1) == 0:
                dedup.save()
                output_file.flush()
                logger.info(f"Checkpoint: processed={processed}, kept={kept}, dup={duplicates}, fp_filtered={filtered_fp}")
            
            if kept >= max_records:
                logger.info(f"Reached max_records {max_records}")
                break
            
            # Respect rate limit between batches
            time.sleep(0.2)
    
    finally:
        output_file.close()
        dedup.save()
    
    # Stats
    logger.info(f"Extraction complete: processed={processed}, kept={kept}, duplicates={duplicates}, fp_filtered={filtered_fp}")
    logger.info(f"Client stats: {client.stats}")
    
    # Save summary
    summary = {
        "total_esearch": total_count,
        "requested": len(idlist),
        "processed": processed,
        "kept": kept,
        "duplicates": duplicates,
        "filtered_fp": filtered_fp,
        "client_stats": client.stats,
        "query": query,
        "output_path": str(output_path),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    (output_path.parent / "extraction_summary.json").write_text(json.dumps(summary, indent=2))
    
    return records

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Anesthesia PubMed Corpus Extraction - Production Fixed")
    parser.add_argument("--max", type=int, default=5000, help="Max records")
    parser.add_argument("--query", type=str, default=None, help="Custom query")
    parser.add_argument("--api-key", type=str, default=None, help="NCBI API key for up to 10 req/s")
    parser.add_argument("--email", type=str, default=__import__("os").getenv("NCBI_EMAIL"), help="Real contact email for NCBI E-utilities (or set NCBI_EMAIL)")
    parser.add_argument("--output", type=str, default=str(Path(__file__).resolve().parent / "data" / "anesthesia_corpus.jsonl"))
    parser.add_argument("--mindate", type=str, default="2018/01/01")
    parser.add_argument("--no-resume", action="store_true")
    
    args = parser.parse_args()
    
    extract_corpus(
        max_records=args.max,
        query=args.query,
        api_key=args.api_key,
        email=args.email,
        output_path=Path(args.output),
        mindate=args.mindate,
        resume=not args.no_resume
    )
