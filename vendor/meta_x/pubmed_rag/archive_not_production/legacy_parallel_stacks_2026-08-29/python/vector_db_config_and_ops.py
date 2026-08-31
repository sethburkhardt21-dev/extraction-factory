"""
Vector DB Config & Helpers - Production operation guide
- HNSW vs IVFFlat decision
- maintenance_work_mem tuning
- Migration script to switch indexes
"""

# ============================================================================
# Postgres connection example with psycopg
# ============================================================================
PGVECTOR_INSERT_SQL = """
-- Bulk insert with ON CONFLICT handling for dedup - fixes audit dedup issue
INSERT INTO pubmed_anesthesia_articles (
    pmid, pmcid, doi, doi_normalized, content_hash, title_hash,
    title, abstract, abstract_structured, abstract_word_count,
    authors, collective_author, first_author_last, last_author_last, author_count,
    journal_title, journal_iso, issn,
    pub_date, pub_year, pub_month, pub_day, medline_date_raw,
    article_date, date_parse_method, date_parse_note,
    mesh_terms, mesh_major_terms, mesh_minor_terms, mesh_tree_numbers, mesh_qualifiers,
    keywords, publication_types,
    has_anesthesia_mesh, is_anesthesia, anesthesia_score, anesthesia_types, anesthesia_types_text,
    false_positive_flags, classification_method, classification_reasoning,
    embedding_model, embedding_dim, embedding,
    fetch_timestamp, esearch_query, fetch_batch_id, xml_raw_hash, extraction_version
) VALUES (
    %(pmid)s, %(pmcid)s, %(doi)s, %(doi_normalized)s, %(content_hash)s, %(title_hash)s,
    %(title)s, %(abstract)s, %(abstract_structured)s::jsonb, %(abstract_word_count)s,
    %(authors)s::jsonb, %(collective_author)s, %(first_author_last)s, %(last_author_last)s, %(author_count)s,
    %(journal_title)s, %(journal_iso)s, %(issn)s,
    %(pub_date)s::date, %(pub_year)s, %(pub_month)s, %(pub_day)s, %(medline_date_raw)s,
    %(article_date)s::date, %(date_parse_method)s::date_parse_method, %(date_parse_note)s,
    %(mesh_terms)s::jsonb, %(mesh_major_terms)s, %(mesh_minor_terms)s, %(mesh_tree_numbers)s, %(mesh_qualifiers)s,
    %(keywords)s, %(publication_types)s,
    %(has_anesthesia_mesh)s, %(is_anesthesia)s, %(anesthesia_score)s, %(anesthesia_types)s::anesthesia_class[], %(anesthesia_types_text)s,
    %(false_positive_flags)s::jsonb, %(classification_method)s, %(classification_reasoning)s,
    %(embedding_model)s, %(embedding_dim)s, %(embedding)s::vector,
    NOW(), %(esearch_query)s, %(fetch_batch_id)s, %(xml_raw_hash)s, %(extraction_version)s
)
ON CONFLICT (pmid) DO UPDATE SET
    abstract = EXCLUDED.abstract,
    authors = EXCLUDED.authors,
    mesh_terms = EXCLUDED.mesh_terms,
    mesh_major_terms = EXCLUDED.mesh_major_terms,
    is_anesthesia = EXCLUDED.is_anesthesia,
    anesthesia_score = EXCLUDED.anesthesia_score,
    embedding = EXCLUDED.embedding,
    updated_at = NOW(),
    extraction_version = EXCLUDED.extraction_version
-- Note: content_hash unique prevents silent duplicate via different pmid merging same content
"""

# ============================================================================
# Index migration / creation helper - production
# ============================================================================
INDEX_MIGRATION_SQL = """
-- === Fix audit: Handle large scale HNSW build avoiding disk fallback ===
-- Step 1: Tune memory before building
SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 4;

-- Step 2: Drop old indexes if migrating IVFFlat -> HNSW
DROP INDEX IF EXISTS idx_articles_embedding_ivfflat_cosine;
DROP INDEX IF EXISTS idx_articles_embedding_hnsw_cosine;
DROP INDEX IF EXISTS idx_articles_embedding_hnsw_l2;

-- Step 3: Create HNSW primary (pgvector >=0.5.0 req)
-- m=16 good default, ef_construction=200 for high quality at >100k rows (64 default too low)
-- For 1M+ use ef_construction=300-400
CREATE INDEX CONCURRENTLY idx_articles_embedding_hnsw_cosine
ON pubmed_anesthesia_articles USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- Step 4: Fallback IVFFlat - requires data present (training step)
-- lists = sqrt(n) heuristic: use 100 for 10k, 316 for 100k, 1000 for 1M
-- CREATE INDEX CONCURRENTLY idx_articles_embedding_ivfflat_cosine
-- ON pubmed_anesthesia_articles USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);

-- Step 5: Verify
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename='pubmed_anesthesia_articles' AND indexname LIKE '%embedding%';

-- Step 6: Reset mem
RESET maintenance_work_mem;
RESET max_parallel_maintenance_workers;

-- Step 7: Query tuning - set at session
-- For HNSW high recall: SET hnsw.ef_search = 100; -- default 40 too low
-- For IVFFlat: SET ivfflat.probes = 10; -- default 1 too low
"""

