
-- BigQuery alternative DDL for same corpus 280k-380k
CREATE SCHEMA IF NOT EXISTS anesthesia_dataset
OPTIONS(location="US");

CREATE OR REPLACE TABLE anesthesia_dataset.anesthesia_pubmed_records (
    pmid STRING NOT NULL,
    doi STRING,
    doi_normalized STRING,
    pmcid STRING,
    title STRING,
    abstract STRING,
    journal_title STRING,
    journal_if FLOAT64,
    publication_year INT64,
    publication_month INT64,
    mesh_terms JSON,
    mesh_descriptor_names ARRAY<STRING>,
    mesh_major_names ARRAY<STRING>,
    keywords ARRAY<STRING>,
    publication_types ARRAY<STRING>,
    chemical_names ARRAY<STRING>,
    anesthesia_subdomains ARRAY<STRING>,
    study_design_type STRING,
    is_landmark BOOL,
    drugs ARRAY<STRING>,
    techniques ARRAY<STRING>,
    outcomes ARRAY<STRING>,
    citation_count_openalex INT64,
    agent_id INT64,
    search_text STRING, -- concatenated title+abstract for SEARCH index
    embedding ARRAY<FLOAT64> -- for VECTOR_SEARCH
) PARTITION BY RANGE_BUCKET(publication_year, GENERATE_ARRAY(1950, 2030, 1))
CLUSTER BY anesthesia_subdomains, study_design_type, journal_title;

-- BigQuery SEARCH indexes (replaces PG GIN)
CREATE SEARCH INDEX IF NOT EXISTS idx_bq_mesh_search
ON anesthesia_dataset.anesthesia_pubmed_records(mesh_descriptor_names);

CREATE SEARCH INDEX IF NOT EXISTS idx_bq_title_abstract_search
ON anesthesia_dataset.anesthesia_pubmed_records(search_text);

CREATE SEARCH INDEX IF NOT EXISTS idx_bq_subdomain_search
ON anesthesia_dataset.anesthesia_pubmed_records(anesthesia_subdomains);

-- Vector search index for embeddings (if using BigQuery ML embeddings)
CREATE VECTOR INDEX IF NOT EXISTS idx_bq_embedding
ON anesthesia_dataset.anesthesia_pubmed_records(embedding)
OPTIONS(distance_type="COSINE", index_type="IVF", ivf_options='{"num_lists": 100}');

-- Materialized views BigQuery
CREATE MATERIALIZED VIEW IF NOT EXISTS anesthesia_dataset.mv_subdomain_overview AS
SELECT subdomain, COUNT(*) as total_records, COUNTIF(is_landmark) as landmark_count, AVG(citation_count_openalex) as avg_citations
FROM anesthesia_dataset.anesthesia_pubmed_records, UNNEST(anesthesia_subdomains) AS subdomain
GROUP BY subdomain;

-- Example query leveraging SEARCH
-- SELECT * FROM anesthesia_dataset.anesthesia_pubmed_records WHERE SEARCH(search_text, 'awareness general anesthesia');
