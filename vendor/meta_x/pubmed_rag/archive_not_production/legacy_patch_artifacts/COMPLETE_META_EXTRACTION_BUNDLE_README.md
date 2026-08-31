# Complete Meta Extraction Bundle
Version 2.1 Audited - All Extraction Work Included
Generated: 2026-08-28

## This Bundle Contains ALL Extraction Work

### 1. Core Extraction (16-Agent Swarm)
- max-anesthesia-pubmed-extraction.md - Full 16-agent report with query bank, 280k-380k est corpus
- anesthesia_pubmed_schema.json - 18 top-level fields, 60+ subfields JSON Schema Draft 07
- pubmed_extraction_pipeline.py - Original E-utilities pipeline
- anesthesia_full_metadata_SAMPLE.csv/.jsonl - Sample 16 real PMIDs (SPICE III 31112380 etc)
- EXTRACTION_README.md - Full run instructions

### 2. Audit Fixes (4x8 Swarm = 32 Agents)
Critical bugs fixed:
- Rate limits 3/s no-key / 10/s with-key (was inverted)
- WebEnv expiration 200+<ERROR> handling with re-search resume
- DOI normalization (strip doi.org, lower, validate ^10\.)
- Bramer page expansion 123-5→123-125
- Classification FP: \b word boundaries, TAP strict, education trap
- MedlineDate fallback: Year→MedlineDate regex→ArticleDate→PubMedPubDate→EDAT
- ArticleId XPath fix, CollectiveName, itertext

Files:
- b6_dedup_fix_pipeline.py - DOI + Bramer + fuzzy ≥90%
- classification_fix_module.py - regex \b boundaries, MeSH weighting 3.0
- pubmed_client_hardened.py - token bucket + jitter + Retry-After
- agent_b7_rate_limit_fix.py - rate limit fix
- MANIFEST.json - SHA256 inventory

### 3. Database DDLs (Postgres + BigQuery)
- postgres_ddl_anesthesia.sql - 673 lines, 64 tables, 36 indexes, 41 partitions RANGE by year, JSONB GIN, pgvector HNSW m=16 ef_construction=200
- bigquery_ddl_anesthesia_pubmed.sql / bigquery_ddl_anesthesia.sql - PARTITION BY YEAR, CLUSTER BY subdomain/journal/year, STRUCT journal, REPEATED mesh_terms, VECTOR INDEX TREE_AH COSINE, UDFs normalize_doi() + parse_medline_date()
- vector_db_postgres_production.sql - HNSW + IVFFlat fallback
- vector_db_bigquery_production.sql - ARRAY<FLOAT64> + VECTOR INDEX
- postgres_loader_anesthesia.py, etl_loader_postgres_bigquery.py - loaders

### 4. Embeddings & RAG
- pubmedbert_embedding_pipeline.py - PubMedBERT NeuML/pubmedbert-base-embeddings 768-dim normalized batch 32
- metadata_schema.py - Pydantic full schema with MedlineDate fallback
- embedding_pipeline.py, embedding_eval_metrics.py - recall@k/MRR/NDCG
- anesthesia_benchmark_queries.jsonl - 50 queries with qrels SPICE III 31112380 etc graded 0-3
- anesthesia_rag_pipeline/ - RAG with hybrid 0.7 dense + 0.3 BM25, query transform, rerank, CDC watermark EDAT, embedding_backfill

### 5. Handoffs for Next AI
- HANDOFF_PROMPT_FOR_NEXT_MUSE.md - Detailed handoff with placeholder for other AI instructions
- HANDOFF_QUICK_COPY.md - Quick paste version

### 6. Additional Production Code
- anesthesia_pubmed_extractor.py, pubmed_anesthesia_extraction.py, pubmed_client.py, incremental_update_pipeline.py, etc.

## How to Use
1. Unzip
2. Read EXTRACTION_README.md + HANDOFF_PROMPT_FOR_NEXT_MUSE.md
3. Run: pip install biopython pandas tqdm requests sentence-transformers pgvector
4. Export NCBI_API_KEY and run python pubmed_extraction_pipeline.py --max-records 100000 --output ./corpus

## Stats
- Total files: see MANIFEST.json
- Corpus est: 280k-380k before dedup, 180k-250k after
- Journals: Anesthesiology IF 9.1-9.4 23,658 cites, BJA 9.166 20,373 cites, A&A 4.6 22,509 cites
- Landmark trials: GAS 722 infants, BALANCED 6,644 pts BIS 47.2 vs 38.8, SPICE III NEJM 2019, MYRIAD, NAP4

All work from 16-agent + 32-agent audit included.
