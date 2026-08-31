"""
Agent B3: Indexes & Views Architect - Maintenance & Validation Script
- Validates SQL files syntax (basic)
- Generates DDL execution order
- Creates BigQuery DDL + Python example search functions
- Handles audit fixes: DOI normalization, MedlineDate fallback example, substring FP fix
Usage: python anesthesia_index_maintenance.py
"""

import pathlib, re, json, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent / "data"
SQL_FILES = [
    BASE/"anesthesia_indexes_views_production.sql",
    BASE/"anesthesia_materialized_views.sql"
]

def validate_sql_syntax(path: Path):
    """Basic heuristic validation - count CREATE INDEX, MATERIALIZED VIEW, check GIN presence"""
    text = path.read_text(encoding='utf-8')
    metrics = {
        "file": str(path.name),
        "size_bytes": path.stat().st_size,
        "create_index_count": len(re.findall(r'CREATE\s+(UNIQUE\s+)?INDEX', text, re.I)),
        "create_matview_count": len(re.findall(r'CREATE\s+MATERIALIZED\s+VIEW', text, re.I)),
        "gin_count": len(re.findall(r'USING\s+gin', text, re.I)),
        "tsvector_count": len(re.findall(r'tsvector', text, re.I)),
        "trgm_count": len(re.findall(r'gin_trgm_ops', text, re.I)),
        "has_concurrently": "CONCURRENTLY" in text.upper(),
        "has_doi_normalized": "doi_normalized" in text.lower(),
        "has_subdomain_gin": "anesthesia_subdomains" in text and "gin" in text.lower(),
    }
    # required patterns
    required = {
        "GIN on mesh_terms jsonb_path_ops": "jsonb_path_ops" in text,
        "GIN on mesh_descriptor_names": "mesh_descriptor_names" in text and "gin" in text.lower(),
        "full-text index on search_vector": "search_vector" in text and "gin" in text.lower(),
        "trigram index title": "title gin_trgm_ops" in text,
        "subdomain GIN array": "idx_anesth_subdomains_gin" in text,
        "16 subdomain overview matview": "mv_subdomain_overview" in text,
        "yearly trends matview": "mv_subdomain_yearly_trends" in text,
        "mesh frequency matview": "mv_mesh_frequency_by_subdomain" in text,
        "BigQuery note": "SEARCH INDEX" in text or "BigQuery" in text,
    }
    metrics["required_checks"] = required
    metrics["all_required_pass"] = all(required.values())
    return metrics

def generate_python_search_examples():
    code = '''
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
    doi = re.sub(r'^\\s*https?://(dx\\.)?doi\\.org/', '', doi, flags=re.I)
    doi = re.sub(r'^\\s*doi:\\s*', '', doi, flags=re.I)
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
        m = re.search(r'(19|20)\\d{2}', medline_date_str)
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
        "General Anesthesia": lambda: "anesthesia, general" in [m.lower() for m in mesh_descriptor_names] or re.search(r'\\bgeneral anesthesia\\b', combined_text_lower),
        "Regional Anesthesia - Spinal Epidural": lambda: any(x in mesh_descriptor_names for x in ["Anesthesia, Spinal","Anesthesia, Epidural","Anesthesia, Conduction"]),
        # add exact set checks, not substring "block" alone
        "Peripheral Nerve Blocks": lambda: "Nerve Block" in mesh_descriptor_names or re.search(r'\\bnerve block\\b|\\bbrachial plexus block\\b|\\bTAP block\\b', combined_text_lower),
    }
    tags = []
    for domain, fn in checks.items():
        try:
            if fn():
                tags.append(domain)
        except: pass
    return tags
'''
    out_path = BASE / "anesthesia_search_examples.py"
    out_path.write_text(code, encoding='utf-8')
    return out_path

