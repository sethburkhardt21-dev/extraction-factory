-- Preserve every preprint version; do NOT make DOI alone unique.
CREATE TABLE IF NOT EXISTS preprint_versions (
  server TEXT NOT NULL,
  doi TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version >= 1),
  title TEXT,
  authors TEXT,
  author_corresponding TEXT,
  author_corresponding_institution TEXT,
  category TEXT,
  posted_date DATE,
  type TEXT,
  license TEXT,
  abstract TEXT,
  funding JSONB,
  published TEXT,
  jatsxml TEXT,
  source_record_sha256 CHAR(64) NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (server, doi, version)
);
CREATE INDEX IF NOT EXISTS preprint_versions_posted_date_idx ON preprint_versions(posted_date);
CREATE INDEX IF NOT EXISTS preprint_versions_category_idx ON preprint_versions(server, category);

CREATE OR REPLACE VIEW preprint_latest AS
SELECT DISTINCT ON (server, doi) *
FROM preprint_versions
ORDER BY server, doi, version DESC;
