-- ============================================================================
-- Anesthesia PubMed Corpus - PostgreSQL Production DDL
-- Agent B4: ETL Loader Developer
-- Focus: JSONL -> Postgres with batching + upsert on pmid
-- Includes audit fixes: DOI normalization, MedlineDate fallback, safe classification
-- ============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector; -- pgvector for embeddings (optional)
-- CREATE EXTENSION IF NOT EXISTS postgis; -- if geo needed

-- --------------------------------------------------------------------
-- Main table: full metadata canonical storage
-- --------------------------------------------------------------------
DROP TABLE IF EXISTS anesthesia_pubmed CASCADE;

CREATE TABLE anesthesia_pubmed (
    -- Core identifiers - pmid is natural PK
    pmid TEXT PRIMARY KEY,                           -- keep TEXT per schema, but CHECK numeric
    pmid_int BIGINT GENERATED ALWAYS AS (pmid::BIGINT) STORED, -- for numeric sorting, nullable if non-numeric
    doi TEXT,                                        -- normalized lowercase
    doi_raw TEXT,
    pmcid TEXT,
    
    -- Content
    title TEXT NOT NULL,
    abstract TEXT,
    abstract_structured JSONB,                       -- {background, methods, results, conclusions, full_sections}
    
    -- Journal (normalized + JSONB for extras)
    journal_title TEXT,
    journal_iso_abbr TEXT,
    journal_issn TEXT,
    journal_volume TEXT,
    journal_issue TEXT,
    journal_pages TEXT,
    journal_impact_factor REAL,
    journal_publisher TEXT,
    journal_json JSONB,                              -- full journal object
    
    -- Publication date with MedlineDate fallback support
    pub_year INT,
    pub_month INT,
    pub_day INT,
    pub_type_date TEXT,
    pdat TEXT,                                       -- original string for audit
    publication_date_json JSONB,
    
    -- Multi-value arrays - kept as both native array + JSONB for query flexibility
    publication_types TEXT[],                        -- RCT, SR, MA, etc
    keywords TEXT[],
    anesthesia_subdomains TEXT[],                    -- 16 domains
    study_type TEXT,                                 -- from study_design.type
    is_landmark BOOLEAN DEFAULT FALSE,
    n_patients INT,
    n_studies_included INT,
    multicenter BOOLEAN,
    blinding TEXT,
    registration_id TEXT,
    
    -- Anesthesia specific (audit-fixed classification)
    drugs TEXT[],
    techniques TEXT[],
    outcomes TEXT[],
    population TEXT,
    asa_class TEXT,
    anesthesia_specific_json JSONB,
    
    -- Citation
    citation_count_openalex INT,
    citation_count_semantic_scholar INT,
    is_top_100_pediatric BOOLEAN DEFAULT FALSE,
    
    -- Complex nested -> JSONB
    authors JSONB,                                   -- array of author objects
    mesh_terms JSONB,                                -- array of mesh objects
    chemicals JSONB,
    
    -- Extraction metadata
    query_used TEXT,
    agent_id INT CHECK (agent_id BETWEEN 1 AND 16),
    retrieval_date TIMESTAMPTZ,
    dedup_status TEXT CHECK (dedup_status IN ('unique','duplicate_type_I','duplicate_type_II','merged')),
    duplicate_of_pmid TEXT,
    extraction_metadata_json JSONB,
    
    -- ETL lineage
    etl_loaded_at TIMESTAMPTZ DEFAULT NOW(),
    etl_file_source TEXT,
    etl_batch_id TEXT,
    doi_normalized BOOLEAN DEFAULT FALSE,
    
    -- Embedding support (PubMedBERT 768-dim)
    title_abstract_embedding vector(768),            -- requires pgvector
    embedding_model TEXT,
    embedding_generated_at TIMESTAMPTZ,
    
    CONSTRAINT pmid_format CHECK (pmid ~ '^[0-9]+$'),
    CONSTRAINT doi_format CHECK (doi IS NULL OR doi ~ '^10\.[0-9]{4,}/.+')
);

