"""Shared certification-state policy for lifecycle and benchmark recertification.

A semantic certificate may be administratively deactivated after a regression or
safety event. Replaying the exact benchmark evidence that was invalidated must not
restore runtime authority. Reactivation through the benchmark certifier therefore
requires a new evidence fingerprint. RETIRED certification keys remain terminal.

The fingerprint is deliberately evidence-oriented, not wall-clock-oriented. No
automatic TTL is invented here.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
CERTIFIED_STATUSES = {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}
STATUS_PRIORITY = (
    "CERTIFIED", "CERTIFIED_WITH_LIMITS", "SUSPENDED", "DEMOTED", "EXPIRED",
    "PROVISIONAL", "BENCHMARKING", "BLOCKED_EXTERNAL", "REJECTED",
    "FIXTURE_NOT_EMPIRICAL", "RETIRED", "UNBENCHMARKED",
)
EVIDENCE_SCHEMA = "hermes-certification-evidence-1.0"
INVALIDATION_SCHEMA = "hermes-certification-evidence-invalidation-1.0"


def parse_certification_key(key: str) -> tuple[str, str, str, str, str, str]:
    parts = str(key or "").split("|")
    if len(parts) != 6 or any(not x for x in parts):
        raise ValueError("certification_key_must_have_6_nonempty_fields")
    return tuple(parts)  # type: ignore[return-value]


def aggregate_role_status(certifications: dict, *, role: str, work_class: str, benchmark_version: str) -> str:
    if not isinstance(certifications, dict):
        raise ValueError("registry_certifications_not_object")
    statuses: list[str] = []
    for key, entry in certifications.items():
        if not isinstance(entry, dict):
            continue
        try:
            _, _, key_role, key_work, _, key_benchmark = parse_certification_key(key)
        except ValueError:
            continue
        if key_role == role and key_work == work_class and key_benchmark == benchmark_version:
            status = str(entry.get("status") or "UNBENCHMARKED").upper()
            if status in STATUS_PRIORITY:
                statuses.append(status)
    for state in STATUS_PRIORITY:
        if state in statuses:
            return state
    return "UNBENCHMARKED"


def _required_sha(entry: dict, field: str) -> str:
    value = str(entry.get(field) or "").lower()
    if not SHA256_RE.fullmatch(value):
        raise ValueError(f"certification_evidence_{field}_missing_or_invalid")
    return value


def certification_evidence_projection(certification_key: str, entry: dict) -> dict[str, Any]:
    """Project the benchmark evidence whose reuse can restore a role certificate."""
    if not isinstance(entry, dict):
        raise ValueError("certification_entry_not_object")
    provider, model, role, work_class, source_class, benchmark_version = parse_certification_key(certification_key)
    units = entry.get("units_in_scope")
    if not isinstance(units, list) or not units or any(not isinstance(x, str) or not x for x in units):
        raise ValueError("certification_evidence_units_in_scope_invalid")
    primary_candidate_sha = None
    if role == "BLIND_RECALL":
        primary_candidate_sha = _required_sha(entry, "primary_candidate_file_sha256")
    elif entry.get("primary_candidate_file_sha256"):
        primary_candidate_sha = _required_sha(entry, "primary_candidate_file_sha256")
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "certification_key": certification_key,
        "provider": provider,
        "model_alias": model,
        "role": role,
        "work_class": work_class,
        "source_class": source_class,
        "benchmark_version": benchmark_version,
        "source_units_sha256": _required_sha(entry, "source_units_sha256"),
        "candidate_file_sha256": _required_sha(entry, "candidate_file_sha256"),
        "primary_candidate_file_sha256": primary_candidate_sha,
        "gold_reference_sha256": _required_sha(entry, "gold_reference_sha256"),
        "gold_manifest_sha256": _required_sha(entry, "gold_manifest_sha256"),
        "registry_authority_sha256": _required_sha(entry, "registry_authority_sha256"),
        "units_in_scope": sorted(set(units)),
    }


def certification_evidence_sha256(certification_key: str, entry: dict) -> str:
    projection = certification_evidence_projection(certification_key, entry)
    canonical = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def maybe_certification_evidence_sha256(certification_key: str, entry: dict) -> str | None:
    try:
        return certification_evidence_sha256(certification_key, entry)
    except ValueError:
        return None


def invalidated_evidence_rows(registry: dict) -> list[dict]:
    rows = registry.get("invalidated_certification_evidence", [])
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError("invalidated_certification_evidence_not_array")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalidated_certification_evidence_row_not_object")
        if row.get("schema_version") != INVALIDATION_SCHEMA:
            raise ValueError("invalidated_certification_evidence_schema_invalid")
        if not isinstance(row.get("certification_key"), str) or not row["certification_key"]:
            raise ValueError("invalidated_certification_evidence_key_invalid")
        if not SHA256_RE.fullmatch(str(row.get("evidence_sha256") or "")):
            raise ValueError("invalidated_certification_evidence_sha_invalid")
    return rows


def record_evidence_invalidation(registry: dict, *, certification_key: str, entry: dict, event: dict) -> str | None:
    """Record the exact evidence invalidated by a downward lifecycle action.

    Broken/legacy non-authoritative entries may not have enough evidence to form a
    fingerprint; the lifecycle action must still be allowed. Authoritative entries
    created by the current certifier do have the required evidence chain.
    """
    evidence_sha = maybe_certification_evidence_sha256(certification_key, entry)
    event["invalidated_evidence_sha256"] = evidence_sha
    if evidence_sha is None:
        return None
    rows = invalidated_evidence_rows(registry)
    duplicate = any(
        row.get("certification_key") == certification_key and
        str(row.get("evidence_sha256") or "").lower() == evidence_sha.lower()
        for row in rows
    )
    if not duplicate:
        rows.append({
            "schema_version": INVALIDATION_SCHEMA,
            "certification_key": certification_key,
            "evidence_sha256": evidence_sha,
            "lifecycle_event_id": event.get("event_id"),
            "invalidated_at_epoch": event.get("at_epoch"),
            "to_status": event.get("to_status"),
            "incident_ref": event.get("incident_ref"),
        })
    registry["invalidated_certification_evidence"] = rows
    return evidence_sha


def recertification_block_reason(registry: dict, certification_key: str, proposed_entry: dict) -> str | None:
    """Return a fail-closed reason when proposed authority reuses invalidated evidence."""
    status = str(proposed_entry.get("status") or "UNBENCHMARKED").upper()
    if status not in CERTIFIED_STATUSES:
        return None
    retired = registry.get("retired_certification_keys", [])
    if not isinstance(retired, list) or any(not isinstance(x, str) or not x for x in retired):
        raise ValueError("retired_certification_keys_not_string_array")
    if certification_key in retired:
        return "retired_certification_key_is_terminal"
    evidence_sha = certification_evidence_sha256(certification_key, proposed_entry)
    for row in invalidated_evidence_rows(registry):
        if row.get("certification_key") == certification_key and str(row.get("evidence_sha256") or "").lower() == evidence_sha:
            event_id = str(row.get("lifecycle_event_id") or "UNKNOWN")
            return f"certification_evidence_previously_invalidated:{evidence_sha}:event={event_id}"
    return None