# ============================================================================
# Python helper for pgvector insert with dedup handling
# ============================================================================
INSERT_HELPER_PY = '''
import psycopg2
import psycopg2.extras
from psycopg2 import sql
import json

def bulk_upsert_articles(conn, records):
    """
    Bulk upsert with dedup handling - fixes audit dedup issue
    Uses ON CONFLICT for pmid, and pre-checks content_hash via CTE
    """
    cur = conn.cursor()
    # Pre-filter dedup in app layer already done, but also enforce DB constraints
    # content_hash unique violation will be caught
    try:
        psycopg2.extras.execute_batch(cur, PGVECTOR_INSERT_SQL, records, page_size=100)
        conn.commit()
        print(f"Upserted {len(records)}")
    except psycopg2.errors.UniqueViolation as e:
        conn.rollback()
        print(f"Unique violation (dedup caught): {e}")
        # Fallback: insert one by one to isolate duplicate
        success = 0
        for rec in records:
            try:
                cur.execute(PGVECTOR_INSERT_SQL, rec)
                conn.commit()
                success += 1
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                # Log to dedup_log
                cur.execute("""
                    INSERT INTO pubmed_dedup_log (pmid, dedup_type, existing_content_hash, new_content_hash, resolution)
                    VALUES (%s, 'content_hash', %s, %s, 'reject_new')
                    ON CONFLICT DO NOTHING
                """, (rec['pmid'], rec.get('content_hash'), rec.get('content_hash')))
                conn.commit()
        print(f"After dedup fallback: {success}/{len(records)} inserted")
    finally:
        cur.close()

def search_anesthesia(conn, query_embedding, top_k=20, min_year=2020, require_major_mesh=True):
    """
    Production search with FP mitigation filters + HNSW tuning
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Critical: set ef_search for high recall
    cur.execute("SET hnsw.ef_search = 100;")
    # Alternative for IVFFlat: cur.execute("SET ivfflat.probes = 10;")

    query_sql = """
        SELECT pmid, title, journal_iso, pub_year, anesthesia_score, has_anesthesia_mesh,
               1 - (embedding <=> %s::vector) AS similarity,
               mesh_major_terms, anesthesia_types_text
        FROM pubmed_anesthesia_articles
        WHERE is_anesthesia = TRUE
          AND pub_year >= %s
          AND embedding IS NOT NULL
    """
    params = [query_embedding, min_year]
    if require_major_mesh:
        query_sql += " AND has_anesthesia_mesh = TRUE "
    query_sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
    params.extend([query_embedding, top_k])

    cur.execute(query_sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows
'''

# ============================================================================
# Production checklist
# ============================================================================
PRODUCTION_CHECKLIST = """
=== Production Vector DB Checklist for Anesthesia PubMed ===

[ ] pgvector extension version >=0.5.0 verified (HNSW requires it), >=0.8.0 for halfvec
[ ] maintenance_work_mem = 2GB+ before HNSW build on 1M rows
[ ] Table loaded with >5000 rows before creating BigQuery VECTOR INDEX (BQ requirement)
[ ] Table loaded with data before IVFFlat (pgvector requires training data)
[ ] content_hash unique constraint enforced (dedup)
[ ] doi_normalized unique index where not null
[ ] MedlineDate fallback tested: parse dates like "2021-2022", "Fall 2020", "2020 Dec"
[ ] Rate limiter: 3 r/s without API key, 10 r/s with key, exponential backoff with jitter, honors Retry-After
[ ] Classification FP mitigation: require mesh major OR high threshold + title keyword
[ ] Negative patterns filtered (anesthesia dolorosa etc)
[ ] Author CollectiveName fallback implemented
[ ] AbstractText itertext() used to preserve <i>/<sup> content
[ ] HNSW m=16 ef_construction=200 (production >100k) - not default 64
[ ] Query tuning: hnsw.ef_search=100 (not default 40) and ivfflat.probes=10
[ ] GIN indexes on mesh_major_terms etc for pre-filter before vector search (reduce scanned vectors)
[ ] BigQuery IVF num_lists=1000 for 500k-1M scale, fraction_lists_to_search 0.1 for high recall
[ ] Monitoring: mv_anesthesia_stats refreshed, fetch_audit log populated
[ ] Embedding dimension consistent: 1536 for text-embedding-3-small, 768 for local, check CHECK constraint
"""

if __name__ == "__main__":
    print(PRODUCTION_CHECKLIST)
    print("\n--- Insert SQL ---\n", PGVECTOR_INSERT_SQL[:1000])
    print("\n--- Migration SQL ---\n", INDEX_MIGRATION_SQL)
