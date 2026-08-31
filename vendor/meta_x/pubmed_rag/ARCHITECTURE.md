# PubMed canonical architecture

## Production source path

`pubmed_anesthesia_extraction.py` is the **only active PubMed network extraction implementation**. `metadata_schema.py` is its canonical source model.

The extractor performs ESearch completeness partitioning, EFetch reconciliation, raw-XML hashing, complete query provenance, and preserves every source PMID before optional downstream classification. A capped query is `TRUNCATED`, never `PASS`.

## Enrichment boundary

`pubmedbert_embedding_pipeline.py` is an optional enrichment component and is not needed to certify source extraction. No embedding model, vector dimension, classifier score, or RAG answer is source truth.

The older Meta parallel PubMed clients, CDC pipeline, ETL schemas, search API, RAG demo, and alternative embedding stacks are preserved under `archive_not_production/legacy_parallel_stacks_2026-08-29/`. They cannot be invoked by the frontier preflight.

## Warehouse

All new warehouse targets are defined centrally in `../schema/frontier_postgres.sql` and `../schema/frontier_bigquery.sql`; legacy PubMed-specific DDL is archived.

## Enrichment boundary

`experimental_enrichment_not_certified/` is not part of source extraction or frontier
source preflight. No source run may fabricate or infer an embedding, classification,
summary, or RAG answer. Model derivatives must enter `frontier.model_enrichment` only
after a separate enrichment certification pass.
