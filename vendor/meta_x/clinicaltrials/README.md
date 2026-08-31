# ClinicalTrials.gov canonical extractor — repaired

Key repairs:
- no false-success bulk mode: JSON ZIP is actually parsed and canonicalized
- crash-safe immutable page shards; checkpoint advances only after page files are durable
- checkpoint is bound to a query fingerprint
- start/end `/api/v2/version` provenance and source-drift flag
- `last_update_post_date` retained for public-registry synchronization
- preserves `hasResults=false` and all phase values
- page size validated to 1..1000
- retry is bounded and honors Retry-After; no invented hard CTG rate-limit claim

Run offline tests: `python -m pytest -q tests/test_offline.py`
