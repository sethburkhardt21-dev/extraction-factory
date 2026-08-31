-- ============================================================================
-- B6 Deduplication Fix - Production DDL (Postgres + BigQuery UDFs)
-- Agent B6: Dedup Fix Developer
-- Focus:
--   1. DOI normalization: lowercase trim URL prefix
--   2. Bramer page expansion: pagination normalization
--   3. Fuzzy title 90% similarity (pg_trgm + rapidfuzz reference)
-- ============================================================================

-- ---------------------------------------------
-- POSTGRESQL DDL
-- ---------------------------------------------
-- Enable extensions for fuzzy matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Drop if exists for idempotency
DROP TABLE IF EXISTS anesthesia_pubmed_dedup CASCADE;
DROP TABLE IF EXISTS anesthesia_dedup_decisions CASCADE;

-- Main table with improved dedup columns (extends original schema)
CREATE TABLE anesthesia_pubmed_dedup (
    pmid TEXT PRIMARY KEY,
    doi_raw TEXT,
    doi_normalized TEXT, -- lowercase, trimmed, url prefix stripped
    pmcid TEXT,
    title TEXT NOT NULL,
    title_normalized TEXT GENERATED ALWAYS AS (
        lower(
          regexp_replace(
            regexp_replace(title, '<[^>]+>', ' ', 'g'),
            '[^a-z0-9\s]', ' ', 'gi'
          )
        )
    ) STORED,
    abstract TEXT,
    authors_jsonb JSONB,
    first_author_last TEXT GENERATED ALWAYS AS (
        lower((authors_jsonb->0->>'last_name'))
    ) STORED,
    journal_title TEXT,
    journal_iso TEXT,
    volume TEXT,
    issue TEXT,
    pages_raw TEXT,
    pages_normalized TEXT, -- Bramer expanded e.g. 123-125
    page_start INT,
    page_end INT,
    pub_year INT,
    pub_date DATE,
    mesh_terms JSONB,
    publication_types TEXT[],
    anesthesia_subdomains TEXT[],
    study_type TEXT,
    extraction_agent INT,
    dedup_status TEXT CHECK (dedup_status IN ('unique','duplicate_type_I','duplicate_type_II','merged')),
    duplicate_of_pmid TEXT REFERENCES anesthesia_pubmed_dedup(pmid),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for dedup performance
CREATE INDEX idx_doi_norm ON anesthesia_pubmed_dedup (doi_normalized) WHERE doi_normalized IS NOT NULL;
CREATE INDEX idx_pmid ON anesthesia_pubmed_dedup (pmid);
CREATE INDEX idx_title_trgm ON anesthesia_pubmed_dedup USING gin (title_normalized gin_trgm_ops);
CREATE INDEX idx_title_normalized_btree ON anesthesia_pubmed_dedup (title_normalized);
CREATE INDEX idx_year ON anesthesia_pubmed_dedup (pub_year);
CREATE INDEX idx_first_author ON anesthesia_pubmed_dedup (first_author_last);
CREATE INDEX idx_pages_norm ON anesthesia_pubmed_dedup (pages_normalized);
CREATE INDEX idx_bramer1 ON anesthesia_pubmed_dedup (first_author_last, pub_year, pages_normalized);
CREATE INDEX idx_bramer2 ON anesthesia_pubmed_dedup (pub_year, pages_normalized);
CREATE INDEX idx_bramer3 ON anesthesia_pubmed_dedup (journal_title, pages_normalized);

CREATE TABLE anesthesia_dedup_decisions (
    decision_id SERIAL PRIMARY KEY,
    pmid_primary TEXT NOT NULL,
    pmid_duplicate TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN (
        'DOI_normalized','PMID_exact','Bramer_Title_Year_Journal_Pages',
        'Bramer_Author_Year_Title_Journal','Bramer_Title_Journal_Pages',
        'Fuzzy_Title_90','Manual'
    )),
    similarity INT CHECK (similarity BETWEEN 0 AND 100),
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(pmid_primary, pmid_duplicate)
);
CREATE INDEX idx_decisions_dup ON anesthesia_dedup_decisions (pmid_duplicate);
CREATE INDEX idx_decisions_primary ON anesthesia_dedup_decisions (pmid_primary);

