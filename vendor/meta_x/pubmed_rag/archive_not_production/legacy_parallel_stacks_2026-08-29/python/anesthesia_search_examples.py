
import psycopg2
from psycopg2.extras import RealDictCursor

# Optimized queries leveraging B3 indexes

# 1. MeSH exact array containment (avoids substring FP audit issue)
QUERY_MESH_EXACT = """
SELECT pmid, title, publication_year, mesh_descriptor_names
FROM anesthesia_pubmed_records
WHERE mesh_descriptor_names @> ARRAY['Anesthetics, Local']  -- uses idx_anesth_mesh_names_gin GIN
  AND mesh_terms @> '[{"descriptor_name": "Anesthetics, Local"}]'::jsonb  -- uses jsonb_path_ops
LIMIT 100;
"""

# 2. Full-text weighted search with ranking
QUERY_FTS_RANKED = """
SELECT pmid, title, journal_title, publication_year,
       ts_rank(search_vector, q) AS rank,
       ts_headline('english', abstract, q, 'StartSel=<mark>, StopSel=</mark>, MaxFragments=3') AS highlight
FROM anesthesia_pubmed_records, to_tsquery('english', %s) q
WHERE search_vector @@ q
  AND anesthesia_subdomains @> ARRAY['Peripheral Nerve Blocks']
ORDER BY rank DESC
LIMIT 50;
"""
# params e.g. "(ultrasound & guided & nerve) & (block | TAP)"

# 3. Subdomain aggregation using materialized view (ms instead of seq scan 300k)
QUERY_SUBDOMAIN_DASHBOARD = """
SELECT * FROM mv_subdomain_overview ORDER BY total_records DESC;
"""

# 4. Fascial plane blocks - terminology not stable MeSH, needs FTS + trigram fallback
QUERY_FACIAL_PLANE = """
SELECT pmid, title
FROM anesthesia_pubmed_records
WHERE (
    search_vector @@ to_tsquery('english', '(erector & spinae) | ESPB | (transversus & abdominis) | TAP | QLB | PENG')
    OR title ILIKE '%%fascial plane%%'  -- uses idx_anesth_title_trgm
)
AND publication_year >= 2019
ORDER BY publication_year DESC
LIMIT 100;
"""

# 5. Drug-outcome cooccurrence using GIN composite
QUERY_DRUG_OUTCOME = """
SELECT pmid, title, drugs, outcomes
FROM anesthesia_pubmed_records
WHERE drugs @> ARRAY['Propofol'] AND outcomes @> ARRAY['Postoperative Nausea and Vomiting']
  AND publication_year >= 2020
ORDER BY citation_count_openalex DESC NULLS LAST
LIMIT 50;
"""

# 6. Vector semantic search (if embeddings populated)
QUERY_VECTOR = """
SELECT pmid, title, embedding <=> %s::vector AS distance
FROM anesthesia_pubmed_records
ORDER BY distance
LIMIT 20;
"""

# 7. Yearly trend from mv
QUERY_YEARLY_TREND = """
SELECT publication_year, record_count, rct_count
FROM mv_subdomain_yearly_trends
WHERE subdomain = 'Pediatric Anesthesia'
ORDER BY publication_year;
"""

def run_example(conn_str, ts_query="(general & anesthesia & awareness)"):
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(QUERY_FTS_RANKED, (ts_query,))
    rows = cur.fetchall()
    print(f"FTS returned {len(rows)} rows")
    cur.close()
    conn.close()
    return rows

# DOI normalization audit fix - Python helper (mirror SQL generated column)
import re
def normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r'^\s*https?://(dx\.)?doi\.org/', '', doi, flags=re.I)
    doi = re.sub(r'^\s*doi:\s*', '', doi, flags=re.I)
    doi = doi.strip('/').lower()
    return doi

# MedlineDate fallback parser - audit fix
def parse_medline_date_fallback(year_raw, month_raw, day_raw, medline_date_str):
    """Handles MedlineDate like '2023 Spring' or '2021 Dec-2022 Jan'"""
    try:
        if year_raw:
            y = int(year_raw)
            m = int(month_raw) if month_raw else 1
            d = int(day_raw) if day_raw else 1
            return (y,m,d)
    except:
        pass
    # fallback regex from MedlineDate string
    if medline_date_str:
        m = re.search(r'(19|20)\d{2}', medline_date_str)
        if m:
            y = int(m.group(0))
            # try month name
            month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            month_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', medline_date_str, re.I)
            mm = month_map[month_match.group(1).lower()[:3]] if month_match else 1
            return (y, mm, 1)
    return (None, None, None)

# Substring FP fix - exact match vs substring audit
def classify_subdomains_exact_match(combined_text_lower: str, mesh_descriptor_names: list):
    """Fix for audit: classification FP via substring. Use word boundaries and exact MeSH."""
    checks = {
        "General Anesthesia": lambda: "anesthesia, general" in [m.lower() for m in mesh_descriptor_names] or re.search(r'\bgeneral anesthesia\b', combined_text_lower),
        "Regional Anesthesia - Spinal Epidural": lambda: any(x in mesh_descriptor_names for x in ["Anesthesia, Spinal","Anesthesia, Epidural","Anesthesia, Conduction"]),
        # add exact set checks, not substring "block" alone
        "Peripheral Nerve Blocks": lambda: "Nerve Block" in mesh_descriptor_names or re.search(r'\bnerve block\b|\bbrachial plexus block\b|\bTAP block\b', combined_text_lower),
    }
    tags = []
    for domain, fn in checks.items():
        try:
            if fn():
                tags.append(domain)
        except: pass
    return tags
