-- Frontier Research Warehouse - BigQuery schema v2.0
-- Execute with a default project selected. Dataset name: frontier.
-- BigQuery favors nested analytical records while preserving the same Bronze/Silver/Gold identities.

CREATE SCHEMA IF NOT EXISTS frontier;

CREATE TABLE IF NOT EXISTS frontier.ingestion_run (
  run_id STRING NOT NULL,
  source STRING NOT NULL,
  mode STRING NOT NULL,
  parser_version STRING NOT NULL,
  canonical_schema_version STRING NOT NULL,
  manifest_schema_version STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  status STRING NOT NULL,
  certification_status STRING NOT NULL,
  source_version_start STRING,
  source_version_end STRING,
  source_changed_during_run BOOL,
  query JSON,
  query_fingerprint STRING,
  expected_records INT64,
  observed_records INT64 NOT NULL,
  valid_records INT64 NOT NULL,
  quarantined_records INT64 NOT NULL,
  unique_records INT64 NOT NULL,
  truncated BOOL NOT NULL,
  complete_against_source BOOL,
  raw_sha256 STRING,
  canonical_sha256 STRING,
  quarantine_sha256 STRING,
  provenance_sha256 STRING,
  warnings JSON,
  errors JSON,
  artifacts JSON,
  manifest JSON NOT NULL
)
PARTITION BY DATE(started_at)
CLUSTER BY source, certification_status, status;

CREATE TABLE IF NOT EXISTS frontier.run_artifact (
  artifact_id STRING NOT NULL,
  run_id STRING NOT NULL,
  role STRING NOT NULL,
  locator STRING NOT NULL,
  media_type STRING,
  sha256 STRING NOT NULL,
  byte_size INT64,
  record_count INT64,
  created_at TIMESTAMP NOT NULL,
  metadata JSON
)
PARTITION BY DATE(created_at)
CLUSTER BY run_id, role;

CREATE TABLE IF NOT EXISTS frontier.source_record (
  source_record_key STRING NOT NULL,
  source STRING NOT NULL,
  source_record_id STRING NOT NULL,
  source_version_id STRING NOT NULL,
  source_record_sha256 STRING NOT NULL,
  first_seen_at TIMESTAMP NOT NULL,
  source_url STRING,
  metadata JSON
)
PARTITION BY DATE(first_seen_at)
CLUSTER BY source, source_record_id;

CREATE TABLE IF NOT EXISTS frontier.source_observation (
  run_id STRING NOT NULL,
  source_record_key STRING NOT NULL,
  retrieved_at TIMESTAMP NOT NULL,
  source_version STRING,
  source_updated_at TIMESTAMP,
  raw_locator STRING,
  transport_raw_locators ARRAY<STRING>,
  parse_status STRING NOT NULL,
  parse_warnings JSON,
  provenance_schema_version STRING NOT NULL,
  provenance JSON NOT NULL
)
PARTITION BY DATE(retrieved_at)
CLUSTER BY run_id, source_record_key, parse_status;

CREATE TABLE IF NOT EXISTS frontier.canonical_record (
  canonical_record_key STRING NOT NULL,
  source_record_key STRING NOT NULL,
  parser_version STRING NOT NULL,
  canonical_schema_version STRING NOT NULL,
  canonical_sha256 STRING NOT NULL,
  canonical_locator STRING,
  created_at TIMESTAMP NOT NULL,
  validation_status STRING NOT NULL,
  validation_warnings JSON
)
PARTITION BY DATE(created_at)
CLUSTER BY canonical_schema_version, parser_version, source_record_key;

CREATE TABLE IF NOT EXISTS frontier.quarantine_record (
  quarantine_id STRING NOT NULL,
  run_id STRING NOT NULL,
  source STRING NOT NULL,
  source_record_id STRING,
  source_record_sha256 STRING,
  archive_member STRING,
  raw_locator STRING,
  raw_payload JSON,
  raw_text STRING,
  raw_base64 STRING,
  error_type STRING NOT NULL,
  error_message STRING NOT NULL,
  quarantined_at TIMESTAMP NOT NULL,
  metadata JSON
)
PARTITION BY DATE(quarantined_at)
CLUSTER BY source, run_id, error_type;

