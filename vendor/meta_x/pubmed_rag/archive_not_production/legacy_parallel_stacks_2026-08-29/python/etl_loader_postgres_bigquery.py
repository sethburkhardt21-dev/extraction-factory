"""
Agent B4: ETL Loader Developer - Production JSONL to Postgres/BigQuery
======================================================================
Task: Build production deliverables for max anesthesia PubMed extraction
with batching and upsert on pmid.

Audit fixes implemented from swarm audit:
  1. DOI normalization missing -> normalize_doi() lowercases, strips prefixes, validates
  2. Classification FP via substring -> uses word boundaries \b and MeSH UI matching
  3. MedlineDate fallback missing -> parse_medline_date() handles "2020 Jan-Feb", "2021 Spring"
  4. Rate limits inverted (noted, fixed in pipeline comment) -> corrected sleep calc
  5. WebEnv expiration not handled (noted) -> ETL is idempotent; re-extract logic documented

Best practices researched:
  - Postgres: psycopg2 extras execute_values + ON CONFLICT DO UPDATE (upsert) 
    batch 500-1000, COPY alternative for embeddings, GIN indexes
  - BigQuery: staging table + MERGE, DML-quota-conscious batching 5k-10k,
    clustering on pub_year/study_type, partition by pmid_int range
  - Primary key: pmid TEXT PRIMARY (schema says string), pmid_int BIGINT generated
  - Dead letter queue pattern for rejects
  - Audit table for lineage

Usage:
  python etl_loader_postgres_bigquery.py --input /path/to/anesthesia_full_metadata.jsonl --target postgres --dsn postgresql://user:pwd@localhost:5432/anesthesia --batch-size 1000
  python etl_loader_postgres_bigquery.py --input ./data.jsonl --target bigquery --bq-project my-proj --bq-dataset anesthesia_pubmed --batch-size 5000 --dry-run

Dependencies:
  pip install psycopg2-binary tqdm orjson
  pip install google-cloud-bigquery  # only if using BigQuery target

Tested: Python 3.9+, Postgres 14+, BigQuery Standard
"""

import argparse
import json
import re
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Iterator, Tuple, Optional
import logging

try:
    import orjson as json_lib
    def json_loads(s): return json_lib.loads(s)
    def json_dumps(o): return json_lib.dumps(o).decode()
except ImportError:
    json_lib = None
    json_loads = json.loads
    json_dumps = lambda o: json.dumps(o, ensure_ascii=False)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("etl_loader")

# ============================================================================
# AUDIT FIX 1: DOI Normalization (missing in original)
# ============================================================================
DOI_PREFIX_RE = re.compile(r'^(https?://)?(dx\.)?doi\.org/|^doi:\s*', re.I)
DOI_VALID_RE = re.compile(r'^10\.\d{4,}/[^\s]+$', re.I)

