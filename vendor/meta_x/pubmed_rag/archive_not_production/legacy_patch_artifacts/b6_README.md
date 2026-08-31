# B6 Deduplication Improved Pipeline - Production Deliverables Summary

## Files Generated

### 1. Python Production Module
**Path:** `/mnt/data/b6_dedup_fix_pipeline.py`
- DOI normalization: `normalize_doi()` 
  - Lowercase, trim whitespace, strip URL prefixes `https://doi.org/`, `http://doi.org/`, `https://dx.doi.org/`, `http://dx.doi.org/`, `doi:` prefix (case-insensitive)
  - Handles trailing punctuation, `< >` wrapping, double prefix
  - Validates `10.xxxx/...` pattern
  - Returns None for invalid
- Bramer Page Expansion: `expand_abbreviated_pages()`
  - Implements NLM/Bramer rule: `123-5` -> `123-125`, `1101-9` -> `1101-1109`, `123-34` -> `123-134`, `1008-9` -> `1008-1009`
  - Handles en-dash/em-dash, letter prefixes `E123-E134`, single pages, comma separated `123-4, 126-8`
  - Returns `(normalized_pages, page_start, page_end)`
  - Wrapper `bramer_normalize_pages_for_dedup()` for dedup key
- Fuzzy Title 90%: `normalize_title_for_fuzzy()`, `title_similarity()` using rapidfuzz `WRatio` (fallback difflib)
  - Normalization: lowercase, HTML strip, punctuation -> space, collapse whitespace, remove leading articles
  - Threshold 90% per spec, with blocking by first 3 chars + year to reduce O(n^2)
  - Guard: same first author last OR same pages OR same journal with >=95% similarity
- End-to-end: `deduplicate_records(records, fuzzy_threshold=90)`
  - 4-stage: DOI normalized exact, PMID exact, Bramer composite exact (Title+Year+Journal+Pages), Fuzzy Title >=90%
  - Keeps richest abstract (longer abstract wins)
  - Returns `(unique_records, dedup_decisions)` with audit trail

Validated:
- DOI: 7/7 PASS (https, dx.doi.org, doi: prefix, case, trim)
- Bramer: 8/8 PASS incl 123-5, 1101-9, 123-34, 1008-9
- Fuzzy: 92% for SPICE III title variation, 100% for dash vs colon, 22% for unrelated (correct)

### 2. Postgres DDL
**Path:** `/mnt/data/b6_dedup_fix_ddl.sql`
- Table `anesthesia_pubmed_dedup` with generated columns `doi_normalized`, `title_normalized`, `first_author_last`, `pages_normalized`, `page_start/end`
- Indexes: `gin_trgm_ops` for fuzzy, btree for year/author/pages, composite Bramer keys
- `anesthesia_dedup_decisions` audit table for PRISMA reporting (method, similarity, reason)
- Functions:
  - `normalize_doi(TEXT) RETURNS TEXT` IMMUTABLE STRICT
  - `expand_medline_pages(TEXT) RETURNS TABLE(normalized_pages TEXT, page_start INT, page_end INT)` handles abbreviated ranges
  - `bramer_pages_dedup_key(TEXT)` wrapper lower
  - `normalize_title_fuzzy(TEXT)` cleanup
  - View `vw_fuzzy_title_candidates` prefilter trigram >=0.85 + year ±1 + 3-char block + author/pages guard
  - Trigger `trg_normalize_dedup_fields` auto-normalizes on insert/update

### 3. BigQuery DDL+UDFs
**Path:** `/mnt/data/b6_dedup_fix_bq.sql`
- JS UDF `normalize_doi(STRING)` same logic as python
- JS UDF `expand_pages(STRING) RETURNS STRUCT<normalized_pages STRING, page_start INT64, page_end INT64>` Bramer expansion
- Table partitioned by `pub_year` RANGE_BUCKET 1900-2030 step 5
- View `vw_fuzzy_title_candidates` uses `EDIT_DISTANCE` <15% length as proxy for 90% similarity

### 4. Integration Patch
**Path:** `/mnt/data/b6_dedup_integration_patch.py`
- Shows drop-in replacement for `pubmed_extraction_pipeline.py` main loop
- Handles post-fetch global dedup with PRISMA counts
- Function `apply_patch_to_original_pipeline()` to generate patched file

### 5. Validation Results
**Path:** `/mnt/data/b6_validation_results.json`
- Sample run on `anesthesia_full_metadata_SAMPLE.jsonl` + artificial duplicates
- Result: DOI normalization dedup caught `10.3390/xxx` vs `https://doi.org/10.3390/XXX`
- End-to-end pipeline unique count reduced correctly

## Execution Validation

```bash
python /mnt/data/b6_dedup_fix_pipeline.py
# runs _test() inside

psql -f /mnt/data/b6_dedup_fix_ddl.sql
# creates tables/functions, test with:
# SELECT normalize_doi('https://doi.org/10.1234/ABC.123');
# SELECT * FROM expand_medline_pages('123-5');
```

## Best Practices from Research (Sources)
- DOI normalization best practice: lowercase + trim + strip `https://doi.org/`, `http://dx.doi.org/`, `doi:` prefix, treat empty as null【4496958085331085771†L5-L7】 and use central normalize function【4496958085331085771†L11-L13】
- Bramer method: validated multi-step strategy Year+Title+Pages etc progression from strict to relaxed【709481239410584569†L10-L27】, achieves 99.5% sensitivity vs default EndNote【5644712711641846085†L40-L42】
- Fuzzy title 90%: industry uses rapidfuzz threshold 90 for strict matching【3107747129211573825†L27-L30】, with fuzzy_scan threshold 90【3107747129211573825†L12-L14】, token sort ratio >=90【3107747129211573825†L56-L60】, and WRatio 92 for title deduplication【3107747129211573825†L68-L70】

## Critical Issues Fixed
- DOI normalization missing -> now production normalized key prevents Type-I duplicate miss when same DOI appears as url vs bare
- Bramer page expansion missing -> now `123-5` equals `123-125` for Bramer Title-Journal-Pages matching (common in PubMed MedlinePgn)
- Fuzzy title 90% missing -> rapidfuzz WRatio >=90 + author/year/page guard catches Type-II duplicate publications in different journals (duplicate publication)
- Also provides audit trail table for PRISMA flow (required by Cochrane/PRISMA per Bramer guide【709481239410584569†L76-L84】)

## Next Steps for Production
- Install rapidfuzz: `pip install rapidfuzz`
- Run pipeline with `include_performance_metrics` handling etc.
- For Postgres, enable `pg_trgm` extension
- For BigQuery, deploy UDFs before loading
- Use `deduplicate_records` as final step after all 16 agents fetch before JSONL save
