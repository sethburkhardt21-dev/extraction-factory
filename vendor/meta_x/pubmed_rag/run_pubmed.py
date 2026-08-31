#!/usr/bin/env python3
"""Explicitly gated PubMed source extraction CLI.

Without --network this command only emits a dry-run plan and performs no HTTP calls.
A certifiable network run requires explicit publication-date bounds and a real NCBI
contact email. Classification/embeddings are deliberately outside this stage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List
import sys

_ESTATE_ROOT = Path(__file__).resolve().parents[1]
if str(_ESTATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ESTATE_ROOT))
from frontier_core.gate import require_frontier_preflight

try:
    from .pubmed_anesthesia_extraction import (
        PubMedSourceExtractor,
        RateLimitConfig,
        RateLimitedPubMedClient,
    )
except ImportError:
    from pubmed_anesthesia_extraction import (
        PubMedSourceExtractor,
        RateLimitConfig,
        RateLimitedPubMedClient,
    )

MANIFEST_SCHEMA_VERSION = "frontier-run-manifest-1.0"
PROVENANCE_SCHEMA_VERSION = "frontier-source-provenance-1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n")
            count += 1
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return count


def _atomic_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        f.write("\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(content); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _record_dict(rec: Any) -> Dict[str, Any]:
    if hasattr(rec, "model_dump"):
        return rec.model_dump(mode="json")
    if isinstance(rec, dict):
        return dict(rec)
    raise TypeError(f"unsupported PubMed record type: {type(rec)!r}")


def _query_fingerprint(queries: List[str], mindate: str, maxdate: str, max_ids_per_query: int | None) -> str:
    return hashlib.sha256(_canonical_json({
        "queries": queries,
        "mindate": mindate,
        "maxdate": maxdate,
        "max_ids_per_query": max_ids_per_query,
    })).hexdigest()


def run(*, out_dir: Path, email: str, api_key: str | None, mindate: str, maxdate: str,
        queries: List[str] | None = None, max_ids_per_query: int | None = None,
        allow_network: bool = False, extractor_factory=None) -> Dict[str, Any]:
    selected_queries = list(queries or PubMedSourceExtractor.DEFAULT_DOMAIN_QUERIES)
    plan = {
        "source": "pubmed",
        "mode": "esearch_efetch_domain_candidates",
        "mindate": mindate,
        "maxdate": maxdate,
        "queries": selected_queries,
        "max_ids_per_query": max_ids_per_query,
        "query_fingerprint": _query_fingerprint(selected_queries, mindate, maxdate, max_ids_per_query),
        "network_extraction_performed": False,
    }
    if not allow_network:
        return {**plan, "status": "dry_run", "certification_status": "PENDING"}
    if not email or "@" not in email:
        raise ValueError("a real NCBI contact email is required for network extraction")
    if not mindate or not maxdate:
        raise ValueError("frontier PubMed extraction requires explicit mindate and maxdate")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty for a new PubMed run: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    transport_entries: List[Dict[str, Any]] = []
    if extractor_factory is None:
        counter={"n":0}
        def capture(kind: str, request_meta: Dict[str, Any], content: bytes) -> None:
            counter["n"] += 1
            suffix="json" if kind=="esearch" else "xml"
            rel=Path("raw")/"transport"/f"{counter['n']:06d}_{kind}.{suffix}"
            path=out_dir/rel
            _atomic_bytes(path, content)
            transport_entries.append({
                "ordinal":counter["n"],"kind":kind,"path":str(rel),"sha256":_sha256_file(path),
                "bytes":len(content),"retrieved_at":_utc_now(),"request":request_meta,
            })
        cfg = RateLimitConfig(email=email, api_key=api_key, tool="frontier-pubmed-source")
        extractor = PubMedSourceExtractor(RateLimitedPubMedClient(cfg, raw_response_hook=capture))
        transport_capture_status="PASS_EXACT_HTTP_RESPONSES"
    else:
        extractor = extractor_factory()
        transport_capture_status="TEST_INJECTED_NO_NATIVE_TRANSPORT_CAPTURE"

    records = extractor.extract_max(
        query_overrides=selected_queries,
        mindate=mindate,
        maxdate=maxdate,
        max_ids_per_query=max_ids_per_query,
    )
    rows = [_record_dict(r) for r in records]
    raw_path = out_dir / "raw" / "pubmed_source_records.jsonl"
    canonical_path = out_dir / "canonical" / "pubmed_records.jsonl"
    provenance_path = out_dir / "provenance" / "source_records.jsonl"
    raw_rows = [{
        "source": "pubmed", "pmid": str(row["pmid"]),
        "source_record_sha256": row.get("source_record_sha256"),
        "raw_xml": row.get("raw_xml") or "",
    } for row in rows]
    _atomic_jsonl(raw_path, raw_rows)
    _atomic_jsonl(canonical_path, rows)

    transport_index_path = out_dir / "raw" / "transport_index.jsonl"
    _atomic_jsonl(transport_index_path, transport_entries)
    pmid_to_transport: Dict[str, List[str]] = {}
    for entry in transport_entries:
        if entry.get("kind") != "efetch":
            continue
        for pmid in ((entry.get("request") or {}).get("pmids") or []):
            pmid_to_transport.setdefault(str(pmid), []).append(str(entry["path"]))
    if extractor_factory is None:
        missing_transport=[str(row["pmid"]) for row in rows if str(row["pmid"]) not in pmid_to_transport]
        if missing_transport:
            raise RuntimeError(f"exact EFetch transport capture missing for PMID(s): {missing_transport[:10]}")

    provenance = []
    for row in rows:
        sha = row.get("source_record_sha256")
        if not sha or len(str(sha)) != 64:
            raise RuntimeError(f"PubMed record {row.get('pmid')} lacks a valid raw source SHA-256")
        provenance.append({
            "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
            "source": "pubmed",
            "source_record_id": str(row["pmid"]),
            "source_version_id": str(row.get("version") or ""),
            "source_record_sha256": sha,
            "run_id": row.get("run_id"),
            "parser_version": row.get("parser_version"),
            "canonical_schema_version": row.get("canonical_schema_version"),
            "retrieved_at": row.get("retrieved_at"),
            "source_version": None,
            "source_updated_at": None,
            "source_url": row.get("source_url"),
            "raw_locator": f"raw/pubmed_source_records.jsonl#pmid={row['pmid']}",
            "transport_raw_locators": pmid_to_transport.get(str(row["pmid"]), []),
            "parse_status": "parsed",
            "parse_warnings": [],
        })
    _atomic_jsonl(provenance_path, provenance)

    meta = dict(extractor.last_extraction_meta)
    raw_sha = _sha256_file(raw_path)
    canonical_sha = _sha256_file(canonical_path)
    provenance_sha = _sha256_file(provenance_path)
    transport_index_sha = _sha256_file(transport_index_path)
    manifest = {
        **meta,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "network_extraction_performed": True,
        "transport_capture_status": transport_capture_status,
        "transport_response_count": len(transport_entries),
        "transport_index_sha256": transport_index_sha,
        "certification_status": meta.get("certification_status") if extractor_factory is None else "PASS_TEST_INJECTED",
        "query": {"queries": selected_queries, "mindate": mindate, "maxdate": maxdate},
        "query_fingerprint": plan["query_fingerprint"],
        "source_version_start": None,
        "source_version_end": None,
        "source_changed_during_run": None,
        "source_snapshot_semantics": "non_atomic_observation_set_no_global_pubmed_snapshot_version",
        "quarantined_records": 0,
        "raw_sha256": raw_sha,
        "canonical_sha256": canonical_sha,
        "provenance_sha256": provenance_sha,
        "quarantine_sha256": None,
        "artifacts": {
            "raw": {"path": str(raw_path.relative_to(out_dir)), "sha256": raw_sha, "records": len(raw_rows)},
            "canonical": {"path": str(canonical_path.relative_to(out_dir)), "sha256": canonical_sha, "records": len(rows)},
            "provenance": {"path": str(provenance_path.relative_to(out_dir)), "sha256": provenance_sha, "records": len(provenance)},
            "transport_index": {"path": str(transport_index_path.relative_to(out_dir)), "sha256": transport_index_sha, "records": len(transport_entries)},
        },
    }
    _atomic_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--mindate", required=True, help="YYYY/MM/DD publication-date lower bound")
    p.add_argument("--maxdate", required=True, help="YYYY/MM/DD publication-date upper bound")
    p.add_argument("--query", action="append", default=[], help="repeat for custom query set; defaults to canonical anesthesia candidate queries")
    p.add_argument("--max-ids-per-query", type=int, help="testing only; any excluded source IDs produce TRUNCATED status")
    p.add_argument("--email", default=os.getenv("NCBI_EMAIL", ""))
    p.add_argument("--api-key", default=os.getenv("NCBI_API_KEY"))
    p.add_argument("--network", action="store_true", help="explicitly authorize NCBI HTTP requests")
    p.add_argument("--preflight", type=Path, help="PASS FRONTIER_PREFLIGHT.json for the exact active code")
    args = p.parse_args()
    if args.network:
        if not args.preflight: p.error("--preflight is required for network extraction")
        require_frontier_preflight(args.preflight, _ESTATE_ROOT)
    result = run(
        out_dir=args.out_dir, email=args.email, api_key=args.api_key,
        mindate=args.mindate, maxdate=args.maxdate,
        queries=args.query or None, max_ids_per_query=args.max_ids_per_query,
        allow_network=args.network,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
