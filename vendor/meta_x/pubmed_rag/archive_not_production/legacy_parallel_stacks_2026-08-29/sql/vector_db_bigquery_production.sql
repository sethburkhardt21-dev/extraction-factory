-- ============================================================================
-- BIGQUERY VECTOR INDEX DDL - PubMed Anesthesia Extraction
-- Production DDL for max anesthesia PubMed extraction
-- Supports IVF and TREE_AH (ScaNN) index types
-- ============================================================================

-- ============================================================================
-- DATASET SETUP (run once)
-- ============================================================================
-- CREATE SCHEMA IF NOT EXISTS `your-project.anesthesia_prod`
-- OPTIONS (location="US", description="Anesthesia PubMed embeddings");

-- ============================================================================
-- TABLE: pubmed anesthesia articles with ARRAY<FLOAT64> embedding
-- BigQuery requirement: embedding column must be ARRAY<FLOAT64>, all same dim, non-NULL elements
-- For 5000+ rows required to create VECTOR INDEX
-- ============================================================================
CREATE TABLE IF NOT EXISTS `your-project.anesthesia_prod.pubmed_anesthesia_articles`
(
    -- Identifiers - dedup keys
    pmid INT64 NOT NULL OPTIONS(description="PubMed ID primary key"),
    pmcid STRING,
    doi STRING,
    content_hash STRING NOT NULL OPTIONS(description="sha256(title+abstract) for dedup"),
    title_hash STRING NOT NULL,
    doi_normalized STRING,

    -- Bibliographic
    title STRING NOT NULL,
    title_clean STRING,
    abstract STRING,
    abstract_word_count INT64,
    abstract_structured JSON, -- JSON string of labeled abstract sections

    -- Authors JSON
    authors JSON, -- array of author objects
    collective_author STRING,
    first_author_last STRING,
    last_author_last STRING,
    author_count INT64,

    -- Journal
    journal_title STRING,
    journal_iso STRING,
    issn STRING,
    volume STRING,
    issue STRING,
    pages STRING,

    -- Dates: Fix MedlineDate fallback
    pub_date DATE,
    pub_year INT64 NOT NULL, -- Mandatory with fallback parsing
    pub_month INT64,
    pub_day INT64,
    medline_date_raw STRING OPTIONS(description="Original MedlineDate e.g. 2021-2022"),
    article_date DATE,
    date_parse_method STRING NOT NULL OPTIONS(description="Enum: pubdate_year_month, medline_date_full, medline_date_range_start, etc"),
    date_parse_note STRING,

    -- MeSH
    mesh_terms JSON, -- full mesh details
    mesh_major_terms ARRAY<STRING>,
    mesh_minor_terms ARRAY<STRING>,
    mesh_tree_numbers ARRAY<STRING> OPTIONS(description="E03.155.* for anesthesia branch"),
    mesh_qualifiers ARRAY<STRING>,

    -- Indexing
    keywords ARRAY<STRING>,
    publication_types ARRAY<STRING>,
    chemical_list JSON,
    grant_list JSON,

    -- Anesthesia classification - Fix FP
    has_anesthesia_mesh BOOL NOT NULL OPTIONS(description="Whether E03.155.* tree present"),
    is_anesthesia BOOL NOT NULL,
    anesthesia_score FLOAT64,
    anesthesia_types ARRAY<STRING>, -- general, regional, spinal, etc
    procedure_context ARRAY<STRING>,
    classification_method STRING,
    classification_version STRING,
    false_positive_flags JSON, -- risk flags
    classification_reasoning STRING,

    -- Embedding - MUST be ARRAY<FLOAT64> for BigQuery VECTOR INDEX
    embedding ARRAY<FLOAT64> NOT NULL OPTIONS(description="1536-dim OpenAI embedding, all non-null, same length"),
    embedding_model STRING NOT NULL DEFAULT "text-embedding-3-small",
    embedding_dim INT64 NOT NULL DEFAULT 1536,
    embedding_version STRING,

    -- Audit
    fetch_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    esearch_query STRING,
    fetch_batch_id STRING,
    xml_raw_hash STRING,
    extraction_version STRING DEFAULT "v2.1-fixed",
    is_retracted BOOL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),

    -- For vector index STORING clause (pre-filter + hybrid search)
    -- These columns stored in index for filtered VECTOR_SEARCH without table lookup
    search_text STRING OPTIONS(description="Concatenated title+abstract for lexical search")
)
PARTITION BY RANGE_BUCKET(pub_year, GENERATE_ARRAY(1950, 2030, 5))
CLUSTER BY is_anesthesia, has_anesthesia_mesh, journal_iso
OPTIONS(
    description="PubMed anesthesia articles with embeddings - production table for VECTOR_SEARCH",
    partition_expiration_days=7300,
    require_partition_filter=false
);

