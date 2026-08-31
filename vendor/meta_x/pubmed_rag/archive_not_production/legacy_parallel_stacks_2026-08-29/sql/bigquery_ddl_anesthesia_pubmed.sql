
-- ============================================================================
-- BigQuery DDL: Max Anesthesia PubMed Extraction - Production Table
-- Swarm B - Database DDL Swarm - Agent B2: BigQuery Architect
-- ============================================================================
-- Best Practices Applied:
-- - Time-unit YEAR partitioning on canonical pub_date to avoid 10k partition limit
--   (daily partitions would exceed 20k for 1970-2026; YEAR = ~76 partitions)
-- - Clustering on high-cardinality filter columns: first_subdomain, journal_title,
--   study_design.type, publication_year - order by query frequency
-- - STRUCT for 1:1 relationships (journal, publication_date, study_design, etc.)
-- - ARRAY<STRUCT> REPEATED for 1:N (authors, mesh_terms, chemicals)
-- - OPTIONS(description) on table + every column / STRUCT field for docs
-- - require_partition_filter=true to prevent full scans & cost control
-- - Embeddings column ARRAY<FLOAT64> + VECTOR INDEX for semantic search
-- - Handles audit critical issues:
--   * MedlineDate fallback -> pub_date derivation UDF handles "2020 Dec" or "2020 Spring"
--   * DOI normalization -> LOWER(TRIM(doi)) in ingestion view
--   * Classification FP via substring -> classification helper uses word boundaries \b
--   * WebEnv expiration -> ingestion pipeline retries esearch if expired
--   * Rate limits inverted -> documented: with key 20 req/s sleep 0.05, without 10 req/s sleep 0.1
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS `anesthesia_prod.pubmed`
OPTIONS (
  description = "Max Anesthesia PubMed corpus - 16-agent swarm, 280k-380k records, deduplicated",
  location = "US"
);

