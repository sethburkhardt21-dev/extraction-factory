-- ============================================================================
-- Anesthesia PubMed Corpus - BigQuery Production DDL
-- Agent B4: ETL Loader Developer
-- Focus: JSONL -> BigQuery with staging + MERGE upsert on pmid
-- ============================================================================

-- Dataset creation (run once)
-- CREATE SCHEMA `project_id.anesthesia_pubmed` OPTIONS(location="US");

-- --------------------------------------------------------------------
-- Main table with partitioning & clustering for 280k-380k corpus
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `project_id.anesthesia_pubmed.anesthesia_full` (
    -- Identifiers
    pmid STRING NOT NULL OPTIONS(description="PubMed ID, PK"),
    pmid_int INT64,
    doi STRING OPTIONS(description="Normalized lowercase DOI"),
    doi_raw STRING,
    pmcid STRING,
    
    -- Content
    title STRING NOT NULL,
    abstract STRING,
    abstract_structured JSON,  -- BigQuery JSON type
    
    -- Journal
    journal_title STRING,
    journal_iso_abbreviation STRING,
    journal_issn STRING,
    journal_volume STRING,
    journal_issue STRING,
    journal_pages STRING,
    journal_impact_factor FLOAT64,
    journal_publisher STRING,
    journal_json JSON,
    
    -- Publication date (with MedlineDate fallback parsed)
    pub_year INT64,
    pub_month INT64,
    pub_day INT64,
    pub_type_date STRING,
    pdat STRING,
    publication_date_json JSON,
    
    -- Arrays (BigQuery native repeated)
    publication_types ARRAY<STRING>,
    keywords ARRAY<STRING>,
    anesthesia_subdomains ARRAY<STRING>,
    drugs ARRAY<STRING>,
    techniques ARRAY<STRING>,
    outcomes ARRAY<STRING>,
    
    -- Study design
    study_type STRING,
    is_landmark BOOL,
    n_patients INT64,
    n_studies_included INT64,
    multicenter BOOL,
    blinding STRING,
    registration_id STRING,
    population STRING,
    asa_class STRING,
    anesthesia_specific_json JSON,
    
    -- Citation
    citation_count_openalex INT64,
    citation_count_semantic_scholar INT64,
    is_top_100_pediatric BOOL,
    
    -- Complex nested as JSON for flexibility + native repeated for query
    authors JSON,
    mesh_terms JSON,
    chemicals JSON,
    
    -- Extraction metadata
    query_used STRING,
    agent_id INT64,
    retrieval_date TIMESTAMP,
    dedup_status STRING,
    duplicate_of_pmid STRING,
    extraction_metadata_json JSON,
    
    -- ETL lineage
    etl_loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    etl_file_source STRING,
    etl_batch_id STRING,
    doi_normalized BOOL,
    
    -- Embeddings (768-dim PubMedBERT) - for BigQuery ML vector search
    title_abstract_embedding ARRAY<FLOAT64> OPTIONS(description="PubMedBERT 768-dim"),
    embedding_model STRING,
    embedding_generated_at TIMESTAMP
)
PARTITION BY RANGE_BUCKET(pmid_int, GENERATE_ARRAY(0, 40000000, 1000000))
-- Alternative: PARTITION BY _PARTITIONDATE if using ingestion time, but range on pmid_int better
CLUSTER BY pub_year, study_type, agent_id
OPTIONS(
    description="Max anesthesia PubMed 16-agent swarm full metadata, 280k-380k records",
    require_partition_filter=false
);

-- Staging table for MERGE upsert (same schema, no partitioning needed but keep simple)
CREATE TABLE IF NOT EXISTS `project_id.anesthesia_pubmed.anesthesia_full_staging` (
    LIKE `project_id.anesthesia_pubmed.anesthesia_full`
)
OPTIONS(
    description="Staging for batch MERGE upsert"
);

