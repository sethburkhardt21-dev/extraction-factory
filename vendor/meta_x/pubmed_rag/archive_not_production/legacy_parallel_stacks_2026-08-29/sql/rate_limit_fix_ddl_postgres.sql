-- Agent B7: Rate Limit Fix - Production Postgres DDL
-- Max Anesthesia PubMed Extraction - Database DDL Swarm
-- Corrects inverted rate limits, adds WebEnv expiration tracking

-- ============================================================================
-- TABLE: pubmed_extraction_audit (rate limit compliance + WebEnv lifecycle)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pubmed_extraction_audit (
    id BIGSERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL CHECK (agent_id BETWEEN 1 AND 16),
    term_hash TEXT NOT NULL,
    term_preview TEXT NOT NULL,
    esearch_count INTEGER NOT NULL,
    webenv TEXT,
    query_key TEXT,
    
    -- Rate limiting - CORRECT per NCBI https://www.ncbi.nlm.nih.gov/books/NBK25497/
    -- BEFORE BUG: comment said "20 req/s with key, 10 without" and sleep was inverted 0.34 with key vs 0.5 without
    -- AFTER FIX: 3 req/s without key (0.34s gap), 10 req/s with key (0.11s gap)
    has_api_key BOOLEAN NOT NULL,
    configured_rate_limit INTEGER NOT NULL CHECK (configured_rate_limit IN (3, 10)),
    min_gap_seconds NUMERIC(4,3) NOT NULL CHECK (min_gap_seconds IN (0.34, 0.11)),
    observed_avg_rate NUMERIC(6,3),
    rate_limit_violations INTEGER DEFAULT 0,
    rate_limit_429_count INTEGER DEFAULT 0,
    
    -- WebEnv lifecycle - 8h absolute TTL, ~15min idle eviction
    -- Expired returns HTTP 200 with <ERROR>WebEnv not found</ERROR> - must parse body not status
    webenv_created_at TIMESTAMPTZ NOT NULL,
    webenv_last_used_at TIMESTAMPTZ NOT NULL,
    webenv_age_hours NUMERIC(6,2),
    webenv_expired_count INTEGER DEFAULT 0,
    webenv_refresh_count INTEGER DEFAULT 0,
    checkpoint_retstart INTEGER DEFAULT 0,
    
    -- Error tracking
    http_429_errors INTEGER DEFAULT 0,
    http_5xx_errors INTEGER DEFAULT 0,
    xml_error_count INTEGER DEFAULT 0,
    parse_errors INTEGER DEFAULT 0,
    total_retries INTEGER DEFAULT 0,
    
    -- Extraction
    retstart INTEGER NOT NULL,
    retmax INTEGER NOT NULL,
    records_fetched INTEGER NOT NULL,
    batch_success BOOLEAN NOT NULL,
    error_message TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_rate_violations ON pubmed_extraction_audit(rate_limit_violations) WHERE rate_limit_violations > 0;
CREATE INDEX IF NOT EXISTS idx_audit_webenv_expired ON pubmed_extraction_audit(webenv_expired_count) WHERE webenv_expired_count > 0;
CREATE INDEX IF NOT EXISTS idx_audit_agent_time ON pubmed_extraction_audit(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_api_key ON pubmed_extraction_audit(has_api_key);

-- View: compliance dashboard
CREATE OR REPLACE VIEW v_pubmed_rate_limit_compliance AS
SELECT 
    agent_id,
    has_api_key,
    configured_rate_limit,
    COUNT(*) as batches,
    SUM(rate_limit_429_count) as total_429s,
    SUM(webenv_expired_count) as total_webenv_expired,
    AVG(observed_avg_rate) as avg_observed_rate,
    MAX(webenv_age_hours) as max_webenv_age_hours,
    SUM(CASE WHEN batch_success THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*),0) as success_rate
FROM pubmed_extraction_audit
GROUP BY agent_id, has_api_key, configured_rate_limit;

-- Table: checkpoints for resume (survives WebEnv expiration)
CREATE TABLE IF NOT EXISTS pubmed_extraction_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL CHECK (agent_id BETWEEN 1 AND 16),
    term TEXT NOT NULL,
    term_hash TEXT NOT NULL UNIQUE,
    retstart INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL,
    webenv TEXT,
    query_key TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_agent ON pubmed_extraction_checkpoints(agent_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_hash ON pubmed_extraction_checkpoints(term_hash);

COMMENT ON TABLE pubmed_extraction_audit IS 'Agent B7 fix: correct 3/s no key 10/s with key (was inverted), WebEnv expiration handling via ERROR body parse, re-search resume';
COMMENT ON COLUMN pubmed_extraction_audit.configured_rate_limit IS 'NCBI official: 3 without key, 10 with key. Original buggy code had 20/10 comment and inverted sleep';
COMMENT ON COLUMN pubmed_extraction_audit.min_gap_seconds IS 'Correct: 0.34 for 3/s, 0.11 for 10/s (0.10 + safety). Original: 0.34 with key (wrong) 0.5 without (wrong)';

-- ============================================================================
-- BigQuery equivalent
-- ============================================================================
-- See file rate_limit_fix_ddl_bigquery.sql for BigQuery version