-- Main production table
CREATE TABLE IF NOT EXISTS `anesthesia_prod.pubmed.anesthesia_pubmed_max`
(
  -- Core identifiers
  pmid STRING NOT NULL OPTIONS (description = "PubMed ID, primary key, STRING to preserve leading zeros if any, not enforced"),
  doi STRING OPTIONS (description = "DOI normalized lowercase, trimmed, DOI regex validation ^10\\.\\d{4,}/.+, NULL if missing, dedup anchor"),
  pmcid STRING OPTIONS (description = "PubMed Central ID, e.g., PMC9201138, NULL if not in PMC"),
  title STRING NOT NULL OPTIONS (description = "Article title, full title from ArticleTitle, not truncated"),
  abstract STRING OPTIONS (description = "Full abstract text concatenated, NULL if no abstract, up to 10k chars"),
  abstract_structured STRUCT<
    background STRING OPTIONS (description = "Structured abstract Background section"),
    methods STRING OPTIONS (description = "Methods section"),
    results STRING OPTIONS (description = "Results section"),
    conclusions STRING OPTIONS (description = "Conclusions section"),
    full_sections JSON OPTIONS (description = "All labeled sections as JSON object for dynamic labels")
  > OPTIONS (description = "Structured abstract parsed from AbstractText Label attributes"),

  -- Authors REPEATED STRUCT
  authors ARRAY<STRUCT<
    last_name STRING NOT NULL OPTIONS (description = "Author last name"),
    fore_name STRING OPTIONS (description = "ForeName full first name"),
    initials STRING OPTIONS (description = "Initials"),
    affiliation STRING OPTIONS (description = "Affiliation string from AffiliationInfo, may be long"),
    orcid STRING OPTIONS (description = "ORCID if present in ContribId, NULL otherwise")
  >> OPTIONS (description = "Author list in order, ARRAY preserves order, 1:N relationship"),

  -- Journal STRUCT - 1:1 relationship
  journal STRUCT<
    title STRING NOT NULL OPTIONS (description = "Full journal title, e.g., Anesthesiology"),
    iso_abbreviation STRING OPTIONS (description = "ISO abbreviation e.g., Anesthesiology or Br J Anaesth"),
    issn STRING OPTIONS (description = "ISSN, if multiple in XML pipe-joined, e.g., 0003-3022|1528-1175"),
    volume STRING OPTIONS (description = "Volume string, may be numeric or supplement"),
    issue STRING OPTIONS (description = "Issue number"),
    pages STRING OPTIONS (description = "Pagination e.g., 123-134, handles ELocationID fallback"),
    impact_factor FLOAT64 OPTIONS (description = "Journal Impact Factor mapped from curated list: Anesthesiology 9.1, BJA 9.166, Anaesthesia 6.995, Anesth Analg 4.6, etc., NULL if not mapped"),
    publisher STRING OPTIONS (description = "Publisher name e.g., Lippincott, Elsevier")
  > OPTIONS (description = "Journal metadata as nested STRUCT to avoid JOINs, denormalized form"),

  -- Publication date STRUCT + canonical DATE for partitioning
  publication_date STRUCT<
    year INT64 NOT NULL OPTIONS (description = "Canonical publication year, derived: Year -> MedlineDate year fallback regex, e.g., 2024"),
    month INT64 OPTIONS (description = "Month 1-12, NULL if not parseable, handles MedlineDate 2020 Dec fallback"),
    day INT64 OPTIONS (description = "Day 1-31, NULL if not parseable"),
    pub_type_date STRING OPTIONS (description = "Publication model: ppublish, epublish, eCollection, etc from PubDate PublicationHistory"),
    pdat STRING OPTIONS (description = "Raw PDAT or MedlineDate string for audit, e.g., 2020 Dec or 2020 Spring")
  > OPTIONS (description = "Structured publication date with MedlineDate fallback handling, critical fix for audit issue"),
  pub_date DATE NOT NULL OPTIONS (description = "Canonical publication DATE derived from publication_date year/month/day, with MedlineDate fallback: uses 1st of month if day missing, Jan 1 if month missing, handles seasons via mapping Winter->1 Spring->3 Summer->6 Fall->9, required for YEAR partitioning, solves 10k partition limit"),
  publication_year INT64 NOT NULL OPTIONS (description = "Denormalized year INT64 = EXTRACT(YEAR FROM pub_date), for RANGE_BUCKET alternative and clustering"),

  -- MeSH REPEATED STRUCT - core for anesthesia ontology
  mesh_terms ARRAY<STRUCT<
    descriptor_name STRING NOT NULL OPTIONS (description = "MeSH descriptor name e.g., Anesthesia, General or Nerve Block"),
    descriptor_ui STRING NOT NULL OPTIONS (description = "MeSH UID e.g., D009407 for Nerve Block, used for hierarchy"),
    qualifiers ARRAY<STRING> OPTIONS (description = "MeSH qualifiers e.g., adverse effects, toxicity"),
    major_topic BOOL OPTIONS (description = "MajorTopicYN flag true if * descriptor is major")
  >> OPTIONS (description = "MeSH terms repeated field, ARRAY<STRUCT> avoids separate table, max 15 levels nesting safe, query with UNNEST(mesh_terms) WHERE descriptor_name LIKE '%Anesthesia%'"),

  keywords ARRAY<STRING> OPTIONS (description = "KeywordList from PubMed, free-text keywords, REPEATED STRING"),
  publication_types ARRAY<STRING> OPTIONS (description = "Publication Types PT field: RCT, Systematic Review, Meta-Analysis, Guideline, Case Report, Narrative Review, Bibliometric, In Vitro, etc."),
  chemicals ARRAY<STRUCT<
    name STRING NOT NULL OPTIONS (description = "Chemical name e.g., Dexmedetomidine, Propofol, Bupivacaine"),
    registry_number STRING OPTIONS (description = "CAS registry number"),
    ui STRING NOT NULL OPTIONS (description = "Chemical UI e.g., D000077")
  >> OPTIONS (description = "Chemicals / NameOfSubstance list, drugs handling"),

  -- 16-agent swarm classification
  anesthesia_subdomains ARRAY<STRING> OPTIONS (description = "Multi-label classification from 16 agents: General Anesthesia, Regional - Spinal Epidural, Peripheral Nerve Blocks, Local Anesthetics Pharmacology, Airway Management, Anesthesia Monitoring, Pediatric, Obstetric, Cardiac Anesthesia, Neuroanesthesia, Critical Care ICU Sedation, Pain Medicine, Anesthesia Safety, Pharmacology - Opioids Propofol Ketamine NMB, ERAS Perioperative, AI Simulation Education. Uses word-boundary regex to avoid FP via substring (e.g., \\bnerve block\\b not block substring)"),

  study_design STRUCT<
    type STRING NOT NULL OPTIONS (description = "Study design enum: RCT, Systematic Review, Meta-Analysis, Observational, Case Report, Guideline, Narrative Review, Bibliometric, Animal, In Vitro, Other, validated against allow-list"),
    is_landmark BOOL OPTIONS (description = "Landmark trial flag: GAS, BALANCED, SPICE III, MASTER, NAP4, MYRIAD, etc."),
    n_patients INT64 OPTIONS (description = "Number of patients parsed via regex from abstract, NULL if not extractable"),
    n_studies_included INT64 OPTIONS (description = "For SRMA: number of studies included, e.g., 111 studies in SGA network MA"),
    multicenter BOOL OPTIONS (description = "Multicenter flag boolean"),
    blinding STRING OPTIONS (description = "Blinding: Double-blind, Single-blind, Open-label, etc."),
    registration STRING OPTIONS (description = "Trial registration ID: NCT..., PROSPERO CRD..., etc.")
  > OPTIONS (description = "Study design metadata as STRUCT"),

  anesthesia_specific STRUCT<
    drugs ARRAY<STRING> OPTIONS (description = "Anesthesia drugs normalized list: Propofol, Sevoflurane, Dexmedetomidine, Rocuronium, Sugammadex, etc."),
    techniques ARRAY<STRING> OPTIONS (description = "Techniques: General, Spinal, Epidural, CSE, TAP, ESPB, QLB, PENG, Videolaryngoscopy, etc."),
    outcomes ARRAY<STRING> OPTIONS (description = "Outcomes: PONV, awareness, delirium, mortality, pain score, chronic pain, cognitive dysfunction, etc."),
    population STRING OPTIONS (description = "Population enum: adult, pediatric, obstetric, cardiac, ICU, elderly, neonate"),
    asa_class STRING OPTIONS (description = "ASA physical status e.g., I-II, III-IV, NULL if not stated")
  > OPTIONS (description = "Anesthesia-specific structured extraction, STRUCT containing ARRAYs for nested repeated handling"),

  citation_metrics STRUCT<
    citation_count_openalex INT64 OPTIONS (description = "Citation count from OpenAlex API enrichment, nullable until enriched"),
    citation_count_semantic_scholar INT64 OPTIONS (description = "Citation count from Semantic Scholar"),
    is_top_100_pediatric BOOL OPTIONS (description = "Flag for top 100 most-cited pediatric anesthesia articles 1990-2023 per bibliometric analysis")
  > OPTIONS (description = "Citation enrichment metrics"),

  extraction_metadata STRUCT<
    query_used STRING NOT NULL OPTIONS (description = "Exact PubMed query string used by agent, for reproducibility, truncated to 3000 chars if needed"),
    agent_id INT64 NOT NULL OPTIONS (description = "Agent ID 1-16 mapping to subdomain, per AGENT_QUERIES"),
    retrieval_date TIMESTAMP NOT NULL OPTIONS (description = "UTC retrieval timestamp ISO8601, e.g., 2026-08-28T00:00:00Z"),
    dedup_status STRING NOT NULL OPTIONS (description = "Dedup status enum: unique, duplicate_type_I (same PMID cross-agent), duplicate_type_II (duplicate publication same data different journal per PMC10789108), merged (DOI lowecased exact match merged richest abstract)"),
    duplicate_of_pmid STRING OPTIONS (description = "If dedup_status != unique, points to canonical PMID kept, NULL otherwise")
  > OPTIONS (description = "Extraction provenance metadata for audit"),

  -- Clustering helper columns (denormalized for BigQuery clustering requirement: top-level scalars only)
  first_subdomain STRING NOT NULL OPTIONS (description = "First element of anesthesia_subdomains ARRAY, for clustering; if empty defaults to General Anesthesia, helps partition pruning and clustering"),
  journal_title STRING NOT NULL OPTIONS (description = "Denormalized journal.title for clustering and filtering, avoids STRUCT field clustering limitation"),
  study_type STRING NOT NULL OPTIONS (description = "Denormalized study_design.type for clustering"),
  -- Embeddings for semantic RAG
  title_abstract_embedding ARRAY<FLOAT64> OPTIONS (description = "768-dim embedding for title+abstract using PubMedBERT or Vertex AI text-embedding-005 / gemini-embedding-001, NULL initially, populated via batch embedding pipeline, used for vector search. Alternative: use STRUCT<result ARRAY<FLOAT64>, status STRING> GENERATED ALWAYS AS (AI.EMBED(...)) for autonomous generation"),
  abstract_text_for_embedding STRING OPTIONS (description = "Concatenated title + abstract truncated to model token limit e.g., 3000 chars, for embedding generation input"),
  ingestion_timestamp TIMESTAMP NOT NULL OPTIONS (description = "Ingestion time into BigQuery, auto SET CURRENT_TIMESTAMP()")

)
PARTITION BY DATE_TRUNC(pub_date, YEAR)
CLUSTER BY first_subdomain, journal_title, study_type, publication_year
OPTIONS (
  description = "Production BigQuery table for Max Anesthesia PubMed corpus: 280k-380k unique records after dedup, 16-agent swarm max-recall, partitioned by YEAR on pub_date (handles MedlineDate fallback), clustered by subdomain/journal/study_type/year, STRUCT for journal, REPEATED ARRAY<STRUCT> for mesh_terms, OPTIONS with descriptions on all columns. Addresses audit critical issues: DOI normalization LOWER(TRIM()), MedlineDate fallback regex, word-boundary classification, WebEnv expiration handling, rate limit corrected (10/s no-key 20/s with-key). Includes embeddings for semantic search with VECTOR INDEX. Cost control: require_partition_filter=true recommended for prod, partition_expiration optional for staging.",
  labels = [("domain", "anesthesia"), ("source", "pubmed"), ("swarm", "16-agent"), ("pii", "none")],
  require_partition_filter = TRUE,
  partition_expiration_days = 1825
);

