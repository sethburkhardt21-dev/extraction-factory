# Repaired Meta PubMed / RAG bundle

This tree is lineage-cleaned from the supplied Meta bundle. Superseded `_1`, `_1_1`, `_2` copies, unsafe entrypoints,
stale manifests, and misleading production docs have been removed from the active path or moved to
`archive_not_production/`.

## Canonical production paths

### Full PubMed anesthesia extraction

- `production_pipeline.py`
- `pubmed_anesthesia_extraction.py`
- `metadata_schema.py`
- `pubmedbert_embedding_pipeline.py`

A full run requires a real `--email` contact. The canonical extractor:

- honors NCBI's default 3 req/s no-key / 10 req/s keyed policy with safety margin;
- respects `Retry-After` and bounded retry;
- does not pretend PubMed ESearch can expose UIDs beyond its 10,000-record per-query ceiling;
- recursively partitions explicitly bounded publication-date ranges when a query exceeds 10,000 records;
- fails closed if a single day still exceeds the ESearch ceiling;
- verifies every EFetch batch returns exactly the requested PMIDs;
- preserves every source PMID even when title/DOI heuristics flag a possible duplicate;
- stores raw per-record XML plus SHA-256 provenance;
- preserves all candidate records before the anesthesia classification projection;
- marks intentional caps as `TRUNCATED`, never `PASS`.

Example full domain-bounded run:

```bash
export NCBI_EMAIL='real-contact@example.org'
python production_pipeline.py --email "$NCBI_EMAIL" --output ./data/outputs/anesthesia_max
```

An explicit `--max-ids-per-query N` is for development/inspection and makes the extraction manifest `TRUNCATED`
when the source contains more than N records.

### Incremental PubMed ingestion

Use `incremental_update_pipeline.py` with a real `NCBI_EMAIL`; it uses the hardened client and persisted state.

### RAG

`anesthesia_rag_pipeline/` is retrieval scaffolding. Demo records require explicit `--demo`. Production paths do not
auto-load quarantined synthetic artifacts. No LLM generation backend is configured or certified; generation fails closed.

### Embeddings

Embedding code fails closed when a real embedding backend/model is unavailable; it does not manufacture vectors.

## Archived material

`archive_not_production/` contains historical Meta entrypoints, stale documentation, and untrusted/demo generated artifacts.
Nothing under that directory is production evidence.

Run the local suite:

```bash
python -m pytest -q c5_validation_tests.py bigquery_validation_test.py tests/test_repaired_invariants.py
python validate.py
python validate_pipeline.py
```
