-- Frontier Research Warehouse - PostgreSQL schema v2.0
-- Bronze: immutable source/run lineage. Silver: versioned canonical source projections.
-- Gold: non-destructive cross-source entities, evidence, releases and enrichments.

CREATE SCHEMA IF NOT EXISTS frontier;

-- =========================
-- BRONZE: RUNS + SOURCE DATA
-- =========================
CREATE TABLE IF NOT EXISTS frontier.ingestion_run (
  run_id UUID PRIMARY KEY,
  source TEXT NOT NULL,
  mode TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  canonical_schema_version TEXT NOT NULL,
  manifest_schema_version TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('running','completed','failed','dry_run')),
  certification_status TEXT NOT NULL CHECK (certification_status IN ('PENDING','PASS','WARN','FAIL','TRUNCATED')),
  source_version_start TEXT,
  source_version_end TEXT,
  source_changed_during_run BOOLEAN,
  query JSONB,
  query_fingerprint CHAR(64),
  expected_records BIGINT,
  observed_records BIGINT NOT NULL DEFAULT 0 CHECK (observed_records >= 0),
  valid_records BIGINT NOT NULL DEFAULT 0 CHECK (valid_records >= 0),
  quarantined_records BIGINT NOT NULL DEFAULT 0 CHECK (quarantined_records >= 0),
  unique_records BIGINT NOT NULL DEFAULT 0 CHECK (unique_records >= 0),
  truncated BOOLEAN NOT NULL DEFAULT FALSE,
  complete_against_source BOOLEAN,
  raw_sha256 CHAR(64),
  canonical_sha256 CHAR(64),
  quarantine_sha256 CHAR(64),
  provenance_sha256 CHAR(64),
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  errors JSONB NOT NULL DEFAULT '[]'::jsonb,
  artifacts JSONB NOT NULL DEFAULT '{}'::jsonb,
  manifest JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_source_started ON frontier.ingestion_run(source, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_cert ON frontier.ingestion_run(source, certification_status, completed_at DESC);

CREATE OR REPLACE VIEW frontier.promotable_run AS
SELECT *
FROM frontier.ingestion_run
WHERE status = 'completed'
  AND certification_status = 'PASS'
  AND truncated = FALSE
  AND complete_against_source IS TRUE
  AND quarantined_records = 0
  AND COALESCE(source_changed_during_run, FALSE) = FALSE;

CREATE TABLE IF NOT EXISTS frontier.run_artifact (
  artifact_id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES frontier.ingestion_run(run_id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  locator TEXT NOT NULL,
  media_type TEXT,
  sha256 CHAR(64) NOT NULL,
  byte_size BIGINT CHECK (byte_size IS NULL OR byte_size >= 0),
  record_count BIGINT CHECK (record_count IS NULL OR record_count >= 0),
  created_at TIMESTAMPTZ NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (run_id, role, locator)
);
CREATE INDEX IF NOT EXISTS idx_run_artifact_sha ON frontier.run_artifact(sha256);

-- One row per unique raw source payload. The same payload may be observed in many runs.
CREATE TABLE IF NOT EXISTS frontier.source_record (
  source_record_key UUID PRIMARY KEY,
  source TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  source_version_id TEXT NOT NULL DEFAULT '',
  source_record_sha256 CHAR(64) NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL,
  source_url TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source, source_record_id, source_version_id, source_record_sha256)
);
CREATE INDEX IF NOT EXISTS idx_source_record_identity ON frontier.source_record(source, source_record_id, source_version_id);
CREATE INDEX IF NOT EXISTS idx_source_record_sha ON frontier.source_record(source_record_sha256);

-- Observation is the many-to-many bridge between immutable content and extraction runs.
CREATE TABLE IF NOT EXISTS frontier.source_observation (
  run_id UUID NOT NULL REFERENCES frontier.ingestion_run(run_id) ON DELETE CASCADE,
  source_record_key UUID NOT NULL REFERENCES frontier.source_record(source_record_key),
  retrieved_at TIMESTAMPTZ NOT NULL,
  source_version TEXT,
  source_updated_at TIMESTAMPTZ,
  raw_locator TEXT,
  transport_raw_locators JSONB NOT NULL DEFAULT '[]'::jsonb,
  parse_status TEXT NOT NULL CHECK (parse_status IN ('parsed','quarantined','unsupported','skipped')),
  parse_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  provenance_schema_version TEXT NOT NULL,
  provenance JSONB NOT NULL,
  PRIMARY KEY (run_id, source_record_key)
);
CREATE INDEX IF NOT EXISTS idx_source_observation_record ON frontier.source_observation(source_record_key, retrieved_at DESC);

-- Canonical representation is versioned independently from retrieval. Re-parsing the same
-- raw payload with a new parser/schema never mutates an older canonical result.
CREATE TABLE IF NOT EXISTS frontier.canonical_record (
  canonical_record_key UUID PRIMARY KEY,
  source_record_key UUID NOT NULL REFERENCES frontier.source_record(source_record_key),
  parser_version TEXT NOT NULL,
  canonical_schema_version TEXT NOT NULL,
  canonical_sha256 CHAR(64) NOT NULL,
  canonical_locator TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  validation_status TEXT NOT NULL CHECK (validation_status IN ('PASS','WARN','FAIL')),
  validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  UNIQUE (source_record_key, parser_version, canonical_schema_version, canonical_sha256)
);
CREATE INDEX IF NOT EXISTS idx_canonical_source_record ON frontier.canonical_record(source_record_key);

CREATE TABLE IF NOT EXISTS frontier.quarantine_record (
  quarantine_id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES frontier.ingestion_run(run_id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  source_record_id TEXT,
  source_record_sha256 CHAR(64),
  archive_member TEXT,
  raw_locator TEXT,
  raw_payload JSONB,
  raw_text TEXT,
  raw_base64 TEXT,
  error_type TEXT NOT NULL,
  error_message TEXT NOT NULL,
  quarantined_at TIMESTAMPTZ NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_quarantine_run ON frontier.quarantine_record(run_id);

-- =========================
-- SILVER: CLINICALTRIALS.GOV
-- =========================
CREATE TABLE IF NOT EXISTS frontier.ctg_study_record (
  canonical_record_key UUID PRIMARY KEY REFERENCES frontier.canonical_record(canonical_record_key) ON DELETE CASCADE,
  nct_id TEXT NOT NULL,
  brief_title TEXT NOT NULL,
  official_title TEXT,
  acronym TEXT,
  nct_id_aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  org_study_id_info JSONB NOT NULL DEFAULT '{}'::jsonb,
  secondary_id_infos JSONB NOT NULL DEFAULT '[]'::jsonb,
  organization JSONB NOT NULL DEFAULT '{}'::jsonb,
  brief_summary TEXT,
  detailed_description TEXT,
  overall_status TEXT,
  why_stopped TEXT,
  expanded_access_info JSONB NOT NULL DEFAULT '{}'::jsonb,
  phases JSONB NOT NULL DEFAULT '[]'::jsonb,
  study_type TEXT,
  design JSONB NOT NULL DEFAULT '{}'::jsonb,
  enrollment_count INTEGER,
  enrollment_type TEXT,
  conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
  keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
  sponsors JSONB NOT NULL DEFAULT '{}'::jsonb,
  start_date DATE,
  start_date_type TEXT,
  primary_completion_date DATE,
  primary_completion_date_type TEXT,
  completion_date DATE,
  completion_date_type TEXT,
  study_first_submit_date DATE,
  study_first_post_date DATE,
  last_update_submit_date DATE,
  last_update_post_date DATE,
  last_update_post_date_type TEXT,
  eligibility JSONB NOT NULL DEFAULT '{}'::jsonb,
  arms JSONB NOT NULL DEFAULT '[]'::jsonb,
  interventions JSONB NOT NULL DEFAULT '[]'::jsonb,
  contacts JSONB NOT NULL DEFAULT '{}'::jsonb,
  locations JSONB NOT NULL DEFAULT '[]'::jsonb,
  primary_outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,
  secondary_outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,
  other_outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,
  references JSONB NOT NULL DEFAULT '[]'::jsonb,
  see_also_links JSONB NOT NULL DEFAULT '[]'::jsonb,
  available_ipds JSONB NOT NULL DEFAULT '[]'::jsonb,
  ipd_sharing JSONB NOT NULL DEFAULT '{}'::jsonb,
  oversight JSONB NOT NULL DEFAULT '{}'::jsonb,
  has_results BOOLEAN,
  is_fda_regulated_drug BOOLEAN,
  is_fda_regulated_device BOOLEAN,
  protocol_raw JSONB NOT NULL,
  results_raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  annotation_raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  document_raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  derived_raw JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_ctg_record_nct ON frontier.ctg_study_record(nct_id);
CREATE INDEX IF NOT EXISTS idx_ctg_record_status ON frontier.ctg_study_record(overall_status);
CREATE INDEX IF NOT EXISTS idx_ctg_record_update ON frontier.ctg_study_record(last_update_post_date DESC);

-- Snapshot membership makes run/history explicit instead of overwriting by NCT ID.
CREATE TABLE IF NOT EXISTS frontier.ctg_study_snapshot (
  run_id UUID NOT NULL REFERENCES frontier.ingestion_run(run_id) ON DELETE CASCADE,
  nct_id TEXT NOT NULL,
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key),
  source_data_timestamp TIMESTAMPTZ NOT NULL,
  source_api_version TEXT NOT NULL,
  retrieved_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (run_id, nct_id)
);
CREATE INDEX IF NOT EXISTS idx_ctg_snapshot_nct ON frontier.ctg_study_snapshot(nct_id, source_data_timestamp DESC);

CREATE TABLE IF NOT EXISTS frontier.ctg_phase (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  phase TEXT NOT NULL,
  PRIMARY KEY (canonical_record_key, phase)
);
CREATE TABLE IF NOT EXISTS frontier.ctg_condition (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  condition TEXT NOT NULL,
  PRIMARY KEY (canonical_record_key, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_ctg_condition_text ON frontier.ctg_condition(condition);
CREATE TABLE IF NOT EXISTS frontier.ctg_keyword (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  keyword TEXT NOT NULL,
  PRIMARY KEY (canonical_record_key, ordinal)
);
CREATE TABLE IF NOT EXISTS frontier.ctg_sponsor (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  sponsor_role TEXT NOT NULL CHECK (sponsor_role IN ('lead','collaborator','responsible_party')),
  ordinal INTEGER NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
  name TEXT,
  agency_class TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, sponsor_role, ordinal)
);
CREATE TABLE IF NOT EXISTS frontier.ctg_arm (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  label TEXT,
  arm_type TEXT,
  description TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, ordinal)
);
CREATE TABLE IF NOT EXISTS frontier.ctg_intervention (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  intervention_type TEXT,
  name TEXT,
  description TEXT,
  other_names JSONB NOT NULL DEFAULT '[]'::jsonb,
  arm_group_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_ctg_intervention_name ON frontier.ctg_intervention(name);
CREATE TABLE IF NOT EXISTS frontier.ctg_outcome (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  outcome_type TEXT NOT NULL CHECK (outcome_type IN ('primary','secondary','other')),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  measure TEXT,
  description TEXT,
  time_frame TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, outcome_type, ordinal)
);
CREATE TABLE IF NOT EXISTS frontier.ctg_location (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  facility TEXT,
  status TEXT,
  city TEXT,
  state TEXT,
  zip TEXT,
  country TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_ctg_location_country_state ON frontier.ctg_location(country, state);
CREATE TABLE IF NOT EXISTS frontier.ctg_contact (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  contact_type TEXT NOT NULL CHECK (contact_type IN ('central','official')),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  name TEXT,
  role TEXT,
  affiliation TEXT,
  phone TEXT,
  email TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, contact_type, ordinal)
);
CREATE TABLE IF NOT EXISTS frontier.ctg_reference (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  reference_type TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  pmid TEXT,
  citation TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, reference_type, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_ctg_reference_pmid ON frontier.ctg_reference(pmid) WHERE pmid IS NOT NULL;
CREATE TABLE IF NOT EXISTS frontier.ctg_available_ipd (
  canonical_record_key UUID NOT NULL REFERENCES frontier.ctg_study_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  ipd_type TEXT,
  url TEXT,
  comment TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, ordinal)
);

CREATE OR REPLACE VIEW frontier.ctg_latest_certified AS
SELECT DISTINCT ON (s.nct_id)
  s.nct_id, s.run_id, s.canonical_record_key, s.source_data_timestamp,
  r.*
FROM frontier.ctg_study_snapshot s
JOIN frontier.promotable_run pr ON pr.run_id = s.run_id
JOIN frontier.ctg_study_record r ON r.canonical_record_key = s.canonical_record_key
ORDER BY s.nct_id, s.source_data_timestamp DESC, s.retrieved_at DESC;

-- =========================
-- SILVER: PUBMED
-- =========================
CREATE TABLE IF NOT EXISTS frontier.pubmed_record (
  canonical_record_key UUID PRIMARY KEY REFERENCES frontier.canonical_record(canonical_record_key) ON DELETE CASCADE,
  pmid TEXT NOT NULL,
  record_type TEXT NOT NULL DEFAULT 'journal_article' CHECK (record_type IN ('journal_article','book_article')),
  doi TEXT,
  pmcid TEXT,
  version TEXT,
  title TEXT NOT NULL,
  abstract TEXT NOT NULL DEFAULT '',
  abstract_sections JSONB NOT NULL DEFAULT '[]'::jsonb,
  journal TEXT,
  journal_abbrev TEXT,
  journal_issn TEXT,
  volume TEXT,
  issue TEXT,
  pages TEXT,
  publication_date DATE,
  medline_date TEXT,
  article_date DATE,
  pubmed_dates JSONB NOT NULL DEFAULT '{}'::jsonb,
  date_created TIMESTAMPTZ,
  date_completed TIMESTAMPTZ,
  date_revised TIMESTAMPTZ,
  publication_types JSONB NOT NULL DEFAULT '[]'::jsonb,
  languages JSONB NOT NULL DEFAULT '[]'::jsonb,
  keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
  chemicals JSONB NOT NULL DEFAULT '[]'::jsonb,
  grants JSONB NOT NULL DEFAULT '[]'::jsonb,
  article_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
  references JSONB NOT NULL DEFAULT '[]'::jsonb,
  publication_status TEXT,
  book_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  raw_xml TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pubmed_record_pmid ON frontier.pubmed_record(pmid);
CREATE INDEX IF NOT EXISTS idx_pubmed_record_doi ON frontier.pubmed_record(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pubmed_record_date ON frontier.pubmed_record(publication_date DESC);

CREATE TABLE IF NOT EXISTS frontier.pubmed_snapshot (
  run_id UUID NOT NULL REFERENCES frontier.ingestion_run(run_id) ON DELETE CASCADE,
  pmid TEXT NOT NULL,
  canonical_record_key UUID NOT NULL REFERENCES frontier.pubmed_record(canonical_record_key),
  retrieved_at TIMESTAMPTZ NOT NULL,
  retrieval_queries JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (run_id, pmid)
);
CREATE INDEX IF NOT EXISTS idx_pubmed_snapshot_pmid ON frontier.pubmed_snapshot(pmid, retrieved_at DESC);

CREATE TABLE IF NOT EXISTS frontier.pubmed_author (
  canonical_record_key UUID NOT NULL REFERENCES frontier.pubmed_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  family_name TEXT,
  given_name TEXT,
  initials TEXT,
  collective_name TEXT,
  affiliations JSONB NOT NULL DEFAULT '[]'::jsonb,
  identifiers JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload JSONB NOT NULL,
  PRIMARY KEY (canonical_record_key, ordinal)
);
CREATE TABLE IF NOT EXISTS frontier.pubmed_mesh_heading (
  canonical_record_key UUID NOT NULL REFERENCES frontier.pubmed_record(canonical_record_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  descriptor_name TEXT NOT NULL,
  descriptor_ui TEXT,
  major_topic BOOLEAN NOT NULL DEFAULT FALSE,
  qualifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (canonical_record_key, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_pubmed_mesh_descriptor ON frontier.pubmed_mesh_heading(descriptor_name);

CREATE OR REPLACE VIEW frontier.pubmed_latest_certified AS
SELECT DISTINCT ON (s.pmid)
  s.pmid, s.run_id, s.canonical_record_key, s.retrieved_at, r.*
FROM frontier.pubmed_snapshot s
JOIN frontier.promotable_run pr ON pr.run_id = s.run_id
JOIN frontier.pubmed_record r ON r.canonical_record_key = s.canonical_record_key
ORDER BY s.pmid, s.retrieved_at DESC;

-- =========================
-- SILVER: BIORXIV / MEDRXIV
-- =========================
CREATE TABLE IF NOT EXISTS frontier.preprint_record (
  canonical_record_key UUID PRIMARY KEY REFERENCES frontier.canonical_record(canonical_record_key) ON DELETE CASCADE,
  server TEXT NOT NULL CHECK (server IN ('biorxiv','medrxiv')),
  doi TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version >= 1),
  title TEXT NOT NULL,
  abstract TEXT,
  authors TEXT,
  author_corresponding TEXT,
  author_corresponding_institution TEXT,
  category TEXT,
  posted_date DATE,
  license TEXT,
  published_doi TEXT,
  source_payload JSONB NOT NULL,
  UNIQUE (server, doi, version, canonical_record_key)
);
CREATE INDEX IF NOT EXISTS idx_preprint_identity ON frontier.preprint_record(server, doi, version DESC);

CREATE TABLE IF NOT EXISTS frontier.preprint_snapshot (
  run_id UUID NOT NULL REFERENCES frontier.ingestion_run(run_id) ON DELETE CASCADE,
  server TEXT NOT NULL,
  doi TEXT NOT NULL,
  version INTEGER NOT NULL,
  canonical_record_key UUID NOT NULL REFERENCES frontier.preprint_record(canonical_record_key),
  retrieved_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (run_id, server, doi, version)
);

CREATE OR REPLACE VIEW frontier.preprint_latest_certified AS
SELECT server, doi, version, run_id, canonical_record_key, retrieved_at
FROM (
  SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.server, s.doi ORDER BY s.version DESC, s.retrieved_at DESC) AS rn
  FROM frontier.preprint_snapshot s
  JOIN frontier.promotable_run pr ON pr.run_id = s.run_id
) ranked
WHERE rn = 1;

-- =========================
-- SILVER/GOLD: DRUG SOURCES + CROSSWALK
-- =========================
CREATE TABLE IF NOT EXISTS frontier.drug_source_record (
  canonical_record_key UUID PRIMARY KEY REFERENCES frontier.canonical_record(canonical_record_key) ON DELETE CASCADE,
  source TEXT NOT NULL CHECK (source IN ('drugbank','rxnorm','livertox')),
  source_id TEXT NOT NULL,
  preferred_name TEXT,
  normalized_name TEXT,
  payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drug_source_identity ON frontier.drug_source_record(source, source_id);
CREATE INDEX IF NOT EXISTS idx_drug_source_name ON frontier.drug_source_record(normalized_name);

CREATE TABLE IF NOT EXISTS frontier.drug_candidate (
  candidate_id TEXT PRIMARY KEY CHECK (candidate_id LIKE 'CAND:%'),
  domain TEXT NOT NULL CHECK (domain='drug'),
  source_table TEXT NOT NULL,
  source_key TEXT NOT NULL,
  source_identity_sha256 CHAR(64) NOT NULL UNIQUE,
  origin_package_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state='REGISTERED'),
  legacy_entity_id TEXT,
  source_canonical_record_key UUID NOT NULL REFERENCES frontier.drug_source_record(canonical_record_key),
  preferred_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  automatic_identity_merge_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (automatic_identity_merge_allowed=FALSE),
  automatic_selection_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (automatic_selection_allowed=FALSE),
  canonical_internal_eligible BOOLEAN NOT NULL DEFAULT FALSE CHECK (canonical_internal_eligible=FALSE),
  generation_eligible BOOLEAN NOT NULL DEFAULT FALSE CHECK (generation_eligible=FALSE),
  public_eligible BOOLEAN NOT NULL DEFAULT FALSE CHECK (public_eligible=FALSE),
  UNIQUE(source_table, source_key)
);
CREATE INDEX IF NOT EXISTS idx_drug_candidate_normalized ON frontier.drug_candidate(normalized_name);

CREATE TABLE IF NOT EXISTS frontier.drug_candidate_alias (
  candidate_id TEXT NOT NULL REFERENCES frontier.drug_candidate(candidate_id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  normalized_alias TEXT NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY(candidate_id, normalized_alias, source)
);

CREATE TABLE IF NOT EXISTS frontier.drug_candidate_linkage_evidence (
  linkage_id UUID PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES frontier.drug_candidate(candidate_id),
  canonical_record_key UUID REFERENCES frontier.drug_source_record(canonical_record_key),
  source TEXT NOT NULL,
  source_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('matched','ambiguous','missing','rejected')),
  method TEXT NOT NULL,
  confidence NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence>=0 AND confidence<=1)),
  candidate_count INTEGER NOT NULL DEFAULT 0 CHECK (candidate_count>=0),
  evidence JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

-- =========================
-- GOLD: WORKS, EVIDENCE, ENRICHMENT, RELEASES
-- =========================
-- A work is an analytical entity, never the owner of source identity. Source records
-- remain intact even when DOI/PMID/title evidence suggests they represent the same work.
CREATE TABLE IF NOT EXISTS frontier.research_work (
  work_id UUID PRIMARY KEY,
  preferred_title TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','review','deprecated')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS frontier.work_identifier (
  work_id UUID NOT NULL REFERENCES frontier.research_work(work_id) ON DELETE CASCADE,
  identifier_type TEXT NOT NULL,
  identifier_value TEXT NOT NULL,
  source TEXT,
  PRIMARY KEY (work_id, identifier_type, identifier_value)
);
CREATE INDEX IF NOT EXISTS idx_work_identifier_lookup ON frontier.work_identifier(identifier_type, identifier_value);

CREATE TABLE IF NOT EXISTS frontier.work_source_link (
  work_id UUID NOT NULL REFERENCES frontier.research_work(work_id) ON DELETE CASCADE,
  canonical_record_key UUID NOT NULL REFERENCES frontier.canonical_record(canonical_record_key),
  method TEXT NOT NULL,
  confidence NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  evidence JSONB NOT NULL,
  reviewed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (work_id, canonical_record_key, method)
);

CREATE TABLE IF NOT EXISTS frontier.evidence_link (
  link_id UUID PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  method TEXT NOT NULL,
  confidence NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  run_id UUID REFERENCES frontier.ingestion_run(run_id),
  evidence JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE(subject_type, subject_id, predicate, object_type, object_id, method)
);
CREATE INDEX IF NOT EXISTS idx_evidence_subject ON frontier.evidence_link(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_evidence_object ON frontier.evidence_link(object_type, object_id);

-- Enrichments are downstream, reproducible derivatives. Extraction rows never claim a
-- model/vector until a real model run produced it.
CREATE TABLE IF NOT EXISTS frontier.model_enrichment (
  enrichment_id UUID PRIMARY KEY,
  canonical_record_key UUID NOT NULL REFERENCES frontier.canonical_record(canonical_record_key),
  enrichment_type TEXT NOT NULL,
  model_provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_revision TEXT,
  model_config JSONB NOT NULL DEFAULT '{}'::jsonb,
  input_sha256 CHAR(64) NOT NULL,
  output_sha256 CHAR(64) NOT NULL,
  vector_dimension INTEGER CHECK (vector_dimension IS NULL OR vector_dimension > 0),
  normalized BOOLEAN,
  artifact_locator TEXT,
  certification_status TEXT NOT NULL CHECK (certification_status IN ('PASS','WARN','FAIL')),
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (canonical_record_key, enrichment_type, model_provider, model_name, model_revision, input_sha256)
);
CREATE INDEX IF NOT EXISTS idx_model_enrichment_record ON frontier.model_enrichment(canonical_record_key, enrichment_type);

CREATE TABLE IF NOT EXISTS frontier.release_snapshot (
  release_id UUID PRIMARY KEY,
  label TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('candidate','certified','certified_research_ingestion','superseded','rejected')),
  manifest_sha256 CHAR(64) NOT NULL,
  manifest JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS frontier.release_run (
  release_id UUID NOT NULL REFERENCES frontier.release_snapshot(release_id) ON DELETE CASCADE,
  run_id UUID NOT NULL REFERENCES frontier.ingestion_run(run_id),
  PRIMARY KEY (release_id, run_id)
);