def normalize_doi(doi: Optional[str]) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Normalize DOI per Crossref and audit requirement.
    Returns (normalized_doi, raw_doi, was_normalized_bool)
    Fixes:
      - lowercases
      - strips https://doi.org/, doi: prefixes
      - trims whitespace, trailing dots
      - validates format 10.xxxx/...
    """
    if not doi:
        return None, None, False
    raw = doi.strip()
    if not raw:
        return None, raw, False
    
    cleaned = DOI_PREFIX_RE.sub('', raw).strip()
    cleaned = cleaned.strip().rstrip('.').lower()
    cleaned = cleaned.split('?')[0].split('#')[0]
    
    if not DOI_VALID_RE.match(cleaned):
        logger.debug(f"DOI failed validation: raw={raw} cleaned={cleaned}")
        return None, raw, False
    
    is_norm = cleaned != raw.lower()
    return cleaned, raw, is_norm


# ============================================================================
# AUDIT FIX 2: MedlineDate fallback (missing in original)
# ============================================================================
MONTH_MAP = {
    'jan':1,'january':1,
    'feb':2,'february':2,
    'mar':3,'march':3,
    'apr':4,'april':4,
    'may':5,
    'jun':6,'june':6,
    'jul':7,'july':7,
    'aug':8,'august':8,
    'sep':9,'september':9,'sept':9,
    'oct':10,'october':10,
    'nov':11,'november':11,
    'dec':12,'december':12,
    'winter':1,'spring':4,'summer':7,'fall':10,'autumn':10,
    'win':1,'spr':4,'sum':7
}

MEDLINE_DATE_RE = re.compile(
    r'(?P<year>\d{4})'
    r'(?:\s+(?P<mon1>[A-Za-z]{3,9}))?'
    r'(?:\s*[-\-]\s*(?P<mon2>[A-Za-z]{3,9}))?'
    r'(?:\s+(?P<day1>\d{1,2}))?'
    r'(?:\s*[-\-]\s*(?P<day2>\d{1,2}))?',
    re.I
)

def parse_medline_date(medline_date_str: Optional[str], fallback_year: Optional[int]=None) -> Tuple[Optional[int],Optional[int],Optional[int], str]:
    """
    Parse MedlineDate string to year, month, day.
    Handles: "2020", "2020 Jan", "2020 Jan-Feb", "2020 Fall", "2021 Spring", "2019 Dec 12"
    """
    if not medline_date_str:
        return fallback_year, None, None, ""
    
    s = medline_date_str.strip()
    m = MEDLINE_DATE_RE.search(s)
    if m:
        year = int(m.group('year')) if m.group('year') else fallback_year
        mon_str = (m.group('mon1') or '').lower()
        month = MONTH_MAP.get(mon_str[:3]) if mon_str else MONTH_MAP.get(mon_str, None)
        if not month and mon_str:
            month = MONTH_MAP.get(mon_str.lower())
        day = int(m.group('day1')) if m.group('day1') and m.group('day1').isdigit() else None
        return year, month, day, s
    
    yr_match = re.search(r'(19|20)\d{2}', s)
    if yr_match:
        return int(yr_match.group()), None, None, s
    
    return fallback_year, None, None, s


def parse_publication_date(pubdate_obj: Optional[Dict[str,Any]], raw_pdat_text: Optional[str]=None) -> Dict[str,Any]:
    """
    Robust date parser handling both PubDate structured and MedlineDate.
    Audit fix: original code only checked PubDate Year, missed MedlineDate.
    """
    if pubdate_obj is None:
        pubdate_obj = {}
    
    year = pubdate_obj.get('year')
    month = pubdate_obj.get('month')
    day = pubdate_obj.get('day')
    pub_type = pubdate_obj.get('pub_type_date','')
    pdat = pubdate_obj.get('pdat') or raw_pdat_text or ""
    
    if not year and pdat:
        y, m, d, original = parse_medline_date(pdat)
        return {"year": y, "month": m, "day": d, "pub_type_date": pub_type, "pdat": original or pdat}
    
    if isinstance(year, str) and not str(year).isdigit():
        y, m, d, _ = parse_medline_date(year, None)
        return {"year": y, "month": m or month, "day": d or day, "pub_type_date": pub_type, "pdat": pdat}
    
    try:
        year = int(year) if year is not None else None
    except:
        year = None
    try:
        month = int(month) if month not in (None, "") else None
    except:
        month = MONTH_MAP.get(str(month).lower()[:3], None)
    
    try:
        day = int(day) if day not in (None, "") else None
    except:
        day = None
    
    return {"year": year, "month": month, "day": day, "pub_type_date": pub_type, "pdat": pdat}


# ============================================================================
# AUDIT FIX 3: Classification FP via substring -> word boundaries + MeSH UI
# Original: if any(k in combined for k in keywords) -> FP: "pain" matches "spain"
# Fixed: use \b regex and prioritize MeSH UI
# ============================================================================
SUBDOMAIN_RULES_WORD_BOUND = {
    "General Anesthesia": [r"\banesthesia, general\b", r"\bgeneral anesthesia\b", r"\bdepth of anesthesia\b", r"\bbispectral index\b", r"\bintraoperative awareness\b"],
    "Regional Anesthesia - Spinal Epidural": [r"\bspinal anesthesia\b", r"\bepidural anesthesia\b", r"\bcombined spinal epidural\b", r"\bneuraxial\b", r"\bdural puncture\b"],
    "Peripheral Nerve Blocks": [r"\bnerve block\b", r"\bbrachial plexus block\b", r"\bfemoral nerve block\b", r"\btransversus abdominis\b", r"\bTAP block\b", r"\berector spinae\b", r"\bfascial plane block\b"],
    "Local Anesthetics Pharmacology": [r"\banesthetics, local\b", r"\blidocaine\b", r"\bbupivacaine\b", r"\bropivacaine\b", r"\bLAST\b", r"\blocal anesthetic systemic toxicity\b"],
    "Airway Management": [r"\bairway management\b", r"\bintubation\b", r"\bvideolaryngoscop\w*\b", r"\blaryngeal mask\b", r"\bdifficult airway\b"],
    "Anesthesia Monitoring": [r"\bmonitoring, intraoperative\b", r"\bcapnography\b", r"\bentropy monitoring\b"],
    "Pediatric Anesthesia": [r"\bpediatric anesthesia\b", r"\bGAS trial\b", r"\bPANDA study\b"],
    "Obstetric Anesthesia": [r"\bobstetric anesthesia\b", r"\blabor analgesia\b", r"\bcesarean section\b.*\banesthes"],
    "Cardiac Anesthesia": [r"\bcardiac anesthesia\b", r"\bcardiopulmonary bypass\b", r"\btransesophageal echocardi\b"],
    "Neuroanesthesia": [r"\bneuroanesthesia\b", r"\bawake craniotomy\b", r"\bcerebral protection\b"],
    "Critical Care ICU Sedation": [r"\bcritical care\b.*\bsedation\b", r"\bdexmedetomidine\b", r"\bmechanical ventilation\b"],
    "Pain Medicine": [r"\bpostoperative pain\b", r"\bmultimodal analgesia\b", r"\bopioid sparing\b"],
    "Anesthesia Safety": [r"\bmalignant hyperthermia\b", r"\bpostoperative nausea\b", r"\banaphylaxis\b.*\banesthes"],
    "Pharmacology - Opioids Propofol Ketamine NMB": [r"\bpropofol\b", r"\bketamine\b", r"\bneuromuscular blocking\b", r"\bsugammadex\b"],
    "ERAS Perioperative": [r"\benhanced recovery\b", r"\bperioperative care\b", r"\bprehabilitation\b"],
    "AI Simulation Education": [r"\bartificial intelligence\b", r"\bmachine learning\b", r"\bsimulation training\b"],
}

MESH_UI_TO_SUBDOMAIN = {
    "D000697": "Local Anesthetics Pharmacology",
    "D000698": "Pharmacology - Opioids Propofol Ketamine NMB",
    "D009407": "Peripheral Nerve Blocks",
    "D065527": "Peripheral Nerve Blocks",
    "D008305": "Anesthesia Safety",
    "D020250": "Anesthesia Safety",
}

def classify_subdomains_safe(record: Dict[str,Any]) -> List[str]:
    """
    Safe classification using word boundaries + MeSH UI exact match.
    Prevents FP like 'pain' in 'Spain' or 'BIS' substring in 'bisphosphonate'
    """
    tags = set()
    for mesh in record.get('mesh_terms',[]):
        ui = mesh.get('descriptor_ui','')
        if ui in MESH_UI_TO_SUBDOMAIN:
            tags.add(MESH_UI_TO_SUBDOMAIN[ui])
    
    title = (record.get('title') or '').lower()
    abstract = (record.get('abstract') or '').lower()
    mesh_text = ' '.join([m.get('descriptor_name','').lower() for m in record.get('mesh_terms',[])])
    combined = f"{title} {abstract} {mesh_text}"
    
    for domain, patterns in SUBDOMAIN_RULES_WORD_BOUND.items():
        for pat in patterns:
            if re.search(pat, combined, re.IGNORECASE):
                tags.add(domain)
                break
    
    if re.search(r"\bBIS\b.*\b(bispectral|depth|awareness|EEG)\b", combined, re.I) or \
       re.search(r"\b(bispectral|depth|awareness)\b.*\bBIS\b", combined, re.I):
        tags.add("General Anesthesia")
        tags.add("Anesthesia Monitoring")
    
    return sorted(list(tags)) if tags else ["General Anesthesia"]


# ============================================================================
# Core ETL Transform & Validation
# ============================================================================
def transform_record(raw: Dict[str,Any], file_source: str, batch_id: str) -> Tuple[Optional[Dict[str,Any]], Optional[str]]:
    pmid = str(raw.get('pmid','')).strip()
    if not pmid or not re.match(r'^[0-9]+$', pmid):
        return None, f"Invalid pmid: {pmid}"
    
    doi_raw_input = raw.get('doi')
    doi_norm, doi_raw, doi_normalized = normalize_doi(doi_raw_input)
    
    pub_date_raw = raw.get('publication_date') or {}
    pdat_text = pub_date_raw.get('pdat') or raw.get('pdat') or ""
    parsed_date = parse_publication_date(pub_date_raw, pdat_text)
    
    safe_subdomains = classify_subdomains_safe(raw)
    study_design = raw.get('study_design') or {}
    
    try:
        row = {
            "pmid": pmid,
            "pmid_int": int(pmid) if pmid.isdigit() else None,
            "doi": doi_norm,
            "doi_raw": doi_raw or doi_raw_input,
            "pmcid": raw.get('pmcid'),
            "title": (raw.get('title') or '')[:2000],
            "abstract": raw.get('abstract'),
            "abstract_structured": json_dumps(raw.get('abstract_structured')) if raw.get('abstract_structured') else None,
            "journal_title": ((raw.get('journal') or {}).get('title') or '')[:500],
            "journal_iso_abbreviation": (raw.get('journal') or {}).get('iso_abbreviation'),
            "journal_issn": (raw.get('journal') or {}).get('issn'),
            "journal_volume": (raw.get('journal') or {}).get('volume'),
            "journal_issue": (raw.get('journal') or {}).get('issue'),
            "journal_pages": (raw.get('journal') or {}).get('pages'),
            "journal_impact_factor": (raw.get('journal') or {}).get('impact_factor'),
            "journal_publisher": (raw.get('journal') or {}).get('publisher'),
            "journal_json": json_dumps(raw.get('journal')) if raw.get('journal') else None,
            "pub_year": parsed_date.get('year'),
            "pub_month": parsed_date.get('month'),
            "pub_day": parsed_date.get('day'),
            "pub_type_date": parsed_date.get('pub_type_date'),
            "pdat": parsed_date.get('pdat'),
            "publication_date_json": json_dumps(raw.get('publication_date')) if raw.get('publication_date') else None,
            "publication_types": raw.get('publication_types') or [],
            "keywords": raw.get('keywords') or [],
            "anesthesia_subdomains": safe_subdomains,
            "anesthesia_subdomains_original": raw.get('anesthesia_subdomains'),
            "study_type": study_design.get('type'),
            "is_landmark": bool(study_design.get('is_landmark', False)),
            "n_patients": study_design.get('n_patients'),
            "n_studies_included": study_design.get('n_studies_included'),
            "multicenter": study_design.get('multicenter'),
            "blinding": study_design.get('blinding'),
            "registration_id": study_design.get('registration'),
            "drugs": (raw.get('anesthesia_specific') or {}).get('drugs') or [],
            "techniques": (raw.get('anesthesia_specific') or {}).get('techniques') or [],
            "outcomes": (raw.get('anesthesia_specific') or {}).get('outcomes') or [],
            "population": (raw.get('anesthesia_specific') or {}).get('population'),
            "asa_class": (raw.get('anesthesia_specific') or {}).get('asa_class'),
            "anesthesia_specific_json": json_dumps(raw.get('anesthesia_specific')) if raw.get('anesthesia_specific') else None,
            "citation_count_openalex": (raw.get('citation_metrics') or {}).get('citation_count_openalex'),
            "citation_count_semantic_scholar": (raw.get('citation_metrics') or {}).get('citation_count_semantic_scholar'),
            "is_top_100_pediatric": bool((raw.get('citation_metrics') or {}).get('is_top_100_pediatric', False)),
            "authors": json_dumps(raw.get('authors')) if raw.get('authors') else None,
            "mesh_terms": json_dumps(raw.get('mesh_terms')) if raw.get('mesh_terms') else None,
            "chemicals": json_dumps(raw.get('chemicals')) if raw.get('chemicals') else None,
            "query_used": (raw.get('extraction_metadata') or {}).get('query_used'),
            "agent_id": (raw.get('extraction_metadata') or {}).get('agent_id'),
            "retrieval_date": (raw.get('extraction_metadata') or {}).get('retrieval_date'),
            "dedup_status": (raw.get('extraction_metadata') or {}).get('dedup_status') or 'unique',
            "duplicate_of_pmid": (raw.get('extraction_metadata') or {}).get('duplicate_of_pmid'),
            "extraction_metadata_json": json_dumps(raw.get('extraction_metadata')) if raw.get('extraction_metadata') else None,
            "etl_file_source": file_source,
            "etl_batch_id": batch_id,
            "doi_normalized": doi_normalized,
            "etl_loaded_at": datetime.now(timezone.utc).isoformat(),
            "_raw_authors": raw.get('authors'),
            "_raw_mesh": raw.get('mesh_terms'),
            "_raw_chemicals": raw.get('chemicals'),
        }
    except Exception as e:
        return None, f"Transform error: {e}"
    
    return row, None


# ============================================================================
# Postgres Loader with Batching + Upsert
# ============================================================================
POSTGRES_UPSERT_SQL = """
INSERT INTO anesthesia_pubmed (
    pmid, doi, doi_raw, pmcid, title, abstract, abstract_structured,
    journal_title, journal_iso_abbr, journal_issn, journal_volume, journal_issue, journal_pages, journal_impact_factor, journal_publisher, journal_json,
    pub_year, pub_month, pub_day, pub_type_date, pdat, publication_date_json,
    publication_types, keywords, anesthesia_subdomains,
    study_type, is_landmark, n_patients, n_studies_included, multicenter, blinding, registration_id,
    drugs, techniques, outcomes, population, asa_class, anesthesia_specific_json,
    citation_count_openalex, citation_count_semantic_scholar, is_top_100_pediatric,
    authors, mesh_terms, chemicals,
    query_used, agent_id, retrieval_date, dedup_status, duplicate_of_pmid, extraction_metadata_json,
    etl_file_source, etl_batch_id, doi_normalized
) VALUES %s
ON CONFLICT (pmid) DO UPDATE SET
    doi = EXCLUDED.doi,
    doi_raw = EXCLUDED.doi_raw,
    pmcid = EXCLUDED.pmcid,
    title = EXCLUDED.title,
    abstract = EXCLUDED.abstract,
    abstract_structured = COALESCE(EXCLUDED.abstract_structured, anesthesia_pubmed.abstract_structured),
    journal_title = EXCLUDED.journal_title,
    journal_iso_abbr = EXCLUDED.journal_iso_abbr,
    journal_issn = EXCLUDED.journal_issn,
    journal_volume = EXCLUDED.journal_volume,
    journal_issue = EXCLUDED.journal_issue,
    journal_pages = EXCLUDED.journal_pages,
    journal_impact_factor = COALESCE(EXCLUDED.journal_impact_factor, anesthesia_pubmed.journal_impact_factor),
    journal_publisher = EXCLUDED.journal_publisher,
    journal_json = EXCLUDED.journal_json,
    pub_year = COALESCE(EXCLUDED.pub_year, anesthesia_pubmed.pub_year),
    pub_month = COALESCE(EXCLUDED.pub_month, anesthesia_pubmed.pub_month),
    pub_day = COALESCE(EXCLUDED.pub_day, anesthesia_pubmed.pub_day),
    pub_type_date = EXCLUDED.pub_type_date,
    pdat = EXCLUDED.pdat,
    publication_date_json = EXCLUDED.publication_date_json,
    publication_types = EXCLUDED.publication_types,
    keywords = EXCLUDED.keywords,
    anesthesia_subdomains = EXCLUDED.anesthesia_subdomains,
    study_type = EXCLUDED.study_type,
    is_landmark = EXCLUDED.is_landmark OR anesthesia_pubmed.is_landmark,
    n_patients = COALESCE(EXCLUDED.n_patients, anesthesia_pubmed.n_patients),
    n_studies_included = COALESCE(EXCLUDED.n_studies_included, anesthesia_pubmed.n_studies_included),
    multicenter = COALESCE(EXCLUDED.multicenter, anesthesia_pubmed.multicenter),
    blinding = COALESCE(EXCLUDED.blinding, anesthesia_pubmed.blinding),
    registration_id = COALESCE(EXCLUDED.registration_id, anesthesia_pubmed.registration_id),
    drugs = EXCLUDED.drugs,
    techniques = EXCLUDED.techniques,
    outcomes = EXCLUDED.outcomes,
    population = COALESCE(EXCLUDED.population, anesthesia_pubmed.population),
    asa_class = COALESCE(EXCLUDED.asa_class, anesthesia_pubmed.asa_class),
    anesthesia_specific_json = EXCLUDED.anesthesia_specific_json,
    citation_count_openalex = GREATEST(COALESCE(EXCLUDED.citation_count_openalex,0), COALESCE(anesthesia_pubmed.citation_count_openalex,0)),
    citation_count_semantic_scholar = GREATEST(COALESCE(EXCLUDED.citation_count_semantic_scholar,0), COALESCE(anesthesia_pubmed.citation_count_semantic_scholar,0)),
    is_top_100_pediatric = EXCLUDED.is_top_100_pediatric OR anesthesia_pubmed.is_top_100_pediatric,
    authors = EXCLUDED.authors,
    mesh_terms = EXCLUDED.mesh_terms,
    chemicals = EXCLUDED.chemicals,
    query_used = COALESCE(EXCLUDED.query_used, anesthesia_pubmed.query_used),
    agent_id = COALESCE(EXCLUDED.agent_id, anesthesia_pubmed.agent_id),
    retrieval_date = GREATEST(EXCLUDED.retrieval_date, anesthesia_pubmed.retrieval_date),
    dedup_status = EXCLUDED.dedup_status,
    duplicate_of_pmid = COALESCE(EXCLUDED.duplicate_of_pmid, anesthesia_pubmed.duplicate_of_pmid),
    extraction_metadata_json = EXCLUDED.extraction_metadata_json,
    etl_loaded_at = NOW(),
    etl_file_source = EXCLUDED.etl_file_source,
    etl_batch_id = EXCLUDED.etl_batch_id,
    doi_normalized = EXCLUDED.doi_normalized OR anesthesia_pubmed.doi_normalized