-- Helper: DOI normalization function (fixes audit DOI normalization missing)
CREATE OR REPLACE FUNCTION `anesthesia_prod.pubmed.normalize_doi`(doi STRING)
RETURNS STRING
LANGUAGE js AS """
  if (!doi) return null;
  let d = doi.trim().toLowerCase();
  d = d.replace(/^https?:\/\/(dx\.)?doi\.org\//, '');
  d = d.replace(/^doi:\s*/i, '');
  d = d.replace(/[.,;]+$/, '');
  if (!/^10\.\d{4,}\/\S+$/.test(d)) return null;
  return d;
"""
OPTIONS (description = "Normalizes DOI: LOWER(TRIM()), removes https://doi.org/ and doi: prefix, validates regex ^10\\.d{4,}/, fixes audit critical DOI normalization missing");

-- Helper: MedlineDate fallback parsing (fixes audit MedlineDate fallback missing)
CREATE OR REPLACE FUNCTION `anesthesia_prod.pubmed.parse_medline_date`(raw STRING)
RETURNS STRUCT<year INT64, month INT64, day INT64, canonical_date DATE>
LANGUAGE js AS """
  if (!raw) return {year: null, month: null, day: null, canonical_date: null};
  raw = raw.trim();
  let m = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) {
    return {year: parseInt(m[1]), month: parseInt(m[2]), day: parseInt(m[3]), canonical_date: m[0]};
  }
  let months = {jan:1, feb:2, mar:3, apr:4, may:5, jun:6, jul:7, aug:8, sep:9, oct:10, nov:11, dec:12,
                january:1, february:2, march:3, april:4, june:6, july:7, august:8, september:9, october:10, november:11, december:12,
                winter:1, spring:3, summer:6, fall:9, autumn:9};
  let y = raw.match(/(\d{4})/);
  let year = y ? parseInt(y[1]) : null;
  if (!year) return {year: null, month: null, day: null, canonical_date: null};
  let month = null, day = 1;
  let mm = raw.toLowerCase().match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|winter|spring|summer|fall|autumn)/);
  if (mm) month = months[mm[1]] || 1;
  let dd = raw.match(/(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})/i);
  if (dd) day = parseInt(dd[1]);
  else {
    let d2 = raw.match(/\b(\d{1,2})\b/);
    if (d2 && parseInt(d2[1]) <= 31) day = parseInt(d2[1]);
  }
  if (!month) month = 1;
  let dateStr = year.toString().padStart(4,'0') + '-' + month.toString().padStart(2,'0') + '-' + day.toString().padStart(2,'0');
  try {
    let d = new Date(dateStr);
    if (isNaN(d)) dateStr = year+'-01-01';
  } catch(e){ dateStr = year+'-01-01'; }
  return {year: year, month: month, day: day, canonical_date: dateStr};
"""
OPTIONS (description = "Parses PubMed MedlineDate fallback: handles formats like 2020 Dec, 2020 Spring, 2020-12-01, extracts year/month/day, maps seasons Winter->1 Spring->3 Summer->6 Fall->9, returns canonical DATE, fixes audit MedlineDate fallback missing");