-- ============================================================================
-- PRIMARY KEY enforcement via uniqueness check (BigQuery has no PK constraint)
-- Create lookup view for dedup validation
-- ============================================================================
CREATE OR REPLACE VIEW `your-project.anesthesia_prod.v_dedup_check` AS
SELECT content_hash, COUNT(*) AS cnt, ARRAY_AGG(pmid) AS pmids, ARRAY_AGG(doi) AS dois
FROM `your-project.anesthesia_prod.pubmed_anesthesia_articles`
GROUP BY content_hash HAVING cnt > 1;

-- ============================================================================
-- VECTOR INDEXES - Production
-- BigQuery supports IVF and TREE_AH. IVF preferred for small batch, TREE_AH for large batch (100s+ queries)
-- Requires at least 5000 rows to create
-- ============================================================================

-- PRIMARY: IVF index with COSINE distance - optimal for anesthesia RAG queries
-- Best practices:
-- - distance_type COSINE for text embeddings
-- - num_lists: default auto, but tune for granularity: 500-2500 for 100k-1M rows
-- - STORING stored columns for pre-filter: is_anesthesia, has_anesthesia_mesh, pub_year, etc stored in index
-- - lexical_search_columns for hybrid search (requires storing columns)
CREATE OR REPLACE VECTOR INDEX `idx_embedding_ivf_cosine`
ON `your-project.anesthesia_prod.pubmed_anesthesia_articles`(embedding)
STORING (pmid, title, is_anesthesia, has_anesthesia_mesh, pub_year, journal_iso, anesthesia_types, mesh_major_terms, search_text)
OPTIONS(
    index_type = 'IVF',
    distance_type = 'COSINE',
    ivf_options = '{"num_lists": 1000}' -- 100 for 10k, 316 for 100k, 1000 for 500k-1M. Controls tuning granularity vs indexing cost
);

-- ALTERNATIVE: IVF with hybrid search (lexical + vector)
CREATE OR REPLACE VECTOR INDEX `idx_embedding_ivf_hybrid`
ON `your-project.anesthesia_prod.pubmed_anesthesia_articles`(embedding)
STORING (pmid, title, is_anesthesia, pub_year, anesthesia_types, search_text, mesh_major_terms)
OPTIONS(
    index_type = 'IVF',
    distance_type = 'COSINE',
    ivf_options = '{"num_lists": 1000}',
    lexical_search_columns = '["search_text", "title"]' -- enables hybrid search keyword + vector
);

-- LARGE BATCH: TreeAH index (ScaNN) - for 200M rows or fewer, batch queries with 100s+ vectors
-- 10-100x faster than IVF for large batch due to product quantization + asymmetric hashing
-- Use when: frequent large batch embedding searches
CREATE OR REPLACE VECTOR INDEX `idx_embedding_treeah_cosine`
ON `your-project.anesthesia_prod.pubmed_anesthesia_articles`(embedding)
STORING (pmid, title, is_anesthesia, has_anesthesia_mesh, pub_year)
OPTIONS(
    index_type = 'TREE_AH',
    distance_type = 'COSINE',
    tree_ah_options = '{"leaf_node_embedding_count": 1000, "normalization_type": "L2"}'
    -- leaf_node_embedding_count >=500, default 1000. Lower = more lists, finer granularity
    -- L2 normalization can improve recall for cosine depending on embedding model
);

-- ============================================================================
-- VECTOR_SEARCH QUERIES - Production examples
-- ============================================================================

-- Example 1: Basic IVF VECTOR_SEARCH (filtered, high-recall)
-- Uses index idx_embedding_ivf_cosine
-- DECLARE query_embedding ARRAY<FLOAT64> DEFAULT (SELECT embedding FROM ... WHERE pmid=...);

