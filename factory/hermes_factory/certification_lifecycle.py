"""Fail-closed lifecycle policy for role-specific semantic certifications.

Promotions are intentionally absent. A certificate can be administratively
suspended, demoted, expired, or retired, but regaining CERTIFIED authority requires
the normal source-bound benchmark/certification path. RETIRED is terminal.

The living architecture requires an expiry/retest policy in a later turn but does
not define a wall-clock interval. This module therefore implements explicit EXPIRED
state without inventing an automatic TTL.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

DOWNWARD_TARGETS = {"SUSPENDED", "DEMOTED", "EXPIRED", "RETIRED"}
TRANSITIONS = {
    "CERTIFIED": {"SUSPENDED", "DEMOTED", "EXPIRED", "RETIRED"},
    "CERTIFIED_WITH_LIMITS": {"SUSPENDED", "DEMOTED", "EXPIRED", "RETIRED"},
    "PROVISIONAL": {"SUSPENDED", "DEMOTED", "EXPIRED", "RETIRED"},
    "BENCHMARKING": {"SUSPENDED", "RETIRED"},
    "SUSPENDED": {"DEMOTED", "EXPIRED", "RETIRED"},
    "DEMOTED": {"EXPIRED", "RETIRED"},
    "EXPIRED": {"RETIRED"},
    "REJECTED": {"RETIRED"},
    "BLOCKED_EXTERNAL": {"RETIRED"},
    "FIXTURE_NOT_EMPIRICAL": {"RETIRED"},
    "UNBENCHMARKED": {"RETIRED"},
    "RETIRED": set(),
}


def validate_reason(reason: str) -> str:
    value = str(reason or "").strip()
    if not value:
        raise ValueError("lifecycle_reason_required")
    return value


def validate_transition(current_status: str, target_status: str) -> tuple[str, str]:
    current = str(current_status or "").strip().upper()
    target = str(target_status or "").strip().upper()
    if target not in DOWNWARD_TARGETS:
        raise ValueError(f"lifecycle_target_not_downward:{target}")
    allowed = TRANSITIONS.get(current)
    if allowed is None:
        raise ValueError(f"lifecycle_current_status_unknown:{current}")
    if target not in allowed:
        raise ValueError(f"lifecycle_transition_not_allowed:{current}->{target}")
    return current, target


def build_lifecycle_event(*, certification_key: str, current_status: str, target_status: str,
                          reason: str, incident_ref: str | None = None,
                          actor: str = "OPERATOR", now_epoch: float | None = None) -> dict[str, Any]:
    current, target = validate_transition(current_status, target_status)
    reason = validate_reason(reason)
    timestamp = round(float(time.time() if now_epoch is None else now_epoch), 3)
    payload = {
        "certification_key": str(certification_key),
        "from_status": current,
        "to_status": target,
        "reason": reason,
        "incident_ref": str(incident_ref).strip() if incident_ref else None,
        "actor": str(actor or "OPERATOR").strip() or "OPERATOR",
        "at_epoch": timestamp,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["event_id"] = "CERTLIFE-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return payload


def apply_downward_transition(entry: dict, *, certification_key: str, target_status: str,
                              reason: str, incident_ref: str | None = None,
                              actor: str = "OPERATOR", now_epoch: float | None = None) -> tuple[dict, dict]:
    if not isinstance(entry, dict):
        raise ValueError("certification_entry_not_object")
    current = str(entry.get("status") or "UNBENCHMARKED")
    event = build_lifecycle_event(
        certification_key=certification_key,
        current_status=current,
        target_status=target_status,
        reason=reason,
        incident_ref=incident_ref,
        actor=actor,
        now_epoch=now_epoch,
    )
    updated = dict(entry)
    history = updated.get("lifecycle_history")
    if history is None:
        history = []
    if not isinstance(history, list):
        raise ValueError("lifecycle_history_not_array")
    updated["lifecycle_history"] = [*history, event]
    updated["status"] = event["to_status"]
    updated["lifecycle_last_event_id"] = event["event_id"]
    updated["lifecycle_last_changed_at_epoch"] = event["at_epoch"]
    updated["lifecycle_last_reason"] = event["reason"]
    return updated, event


def recertification_history(existing_entry: dict | None, new_status: str, *, now_epoch: float | None = None) -> list[dict]:
    """Preserve demotion history when benchmark certification re-establishes authority.

    RETIRED is terminal. Other non-authoritative states may be replaced only by the
    normal benchmark certifier, which records a RECERTIFIED event in the retained
    history. This helper does not itself grant certification.
    """
    if existing_entry is None:
        return []
    if not isinstance(existing_entry, dict):
        raise ValueError("existing_certification_entry_not_object")
    prior = str(existing_entry.get("status") or "UNBENCHMARKED").upper()
    if prior == "RETIRED":
        raise ValueError("retired_certification_cannot_be_reactivated")
    history = existing_entry.get("lifecycle_history") or []
    if not isinstance(history, list):
        raise ValueError("lifecycle_history_not_array")
    if prior in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"} and prior == str(new_status).upper():
        return list(history)
    timestamp = round(float(time.time() if now_epoch is None else now_epoch), 3)
    event = {
        "certification_key": None,
        "from_status": prior,
        "to_status": str(new_status).upper(),
        "reason": "source-bound benchmark recertification",
        "incident_ref": None,
        "actor": "BENCHMARK_CERTIFIER",
        "at_epoch": timestamp,
    }
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    event["event_id"] = "CERTLIFE-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return [*history, event]