-- -----------------------------------------------------------
-- FUNCTION 1: DOI NORMALIZATION (lowercase trim URL prefix)
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION normalize_doi(input_doi TEXT)
RETURNS TEXT AS $$
DECLARE
    s TEXT;
BEGIN
    IF input_doi IS NULL THEN RETURN NULL; END IF;
    s := trim(input_doi);
    IF s = '' THEN RETURN NULL; END IF;
    FOR i IN 1..3 LOOP
        s := regexp_replace(s, '^\s*(https?://(dx\.)?doi\.org/|doi:\s*)\s*', '', 'i');
        s := trim(s);
    END LOOP;
    s := trim(both '<> ' FROM s);
    s := regexp_replace(s, '[.\s;,?]+$', '', 'g');
    s := lower(s);
    s := regexp_replace(s, '\s+', '', 'g');
    IF s !~ '^10\.[0-9]+/.+' THEN
        RETURN NULL;
    END IF;
    RETURN s;
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

-- -----------------------------------------------------------
-- FUNCTION 2: BRAMER PAGE EXPANSION
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION expand_medline_pages(pages_raw TEXT)
RETURNS TABLE(normalized_pages TEXT, page_start INT, page_end INT) AS $$
DECLARE
    s TEXT;
    start_raw TEXT;
    end_raw TEXT;
    start_num INT;
    end_num INT;
    len_s INT;
    len_e INT;
    expanded_end INT;
    prefix_part TEXT;
BEGIN
    IF pages_raw IS NULL THEN
        RETURN QUERY SELECT NULL::TEXT, NULL::INT, NULL::INT;
        RETURN;
    END IF;
    s := trim(pages_raw);
    s := replace(s, ' ', '');
    s := regexp_replace(s, '[–—]', '-', 'g');
    IF s = '' THEN
        RETURN QUERY SELECT NULL::TEXT, NULL::INT, NULL::INT;
        RETURN;
    END IF;
    IF s ~ '^([A-Za-z]*[0-9]+[A-Za-z]*)-([A-Za-z]*[0-9]+[A-Za-z]*)$' THEN
        start_raw := (regexp_match(s, '^([A-Za-z]*[0-9]+[A-Za-z]*)-([A-Za-z]*[0-9]+[A-Za-z]*)$'))[1];
        end_raw := (regexp_match(s, '^([A-Za-z]*[0-9]+[A-Za-z]*)-([A-Za-z]*[0-9]+[A-Za-z]*)$'))[2];
        BEGIN
            start_num := (regexp_match(start_raw, '(\d+)'))[1]::INT;
        EXCEPTION WHEN OTHERS THEN
            RETURN QUERY SELECT (start_raw || '-' || end_raw)::TEXT, NULL::INT, NULL::INT;
            RETURN;
        END;
        BEGIN
            end_num := (regexp_match(end_raw, '(\d+)'))[1]::INT;
        EXCEPTION WHEN OTHERS THEN
            RETURN QUERY SELECT (start_raw || '-' || end_raw)::TEXT, start_num, NULL::INT;
            RETURN;
        END;
        DECLARE
            start_digits TEXT;
            end_digits TEXT;
        BEGIN
            start_digits := (regexp_match(start_raw, '(\d+)'))[1];
            end_digits := (regexp_match(end_raw, '(\d+)'))[1];
            len_s := length(start_digits);
            len_e := length(end_digits);
            IF end_num < start_num AND len_e < len_s THEN
                prefix_part := substring(start_digits from 1 for len_s - len_e);
                expanded_end := (prefix_part || end_digits)::INT;
                RETURN QUERY SELECT (start_digits || '-' || expanded_end::TEXT)::TEXT, start_num, expanded_end;
                RETURN;
            ELSE
                RETURN QUERY SELECT (start_raw || '-' || end_raw)::TEXT, start_num, end_num;
                RETURN;
            END IF;
        END;
    END IF;
    IF s ~ '^[A-Za-z]*[0-9]+[A-Za-z]*$' THEN
        BEGIN
            start_num := (regexp_match(s, '(\d+)'))[1]::INT;
            RETURN QUERY SELECT s::TEXT, start_num, start_num;
            RETURN;
        EXCEPTION WHEN OTHERS THEN
            RETURN QUERY SELECT s::TEXT, NULL::INT, NULL::INT;
            RETURN;
        END;
    END IF;
    IF s ~ '[;,]' THEN
        s := split_part(s, ',', 1);
        s := split_part(s, ';', 1);
        RETURN QUERY SELECT * FROM expand_medline_pages(s);
        RETURN;
    END IF;
    RETURN QUERY SELECT NULL::TEXT, NULL::INT, NULL::INT;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION bramer_pages_dedup_key(pages_raw TEXT)
