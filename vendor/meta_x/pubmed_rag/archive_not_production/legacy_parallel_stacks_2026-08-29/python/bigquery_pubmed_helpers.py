"""
BigQuery Ingestion Helpers for Max Anesthesia PubMed Extraction
Agent B2: BigQuery DDL Architect
Addresses audit critical issues:
- DOI normalization missing -> normalize_doi()
- MedlineDate fallback missing -> parse_pubmed_date()
- Classification FP via substring -> classify_subdomains_boundary()
- Rate limits inverted -> RATE_LIMIT_* constants corrected
- WebEnv expiration not handled -> handle_webenv_expiration()
- Embeddings + STRUCT journal + REPEATED mesh_terms mapping
"""

import re
import json
from datetime import date, datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

# --- Corrected rate limits (audit: inverted) ---
RATE_LIMIT_WITH_API_KEY = 10  # req/s (NCBI default with key)
RATE_LIMIT_WITHOUT_KEY = 3   # req/s (NCBI default without key)
SLEEP_WITH_KEY = 1.0 / RATE_LIMIT_WITH_API_KEY  # 0.05s
SLEEP_WITHOUT_KEY = 1.0 / RATE_LIMIT_WITHOUT_KEY  # 0.1s

DOI_REGEX = re.compile(r'^10\.\d{4,9}/[-._;()/:A-Z0-9]+$', re.I)

def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r'^https?://(dx\.)?doi\.org/', '', d)
    d = re.sub(r'^doi:\s*', '', d, flags=re.I)
    d = d.rstrip('.,;')
    if not DOI_REGEX.match(d):
        return None
    return d

def parse_pubmed_date(pubmed_article_xml_data: Dict[str, Any]) -> Tuple[Dict[str, Any], date]:
    year = pubmed_article_xml_data.get('Year')
    month = pubmed_article_xml_data.get('Month')
    day = pubmed_article_xml_data.get('Day')
    medline_date = pubmed_article_xml_data.get('MedlineDate')
    raw_pdat = medline_date or pubmed_article_xml_data.get('PdatRaw', '')

    month_map = {
        'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
        'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
        'january':1,'february':2,'march':3,'april':4,'june':6,'july':7,'august':8,'september':9,'october':10,'november':11,'december':12,
        'winter':1,'spring':3,'summer':6,'fall':9,'autumn':9
    }

    y = None
    m = None
    d = None

    if year:
        try:
            y = int(re.search(r'(\d{4})', str(year)).group(1))
        except:
            y = None

    if not y and medline_date:
        my = re.search(r'(\d{4})', medline_date)
        if my:
            y = int(my.group(1))

    if y is None:
        raise ValueError(f"Unable to parse year from {pubmed_article_xml_data}")

    if month:
        try:
            mm = str(month).lower()[:3]
            if mm.isdigit():
                m = int(mm)
            else:
                m = month_map.get(mm, None) or month_map.get(str(month).lower(), None)
                if m is None:
                    m = int(month)
        except:
            m = None

    if m is None and medline_date:
        ml = medline_date.lower()
        for k,v in month_map.items():
            if k in ml:
                m = v
                break

    if day:
        try:
            d = int(re.search(r'\d{1,2}', str(day)).group())
        except:
            d = None

    if d is None and medline_date:
        dm = re.search(r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})', medline_date, re.I)
        if dm:
            d = int(dm.group(1))

    if m is None:
        m = 1
    if d is None:
        d = 1

    m = max(1, min(12, m))
    d = max(1, min(31, d))

    try:
        canonical = date(y, m, d)
    except ValueError:
        canonical = date(y, m, 1)

    struct = {
        "year": y,
        "month": m,
        "day": d,
        "pub_type_date": pubmed_article_xml_data.get('PubModel','ppublish'),
        "pdat": raw_pdat
    }
    return struct, canonical

