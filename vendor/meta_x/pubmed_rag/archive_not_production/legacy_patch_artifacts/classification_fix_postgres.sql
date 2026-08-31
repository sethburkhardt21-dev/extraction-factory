
-- ============================================
-- Agent B8: Classification Fix - Postgres DDL
-- Production deliverable for max anesthesia PubMed extraction
-- Fixes: regex \b word boundaries, MeSH major topic weighting,
--        child/children FP, education trap
-- ============================================

-- 1. Core table: anesthesia_pubmed with JSONB for mesh_terms (if not exists)
CREATE TABLE IF NOT EXISTS anesthesia_pubmed (
    pmid VARCHAR(20) PRIMARY KEY,
    doi TEXT,
    pmcid TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    journal_title TEXT,
    publication_date_year INT,
    mesh_terms JSONB,
    keywords JSONB,
    publication_types JSONB,
    chemicals JSONB,
    anesthesia_subdomains TEXT[],
    extraction_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Classification scores with MeSH weighting
CREATE TABLE IF NOT EXISTS anesthesia_classification_scores (
    pmid VARCHAR(20) REFERENCES anesthesia_pubmed(pmid) ON DELETE CASCADE,
    domain VARCHAR(100) NOT NULL,
    score NUMERIC(6,3) NOT NULL,
    evidence JSONB,
    mesh_major_weighted_score NUMERIC(6,3),
    mesh_minor_weighted_score NUMERIC(6,3),
    tiab_score NUMERIC(6,3),
    mesh_major_count INT DEFAULT 0,
    mesh_minor_count INT DEFAULT 0,
    tiab_match_count INT DEFAULT 0,
    threshold_applied NUMERIC(4,2) DEFAULT 1.5,
    is_tagged BOOLEAN GENERATED ALWAYS AS (score >= threshold_applied) STORED,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (pmid, domain)
);

CREATE INDEX IF NOT EXISTS idx_class_scores_domain_score ON anesthesia_classification_scores(domain, score DESC);
CREATE INDEX IF NOT EXISTS idx_class_scores_tagged ON anesthesia_classification_scores(is_tagged) WHERE is_tagged = TRUE;
CREATE INDEX IF NOT EXISTS idx_pubmed_mesh_gin ON anesthesia_pubmed USING GIN (mesh_terms);

-- 3. Helper function: PostgreSQL word boundary regex (\m \M = start/end of word)
CREATE OR REPLACE FUNCTION fn_has_word_boundary(
    content TEXT,
    pattern TEXT,
    case_sensitive BOOLEAN DEFAULT FALSE
) RETURNS BOOLEAN AS $$
DECLARE
    regex TEXT;
BEGIN
    regex := '\m' || pattern || '\M';
    IF case_sensitive THEN
        RETURN content ~ regex;
    ELSE
        RETURN content ~* regex;
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE;

-- 4. Specific FP-guard functions
CREATE OR REPLACE FUNCTION fn_is_pediatric_text(content TEXT) RETURNS BOOLEAN AS $$
BEGIN
    RETURN 
        content ~* '\mchildren\M' OR
        content ~* '\mchild\M' OR
        content ~* '\mpediatric\M' OR
        content ~* '\mpaediatric\M' OR
        content ~* '\minfant\M' OR
        content ~* '\mneonat\w*\M';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION fn_is_anesthesia_education(content TEXT) RETURNS BOOLEAN AS $$
BEGIN
    IF content ~* '\mpatient education\M' OR
       content ~* '\mhealth education\M' OR
       content ~* '\meducation level\M' OR
       content ~* '\meducational attainment\M' THEN
        IF NOT (content ~* '\manesthesia education\M' OR
                content ~* '\manaesthesia education\M' OR
                content ~* '\msimulation training\M' OR
                content ~* '\martificial intelligence\M') THEN
            RETURN FALSE;
        END IF;
    END IF;
    RETURN 
        content ~* '\manesthesia education\M' OR
        content ~* '\manaesthesia education\M' OR
        content ~* '\msimulation training\M' OR
        content ~* '\martificial intelligence\M.*\manesthes' OR
        content ~* '\mmachine learning\M.*\manesthes' OR
        content ~* '\manesthesia simulation\M';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION fn_has_strict_acronym(content TEXT, acronym TEXT) RETURNS BOOLEAN AS $$
BEGIN
    RETURN content ~ ('\m' || acronym || '\M');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION fn_mesh_weight(is_major BOOLEAN) RETURNS NUMERIC AS $$
BEGIN
    RETURN CASE WHEN is_major THEN 3.0 ELSE 1.5 END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 5. Main classification view with weighting
CREATE OR REPLACE VIEW v_classification_scoring AS
WITH mesh_flat AS (
    SELECT pmid, title, abstract, jsonb_array_elements(mesh_terms) AS mesh_elem
    FROM anesthesia_pubmed WHERE mesh_terms IS NOT NULL
),
mesh_scored AS (
    SELECT
        pmid,
        (mesh_elem->>'descriptor_name') AS descriptor_name,
        COALESCE((mesh_elem->>'major_topic')::BOOLEAN, FALSE) AS is_major,
        fn_mesh_weight(COALESCE((mesh_elem->>'major_topic')::BOOLEAN, FALSE)) AS w,
        LOWER(mesh_elem->>'descriptor_name') AS desc_lower
    FROM mesh_flat
),
domain_scores_mesh AS (
    SELECT
        pmid,
        CASE
            WHEN desc_lower = 'anesthesia, general' THEN 'General Anesthesia'
            WHEN desc_lower IN ('anesthesia, spinal','anesthesia, epidural','anesthesia, conduction') THEN 'Regional Anesthesia - Spinal Epidural'
            WHEN desc_lower IN ('nerve block','brachial plexus block') THEN 'Peripheral Nerve Blocks'
            WHEN desc_lower IN ('anesthetics, local','lidocaine','bupivacaine','ropivacaine') THEN 'Local Anesthetics Pharmacology'
            WHEN desc_lower IN ('airway management','intubation, intratracheal','laryngoscopy') THEN 'Airway Management'
            WHEN desc_lower = 'pediatrics' OR desc_lower = 'child' OR desc_lower = 'infant' THEN 'Pediatric Anesthesia'
            WHEN desc_lower = 'anesthesia, obstetrical' THEN 'Obstetric Anesthesia'
            WHEN desc_lower = 'cardiac surgical procedures' THEN 'Cardiac Anesthesia'
            WHEN desc_lower = 'artificial intelligence' THEN 'AI Simulation Education'
            ELSE NULL
        END AS domain,
        SUM(w) AS mesh_score,
        COUNT(*) FILTER (WHERE is_major) AS major_cnt,
        COUNT(*) FILTER (WHERE NOT is_major) AS minor_cnt
    FROM mesh_scored
    GROUP BY pmid, domain
    HAVING CASE
            WHEN desc_lower = 'anesthesia, general' THEN 'General Anesthesia'
            WHEN desc_lower IN ('anesthesia, spinal','anesthesia, epidural','anesthesia, conduction') THEN 'Regional Anesthesia - Spinal Epidural'
            WHEN desc_lower IN ('nerve block','brachial plexus block') THEN 'Peripheral Nerve Blocks'
            WHEN desc_lower IN ('anesthetics, local','lidocaine','bupivacaine','ropivacaine') THEN 'Local Anesthetics Pharmacology'
            WHEN desc_lower IN ('airway management','intubation, intratracheal','laryngoscopy') THEN 'Airway Management'
            WHEN desc_lower = 'pediatrics' OR desc_lower = 'child' OR desc_lower = 'infant' THEN 'Pediatric Anesthesia'
            WHEN desc_lower = 'anesthesia, obstetrical' THEN 'Obstetric Anesthesia'
            WHEN desc_lower = 'cardiac surgical procedures' THEN 'Cardiac Anesthesia'
            WHEN desc_lower = 'artificial intelligence' THEN 'AI Simulation Education'
            ELSE NULL
        END IS NOT NULL
)
SELECT * FROM domain_scores_mesh;

CREATE OR REPLACE VIEW v_anesthesia_final_tags AS
SELECT
    p.pmid,
    p.title,
    ARRAY_AGG(DISTINCT cs.domain) FILTER (WHERE cs.score >= 1.5) AS final_domains,
    JSONB_OBJECT_AGG(cs.domain, cs.score) FILTER (WHERE cs.domain IS NOT NULL) AS score_map
FROM anesthesia_pubmed p
LEFT JOIN anesthesia_classification_scores cs ON cs.pmid = p.pmid
GROUP BY p.pmid, p.title;
