"""Production DAG template plus offline validation for the repaired pipeline."""
from __future__ import annotations
from pathlib import Path

BASE = Path(__file__).resolve().parent
DAG_CODE = r'''
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from pathlib import Path
import os

def run_incremental(**ctx):
    from incremental_update_pipeline import AnesthesiaPubMedIncrementalPipeline
    pipeline = AnesthesiaPubMedIncrementalPipeline(
        tool="AnesthesiaRAG_C6",
        email=os.environ["NCBI_EMAIL"],
        api_key=os.getenv("NCBI_API_KEY"),
        lookback_days=2,
    )
    return pipeline.run_incremental()

def run_embedding_backfill(**ctx):
    # Real-model path only. Missing credentials/model dependencies fail the task;
    # no deterministic pseudo-embeddings are generated.
    from pathlib import Path
    from embedding_loader import load_embeddings_postgres
    dsn = os.environ["POSTGRES_DSN"]
    corpus = Path(os.environ["ANESTHESIA_CORPUS_PATH"])
    return load_embeddings_postgres(
        corpus, dsn,
        os.getenv("EMBEDDING_MODEL", "NeuML/pubmedbert-base-embeddings"),
        int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
        dry_run=False,
    )

default_args = {
    "owner": "anesthesia-rag",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}
with DAG(
    dag_id="anesthesia_pubmed_cdc_daily",
    default_args=default_args,
    start_date=datetime(2026,1,1),
    schedule="0 3 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["pubmed","anesthesia","cdc","embedding"],
) as dag:
    incremental = PythonOperator(task_id="pubmed_incremental", python_callable=run_incremental)
    backfill = PythonOperator(task_id="embedding_backfill", python_callable=run_embedding_backfill)
    incremental >> backfill
'''

def validate() -> None:
    for module in ["anesthesia_pubmed_schema","pubmed_client_hardened","incremental_update_pipeline","embedding_loader"]:
        __import__(module)
    from anesthesia_pubmed_schema import parse_pubmed_date_hardened, PubMedAnesthesiaRecord, PubDateInfo, JournalInfo, AnesthesiaClassification
    tests=[
        (None,"2021-2022",None,2021),
        (None,"2024 Spring",None,2024),
        (None,"Fall 2022",None,2022),
        ({"Year":"2020","Month":"Jan"},None,None,2020),
        (None,None,{"Year":"2019"},2019),
    ]
    for pubdate, medline, article_date, expected in tests:
        got=parse_pubmed_date_hardened(pubdate,medline,article_date,None,None)
        assert got.year==expected, (pubdate,medline,got.year,expected)
    from pubmed_client_hardened import PubMedHardenedClient
    client=PubMedHardenedClient(email="offline-validator@example.invalid")
    client.load_existing_keys({"12345"},{"10.1000/xyz"},{"abc"})
    rec=PubMedAnesthesiaRecord(pmid="12345",doi="10.1000/xyz",title="Test",pub_date=PubDateInfo(year=2020,parsed_source="PubDate_Year"),journal=JournalInfo(title="Anesthesiology"),classification=AnesthesiaClassification(is_anesthesia_relevant=True))
    rec.content_hash=rec.compute_content_hash()
    assert client._dedup_records([rec])==[]
    print("VALIDATION OK: imports, date fallback, and dedup")

if __name__ == "__main__":
    (BASE/"dag_anesthesia_pubmed_cdc.py").write_text(DAG_CODE,encoding="utf-8")
    validate()