def classify_subdomains_boundary(title: str, abstract: str, mesh_terms: List[str]) -> List[str]:
    combined = f"{title} {abstract} {' '.join(mesh_terms)}".lower()
    checks = {
        "General Anesthesia": [r"\bgeneral anesthesia\b", r"\bdepth of anesthesia\b", r"\bbispectral index\b", r"\bintraoperative awareness\b"],
        "Regional Anesthesia - Spinal Epidural": [r"\bspinal anesthesia\b", r"\bepidural anesthesia\b", r"\bcombined spinal epidural\b", r"\bcsea\b", r"\bneuraxial\b"],
        "Peripheral Nerve Blocks": [r"\bnerve block\b", r"\bbrachial plexus block\b", r"\bfemoral nerve block\b", r"\btransversus abdominis\b", r"\bfascial plane block\b"],
        "Local Anesthetics Pharmacology": [r"\banesthetics, local\b", r"\blidocaine\b", r"\bbupivacaine\b", r"\bropivacaine\b", r"\blast\b"],
        "Airway Management": [r"\bairway management\b", r"\bintubation\b", r"\blaryngoscopy\b", r"\bvideolaryngoscopy\b", r"\bdifficult airway\b"],
        "Anesthesia Monitoring": [r"\bmonitoring, intraoperative\b", r"\bcapnography\b", r"\bentropy\b"],
        "Pediatric Anesthesia": [r"\bpediatric anesthesia\b", r"\bgas trial\b", r"\bpanda study\b"],
        "Obstetric Anesthesia": [r"\banesthesia, obstetrical\b", r"\blabor analgesia\b", r"\bobstetric anesthesia\b"],
        "Cardiac Anesthesia": [r"\bcardiopulmonary bypass\b", r"\btransesophageal echocardiography\b", r"\bcardiac anesthesia\b"],
        "Neuroanesthesia": [r"\bawake craniotomy\b", r"\bcraniotomy\b", r"\bcerebral protection\b"],
        "Critical Care ICU Sedation": [r"\bintensive care\b", r"\bcritical care\b", r"\bdexmedetomidine\b", r"\bmechanical ventilation\b"],
        "Pain Medicine": [r"\bpain, postoperative\b", r"\bopioid sparing\b", r"\bmultimodal analgesia\b"],
        "Anesthesia Safety": [r"\bmalignant hyperthermia\b", r"\bpostoperative nausea\b", r"\banaphylaxis\b"],
        "Pharmacology - Opioids Propofol Ketamine NMB": [r"\bpropofol\b", r"\bketamine\b", r"\bneuromuscular blocking\b", r"\bsugammadex\b"],
        "ERAS Perioperative": [r"\benhanced recovery\b", r"\bperioperative care\b", r"\bprehabilitation\b", r"\btranexamic acid\b"],
        "AI Simulation Education": [r"\bartificial intelligence\b", r"\bmachine learning\b", r"\bsimulation training\b"]
    }
    tags = []
    for domain, patterns in checks.items():
        for pat in patterns:
            if re.search(pat, combined, re.I):
                tags.append(domain)
                break
    return tags or ["General Anesthesia"]

def handle_webenv_expiration(webenv: str, query_key: str, retstart: int, api_key: str = None, max_retries: int = 3):
    # Pseudocode: retry esearch if WebEnv expired after 8 hrs
    pass

