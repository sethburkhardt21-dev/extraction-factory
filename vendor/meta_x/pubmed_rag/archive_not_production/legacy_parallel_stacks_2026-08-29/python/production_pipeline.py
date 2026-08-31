"""
Production Pipeline - End-to-End
Combines max extraction + PubMedBERT embeddings 768-dim + cosine similarity + audit fixes

Deliverables:
- Max anesthesia PubMed extraction with full metadata schema
- PubMedBERT embeddings title+abstract batch encoding 768-dim normalized
- Cosine similarity search
- Production ready with rate limits, dedup, classification FP fix, MedlineDate fallback

Usage:
    python production_pipeline.py --query "Anesthesia[mh]" --max 5000 --api-key YOUR_KEY --email your@email.com
"""

import os
import sys
import argparse
import json
import logging
import hashlib
from typing import List, Optional
import numpy as np
from datetime import datetime, date, timezone

# Local imports
from metadata_schema import PubMedRecordFull, build_embedding_text
from pubmed_anesthesia_extraction import (
    RateLimitConfig, RateLimitedPubMedClient, DedupManager, AnesthesiaClassifier,
    AnesthesiaPubMedMaxExtractor
)
from pubmedbert_embedding_pipeline import PubMedBERTEmbedder, EmbeddingConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "outputs", "anesthesia_max")
DEFAULT_FULL_MINDATE = "1800/01/01"  # domain bound: modern anesthesia literature begins well after this

def _record_dict(rec, *, exclude_embedding=False):
    exclude = {"embedding_vector"} if exclude_embedding else None
    if hasattr(rec, "model_dump"):
        return rec.model_dump(exclude=exclude)
    return rec.dict(exclude=exclude)

def _write_jsonl(path: str, records: List[PubMedRecordFull], *, exclude_embedding=True) -> str:
    h = hashlib.sha256()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            line = json.dumps(_record_dict(rec, exclude_embedding=exclude_embedding), default=str, ensure_ascii=False, sort_keys=True) + "\n"
            f.write(line)
            h.update(line.encode("utf-8"))
    return h.hexdigest()

