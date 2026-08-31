# Vector DB Architect - Production Deliverables - Validation Summary

## Files Generated

### 1. Postgres pgvector Production DDL
- **Path**: `/mnt/data/vector_db_postgres_production.sql`
- **Features**:
  - `CREATE EXTENSION vector` (>=0.5.0 for HNSW)
  - Full metadata schema: pmid, pmcid, doi, content_hash (dedup), title_hash, authors JSONB with CollectiveName, journal, dates with MedlineDate raw, mesh_terms JSONB with MajorTopicYN, tree numbers, keywords, chemicals, grants, anesthesia classification fields
  - Enums: `date_parse_method` (pubdate_year_month, article_date, medline_date_full, medline_date_range_start, medline_date_season, fallback_regex, unknown), `anesthesia_class`
  - Dedup: UNIQUE on `content_hash`, UNIQUE on `doi_normalized WHERE NOT NULL`, `pubmed_dedup_log` table, title trigram GIN
  - Fetch audit: `pubmed_fetch_audit` with had_rate_limit, retry_count, backoff_ms - fixes rate limit audit
  - Classification audit: `anesthesia_classification_audit` tracks FP risk
  - Indexes:
    - B-tree: pub_year, is_anesthesia, journal, fetch_timestamp
    - GIN: mesh_major_terms, mesh_tree_numbers, anesthesia_types_text, keywords, pub_types, authors jsonb_path_ops, false_positive_flags
    - FTS: tsvector generated from title+abstract+mesh_major, trigger update_search_vector
    - Trigram: title gin_trgm_ops for near-dedup
    - **HNSW primary**: `idx_articles_embedding_hnsw_cosine` USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=200) - tuned for prod >100k (default 64 too low)
    - **IVFFlat fallback**: commented example WITH (lists=100) - lists = sqrt(n) heuristic; requires data before build; probes tuning at query time
  - Performance: `maintenance_work_mem = '2GB'` note to avoid "hnsw graph no longer fits" NOTICE causing 10-100x slower disk build
  - Query examples: filtered HNSW search with `SET hnsw.ef_search=100`, IVFFlat `SET ivfflat.probes=10`, hybrid FTS+vector, pre-filter using has_anesthesia_mesh to mitigate FP
  - Materialized view `mv_anesthesia_stats` for monitoring date fallback count

### 2. BigQuery VECTOR Index Production DDL
- **Path**: `/mnt/data/vector_db_bigquery_production.sql`
- **Features**:
  - Table `pubmed_anesthesia_articles` with `embedding ARRAY<FLOAT64>` NOT NULL (BQ requirement: all same dim, non-NULL elements), partitioned by RANGE_BUCKET pub_year 5-year buckets, clustered by is_anesthesia, has_anesthesia_mesh, journal_iso
  - Dedup view `v_dedup_check` grouping by content_hash
  - **VECTOR INDEX IVF primary**: 
    ```sql
    CREATE VECTOR INDEX idx_embedding_ivf_cosine ON ... (embedding) STORING (pmid, title, is_anesthesia, has_anesthesia_mesh, pub_year...) OPTIONS(index_type='IVF', distance_type='COSINE', ivf_options='{"num_lists":1000}')
    ```
    Best practice: num_lists 100 for 10k, 316 for 100k, 1000 for 500k-1M; controls tuning granularity
  - **Hybrid IVF**: same with `lexical_search_columns = '["search_text","title"]'` for hybrid 70% vector 30% lexical
  - **TreeAH (ScaNN)**: `index_type='TREE_AH'` with `leaf_node_embedding_count=1000, normalization_type='L2'` - 10-100x faster for large batch (100s+ query vectors), batch queries via TABLE query_embeddings, options `fraction_leaves_to_search`
  - Query patterns: `VECTOR_SEARCH` with `top_k`, `distance_type='COSINE'`, `fraction_lists_to_search => 0.1` for high recall, `use_brute_force=false`, hybrid enable
  - Monitoring via `INFORMATION_SCHEMA.VECTOR_INDEXES`
  - Autonomous embedding alternative with `AI.EMBED` generated column
  - Audit tables partitioned/clustered mirrored from Postgres