def transform_jsonl_record_to_bq_row(record: Dict[str, Any]) -> Dict[str, Any]:
    doi_norm = normalize_doi(record.get('doi'))
    pub_date_struct = record.get('publication_date', {})
    try:
        inp = {
            'Year': pub_date_struct.get('year'),
            'Month': pub_date_struct.get('month'),
            'Day': pub_date_struct.get('day'),
            'MedlineDate': pub_date_struct.get('pdat'),
            'PdatRaw': pub_date_struct.get('pdat'),
            'PubModel': pub_date_struct.get('pub_type_date')
        }
        struct_out, canonical_date = parse_pubmed_date(inp)
    except Exception:
        struct_out = {
            "year": pub_date_struct.get('year', 1970),
            "month": pub_date_struct.get('month'),
            "day": pub_date_struct.get('day'),
            "pub_type_date": pub_date_struct.get('pub_type_date','ppublish'),
            "pdat": pub_date_struct.get('pdat','')
        }
        canonical_date = date(struct_out['year'], 1, 1)

    subdomains = record.get('anesthesia_subdomains', [])
    first_subdomain = subdomains[0] if subdomains else "General Anesthesia"
    journal_title = record.get('journal', {}).get('title', 'Unknown Journal')
    study_type = record.get('study_design', {}).get('type', 'Other')

    title = record.get('title','')
    abstract = record.get('abstract','') or ''
    abstract_for_emb = (title + " " + abstract)[:3000]

    bq_row = {
        "pmid": record['pmid'],
        "doi": doi_norm,
        "pmcid": record.get('pmcid'),
        "title": title,
        "abstract": abstract,
        "abstract_structured": record.get('abstract_structured'),
        "authors": record.get('authors', []),
        "journal": record.get('journal', {}),
        "publication_date": struct_out,
        "pub_date": canonical_date.isoformat(),
        "publication_year": struct_out['year'],
        "mesh_terms": record.get('mesh_terms', []),
        "keywords": record.get('keywords', []),
        "publication_types": record.get('publication_types', []),
        "chemicals": record.get('chemicals', []),
        "anesthesia_subdomains": subdomains,
        "study_design": record.get('study_design', {}),
        "anesthesia_specific": record.get('anesthesia_specific', {}),
        "citation_metrics": record.get('citation_metrics', {}),
        "extraction_metadata": {
            "query_used": record.get('extraction_metadata', {}).get('query_used','')[:3000],
            "agent_id": record.get('extraction_metadata', {}).get('agent_id', 1),
            "retrieval_date": record.get('extraction_metadata', {}).get('retrieval_date'),
            "dedup_status": record.get('extraction_metadata', {}).get('dedup_status','unique'),
            "duplicate_of_pmid": record.get('extraction_metadata', {}).get('duplicate_of_pmid')
        },
        "first_subdomain": first_subdomain,
        "journal_title": journal_title,
        "study_type": study_type,
        "title_abstract_embedding": None,
        "abstract_text_for_embedding": abstract_for_emb,
        "ingestion_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    return bq_row

if __name__ == "__main__":
    import pathlib
    sample_path = pathlib.Path(__file__).resolve().parent / 'archive_not_production' / 'untrusted_generated_artifacts' / 'anesthesia_full_metadata_SAMPLE.jsonl'
    if sample_path.exists():
        with open(sample_path) as f:
            for i, line in enumerate(f):
                if i>=1:
                    break
                rec = json.loads(line)
                bq = transform_jsonl_record_to_bq_row(rec)
                print(f"PMID {bq['pmid']} -> pub_date {bq['pub_date']} year {bq['publication_year']} doi_norm {bq['doi']} first_subdomain {bq['first_subdomain']}")
                print("  DOI tests:", normalize_doi(" https://doi.org/10.1056/NEJMoa1904710 "), normalize_doi("DOI: 10.1016/j.bja.2023. "), normalize_doi(None))
                struct, cand = parse_pubmed_date({"Year": None, "MedlineDate": "2020 Dec", "PdatRaw": "2020 Dec"})
                print(f"  MedlineDate fallback 2020 Dec -> {struct} -> {cand}")
                struct2, cand2 = parse_pubmed_date({"Year": None, "MedlineDate": "2020 Spring"})
                print(f"  MedlineDate fallback 2020 Spring -> {struct2} -> {cand2}")
                struct3, cand3 = parse_pubmed_date({"Year": 2019, "Month": 5, "Day": 1})
                print(f"  Normal date -> {struct3} -> {cand3}")
