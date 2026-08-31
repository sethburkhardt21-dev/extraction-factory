"""Frontier-ready medRxiv/bioRxiv extraction pipeline."""
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
from datetime import datetime, timedelta, timezone
import inspect
import json
import os
from pathlib import Path
from typing import Any, Dict, List
import uuid
from dateutil.parser import isoparse

from frontier_core.gate import require_frontier_preflight
from src.medrxiv_biorxiv.client import FetchConfig, fetch_interval
from src.medrxiv_biorxiv.parser import dedup_versions, latest_by_doi, validate_record
from src.medrxiv_biorxiv.storage import atomic_write_bytes, atomic_write_json, atomic_write_jsonl, sha256_file

PARSER_VERSION = "preprint-canonical-2.0"
CANONICAL_SCHEMA_VERSION = "preprint-record-2.0"
MANIFEST_SCHEMA_VERSION = "frontier-run-manifest-1.0"
PROVENANCE_SCHEMA_VERSION = "frontier-source-provenance-1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iter_months(start: str, end: str):
    s = isoparse(start).date(); e = isoparse(end).date()
    if e < s: raise ValueError("end before start")
    cur = s
    while cur <= e:
        if cur.month == 12:
            nxt = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            nxt = cur.replace(month=cur.month + 1, day=1)
        month_end = min(nxt - timedelta(days=1), e)
        yield cur.isoformat(), month_end.isoformat()
        cur = month_end + timedelta(days=1)


def _source_url(rec: Dict[str, Any]) -> str:
    server = str(rec.get("server") or "").lower()
    doi = str(rec.get("doi") or "")
    version = str(rec.get("version") or "1")
    return f"https://www.{server}.org/content/{doi}v{version}" if server and doi else ""