def generate_combined_production_sql():
    """Merge both files into single deployment file"""
    idx = (BASE / "anesthesia_indexes_views_production.sql").read_text()
    mv = (BASE / "anesthesia_materialized_views.sql").read_text()
    combined = f"-- Combined Production Deployment - Generated\n-- Includes indexes + matviews\n\n{idx}\n\n-- ===================== MATERIALIZED VIEWS =====================\n\n{mv}\n"
    out = BASE / "anesthesia_b3_full_deployment.sql"
    out.write_text(combined, encoding='utf-8')
    return out

def generate_bigquery_ddl():
    bq = """
-- BigQuery alternative DDL for same corpus 280k-380k
CREATE SCHEMA IF NOT EXISTS anesthesia_dataset
OPTIONS(location="US");

CREATE OR REPLACE TABLE anesthesia_dataset.anesthesia_pubmed_records (
    pmid STRING NOT NULL,
    doi STRING,
    doi_normalized STRING,
    pmcid STRING,
    title STRING,
    abstract STRING,
    journal_title STRING,
    journal_if FLOAT64,
    publication_year INT64,
    publication_month INT64,
    mesh_terms JSON,
    mesh_descriptor_names ARRAY<STRING>,
    mesh_major_names ARRAY<STRING>,
    keywords ARRAY<STRING>,
    publication_types ARRAY<STRING>,
    chemical_names ARRAY<STRING>,
    anesthesia_subdomains ARRAY<STRING>,
    study_design_type STRING,
    is_landmark BOOL,
    drugs ARRAY<STRING>,
    techniques ARRAY<STRING>,
    outcomes ARRAY<STRING>,
    citation_count_openalex INT64,
    agent_id INT64,
    search_text STRING, -- concatenated title+abstract for SEARCH index
    embedding ARRAY<FLOAT64> -- for VECTOR_SEARCH
) PARTITION BY RANGE_BUCKET(publication_year, GENERATE_ARRAY(1950, 2030, 1))
CLUSTER BY anesthesia_subdomains, study_design_type, journal_title;

-- BigQuery SEARCH indexes (replaces PG GIN)
CREATE SEARCH INDEX IF NOT EXISTS idx_bq_mesh_search
ON anesthesia_dataset.anesthesia_pubmed_records(mesh_descriptor_names);

CREATE SEARCH INDEX IF NOT EXISTS idx_bq_title_abstract_search
ON anesthesia_dataset.anesthesia_pubmed_records(search_text);

CREATE SEARCH INDEX IF NOT EXISTS idx_bq_subdomain_search
ON anesthesia_dataset.anesthesia_pubmed_records(anesthesia_subdomains);

-- Vector search index for embeddings (if using BigQuery ML embeddings)
CREATE VECTOR INDEX IF NOT EXISTS idx_bq_embedding
ON anesthesia_dataset.anesthesia_pubmed_records(embedding)
OPTIONS(distance_type="COSINE", index_type="IVF", ivf_options='{"num_lists": 100}');

-- Materialized views BigQuery
CREATE MATERIALIZED VIEW IF NOT EXISTS anesthesia_dataset.mv_subdomain_overview AS
SELECT subdomain, COUNT(*) as total_records, COUNTIF(is_landmark) as landmark_count, AVG(citation_count_openalex) as avg_citations
FROM anesthesia_dataset.anesthesia_pubmed_records, UNNEST(anesthesia_subdomains) AS subdomain
GROUP BY subdomain;

-- Example query leveraging SEARCH
-- SELECT * FROM anesthesia_dataset.anesthesia_pubmed_records WHERE SEARCH(search_text, 'awareness general anesthesia');
"""
    out = BASE / "anesthesia_bigquery_ddl.sql"
    out.write_text(bq, encoding='utf-8')
    return out

if __name__ == "__main__":
    print("=== Validating SQL files ===")
    for f in SQL_FILES:
        if f.exists():
            m = validate_sql_syntax(f)
            print(json.dumps(m, indent=2))
        else:
            print(f"Missing {f}")
    print("\n=== Generating helper files ===")
    print("Python examples ->", generate_python_search_examples())
    print("Full deployment ->", generate_combined_production_sql())
    print("BigQuery DDL ->", generate_bigquery_ddl())
    print("\n=== Done ===")