-- Indexes for query patterns (from blueprint: 280k-380k records max)
CREATE INDEX idx_anesthesia_year ON anesthesia_pubmed (pub_year DESC);
CREATE INDEX idx_anesthesia_agent ON anesthesia_pubmed (agent_id);
CREATE INDEX idx_anesthesia_subdomains_gin ON anesthesia_pubmed USING GIN (anesthesia_subdomains);
CREATE INDEX idx_anesthesia_drugs_gin ON anesthesia_pubmed USING GIN (drugs);
CREATE INDEX idx_anesthesia_pubtypes_gin ON anesthesia_pubmed USING GIN (publication_types);
CREATE INDEX idx_anesthesia_mesh_gin ON anesthesia_pubmed USING GIN (mesh_terms);
CREATE INDEX idx_anesthesia_authors_gin ON anesthesia_pubmed USING GIN (authors);
CREATE INDEX idx_anesthesia_journal_title ON anesthesia_pubmed (journal_title);
CREATE INDEX idx_anesthesia_doi ON anesthesia_pubmed (doi) WHERE doi IS NOT NULL;
CREATE INDEX idx_anesthesia_study_type ON anesthesia_pubmed (study_type);
CREATE INDEX idx_anesthesia_dedup ON anesthesia_pubmed (dedup_status);
CREATE INDEX idx_anesthesia_retrieval_date ON anesthesia_pubmed (retrieval_date DESC);
-- Full-text search
CREATE INDEX idx_anesthesia_title_trgm ON anesthesia_pubmed USING GIN (title gin_trgm_ops);
CREATE INDEX idx_anesthesia_abstract_trgm ON anesthesia_pubmed USING GIN (abstract gin_trgm_ops);
-- Vector index for semantic search (ivfflat needs ANALYZE)
-- CREATE INDEX idx_anesthesia_embedding ON anesthesia_pubmed USING ivfflat (title_abstract_embedding vector_cosine_ops) WITH (lists = 100);

-- --------------------------------------------------------------------
-- Normalized side tables for analytics (optional star schema)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS anesthesia_authors_normalized (
    pmid TEXT REFERENCES anesthesia_pubmed(pmid) ON DELETE CASCADE,
    author_order INT,
    last_name TEXT,
    fore_name TEXT,
    initials TEXT,
    affiliation TEXT,
    orcid TEXT,
    PRIMARY KEY (pmid, author_order)
);
CREATE INDEX idx_auth_norm_lastname ON anesthesia_authors_normalized (last_name);

CREATE TABLE IF NOT EXISTS anesthesia_mesh_normalized (
    pmid TEXT REFERENCES anesthesia_pubmed(pmid) ON DELETE CASCADE,
    descriptor_name TEXT,
    descriptor_ui TEXT,
    qualifier TEXT,
    major_topic BOOLEAN,
    PRIMARY KEY (pmid, descriptor_ui, qualifier)
);
CREATE INDEX idx_mesh_desc ON anesthesia_mesh_normalized (descriptor_name);
CREATE INDEX idx_mesh_ui ON anesthesia_mesh_normalized (descriptor_ui);

-- --------------------------------------------------------------------
-- Dead letter queue for ETL rejects
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_rejections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmid TEXT,
    file_source TEXT,
    batch_id TEXT,
    error_message TEXT,
    raw_json JSONB,
    rejected_at TIMESTAMPTZ DEFAULT NOW()
);

-- --------------------------------------------------------------------
-- ETL audit table
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_audit (
    batch_id TEXT PRIMARY KEY,
    file_source TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    records_read INT,
    records_inserted INT,
    records_updated INT,
    records_rejected INT,
    status TEXT,
    notes JSONB
);

-- View for deduplicated unique corpus (for downstream)
CREATE OR REPLACE VIEW v_anesthesia_unique AS
SELECT * FROM anesthesia_pubmed
WHERE dedup_status = 'unique' OR dedup_status = 'merged';

-- Grant example (adjust role)
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO loader_role;