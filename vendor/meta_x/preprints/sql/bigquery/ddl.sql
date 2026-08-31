CREATE TABLE IF NOT EXISTS `preprint_extraction.preprint_versions` (
  server STRING NOT NULL,
  doi STRING NOT NULL,
  version INT64 NOT NULL,
  title STRING,
  authors STRING,
  author_corresponding STRING,
  author_corresponding_institution STRING,
  category STRING,
  posted_date DATE,
  type STRING,
  license STRING,
  abstract STRING,
  funding JSON,
  published STRING,
  jatsxml STRING,
  source_record_sha256 STRING NOT NULL,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY posted_date
CLUSTER BY server, doi, category;

CREATE OR REPLACE VIEW `preprint_extraction.preprint_latest` AS
SELECT * EXCEPT(row_num) FROM (
  SELECT *, ROW_NUMBER() OVER(PARTITION BY server, doi ORDER BY version DESC) AS row_num
  FROM `preprint_extraction.preprint_versions`
) WHERE row_num = 1;