-- ClinicalTrials.gov canonical content. Arrays are nested for BigQuery scan efficiency.
CREATE TABLE IF NOT EXISTS frontier.ctg_study_record (
  canonical_record_key STRING NOT NULL,
  nct_id STRING NOT NULL,
  brief_title STRING NOT NULL,
  official_title STRING,
  acronym STRING,
  nct_id_aliases ARRAY<STRING>,
  org_study_id_info JSON,
  secondary_id_infos JSON,
  organization JSON,
  brief_summary STRING,
  detailed_description STRING,
  overall_status STRING,
  why_stopped STRING,
  expanded_access_info JSON,
  phases ARRAY<STRING>,
  study_type STRING,
  design JSON,
  enrollment_count INT64,
  enrollment_type STRING,
  conditions ARRAY<STRING>,
  keywords ARRAY<STRING>,
  sponsors JSON,
  start_date DATE,
  start_date_type STRING,
  primary_completion_date DATE,
  primary_completion_date_type STRING,
  completion_date DATE,
  completion_date_type STRING,
  study_first_submit_date DATE,
  study_first_post_date DATE,
  last_update_submit_date DATE,
  last_update_post_date DATE,
  last_update_post_date_type STRING,
  eligibility JSON,
  arms JSON,
  interventions JSON,
  contacts JSON,
  locations JSON,
  primary_outcomes JSON,
  secondary_outcomes JSON,
  other_outcomes JSON,
  references JSON,
  see_also_links JSON,
  available_ipds JSON,
  ipd_sharing JSON,
  oversight JSON,
  has_results BOOL,
  is_fda_regulated_drug BOOL,
  is_fda_regulated_device BOOL,
  protocol_raw JSON NOT NULL,
  results_raw JSON,
  annotation_raw JSON,
  document_raw JSON,
  derived_raw JSON
)
CLUSTER BY nct_id, overall_status, study_type;