-- Rejections table
CREATE TABLE IF NOT EXISTS `project_id.anesthesia_pubmed.etl_rejections` (
    id STRING DEFAULT GENERATE_UUID(),
    pmid STRING,
    file_source STRING,
    batch_id STRING,
    error_message STRING,
    raw_json JSON,
    rejected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- Audit table
CREATE TABLE IF NOT EXISTS `project_id.anesthesia_pubmed.etl_audit` (
    batch_id STRING NOT NULL,
    file_source STRING,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    finished_at TIMESTAMP,
    records_read INT64,
    records_inserted INT64,
    records_updated INT64,
    records_rejected INT64,
    status STRING,
    notes JSON
);

-- --------------------------------------------------------------------
-- MERGE template for upsert (use in loader script)
-- --------------------------------------------------------------------
/*
-- BigQuery MERGE upsert best practice: load batch to staging, then MERGE
-- DML-quota-conscious: batch 5k-10k per MERGE, not one MERGE per row

MERGE `project_id.anesthesia_pubmed.anesthesia_full` T
USING `project_id.anesthesia_pubmed.anesthesia_full_staging` S
ON T.pmid = S.pmid
WHEN MATCHED THEN
  UPDATE SET
    doi = S.doi,
    doi_raw = S.doi_raw,
    pmcid = S.pmcid,
    title = S.title,
    abstract = S.abstract,
    abstract_structured = S.abstract_structured,
    journal_title = S.journal_title,
    journal_iso_abbreviation = S.journal_iso_abbreviation,
    journal_issn = S.journal_issn,
    journal_volume = S.journal_volume,
    journal_issue = S.journal_issue,
    journal_pages = S.journal_pages,
    journal_impact_factor = S.journal_impact_factor,
    journal_publisher = S.journal_publisher,
    journal_json = S.journal_json,
    pub_year = S.pub_year,
    pub_month = S.pub_month,
    pub_day = S.pub_day,
    pub_type_date = S.pub_type_date,
    pdat = S.pdat,
    publication_date_json = S.publication_date_json,
    publication_types = S.publication_types,
    keywords = S.keywords,
    anesthesia_subdomains = S.anesthesia_subdomains,
    drugs = S.drugs,
    techniques = S.techniques,
    outcomes = S.outcomes,
    study_type = S.study_type,
    is_landmark = S.is_landmark,
    n_patients = S.n_patients,
    n_studies_included = S.n_studies_included,
    multicenter = S.multicenter,
    blinding = S.blinding,
    registration_id = S.registration_id,
    population = S.population,
    asa_class = S.asa_class,
    anesthesia_specific_json = S.anesthesia_specific_json,
    citation_count_openalex = S.citation_count_openalex,
    citation_count_semantic_scholar = S.citation_count_semantic_scholar,
    is_top_100_pediatric = S.is_top_100_pediatric,
    authors = S.authors,
    mesh_terms = S.mesh_terms,
    chemicals = S.chemicals,
    query_used = S.query_used,
    agent_id = S.agent_id,
    retrieval_date = S.retrieval_date,
    dedup_status = S.dedup_status,
    duplicate_of_pmid = S.duplicate_of_pmid,
    extraction_metadata_json = S.extraction_metadata_json,
    etl_loaded_at = CURRENT_TIMESTAMP(),
    etl_file_source = S.etl_file_source,
    etl_batch_id = S.etl_batch_id,
    doi_normalized = S.doi_normalized,
    title_abstract_embedding = S.title_abstract_embedding,
    embedding_model = S.embedding_model,
    embedding_generated_at = S.embedding_generated_at
WHEN NOT MATCHED THEN
  INSERT ROW;

-- Then truncate staging
TRUNCATE TABLE `project_id.anesthesia_pubmed.anesthesia_full_staging`;
*/

-- Views
CREATE OR REPLACE VIEW `project_id.anesthesia_pubmed.v_unique` AS
SELECT * FROM `project_id.anesthesia_pubmed.anesthesia_full`
WHERE dedup_status IN ('unique','merged');

-- Search view for flattened reporting
CREATE OR REPLACE VIEW `project_id.anesthesia_pubmed.v_flat_for_bi` AS
SELECT
    pmid,
    doi,
    title,
    pub_year,
    journal_title,
    journal_impact_factor,
    study_type,
    is_landmark,
    ARRAY_TO_STRING(anesthesia_subdomains, '|') AS subdomains_pipe,
    ARRAY_TO_STRING(drugs, '|') AS drugs_pipe,
    ARRAY_TO_STRING(publication_types, '|') AS pubtypes_pipe
FROM `project_id.anesthesia_pubmed.anesthesia_full`;