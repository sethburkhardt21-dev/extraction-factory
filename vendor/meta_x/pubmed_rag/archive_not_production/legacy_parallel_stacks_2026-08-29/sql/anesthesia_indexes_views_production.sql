-- ============================================================================
-- Agent B3: Indexes & Views Architect - Production DDL
-- Max Anesthesia PubMed Extraction - 280k-380k records target
-- Focus: GIN on mesh_terms, full-text on title/abstract, subdomain aggregations
-- DB: PostgreSQL 15+ (primary), BigQuery notes inline
-- Author: Swarm B - Database DDL Swarm
-- ============================================================================

-- --------------------------------------------------------------------------
-- 0. Extensions (idempotent)
-- --------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- trigram fuzzy ILIKE
CREATE EXTENSION IF NOT EXISTS btree_gin;     -- composite GIN+BTree
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector for embeddings (optional, ignore if absent)
-- Note: If vector extension unavailable, embedding indexes skip gracefully

-- Performance tuning expectations:
-- shared_buffers >= 4GB, work_mem 64MB for GIN fastupdate off builds
-- maintenance_work_mem 1GB for CONCURRENTLY builds

-- --------------------------------------------------------------------------
-- 1. Base table (canonical) - produces executable context
-- Assumes JSON schema anesthesia_pubmed_schema.json mapped to relational
-- If table already exists via migration, this is skipped via IF NOT EXISTS
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS anesthesia_pubmed_records (
    pmid TEXT PRIMARY KEY,  -- e.g. "39769238"
    doi TEXT,               -- raw, normalization via index
    doi_normalized TEXT GENERATED ALWAYS AS (
        -- Handles audit issue: DOI normalization missing - lower, trim, remove URL prefix
        lower(
          trim(BOTH '/' FROM 
            regexp_replace(
              regexp_replace(coalesce(doi,''), '^\s*https?://(dx\.)?doi\.org/', '', 'i'),
              '^\s*doi:\s*', '', 'i'
            )
          )
        )
    ) STORED,
    pmcid TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    abstract_word_count INT,

    -- Structured abstract JSON
    abstract_structured JSONB,

    -- Journal
    journal_title TEXT,
    journal_iso TEXT,
    journal_issn TEXT,
    journal_volume TEXT,
    journal_issue TEXT,
    journal_pages TEXT,
    journal_if DOUBLE PRECISION,
    publisher TEXT,

    -- Dates - handles MedlineDate fallback audit issue
    publication_year INT NOT NULL,
    publication_month INT,
    publication_day INT,
    pub_type_date TEXT, -- epub, ppublish
    pdat_raw TEXT,       -- original PDAT or MedlineDate fallback string like "2023 Spring"
    publication_date DATE GENERATED ALWAYS AS (
        -- robust to MedlineDate: tries make_date, else NULL
        CASE WHEN publication_year IS NOT NULL AND publication_month BETWEEN 1 AND 12 AND publication_day BETWEEN 1 AND 31
             THEN make_date(publication_year, COALESCE(publication_month,1), COALESCE(publication_day,1))
             WHEN publication_year IS NOT NULL THEN make_date(publication_year, COALESCE(publication_month,1), 1)
             ELSE NULL
        END
    ) STORED,

    -- Full text search vector - WEIGHTED
    -- Title weight A, abstract weight B, mesh major topics weight C via separate column? Here combined
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(title,'')), 'A') ||
        setweight(to_tsvector('english', COALESCE(abstract,'')), 'B') ||
        -- Keywords/journal as C
        setweight(to_tsvector('english', COALESCE(journal_title,'') || ' ' || COALESCE(publisher,'')), 'C')
    ) STORED,

    -- MeSH - array + JSONB
    mesh_terms JSONB, -- array of objects [{descriptor_name, descriptor_ui, qualifiers[], major_topic}]
    mesh_descriptor_names TEXT[] GENERATED ALWAYS AS (
        -- Extract descriptor_name from JSONB for GIN array indexing
        -- Handles NULL
        CASE WHEN mesh_terms IS NULL THEN '{}'::TEXT[]
             ELSE ARRAY(SELECT jsonb_path_query_first(m, '$.descriptor_name') #>> '{}' FROM jsonb_array_elements(mesh_terms) AS t(m))
        END
    ) STORED,
    mesh_descriptor_uis TEXT[] GENERATED ALWAYS AS (
        CASE WHEN mesh_terms IS NULL THEN '{}'::TEXT[]
             ELSE ARRAY(SELECT jsonb_path_query_first(m, '$.descriptor_ui') #>> '{}' FROM jsonb_array_elements(mesh_terms) AS t(m))
        END
    ) STORED,
    mesh_major_names TEXT[] GENERATED ALWAYS AS (
        CASE WHEN mesh_terms IS NULL THEN '{}'::TEXT[]
             ELSE ARRAY(SELECT jsonb_path_query_first(m, '$.descriptor_name') #>> '{}' FROM jsonb_array_elements(mesh_terms) AS t(m) WHERE (m->>'major_topic')::boolean = true)
        END
    ) STORED,

    -- Keywords
    keywords TEXT[],

    -- Publication types: e.g. RCT, Systematic Review, Guideline
    publication_types TEXT[],

    -- Chemicals
    chemicals JSONB,
    chemical_names TEXT[] GENERATED ALWAYS AS (
        CASE WHEN chemicals IS NULL THEN '{}'::TEXT[]
             ELSE ARRAY(SELECT jsonb_path_query_first(c, '$.name') #>> '{}' FROM jsonb_array_elements(chemicals) AS t(c))
        END
    ) STORED,

    -- Anesthesia specific - arrays for GIN
    anesthesia_subdomains TEXT[] NOT NULL DEFAULT '{}', -- 16 enum values
    study_design_type TEXT, -- RCT, Systematic Review, etc
    is_landmark BOOLEAN DEFAULT FALSE,
    n_patients INT,
    n_studies_included INT,
    multicenter BOOLEAN,
    blinding TEXT,
    registration_id TEXT, -- NCT, PROSPERO

    drugs TEXT[],        -- Dexmedetomidine, Propofol...
    techniques TEXT[],   -- General, Spinal, etc
    outcomes TEXT[],     -- PONV, awareness, delirium
    population TEXT,     -- adult, pediatric...
    asa_class TEXT,

    authors JSONB,
    n_authors INT,
    first_author_last TEXT,
    first_author_affiliation TEXT,

    citation_count_openalex INT,
    citation_count_scholar INT,
    is_top_100_pediatric BOOLEAN DEFAULT FALSE,

    -- Extraction metadata
    extraction_query TEXT,
    agent_id INT, -- 1..16
    retrieval_date TIMESTAMPTZ,
    dedup_status TEXT, -- unique, duplicate_type_I, etc
    duplicate_of_pmid TEXT,

    -- Embeddings (pgvector) - optional 768d for title+abstract
    embedding vector(768),

    -- Audit
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE anesthesia_pubmed_records IS 'Max anesthesia PubMed corpus 280k-380k, 16-agent swarm extraction, full metadata schema v1';

-- --------------------------------------------------------------------------
-- 2. CORE INDEXES - Production Conforming
-- Use CONCURRENTLY in live migrations (commented). Fresh DB: plain CREATE INDEX.
-- All indexes IF NOT EXISTS for idempotency (PG 9.5+)
-- --------------------------------------------------------------------------

-- 2.1 DOI normalization - handles audit "DOI normalization missing"
-- Unique partial ensures dedup can rely on normalized DOI
CREATE UNIQUE INDEX IF NOT EXISTS idx_anesth_doi_normalized_unique
    ON anesthesia_pubmed_records (doi_normalized)
    WHERE doi_normalized IS NOT NULL AND doi_normalized <> '';
COMMENT ON INDEX idx_anesth_doi_normalized_unique IS 'Dedup Type-I via normalized DOI lowercase exact match audit fix';

-- Expression trigram for DOI URL variants search
CREATE INDEX IF NOT EXISTS idx_anesth_doi_trgm
    ON anesthesia_pubmed_records USING gin (doi_normalized gin_trgm_ops);

-- 2.2 PMID cluster (already PK) + brin for append-only year-ordered scans
CREATE INDEX IF NOT EXISTS idx_anesth_pub_year_brin
    ON anesthesia_pubmed_records USING brin (publication_year) WITH (pages_per_range=128);

-- B-Tree year desc for recent trends
CREATE INDEX IF NOT EXISTS idx_anesth_pub_year_desc
    ON anesthesia_pubmed_records (publication_year DESC, publication_month DESC);

-- 2.3 GIN on mesh_terms JSONB - core requirement
-- jsonb_path_ops for containment @> which is smaller & faster than jsonb_ops when querying existence
CREATE INDEX IF NOT EXISTS idx_anesth_mesh_terms_jsonb_path
    ON anesthesia_pubmed_records USING gin (mesh_terms jsonb_path_ops)
    WHERE mesh_terms IS NOT NULL;

-- GIN ops default for full JSONB query versatility
CREATE INDEX IF NOT EXISTS idx_anesth_mesh_terms_jsonb_ops
    ON anesthesia_pubmed_records USING gin (mesh_terms)
    WHERE mesh_terms IS NOT NULL;

-- GIN on extracted descriptor names array - handles exact array overlap, not substring FP
-- Audit fix: classification via substring caused FP - use array containment @> not LIKE
CREATE INDEX IF NOT EXISTS idx_anesth_mesh_names_gin
    ON anesthesia_pubmed_records USING gin (mesh_descriptor_names);
CREATE INDEX IF NOT EXISTS idx_anesth_mesh_uis_gin
    ON anesthesia_pubmed_records USING gin (mesh_descriptor_uis);
CREATE INDEX IF NOT EXISTS idx_anesth_mesh_major_gin
    ON anesthesia_pubmed_records USING gin (mesh_major_names);

-- Trigram for fuzzy MeSH search
CREATE INDEX IF NOT EXISTS idx_anesth_mesh_names_trgm
    ON anesthesia_pubmed_records USING gin (array_to_string(mesh_descriptor_names,'|') gin_trgm_ops);

-- 2.4 Full-text search on title abstract - core requirement
CREATE INDEX IF NOT EXISTS idx_anesth_search_vector_gin
    ON anesthesia_pubmed_records USING gin (search_vector);
COMMENT ON INDEX idx_anesth_search_vector_gin IS 'Weighted A=title, B=abstract, C=journal - uses English stem';

-- Additional tsvector expression fallback if generated column delayed
CREATE INDEX IF NOT EXISTS idx_anesth_title_abstract_tsv_expr
    ON anesthesia_pubmed_records USING gin (to_tsvector('english', COALESCE(title,'') || ' ' || COALESCE(abstract,'')));

-- Trigram indexes for fuzzy title/abstract ILIKE '%awareness%' etc (before tsvector)
CREATE INDEX IF NOT EXISTS idx_anesth_title_trgm
    ON anesthesia_pubmed_records USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_anesth_abstract_trgm
    ON anesthesia_pubmed_records USING gin (abstract gin_trgm_ops);

-- 2.5 Anesthesia subdomains - GIN array core for aggregation queries
CREATE INDEX IF NOT EXISTS idx_anesth_subdomains_gin
    ON anesthesia_pubmed_records USING gin (anesthesia_subdomains);
COMMENT ON INDEX idx_anesth_subdomains_gin IS '16-agent swarm subdomain tags - use @> ARRAY[?], && operator, or unnest for aggregations';

-- Composite with year for trending queries
CREATE INDEX IF NOT EXISTS idx_anesth_subdomains_year
    ON anesthesia_pubmed_records USING gin (anesthesia_subdomains) INCLUDE (publication_year);
-- Note: INCLUDE available PG11+ - BTree alternative below for <11
CREATE INDEX IF NOT EXISTS idx_anesth_subdomain_year_btree_trgmhelper
    ON anesthesia_pubmed_records (publication_year DESC) WHERE anesthesia_subdomains IS NOT NULL;

-- Partial indexes per high-value subdomain (saves active query memory)
-- Per best practice: partial indexes for hot subsets
CREATE INDEX IF NOT EXISTS idx_anesth_sub_pediatric
    ON anesthesia_pubmed_records (publication_year DESC, citation_count_openalex DESC)
    WHERE anesthesia_subdomains @> ARRAY['Pediatric Anesthesia'];
CREATE INDEX IF NOT EXISTS idx_anesth_sub_regional
    ON anesthesia_pubmed_records (publication_year DESC)
    WHERE anesthesia_subdomains @> ARRAY['Regional Anesthesia - Spinal Epidural'];
CREATE INDEX IF NOT EXISTS idx_anesth_sub_pnb
    ON anesthesia_pubmed_records (publication_year DESC)
    WHERE anesthesia_subdomains @> ARRAY['Peripheral Nerve Blocks'];
CREATE INDEX IF NOT EXISTS idx_anesth_sub_airway
    ON anesthesia_pubmed_records (publication_year DESC)
    WHERE anesthesia_subdomains @> ARRAY['Airway Management'];

-- 2.6 Study design, drugs, techniques, outcomes - GIN arrays
CREATE INDEX IF NOT EXISTS idx_anesth_pubtypes_gin
    ON anesthesia_pubmed_records USING gin (publication_types);
CREATE INDEX IF NOT EXISTS idx_anesth_drugs_gin
    ON anesthesia_pubmed_records USING gin (drugs);
CREATE INDEX IF NOT EXISTS idx_anesth_techniques_gin
    ON anesthesia_pubmed_records USING gin (techniques);
CREATE INDEX IF NOT EXISTS idx_anesth_outcomes_gin
    ON anesthesia_pubmed_records USING gin (outcomes);
CREATE INDEX IF NOT EXISTS idx_anesth_chemical_names_gin
    ON anesthesia_pubmed_records USING gin (chemical_names);
CREATE INDEX IF NOT EXISTS idx_anesth_keywords_gin
    ON anesthesia_pubmed_records USING gin (keywords);

-- Composite GIN for drug+outcome typical anesthesia query
-- Example: drugs @> {Propofol} AND outcomes @> {PONV}
-- Need btree_gin extension for mixed
CREATE INDEX IF NOT EXISTS idx_anesth_drugs_outcomes_bgin
    ON anesthesia_pubmed_records USING gin (drugs, outcomes);

-- 2.7 Journal & citation metrics
CREATE INDEX IF NOT EXISTS idx_anesth_journal_title_btree
    ON anesthesia_pubmed_records (journal_title);
CREATE INDEX IF NOT EXISTS idx_anesth_journal_if_desc
    ON anesthesia_pubmed_records (journal_if DESC, publication_year DESC);
CREATE INDEX IF NOT EXISTS idx_anesth_citation_desc
    ON anesthesia_pubmed_records (citation_count_openalex DESC) WHERE citation_count_openalex IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_anesth_impact_citation_composite
    ON anesthesia_pubmed_records (journal_title, citation_count_openalex DESC, publication_year DESC);

-- 2.8 Study design categorical
CREATE INDEX IF NOT EXISTS idx_anesth_study_type
    ON anesthesia_pubmed_records (study_design_type, publication_year DESC);
CREATE INDEX IF NOT EXISTS idx_anesth_landmark_partial
    ON anesthesia_pubmed_records (publication_year DESC, citation_count_openalex DESC)
    WHERE is_landmark = true;
CREATE INDEX IF NOT EXISTS idx_anesth_multicenter
    ON anesthesia_pubmed_records (publication_year DESC) WHERE multicenter = true;
CREATE INDEX IF NOT EXISTS idx_anesth_population
    ON anesthesia_pubmed_records (population) WHERE population IS NOT NULL;

-- 2.9 Agent & extraction provenance
CREATE INDEX IF NOT EXISTS idx_anesth_agent_id
    ON anesthesia_pubmed_records (agent_id, publication_year DESC);

-- 2.10 Embeddings (pgvector) - cosine similarity for semantic search over title+abstract
-- Only if extension present and embeddings populated
-- Choose IVFFLAT for 300k scale, HNSW for <1M with higher recall if PG16+
DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_anesth_embedding_cosine ON anesthesia_pubmed_records USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)';
        EXECUTE 'COMMENT ON INDEX idx_anesth_embedding_cosine IS ''Semantic search for anesthesia queries - e.g., anesthesia awareness mechanisms''';
    END IF;
END$$;

-- 2.11 BigQuery equivalent DDL (commented)
-- For BigQuery, replace GIN with SEARCH indexes:
-- CREATE SEARCH INDEX idx_bq_mesh_names ON anesthesia_dataset.anesthesia_pubmed_records (mesh_descriptor_names);
-- CREATE SEARCH INDEX idx_bq_search ON anesthesia_dataset.anesthesia_pubmed_records (ALL COLUMNS); -- or title, abstract
-- Partition by publication_year CLUSTER BY anesthesia_subdomains, study_design_type, journal_title

-- --------------------------------------------------------------------------
-- 3. Validation queries for index usage
-- --------------------------------------------------------------------------
-- EXPLAIN (ANALYZE, BUFFERS) SELECT pmid, title FROM anesthesia_pubmed_records
-- WHERE search_vector @@ to_tsquery('english', 'awareness & (general | anesthesia)') ORDER BY ts_rank(search_vector, to_tsquery('english','awareness')) DESC LIMIT 20;
--
-- SELECT * FROM anesthesia_pubmed_records WHERE mesh_descriptor_names @> ARRAY['Anesthesia, General'];
-- SELECT * FROM anesthesia_pubmed_records WHERE anesthesia_subdomains @> ARRAY['Pediatric Anesthesia'];
-- SELECT * FROM anesthesia_pubmed_records WHERE drugs @> ARRAY['Propofol'] AND outcomes @> ARRAY['Postoperative Nausea and Vomiting'];

-- --------------------------------------------------------------------------
-- End indexes
-- --------------------------------------------------------------------------