def _decorate(rec: Dict[str, Any], run_id: str, retrieved_at: str, transport_raw_locator: str | None = None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    row = dict(rec)
    row.update({
        "run_id": run_id,
        "parser_version": PARSER_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "retrieved_at": retrieved_at,
        "source_url": _source_url(rec),
    })
    provenance = {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "source": str(rec.get("server") or ""),
        "source_record_id": str(rec.get("doi") or ""),
        "source_version_id": str(rec.get("version") or ""),
        "source_record_sha256": rec.get("source_record_sha256"),
        "run_id": run_id,
        "parser_version": PARSER_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "retrieved_at": retrieved_at,
        "source_version": None,
        "source_updated_at": rec.get("date") or None,
        "source_url": _source_url(rec),
        "raw_locator": None,
        "transport_raw_locator": transport_raw_locator,
        "parse_status": "parsed",
        "parse_warnings": [],
    }
    return row, provenance


def run_extraction(server: str, start: str, end: str, out_dir: str, contact_email: str,
                   *, allow_network: bool = False, fetcher=fetch_interval) -> Dict[str, Any]:
    """Write lossless observed records, canonical versions, latest projection and provenance."""
    out = Path(out_dir)
    if not allow_network:
        return {
            "status": "dry_run", "certification_status": "PENDING", "network_extraction_performed": False,
            "server": server, "start": start, "end": end, "written": 0,
        }
    if fetcher is fetch_interval and (not contact_email or "@" not in contact_email):
        raise ValueError("a real contact email is required for bioRxiv/medRxiv network extraction")
    if out.exists() and any(out.iterdir()):
        raise RuntimeError(f"output directory must be empty for a new preprint run: {out}")
    out.mkdir(parents=True, exist_ok=True)

    run_id = str(uuid.uuid4())
    started_at = _utc_now()
    cfg = FetchConfig(server=server, start_date=start, end_date=end, contact_email=contact_email)
    fetch_meta: Dict[str, Any] = {}
    native_transport_capture = fetcher is fetch_interval
    transport_dir = out / "raw" / "transport"
    transport_index_path = out / "raw" / "transport_index.jsonl"
    transport_rows: List[Dict[str, Any]] = []
    transport_state: Dict[str, str | None] = {"locator": None}

    def capture_transport(url: str, response_meta: Dict[str, Any], payload: bytes) -> None:
        ordinal = len(transport_rows)
        payload_path = transport_dir / f"{ordinal:08d}_details_page.json"
        atomic_write_bytes(payload_path, bytes(payload))
        row = {
            "transport_schema_version": "frontier-http-transport-1.0",
            "source": server,
            "kind": "details_page",
            "url": url,
            "status_code": response_meta.get("status_code"),
            "content_type": response_meta.get("content_type"),
            "retrieved_at": _utc_now(),
            "path": str(payload_path.relative_to(out)),
            "sha256": sha256_file(payload_path),
            "bytes": payload_path.stat().st_size,
        }
        transport_rows.append(row)
        transport_state["locator"] = row["path"]

    sig = inspect.signature(fetcher)
    kwargs: Dict[str, Any] = {}
    if "metadata" in sig.parameters:
        kwargs["metadata"] = fetch_meta
    if native_transport_capture and "raw_response_hook" in sig.parameters:
        kwargs["raw_response_hook"] = capture_transport
    iterator = fetcher(cfg, **kwargs) if kwargs else fetcher(cfg)

    observed: List[Dict[str, Any]] = []
    valid: List[Dict[str, Any]] = []
    invalid_records: List[Dict[str, Any]] = []
    provenance: List[Dict[str, Any]] = []
    for rec in iterator:
        retrieved_at = _utc_now()
        observed.append(rec)
        errs = validate_record(rec)
        if errs:
            quarantined = dict(rec)
            quarantined.update({"_validation_errors": errs, "run_id": run_id, "retrieved_at": retrieved_at})
            invalid_records.append(quarantined)
        else:
            row, prov = _decorate(
                rec, run_id, retrieved_at,
                transport_state.get("locator") if native_transport_capture else None,
            )
            valid.append(row)
            provenance.append(prov)

    versions = dedup_versions(valid)
    latest = latest_by_doi(versions)
    observed_path = out / "observed_source.jsonl"
    versions_path = out / "versions.jsonl"
    latest_path = out / "latest.jsonl"
    provenance_path = out / "provenance" / "source_records.jsonl"
    quarantine_path = out / "quarantine" / "invalid_records.jsonl"
    atomic_write_jsonl(observed_path, observed)
    atomic_write_jsonl(versions_path, versions)
    atomic_write_jsonl(latest_path, latest)
    atomic_write_jsonl(provenance_path, provenance)
    atomic_write_jsonl(quarantine_path, invalid_records)
    if native_transport_capture:
        atomic_write_jsonl(transport_index_path, transport_rows)
        if int(fetch_meta.get("pages") or 0) != len(transport_rows):
            raise RuntimeError(
                f"preprint transport capture mismatch: pages={fetch_meta.get('pages')} responses={len(transport_rows)}"
            )
        transport_capture_status = "PASS_EXACT_HTTP_RESPONSES"
    else:
        transport_capture_status = "TEST_INJECTED_NO_NATIVE_TRANSPORT_CAPTURE"

    expected = fetch_meta.get("reported_total")
    observed_count = len(observed)
    complete = (observed_count == expected) if expected is not None else (
        bool(fetch_meta.get("eof_observed")) if native_transport_capture else None
    )
    warnings = list(fetch_meta.get("warnings") or [])
    duplicate_versions = len(valid) - len(versions)
    if duplicate_versions:
        warnings.append(f"{duplicate_versions} exact logical duplicate versions observed")
    if invalid_records:
        warnings.append(f"{len(invalid_records)} records quarantined")
    errors: List[str] = []
    if complete is False:
        errors.append(f"observed {observed_count} records but API reported {expected}")

    if errors:
        certification = "FAIL"
    elif complete is True and not warnings:
        certification = "PASS" if native_transport_capture else "PASS_TEST_INJECTED"
    else:
        certification = "WARN"

    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "source": server,
        "mode": "details_interval",
        "status": "completed" if not errors else "failed",
        "certification_status": certification,
        "network_extraction_performed": True,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "parser_version": PARSER_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "query": {"server": server, "start": start, "end": end},
        "server": server, "start": start, "end": end,
        "expected_records": expected,
        "api_records_observed": observed_count,
        "observed_records": observed_count,
        "valid_records_observed": len(valid),
        "valid_records": len(valid),
        "unique_versions": len(versions),
        "unique_records": len(versions),
        "latest_unique_dois": len(latest),
        "records_quarantined": len(invalid_records),
        "quarantined_records": len(invalid_records),
        "complete_against_source": complete,
        "truncated": False,
        "warnings": warnings,
        "errors": errors,
        "observed_sha256": sha256_file(observed_path),
        "raw_sha256": sha256_file(observed_path),
        "versions_sha256": sha256_file(versions_path),
        "canonical_sha256": sha256_file(versions_path),
        "latest_sha256": sha256_file(latest_path),
        "provenance_sha256": sha256_file(provenance_path),
        "quarantine_sha256": sha256_file(quarantine_path),
        "source_snapshot_sha256": sha256_file(observed_path),
        "transport_capture_status": transport_capture_status,
        "transport_response_count": len(transport_rows),
        "transport_index": str(transport_index_path.relative_to(out)) if native_transport_capture else None,
        "transport_index_sha256": sha256_file(transport_index_path) if native_transport_capture else None,
        "artifacts": {
            "raw": {"path": str(observed_path.relative_to(out)), "sha256": sha256_file(observed_path), "records": observed_count},
            "canonical": {"path": str(versions_path.relative_to(out)), "sha256": sha256_file(versions_path), "records": len(versions)},
            "latest": {"path": str(latest_path.relative_to(out)), "sha256": sha256_file(latest_path), "records": len(latest)},
            "provenance": {"path": str(provenance_path.relative_to(out)), "sha256": sha256_file(provenance_path), "records": len(provenance)},
            "quarantine": {"path": str(quarantine_path.relative_to(out)), "sha256": sha256_file(quarantine_path), "records": len(invalid_records)},
            **({"transport_index": {"path": str(transport_index_path.relative_to(out)), "sha256": sha256_file(transport_index_path), "records": len(transport_rows)}} if native_transport_capture else {}),
        },
        "fetch_metadata": fetch_meta,
    }
    atomic_write_json(out / "manifest.json", manifest)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", choices=["medrxiv", "biorxiv"], required=True)
    ap.add_argument("--start", required=True); ap.add_argument("--end", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--contact-email", default=os.getenv("BIORXIV_CONTACT_EMAIL", ""))
    ap.add_argument("--network", action="store_true", help="explicitly permit HTTP requests")
    ap.add_argument("--preflight", type=Path, help="PASS FRONTIER_PREFLIGHT.json for the exact active code")
    args = ap.parse_args()
    if args.network:
        if not args.preflight: ap.error("--preflight is required for network extraction")
        require_frontier_preflight(args.preflight, _ESTATE_ROOT)
    result = run_extraction(args.server, args.start, args.end, args.out_dir, args.contact_email, allow_network=args.network)
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