class ProductionAnesthesiaPipeline:
    def __init__(self, email: str, api_key: Optional[str] = None, 
                 embedding_model: str = "NeuML/pubmedbert-base-embeddings",
                 batch_size: int = 32,
                 device: Optional[str] = None):
        
        rate_cfg = RateLimitConfig(email=email, api_key=api_key)
        self.client = RateLimitedPubMedClient(rate_cfg)
        self.dedup = DedupManager()
        self.classifier = AnesthesiaClassifier()
        self.extractor = AnesthesiaPubMedMaxExtractor(
            client=self.client,
            deduplicator=self.dedup,
            classifier=self.classifier
        )
        
        emb_cfg = EmbeddingConfig(
            model_name=embedding_model,
            dimension=768,
            batch_size=batch_size,
            normalize_embeddings=True,
            device=device,
            max_seq_length=512
        )
        self.embedder = PubMedBERTEmbedder(emb_cfg)
        logger.info(f"Production pipeline ready: model={embedding_model} 768-dim normalized")
    
    def run_extraction(self, queries: Optional[List[str]] = None, mindate: str = DEFAULT_FULL_MINDATE,
                       maxdate: str = None, max_ids_per_query: Optional[int] = None,
                       require_anesthesia_classification: bool = False) -> List[PubMedRecordFull]:
        # NCBI requires both mindate/maxdate for arbitrary date ranges. The production
        # full run defaults to a transparent anesthesia-domain lower bound and today.
        maxdate = maxdate or date.today().strftime("%Y/%m/%d")
        return self.extractor.extract_max(
            query_overrides=queries,
            mindate=mindate,
            maxdate=maxdate,
            max_ids_per_query=max_ids_per_query,
            require_anesthesia_classification=require_anesthesia_classification
        )
    
    def run_embedding(self, records: List[PubMedRecordFull], use_weighted: bool = False) -> np.ndarray:
        titles = [r.title for r in records]
        abstracts = [r.abstract for r in records]
        if use_weighted:
            embeddings = self.embedder.encode_weighted(titles, abstracts)
        else:
            embeddings = self.embedder.encode_batch(titles, abstracts)
        # Attach enrichment provenance only after a real embedding backend ran.
        for rec, emb in zip(records, embeddings):
            rec.embedding_vector = emb.tolist()
            rec.embedding_model = self.embedder.config.model_name
            rec.embedding_model_revision = self.embedder.config.model_revision
            rec.embedding_dim = int(emb.shape[0])
            rec.embedding_normalized = bool(self.embedder.config.normalize_embeddings)
        return embeddings
    
    def save_outputs(self, records: List[PubMedRecordFull], embeddings: np.ndarray, output_dir: str,
                     *, candidate_records: Optional[List[PubMedRecordFull]] = None,
                     excluded_records: Optional[List[PubMedRecordFull]] = None):
        os.makedirs(output_dir, exist_ok=True)
        candidate_records = candidate_records if candidate_records is not None else records
        excluded_records = excluded_records or []

        candidate_sha = _write_jsonl(os.path.join(output_dir, "candidate_records_full_metadata.jsonl"), candidate_records)
        excluded_sha = _write_jsonl(os.path.join(output_dir, "excluded_candidates.jsonl"), excluded_records)
        retained_sha = _write_jsonl(os.path.join(output_dir, "anesthesia_records_full_metadata.jsonl"), records, exclude_embedding=(len(records) > 1000))
        embedding_path = os.path.join(output_dir, "anesthesia_embeddings_768d.npy")
        np.save(embedding_path, embeddings)
        with open(embedding_path, "rb") as fh:
            embedding_sha = hashlib.sha256(fh.read()).hexdigest()

        provenance_path = os.path.join(output_dir, "source_record_provenance.jsonl")
        with open(provenance_path, "w", encoding="utf-8", newline="\n") as f:
            for rec in candidate_records:
                prov = {
                    "provenance_schema_version":"frontier-source-provenance-1.0",
                    "source":"pubmed",
                    "source_record_id":rec.pmid,
                    "source_version_id":str(rec.version or ""),
                    "source_record_sha256":rec.source_record_sha256,
                    "run_id":rec.run_id,
                    "parser_version":rec.parser_version,
                    "canonical_schema_version":rec.canonical_schema_version,
                    "retrieved_at":str(rec.retrieved_at) if rec.retrieved_at else None,
                    "source_url":rec.source_url,
                    "parse_status":"parsed",
                    "parse_warnings":[],
                }
                f.write(json.dumps(prov, ensure_ascii=False, sort_keys=True)+"\n")
        with open(provenance_path, "rb") as fh:
            provenance_sha = hashlib.sha256(fh.read()).hexdigest()

        extraction_meta = getattr(self.extractor, "last_extraction_meta", {})
        manifest = {
            "candidate_count": len(candidate_records),
            "retained_anesthesia_count": len(records),
            "excluded_candidate_count": len(excluded_records),
            "embedding_count": int(embeddings.shape[0]),
            "embedding_dim": int(embeddings.shape[1]) if embeddings.ndim == 2 and embeddings.shape[0] else 768,
            "manifest_schema_version": "frontier-run-manifest-1.0",
            "run_id": extraction_meta.get("run_id"),
            "source": "pubmed",
            "mode": "domain_candidates_plus_embedding_enrichment",
            "parser_version": extraction_meta.get("parser_version", "pubmed-canonical-3.0"),
            "canonical_schema_version": extraction_meta.get("canonical_schema_version", "pubmed-record-3.0"),
            "model": self.embedder.config.model_name,
            "model_revision": self.embedder.config.model_revision,
            "embedding_reproducibility": "PINNED" if self.embedder.config.model_revision else "UNPINNED_MODEL_REVISION",
            "normalized": bool(self.embedder.config.normalize_embeddings),
            "similarity": "cosine (dot product on normalized vectors)",
            "batch_size": self.embedder.config.batch_size,
            "device": self.embedder._device,
            "extraction": extraction_meta,
            "certification_status": extraction_meta.get("certification_status", "UNVERIFIED"),
            "candidate_jsonl_sha256": candidate_sha,
            "retained_jsonl_sha256": retained_sha,
            "excluded_jsonl_sha256": excluded_sha,
            "embedding_npy_sha256": embedding_sha,
            "provenance_sha256": provenance_sha,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "fields": list(getattr(PubMedRecordFull, "model_fields", getattr(PubMedRecordFull, "__fields__", {})).keys()),
        }
        tmp = os.path.join(output_dir, "manifest.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, os.path.join(output_dir, "manifest.json"))

        if len(embeddings) > 0:
            sample_query = embeddings[0]
            sims = np.dot(embeddings, sample_query)
            top_idx = np.argsort(sims)[::-1][:5]
            sample_search = [{"rank": i+1, "pmid": records[int(idx)].pmid, "title": records[int(idx)].title[:120], "cosine_sim": float(sims[int(idx)])} for i, idx in enumerate(top_idx)]
            with open(os.path.join(output_dir, "sample_cosine_search.json"), "w", encoding="utf-8") as f:
                json.dump(sample_search, f, indent=2)
        logger.info(f"Saved source candidates={len(candidate_records)}, retained={len(records)}, embeddings={embeddings.shape} to {output_dir}")

    def run_full(self, output_dir: str = DEFAULT_OUTPUT_DIR,
                 queries: Optional[List[str]] = None, max_ids_per_query: Optional[int] = None,
                 mindate: str = DEFAULT_FULL_MINDATE, maxdate: str = None):
        logger.info("=== STEP 1: Complete anesthesia candidate extraction with fail-closed reconciliation ===")
        candidates = self.run_extraction(
            queries=queries, mindate=mindate, maxdate=maxdate,
            max_ids_per_query=max_ids_per_query, require_anesthesia_classification=False
        )
        retained = [r for r in candidates if r.anesthesia_classification and r.anesthesia_classification.is_anesthesia]
        excluded = [r for r in candidates if not (r.anesthesia_classification and r.anesthesia_classification.is_anesthesia)]
        logger.info(f"Candidates={len(candidates)} retained={len(retained)} excluded={len(excluded)}")

        if retained:
            logger.info("=== STEP 2: PubMedBERT 768-dim encoding ===")
            embeddings = self.run_embedding(retained)
            if embeddings.ndim != 2 or embeddings.shape[1] != 768:
                raise RuntimeError(f"Expected Nx768 embeddings, got {embeddings.shape}")
            norms = np.linalg.norm(embeddings, axis=1)
            if not np.all(np.isfinite(norms)) or not np.allclose(norms, 1.0, atol=1e-3):
                raise RuntimeError("Embedding normalization certification failed")
        else:
            embeddings = np.empty((0, 768), dtype=np.float32)

        self.save_outputs(
            retained, embeddings, output_dir,
            candidate_records=candidates, excluded_records=excluded
        )
        return retained, embeddings


def main():
    parser = argparse.ArgumentParser(description="Max Anesthesia PubMed Extraction + PubMedBERT 768-dim")
    parser.add_argument("--email", required=True, help="Email for NCBI E-utilities")
    parser.add_argument("--api-key", default=None, help="NCBI API key for 10 req/s (optional, default 3 req/s)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="Output dir")
    parser.add_argument("--max-ids-per-query", type=int, default=None, help="Optional explicit cap per query. Capped runs are marked TRUNCATED; omit for complete extraction.")
    parser.add_argument("--mindate", default=DEFAULT_FULL_MINDATE, help="Publication-date lower bound YYYY/MM/DD (default: 1800/01/01 for anesthesia corpus)")
    parser.add_argument("--maxdate", default=None, help="Max date YYYY/MM/DD")
    parser.add_argument("--model", default="NeuML/pubmedbert-base-embeddings", help="Embedding model")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size")
    parser.add_argument("--device", default=None, help="cuda/cpu/mps")
    args = parser.parse_args()
    
    pipeline = ProductionAnesthesiaPipeline(
        email=args.email,
        api_key=args.api_key,
        embedding_model=args.model,
        batch_size=args.batch_size,
        device=args.device
    )
    pipeline.run_full(output_dir=args.output, max_ids_per_query=args.max_ids_per_query, mindate=args.mindate, maxdate=args.maxdate)


if __name__ == "__main__":
    main()
