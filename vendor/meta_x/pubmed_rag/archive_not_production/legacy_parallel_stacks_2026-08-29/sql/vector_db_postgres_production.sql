-- ============================================================================
-- PRODUCTION VECTOR DB SCHEMA - PubMed Anesthesia Extraction
-- Agent C2: Vector DB Architect - Swarm C Embedding Pipeline
-- Fixes audit issues: rate limits handled in app layer, dedup, FP, MedlineDate
-- Supports pgvector extension with HNSW (primary) + IVFFlat (fallback)
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector >=0.5.0 required for HNSW
CREATE EXTENSION IF NOT EXISTS pg_trgm;         -- trigram search for dedup
CREATE EXTENSION IF NOT EXISTS btree_gin;       -- gin compound indexes

-- ============================================================================
-- PERFORMANCE TUNING - Apply before index builds on large tables
-- CRITICAL: HNSW build is memory-bound. Set maintenance_work_mem high.
-- For 1M x 1536-dim, need 1GB+ maintenance_work_mem to avoid disk fallback
-- Reference: pgvector NOTICE "hnsw graph no longer fits into maintenance_work_mem"
-- ============================================================================
-- SET maintenance_work_mem = '2GB';  -- Uncomment for index creation
-- SET max_parallel_maintenance_workers = 4;

-- ============================================================================
-- ENUMS
-- ============================================================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='date_parse_method') THEN
        CREATE TYPE date_parse_method AS ENUM (
            'pubdate_year_month',
            'pubdate_year_only',
            'article_date',
            'medline_date_full',
            'medline_date_range_start',
            'medline_date_season',
            'medline_date_fallback_regex',
            'unknown'
        );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='anesthesia_class') THEN
        CREATE TYPE anesthesia_class AS ENUM (
            'general',
            'inhalation',
            'intravenous',
            'balanced',
            'conduction',
            'regional',
            'spinal',
            'epidural',
            'local',
            'obstetrical',
            'dissociative',
            'monitored',
            'unknown'
        );
    END IF;
END $$;

