"""Offline validator for the canonical PubMed source path. No network calls."""
from __future__ import annotations
from pathlib import Path

BASE = Path(__file__).resolve().parent
REQUIRED = [
    "metadata_schema.py",
    "pubmed_anesthesia_extraction.py",
    "requirements.txt",
    "ARCHITECTURE.md",
]
FORBIDDEN_ACTIVE = [
    "pubmed_client.py",
    "pubmed_client_hardened.py",
    "ingestion_pipeline.py",
    "incremental_update_pipeline.py",
    "production_pipeline.py",
    "embedding_engine.py",
]


def validate_files() -> None:
    missing=[name for name in REQUIRED if not (BASE/name).is_file() or (BASE/name).stat().st_size == 0]
    if missing:
        raise AssertionError(f"missing/empty canonical PubMed files: {missing}")
    active=[name for name in FORBIDDEN_ACTIVE if (BASE/name).exists()]
    if active:
        raise AssertionError(f"competing legacy PubMed production paths are active: {active}")
    extractor=(BASE/"pubmed_anesthesia_extraction.py").read_text(encoding="utf-8")
    for token in ("esearch_all", "one day still exceeds", "EFetch reconciliation failed", "source_record_sha256"):
        if token not in extractor:
            raise AssertionError(f"canonical extractor missing invariant: {token}")
    schema=(BASE/"metadata_schema.py").read_text(encoding="utf-8")
    for token in ("retrieval_queries", "raw_xml"):
        if token not in schema:
            raise AssertionError(f"canonical metadata schema missing invariant: {token}")
    for token in ("embedding_model", "embedding_vector", "anesthesia_classification", "duplicate_of"):
        if token in schema:
            raise AssertionError(f"source metadata schema contains downstream enrichment field: {token}")
    print("PASS canonical PubMed source-path validation")


if __name__ == "__main__":
    validate_files()
