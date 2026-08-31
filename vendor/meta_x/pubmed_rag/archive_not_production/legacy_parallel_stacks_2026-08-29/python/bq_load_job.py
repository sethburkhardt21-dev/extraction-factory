"""
BigQuery Load Job for Max Anesthesia PubMed Extraction
Loads transformed JSONL to partitioned clustered table
"""

import argparse
import json
import pathlib
from datetime import datetime
from typing import Iterator
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bigquery_pubmed_helpers import transform_jsonl_record_to_bq_row

def iter_bq_rows(jsonl_path: pathlib.Path) -> Iterator[dict]:
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            bq_row = transform_jsonl_record_to_bq_row(rec)
            yield bq_row

def write_bq_jsonl(input_path: pathlib.Path, output_path: pathlib.Path, limit=None):
    count = 0
    with open(output_path, 'w', encoding='utf-8') as out:
        for bq_row in iter_bq_rows(input_path):
            out.write(json.dumps(bq_row, ensure_ascii=False) + "\n")
            count += 1
            if limit and count >= limit:
                break
    print(f"Wrote {count} BQ rows to {output_path}")

def load_to_bigquery(bq_jsonl_path: pathlib.Path, project: str, dataset: str, table: str):
    try:
        from google.cloud import bigquery
    except ImportError:
        print("google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery")
        print(f"Instead, use bq CLI: bq load --source_format=NEWLINE_DELIMITED_JSON {dataset}.{table} {bq_jsonl_path}")
        return

    client = bigquery.Client(project=project)
    table_id = f"{project}.{dataset}.{table}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        # Schema autodetect can be used, but we have DDL already created, so use:
        autodetect=False,
        # Partitioning handled by DDL table definition, not needed here
    )

    # Define schema explicitly matching DDL for safety (subset for example)
    # In prod, schema is already defined via DDL, so autodetect=False with existing table works
    job_config.schema_update_options = [
        bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION
    ]

    with open(bq_jsonl_path, "rb") as source_file:
        job = client.load_table_from_file(source_file, table_id, job_config=job_config)

    job.result()
    print(f"Loaded {job.output_rows} rows to {table_id}")

    # After load, embeddings generation (optional batch)
    # Example: use bigquery ML.GENERATE_EMBEDDING
    embedding_query = f"""
    -- Generate embeddings for rows without embeddings
    -- Requires Vertex AI connection and embedding model
    -- UPDATE `{project}.{dataset}.{table}`
    -- SET title_abstract_embedding = ML.GENERATE_EMBEDDING(...)
    """
    print("Embedding generation query template:", embedding_query)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transform anesthesia JSONL to BQ and load")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL path produced from a provenance-verified extraction")
    parser.add_argument("--bq-jsonl", type=str, default="/tmp/anesthesia_bq.jsonl", help="Intermediate BQ JSONL")
    parser.add_argument("--project", type=str, default="anesthesia_prod", help="GCP project")
    parser.add_argument("--dataset", type=str, default="pubmed", help="BQ dataset")
    parser.add_argument("--table", type=str, default="anesthesia_pubmed_max", help="BQ table")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows for testing")
    parser.add_argument("--dry-run", action="store_true", help="Only transform, don't load to BQ")
    args = parser.parse_args()

    input_path = pathlib.Path(args.input)
    bq_jsonl_path = pathlib.Path(args.bq_jsonl)

    write_bq_jsonl(input_path, bq_jsonl_path, limit=args.limit)

    if not args.dry_run:
        load_to_bigquery(bq_jsonl_path, args.project, args.dataset, args.table)
    else:
        print("Dry run complete, BQ JSONL ready for bq load CLI")