-- ============================================================================
-- MAIN TABLE: pubmed anesthesia articles with full metadata + vector
-- ============================================================================
CREATE TABLE IF NOT EXISTS pubmed_anesthesia_articles (
    -- Primary Identifiers (DEDUP KEYS)
    pmid BIGINT PRIMARY KEY,
    pmcid TEXT,
    doi TEXT,

    -- DEDUP: content hash to prevent duplicate title+abstract ingestion
    -- Fixes audit: dedup critical issue
    content_hash TEXT UNIQUE NOT NULL,  -- sha256(normalized lower title + abstract)
    title_hash TEXT NOT NULL,           -- separate for title-only dedup check
    doi_normalized TEXT,                -- lower(doi) without prefix

    -- Bibliographic
    title TEXT NOT NULL,
    title_clean TEXT,                   -- stripped XML tags
    abstract TEXT,
    abstract_structured JSONB,           -- [{"label":"BACKGROUND","text":...}] for labeled abstracts
    abstract_word_count INT,

    -- Authors: Fix audit - CollectiveName fallback
    -- Schema: [{"last_name":..., "fore_name":..., "full_name":..., "collective":false, "orcid":..., "affiliations":[...]}]
    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    collective_author TEXT,              -- For consortiums
    first_author_last TEXT,
    last_author_last TEXT,
    author_count INT,

    -- Journal
    journal_title TEXT,
    journal_iso TEXT,
    journal_nlm_id TEXT,
    issn TEXT,
    issn_type TEXT,
    volume TEXT,
    issue TEXT,
    pages TEXT,

    -- Dates: Fix audit - Missing MedlineDate fallback
    -- Parsing priority: PubDate Year+Month -> Year -> ArticleDate -> MedlineDate regex -> unknown
    pub_date DATE,
    pub_year INT,                        -- Never null fallback via MedlineDate regex extraction
    pub_month INT,
    pub_day INT,
    medline_date_raw TEXT,               -- Store original e.g. "2021-2022" or "Fall 2020"
    article_date DATE,                   -- Electronic publication date
    date_parse_method date_parse_method NOT NULL DEFAULT 'unknown',
    date_parse_note TEXT,

    -- MeSH Terms: Fix audit - classification FP
    -- Full structure for FP filtering: need MajorTopicYN, TreeNumber check
    mesh_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Example: [{"descriptor":"Anesthesia, General", "ui":"D000760", "major":true, "qualifiers":[{"name":"adverse effects","major":false}]}]
    mesh_major_terms TEXT[] DEFAULT '{}', -- Only MajorTopicYN=Y descriptors
    mesh_minor_terms TEXT[] DEFAULT '{}',
    mesh_tree_numbers TEXT[] DEFAULT '{}', -- E03.155.* for anesthesia branch
    mesh_qualifiers TEXT[] DEFAULT '{}',

    -- Other indexing
    keywords TEXT[] DEFAULT '{}',        -- KeywordList
    chemical_list JSONB DEFAULT '[]'::jsonb,  -- [{"registry":"...","name":"..."}]
    grant_list JSONB DEFAULT '[]'::jsonb,
    publication_types TEXT[] DEFAULT '{}', -- e.g., {Journal Article, Review, Meta-Analysis}

    -- Anesthesia Specific Classification
    has_anesthesia_mesh BOOLEAN NOT NULL DEFAULT FALSE, -- Did MeSH contain E03.155.* ?
    is_anesthesia BOOLEAN NOT NULL DEFAULT FALSE,       -- Final determination
    anesthesia_score DOUBLE PRECISION,   -- 0-1 classifier confidence
    anesthesia_types anesthesia_class[] DEFAULT '{}',
    anesthesia_types_text TEXT[] DEFAULT '{}', -- string version for query
    procedure_context TEXT[],            -- e.g., {cardiac, pediatric, obstetric}
    classification_method TEXT,          -- 'mesh_major+keyword', 'mesh_only', 'ml_model'
    classification_version TEXT DEFAULT 'v2.0',
    false_positive_flags JSONB DEFAULT '{}'::jsonb, -- {"low_mesh_confidence":true, "no_major_topic":true, "negative_pattern_matched":"..."}
    classification_reasoning TEXT,

    -- Embeddings - Support multiple dimensions, primary 1536 (OpenAI) + 768 fallback
    embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    embedding_dim INT NOT NULL DEFAULT 1536 CHECK (embedding_dim IN (256,384,512,768,1024,1536,3072)),
    embedding_version TEXT DEFAULT 'v1',
    -- Primary vector column - cosine distance is standard for semantic search
    embedding VECTOR(1536),

    -- Optional halfvec for storage optimization (pgvector >=0.7.0)
    -- Uncomment if using halfvec: embedding_half halfvec(1536)

    -- Audit & Provenance
    fetch_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    esearch_query TEXT,
    fetch_batch_id TEXT,
    xml_raw_hash TEXT,                   -- hash of raw XML for change detection
    extraction_version TEXT DEFAULT 'v2.1-fixed',
    is_retracted BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- DEDUP Supporting Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS pubmed_dedup_log (
    id BIGSERIAL PRIMARY KEY,
    pmid BIGINT NOT NULL,
    duplicate_of_pmid BIGINT,
    dedup_type TEXT NOT NULL, -- 'pmid_exact', 'doi_exact', 'content_hash', 'title_hash_near', 'title_trgm'
    existing_content_hash TEXT,
    new_content_hash TEXT,
    similarity_score DOUBLE PRECISION,
    resolution TEXT NOT NULL DEFAULT 'reject_new', -- reject_new, keep_both, merge
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dedup_log_pmid ON pubmed_dedup_log(pmid);
CREATE INDEX IF NOT EXISTS idx_dedup_log_hash ON pubmed_dedup_log(existing_content_hash);

-- ============================================================================
-- FETCH AUDIT LOG - Fixes audit: rate limits tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS pubmed_fetch_audit (
    id BIGSERIAL PRIMARY KEY,
    batch_id TEXT NOT NULL,
    query TEXT NOT NULL,
    esearch_time TIMESTAMPTZ DEFAULT NOW(),
    retstart INT,
    retmax INT,
    total_count INT,
    returned_count INT,
    pmids BIGINT[],
    had_rate_limit BOOLEAN DEFAULT FALSE,
    retry_count INT DEFAULT 0,
    backoff_ms BIGINT[],
    http_status_codes INT[],
    error_messages TEXT[],
    eutils_api_key_used BOOLEAN DEFAULT FALSE,
    duration_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fetch_audit_batch ON pubmed_fetch_audit(batch_id);
CREATE INDEX IF NOT EXISTS idx_fetch_audit_time ON pubmed_fetch_audit(esearch_time);

-- ============================================================================
-- CLASSIFICATION AUDIT - Fix audit: FP tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS anesthesia_classification_audit (
    pmid BIGINT PRIMARY KEY REFERENCES pubmed_anesthesia_articles(pmid) ON DELETE CASCADE,
    title TEXT,
    mesh_terms_raw JSONB,
    has_major_anesthesia_mesh BOOLEAN,
    keyword_match_score DOUBLE PRECISION,
    negative_pattern_match TEXT,
    false_positive_risk DOUBLE PRECISION,
    final_label BOOLEAN,
    reviewer_override BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES - B-Tree, GIN for metadata, HNSW + IVFFlat for vector
-- ============================================================================

-- Unique constraints (DEDUP)
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_doi_norm ON pubmed_anesthesia_articles(doi_normalized) WHERE doi_normalized IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_content_hash ON pubmed_anesthesia_articles(content_hash);

-- B-tree for filtering
CREATE INDEX IF NOT EXISTS idx_articles_pub_year ON pubmed_anesthesia_articles(pub_year);
CREATE INDEX IF NOT EXISTS idx_articles_is_anesthesia ON pubmed_anesthesia_articles(is_anesthesia) WHERE is_anesthesia = TRUE;
CREATE INDEX IF NOT EXISTS idx_articles_anesthesia_score ON pubmed_anesthesia_articles(anesthesia_score DESC) WHERE is_anesthesia = TRUE;
CREATE INDEX IF NOT EXISTS idx_articles_journal ON pubmed_anesthesia_articles(journal_iso);
CREATE INDEX IF NOT EXISTS idx_articles_fetch_ts ON pubmed_anesthesia_articles(fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_articles_has_mesh ON pubmed_anesthesia_articles(has_anesthesia_mesh) WHERE has_anesthesia_mesh = TRUE;

-- GIN indexes for array/JSONB filtering (critical for pre-filter before vector search)
CREATE INDEX IF NOT EXISTS idx_articles_mesh_major_gin ON pubmed_anesthesia_articles USING GIN(mesh_major_terms);
CREATE INDEX IF NOT EXISTS idx_articles_mesh_minor_gin ON pubmed_anesthesia_articles USING GIN(mesh_minor_terms);
CREATE INDEX IF NOT EXISTS idx_articles_mesh_tree_gin ON pubmed_anesthesia_articles USING GIN(mesh_tree_numbers);
CREATE INDEX IF NOT EXISTS idx_articles_anesthesia_types_gin ON pubmed_anesthesia_articles USING GIN(anesthesia_types_text);
CREATE INDEX IF NOT EXISTS idx_articles_keywords_gin ON pubmed_anesthesia_articles USING GIN(keywords);
CREATE INDEX IF NOT EXISTS idx_articles_pub_type_gin ON pubmed_anesthesia_articles USING GIN(publication_types);
CREATE INDEX IF NOT EXISTS idx_articles_authors_gin ON pubmed_anesthesia_articles USING GIN(authors jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_articles_fp_flags_gin ON pubmed_anesthesia_articles USING GIN(false_positive_flags);

-- Full Text Search indexes
ALTER TABLE pubmed_anesthesia_articles ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_articles_search_vector ON pubmed_anesthesia_articles USING GIN(search_vector);
-- Trigger to populate tsvector
CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.title,'')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.abstract,'')), 'B') ||
        setweight(to_tsvector('english', COALESCE(array_to_string(NEW.mesh_major_terms,' '),'')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trig_search_vector ON pubmed_anesthesia_articles;
CREATE TRIGGER trig_search_vector BEFORE INSERT OR UPDATE OF title, abstract, mesh_major_terms ON pubmed_anesthesia_articles
FOR EACH ROW EXECUTE FUNCTION update_search_vector();

-- Trigram for near-dedup title search
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON pubmed_anesthesia_articles USING GIN(title gin_trgm_ops);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trig_updated_at ON pubmed_anesthesia_articles;
CREATE TRIGGER trig_updated_at BEFORE UPDATE ON pubmed_anesthesia_articles FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- VECTOR INDEXES - HNSW (Primary for production) + IVFFlat (fallback)
-- Production tuning notes:
-- HNSW: m=16 default good for most, higher m=24-32 for higher recall at memory cost
--       ef_construction=200-400 for high quality (64 default is too low for production >100k)
--       ef_search at query time: SET hnsw.ef_search = 100 (default 40 too low for high recall)
-- IVFFlat: lists = sqrt(n) ~ 100 for 10k, 316 for 100k, 1000 for 1M - requires training after data load
--          probes at query: SET ivfflat.probes = 10 (default 1 too low)
-- ============================================================================

-- IMPORTANT: Increase maintenance_work_mem before creating HNSW index on large tables
-- Example: SET maintenance_work_mem = '2GB';

-- PRIMARY: HNSW index for cosine similarity (production, read-heavy RAG workloads up to ~10M)
-- Best for: sub-50ms queries, high recall, read-heavy
DROP INDEX IF EXISTS idx_articles_embedding_hnsw_cosine;
CREATE INDEX idx_articles_embedding_hnsw_cosine ON pubmed_anesthesia_articles
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- SECONDARY: HNSW for L2 if needed for some models (keep for flexibility)
-- DROP INDEX IF EXISTS idx_articles_embedding_hnsw_l2;
-- CREATE INDEX idx_articles_embedding_hnsw_l2 ON pubmed_anesthesia_articles USING hnsw (embedding vector_l2_ops) WITH (m=16, ef_construction=200);

-- FALLBACK: IVFFlat for write-heavy or memory-constrained, or compatibility fallback (pgvector <0.5.0)
-- Note: IVFFlat requires table to have data before building (needs training). Build after bulk load.
DROP INDEX IF EXISTS idx_articles_embedding_ivfflat_cosine;
-- Uncomment after loading >10k rows:
-- CREATE INDEX idx_articles_embedding_ivfflat_cosine ON pubmed_anesthesia_articles
-- USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- For partitioned search by year (if table grows >1M, consider partitioning)
-- CREATE INDEX idx_articles_embedding_hnsw_2024 ON pubmed_anesthesia_articles USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=200) WHERE pub_year >= 2020;

-- ============================================================================
-- PRODUCTION SEARCH QUERIES - Tuned examples
-- ============================================================================
-- Example 1: HNSW high-recall filtered search (recommended)
-- SET hnsw.ef_search = 100;  -- 100-200 for high recall production
-- SELECT pmid, title, journal_iso, pub_year, anesthesia_score,
--        1 - (embedding <=> $1::vector) AS similarity
-- FROM pubmed_anesthesia_articles
-- WHERE is_anesthesia = TRUE
--   AND has_anesthesia_mesh = TRUE  -- Fix FP: require major MeSH
--   AND pub_year >= 2020
--   AND anesthesia_types_text && ARRAY['general','regional']  -- Overlap filter
-- ORDER BY embedding <=> $1::vector
-- LIMIT 20;

-- Example 2: IVFFlat search (if using IVFFlat)
-- SET ivfflat.probes = 10; -- probes 10-50 for recall
-- SELECT ... same as above ORDER BY embedding <=> $1 LIMIT 20;

-- Example 3: Hybrid - FTS + Vector (for anesthesia RAG)
-- WITH semantic AS (
--   SELECT pmid, 1 - (embedding <=> $1::vector) AS sim FROM pubmed_anesthesia_articles
--   WHERE is_anesthesia AND embedding IS NOT NULL ORDER BY embedding <=> $1 LIMIT 100
-- ), keyword AS (
--   SELECT pmid, ts_rank(search_vector, plainto_tsquery('english',$2)) AS rank FROM pubmed_anesthesia_articles WHERE search_vector @@ plainto_tsquery('english',$2) LIMIT 100
-- )
-- SELECT a.pmid, a.title, (0.7*s.sim + 0.3*k.rank) AS hybrid_score FROM semantic s JOIN keyword k USING(pmid) JOIN pubmed_anesthesia_articles a USING(pmid) ORDER BY hybrid_score DESC LIMIT 20;

-- ============================================================================
-- MATERIALIZED VIEW for fast stats
-- ============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_anesthesia_stats AS
SELECT
    COUNT(*) AS total_articles,
    COUNT(*) FILTER (WHERE is_anesthesia) AS anesthesia_positive,
    COUNT(*) FILTER (WHERE has_anesthesia_mesh) AS has_mesh,
    COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
    COUNT(DISTINCT journal_iso) AS journal_count,
    MIN(pub_year) AS min_year,
    MAX(pub_year) AS max_year,
    AVG(anesthesia_score) FILTER (WHERE is_anesthesia) AS avg_score,
    COUNT(*) FILTER (WHERE date_parse_method LIKE 'medline%') AS medline_date_fallback_used
FROM pubmed_anesthesia_articles;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_stats ON mv_anesthesia_stats(total_articles);

-- ============================================================================
-- GRANT (adjust for your role)
-- ============================================================================
-- GRANT SELECT ON pubmed_anesthesia_articles TO app_reader;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_writer;
