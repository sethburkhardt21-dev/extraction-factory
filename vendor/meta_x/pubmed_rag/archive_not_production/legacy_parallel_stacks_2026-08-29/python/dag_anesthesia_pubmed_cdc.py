
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
