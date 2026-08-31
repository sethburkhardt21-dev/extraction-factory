"""Validate central frontier BigQuery schema without executing BigQuery."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
DDL=ROOT/"schema"/"frontier_bigquery.sql"


def validate_bigquery_schema():
    text=DDL.read_text(encoding="utf-8")
    required_tables=[
        "ingestion_run","run_artifact","source_record","source_observation","canonical_record",
        "quarantine_record","ctg_study_record","ctg_study_snapshot","pubmed_record","pubmed_snapshot",
        "preprint_record","preprint_snapshot","drug_source_record","drug_candidate","drug_candidate_linkage_evidence",
        "research_work","work_source_link","model_enrichment","release_snapshot","release_run",
    ]
    missing=[t for t in required_tables if not re.search(rf"CREATE TABLE IF NOT EXISTS frontier\.{re.escape(t)}\b",text,re.I)]
    return missing, text


def test_frontier_bigquery_schema_contract():
    missing,text=validate_bigquery_schema()
    assert not missing, missing
    assert "raw_xml STRING NOT NULL" in text
    assert "source_payload JSON NOT NULL" in text
    assert "model_enrichment" in text
    assert "PARTITION BY" in text and "CLUSTER BY" in text


def main():
    missing,_=validate_bigquery_schema()
    if missing:
        print("FAIL missing tables:", ", ".join(missing)); return 1
    print("PASS frontier BigQuery structural validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