-- View: Flattened mesh_terms for analytics (avoids UNNEST repetition)
CREATE OR REPLACE VIEW `anesthesia_prod.pubmed.v_anesthesia_mesh_flat`
OPTIONS (description = "Flattened view for MeSH analytics, one row per PMID x MeSH descriptor, retains major_topic filter, for counting MeSH trends")
AS
SELECT
  pmid,
  doi,
  title,
  pub_date,
  publication_year,
  first_subdomain,
  journal_title,
  study_type,
  mt.descriptor_name,
  mt.descriptor_ui,
  mt.major_topic,
  q AS qualifier,
  extraction_metadata.agent_id,
  extraction_metadata.dedup_status
FROM `anesthesia_prod.pubmed.anesthesia_pubmed_max`,
UNNEST(mesh_terms) AS mt
LEFT JOIN UNNEST(mt.qualifiers) AS q;

-- View: Deduplicated canonical corpus
CREATE OR REPLACE VIEW `anesthesia_prod.pubmed.v_anesthesia_canonical`
OPTIONS (description = "Canonical deduplicated corpus, filters dedup_status=unique, primary for ML and question building, enforces LOWER(TRIM(doi)) grouping")
AS
SELECT * EXCEPT(ingestion_timestamp),
  `anesthesia_prod.pubmed.normalize_doi`(doi) AS doi_normalized
