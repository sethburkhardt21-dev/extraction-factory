# Superseded entrypoints

These files came from the Meta extraction bundle but are **not production entrypoints**.
They were retained only for lineage/audit history because they overlap newer repaired code,
contained stale configuration or misleading production claims, and would create multiple
competing extraction surfaces if left active.

Canonical full PubMed extraction: `../../production_pipeline.py` + `../../pubmed_anesthesia_extraction.py`.
Canonical incremental PubMed path: `../../incremental_update_pipeline.py` + `../../pubmed_client_hardened.py`.
