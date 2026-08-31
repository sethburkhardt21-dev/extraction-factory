
-- BigQuery equivalent partitioned by year for comparison / migration
-- Partitioned + clustered for anesthesia corpus 280k-380k records

CREATE SCHEMA IF NOT EXISTS anesthesia_pubmed OPTIONS (location="US");

CREATE TABLE `anesthesia_pubmed.articles`
(
  pmid INT64 NOT NULL,
  doi STRING,
  doi_normalized STRING,
  pmcid STRING,
  title STRING NOT NULL,
  abstract_text STRING,
  abstract_structured JSON,
  authors JSON, -- ARRAY<STRUCT>
  publication_year INT64 NOT NULL,
  publication_date JSON,
  journal JSON,
  mesh_terms JSON, -- repeated
  keywords ARRAY<STRING>,
  publication_types ARRAY<STRING>,
  chemicals JSON,
  anesthesia_subdomains ARRAY<STRING>,
  study_design JSON,
  anesthesia_specific JSON,
  citation_metrics JSON,
  extraction_metadata JSON,
  ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY RANGE_BUCKET(publication_year, GENERATE_ARRAY(1960, 2030, 1))
CLUSTER BY anesthesia_subdomains, publication_types
OPTIONS (
  description="Max anesthesia PubMed 16-agent swarm, DOI normalized, MedlineDate fallback handled",
  require_partition_filter=false
);

-- GIN equivalent in BigQuery is SEARCH INDEX
CREATE SEARCH INDEX idx_title_search ON `anesthesia_pubmed.articles` (title);
CREATE SEARCH INDEX idx_abstract_search ON `anesthesia_pubmed.articles` (abstract_text);