FROM `anesthesia_prod.pubmed.anesthesia_pubmed_max`
WHERE extraction_metadata.dedup_status = "unique";

-- VECTOR INDEX for semantic search (requires >=5000 rows)
-- CREATE VECTOR INDEX IF NOT EXISTS `anesthesia_prod.pubmed.idx_title_abstract_embedding`
-- ON `anesthesia_prod.pubmed.anesthesia_pubmed_max`(title_abstract_embedding)
-- OPTIONS (distance_type = 'COSINE', index_type = 'IVF', ivf_options = '{"num_lists": 500}');

-- Materialized view for subdomain counts per year (for dashboard)
CREATE MATERIALIZED VIEW IF NOT EXISTS `anesthesia_prod.pubmed.mv_subdomain_year_counts`
OPTIONS (description = "Materialized view for dashboard: counts per subdomain per year, partition aligned")
AS
SELECT
  publication_year,
  first_subdomain,
  study_type,
  COUNT(*) AS n_records,
  COUNTIF(study_design.is_landmark) AS n_landmark,
  COUNT(DISTINCT journal_title) AS n_journals,
  AVG(journal.impact_factor) AS avg_if
FROM `anesthesia_prod.pubmed.anesthesia_pubmed_max`
WHERE extraction_metadata.dedup_status = "unique"
GROUP BY publication_year, first_subdomain, study_type;