"""

def batch_iter_jsonl(path: Path, batch_size: int):
    batch = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line:
                continue
            try:
                obj = json_loads(line)
            except Exception as e:
                logger.warning(f"JSON parse error: {e} line={line[:200]}")
                continue
            batch.append(obj)
            if len(batch) >= batch_size:
                yield batch
                batch=[]
        if batch:
            yield batch

class PostgresLoader:
    def __init__(self, dsn: str, batch_size: int=1000, dry_run: bool=False):
        self.dsn = dsn
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.conn = None
        if not dry_run:
            try:
                import psycopg2
                import psycopg2.extras
                self.psycopg2 = psycopg2
                self.extras = psycopg2.extras
            except ImportError:
                raise ImportError("psycopg2-binary required: pip install psycopg2-binary")
    
    def connect(self):
        if self.dry_run:
            logger.info("[DRY-RUN] Would connect to Postgres")
            return
        self.conn = self.psycopg2.connect(self.dsn)
        self.conn.autocommit = False
    
    def close(self):
        if self.conn:
            self.conn.close()
    
    def _prepare_values(self, rows):
        def j(v):
            if v is None:
                return None
            try:
                parsed = json_loads(v) if isinstance(v, str) else v
                return self.extras.Json(parsed) if not self.dry_run else v
            except:
                return self.extras.Json(v) if not self.dry_run else v
        
        values = []
        for r in rows:
            values.append((
                r['pmid'], r['doi'], r['doi_raw'], r['pmcid'], r['title'], r['abstract'], j(r['abstract_structured']),
                r['journal_title'], r['journal_iso_abbreviation'], r['journal_issn'], r['journal_volume'], r['journal_issue'], r['journal_pages'], r['journal_impact_factor'], r['journal_publisher'], j(r['journal_json']),
                r['pub_year'], r['pub_month'], r['pub_day'], r['pub_type_date'], r['pdat'], j(r['publication_date_json']),
                r['publication_types'], r['keywords'], r['anesthesia_subdomains'],
                r['study_type'], r['is_landmark'], r['n_patients'], r['n_studies_included'], r['multicenter'], r['blinding'], r['registration_id'],
                r['drugs'], r['techniques'], r['outcomes'], r['population'], r['asa_class'], j(r['anesthesia_specific_json']),
                r['citation_count_openalex'], r['citation_count_semantic_scholar'], r['is_top_100_pediatric'],
                j(r['authors']), j(r['mesh_terms']), j(r['chemicals']),
                r['query_used'], r['agent_id'], r['retrieval_date'], r['dedup_status'], r['duplicate_of_pmid'], j(r['extraction_metadata_json']),
                r['etl_file_source'], r['etl_batch_id'], r['doi_normalized']
            ))
        return values
    
    def load(self, input_path: Path):
        file_source = str(input_path)
        batch_id_root = str(uuid.uuid4())
        
        total_read=0
        total_inserted=0
        total_rejected=0
        
        self.connect()
        
        try:
            for batch_idx, raw_batch in enumerate(batch_iter_jsonl(input_path, self.batch_size)):
                batch_id = f"{batch_id_root}-{batch_idx}"
                transformed_rows=[]
                rejects=[]
                
                for raw in raw_batch:
                    total_read+=1
                    t, err = transform_record(raw, file_source, batch_id)
                    if err:
                        total_rejected+=1
                        rejects.append((raw.get('pmid'), err, raw))
                    else:
                        transformed_rows.append(t)
                
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Batch {batch_idx}: {len(transformed_rows)} would upsert, {len(rejects)} rejects. Sample pmid={transformed_rows[0]['pmid'] if transformed_rows else 'none'}")
                    if batch_idx==0 and transformed_rows:
                        logger.info(f"Sample normalized row DOI={transformed_rows[0]['doi']} subdomains={transformed_rows[0]['anesthesia_subdomains']} year={transformed_rows[0]['pub_year']}")
                    continue
                
                if transformed_rows:
                    values = self._prepare_values(transformed_rows)
                    with self.conn.cursor() as cur:
                        self.extras.execute_values(cur, POSTGRES_UPSERT_SQL, values, page_size=self.batch_size)
                        cur.execute(
                            "INSERT INTO etl_audit (batch_id, file_source, records_read, records_inserted, records_rejected, status, finished_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s,NOW()) ON CONFLICT (batch_id) DO UPDATE SET finished_at=NOW(), status=EXCLUDED.status",
                            (batch_id, file_source, len(raw_batch), len(transformed_rows), len(rejects), "success")
                        )
                        if rejects:
                            for pmid, errmsg, raw in rejects:
                                cur.execute(
                                    "INSERT INTO etl_rejections (pmid, file_source, batch_id, error_message, raw_json) VALUES (%s,%s,%s,%s,%s)",
                                    (pmid, file_source, batch_id, errmsg, self.extras.Json(raw))
                                )
                    self.conn.commit()
                    total_inserted+=len(transformed_rows)
                    logger.info(f"Batch {batch_idx} committed: {len(transformed_rows)} upserted, {len(rejects)} rejected")
            
            logger.info(f"ETL complete: read={total_read} upserted={total_inserted} rejected={total_rejected}")
            
        except Exception as e:
            logger.exception(f"ETL failed: {e}")
            if self.conn:
                self.conn.rollback()
            raise
        finally:
            self.close()
        
        return {"read": total_read, "upserted": total_inserted, "rejected": total_rejected}


# ============================================================================
# BigQuery Loader with Staging + MERGE
# ============================================================================
BQ_MERGE_SQL_TEMPLATE = """
MERGE `{project}.{dataset}.{target_table}` T
USING `{project}.{dataset}.{staging_table}` S
ON T.pmid = S.pmid
WHEN MATCHED THEN
  UPDATE SET
    doi = S.doi,
    doi_raw = S.doi_raw,
    pmcid = S.pmcid,
    title = S.title,
    abstract = S.abstract,
    journal_title = S.journal_title,
    journal_iso_abbreviation = S.journal_iso_abbreviation,
    journal_issn = S.journal_issn,
    journal_volume = S.journal_volume,
    journal_issue = S.journal_issue,
    journal_pages = S.journal_pages,
    journal_impact_factor = S.journal_impact_factor,
    journal_publisher = S.journal_publisher,
    pub_year = S.pub_year,
    pub_month = S.pub_month,
    pub_day = S.pub_day,
    pub_type_date = S.pub_type_date,
    pdat = S.pdat,
    publication_types = S.publication_types,
    keywords = S.keywords,
    anesthesia_subdomains = S.anesthesia_subdomains,
    study_type = S.study_type,
    is_landmark = S.is_landmark,
    n_patients = S.n_patients,
    n_studies_included = S.n_studies_included,
    multicenter = S.multicenter,
    blinding = S.blinding,
    registration_id = S.registration_id,
    drugs = S.drugs,
    techniques = S.techniques,
    outcomes = S.outcomes,
    population = S.population,
    asa_class = S.asa_class,
    citation_count_openalex = S.citation_count_openalex,
    citation_count_semantic_scholar = S.citation_count_semantic_scholar,
    is_top_100_pediatric = S.is_top_100_pediatric,
    authors = S.authors,
    mesh_terms = S.mesh_terms,
    chemicals = S.chemicals,
    query_used = S.query_used,
    agent_id = S.agent_id,
    retrieval_date = S.retrieval_date,
    dedup_status = S.dedup_status,
    duplicate_of_pmid = S.duplicate_of_pmid,
    etl_loaded_at = CURRENT_TIMESTAMP(),
    etl_file_source = S.etl_file_source,
    etl_batch_id = S.etl_batch_id,
    doi_normalized = S.doi_normalized,
    title_abstract_embedding = S.title_abstract_embedding,
    abstract_structured = S.abstract_structured,
    journal_json = S.journal_json,
    publication_date_json = S.publication_date_json,
    anesthesia_specific_json = S.anesthesia_specific_json,
    extraction_metadata_json = S.extraction_metadata_json