CREATE TABLE IF NOT EXISTS frontier.ctg_study_snapshot (
  run_id STRING NOT NULL,
  nct_id STRING NOT NULL,
  canonical_record_key STRING NOT NULL,
  source_data_timestamp TIMESTAMP NOT NULL,
  source_api_version STRING NOT NULL,
  retrieved_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(source_data_timestamp)
CLUSTER BY nct_id, run_id;

-- ClinicalTrials.gov normalized child projections.
CREATE TABLE IF NOT EXISTS frontier.ctg_phase (
  canonical_record_key STRING NOT NULL,
  phase STRING NOT NULL
)
CLUSTER BY canonical_record_key, phase;

CREATE TABLE IF NOT EXISTS frontier.ctg_condition (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  condition STRING NOT NULL
)
CLUSTER BY condition, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_keyword (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  keyword STRING NOT NULL
)
CLUSTER BY canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_sponsor (
  canonical_record_key STRING NOT NULL,
  sponsor_role STRING NOT NULL,
  ordinal INT64 NOT NULL,
  name STRING,
  agency_class STRING,
  payload JSON NOT NULL
)
CLUSTER BY sponsor_role, name, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_arm (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  label STRING,
  arm_type STRING,
  description STRING,
  payload JSON NOT NULL
)
CLUSTER BY canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_intervention (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  intervention_type STRING,
  name STRING,
  description STRING,
  other_names ARRAY<STRING>,
  arm_group_labels ARRAY<STRING>,
  payload JSON NOT NULL
)
CLUSTER BY name, intervention_type, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_outcome (
  canonical_record_key STRING NOT NULL,
  outcome_type STRING NOT NULL,
  ordinal INT64 NOT NULL,
  measure STRING,
  description STRING,
  time_frame STRING,
  payload JSON NOT NULL
)
CLUSTER BY outcome_type, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_location (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  facility STRING,
  status STRING,
  city STRING,
  state STRING,
  zip STRING,
  country STRING,
  latitude FLOAT64,
  longitude FLOAT64,
  payload JSON NOT NULL
)
CLUSTER BY country, state, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_contact (
  canonical_record_key STRING NOT NULL,
  contact_type STRING NOT NULL,
  ordinal INT64 NOT NULL,
  name STRING,
  role STRING,
  affiliation STRING,
  phone STRING,
  email STRING,
  payload JSON NOT NULL
)
CLUSTER BY contact_type, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_reference (
  canonical_record_key STRING NOT NULL,
  reference_type STRING NOT NULL,
  ordinal INT64 NOT NULL,
  pmid STRING,
  citation STRING,
  payload JSON NOT NULL
)
CLUSTER BY pmid, reference_type, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.ctg_available_ipd (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  ipd_type STRING,
  url STRING,
  comment STRING,
  payload JSON NOT NULL
)
CLUSTER BY canonical_record_key;

-- PubMed: full source metadata, but no embedding/model claims in extraction rows.
CREATE TABLE IF NOT EXISTS frontier.pubmed_record (
  canonical_record_key STRING NOT NULL,
  pmid STRING NOT NULL,
  record_type STRING NOT NULL,
  doi STRING,
  pmcid STRING,
  version STRING,
  title STRING NOT NULL,
  abstract STRING,
  abstract_sections JSON,
  authors ARRAY<STRUCT<
    ordinal INT64,
    family_name STRING,
    given_name STRING,
    initials STRING,
    collective_name STRING,
    affiliations ARRAY<STRING>,
    identifiers JSON
  >>,
  journal STRING,
  journal_abbrev STRING,
  journal_issn STRING,
  volume STRING,
  issue STRING,
  pages STRING,
  publication_date DATE,
  medline_date STRING,
  article_date DATE,
  pubmed_dates JSON,
  date_created TIMESTAMP,
  date_completed TIMESTAMP,
  date_revised TIMESTAMP,
  publication_types ARRAY<STRING>,
  languages ARRAY<STRING>,
  keywords ARRAY<STRING>,
  mesh_headings JSON,
  chemicals JSON,
  grants JSON,
  article_ids JSON,
  references JSON,
  publication_status STRING,
  book_metadata JSON,
  raw_xml STRING NOT NULL
)
CLUSTER BY pmid, doi, journal;

CREATE TABLE IF NOT EXISTS frontier.pubmed_snapshot (
  run_id STRING NOT NULL,
  pmid STRING NOT NULL,
  canonical_record_key STRING NOT NULL,
  retrieved_at TIMESTAMP NOT NULL,
  retrieval_queries ARRAY<STRING>
)
PARTITION BY DATE(retrieved_at)
CLUSTER BY pmid, run_id;

CREATE TABLE IF NOT EXISTS frontier.pubmed_author (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  family_name STRING,
  given_name STRING,
  initials STRING,
  collective_name STRING,
  affiliations ARRAY<STRING>,
  identifiers JSON,
  payload JSON NOT NULL
)
CLUSTER BY canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.pubmed_mesh_heading (
  canonical_record_key STRING NOT NULL,
  ordinal INT64 NOT NULL,
  descriptor_name STRING,
  descriptor_ui STRING,
  major_topic BOOL NOT NULL,
  qualifiers JSON NOT NULL
)
CLUSTER BY descriptor_name, canonical_record_key;

CREATE TABLE IF NOT EXISTS frontier.preprint_record (
  canonical_record_key STRING NOT NULL,
  server STRING NOT NULL,
  doi STRING NOT NULL,
  version INT64 NOT NULL,
  title STRING NOT NULL,
  abstract STRING,
  authors STRING,
  author_corresponding STRING,
  author_corresponding_institution STRING,
  category STRING,
  posted_date DATE,
  license STRING,
  published_doi STRING,
  source_payload JSON NOT NULL
)
CLUSTER BY server, doi, version;

CREATE TABLE IF NOT EXISTS frontier.preprint_snapshot (
  run_id STRING NOT NULL,
  server STRING NOT NULL,
  doi STRING NOT NULL,
  version INT64 NOT NULL,
  canonical_record_key STRING NOT NULL,
  retrieved_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(retrieved_at)
CLUSTER BY server, doi, run_id;

CREATE TABLE IF NOT EXISTS frontier.drug_source_record (
  canonical_record_key STRING NOT NULL,
  source STRING NOT NULL,
  source_id STRING NOT NULL,
  preferred_name STRING,
  normalized_name STRING,
  payload JSON NOT NULL
)
CLUSTER BY source, source_id, normalized_name;

CREATE TABLE IF NOT EXISTS frontier.drug_candidate (
  candidate_id STRING NOT NULL,
  domain STRING NOT NULL,
  source_table STRING NOT NULL,
  source_key STRING NOT NULL,
  source_identity_sha256 STRING NOT NULL,
  origin_package_id STRING NOT NULL,
  state STRING NOT NULL,
  legacy_entity_id STRING,
  source_canonical_record_key STRING NOT NULL,
  preferred_name STRING NOT NULL,
  normalized_name STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  automatic_identity_merge_allowed BOOL NOT NULL,
  automatic_selection_allowed BOOL NOT NULL,
  canonical_internal_eligible BOOL NOT NULL,
  generation_eligible BOOL NOT NULL,
  public_eligible BOOL NOT NULL
)
CLUSTER BY normalized_name, state, candidate_id;

CREATE TABLE IF NOT EXISTS frontier.drug_candidate_alias (
  candidate_id STRING NOT NULL,
  alias STRING NOT NULL,
  normalized_alias STRING NOT NULL,
  source STRING NOT NULL
)
CLUSTER BY normalized_alias, source, candidate_id;

CREATE TABLE IF NOT EXISTS frontier.drug_candidate_linkage_evidence (
  linkage_id STRING NOT NULL,
  candidate_id STRING NOT NULL,
  canonical_record_key STRING,
  source STRING NOT NULL,
  source_id STRING,
  status STRING NOT NULL,
  method STRING NOT NULL,
  confidence FLOAT64,
  candidate_count INT64 NOT NULL,
  evidence JSON NOT NULL,
  created_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY source, status, candidate_id;

CREATE TABLE IF NOT EXISTS frontier.research_work (
  work_id STRING NOT NULL,
  preferred_title STRING,
  created_at TIMESTAMP NOT NULL,
  status STRING NOT NULL,
  metadata JSON
)
PARTITION BY DATE(created_at)
CLUSTER BY status;

CREATE TABLE IF NOT EXISTS frontier.work_identifier (
  work_id STRING NOT NULL,
  identifier_type STRING NOT NULL,
  identifier_value STRING NOT NULL,
  source STRING
)
CLUSTER BY identifier_type, identifier_value, work_id;

CREATE TABLE IF NOT EXISTS frontier.work_source_link (
  work_id STRING NOT NULL,
  canonical_record_key STRING NOT NULL,
  method STRING NOT NULL,
  confidence FLOAT64,
  evidence JSON NOT NULL,
  reviewed BOOL NOT NULL,
  created_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY work_id, method;

CREATE TABLE IF NOT EXISTS frontier.evidence_link (
  link_id STRING NOT NULL,
  subject_type STRING NOT NULL,
  subject_id STRING NOT NULL,
  predicate STRING NOT NULL,
  object_type STRING NOT NULL,
  object_id STRING NOT NULL,
  method STRING NOT NULL,
  confidence FLOAT64,
  run_id STRING,
  evidence JSON NOT NULL,
  created_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY subject_type, object_type, predicate, method;

CREATE TABLE IF NOT EXISTS frontier.model_enrichment (
  enrichment_id STRING NOT NULL,
  canonical_record_key STRING NOT NULL,
  enrichment_type STRING NOT NULL,
  model_provider STRING NOT NULL,
  model_name STRING NOT NULL,
  model_revision STRING,
  model_config JSON,
  input_sha256 STRING NOT NULL,
  output_sha256 STRING NOT NULL,
  vector_dimension INT64,
  normalized BOOL,
  artifact_locator STRING,
  certification_status STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY enrichment_type, model_provider, model_name, certification_status;

CREATE TABLE IF NOT EXISTS frontier.release_snapshot (
  release_id STRING NOT NULL,
  label STRING NOT NULL,
  schema_version STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  status STRING NOT NULL,
  manifest_sha256 STRING NOT NULL,
  manifest JSON NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY status, schema_version;

CREATE TABLE IF NOT EXISTS frontier.release_run (
  release_id STRING NOT NULL,
  run_id STRING NOT NULL
)
CLUSTER BY release_id, run_id;
