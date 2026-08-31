-- ============================================================================
-- Materialized Views for Anesthesia Subdomain Aggregations
-- Depends on anesthesia_indexes_views_production.sql base table
-- Production: refresh concurrently where unique index exists
-- ============================================================================

-- Helper: safe drop/recreate for idempotency
-- Use CREATE MATERIALIZED VIEW IF NOT EXISTS where possible (PG 9.4+)

-- --------------------------------------------------------------------------
-- 1. mv_subdomain_overview - core counts per subdomain
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_subdomain_overview AS
SELECT
    subdomain,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE publication_year >= 2020) AS total_since_2020,
    COUNT(*) FILTER (WHERE is_landmark = true) AS landmark_count,
    COUNT(*) FILTER (WHERE study_design_type = 'RCT') AS rct_count,
    COUNT(*) FILTER (WHERE study_design_type IN ('Systematic Review','Meta-Analysis')) AS srma_count,
    COUNT(*) FILTER (WHERE publication_types @> ARRAY['Guideline']) AS guideline_count,
    AVG(citation_count_openalex)::INT AS avg_citations,
    MAX(citation_count_openalex) AS max_citations,
    COUNT(DISTINCT journal_title) AS distinct_journals,
    MIN(publication_year) AS earliest_year,
    MAX(publication_year) AS latest_year,
    AVG(n_patients) FILTER (WHERE n_patients IS NOT NULL)::INT AS avg_n_patients
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
GROUP BY subdomain
ORDER BY total_records DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_subdomain_overview_pk
    ON mv_subdomain_overview (subdomain);
COMMENT ON MATERIALIZED VIEW mv_subdomain_overview IS 'Per-subdomain 16-agent aggregation for dashboard, refreshed nightly';

-- --------------------------------------------------------------------------
-- 2. mv_subdomain_yearly_trends - trends per year for time-series charts
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_subdomain_yearly_trends AS
SELECT
    subdomain,
    publication_year,
    COUNT(*) AS record_count,
    COUNT(*) FILTER (WHERE is_landmark) AS landmark_count,
    COUNT(*) FILTER (WHERE study_design_type='RCT') AS rct_count,
    AVG(journal_if)::NUMERIC(6,2) AS avg_if,
    AVG(citation_count_openalex)::INT AS avg_citations,
    COUNT(DISTINCT journal_title) AS n_journals
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
WHERE publication_year IS NOT NULL
GROUP BY subdomain, publication_year
ORDER BY subdomain, publication_year DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_yearly_pk
    ON mv_subdomain_yearly_trends (subdomain, publication_year);
CREATE INDEX IF NOT EXISTS idx_mv_yearly_year
    ON mv_subdomain_yearly_trends (publication_year DESC);

-- Query example: linear growth pediatric from 2021 report 202 -> 954 trend
-- SELECT publication_year, record_count FROM mv_subdomain_yearly_trends WHERE subdomain='Pediatric Anesthesia' ORDER BY publication_year;

-- --------------------------------------------------------------------------
-- 3. mv_mesh_frequency_by_subdomain - top MeSH per subdomain
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_mesh_frequency_by_subdomain AS
SELECT
    subdomain,
    mesh_name,
    COUNT(*) AS freq,
    COUNT(*) FILTER (WHERE mesh_major_names @> ARRAY[mesh_name]) AS freq_as_major,
    ROUND(100.0*COUNT(*)/NULLIF(SUM(COUNT(*)) OVER (PARTITION BY subdomain),0),2) AS pct_of_subdomain
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
CROSS JOIN LATERAL unnest(mesh_descriptor_names) AS m(mesh_name)
WHERE mesh_name IS NOT NULL
GROUP BY subdomain, mesh_name
ORDER BY subdomain, freq DESC;