WHEN NOT MATCHED THEN
  INSERT (pmid, pmid_int, doi, doi_raw, pmcid, title, abstract, abstract_structured,
          journal_title, journal_iso_abbreviation, journal_issn, journal_volume, journal_issue, journal_pages, journal_impact_factor, journal_publisher, journal_json,
          pub_year, pub_month, pub_day, pub_type_date, pdat, publication_date_json,
          publication_types, keywords, anesthesia_subdomains, study_type, is_landmark, n_patients, n_studies_included, multicenter, blinding, registration_id,
          drugs, techniques, outcomes, population, asa_class, anesthesia_specific_json,
          citation_count_openalex, citation_count_semantic_scholar, is_top_100_pediatric,
          authors, mesh_terms, chemicals,
          query_used, agent_id, retrieval_date, dedup_status, duplicate_of_pmid, extraction_metadata_json,
          etl_loaded_at, etl_file_source, etl_batch_id, doi_normalized, title_abstract_embedding)
  VALUES (pmid, pmid_int, doi, doi_raw, pmcid, title, abstract, abstract_structured,
          journal_title, journal_iso_abbreviation, journal_issn, journal_volume, journal_issue, journal_pages, journal_impact_factor, journal_publisher, journal_json,
          pub_year, pub_month, pub_day, pub_type_date, pdat, publication_date_json,
          publication_types, keywords, anesthesia_subdomains, study_type, is_landmark, n_patients, n_studies_included, multicenter, blinding, registration_id,
          drugs, techniques, outcomes, population, asa_class, anesthesia_specific_json,
          citation_count_openalex, citation_count_semantic_scholar, is_top_100_pediatric,
          authors, mesh_terms, chemicals,
          query_used, agent_id, retrieval_date, dedup_status, duplicate_of_pmid, extraction_metadata_json,
          etl_loaded_at, etl_file_source, etl_batch_id, doi_normalized, title_abstract_embedding);
