
-- ============================================
-- Agent B8: Classification Fix - BigQuery DDL
-- ============================================

CREATE TABLE IF NOT EXISTS `project.dataset.anesthesia_pubmed` (
  pmid STRING NOT NULL,
  doi STRING,
  pmcid STRING,
  title STRING NOT NULL,
  abstract STRING,
  publication_date_year INT64,
  mesh_terms ARRAY<STRUCT<descriptor_name STRING, descriptor_ui STRING, qualifiers ARRAY<STRING>, major_topic BOOL>>,
  keywords ARRAY<STRING>,
  anesthesia_subdomains ARRAY<STRING>,
  extraction_metadata STRUCT<query_used STRING, agent_id INT64, retrieval_date TIMESTAMP, dedup_status STRING>,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY RANGE_BUCKET(publication_date_year, GENERATE_ARRAY(1900, 2030, 1))
CLUSTER BY pmid
OPTIONS (description="Max anesthesia PubMed extraction with fixed classification");

CREATE TABLE IF NOT EXISTS `project.dataset.anesthesia_classification_scores` (
  pmid STRING NOT NULL,
  domain STRING NOT NULL,
  score FLOAT64 NOT NULL,
  mesh_major_score FLOAT64,
  mesh_minor_score FLOAT64,
  tiab_score FLOAT64,
  evidence ARRAY<STRING>,
  mesh_major_count INT64,
  mesh_minor_count INT64,
  tiab_match_count INT64,
  threshold FLOAT64 DEFAULT 1.5,
  is_tagged BOOL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY domain, pmid;

CREATE OR REPLACE VIEW `project.dataset.v_classification_fixed` AS
WITH base AS (
  SELECT pmid, title, IFNULL(abstract,'') AS abstract, CONCAT(title, ' ', IFNULL(abstract,'')) AS combined, mesh_terms
  FROM `project.dataset.anesthesia_pubmed`
),
mesh_exploded AS (
  SELECT pmid, title, abstract, combined, m.descriptor_name AS mesh_desc, LOWER(m.descriptor_name) AS mesh_lower, m.major_topic AS is_major, IF(m.major_topic, 3.0, 1.5) AS mesh_weight
  FROM base, UNNEST(mesh_terms) AS m
),
mesh_domain_scores AS (
  SELECT pmid,
    CASE
      WHEN mesh_lower IN ('anesthesia, general','anesthesia, inhalation','anesthesia, intravenous') THEN 'General Anesthesia'
      WHEN mesh_lower IN ('anesthesia, spinal','anesthesia, epidural','anesthesia, conduction','anesthesia, caudal') THEN 'Regional Anesthesia - Spinal Epidural'
      WHEN mesh_lower IN ('nerve block','brachial plexus block','transversus abdominis plane block') THEN 'Peripheral Nerve Blocks'
      WHEN mesh_lower IN ('anesthetics, local','lidocaine','bupivacaine','ropivacaine','levobupivacaine') THEN 'Local Anesthetics Pharmacology'
      WHEN mesh_lower IN ('airway management','intubation, intratracheal','laryngoscopy','laryngeal masks') THEN 'Airway Management'
      WHEN mesh_lower IN ('pediatrics','infant','child','child, preschool','adolescent') THEN 'Pediatric Anesthesia'
      WHEN mesh_lower IN ('anesthesia, obstetrical','analgesia, obstetrical','labor, obstetric','cesarean section') THEN 'Obstetric Anesthesia'
      WHEN mesh_lower IN ('cardiac surgical procedures','cardiopulmonary bypass','echocardiography, transesophageal') THEN 'Cardiac Anesthesia'
      WHEN mesh_lower IN ('neurosurgical procedures','craniotomy') THEN 'Neuroanesthesia'
      WHEN mesh_lower IN ('intensive care units','critical care','dexmedetomidine','conscious sedation') THEN 'Critical Care ICU Sedation'
      WHEN mesh_lower IN ('pain, postoperative','acute pain','chronic pain','pain management') THEN 'Pain Medicine'
      WHEN mesh_lower IN ('malignant hyperthermia','postoperative nausea and vomiting','anaphylaxis') THEN 'Anesthesia Safety'
      WHEN mesh_lower IN ('propofol','ketamine','analgesics, opioid','neuromuscular blocking agents','sugammadex') THEN 'Pharmacology - Opioids Propofol Ketamine NMB'
      WHEN mesh_lower IN ('enhanced recovery after surgery','perioperative care') THEN 'ERAS Perioperative'
      WHEN mesh_lower IN ('artificial intelligence','machine learning','deep learning','simulation training','computer simulation') THEN 'AI Simulation Education'
      ELSE NULL
    END AS domain,
    SUM(mesh_weight) AS mesh_score,
    COUNTIF(is_major) AS major_cnt,
    COUNTIF(NOT is_major) AS minor_cnt
  FROM mesh_exploded GROUP BY pmid, domain, mesh_lower HAVING domain IS NOT NULL
),
tiab_scores AS (
  SELECT pmid,
    IF(REGEXP_CONTAINS(combined, r'(?i)\bchildren\b'), 1.0, 0) AS has_children,
    IF(REGEXP_CONTAINS(combined, r'(?i)\bchild\b') AND NOT REGEXP_CONTAINS(combined, r'(?i)\bchildhood\b'), 1.0, 0) AS has_child_exact,
    IF(REGEXP_CONTAINS(combined, r'(?i)\bpediatric anesthesia\b|\bpaediatric anaesthesia\b'), 1.2, 0) AS has_peds_anes,
    IF(REGEXP_CONTAINS(combined, r'(?i)\binfant\b|\bneonat\w*\b'), 1.0, 0) AS has_infant,
    IF(REGEXP_CONTAINS(combined, r'\bTAP\b') AND NOT REGEXP_CONTAINS(LOWER(combined), r'water tap|tap water'), 1.0, 0) AS has_TAP_strict,
    IF(REGEXP_CONTAINS(combined, r'\bBIS\b'), 1.0, 0) AS has_BIS_strict,
    IF(REGEXP_CONTAINS(combined, r'\bTEE\b|\bTOE\b'), 1.0, 0) AS has_TEE_strict,
    IF(REGEXP_CONTAINS(combined, r'\bCPB\b'), 1.0, 0) AS has_CPB_strict,
    IF(REGEXP_CONTAINS(combined, r'\bERAS\b'), 1.0, 0) AS has_ERAS_strict,
    IF((REGEXP_CONTAINS(combined, r'(?i)\banesthesia education\b|\banaesthesia education\b|\banesthesia simulation\b') OR (REGEXP_CONTAINS(combined, r'(?i)\bsimulation training\b') AND REGEXP_CONTAINS(combined, r'(?i)\banesthes'))) AND NOT (REGEXP_CONTAINS(combined, r'(?i)\bpatient education\b|\bhealth education\b|\beducation level\b') AND NOT REGEXP_CONTAINS(combined, r'(?i)\bsimulation|artificial intelligence|machine learning')), 1.5, 0) AS has_valid_anesth_edu,
    IF(REGEXP_CONTAINS(combined, r'(?i)\bnerve block\b|\bbrachial plexus\b|\bfemoral nerve\b'), 1.0, 0) AS has_PNB,
    IF(REGEXP_CONTAINS(combined, r'(?i)\bspinal anesthesia\b|\bepidural anesthesia\b|\bneuraxial\b'), 1.0, 0) AS has_neuraxial,
    IF(REGEXP_CONTAINS(combined, r'(?i)\bairway management\b|\bdifficult airway\b|\bvideolaryngoscop'), 1.0, 0) AS has_airway
  FROM base
),
final AS (
  SELECT b.pmid,
    COALESCE(m.domain, CASE WHEN t.has_children >0 OR t.has_child_exact>0 OR t.has_peds_anes>0 THEN 'Pediatric Anesthesia' WHEN t.has_TAP_strict>0 OR t.has_PNB>0 THEN 'Peripheral Nerve Blocks' WHEN t.has_neuraxial>0 THEN 'Regional Anesthesia - Spinal Epidural' WHEN t.has_airway>0 THEN 'Airway Management' WHEN t.has_valid_anesth_edu>0 THEN 'AI Simulation Education' WHEN t.has_BIS_strict>0 THEN 'Anesthesia Monitoring' WHEN t.has_ERAS_strict>0 THEN 'ERAS Perioperative' ELSE NULL END) AS domain,
    COALESCE(m.mesh_score,0) + t.has_children + t.has_child_exact + t.has_peds_anes + t.has_infant + t.has_TAP_strict + t.has_BIS_strict + t.has_TEE_strict + t.has_CPB_strict + t.has_ERAS_strict + t.has_valid_anesth_edu + t.has_PNB + t.has_neuraxial + t.has_airway AS total_score,
    m.mesh_score AS mesh_s, m.major_cnt, m.minor_cnt
  FROM base b LEFT JOIN mesh_domain_scores m USING(pmid) LEFT JOIN tiab_scores t USING(pmid)
)
SELECT pmid, domain, total_score AS score, total_score >= 1.5 AS is_tagged, mesh_s, major_cnt, minor_cnt FROM final WHERE domain IS NOT NULL AND total_score >= 1.5 ORDER BY pmid, total_score DESC;