CREATE INDEX IF NOT EXISTS idx_mv_mesh_subdomain
    ON mv_mesh_frequency_by_subdomain (subdomain, freq DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_mesh_pk
    ON mv_mesh_frequency_by_subdomain (subdomain, mesh_name);
CREATE INDEX IF NOT EXISTS idx_mv_mesh_name_trgm
    ON mv_mesh_frequency_by_subdomain USING gin (mesh_name gin_trgm_ops);

-- --------------------------------------------------------------------------
-- 4. mv_drug_frequency_by_subdomain
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_drug_frequency_by_subdomain AS
SELECT
    subdomain,
    drug,
    COUNT(*) AS freq,
    COUNT(*) FILTER (WHERE study_design_type='RCT') AS rct_freq,
    AVG(citation_count_openalex)::INT AS avg_cit
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
CROSS JOIN LATERAL unnest(drugs) AS d(drug)
WHERE drug IS NOT NULL
GROUP BY subdomain, drug
HAVING COUNT(*) >= 2 -- noise filter
ORDER BY subdomain, freq DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_drug_pk
    ON mv_drug_frequency_by_subdomain (subdomain, drug);
CREATE INDEX IF NOT EXISTS idx_mv_drug_freq
    ON mv_drug_frequency_by_subdomain (subdomain, freq DESC);

-- --------------------------------------------------------------------------
-- 5. mv_outcome_frequency_by_subdomain
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_outcome_frequency_by_subdomain AS
SELECT
    subdomain,
    outcome,
    COUNT(*) AS freq,
    COUNT(DISTINCT drugs) AS n_drugs_associated -- will recompute from lateral
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
CROSS JOIN LATERAL unnest(outcomes) AS o(outcome)
WHERE outcome IS NOT NULL
GROUP BY subdomain, outcome
ORDER BY subdomain, freq DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_outcome_pk
    ON mv_outcome_frequency_by_subdomain (subdomain, outcome);

-- --------------------------------------------------------------------------
-- 6. mv_journal_ranking_by_subdomain
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_journal_ranking_by_subdomain AS
SELECT
    subdomain,
    journal_title,
    COUNT(*) AS n_records,
    AVG(journal_if)::NUMERIC(5,2) AS avg_if,
    MAX(journal_if) AS max_if,
    AVG(citation_count_openalex)::INT AS avg_citations,
    COUNT(*) FILTER (WHERE is_landmark) AS landmark_count,
    COUNT(*) FILTER (WHERE publication_year >= 2023) AS recent_2023_plus
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
WHERE journal_title IS NOT NULL
GROUP BY subdomain, journal_title
ORDER BY subdomain, n_records DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_journal_pk
    ON mv_journal_ranking_by_subdomain (subdomain, journal_title);
CREATE INDEX IF NOT EXISTS idx_mv_journal_n
    ON mv_journal_ranking_by_subdomain (subdomain, n_records DESC);

-- Expectation: Anesthesiology 9.1, BJA 9.166 etc top

-- --------------------------------------------------------------------------
-- 7. mv_study_design_by_subdomain
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_study_design_by_subdomain AS
SELECT
    subdomain,
    study_design_type,
    COUNT(*) AS freq,
    AVG(n_patients)::INT FILTER (WHERE n_patients IS NOT NULL) AS avg_n_patients,
    COUNT(*) FILTER (WHERE multicenter) AS multicenter_count,
    AVG(citation_count_openalex)::INT AS avg_citations
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
WHERE study_design_type IS NOT NULL
GROUP BY subdomain, study_design_type
ORDER BY subdomain, freq DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_studydesign_pk
    ON mv_study_design_by_subdomain (subdomain, study_design_type);

-- Highlights gap: neuroanesthesia only 13 multicenter RCTs 1997-2025 (from max-anesthesia report)

-- --------------------------------------------------------------------------
-- 8. mv_subdomain_cooccurrence - pair analysis
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_subdomain_cooccurrence AS
SELECT
    a AS subdomain_a,
    b AS subdomain_b,
    COUNT(*) AS cooccurrence_count,
    ROUND(100.0*COUNT(*) / (SELECT COUNT(*) FROM anesthesia_pubmed_records),3) AS pct_total
FROM (
    SELECT
        sd1 AS a,
        sd2 AS b
    FROM anesthesia_pubmed_records
    CROSS JOIN LATERAL (
        SELECT ARRAY(SELECT unnest(anesthesia_subdomains) ORDER BY 1) AS sorted_sd
    ) s
    CROSS JOIN LATERAL unnest(sorted_sd) WITH ORDINALITY AS t1(sd1, ord1)
    CROSS JOIN LATERAL unnest(sorted_sd) WITH ORDINALITY AS t2(sd2, ord2)
    WHERE ord1 < ord2
) pairs
GROUP BY a,b
HAVING COUNT(*) >= 3
ORDER BY cooccurrence_count DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_cooccur_pk
    ON mv_subdomain_cooccurrence (subdomain_a, subdomain_b);
COMMENT ON MATERIALIZED VIEW mv_subdomain_cooccurrence IS 'Overlap between subdomains - e.g., Pain Medicine + Peripheral Nerve Blocks high';

-- --------------------------------------------------------------------------
-- 9. mv_chemical_frequency - anesthesia specific drugs list from chemicals table
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_chemical_frequency AS
SELECT
    chem_name,
    COUNT(*) AS freq,
    COUNT(DISTINCT unnest_sub) AS n_subdomains_covered,
    AVG(citation_count_openalex)::INT AS avg_citations
FROM anesthesia_pubmed_records
CROSS JOIN LATERAL unnest(chemical_names) AS c(chem_name)
CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS u(unnest_sub)
WHERE chem_name IS NOT NULL
GROUP BY chem_name
ORDER BY freq DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_chem_pk
    ON mv_chemical_frequency (chem_name);

-- --------------------------------------------------------------------------
-- 10. mv_top_cited_per_subdomain - landmark ranking view
-- --------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_top_cited_per_subdomain AS
SELECT
    subdomain,
    pmid,
    doi_normalized,
    title,
    journal_title,
    publication_year,
    citation_count_openalex,
    citation_count_scholar,
    is_landmark,
    study_design_type,
    ROW_NUMBER() OVER (PARTITION BY subdomain ORDER BY citation_count_openalex DESC NULLS LAST, publication_year DESC) AS rank_in_subdomain
FROM (
    SELECT DISTINCT ON (subdomain, pmid) -- dedup per subdomain after lateral
        subdomain,
        r.pmid,
        r.doi_normalized,
        r.title,
        r.journal_title,
        r.publication_year,
        r.citation_count_openalex,
        r.citation_count_scholar,
        r.is_landmark,
        r.study_design_type
    FROM anesthesia_pubmed_records r
    CROSS JOIN LATERAL unnest(r.anesthesia_subdomains) AS t(subdomain)
    WHERE r.citation_count_openalex IS NOT NULL
    ORDER BY subdomain, pmid, citation_count_openalex DESC
) dedup
ORDER BY subdomain, rank_in_subdomain;

CREATE INDEX IF NOT EXISTS idx_mv_topcited_sub_rank
    ON mv_top_cited_per_subdomain (subdomain, rank_in_subdomain);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_topcited_pk
    ON mv_top_cited_per_subdomain (subdomain, pmid);

-- --------------------------------------------------------------------------
-- 11. mv_fulltext_keyphrase - tsvector lexeme frequency per subdomain (optional heavy)
-- --------------------------------------------------------------------------
-- Note: heavy - use for dashboard, skip if corpus > 500k without extra shared_buffers
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_keyphrase_trends AS
SELECT
    subdomain,
    publication_year,
    word,
    ndoc,
    nentry
FROM (
    SELECT
        subdomain,
        publication_year,
        (ts_stat('SELECT search_vector FROM anesthesia_pubmed_records')).*
    FROM anesthesia_pubmed_records
    CROSS JOIN LATERAL unnest(anesthesia_subdomains) AS t(subdomain)
    WHERE publication_year >= 2020
    GROUP BY subdomain, publication_year
) s
LIMIT 0; -- create empty skeleton, populate via refresh function if needed
-- Alternative production population via ts_stat on filtered set

-- --------------------------------------------------------------------------
-- 12. Refresh strategy & concurrency helpers
-- --------------------------------------------------------------------------
-- Concurrent refresh requires unique index - all above have it
-- Create function for nightly refresh

CREATE OR REPLACE FUNCTION refresh_anesthesia_matviews(concurrent BOOLEAN DEFAULT true)
RETURNS TABLE(view_name TEXT, refreshed_at TIMESTAMPTZ, duration_ms INT) AS $$
DECLARE
    v TEXT;
    start_ts TIMESTAMPTZ;
    views TEXT[] := ARRAY[
        'mv_subdomain_overview',
        'mv_subdomain_yearly_trends',
        'mv_mesh_frequency_by_subdomain',
        'mv_drug_frequency_by_subdomain',
        'mv_outcome_frequency_by_subdomain',
        'mv_journal_ranking_by_subdomain',
        'mv_study_design_by_subdomain',
        'mv_subdomain_cooccurrence',
        'mv_chemical_frequency',
        'mv_top_cited_per_subdomain'
    ];
BEGIN
    FOREACH v IN ARRAY views LOOP
        start_ts := clock_timestamp();
        IF concurrent THEN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', v);
        ELSE
            EXECUTE format('REFRESH MATERIALIZED VIEW %I', v);
        END IF;
        view_name := v;
        refreshed_at := now();
        duration_ms := EXTRACT(MILLISECOND FROM (clock_timestamp() - start_ts))::INT;
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_anesthesia_matviews IS 'Nightly refresh. Use concurrent=true to avoid blocking reads. Schedule via pg_cron or airflow';

-- pg_cron scheduling example (if extension enabled):
-- SELECT cron.schedule('refresh-anesthesia-mvs', '0 3 * * *', 'SELECT refresh_anesthesia_matviews(true)');

-- --------------------------------------------------------------------------
-- 13. Example optimized queries using indexes & matviews
-- --------------------------------------------------------------------------
-- Q1: Pediatric neurotoxicity max recall using FTS + subdomain + mesh major
-- SELECT pmid, title, publication_year, ts_rank(search_vector, q) AS rank
-- FROM anesthesia_pubmed_records, to_tsquery('english','pediatric & neurotoxicity & (anesthesia | anaesthesia)') q
-- WHERE search_vector @@ q AND anesthesia_subdomains @> ARRAY['Pediatric Anesthesia']
-- ORDER BY rank DESC LIMIT 50;

-- Q2: Fascial plane blocks (terminology not stable MeSH) - requires trigram + FTS
-- SELECT pmid, title FROM anesthesia_pubmed_records
-- WHERE search_vector @@ to_tsquery('english','(ESP | erector & spinae | TAP | transversus & abdominis | QLB | PENG) & block')
--    OR title ILIKE '%fascial plane%'; -- uses idx_anesth_title_trgm gin_trgm_ops

-- Q3: Subdomain aggregation dashboard - uses mv_subdomain_overview (ms vs seq)
-- SELECT * FROM mv_subdomain_overview ORDER BY total_records DESC;

-- Q4: MeSH major topic drill down
-- SELECT * FROM mv_mesh_frequency_by_subdomain WHERE subdomain='Airway Management' ORDER BY freq DESC LIMIT 20;

-- Q5: Journal impact per subdomain - uses mv
-- SELECT * FROM mv_journal_ranking_by_subdomain WHERE subdomain='General Anesthesia' ORDER BY avg_if DESC;

-- Q6: Vector semantic search (if pgvector populated)
-- SELECT pmid, title, embedding <=> query_embedding AS distance FROM anesthesia_pubmed_records ORDER BY distance LIMIT 20;

-- --------------------------------------------------------------------------
-- 14. BigQuery materialized view equivalents (commented)
-- --------------------------------------------------------------------------
-- In BigQuery, use BI Engine + materialized views:
-- CREATE MATERIALIZED VIEW dataset.mv_subdomain_yearly AS
-- SELECT subdomain, publication_year, COUNT(*) AS cnt FROM dataset.anesthesia_pubmed_records CROSS JOIN UNNEST(anesthesia_subdomains) AS subdomain GROUP BY 1,2;
-- Cluster & partition source table for cost.

-- End materialized views
