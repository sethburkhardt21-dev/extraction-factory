"""Source-agnostic provenance and run-manifest contracts.

These models intentionally use only the Python standard library so every source
extractor can depend on them without creating a dependency knot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional

MANIFEST_SCHEMA_VERSION = "frontier-run-manifest-1.0"
PROVENANCE_SCHEMA_VERSION = "frontier-source-provenance-1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SourceRecordProvenance:
    source: str
    source_record_id: str
    source_record_sha256: str
    run_id: str
    parser_version: str
    canonical_schema_version: str
    retrieved_at: str
    source_version: Optional[str] = None
    source_updated_at: Optional[str] = None
    source_url: Optional[str] = None
    source_version_id: Optional[str] = None
    raw_locator: Optional[str] = None
    parse_status: str = "parsed"
    parse_warnings: List[str] = field(default_factory=list)
    provenance_schema_version: str = PROVENANCE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunManifest:
    run_id: str
    source: str
    mode: str
    parser_version: str
    canonical_schema_version: str
    started_at: str
    status: str = "running"
    certification_status: str = "PENDING"
    completed_at: Optional[str] = None
    source_version_start: Optional[str] = None
    source_version_end: Optional[str] = None
    source_changed_during_run: Optional[bool] = None
    query: Optional[Dict[str, Any]] = None
    expected_records: Optional[int] = None
    observed_records: int = 0
    valid_records: int = 0
    quarantined_records: int = 0
    unique_records: int = 0
    truncated: bool = False
    complete_against_source: Optional[bool] = None
    raw_sha256: Optional[str] = None
    canonical_sha256: Optional[str] = None
    quarantine_sha256: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    manifest_schema_version: str = MANIFEST_SCHEMA_VERSION

    def finalize(self) -> "RunManifest":
        self.completed_at = self.completed_at or utc_now_iso()
        self.status = "completed" if not self.errors else "failed"
        if self.errors:
            self.certification_status = "FAIL"
        elif self.truncated:
            self.certification_status = "TRUNCATED"
        elif self.complete_against_source is True and self.quarantined_records == 0 and not self.warnings:
            self.certification_status = "PASS"
        elif self.complete_against_source is False:
            self.certification_status = "FAIL"
        else:
            self.certification_status = "WARN"
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
