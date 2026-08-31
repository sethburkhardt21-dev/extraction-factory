"""Crash-consistent, provenance-complete ClinicalTrials.gov extraction.

Commit authority is page-level metadata + checkpoint. Raw source is always
retained; parse failures are quarantined instead of silently disappearing.
"""
from __future__ import annotations
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import pathlib
import tempfile
import time
import uuid
import zipfile
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from .client import ApiVersionInfo, ClinicalTrialsClient, FetchConfig
from .models import CANONICAL_SCHEMA_VERSION, parse_study

PARSER_VERSION = "ctg-canonical-3.0"
MANIFEST_SCHEMA_VERSION = "frontier-run-manifest-1.0"
PROVENANCE_SCHEMA_VERSION = "frontier-source-provenance-1.0"
SOURCE_NAME = "clinicaltrials.gov"


@dataclass
class ExtractionConfig:
    output_dir: pathlib.Path
    page_size: int = 1000
    query: Optional[str] = None
    filters: Optional[Dict[str, str]] = None
    max_studies: Optional[int] = None
    rate_per_sec: float = 2.0
    resume: bool = True
    use_bulk: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_dir(path: pathlib.Path) -> None:
    """Best-effort directory fsync after atomic rename on POSIX."""
    if os.name != "posix":
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _atomic_bytes(path: pathlib.Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class MassExtractor:
    def __init__(self, config: ExtractionConfig, client: Optional[ClinicalTrialsClient] = None):
        self.config = config
        self.output_dir = pathlib.Path(config.output_dir)
        self.transport_dir = self.output_dir / "raw" / "transport"
        self.transport_index_path = self.output_dir / "raw" / "transport_index.jsonl"
        self._native_transport_capture = client is None
        self._last_transport_by_kind: Dict[str, str] = {}
        self.client = client or ClinicalTrialsClient(
            rate_per_sec=config.rate_per_sec, raw_response_hook=self._capture_transport
        )
        self.raw_pages = self.output_dir / "raw" / "pages"
        self.canon_pages = self.output_dir / "canonical" / "pages"
        self.quarantine_pages = self.output_dir / "quarantine" / "pages"
        self.provenance_pages = self.output_dir / "provenance" / "pages"
        self.commit_dir = self.output_dir / "commits"
        self.raw_path = self.output_dir / "raw" / "studies_raw.jsonl"
        self.canonical_path = self.output_dir / "canonical" / "studies_canonical.jsonl"
        self.quarantine_path = self.output_dir / "quarantine" / "invalid_records.jsonl"
        self.provenance_path = self.output_dir / "provenance" / "source_records.jsonl"
        self.checkpoint_path = self.output_dir / "checkpoint.json"
        self.manifest_path = self.output_dir / "extraction_manifest.json"
        for p in (self.raw_pages, self.canon_pages, self.quarantine_pages, self.provenance_pages, self.commit_dir, self.transport_dir):
            p.mkdir(parents=True, exist_ok=True)
        self.query_descriptor = {
            "query": config.query,
            "filters": config.filters or {},
            "page_size": config.page_size,
            "max_studies": config.max_studies,
            "use_bulk": config.use_bulk,
        }
        self.query_fingerprint = _json_sha256(self.query_descriptor)

    def _capture_transport(self, url: str, metadata: Dict[str, Any], payload: bytes) -> None:
        """Persist exact non-stream HTTP response bytes before parsing.

        The bulk ZIP is a streaming response and is retained separately as the
        exact downloaded archive; version/API JSON responses flow through here.
        """
        if url.rstrip("/").endswith("/version"):
            kind = "version"
        elif "/studies/" in url.rstrip("/"):
            kind = "study"
        else:
            kind = "studies_page"
        existing = sorted(self.transport_dir.glob("*.meta.json"))
        ordinal = len(existing)
        stem = f"{ordinal:08d}_{kind}"
        payload_path = self.transport_dir / f"{stem}.json"
        meta_path = self.transport_dir / f"{stem}.meta.json"
        _atomic_bytes(payload_path, bytes(payload))
        meta = {
            "transport_schema_version": "frontier-http-transport-1.0",
            "source": SOURCE_NAME,
            "kind": kind,
            "url": url,
            "request": metadata.get("params") or {},
            "status_code": metadata.get("status_code"),
            "content_type": metadata.get("content_type"),
            "retrieved_at": _utc_now(),
            "path": str(payload_path.relative_to(self.output_dir)),
            "sha256": _sha256(payload_path),
            "bytes": payload_path.stat().st_size,
        }
        _atomic_text(meta_path, json.dumps(meta, indent=2, sort_keys=True) + "\n")
        self._last_transport_by_kind[kind] = meta["path"]

    def _finalize_transport_index(self) -> Dict[str, Any]:
        rows = []
        for meta_path in sorted(self.transport_dir.glob("*.meta.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            payload_path = self.output_dir / meta["path"]
            if not payload_path.exists() or _sha256(payload_path) != meta.get("sha256"):
                raise RuntimeError(f"transport artifact integrity failure: {meta.get('path')}")
            rows.append(meta)
        _atomic_text(
            self.transport_index_path,
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        )
        return {
            "transport_response_count": len(rows),
            "transport_index": str(self.transport_index_path.relative_to(self.output_dir)),
            "transport_index_sha256": _sha256(self.transport_index_path),
        }

    def _load_checkpoint(self) -> Dict[str, Any]:
        if not self.config.resume or not self.checkpoint_path.exists():
            return {}
        cp = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if cp.get("query_fingerprint") != self.query_fingerprint:
            raise RuntimeError("checkpoint belongs to a different query/configuration; use a new output directory or --no-resume")
        return cp

    def _save_checkpoint(self, **values: Any) -> None:
        body = {
            "checkpoint_schema_version": "ctg-checkpoint-2.0",
            "query_fingerprint": self.query_fingerprint,
            **values,
            "updated_at": _utc_now(),
        }
        _atomic_text(self.checkpoint_path, json.dumps(body, indent=2, sort_keys=True) + "\n")

    @staticmethod
    def _write_page_atomic(path: pathlib.Path, records: Iterable[Dict[str, Any]]) -> int:
        rows = list(records)
        lines = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
        _atomic_text(path, lines)
        return len(rows)

    @staticmethod
    def _source_record_sha256(raw: Dict[str, Any]) -> str:
        return _json_sha256(raw)

    def _canonical_and_provenance(
        self,
        raw: Dict[str, Any],
        parsed,
        source_version: ApiVersionInfo,
        run_id: str,
        retrieved_at: str,
        transport_raw_locator: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        source_hash = self._source_record_sha256(raw)
        source_updated_at = parsed.last_update_post_date
        source_url = f"https://clinicaltrials.gov/study/{parsed.nct_id}"
        provenance = {
            "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
            "source": SOURCE_NAME,
            "source_record_id": parsed.nct_id,
            "source_version_id": source_updated_at or "",
            "source_record_sha256": source_hash,
            "run_id": run_id,
            "parser_version": PARSER_VERSION,
            "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
            "retrieved_at": retrieved_at,
            "source_version": source_version.data_timestamp,
            "source_updated_at": source_updated_at,
            "source_url": source_url,
            "raw_locator": None,
            "transport_raw_locator": transport_raw_locator,
            "parse_status": "parsed",
            "parse_warnings": [],
        }
        row = parsed.to_dict(include_raw=True)
        row.update({
            "run_id": run_id,
            "source": SOURCE_NAME,
            "source_record_sha256": source_hash,
            "source_data_timestamp": source_version.data_timestamp,
            "source_api_version": source_version.api_version,
            "parser_version": PARSER_VERSION,
            "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
            "retrieved_at": retrieved_at,
            "source_url": source_url,
        })
        return row, provenance

    def _reconcile_resume_boundary(self, checkpoint: Dict[str, Any]) -> None:
        """Discard every artifact that is not checkpoint-committed."""
        boundary = int(checkpoint.get("next_page_index", 0)) if checkpoint else 0
        for directory in (self.raw_pages, self.canon_pages, self.quarantine_pages, self.provenance_pages, self.commit_dir):
            for path in directory.glob("*.json*"):
                try:
                    index = int(path.name.split(".", 1)[0])
                except ValueError as exc:
                    raise RuntimeError(f"unexpected page artifact name: {path.name}") from exc
                if index >= boundary:
                    path.unlink()
        if checkpoint:
            self._verify_committed_pages(boundary)

    def _verify_committed_pages(self, boundary: int) -> None:
        for index in range(boundary):
            commit_path = self.commit_dir / f"{index:08d}.json"
            if not commit_path.exists():
                raise RuntimeError(f"missing commit metadata for checkpoint-committed page {index}")
            commit = json.loads(commit_path.read_text(encoding="utf-8"))
            for key, directory in (
                ("raw_sha256", self.raw_pages),
                ("canonical_sha256", self.canon_pages),
                ("quarantine_sha256", self.quarantine_pages),
                ("provenance_sha256", self.provenance_pages),
            ):
                path = directory / f"{index:08d}.jsonl"
                expected = commit.get(key)
                if not path.exists() or not expected or _sha256(path) != expected:
                    raise RuntimeError(f"committed page integrity failure: page={index} artifact={key}")
            transport_locator = commit.get("transport_raw_locator")
            if transport_locator:
                transport_path = self.output_dir / transport_locator
                expected_transport = commit.get("transport_raw_sha256")
                if not transport_path.exists() or not expected_transport or _sha256(transport_path) != expected_transport:
                    raise RuntimeError(f"committed page transport integrity failure: page={index}")

    def _commit_page(
        self,
        page_index: int,
        raw_page: list,
        canonical_page: list,
        quarantine_page: list,
        provenance_page: list,
        *,
        next_page_token: Optional[str],
        transport_raw_locator: Optional[str] = None,
    ) -> Dict[str, Any]:
        paths = {
            "raw": self.raw_pages / f"{page_index:08d}.jsonl",
            "canonical": self.canon_pages / f"{page_index:08d}.jsonl",
            "quarantine": self.quarantine_pages / f"{page_index:08d}.jsonl",
            "provenance": self.provenance_pages / f"{page_index:08d}.jsonl",
        }
        self._write_page_atomic(paths["raw"], raw_page)
        self._write_page_atomic(paths["canonical"], canonical_page)
        self._write_page_atomic(paths["quarantine"], quarantine_page)
        self._write_page_atomic(paths["provenance"], provenance_page)
        commit = {
            "commit_schema_version": "ctg-page-commit-1.0",
            "page_index": page_index,
            "next_page_token_sha256": hashlib.sha256((next_page_token or "").encode()).hexdigest(),
            "observed_records": len(raw_page),
            "valid_records": len(canonical_page),
            "quarantined_records": len(quarantine_page),
            "raw_sha256": _sha256(paths["raw"]),
            "canonical_sha256": _sha256(paths["canonical"]),
            "quarantine_sha256": _sha256(paths["quarantine"]),
            "provenance_sha256": _sha256(paths["provenance"]),
            "transport_raw_locator": transport_raw_locator,
            "transport_raw_sha256": (
                _sha256(self.output_dir / transport_raw_locator) if transport_raw_locator else None
            ),
            "committed_at": _utc_now(),
        }
        _atomic_text(self.commit_dir / f"{page_index:08d}.json", json.dumps(commit, indent=2, sort_keys=True) + "\n")
        return commit

    def _seen_ids(self) -> Set[str]:
        seen: Set[str] = set()
        for path in sorted(self.canon_pages.glob("*.jsonl")):
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        row = json.loads(line)
                        nct_id = row.get("nct_id")
                        if nct_id:
                            if nct_id in seen:
                                raise RuntimeError(f"duplicate NCTId already present in committed pages: {nct_id}")
                            seen.add(nct_id)
        return seen

    def _count_committed(self) -> Tuple[int, int, int]:
        observed = valid = quarantined = 0
        for path in sorted(self.commit_dir.glob("*.json")):
            c = json.loads(path.read_text(encoding="utf-8"))
            observed += int(c.get("observed_records", 0))
            valid += int(c.get("valid_records", 0))
            quarantined += int(c.get("quarantined_records", 0))
        return observed, valid, quarantined

    def _finalize_monoliths(self) -> None:
        for pages_dir, output in (
            (self.raw_pages, self.raw_path),
            (self.canon_pages, self.canonical_path),
            (self.quarantine_pages, self.quarantine_path),
            (self.provenance_pages, self.provenance_path),
        ):
            tmp = output.with_suffix(output.suffix + ".tmp")
            output.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("wb") as out:
                for page in sorted(pages_dir.glob("*.jsonl")):
                    with page.open("rb") as src:
                        for chunk in iter(lambda: src.read(1024 * 1024), b""):
                            out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, output)
            _fsync_dir(output.parent)

    def _clear_page_artifacts(self) -> None:
        for directory in (self.raw_pages, self.canon_pages, self.quarantine_pages, self.provenance_pages, self.commit_dir):
            for path in directory.glob("*.json*"):
                path.unlink()

    @staticmethod
    def _quarantine(raw: Any, error: BaseException, *, retrieved_at: str, archive_name: Optional[str] = None) -> Dict[str, Any]:
        if isinstance(raw, (bytes, bytearray)):
            payload = bytes(raw)
            source_hash = hashlib.sha256(payload).hexdigest()
            raw_value = None
            raw_base64 = base64.b64encode(payload).decode("ascii")
        else:
            source_hash = _json_sha256(raw) if raw is not None else None
            raw_value = raw
            raw_base64 = None
        return {
            "source": SOURCE_NAME,
            "retrieved_at": retrieved_at,
            "archive_name": archive_name,
            "error_type": type(error).__name__,
            "error": str(error),
            "source_record_sha256": source_hash,
            "raw": raw_value,
            "raw_base64": raw_base64,
        }

    def _manifest(
        self,
        *,
        run_id: str,
        started_at: str,
        start_version: ApiVersionInfo,
        end_version: ApiVersionInfo,
        observed: int,
        valid: int,
        quarantined: int,
        unique_records: int,
        pages: int,
        method: str,
        expected_total: Optional[int],
        truncated: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source_changed = start_version.data_timestamp != end_version.data_timestamp
        complete = expected_total is not None and observed == expected_total
        warnings = []
        errors = []
        if source_changed:
            warnings.append("source dataTimestamp changed during run")
        if quarantined:
            warnings.append(f"{quarantined} source records quarantined")
        if observed != unique_records + quarantined:
            errors.append("observed count does not reconcile to unique valid IDs plus quarantined records")
        if expected_total is not None and observed != expected_total and not truncated:
            errors.append(f"observed {observed} records but source reported {expected_total}")
        if truncated:
            status = "TRUNCATED"
        elif errors:
            status = "FAIL"
        elif not source_changed and complete and quarantined == 0:
            status = "PASS"
        else:
            status = "WARN"
        manifest = {
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "run_id": run_id,
            "source": SOURCE_NAME,
            "mode": method,
            "method": method,
            "status": "completed" if not errors else "failed",
            "certification_status": status,
            "started_at": started_at,
            "completed_at": _utc_now(),
            "parser_version": PARSER_VERSION,
            "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
            "query": self.query_descriptor,
            "query_fingerprint": self.query_fingerprint,
            "api_version_start": start_version.api_version,
            "api_version_end": end_version.api_version,
            "source_version_start": start_version.data_timestamp,
            "source_version_end": end_version.data_timestamp,
            "data_timestamp_start": start_version.data_timestamp,
            "data_timestamp_end": end_version.data_timestamp,
            "source_changed_during_run": source_changed,
            "snapshot_consistent": not source_changed,
            "expected_records": expected_total,
            "expected_total": expected_total,
            "observed_records": observed,
            "valid_records": valid,
            "quarantined_records": quarantined,
            "unique_records": unique_records,
            "records": valid,
            "pages": pages,
            "truncated": truncated,
            "truncated_by_max": truncated,
            "complete_against_source": complete,
            "complete_against_total": complete,
            "warnings": warnings,
            "errors": errors,
            "raw_sha256": _sha256(self.raw_path),
            "canonical_sha256": _sha256(self.canonical_path),
            "quarantine_sha256": _sha256(self.quarantine_path),
            "provenance_sha256": _sha256(self.provenance_path),
            "artifacts": {
                "raw": str(self.raw_path.relative_to(self.output_dir)),
                "canonical": str(self.canonical_path.relative_to(self.output_dir)),
                "quarantine": str(self.quarantine_path.relative_to(self.output_dir)),
                "provenance": str(self.provenance_path.relative_to(self.output_dir)),
            },
        }
        if extra:
            manifest.update(extra)
        return manifest

    def _run_bulk(self, start_version: ApiVersionInfo, started_at: str, run_id: str) -> Dict[str, Any]:
        self._clear_page_artifacts()
        self.checkpoint_path.unlink(missing_ok=True)
        bulk_path = self.output_dir / "bulk" / "studies.json.zip"
        self.client.download_bulk(bulk_path)
        bulk_sha256 = _sha256(bulk_path)
        seen: Set[str] = set()
        page_index = 0
        observed = valid = quarantined = 0
        raw_page: list = []
        canonical_page: list = []
        quarantine_page: list = []
        provenance_page: list = []

        with zipfile.ZipFile(bulk_path) as zf:
            json_names = sorted(n for n in zf.namelist() if n.lower().endswith(".json"))
            expected_archive_records = len(json_names)
            for name in json_names:
                if self.config.max_studies is not None and observed >= self.config.max_studies:
                    break
                retrieved_at = _utc_now()
                payload = zf.read(name)
                try:
                    raw = json.loads(payload)
                except Exception as exc:
                    observed += 1
                    quarantine_page.append(self._quarantine(payload, exc, retrieved_at=retrieved_at, archive_name=name))
                    quarantined += 1
                    continue
                observed += 1
                raw_page.append(raw)
                try:
                    parsed = parse_study(raw)
                    if parsed.nct_id in seen:
                        raise ValueError(f"duplicate NCTId in bulk archive: {parsed.nct_id}")
                    seen.add(parsed.nct_id)
                    row, provenance = self._canonical_and_provenance(
                        raw, parsed, start_version, run_id, retrieved_at,
                        transport_raw_locator="bulk/studies.json.zip",
                    )
                    provenance["raw_locator"] = f"bulk/studies.json.zip#{name}"
                    canonical_page.append(row)
                    provenance_page.append(provenance)
                    valid += 1
                except Exception as exc:
                    quarantine_page.append(self._quarantine(raw, exc, retrieved_at=retrieved_at, archive_name=name))
                    quarantined += 1

                if len(raw_page) + len(quarantine_page) >= 1000:
                    self._commit_page(
                        page_index, raw_page, canonical_page, quarantine_page, provenance_page,
                        next_page_token=None, transport_raw_locator="bulk/studies.json.zip",
                    )
                    page_index += 1
                    raw_page, canonical_page, quarantine_page, provenance_page = [], [], [], []

            if raw_page or canonical_page or quarantine_page or provenance_page:
                self._commit_page(
                    page_index, raw_page, canonical_page, quarantine_page, provenance_page,
                    next_page_token=None, transport_raw_locator="bulk/studies.json.zip",
                )
                page_index += 1

        self._finalize_monoliths()
        end_version = self.client.fetch_version()
        transport = self._finalize_transport_index()
        truncated = bool(self.config.max_studies is not None and observed < expected_archive_records and observed >= self.config.max_studies)
        manifest = self._manifest(
            run_id=run_id,
            started_at=started_at,
            start_version=start_version,
            end_version=end_version,
            observed=observed,
            valid=valid,
            quarantined=quarantined,
            unique_records=len(seen),
            pages=page_index,
            method="bulk_json_zip",
            expected_total=expected_archive_records,
            truncated=truncated,
            extra={
                "bulk_zip_sha256": bulk_sha256,
                "bulk_archive_json_files": expected_archive_records,
                "transport_capture_status": (
                    "PASS_EXACT_BULK_ZIP_PLUS_HTTP_VERSION_RESPONSES"
                    if self._native_transport_capture else "TEST_INJECTED_BULK_ARCHIVE"
                ),
                **transport,
            },
        )
        _atomic_text(self.manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return manifest

    def run(self) -> Dict[str, Any]:
        current_version = self.client.fetch_version()
        started_at = _utc_now()
        cp = self._load_checkpoint() if not self.config.use_bulk else {}
        if cp:
            original_ts = cp.get("data_timestamp_start")
            original_api = cp.get("api_version_start")
            if original_ts and original_ts != current_version.data_timestamp:
                raise RuntimeError(
                    "ClinicalTrials.gov dataTimestamp changed since checkpoint; restart into a fresh output directory "
                    "to avoid mixing source revisions"
                )
            start_version = ApiVersionInfo(original_api or current_version.api_version, original_ts or current_version.data_timestamp, {})
            started_at = cp.get("started_at") or started_at
            run_id = cp.get("run_id") or str(uuid.uuid4())
        else:
            start_version = current_version
            run_id = str(uuid.uuid4())

        if self.config.use_bulk:
            return self._run_bulk(start_version, started_at, run_id)

        self._reconcile_resume_boundary(cp)
        token = cp.get("next_page_token")
        page_index = int(cp.get("next_page_index", 0))
        seen = self._seen_ids()
        observed, valid, quarantined = self._count_committed()
        expected_total = cp.get("expected_total")
        cfg = FetchConfig(page_size=self.config.page_size, query=self.config.query, filters=self.config.filters, count_total=True)

        limit_hit = False
        while True:
            if self.config.max_studies is not None and observed >= self.config.max_studies:
                limit_hit = True
                break
            data = self.client.fetch_page(token, cfg)
            page_transport_locator = self._last_transport_by_kind.get("studies_page") if self._native_transport_capture else None
            if self._native_transport_capture and not page_transport_locator:
                raise RuntimeError("native ClinicalTrials API page returned without retained transport evidence")
            if expected_total is None:
                expected_total = data.get("totalCount")
            studies = data.get("studies") or []
            if not isinstance(studies, list):
                raise ValueError("ClinicalTrials.gov `studies` must be a list")
            if not studies:
                break

            raw_page: list = []
            canonical_page: list = []
            quarantine_page: list = []
            provenance_page: list = []
            for raw in studies:
                if self.config.max_studies is not None and observed >= self.config.max_studies:
                    limit_hit = True
                    break
                observed += 1
                retrieved_at = _utc_now()
                if not isinstance(raw, dict):
                    quarantine_page.append(self._quarantine(raw, ValueError("study item must be an object"), retrieved_at=retrieved_at))
                    quarantined += 1
                    continue
                raw_page.append(raw)
                try:
                    parsed = parse_study(raw)
                    if parsed.nct_id in seen:
                        raise ValueError(f"duplicate NCTId observed during pagination: {parsed.nct_id}")
                    seen.add(parsed.nct_id)
                    row, provenance = self._canonical_and_provenance(
                        raw, parsed, start_version, run_id, retrieved_at, page_transport_locator
                    )
                    canonical_page.append(row)
                    provenance_page.append(provenance)
                    valid += 1
                except Exception as exc:
                    quarantine_page.append(self._quarantine(raw, exc, retrieved_at=retrieved_at))
                    quarantined += 1

            next_token = data.get("nextPageToken")
            self._commit_page(
                page_index, raw_page, canonical_page, quarantine_page, provenance_page,
                next_page_token=next_token, transport_raw_locator=page_transport_locator,
            )
            page_index += 1
            token = next_token
            self._save_checkpoint(
                run_id=run_id,
                started_at=started_at,
                next_page_token=token,
                next_page_index=page_index,
                observed_records=observed,
                valid_records=valid,
                quarantined_records=quarantined,
                unique_records=len(seen),
                expected_total=expected_total,
                data_timestamp_start=start_version.data_timestamp,
                api_version_start=start_version.api_version,
            )
            if limit_hit or not token:
                break

        self._finalize_monoliths()
        end_version = self.client.fetch_version()
        transport = self._finalize_transport_index()
        truncated = bool(limit_hit and (expected_total is None or observed < expected_total))
        manifest = self._manifest(
            run_id=run_id,
            started_at=started_at,
            start_version=start_version,
            end_version=end_version,
            observed=observed,
            valid=valid,
            quarantined=quarantined,
            unique_records=len(seen),
            pages=page_index,
            method="paginated_api",
            expected_total=expected_total,
            truncated=truncated,
            extra={
                "transport_capture_status": (
                    "PASS_EXACT_HTTP_RESPONSES" if self._native_transport_capture
                    else "TEST_INJECTED_NO_NATIVE_TRANSPORT_CAPTURE"
                ),
                **transport,
            },
        )
        _atomic_text(self.manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        self.checkpoint_path.unlink(missing_ok=True)
        return manifest
