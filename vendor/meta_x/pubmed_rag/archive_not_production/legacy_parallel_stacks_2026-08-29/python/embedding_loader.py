"""
Embedding Loader - PubMedBERT embeddings for anesthesia corpus
Complements etl_loader_postgres_bigquery.py
Supports Postgres pgvector upsert and BigQuery ARRAY<FLOAT64>

Usage:
  pip install transformers torch sentence-transformers psycopg2-binary google-cloud-bigquery
  python embedding_loader.py --input anesthesia_full_metadata.jsonl --target postgres --dsn postgresql://... --model microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext --batch-size 32
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict
import logging
from datetime import datetime, timezone
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("emb_loader")

try:
    import orjson
    def json_loads(s): return orjson.loads(s)
except ImportError:
    json_loads = json.loads

def get_title_abstract(record: Dict) -> str:
    """Combine title + abstract for embedding input, truncate to 512 tokens approx 2000 chars"""
    title = record.get('title','') or ''
    abstract = record.get('abstract','') or ''
    combined = f"{title} [SEP] {abstract}"
    # Truncate to ~ 8192 chars safe for PubMedBERT 512 tokens
    return combined[:8000]

def normalize_doi_quick(doi):
    if not doi:
        return None
    return doi.lower().replace('https://doi.org/','').replace('http://doi.org/','').split('?')[0].strip().rstrip('.')

class EmbeddingGenerator:
    def __init__(self, model_name: str = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext", batch_size: int=32, device: str=None):
        self.model_name = model_name
        self.batch_size = batch_size
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name, device=device)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"Loaded {model_name} dim={self.embedding_dim}")
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is required for embedding writes; synthetic embeddings are forbidden") from exc
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self.model is None:
            raise RuntimeError("embedding model unavailable; refusing synthetic vectors")
        # Real embedding
        embs = self.model.encode(texts, batch_size=self.batch_size, show_progress_bar=False, normalize_embeddings=True)
        return embs.tolist() if hasattr(embs,'tolist') else embs

# Postgres embedding upsert
POSTGRES_EMB_UPSERT = """
INSERT INTO anesthesia_pubmed (pmid, title_abstract_embedding, embedding_model, embedding_generated_at)
VALUES %s
ON CONFLICT (pmid) DO UPDATE SET
    title_abstract_embedding = EXCLUDED.title_abstract_embedding,
    embedding_model = EXCLUDED.embedding_model,
    embedding_generated_at = EXCLUDED.embedding_generated_at
"""

def load_embeddings_postgres(input_path: Path, dsn: str, model_name: str, batch_size: int, dry_run: bool=False):
    generator = None if dry_run else EmbeddingGenerator(model_name, batch_size=batch_size)
    
    pmids = []
    texts = []
    total = 0
    
    if not dry_run:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
    
    def flush():
        nonlocal pmids, texts
        if not pmids:
            return
        if dry_run:
            logger.info(f"[DRY-RUN] Would embed/upsert {len(pmids)} records; no vectors generated")
        else:
            embs = generator.embed_batch(texts)
            with conn.cursor() as cur:
                values = [(pmid, emb, model_name, datetime.now(timezone.utc)) for pmid, emb in zip(pmids, embs)]
                # Need to adapt for vector type - psycopg2 vector extension handles list
                psycopg2.extras.execute_values(cur, POSTGRES_EMB_UPSERT, values, page_size=batch_size)
            conn.commit()
            logger.info(f"Flushed {len(pmids)} embeddings")
        pmids = []
        texts = []
    
    with input_path.open('r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json_loads(line)
            except:
                continue
            pmid = str(rec.get('pmid','')).strip()
            if not pmid:
                continue
            txt = get_title_abstract(rec)
            pmids.append(pmid)
            texts.append(txt)
            total += 1
            if len(pmids) >= batch_size:
                flush()
    
    flush()
    if not dry_run:
        conn.close()
    logger.info(f"Embedding ETL done total={total} dim={generator.embedding_dim if generator else 'not-generated-dry-run'}")

def load_embeddings_bigquery(input_path: Path, project: str, dataset: str, target_table: str, model_name: str, batch_size: int, dry_run: bool=False):
    generator = None if dry_run else EmbeddingGenerator(model_name, batch_size=batch_size)
    
    if not dry_run:
        from google.cloud import bigquery
        client = bigquery.Client(project=project)
        table_ref = f"{project}.{dataset}.{target_table}"
    
    pmids = []
    texts = []
    total = 0
    
    def flush():
        nonlocal pmids, texts
        if not pmids:
            return
        if dry_run:
            logger.info(f"[DRY-RUN] BQ would embed and MERGE {len(pmids)} records; no vectors generated")
            pmids.clear(); texts.clear(); return
        embs = generator.embed_batch(texts)
        rows = [{"pmid": pmid, "title_abstract_embedding": emb, "embedding_model": model_name,
                 "embedding_generated_at": datetime.now(timezone.utc).isoformat()}
                for pmid, emb in zip(pmids, embs)]
        import uuid
        from google.cloud import bigquery
        stage = f"{project}.{dataset}._embedding_stage_{uuid.uuid4().hex}"
        schema = [
            bigquery.SchemaField("pmid", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("title_abstract_embedding", "FLOAT", mode="REPEATED"),
            bigquery.SchemaField("embedding_model", "STRING"),
            bigquery.SchemaField("embedding_generated_at", "TIMESTAMP"),
        ]
        try:
            job_config = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")
            client.load_table_from_json(rows, stage, job_config=job_config).result()
            merge_sql = f"""
            MERGE `{{table_ref}}` T
            USING `{{stage}}` S
            ON T.pmid = S.pmid
            WHEN MATCHED THEN UPDATE SET
              title_abstract_embedding = S.title_abstract_embedding,
              embedding_model = S.embedding_model,
              embedding_generated_at = S.embedding_generated_at
            """
            client.query(merge_sql).result()
            logger.info(f"BQ merged {len(rows)} embeddings")
        finally:
            client.delete_table(stage, not_found_ok=True)
        pmids.clear(); texts.clear()

    with input_path.open('r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            rec = json_loads(line)
            pmid = str(rec.get('pmid','')).strip()
            if not pmid:
                continue
            pmids.append(pmid)
            texts.append(get_title_abstract(rec))
            total += 1
            if len(pmids) >= batch_size:
                flush()
    flush()
    logger.info(f"BQ Embedding done total={total}")

def main():
    parser = argparse.ArgumentParser(description="Embedding loader for anesthesia corpus")
    parser.add_argument("--input", required=True)
    parser.add_argument("--target", choices=["postgres","bigquery","both"], required=True)
    parser.add_argument("--dsn", help="Postgres DSN")
    parser.add_argument("--bq-project")
    parser.add_argument("--bq-dataset")
    parser.add_argument("--bq-target-table", default="anesthesia_full")
    parser.add_argument("--model", default="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    if args.target in ("postgres","both"):
        dsn = args.dsn or "postgresql://postgres:postgres@localhost:5432/postgres"
        load_embeddings_postgres(input_path, dsn, args.model, args.batch_size, args.dry_run)
    
    if args.target in ("bigquery","both"):
        project = args.bq_project or "my-project"
        dataset = args.bq_dataset or "anesthesia_pubmed"
        load_embeddings_bigquery(input_path, project, dataset, args.bq_target_table, args.model, args.batch_size, args.dry_run)

if __name__ == "__main__":
    main()
