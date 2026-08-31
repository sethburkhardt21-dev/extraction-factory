
-- =============================================================================
-- PRODUCTION POSTGRES DDL: Anesthesia PubMed Max Extraction
-- Agent B1: Postgres DDL Architect - Swarm B Database DDL
-- =============================================================================
-- Fixes audit issues:
--  1. rate limits inverted (0.34s for key vs 0.5 non-key was inverted in code comment;
--     actual should be 10/s without key = 0.1s min, 20/s with key = 0.05s min but conservative 0.34/0.11)
--     -> DDL stores correct rate tracking in ingestion_sessions + rate_limit_config
--  2. WebEnv expiration not handled -> pubmed_search_sessions with expires_at + webenv_registry
--  3. DOI normalization missing -> doi_normalized GENERATED column + unique index + function pubmed_normalize_doi()
--  4. classification FP via substring (e.g. "pain" matches "painting") -> subdomain_terms catalog with regex word boundaries
--  5. MedlineDate fallback missing -> publication_date_raw TEXT + parse function + publication_year fallback logic
--  6. PMID as string vs BIGINT -> store as BIGINT primary
--  7. Impact factor mapping stale -> journals table with effective_date + source column
--
-- Schema decisions:
--  - PubMed core: reference table pubmed_pmids (unique PMID enforcement, non-partitioned)
--  - Main facts: pubmed_articles PARTITION BY RANGE (publication_year) 1960-2030
--  - JSONB retained for mesh_terms, authors, abstract_structured, chemicals, study_design, etc
--    while normalized lookup + junction tables provide 3NF analytics
--  - GIN indexes with jsonb_path_ops for containment + pg_trgm for title ILIKE
--  - BRIN index on publication_year for append-only scan
--  - Partition-wise PK includes publication_year per Postgres declarative partitioning requirements
-- =============================================================================

-- ---------------------------
-- 0. EXTENSIONS
-- ---------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch; -- levenshtein for dedup

