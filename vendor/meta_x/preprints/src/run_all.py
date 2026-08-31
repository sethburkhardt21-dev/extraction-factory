"""Monthly-sharded medRxiv/bioRxiv extraction with a frontier root manifest.

No network access occurs unless ``allow_network``/``--network`` is explicit.
Every shard retains its own run manifest; the root manifest records and hashes
those manifests rather than flattening their provenance away.
"""
from __future__ import annotations

import sys
from pathlib import Path as _BootstrapPath
_PREPRINT_ROOT = _BootstrapPath(__file__).resolve().parents[1]
if str(_PREPRINT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PREPRINT_ROOT))
_ESTATE_ROOT = _BootstrapPath(__file__).resolve().parents[2]
if str(_ESTATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ESTATE_ROOT))

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List
import uuid

from frontier_core.gate import require_frontier_preflight
from src.pipeline import (
    CANONICAL_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    PARSER_VERSION,
    iter_months,
    run_extraction,
)
from src.medrxiv_biorxiv.parser import dedup_versions, latest_by_doi
from src.medrxiv_biorxiv.storage import atomic_write_json, atomic_write_jsonl, read_jsonl, sha256_file

ROOT_SCHEMA_VERSION = "preprint-root-aggregate-2.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_all(
    server: str,
    start: str,
    end: str,
    out_dir: str,
    contact_email: str,
    *,
    allow_network: bool = False,
    runner: Callable[..., Dict[str, Any]] = run_extraction,
) -> Dict[str, Any]:
    root = Path(out_dir)
    if allow_network:
        if runner is run_extraction and (not contact_email or "@" not in contact_email):
            raise ValueError("a real contact email is required for bioRxiv/medRxiv network extraction")
        if root.exists() and any(root.iterdir()):
            raise RuntimeError(f"output directory must be empty for a new preprint aggregate run: {root}")
        root.mkdir(parents=True, exist_ok=True)
    root_run_id = str(uuid.uuid4())
    started_at = _utc_now()
    shard_results: List[Dict[str, Any]] = []
    all_versions: List[Dict[str, Any]] = []

    for shard_index, (s, e) in enumerate(iter_months(start, end)):
        shard = root / "shards" / f"{s}_{e}"
        result = runner(server, s, e, str(shard), contact_email, allow_network=allow_network)
        entry = dict(result)
        entry["shard_index"] = shard_index
        entry["shard_start"] = s
        entry["shard_end"] = e
        entry["shard_path"] = str(shard.relative_to(root))
        manifest_path = shard / "manifest.json"
        if allow_network and manifest_path.exists():
            entry["shard_manifest_sha256"] = sha256_file(manifest_path)
        shard_results.append(entry)
        if allow_network and result.get("status") == "completed" and (shard / "versions.jsonl").exists():
            all_versions.extend(read_jsonl(shard / "versions.jsonl"))

    if not allow_network:
        return {
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "aggregate_schema_version": ROOT_SCHEMA_VERSION,
            "run_id": root_run_id,
            "source": server,
            "mode": "monthly_sharded_details_interval",
            "status": "dry_run",
            "certification_status": "PENDING",
            "network_extraction_performed": False,
            "started_at": started_at,
            "completed_at": _utc_now(),
            "query": {"server": server, "start": start, "end": end},
            "shards": shard_results,
        }

    versions = dedup_versions(all_versions)
    latest = latest_by_doi(versions)
    versions_path = root / "versions_all.jsonl"
    latest_path = root / "latest_all.jsonl"
    atomic_write_jsonl(versions_path, versions)
    atomic_write_jsonl(latest_path, latest)

    failed_shards = [s for s in shard_results if s.get("status") != "completed" or s.get("certification_status") == "FAIL"]
    nonpass_shards = [s for s in shard_results if s.get("certification_status") != "PASS"]
    transport_bad_shards = [
        s for s in shard_results
        if not str(s.get("transport_capture_status") or "").startswith("PASS_EXACT_HTTP_RESPONSES")
    ]
    expected_values = [s.get("expected_records") for s in shard_results]
    expected_total = sum(int(x) for x in expected_values) if expected_values and all(x is not None for x in expected_values) else None
    observed_total = sum(int(s.get("observed_records") or 0) for s in shard_results)
    quarantined_total = sum(int(s.get("records_quarantined") or 0) for s in shard_results)
    valid_total = sum(int(s.get("valid_records") or 0) for s in shard_results)
    shard_complete = all(s.get("complete_against_source") is True for s in shard_results)
    root_complete = shard_complete and not failed_shards and (expected_total is None or observed_total == expected_total)

    warnings: List[str] = []
    errors: List[str] = []
    if nonpass_shards:
        warnings.append(f"{len(nonpass_shards)} shard(s) are not PASS")
    if quarantined_total:
        warnings.append(f"{quarantined_total} record(s) quarantined across shards")
    if failed_shards:
        errors.append(f"{len(failed_shards)} shard(s) failed")
    if transport_bad_shards:
        errors.append(f"{len(transport_bad_shards)} shard(s) lack exact HTTP transport capture")
    if expected_total is not None and observed_total != expected_total:
        errors.append(f"aggregate source count mismatch: observed={observed_total}, expected={expected_total}")

    certification = "FAIL" if errors else ("PASS" if root_complete and not warnings else "WARN")
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "aggregate_schema_version": ROOT_SCHEMA_VERSION,
        "run_id": root_run_id,
        "source": server,
        "mode": "monthly_sharded_details_interval",
        "status": "completed" if not errors else "failed",
        "certification_status": certification,
        "network_extraction_performed": True,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "parser_version": PARSER_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "query": {"server": server, "start": start, "end": end},
        "server": server,
        "start": start,
        "end": end,
        "shard_count": len(shard_results),
        "shard_pass_count": sum(s.get("certification_status") == "PASS" for s in shard_results),
        "shard_manifest_chain": [
            {
                "shard_index": s["shard_index"],
                "run_id": s.get("run_id"),
                "path": s["shard_path"],
                "manifest_sha256": s.get("shard_manifest_sha256"),
                "certification_status": s.get("certification_status"),
            }
            for s in shard_results
        ],
        "expected_records": expected_total,
        "observed_records": observed_total,
        "valid_records": valid_total,
        "unique_versions": len(versions),
        "unique_records": len(versions),
        "latest_unique_dois": len(latest),
        "records_quarantined": quarantined_total,
        "complete_against_source": root_complete,
        "truncated": any(bool(s.get("truncated")) for s in shard_results),
        "transport_capture_status": (
            "PASS_EXACT_HTTP_RESPONSES_ALL_SHARDS" if not transport_bad_shards
            else "FAIL_MISSING_EXACT_HTTP_RESPONSES"
        ),
        "transport_response_count": sum(int(s.get("transport_response_count") or 0) for s in shard_results),
        "warnings": warnings,
        "errors": errors,
        "versions_sha256": sha256_file(versions_path),
        "canonical_sha256": sha256_file(versions_path),
        "latest_sha256": sha256_file(latest_path),
    }
    atomic_write_json(root / "manifest.json", manifest)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", choices=["medrxiv", "biorxiv"], required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--contact-email", default=os.getenv("BIORXIV_CONTACT_EMAIL", ""))
    ap.add_argument("--network", action="store_true", help="explicitly permit HTTP requests")
    ap.add_argument("--preflight", type=Path, help="PASS FRONTIER_PREFLIGHT.json for the exact active code")
    args = ap.parse_args()
    if args.network:
        if not args.preflight: ap.error("--preflight is required for network extraction")
        require_frontier_preflight(args.preflight, _ESTATE_ROOT)
    result = run_all(
        args.server, args.start, args.end, args.out_dir, args.contact_email,
        allow_network=args.network,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
