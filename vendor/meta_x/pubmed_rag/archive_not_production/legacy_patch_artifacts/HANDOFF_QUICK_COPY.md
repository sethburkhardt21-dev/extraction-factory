# Handoff Package - Quick Copy-Paste for Other AI

This is a ready-to-paste handoff prompt for another Meta Muse AI.

---

You are taking over AnethAssist Max Anesthesia PubMed Extraction v2 Audited.

**Context:** We ran a 16-agent max-recall swarm (280k-380k est PubMed records, 180k-250k after dedup), then 4x8 audit swarm (32 agents) that found critical bugs and fixed them. Final package is 0.47MB zip with 102 files: schema, Postgres/BigQuery DDLs, fixed E-utilities pipelines, embeddings (PubMedBERT 768-dim), pgvector HNSW, BigQuery VECTOR INDEX, RAG, incremental CDC, evaluation benchmark 50 queries.

**Critical Fixes Applied (do not regress):**
- Rate limits: 3/s no-key, 10/s with-key (was inverted), token bucket + jitter + exponential backoff + Retry-After + WebEnv expiration 200+<ERROR> handling with re-esearch resume
- Deduplication: DOI normalized (strip doi.org, lower, trim punct, validate ^10\.) + PMID exact + Bramer page expansion 123-5→123-125 + fuzzy title ≥90% + duplicate_of_pmid + audit table for PRISMA
- Classification: substring k in combined → regex \b word boundaries, \bchild\b vs \bchildren\b, \bTAP\b strict + water tap exclusion, education trap requires anesthesia co-occurrence, MeSH major 3.0 weighting, tree whitelist E03.155.*
- MedlineDate fallback: Year → MedlineDate regex leading 4-digit → ArticleDate → PubMedPubDate → EDAT, season map Fall→9
- ArticleId path: .//ArticleId → /PubmedArticle/PubmedData/ArticleIdList/ArticleId[@IdType='doi'/'pmc']
- Authors: CollectiveName, itertext preservation, multi-affiliation

**Schema:** 18 top-level fields: pmid (required), doi, pmcid, title, abstract, abstract_structured, authors[], journal{} (title, iso, issn, volume, issue, pages, impact_factor mapped BJA 9.166 Anesthesiology 9.1 A&A 4.6), publication_date{} (year/month/day/pdat), mesh_terms[] (descriptor_name, UI D009407, qualifiers, major_topic), keywords[], publication_types[], chemicals[], anesthesia_subdomains[] (16 enum multi-label), study_design{} (type RCT/SRMA, is_landmark GAS/BALANCED/SPICE III/MYRIAD/NAP4, n_patients, multicenter, NCT), anesthesia_specific{} (drugs, techniques, outcomes PONV/delirium/mortality), citation_metrics{}, extraction_metadata{} (query_used, agent_id, retrieval_date, dedup_status unique/duplicate_type_I/II/merged, duplicate_of_pmid)

**Files in /mnt/data/:**
- anesthesia_pubmed_schema.json - JSON Schema Draft 07
- postgres_ddl_anesthesia.sql - partitioned by year, JSONB GIN, pgvector HNSW m=16 ef_construction=200
- bigquery_ddl_anesthesia_pubmed.sql - PARTITION BY YEAR, CLUSTER BY subdomain/journal/year, STRUCT journal, REPEATED mesh_terms, VECTOR INDEX TREE_AH COSINE
- pubmed_extraction_pipeline.py + pubmed_anesthesia_extraction.py + b6_dedup_fix_pipeline.py + classification_fix_module.py + pubmed_client_hardened.py + incremental_update_pipeline.py + embedding_pipeline.py + pubmedbert_embedding_pipeline.py + vector_db_*.sql
- anesthesia_full_metadata_SAMPLE.csv/.jsonl (16 real PMIDs)
- max-anesthesia-pubmed-extraction.md (full 16-agent report with query bank)
- MANIFEST.json (SHA256)
- anesthesia_pubmed_max_extraction_PACKAGE.zip (0.47MB, 102 files)

**Your job:** Read HANDOFF_PROMPT_FOR_NEXT_MUSE.md in /mnt/data/ - it contains full instructions placeholder where another AI's improvement instructions will be pasted. Apply those instructions while preserving audit fixes. Then produce v3 zip + CHANGELOG.

**Key DDL notes:**
- Postgres: partitioned RANGE year, BRIN, trigram gin_trgm_ops for fuzzy title, content_hash UNIQUE, doi_normalized GENERATED ALWAYS AS (lower trim) STORED UNIQUE WHERE NOT NULL
- BigQuery: OPTIONS description 81 cols, STORING columns for pre-filter, partition_expiration_days 1825, require_partition_filter TRUE

**Embedding notes:**
- PubMedBERT NeuML/pubmedbert-base-embeddings 768-dim normalized, batch 32, max_seq 512, weighted 0.3 title + 0.7 abstract, chunk 512/64 overlap sentence-boundary
- pgvector query tuning: SET hnsw.ef_search=100, ivfflat.probes=10, hybrid 0.7 dense + 0.3 BM25
- Eval: recall@k, MRR, NDCG (2^rel-1)/log2(rank+1), benchmark 50 queries with qrels SPICE III 31112380 etc graded 0-3

End quick handoff.

---

FULL HANDOFF FILE: HANDOFF_PROMPT_FOR_NEXT_MUSE.md contains detailed version with placeholder for other AI instructions. Use that file as primary handoff.