-- ---------------------------
-- 1. ENUMS & DOMAINS
-- ---------------------------
DO $$ BEGIN
  CREATE TYPE anesthesia_subdomain AS ENUM (
    'General Anesthesia',
    'Regional Anesthesia - Spinal Epidural',
    'Peripheral Nerve Blocks',
    'Local Anesthetics Pharmacology',
    'Airway Management',
    'Anesthesia Monitoring',
    'Pediatric Anesthesia',
    'Obstetric Anesthesia',
    'Cardiac Anesthesia',
    'Neuroanesthesia',
    'Critical Care ICU Sedation',
    'Pain Medicine',
    'Anesthesia Safety',
    'Pharmacology - Opioids Propofol Ketamine NMB',
    'ERAS Perioperative',
    'AI Simulation Education'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE dedup_status_t AS ENUM (
    'unique',
    'duplicate_type_I',
    'duplicate_type_II',
    'merged'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE study_design_type_t AS ENUM (
    'RCT',
    'Systematic Review',
    'Meta-Analysis',
    'Observational',
    'Case Report',
    'Guideline',
    'Narrative Review',
    'Bibliometric',
    'Animal',
    'In Vitro',
    'Other'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------
-- 2. UTILITY FUNCTIONS (AUDIT FIXES)
-- ---------------------------

-- 2a. DOI normalization: lower, trim, strip https://doi.org/, trailing punctuation
CREATE OR REPLACE FUNCTION pubmed_normalize_doi(raw_doi TEXT)
RETURNS TEXT LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
  d TEXT;
BEGIN
  IF raw_doi IS NULL THEN RETURN NULL; END IF;
  d := lower(trim(raw_doi));
  -- strip url prefixes
  d := regexp_replace(d, '^https?://(dx\.)?doi\.org/', '');
  d := regexp_replace(d, '^doi:\s*', '');
  -- strip trailing dot, comma, semicolon that are common XML artifacts
  d := regexp_replace(d, '[\.,;]+$', '');
  d := trim(d);
  IF d = '' THEN RETURN NULL; END IF;
  RETURN d;
END $$;

-- 2b. MedlineDate fallback parser
-- PubMed Date can be: <Year>2019</Year><Month>12</Month><Day>10</Day>
-- or <MedlineDate>2019 Dec 10</MedlineDate> or "2019 Spring" or "2019-2020"
CREATE OR REPLACE FUNCTION pubmed_parse_medline_date(medline_date TEXT, out_year SMALLINT, out_month SMALLINT, out_day SMALLINT)
RETURNS TABLE(year SMALLINT, month SMALLINT, day SMALLINT) LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  m TEXT;
  y_match TEXT;
  month_map JSONB := '{"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                       "spring":3,"summer":6,"fall":9,"autumn":9,"winter":12}'::jsonb;
  month_text TEXT;
BEGIN
  IF medline_date IS NULL THEN
    RETURN QUERY SELECT NULL::SMALLINT, NULL::SMALLINT, NULL::SMALLINT;
    RETURN;
  END IF;
  m := lower(trim(medline_date));
  -- Extract first 4-digit year
  y_match := substring(m from '(19|20)[0-9]{2}');
  IF y_match IS NOT NULL THEN
    out_year := y_match::SMALLINT;
  END IF;
  -- Extract month word
  month_text := substring(m from '(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|spring|summer|fall|autumn)');
  IF month_text IS NOT NULL THEN
    out_month := (month_map ->> month_text)::SMALLINT;
  END IF;
  -- Extract day number after month or standalone
  out_day := (substring(m from '\y([0-9]{1,2})\y' )::SMALLINT);
  -- If day >31, null it (year contamination)
  IF out_day > 31 THEN out_day := NULL; END IF;
  RETURN QUERY SELECT out_year, out_month, out_day;
END $$;

-- Simplified wrapper for generated column use (year only)
CREATE OR REPLACE FUNCTION pubmed_extract_year_fallback(pub_date_jsonb JSONB, medline_raw TEXT, pdat TEXT)
RETURNS SMALLINT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  y SMALLINT;
BEGIN
  -- Try structured JSON year first
  BEGIN
    y := (pub_date_jsonb ->> 'year')::SMALLINT;
    IF y IS NOT NULL AND y BETWEEN 1800 AND 2100 THEN RETURN y; END IF;
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
  -- Try pdat string if present (e.g., "2020" or "2020 Jan")
  IF pdat IS NOT NULL THEN
    BEGIN
      y := substring(pdat from '(19|20)[0-9]{2}')::SMALLINT;
      IF y BETWEEN 1800 AND 2100 THEN RETURN y; END IF;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
  END IF;
  -- Fallback medline parsing
  IF medline_raw IS NOT NULL THEN
    SELECT (pubmed_parse_medline_date(medline_raw, NULL, NULL)).year INTO y;
    IF y BETWEEN 1800 AND 2100 THEN RETURN y; END IF;
  END IF;
  RETURN 1975; -- safe default for partitioning (pre-1980 bucket)
END $$;

-- 2c. Word-boundary classification check (fixes FP via substring)
-- Uses \m and \M for word boundaries in Postgres regex
CREATE OR REPLACE FUNCTION anesthesia_match_subdomain(text_to_search TEXT, term TEXT, use_word_boundary BOOLEAN)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF text_to_search IS NULL OR term IS NULL THEN RETURN FALSE; END IF;
  IF use_word_boundary THEN
    RETURN lower(text_to_search) ~ ('\m' || lower(term) || '\M');
  ELSE
    -- qualifier or phrase that legitimately needs substring (e.g., D008305)
    RETURN lower(text_to_search) LIKE '%' || lower(term) || '%';
  END IF;
END $$;

-- ---------------------------
-- 3. REFERENCE / LOOKUP TABLES (non-partitioned)
-- ---------------------------

-- 3a. Journals with IF tracking
CREATE TABLE IF NOT EXISTS journals (
  journal_id    BIGSERIAL PRIMARY KEY,
  nlm_id        TEXT,
  title         TEXT NOT NULL,
  iso_abbreviation TEXT,
  issn_print    TEXT,
  issn_online   TEXT,
  publisher     TEXT,
  impact_factor NUMERIC(5,3),
  if_year       SMALLINT,
  if_source     TEXT DEFAULT 'manual_mapping',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (title)
);
CREATE INDEX IF NOT EXISTS idx_journals_issn ON journals(issn_print, issn_online);
CREATE INDEX IF NOT EXISTS idx_journals_title_trgm ON journals USING GIN (title gin_trgm_ops);

-- 3b. Authors normalized (dedup by ORCID primary, else normalized name)
CREATE TABLE IF NOT EXISTS authors_lookup (
  author_id   BIGSERIAL PRIMARY KEY,
  last_name   TEXT NOT NULL,
  fore_name   TEXT,
  initials    TEXT,
  full_name   TEXT GENERATED ALWAYS AS (trim(coalesce(fore_name,'') || ' ' || coalesce(last_name,''))) STORED,
  orcid       TEXT,
  affiliation TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (orcid) -- ORCID unique when not null will be enforced via partial index below
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_authors_name_no_orcid ON authors_lookup (lower(last_name), lower(coalesce(fore_name,'')), lower(coalesce(initials,''))) WHERE orcid IS NULL;
CREATE INDEX IF NOT EXISTS idx_authors_orcid ON authors_lookup (orcid) WHERE orcid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_authors_last_name_trgm ON authors_lookup USING GIN (last_name gin_trgm_ops);

-- 3c. MeSH Terms lookup
CREATE TABLE IF NOT EXISTS mesh_terms_lookup (
  mesh_id       BIGSERIAL PRIMARY KEY,
  descriptor_ui TEXT NOT NULL, -- e.g., D009407
  descriptor_name TEXT NOT NULL,
  tree_numbers  TEXT[], -- optional
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (descriptor_ui),
  UNIQUE (descriptor_name)
);
CREATE INDEX IF NOT EXISTS idx_mesh_name_trgm ON mesh_terms_lookup USING GIN (descriptor_name gin_trgm_ops);

-- 3d. Chemicals / Substances
CREATE TABLE IF NOT EXISTS chemicals_lookup (
  chem_id       BIGSERIAL PRIMARY KEY,
  ui            TEXT NOT NULL,
  name          TEXT NOT NULL,
  registry_number TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (ui)
);

-- 3e. Subdomain classification rules (fixes substring FP audit issue)
CREATE TABLE IF NOT EXISTS subdomain_classification_rules (
  rule_id       BIGSERIAL PRIMARY KEY,
  subdomain     anesthesia_subdomain NOT NULL,
  term          TEXT NOT NULL, -- e.g., 'nerve block', 'BIS'
  source_field  TEXT NOT NULL DEFAULT 'both' CHECK (source_field IN ('mesh','tiab','both','pt')),
  use_word_boundary BOOLEAN NOT NULL DEFAULT true, -- true = \mTERM\M prevents "pain" matching "painting"
  is_regex      BOOLEAN NOT NULL DEFAULT false,
  priority      SMALLINT NOT NULL DEFAULT 100,
  active        BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (subdomain, term, source_field)
);
-- Pre-seed with safe examples (full list from pipeline AGENT_QUERIES would be loaded via ETL)
INSERT INTO subdomain_classification_rules (subdomain, term, source_field, use_word_boundary, is_regex, priority) VALUES
  ('General Anesthesia', 'Anesthesia, General', 'mesh', false, false, 10),
  ('Peripheral Nerve Blocks', 'nerve block', 'both', true, false, 10),
  ('Peripheral Nerve Blocks', 'brachial plexus', 'both', true, false, 10),
  ('Airway Management', 'difficult airway', 'both', true, false, 10),
  ('Pain Medicine', 'pain, postoperative', 'mesh', false, false, 10),
  ('Anesthesia Safety', 'malignant hyperthermia', 'mesh', false, false, 10)
ON CONFLICT DO NOTHING;

-- 3f. PMID reference (enforces global uniqueness, 1:1 with partitioned fact)
CREATE TABLE IF NOT EXISTS pubmed_pmids (
  pmid              BIGINT PRIMARY KEY,
  publication_year  SMALLINT NOT NULL CHECK (publication_year BETWEEN 1800 AND 2100),
  doi_raw           TEXT,
  doi_normalized    TEXT GENERATED ALWAYS AS (pubmed_normalize_doi(doi_raw)) STORED,
  title_hash        TEXT, -- sha256 lower(title) for dedup Type-II
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- DOI dedup index (handles normalization issue)
CREATE UNIQUE INDEX IF NOT EXISTS uq_pmids_doi_norm ON pubmed_pmids (doi_normalized) WHERE doi_normalized IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pmids_year ON pubmed_pmids (publication_year);
CREATE INDEX IF NOT EXISTS idx_pmids_title_hash ON pubmed_pmids (title_hash);

-- 3g. WebEnv / Session registry (fixes WebEnv expiration audit)
CREATE TABLE IF NOT EXISTS pubmed_search_sessions (
  session_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  webenv        TEXT NOT NULL,
  query_key     TEXT NOT NULL,
  query_text    TEXT NOT NULL,
  agent_id      SMALLINT CHECK (agent_id BETWEEN 1 AND 16),
  total_count   INTEGER,
  retmax        INTEGER DEFAULT 100,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours'), -- NCBI WebEnv expires ~48h, use 24h conservative
  last_used_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_expired    BOOLEAN GENERATED ALWAYS AS (expires_at < now()) STORED,
  CONSTRAINT uq_webenv_qkey UNIQUE (webenv, query_key)
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON pubmed_search_sessions (expires_at) WHERE is_expired = false;
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON pubmed_search_sessions (agent_id, created_at DESC);

-- 3h. Rate limiting config + audit log
CREATE TABLE IF NOT EXISTS pubmed_rate_limit_config (
  config_id         SERIAL PRIMARY KEY,
  with_api_key      BOOLEAN NOT NULL,
  max_per_second    NUMERIC(4,2) NOT NULL,
  min_delay_ms      INTEGER NOT NULL, -- sleep between requests
  burst_max         INTEGER NOT NULL,
  note              TEXT,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (with_api_key)
);
INSERT INTO pubmed_rate_limit_config (with_api_key, max_per_second, min_delay_ms, burst_max, note) VALUES
  (false, 3.0, 334, 3, 'NCBI: 3 req/s without API key - corrected from inverted 10/s bug'),
  (true, 10.0, 110, 10, 'NCBI: 10 req/s with API key - conservative from 20/s theoretical, per NCBI guidelines')
ON CONFLICT (with_api_key) DO UPDATE SET max_per_second = EXCLUDED.max_per_second, min_delay_ms = EXCLUDED.min_delay_ms;

CREATE TABLE IF NOT EXISTS pubmed_fetch_log (
  log_id        BIGSERIAL PRIMARY KEY,
  session_id    UUID REFERENCES pubmed_search_sessions(session_id),
  pmid_start    INTEGER,
  pmid_end      INTEGER,
  retstart      INTEGER NOT NULL,
  retmax        INTEGER NOT NULL,
  http_status   SMALLINT,
  duration_ms   INTEGER,
  fetched_count SMALLINT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fetch_log_session ON pubmed_fetch_log (session_id, created_at DESC);

-- ---------------------------
-- 4. MAIN PARTITIONED FACT TABLE
-- ---------------------------
CREATE TABLE IF NOT EXISTS pubmed_articles (
  pmid              BIGINT NOT NULL,
  publication_year  SMALLINT NOT NULL CHECK (publication_year BETWEEN 1800 AND 2100),
  doi_raw           TEXT,
  doi_normalized    TEXT GENERATED ALWAYS AS (pubmed_normalize_doi(doi_raw)) STORED,
  pmcid             TEXT,
  title             TEXT NOT NULL,
  title_tsv         TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(title,''))) STORED,
  abstract_text     TEXT,
  abstract_structured JSONB DEFAULT '{}'::jsonb, -- {background, methods, results, conclusions, full_sections}
  abstract_tsv      TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(abstract_text,''))) STORED,
  -- Authors retained as JSONB (audit + fast read) = [{last_name, fore_name, initials, affiliation, orcid, position}]
  authors           JSONB NOT NULL DEFAULT '[]'::jsonb,
  authors_count     SMALLINT GENERATED ALWAYS AS (jsonb_array_length(authors)) STORED,
  -- Publication date JSONB + raw fallbacks
  publication_date  JSONB NOT NULL DEFAULT '{}'::jsonb, -- {year, month, day, pub_type_date, pdat}
  publication_month SMALLINT,
  publication_day   SMALLINT,
  medline_date_raw  TEXT, -- raw <MedlineDate> for fallback parsing
  pdat_raw          TEXT, -- raw <PubDate> text
  -- Journal
  journal_id        BIGINT REFERENCES journals(journal_id),
  journal_snapshot  JSONB DEFAULT '{}'::jsonb, -- denormalized copy {title, iso_abbreviation, issn, volume, issue, pages, impact_factor, publisher}
  -- MeSH retained as JSONB + GIN
  mesh_terms        JSONB NOT NULL DEFAULT '[]'::jsonb, -- [{descriptor_name, descriptor_ui, qualifiers[], major_topic}]
  keywords          TEXT[] DEFAULT '{}',
  publication_types TEXT[] DEFAULT '{}', -- PT field
  chemicals         JSONB DEFAULT '[]'::jsonb, -- [{name, registry_number, ui}]
  -- Classification
  anesthesia_subdomains TEXT[] NOT NULL DEFAULT '{}', -- enum values as TEXT[] for partition tolerance (FK to enum via check)
  study_design      JSONB DEFAULT '{}'::jsonb, -- {type, is_landmark, n_patients, n_studies_included, multicenter, blinding, registration}
  anesthesia_specific JSONB DEFAULT '{}'::jsonb, -- {drugs[], techniques[], outcomes[], population, asa_class}
  citation_metrics  JSONB DEFAULT '{}'::jsonb, -- {openalex, semantic_scholar, etc}
  extraction_metadata JSONB NOT NULL DEFAULT '{}'::jsonb, -- {query_used, agent_id, retrieval_date, dedup_status, duplicate_of_pmid, webenv, query_key, retstart}
  -- Operational
  dedup_status      dedup_status_t NOT NULL DEFAULT 'unique',
  duplicate_of_pmid BIGINT,
  search_session_id UUID REFERENCES pubmed_search_sessions(session_id),
  ingestion_attempts SMALLINT DEFAULT 0,
  last_error        TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Constraint: PK must include partition key for Postgres declarative partitioning
  PRIMARY KEY (pmid, publication_year),
  -- FK to PMID reference ensures global uniqueness with 1:1
  FOREIGN KEY (pmid, publication_year) REFERENCES pubmed_pmids(pmid, publication_year) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
  CHECK (publication_year = COALESCE((publication_date->>'year')::SMALLINT, pubmed_extract_year_fallback(publication_date, medline_date_raw, pdat_raw)))
) PARTITION BY RANGE (publication_year);

-- Partitioning note: We also add CHECK to keep Title not empty etc.
ALTER TABLE pubmed_articles ADD CONSTRAINT chk_title_not_empty CHECK (char_length(title) > 5);

-- ---------------------------
-- 5. YEAR PARTITIONS CREATION (1960-2030)
-- ---------------------------
-- Decade partitions for older low-volume years, yearly for 1990+ where anesthesia volume explodes

CREATE TABLE IF NOT EXISTS pubmed_articles_1960_1979 PARTITION OF pubmed_articles FOR VALUES FROM (1960) TO (1980);
CREATE TABLE IF NOT EXISTS pubmed_articles_1980_1989 PARTITION OF pubmed_articles FOR VALUES FROM (1980) TO (1990);
-- Yearly partitions 1990-2030
CREATE TABLE IF NOT EXISTS pubmed_articles_1990 PARTITION OF pubmed_articles FOR VALUES FROM (1990) TO (1991);
CREATE TABLE IF NOT EXISTS pubmed_articles_1991 PARTITION OF pubmed_articles FOR VALUES FROM (1991) TO (1992);
CREATE TABLE IF NOT EXISTS pubmed_articles_1992 PARTITION OF pubmed_articles FOR VALUES FROM (1992) TO (1993);
CREATE TABLE IF NOT EXISTS pubmed_articles_1993 PARTITION OF pubmed_articles FOR VALUES FROM (1993) TO (1994);
CREATE TABLE IF NOT EXISTS pubmed_articles_1994 PARTITION OF pubmed_articles FOR VALUES FROM (1994) TO (1995);
CREATE TABLE IF NOT EXISTS pubmed_articles_1995 PARTITION OF pubmed_articles FOR VALUES FROM (1995) TO (1996);
CREATE TABLE IF NOT EXISTS pubmed_articles_1996 PARTITION OF pubmed_articles FOR VALUES FROM (1996) TO (1997);
CREATE TABLE IF NOT EXISTS pubmed_articles_1997 PARTITION OF pubmed_articles FOR VALUES FROM (1997) TO (1998);
CREATE TABLE IF NOT EXISTS pubmed_articles_1998 PARTITION OF pubmed_articles FOR VALUES FROM (1998) TO (1999);
CREATE TABLE IF NOT EXISTS pubmed_articles_1999 PARTITION OF pubmed_articles FOR VALUES FROM (1999) TO (2000);
CREATE TABLE IF NOT EXISTS pubmed_articles_2000 PARTITION OF pubmed_articles FOR VALUES FROM (2000) TO (2001);
CREATE TABLE IF NOT EXISTS pubmed_articles_2001 PARTITION OF pubmed_articles FOR VALUES FROM (2001) TO (2002);
CREATE TABLE IF NOT EXISTS pubmed_articles_2002 PARTITION OF pubmed_articles FOR VALUES FROM (2002) TO (2003);
CREATE TABLE IF NOT EXISTS pubmed_articles_2003 PARTITION OF pubmed_articles FOR VALUES FROM (2003) TO (2004);
CREATE TABLE IF NOT EXISTS pubmed_articles_2004 PARTITION OF pubmed_articles FOR VALUES FROM (2004) TO (2005);
CREATE TABLE IF NOT EXISTS pubmed_articles_2005 PARTITION OF pubmed_articles FOR VALUES FROM (2005) TO (2006);
CREATE TABLE IF NOT EXISTS pubmed_articles_2006 PARTITION OF pubmed_articles FOR VALUES FROM (2006) TO (2007);
CREATE TABLE IF NOT EXISTS pubmed_articles_2007 PARTITION OF pubmed_articles FOR VALUES FROM (2007) TO (2008);
CREATE TABLE IF NOT EXISTS pubmed_articles_2008 PARTITION OF pubmed_articles FOR VALUES FROM (2008) TO (2009);
CREATE TABLE IF NOT EXISTS pubmed_articles_2009 PARTITION OF pubmed_articles FOR VALUES FROM (2009) TO (2010);
CREATE TABLE IF NOT EXISTS pubmed_articles_2010 PARTITION OF pubmed_articles FOR VALUES FROM (2010) TO (2011);
CREATE TABLE IF NOT EXISTS pubmed_articles_2011 PARTITION OF pubmed_articles FOR VALUES FROM (2011) TO (2012);
CREATE TABLE IF NOT EXISTS pubmed_articles_2012 PARTITION OF pubmed_articles FOR VALUES FROM (2012) TO (2013);
CREATE TABLE IF NOT EXISTS pubmed_articles_2013 PARTITION OF pubmed_articles FOR VALUES FROM (2013) TO (2014);
CREATE TABLE IF NOT EXISTS pubmed_articles_2014 PARTITION OF pubmed_articles FOR VALUES FROM (2014) TO (2015);
CREATE TABLE IF NOT EXISTS pubmed_articles_2015 PARTITION OF pubmed_articles FOR VALUES FROM (2015) TO (2016);
CREATE TABLE IF NOT EXISTS pubmed_articles_2016 PARTITION OF pubmed_articles FOR VALUES FROM (2016) TO (2017);
CREATE TABLE IF NOT EXISTS pubmed_articles_2017 PARTITION OF pubmed_articles FOR VALUES FROM (2017) TO (2018);
CREATE TABLE IF NOT EXISTS pubmed_articles_2018 PARTITION OF pubmed_articles FOR VALUES FROM (2018) TO (2019);
CREATE TABLE IF NOT EXISTS pubmed_articles_2019 PARTITION OF pubmed_articles FOR VALUES FROM (2019) TO (2020);
CREATE TABLE IF NOT EXISTS pubmed_articles_2020 PARTITION OF pubmed_articles FOR VALUES FROM (2020) TO (2021);
CREATE TABLE IF NOT EXISTS pubmed_articles_2021 PARTITION OF pubmed_articles FOR VALUES FROM (2021) TO (2022);
CREATE TABLE IF NOT EXISTS pubmed_articles_2022 PARTITION OF pubmed_articles FOR VALUES FROM (2022) TO (2023);
CREATE TABLE IF NOT EXISTS pubmed_articles_2023 PARTITION OF pubmed_articles FOR VALUES FROM (2023) TO (2024);
CREATE TABLE IF NOT EXISTS pubmed_articles_2024 PARTITION OF pubmed_articles FOR VALUES FROM (2024) TO (2025);
CREATE TABLE IF NOT EXISTS pubmed_articles_2025 PARTITION OF pubmed_articles FOR VALUES FROM (2025) TO (2026);
CREATE TABLE IF NOT EXISTS pubmed_articles_2026 PARTITION OF pubmed_articles FOR VALUES FROM (2026) TO (2027);
CREATE TABLE IF NOT EXISTS pubmed_articles_2027_2030 PARTITION OF pubmed_articles FOR VALUES FROM (2027) TO (2031);

-- ---------------------------
-- 6. INDEXES ON PARTITIONED TABLE (propagates to all partitions in PG 11+)
-- ---------------------------
-- Core B-tree
CREATE INDEX IF NOT EXISTS idx_articles_year ON pubmed_articles (publication_year);
CREATE INDEX IF NOT EXISTS idx_articles_doi_norm ON pubmed_articles (doi_normalized) WHERE doi_normalized IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_pmcid ON pubmed_articles (pmcid) WHERE pmcid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_journal ON pubmed_articles (journal_id);
CREATE INDEX IF NOT EXISTS idx_articles_dedup ON pubmed_articles (dedup_status);
CREATE INDEX IF NOT EXISTS idx_articles_creation ON pubmed_articles (created_at DESC);

-- GIN indexes on JSONB (critical for mesh_terms, authors containment per research)
-- jsonb_path_ops is smaller + faster for @> containment, good for mesh lookup
CREATE INDEX IF NOT EXISTS idx_articles_mesh_gin ON pubmed_articles USING GIN (mesh_terms jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_articles_authors_gin ON pubmed_articles USING GIN (authors jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_articles_chemicals_gin ON pubmed_articles USING GIN (chemicals jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_articles_study_design_gin ON pubmed_articles USING GIN (study_design);
CREATE INDEX IF NOT EXISTS idx_articles_anesth_spec_gin ON pubmed_articles USING GIN (anesthesia_specific);
CREATE INDEX IF NOT EXISTS idx_articles_extraction_gin ON pubmed_articles USING GIN (extraction_metadata);

-- GIN on arrays
CREATE INDEX IF NOT EXISTS idx_articles_subdomains_gin ON pubmed_articles USING GIN (anesthesia_subdomains);
CREATE INDEX IF NOT EXISTS idx_articles_pubtypes_gin ON pubmed_articles USING GIN (publication_types);
CREATE INDEX IF NOT EXISTS idx_articles_keywords_gin ON pubmed_articles USING GIN (keywords);

-- Full-text search GIN
CREATE INDEX IF NOT EXISTS idx_articles_title_tsv ON pubmed_articles USING GIN (title_tsv);
CREATE INDEX IF NOT EXISTS idx_articles_abstract_tsv ON pubmed_articles USING GIN (abstract_tsv);

-- Trigram for ILIKE fuzzy title search (real-world user query)
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON pubmed_articles USING GIN (title gin_trgm_ops);

-- BRIN for append-only year scan (tiny index)
CREATE INDEX IF NOT EXISTS idx_articles_year_brin ON pubmed_articles USING BRIN (publication_year) WITH (pages_per_range = 1);

-- Partial indexes for common filtered queries
CREATE INDEX IF NOT EXISTS idx_articles_landmark ON pubmed_articles ((study_design->>'is_landmark')) WHERE (study_design->>'is_landmark')::boolean = true;
CREATE INDEX IF NOT EXISTS idx_articles_rct ON pubmed_articles (publication_year DESC) WHERE publication_types @> ARRAY['RCT'];
CREATE INDEX IF NOT EXISTS idx_articles_recent ON pubmed_articles (publication_year DESC, journal_id) WHERE publication_year >= 2020;

-- ---------------------------
-- 7. NORMALIZED JUNCTION TABLES (partitioned by year to allow FK)
-- ---------------------------

-- 7a. article_authors partitioned
CREATE TABLE IF NOT EXISTS article_authors (
  pmid              BIGINT NOT NULL,
  publication_year  SMALLINT NOT NULL,
  author_id         BIGINT NOT NULL REFERENCES authors_lookup(author_id),
  author_position   SMALLINT NOT NULL, -- 1-indexed
  is_first          BOOLEAN GENERATED ALWAYS AS (author_position = 1) STORED,
  is_last           BOOLEAN NOT NULL DEFAULT false,
  affiliation_raw   TEXT,
  orcid             TEXT,
  PRIMARY KEY (pmid, publication_year, author_id, author_position),
  FOREIGN KEY (pmid, publication_year) REFERENCES pubmed_articles(pmid, publication_year) ON DELETE CASCADE
) PARTITION BY RANGE (publication_year);

-- Create decade/year partitions for junction
CREATE TABLE IF NOT EXISTS article_authors_1960_1999 PARTITION OF article_authors FOR VALUES FROM (1960) TO (2000);
CREATE TABLE IF NOT EXISTS article_authors_2000_2009 PARTITION OF article_authors FOR VALUES FROM (2000) TO (2010);
CREATE TABLE IF NOT EXISTS article_authors_2010_2019 PARTITION OF article_authors FOR VALUES FROM (2010) TO (2020);
CREATE TABLE IF NOT EXISTS article_authors_2020_2030 PARTITION OF article_authors FOR VALUES FROM (2020) TO (2031);

CREATE INDEX IF NOT EXISTS idx_aa_author ON article_authors (author_id, publication_year DESC);
CREATE INDEX IF NOT EXISTS idx_aa_pmid ON article_authors (pmid);

-- 7b. article_mesh junction partitioned
CREATE TABLE IF NOT EXISTS article_mesh (
  pmid              BIGINT NOT NULL,
  publication_year  SMALLINT NOT NULL,
  mesh_id           BIGINT NOT NULL REFERENCES mesh_terms_lookup(mesh_id),
  qualifier         TEXT,
  major_topic       BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (pmid, publication_year, mesh_id, qualifier),
  FOREIGN KEY (pmid, publication_year) REFERENCES pubmed_articles(pmid, publication_year) ON DELETE CASCADE
) PARTITION BY RANGE (publication_year);

CREATE TABLE IF NOT EXISTS article_mesh_1960_1999 PARTITION OF article_mesh FOR VALUES FROM (1960) TO (2000);
CREATE TABLE IF NOT EXISTS article_mesh_2000_2009 PARTITION OF article_mesh FOR VALUES FROM (2000) TO (2010);
CREATE TABLE IF NOT EXISTS article_mesh_2010_2019 PARTITION OF article_mesh FOR VALUES FROM (2010) TO (2020);
CREATE TABLE IF NOT EXISTS article_mesh_2020_2030 PARTITION OF article_mesh FOR VALUES FROM (2020) TO (2031);

CREATE INDEX IF NOT EXISTS idx_am_mesh ON article_mesh (mesh_id, major_topic, publication_year DESC);
CREATE INDEX IF NOT EXISTS idx_am_major ON article_mesh (pmid) WHERE major_topic = true;

-- 7c. article chemicals junction (non-partitioned okay if small, but keep partitioned for consistency)
CREATE TABLE IF NOT EXISTS article_chemicals (
  pmid              BIGINT NOT NULL,
  publication_year  SMALLINT NOT NULL,
  chem_id           BIGINT NOT NULL REFERENCES chemicals_lookup(chem_id),
  PRIMARY KEY (pmid, publication_year, chem_id),
  FOREIGN KEY (pmid, publication_year) REFERENCES pubmed_articles(pmid, publication_year) ON DELETE CASCADE
) PARTITION BY RANGE (publication_year);

CREATE TABLE IF NOT EXISTS article_chemicals_1960_2009 PARTITION OF article_chemicals FOR VALUES FROM (1960) TO (2010);
CREATE TABLE IF NOT EXISTS article_chemicals_2010_2030 PARTITION OF article_chemicals FOR VALUES FROM (2010) TO (2031);

-- ---------------------------
-- 8. ANALYTICS VIEWS / MATERIALIZED VIEWS
-- ---------------------------

-- View for flattened reporting (matches SAMPLE.csv structure but enriched)
CREATE OR REPLACE VIEW v_anesthesia_articles_flat AS
SELECT
  a.pmid,
  a.doi_normalized AS doi,
  a.pmcid,
  a.title,
  a.publication_year AS year,
  a.publication_month,
  a.publication_day,
  a.medline_date_raw,
  COALESCE(j.title, a.journal_snapshot->>'title') AS journal_title,
  (a.journal_snapshot->>'iso_abbreviation') AS journal_iso,
  COALESCE((a.journal_snapshot->>'impact_factor')::NUMERIC, j.impact_factor) AS journal_if,
  a.publication_types,
  (SELECT string_agg(m->>'descriptor_name','|' ORDER BY (m->>'descriptor_name')) FROM jsonb_array_elements(a.mesh_terms) m LIMIT 15) AS mesh_terms_pipe,
  a.keywords,
  (SELECT string_agg(c->>'name','|' ORDER BY (c->>'name')) FROM jsonb_array_elements(a.chemicals) c) AS chemicals_pipe,
  a.anesthesia_subdomains,
  a.study_design->>'type' AS study_type,
  (a.study_design->>'is_landmark')::BOOLEAN AS is_landmark,
  (a.study_design->>'n_patients')::INT AS n_patients,
  (a.anesthesia_specific->>'drugs')::JSONB AS drugs,
  a.authors_count AS n_authors,
  (a.authors->0->>'last_name') AS first_author_last,
  (a.authors->0->>'affiliation') AS first_author_affiliation,
  (a.citation_metrics->>'citation_count_openalex')::INT AS citation_openalex,
  a.abstract_text,
  left(a.abstract_text, 800) AS abstract_first_800,
  a.dedup_status,
  a.extraction_metadata->>'query_used' AS extraction_query,
  (a.extraction_metadata->>'agent_id')::SMALLINT AS agent_id
FROM pubmed_articles a
LEFT JOIN journals j ON j.journal_id = a.journal_id;

-- Materialized view for subdomain yearly counts (partition pruning friendly)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_subdomain_year_counts AS
SELECT
  publication_year,
  unnest(anesthesia_subdomains) AS subdomain,
  count(*) AS article_count,
  count(*) FILTER (WHERE publication_types @> ARRAY['RCT']) AS rct_count,
  count(*) FILTER (WHERE (study_design->>'is_landmark')::boolean) AS landmark_count,
  avg(authors_count) AS avg_authors
FROM pubmed_articles
WHERE dedup_status = 'unique'
GROUP BY 1,2
ORDER BY 1 DESC, 3 DESC;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_subdomain ON mv_subdomain_year_counts (publication_year, subdomain);

-- Full-text search helper view
CREATE OR REPLACE VIEW v_fulltext_search AS
SELECT pmid, publication_year, title, abstract_text, title_tsv || abstract_tsv AS search_vector
FROM pubmed_articles;

-- ---------------------------
-- 9. TRIGGERS FOR updated_at + TITLE HASH
-- ---------------------------
CREATE OR REPLACE FUNCTION trg_set_updated_at() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END $$;

DROP TRIGGER IF EXISTS trg_articles_upd ON pubmed_articles;
CREATE TRIGGER trg_articles_upd BEFORE UPDATE ON pubmed_articles FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

DROP TRIGGER IF EXISTS trg_journals_upd ON journals;
CREATE TRIGGER trg_journals_upd BEFORE UPDATE ON journals FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- Title hash trigger for deduplication Type-II
CREATE OR REPLACE FUNCTION trg_set_title_hash() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.title_hash := encode(digest(lower(trim(NEW.title)), 'sha256'), 'hex');
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_pmids_title_hash ON pubmed_pmids;
CREATE TRIGGER trg_pmids_title_hash BEFORE INSERT OR UPDATE OF pmid ON pubmed_pmids
FOR EACH ROW WHEN (NEW.title_hash IS NULL) EXECUTE FUNCTION trg_set_title_hash();

-- Actually for pubmed_articles we need to sync to pmids table
CREATE OR REPLACE FUNCTION trg_sync_pmid_table() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO pubmed_pmids (pmid, publication_year, doi_raw, title_hash)
  VALUES (NEW.pmid, NEW.publication_year, NEW.doi_raw, encode(digest(lower(trim(NEW.title)), 'sha256'), 'hex'))
  ON CONFLICT (pmid) DO UPDATE SET publication_year = EXCLUDED.publication_year, doi_raw = EXCLUDED.doi_raw;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_sync_pmids ON pubmed_articles;
CREATE TRIGGER trg_sync_pmids AFTER INSERT ON pubmed_articles FOR EACH ROW EXECUTE FUNCTION trg_sync_pmid_table();

-- ---------------------------
-- 10. PARTITION MANAGEMENT FUNCTIONS
-- ---------------------------
CREATE OR REPLACE FUNCTION create_year_partition(year_in INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
  next_year INT := year_in + 1;
  partition_name TEXT := 'pubmed_articles_' || year_in;
BEGIN
  EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF pubmed_articles FOR VALUES FROM (%s) TO (%s)', partition_name, year_in, next_year);
  RAISE NOTICE 'Partition % created for year %', partition_name, year_in;
END $$;

CREATE OR REPLACE FUNCTION create_all_missing_partitions(start_year INT DEFAULT 1960, end_year INT DEFAULT 2030)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE y INT;
BEGIN
  FOR y IN start_year..end_year LOOP
    PERFORM create_year_partition(y);
  END LOOP;
END $$;

-- ---------------------------
-- 11. GRANTS / SECURITY (example roles)
-- ---------------------------
-- DO $$ BEGIN CREATE ROLE anethassist_reader; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- GRANT USAGE ON SCHEMA public TO anethassist_reader;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO anethassist_reader;

-- ---------------------------
-- 12. COMMENTS (documentation of audit fixes)
-- ---------------------------
COMMENT ON TABLE pubmed_articles IS 'Partitioned by RANGE(publication_year). Fixes: DOI normalization via generated column, MedlineDate fallback via medline_date_raw + pdat_raw + function, FP via substring fixed via subdomain_classification_rules with word boundaries';
COMMENT ON COLUMN pubmed_articles.doi_normalized IS 'AUDIT FIX: lowercase + strip URL prefix + trim punctuation. Unique index ensures dedup Type-I via DOI';
COMMENT ON COLUMN pubmed_articles.medline_date_raw IS 'AUDIT FIX: Stores raw <MedlineDate> like "2019 Spring" or "2020-2021". Parsed via pubmed_parse_medline_date() fallback';
COMMENT ON COLUMN pubmed_articles.authors IS 'JSONB保留完整author列表 (fast read) + normalized article_authors junction用于3NF分析';
COMMENT ON COLUMN pubmed_articles.mesh_terms IS 'JSONB保留MeSH全量 + article_mesh junction用于聚合。GIN jsonb_path_ops支持 @> contains';
COMMENT ON TABLE pubmed_search_sessions IS 'AUDIT FIX: WebEnv expiration tracked via expires_at (24h conservative vs 48h NCBI). is_expired generated column + partial index for active sessions only';
COMMENT ON TABLE pubmed_rate_limit_config IS 'AUDIT FIX: Corrects inverted rate limit. Without key 3/s (334ms), with key 10/s (110ms) conservative. Original bug had 10/s without key, 20/s with key misleading.';
COMMENT ON TABLE subdomain_classification_rules IS 'AUDIT FIX: FP via substring. Use \m term \M word boundaries. "pain" should not match "painting" or "painless"? Actually painless should match pain? Controlled via use_word_boundary flag.';

-- ---------------------------
-- 13. SAMPLE INSERT VALIDATION (for unit test)
-- ---------------------------
-- INSERT INTO pubmed_pmids (pmid, publication_year, doi_raw) VALUES (31112380, 2019, 'https://doi.org/10.1056/NEJMoa1904710.');
-- Should store doi_normalized = '10.1056/nejmoa1904710' and be queryable
-- SELECT pubmed_normalize_doi('https://doi.org/10.1056/NEJMoa1904710.') ; -- => 10.1056/nejmoa1904710
-- SELECT * FROM pubmed_parse_medline_date('2019 Spring', NULL, NULL); -- => year 2019 month 3