RETURNS TEXT AS $$
DECLARE
    rec RECORD;
BEGIN
    SELECT * INTO rec FROM expand_medline_pages(pages_raw) LIMIT 1;
    RETURN lower(COALESCE(rec.normalized_pages, ''));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- -----------------------------------------------------------
-- FUNCTION 3: TITLE NORMALIZATION
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION normalize_title_fuzzy(input_title TEXT)
RETURNS TEXT AS $$
BEGIN
    IF input_title IS NULL THEN RETURN ''; END IF;
    RETURN lower(
        regexp_replace(
            regexp_replace(
                regexp_replace(input_title, '<[^>]+>', ' ', 'g'),
                '[^a-z0-9\s]', ' ', 'gi'
            ),
            '\s+', ' ', 'g'
        )
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- -----------------------------------------------------------
-- VIEW: DEDUP CANDIDATES - fuzzy title >=90% within year block
-- -----------------------------------------------------------
CREATE OR REPLACE VIEW vw_fuzzy_title_candidates AS
WITH normalized AS (
    SELECT 
        pmid,
        title,
        normalize_title_fuzzy(title) AS title_norm,
        pub_year,
        first_author_last,
        pages_normalized,
        journal_title
    FROM anesthesia_pubmed_dedup
    WHERE dedup_status = 'unique' OR dedup_status IS NULL
)
SELECT
    a.pmid AS pmid_a,
    b.pmid AS pmid_b,
    a.title AS title_a,
    b.title AS title_b,
    similarity(a.title_norm, b.title_norm) AS trigram_sim,
    a.pub_year,
    a.first_author_last,
    a.pages_normalized
FROM normalized a
JOIN normalized b ON 
    a.pmid < b.pmid
    AND a.pub_year BETWEEN b.pub_year -1 AND b.pub_year +1
    AND left(a.title_norm,3) = left(b.title_norm,3)
    AND similarity(a.title_norm, b.title_norm) >= 0.85
WHERE 
    (a.first_author_last = b.first_author_last OR a.pages_normalized = b.pages_normalized)
    AND length(a.title_norm) > 20
ORDER BY trigram_sim DESC;

-- -----------------------------------------------------------
-- TRIGGER: auto-normalize DOI and pages on insert
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_normalize_dedup_fields()
RETURNS TRIGGER AS $$
DECLARE
    rec RECORD;
BEGIN
    NEW.doi_normalized := normalize_doi(NEW.doi_raw);
    IF NEW.pages_raw IS NOT NULL THEN
        SELECT * INTO rec FROM expand_medline_pages(NEW.pages_raw) LIMIT 1;
        NEW.pages_normalized := rec.normalized_pages;
        NEW.page_start := rec.page_start;
        NEW.page_end := rec.page_end;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS t_normalize_dedup ON anesthesia_pubmed_dedup;
CREATE TRIGGER t_normalize_dedup
    BEFORE INSERT OR UPDATE ON anesthesia_pubmed_dedup
    FOR EACH ROW EXECUTE FUNCTION trg_normalize_dedup_fields();

-- ---------------------------------------------
-- BIGQUERY DDL + UDFs (StandardSQL) - Commented reference implementation
-- ---------------------------------------------
-- See companion file b6_dedup_fix_bq.sql for executable BigQuery version

-- ============================================================================
-- VALIDATION QUERIES (Postgres)
-- ============================================================================
-- SELECT normalize_doi('https://doi.org/10.1234/ABC.123');
-- SELECT * FROM expand_medline_pages('123-5');
-- SELECT * FROM expand_medline_pages('1101-9');
-- SELECT * FROM expand_medline_pages('123-34');
-- SELECT * FROM vw_fuzzy_title_candidates WHERE trigram_sim >= 0.9 LIMIT 50;
-- SELECT dedup_status, COUNT(*) FROM anesthesia_pubmed_dedup GROUP BY dedup_status;
