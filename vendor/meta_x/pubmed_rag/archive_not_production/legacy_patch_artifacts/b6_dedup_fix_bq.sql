-- BigQuery Production DDL + UDFs
-- Project: anesthesia PubMed max extraction - Dedup fix B6

-- UDF: DOI normalization lowercase trim URL prefix
CREATE OR REPLACE FUNCTION `project.dataset.normalize_doi`(doi_raw STRING)
RETURNS STRING
LANGUAGE js AS """
  if (!doi_raw) return null;
  let s = doi_raw.trim();
  if (!s) return null;
  for (let i=0;i<3;i++) {
    let new_s = s.replace(/^\\s*(https?:\\/\\/(dx\\.)?doi\\.org\\/|doi:\\s*)\\s*/i, '').trim();
    if (new_s === s) break;
    s = new_s;
  }
  s = s.replace(/^[<>\\s]+|[<>\\s]+$/g, '').replace(/[.\\s;,?]+$/g,'').toLowerCase().replace(/\\s+/g,'');
  if (!/^10\\.\\d+\\/.+/.test(s)) return null;
  return s;
""";

-- UDF: Bramer page expansion struct
CREATE OR REPLACE FUNCTION `project.dataset.expand_pages`(pages_raw STRING)
RETURNS STRUCT<normalized_pages STRING, page_start INT64, page_end INT64>
LANGUAGE js AS """
  if (!pages_raw) return {normalized_pages: null, page_start: null, page_end: null};
  let s = pages_raw.trim().replace(/ /g,'').replace(/[–—]/g,'-');
  if (!s) return {normalized_pages: null, page_start: null, page_end: null};
  let m = s.match(/^([A-Za-z]*\\d+[A-Za-z]*)-([A-Za-z]*\\d+[A-Za-z]*)$/);
  if (m) {
    let start_raw = m[1], end_raw = m[2];
    let start_match = start_raw.match(/(\\d+)/);
    let end_match = end_raw.match(/(\\d+)/);
    if (!start_match || !end_match) return {normalized_pages: start_raw + '-' + end_raw, page_start: null, page_end: null};
    let start_num = parseInt(start_match[1],10);
    let end_num = parseInt(end_match[1],10);
    let start_digits = start_match[1];
    let end_digits = end_match[1];
    if (end_num < start_num && end_digits.length < start_digits.length) {
      let prefix = start_digits.substring(0, start_digits.length - end_digits.length);
      let expanded = parseInt(prefix + end_digits,10);
      return {normalized_pages: start_digits + '-' + expanded, page_start: start_num, page_end: expanded};
    }
    return {normalized_pages: start_raw + '-' + end_raw, page_start: start_num, page_end: end_num};
  }
  let single = s.match(/^[A-Za-z]*\\d+[A-Za-z]*$/);
  if (single) {
    let num = parseInt(s.match(/(\\d+)/)[1],10);
    return {normalized_pages: s, page_start: num, page_end: num};
  }
  if (s.includes(',') || s.includes(';')) {
    let first = s.split(/[,;]/)[0];
    // manual recursion for first token
    let inner = (function(p){ 
      let t = p.trim().replace(/ /g,'').replace(/[–—]/g,'-');
      let mm = t.match(/^([A-Za-z]*\\d+[A-Za-z]*)-([A-Za-z]*\\d+[A-Za-z]*)$/);
      if(mm){
        let sm = mm[1].match(/(\\d+)/); let em = mm[2].match(/(\\d+)/);
        if(!sm||!em) return {normalized_pages: mm[1]+'-'+mm[2], page_start:null,page_end:null};
        let sn=parseInt(sm[1],10); let en=parseInt(em[1],10); let sd=sm[1]; let ed=em[1];
        if(en<sn && ed.length<sd.length){ let pre=sd.substring(0,sd.length-ed.length); let ex=parseInt(pre+ed,10); return {normalized_pages: sd+'-'+ex, page_start:sn, page_end:ex} }
        return {normalized_pages: mm[1]+'-'+mm[2], page_start:sn, page_end:en};
      }
      let sing=t.match(/^[A-Za-z]*\\d+[A-Za-z]*$/); if(sing){ let n=parseInt(t.match(/(\\d+)/)[1],10); return {normalized_pages:t, page_start:n, page_end:n} }
      return {normalized_pages:null,page_start:null,page_end:null};
    })(first);
    return inner;
  }
  return {normalized_pages: null, page_start: null, page_end: null};
""";

-- Table
CREATE TABLE IF NOT EXISTS `project.dataset.anesthesia_pubmed_dedup` (
  pmid STRING NOT NULL OPTIONS(description="PubMed ID"),
  doi_raw STRING,
  doi_normalized STRING OPTIONS(description="Normalized DOI lowercase trim URL prefix"),
  pmcid STRING,
  title STRING NOT NULL,
  title_normalized STRING OPTIONS(description="Lowercase no punct"),
  abstract STRING,
  authors_json STRING,
  first_author_last STRING,
  journal_title STRING,
  pages_raw STRING,
  pages_normalized STRING OPTIONS(description="Bramer expanded"),
  page_start INT64,
  page_end INT64,
  pub_year INT64,
  dedup_status STRING,
  duplicate_of_pmid STRING
)
PARTITION BY RANGE_BUCKET(pub_year, GENERATE_ARRAY(1900, 2030, 5))
OPTIONS(description="Dedup improved anesthesia corpus");

-- View: Fuzzy candidates prefilter edit distance <15% length
CREATE OR REPLACE VIEW `project.dataset.vw_fuzzy_title_candidates` AS
WITH norm AS (
  SELECT
    pmid,
    title,
    LOWER(REGEXP_REPLACE(title, r'[^a-zA-Z0-9 ]', ' ')) AS title_norm,
    pub_year,
    first_author_last,
    pages_normalized
  FROM `project.dataset.anesthesia_pubmed_dedup`
)
SELECT
  a.pmid AS pmid_a,
  b.pmid AS pmid_b,
  EDIT_DISTANCE(a.title_norm, b.title_norm) AS edit_dist,
  LENGTH(a.title_norm) AS len_a,
  LENGTH(b.title_norm) AS len_b,
  a.title_norm,
  b.title_norm
FROM norm a
JOIN norm b ON a.pmid < b.pmid
  AND ABS(a.pub_year - b.pub_year) <=1
  AND SUBSTR(a.title_norm,1,3) = SUBSTR(b.title_norm,1,3)
WHERE 
  (a.first_author_last = b.first_author_last OR a.pages_normalized = b.pages_normalized)
  AND LENGTH(a.title_norm) > 20
  AND EDIT_DISTANCE(a.title_norm, b.title_norm) < CAST(GREATEST(LENGTH(a.title_norm), LENGTH(b.title_norm)) * 0.15 AS INT64);