-- SELECT 
--   base.pmid,
--   base.title,
--   base.journal_iso,
--   base.pub_year,
--   base.anesthesia_score,
--   distance
-- FROM VECTOR_SEARCH(
--   TABLE `your-project.anesthesia_prod.pubmed_anesthesia_articles`,
--   'embedding',
--   (SELECT [query_embedding]), -- or TABLE with many query embeddings
--   top_k => 20,
--   distance_type => 'COSINE',
--   fraction_lists_to_search => 0.1, -- 10% of lists => higher recall. Default 0.01. For high recall use 0.05-0.2
--   options => '{"use_brute_force": false}' -- force index use
-- )
-- WHERE is_anesthesia = TRUE
--   AND has_anesthesia_mesh = TRUE -- Fix FP: require major mesh
--   AND pub_year >= 2020;

-- Example 2: Hybrid search (lexical + vector) - improves anesthesia retrieval
-- SELECT 
--   base.pmid,
--   base.title,
--   distance
-- FROM VECTOR_SEARCH(
--   TABLE `your-project.anesthesia_prod.pubmed_anesthesia_articles`,
--   'embedding',
--   (SELECT [query_embedding]),
--   top_k => 100,
--   distance_type => 'COSINE',
--   options => '{"enable_hybrid_search": true, "hybrid_search_weights": [0.7, 0.3]}' -- 70% vector, 30% lexical
-- );

-- Example 3: TreeAH large batch search
-- CREATE TEMP TABLE query_embeddings AS (
--   SELECT embedding FROM `your-project.anesthesia_prod.query_batch` -- 100s of queries
-- );
-- SELECT query.embedding AS query_embedding, base.pmid, base.title
-- FROM VECTOR_SEARCH(
--   TABLE `your-project.anesthesia_prod.pubmed_anesthesia_articles`,
--   'embedding',
--   TABLE query_embeddings,
--   top_k => 20,
--   distance_type => 'COSINE',
--   options => '{"fraction_leaves_to_search": 0.1}' -- TreeAH equivalent of fraction_lists_to_search
-- );

-- Example 4: Aggregation for monitoring
-- SELECT has_anesthesia_mesh, COUNT(*) AS cnt, AVG(anesthesia_score) AS avg_score
-- FROM `your-project.anesthesia_prod.pubmed_anesthesia_articles`
-- GROUP BY has_anesthesia_mesh;

-- ============================================================================
-- MONITORING: VECTOR INDEX status
-- ============================================================================
-- Check index creation status:
-- SELECT * FROM `your-project.anesthesia_prod.INFORMATION_SCHEMA.VECTOR_INDEXES`
-- WHERE table_name = 'pubmed_anesthesia_articles';

-- Check indexes:
-- SELECT index_name, index_status, coverage_percentage FROM `your-project.anesthesia_prod.INFORMATION_SCHEMA.VECTOR_INDEXES`;

-- ============================================================================
-- AUTONOMOUS EMBEDDING GENERATION alternative (optional)
-- If you want BigQuery to auto-generate embeddings using AI.EMBED
-- ============================================================================
-- CREATE OR REPLACE TABLE `your-project.anesthesia_prod.pubmed_auto_embed`
-- (
--    pmid INT64 NOT NULL,
--    title STRING,
--    abstract STRING,
--    search_text STRING,
--    search_text_embedding STRUCT<result ARRAY<FLOAT64>, status STRING>
--      GENERATED ALWAYS AS (
--        AI.EMBED(search_text, connection_id=>'us.anesthesia_embed_conn', endpoint=>'text-embedding-005')
--      ) STORED OPTIONS (asynchronous = TRUE)
-- );
-- -- Then index auto embedding column
-- CREATE VECTOR INDEX `idx_auto_embed` ON `your-project.anesthesia_prod.pubmed_auto_embed` (search_text_embedding)
-- OPTIONS(index_type='IVF', distance_type='COSINE');

-- ============================================================================
-- DEDUP + CLASSIFICATION AUDIT tables (BigQuery version)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `your-project.anesthesia_prod.pubmed_fetch_audit`
(
    batch_id STRING NOT NULL,
    query STRING NOT NULL,
    esearch_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    total_count INT64,
    returned_count INT64,
    had_rate_limit BOOL DEFAULT FALSE,
    retry_count INT64 DEFAULT 0,
    http_status_codes ARRAY<INT64>,
    duration_ms INT64,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(created_at)
CLUSTER BY batch_id;

CREATE TABLE IF NOT EXISTS `your-project.anesthesia_prod.anesthesia_classification_audit`
(
    pmid INT64 NOT NULL,
    title STRING,
    has_major_anesthesia_mesh BOOL,
    keyword_match_score FLOAT64,
    false_positive_risk FLOAT64,
    final_label BOOL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY final_label, has_major_anesthesia_mesh;