### 3. Extraction Pipeline - Fixes All Audit Critical Issues
- **Path**: `/mnt/data/anesthesia_extraction_pipeline.py`
- **Fixes**:
  - **Rate limits**: `RateLimiter` token bucket 3/s no-key 10/s with key, honors `Retry-After` header, exponential backoff with jitter (1s,2s,4s,8s... max 30s), audit log of backoff_ms and http status codes in `pubmed_fetch_audit`
  - **MedlineDate fallback**: Function `parse_pub_date` chain: PubDate Year+Month+Day -> Year+Month -> Year -> ArticleDate -> MedlineDate regex extraction of leading year from ranges like "2021-2022", season mapping Fall/Spring, `medline_date_range_start`, `medline_date_season`, `medline_date_fallback_regex`; last ditch search `<MedlineDate>` raw XML regex; never leaves pub_year NULL if parse possible; date_parse_method enum tracks which path used for audit
  - **CollectiveName fallback**: `parse_authors` handles ForeName LastName -> LastName -> CollectiveName chain, ORCID extraction, affiliation; stores collective_author separate
  - **AbstractText labeled**: `parse_abstract` uses `itertext()` to preserve <i>, <b>, <sup> inner text (fixes tag stripping bug), keeps Label and NlmCategory, joins as "BACKGROUND: text" to preserve structure
  - **Dedup**: `compute_content_hash` sha256(normalized title+abstract), title_hash, doi_normalized lower without prefix; `DedupManager` in-memory + DB unique constraints; `ON CONFLICT` handling with fallback one-by-one insertion and logging to `pubmed_dedup_log`
  - **Classification FP**: `classify_anesthesia` mitigates false positives:
    - Whitelist MeSH UI D000758 etc + tree prefix E03.155.*
    - Requires MajorTopicYN=Y for anesthesia for threshold 0.35, minor mesh raises threshold to 0.65, no mesh requires 0.80 + title keyword
    - Positive keyword patterns with type extraction, title boost
    - Negative patterns: "without anesthesia", "anesthesia dolorosa" -> score -0.4, flags dolorosa_fp
    - Flags: no_anesthesia_mesh, no_major_topic, low_mesh_confidence, negative_pattern_matched, stored in false_positive_flags JSONB
    - Produces anesthesia_types, score, reasoning
- **pgvector/BigQuery ready**: `prepare_for_pgvector` adds embedding (stub deterministic for offline testing, replace with OpenAI), normalized for cosine; `prepare_for_bigquery` adds search_text concatenation
- **Client**: `PubMedClient.esearch` + `efetch_batch` with chunk 200, retry handling for 429/503, chunked parsing

### 4. Ops & Config Helper
- **Path**: `/mnt/data/vector_db_config_and_ops.py`
- Contains:
  - `PGVECTOR_INSERT_SQL` with `ON CONFLICT (pmid) DO UPDATE` + content_hash unique handling
  - `INDEX_MIGRATION_SQL` migration script CONCURRENTLY with maintenance_work_mem 2GB, dropping old, creating HNSW, optional IVFFlat, query tuning SET commands
  - Python bulk_upsert with UniqueViolation handling, dedup_log insert
  - Production search function with FP filter `has_anesthesia_mesh=TRUE` and `SET hnsw.ef_search=100`
  - Production checklist covering all audit fixes and tuning

## Validation

- SQL syntax checked: pgvector extension, HNSW WITH (m=16, ef_construction=200), IVFFlat WITH (lists=100), GIN/trigram/FTS indexes, enums, triggers
- BigQuery DDL validated against docs: CREATE VECTOR INDEX syntax with STORING, OPTIONS index_type IVF/TREE_AH, distance_type COSINE, ivf_options num_lists, tree_ah_options leaf_node_embedding_count + normalization_type, lexical_search_columns for hybrid
- Python pipeline: parses sample MedlineDate formats via regex year extraction, handles 429 retry, CollectiveName fallback present, itertext() for abstract, content_hash dedup logic implemented
- FP mitigation: MeSH major topic required logic implemented, negative pattern detection, threshold tiered
- Rate limit: token bucket + backoff + Retry-After honored

## Best Practice Highlights Used (from search)

- HNSW default for production read-heavy RAG up to 10M, IVFFlat for write-heavy/memory-constrained (from pgvector docs)
- maintenance_work_mem 2GB before HNSW build to avoid disk fallback 10-100x slower (observed at 78k tuples 1536-dim with 64MB default)
- HNSW tuning: m=16 default correct, ef_construction 200-400 for high quality (not 64), ef_search 100 at query (not 40 default) - from Supabase tuning guide
- IVFFlat lists = sqrt(rows) heuristic, probes=10 at query, requires data before index creation (training)
- BigQuery VECTOR: 5000 rows minimum, IVF for small batch, TreeAH (ScaNN) for large batch 100s+ queries, fraction_lists_to_search for recall tuning, storing columns for pre-filter without table lookup, product quantization for latency reduction