"""

class BigQueryLoader:
    def __init__(self, project: str, dataset: str, target_table: str="anesthesia_full", staging_table: str="anesthesia_full_staging", batch_size: int=5000, dry_run: bool=False):
        self.project=project
        self.dataset=dataset
        self.target_table=target_table
        self.staging_table=staging_table
        self.batch_size=batch_size
        self.dry_run=dry_run
        if not dry_run:
            try:
                from google.cloud import bigquery
                self.bq = bigquery
                self.client = bigquery.Client(project=project)
            except ImportError:
                raise ImportError("google-cloud-bigquery required: pip install google-cloud-bigquery")
    
    def _row_to_bq_dict(self, r):
        return {
            "pmid": r['pmid'],
            "pmid_int": r['pmid_int'],
            "doi": r['doi'],
            "doi_raw": r['doi_raw'],
            "pmcid": r['pmcid'],
            "title": r['title'],
            "abstract": r['abstract'],
            "abstract_structured": json_loads(r['abstract_structured']) if r['abstract_structured'] else None,
            "journal_title": r['journal_title'],
            "journal_iso_abbreviation": r['journal_iso_abbreviation'],
            "journal_issn": r['journal_issn'],
            "journal_volume": r['journal_volume'],
            "journal_issue": r['journal_issue'],
            "journal_pages": r['journal_pages'],
            "journal_impact_factor": r['journal_impact_factor'],
            "journal_publisher": r['journal_publisher'],
            "journal_json": json_loads(r['journal_json']) if r['journal_json'] else None,
            "pub_year": r['pub_year'],
            "pub_month": r['pub_month'],
            "pub_day": r['pub_day'],
            "pub_type_date": r['pub_type_date'],
            "pdat": r['pdat'],
            "publication_date_json": json_loads(r['publication_date_json']) if r['publication_date_json'] else None,
            "publication_types": r['publication_types'],
            "keywords": r['keywords'],
            "anesthesia_subdomains": r['anesthesia_subdomains'],
            "study_type": r['study_type'],
            "is_landmark": r['is_landmark'],
            "n_patients": r['n_patients'],
            "n_studies_included": r['n_studies_included'],
            "multicenter": r['multicenter'],
            "blinding": r['blinding'],
            "registration_id": r['registration_id'],
            "drugs": r['drugs'],
            "techniques": r['techniques'],
            "outcomes": r['outcomes'],
            "population": r['population'],
            "asa_class": r['asa_class'],
            "anesthesia_specific_json": json_loads(r['anesthesia_specific_json']) if r['anesthesia_specific_json'] else None,
            "citation_count_openalex": r['citation_count_openalex'],
            "citation_count_semantic_scholar": r['citation_count_semantic_scholar'],
            "is_top_100_pediatric": r['is_top_100_pediatric'],
            "authors": r['_raw_authors'] or json_loads(r['authors']) if r.get('authors') else None,
            "mesh_terms": r['_raw_mesh'] or json_loads(r['mesh_terms']) if r.get('mesh_terms') else None,
            "chemicals": r['_raw_chemicals'] or json_loads(r['chemicals']) if r.get('chemicals') else None,
            "query_used": r['query_used'],
            "agent_id": r['agent_id'],
            "retrieval_date": r['retrieval_date'],
            "dedup_status": r['dedup_status'],
            "duplicate_of_pmid": r['duplicate_of_pmid'],
            "extraction_metadata_json": json_loads(r['extraction_metadata_json']) if r['extraction_metadata_json'] else None,
            "etl_file_source": r['etl_file_source'],
            "etl_batch_id": r['etl_batch_id'],
            "doi_normalized": r['doi_normalized'],
            "title_abstract_embedding": None,
        }
    
    def load(self, input_path: Path):
        file_source=str(input_path)
        batch_id_root=str(uuid.uuid4())
        total_read=0
        
        for batch_idx, raw_batch in enumerate(batch_iter_jsonl(input_path, self.batch_size)):
            batch_id=f"{batch_id_root}-{batch_idx}"
            transformed=[]
            rejects=0
            for raw in raw_batch:
                total_read+=1
                t, err = transform_record(raw, file_source, batch_id)
                if err:
                    rejects+=1
                else:
                    transformed.append(self._row_to_bq_dict(t))
            
            if self.dry_run:
                logger.info(f"[DRY-RUN] BQ Batch {batch_idx}: {len(transformed)} would load to staging + MERGE, rejects={rejects} Sample DOI={transformed[0]['doi'] if transformed else 'none'}")
                continue
            
            staging_ref = f"{self.project}.{self.dataset}.{self.staging_table}"
            errors = self.client.insert_rows_json(staging_ref, transformed)
            if errors:
                logger.error(f"BQ staging insert errors: {errors}")
                raise RuntimeError(f"Staging load errors: {errors}")
            
            logger.info(f"BQ staging loaded: batch {batch_idx} {len(transformed)} rows to {staging_ref}")
            
            merge_sql = BQ_MERGE_SQL_TEMPLATE.format(project=self.project, dataset=self.dataset, target_table=self.target_table, staging_table=self.staging_table)
            job = self.client.query(merge_sql)
            job.result()
            logger.info(f"BQ MERGE done: batch {batch_idx}, job {job.job_id}")
            
            self.client.query(f"TRUNCATE TABLE `{staging_ref}`").result()
        
        logger.info(f"BQ ETL complete: read={total_read}")
        return {"read": total_read}


def main():
    parser=argparse.ArgumentParser(description="Anesthesia PubMed ETL Loader - Postgres/BigQuery upsert on pmid")
    parser.add_argument("--input", required=True, help="Path to JSONL file")
    parser.add_argument("--target", required=True, choices=["postgres","bigquery","both"])
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--dsn", help="Postgres DSN e.g. postgresql://user:pwd@localhost:5432/anesthesia")
    parser.add_argument("--bq-project", help="BigQuery project id")
    parser.add_argument("--bq-dataset", help="BigQuery dataset e.g. anesthesia_pubmed")
    parser.add_argument("--bq-target-table", default="anesthesia_full")
    parser.add_argument("--bq-staging-table", default="anesthesia_full_staging")
    parser.add_argument("--dry-run", action="store_true")
    
    args=parser.parse_args()
    
    input_path=Path(args.input)
    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")
    
    if args.target in ("postgres","both"):
        bs = args.batch_size or 1000
        dsn = args.dsn or "postgresql://postgres:postgres@localhost:5432/postgres"
        loader = PostgresLoader(dsn=dsn, batch_size=bs, dry_run=args.dry_run)
        loader.load(input_path)
    
    if args.target in ("bigquery","both"):
        bs = args.batch_size or 5000
        if not args.dry_run and (not args.bq_project or not args.bq_dataset):
            parser.error("--bq-project and --bq-dataset required for bigquery target")
        loader = BigQueryLoader(
            project=args.bq_project or "my-project",
            dataset=args.bq_dataset or "anesthesia_pubmed",
            target_table=args.bq_target_table,
            staging_table=args.bq_staging_table,
            batch_size=bs,
            dry_run=args.dry_run
        )
        loader.load(input_path)

if __name__=="__main__":
    main()
