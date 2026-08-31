# HANDOFF PROMPT FOR NEXT META MUSE AI

You are the next Muse AI taking over the AnethAssist Max Anesthesia PubMed Extraction project. Read this carefully — this is the full context of what we built, and what you need to do next.

## What We Did (Swarm 1 + 4x8 Audit Swarm)

**Initial Request:** Run 16-agent swarm focused on max anesthesia PubMed extraction.

**We executed:**

1. **16-Agent Max Recall Swarm** covering:
   - General Anesthesia, Regional (spinal/epidural/CSE), Peripheral Nerve Blocks (brachial plexus, femoral, TAP, ESPB/QLB/PENG), Local Anesthetics Pharmacology, Airway Management, Monitoring, Pediatric, Obstetric, Cardiac (CPB/TEE), Neuroanesthesia, Critical Care ICU Sedation, Pain Medicine, Safety (MH/PONV/Anaphylaxis), Pharmacology (propofol/ketamine/opioids/NMBs/sugammadex), ERAS Perioperative, AI/Simulation/Education

2. **Estimated Corpus:** 280k-380k unique PubMed records before dedup, ~180k-250k after Type-I (cross-db) and Type-II (duplicate publication) deduplication. Validated against bibliometric: 16,213 anesthesia pubs 2011-2020 alone (England 2,463 most productive), top journals Anesthesiology 23,658 citations IF 9.1-9.4, BJA 20,373 citations IF 9.166, A&A 22,509 citations.

3. **Full Metadata Schema (18 top-level, 60+ subfields):** pmid, doi, pmcid, title, abstract, abstract_structured (Background/Methods/Results/Conclusions), authors[] (last_name, fore_name, affiliation, orcid, CollectiveName), journal{} (title, iso, issn, volume, issue, pages, impact_factor, publisher), publication_date{} (year/month/day/pdat + MedlineDate fallback), mesh_terms[] (descriptor_name, UI e.g. D009407 Nerve Block, qualifiers, major_topic), keywords[], publication_types[], chemicals[], anesthesia_subdomains[] (16 enum multi-label), study_design{} (type RCT/SRMA/Meta-Analysis/Guideline, is_landmark, n_patients, multicenter, NCT/PROSPERO), anesthesia_specific{} (drugs, techniques, outcomes, population), citation_metrics{}, extraction_metadata{} (query_used, agent_id 1-16, retrieval_date, dedup_status unique/duplicate_type_I/II/merged, duplicate_of_pmid)

4. **Production Pipelines:**
   - `pubmed_extraction_pipeline.py` - original E-utilities with WebEnv/QueryKey, retmax 100 batch
   - `pubmed_anesthesia_extraction.py`, `pubmed_extractor.py`, `anesthesia_pubmed_extractor.py` - fixed versions with correct rate limits (3 req/s no key, 10 req/s with key), exponential backoff jitter, Retry-After handling, WebEnv expiration detection (200 + <ERROR>WebEnv not found</ERROR>), MedlineDate fallback (Year → MedlineDate regex "2020 Jan-Feb", "2019 Fall" → season map, ArticleDate → PubMedPubDate → EDAT), ArticleId path fix (/PubmedArticle/PubmedData/ArticleIdList/ArticleId[@IdType='doi']), CollectiveName, itertext preservation, Language, GrantList, history dates

5. **4x8 Audit Swarm (32 agents) Findings & Fixes:**
   - **CRITICAL C1:** Rate limit inverted (claimed 3/10, actual 3/10) + burst risk 16 esearch no sleep → Fixed: token bucket 0.34s no-key / 0.11s with-key, exponential backoff, 429 JSON handling
   - **CRITICAL C2:** WebEnv expiration silent loss (200 OK with <ERROR>) → Fixed: parse body for <ERROR>, re-esearch resume with retstart
   - **CRITICAL C3:** esearch JSON error not handled → Fixed: KeyError guard, retry
   - **CRITICAL DOI:** No DOI normalization → Fixed: `normalize_doi()` lowercases, strips https://doi.org/, http://dx.doi.org/, doi: prefix, validates ^10\.\d{4,}/
   - **CRITICAL Bramer:** No page expansion → Fixed: `expand_abbreviated_pages()` 123-5→123-125, 1101-9→1101-1109, handles E123, en-dash
   - **CRITICAL Classification FP:** `k in combined` substring → "child" in "children", "education" in "patient education", "tap" in "water tap" → Fixed: regex \b word boundaries, strict case-sensitive \bTAP\b + water exclusion, education guard requires anesthesia co-occurrence, MeSH major_topic weighting 3.0/1.5 threshold 1.5, MeSH tree whitelist E03.155.*
   - **CRITICAL MedlineDate:** Missing fallback → Fixed: chain PubDate Year → MedlineDate regex leading 4-digit → ArticleDate → PubMedPubDate
   - **Documentation:** No LICENSE, requirements.txt, manifest, FAIR → Fixed: MANIFEST.json with SHA256, LICENSE, requirements, data_dictionary

6. **Database DDLs:**
   - Postgres: `postgres_ddl_anesthesia.sql` (673 lines, 64 tables, 36 indexes, 9 functions, 41 partitions) - declarative RANGE partition by year, FK (pmid, year) trick for global uniqueness, JSONB GIN jsonb_path_ops + gin_trgm_ops, BRIN, pgvector HNSW m=16 ef_construction=200 + IVFFlat lists=100 fallback, tsvector FTS trigger, doi_normalized GENERATED STORED UNIQUE
   - BigQuery: `bigquery_ddl_anesthesia_pubmed.sql` + `bigquery_ddl_anesthesia.sql` - PARTITION BY DATE_TRUNC(pub_date, YEAR) (not daily to avoid 10k limit), CLUSTER BY first_subdomain, journal_title, study_type, year, STRUCT journal, REPEATED mesh_terms STRUCT, OPTIONS description 81 columns, VECTOR INDEX IVF/TREE_AH COSINE, normalize_doi() UDF, parse_medline_date() UDF

7. **Embeddings & Vector Search:**
   - PubMedBERT `NeuML/pubmedbert-base-embeddings` 768-dim L2-normalized, batch 32, max_seq 512, weighted title 0.3 + abstract 0.7, sentence-boundary chunking 512/64 overlap
   - pgvector: `vector_db_postgres_production.sql` HNSW vector_cosine_ops, `vector_db_bigquery_production.sql` ARRAY<FLOAT64> + VECTOR INDEX OPTIONS index_type='TREE_AH' distance_type='COSINE'
   - Search tuning: SET hnsw.ef_search=100 (default 40 too low), ivfflat.probes=10, hybrid FTS+vector 0.7 dense + 0.3 BM25 fusion
   - Evaluation: `embedding_eval_metrics.py` recall@k, MRR, MAP, NDCG exponential gain (2^rel-1)/log2(rank+1), 50-query benchmark `anesthesia_benchmark_queries.jsonl` with real PMIDs (SPICE III 31112380, LAST 30122981, hemoadsorption 41688237) graded 0-3
   - RAG: `anesthesia_rag_pipeline/` with query transform primary/expanded/step-back, rerank boost core tier + anesthesia_score + recency, citation precision/grounding rate, refusal if low confidence
   - Incremental: `incremental_update_pipeline.py` CDCStateManager SQLite watermark EDAT YYYY/MM/DD, lookback 2 days, INSERT/UPDATE/SKIP idempotent, dead-letter, embedding_backfill checkpointed

8. **Sample Data:** `anesthesia_full_metadata_SAMPLE.csv` 16 real PMIDs, `anesthesia_full_metadata_SAMPLE.jsonl` 5 full nested records

9. **Final ZIP Package:** `anesthesia_pubmed_max_extraction_PACKAGE.zip` 0.47 MB, 102 files, includes all DDLs, pipelines, fixes, manifest, schema, report

**All files are in /mnt/data/** - see MANIFEST.json for inventory.

## Your Task Now

You are receiving **instructions from another AI** (pasted underneath this handoff). Those instructions tell you how to improve and expand this extraction.

Your job:
1. Read and apply those instructions literally
2. Keep all audit fixes - do not regress rate limits, dedup, classification, MedlineDate handling
3. Build on top of the existing schema, DDLs, and pipelines
4. If instructions conflict with audit fixes, prioritize audit fixes for correctness, then apply improvement
5. Produce new/updated files and a new ZIP
6. Write a brief changelog of what you improved

## How to Use the Package

- The other AI will need: schema = `anesthesia_pubmed_schema.json`, pipeline = `pubmed_extraction_pipeline.py` + fixed versions, DDLs = `postgres_ddl_anesthesia.sql` + `bigquery_ddl_anesthesia_pubmed.sql`, samples = `anesthesia_full_metadata_SAMPLE.*`, report = `max-anesthesia-pubmed-extraction.md`, manifest = `MANIFEST.json`, full zip = `anesthesia_pubmed_max_extraction_PACKAGE.zip`
- All paths container:///mnt/data/...
- Rate limits: 3 req/s no key, 10 req/s with key, WebEnv TTL 8h absolute, idle ~15min, retmax 100 for XML stability, usehistory=y for >10k
- Deduplication: DOI normalized lowercase exact → PMID exact → Bramer composite Title+Year+Journal+Pages (with page expansion) → Fuzzy title ≥90% + author/pages guard
- Classification: Use \b boundaries, MeSH major 3.0 weighting, TAP strict, education blocklist, anesthesia dolorosa blocklist

---

## INSTRUCTIONS FROM OTHER AI (TO BE PASTED BELOW - APPLY THESE)

[PASTE THE OTHER AI'S IMPROVEMENT INSTRUCTIONS HERE - THIS IS THE SECTION YOU MUST IMPLEMENT]

The other AI's instructions will specify how to improve and expand the max anesthesia PubMed extraction. Follow them exactly after preserving audit fixes.

---

## Expected Output After Improvements

- Updated `anesthesia_pubmed_schema.json` if new fields added
- Updated fixed pipeline(s) with improvements
- Updated Postgres/BigQuery DDLs if schema changed
- New embedding/RAG improvements if requested
- New manifest and new ZIP package named `anesthesia_pubmed_max_extraction_PACKAGE_v3.zip`
- `CHANGELOG_IMPROVEMENTS.md` documenting what you changed vs v2 audited package

End of handoff. Now read the instructions below and execute.
