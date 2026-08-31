"""Deterministic semantic-review routing across verifier and blind-recall evidence.

This module schedules review work; it never changes assertions, chooses a clinical
winner, resolves identity, or grants 09D authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping, Sequence

from .semantic_capsules import HIGH_RISK_ASSERTION_TYPES, CRITICAL_NUMERIC_TYPES, RELATIONSHIP_TYPES

ROUTER_SCHEMA_VERSION = "frontier-semantic-review-router-1.0"
REVIEW_CASE_SCHEMA_VERSION = "frontier-semantic-review-case-1.0"
ALLOWED_LANES = {
    "BLIND_ENTAILMENT",
    "BLIND_RECALL_REVIEW",
    "NUMERIC_BINDING",
    "QUALIFIER_SCOPE",
    "TABLE_BINDING",
    "VISUAL_BINDING",
    "RELATIONSHIP_BINDING",
    "PRECISION_REVIEW",
    "FRONTIER_ADJUDICATION",
    "COLD_AUDIT",
    "PROVENANCE_REPAIR",
}
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _case_id(payload: Mapping[str, Any]) -> str:
    return "SEMCASE:" + hashlib.sha256(_canonical(payload)).hexdigest()[:32]


def _max_risk(*levels: str) -> str:
    clean = [x for x in levels if x in RISK_ORDER]
    return max(clean, key=lambda x: RISK_ORDER[x]) if clean else "LOW"


def _build_case(*, reason: str, risk_tier: str, required_lanes: Sequence[str], assertion_ids: Sequence[str] = (), recall_assertion_ids: Sequence[str] = (), source_unit_id: str | None = None, detail: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    lanes = list(dict.fromkeys(required_lanes))
    unknown = [x for x in lanes if x not in ALLOWED_LANES]
    if unknown:
        raise ValueError("unknown semantic review lanes: " + ", ".join(unknown))
    identity = {
        "reason": reason,
        "risk_tier": risk_tier,
        "required_lanes": lanes,
        "assertion_ids": sorted(set(assertion_ids)),
        "recall_assertion_ids": sorted(set(recall_assertion_ids)),
        "source_unit_id": source_unit_id,
        "detail": dict(detail or {}),
    }
    return {
        "review_case_schema_version": REVIEW_CASE_SCHEMA_VERSION,
        "review_case_id": _case_id(identity),
        **identity,
        "status": "OPEN",
        "automatic_action_allowed": False,
        "automatic_repair_allowed": False,
        "automatic_selection_allowed": False,
        "candidate_resolution_allowed": False,
        "canonical_authority": False,
        "generation_eligible": False,
        "public_eligible": False,
    }


def _recall_risk_and_lanes(assertion: Mapping[str, Any] | None) -> tuple[str, list[str]]:
    if not assertion:
        return "MEDIUM", ["BLIND_ENTAILMENT", "BLIND_RECALL_REVIEW", "PRECISION_REVIEW"]
    at = str(assertion.get("assertion_type") or "")
    numeric = isinstance(assertion.get("numeric"), Mapping) and bool(assertion.get("numeric"))
    risk = "LOW"
    lanes = ["BLIND_ENTAILMENT", "BLIND_RECALL_REVIEW"]
    if at in HIGH_RISK_ASSERTION_TYPES:
        risk = "HIGH"
    elif at in RELATIONSHIP_TYPES or numeric:
        risk = "MEDIUM"
    if numeric:
        lanes.append("NUMERIC_BINDING")
    if at in HIGH_RISK_ASSERTION_TYPES:
        lanes.extend(["QUALIFIER_SCOPE", "PRECISION_REVIEW"])
    if at in RELATIONSHIP_TYPES:
        lanes.append("RELATIONSHIP_BINDING")
    if numeric and at in CRITICAL_NUMERIC_TYPES:
        risk = "CRITICAL"
        lanes.extend(["PRECISION_REVIEW", "FRONTIER_ADJUDICATION"] )
    return risk, list(dict.fromkeys(lanes))


def route_semantic_review(
    *,
    verification_events: Iterable[Mapping[str, Any]],
    recall_reconciliation: Mapping[str, Any] | None = None,
    recall_assertions: Iterable[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    events = list(verification_events)
    event_by_assertion = {str(e.get("assertion_id") or ""): e for e in events}
    recall_rows = list((recall_reconciliation or {}).get("rows") or [])
    recall_by_id = {str(a.get("assertion_id") or ""): a for a in (recall_assertions or [])}
    cases: list[Dict[str, Any]] = []

    for event in events:
        aid = str(event.get("assertion_id") or "")
        uid = str(event.get("source_unit_id") or "") or None
        verdict = str(event.get("verdict") or "")
        risk = str(event.get("risk_tier") or "LOW")
        lanes = list(event.get("required_review_lanes") or [])
        state = str(event.get("review_state") or "")
        if verdict == "PROVENANCE_INCOMPLETE":
            cases.append(_build_case(reason="PROVENANCE_INCOMPLETE", risk_tier="CRITICAL", required_lanes=["PROVENANCE_REPAIR", "COLD_AUDIT"], assertion_ids=[aid], source_unit_id=uid, detail={"review_state": state}))
        elif verdict == "NOT_ENTAILED":
            needed = [x for x in lanes if x in ALLOWED_LANES]
            if "COLD_AUDIT" not in needed:
                needed.append("COLD_AUDIT")
            cases.append(_build_case(reason="ASSERTION_NOT_ENTAILED", risk_tier=_max_risk(risk, "HIGH"), required_lanes=needed, assertion_ids=[aid], source_unit_id=uid, detail={"review_state": state, "decision_basis": event.get("decision_basis")}))
        elif verdict in {"PARTIAL", "AMBIGUOUS"} or event.get("downstream_semantic_ready") is not True:
            needed = [x for x in lanes if x in ALLOWED_LANES]
            if not needed:
                needed = ["PRECISION_REVIEW"]
            cases.append(_build_case(reason="SEMANTIC_REVIEW_UNRESOLVED", risk_tier=risk, required_lanes=needed, assertion_ids=[aid], source_unit_id=uid, detail={"verdict": verdict, "review_state": state, "unresolved_warning_codes": event.get("unresolved_warning_codes") or []}))
        elif risk == "CRITICAL" or state == "FRONTIER_ADJUDICATION_REQUIRED":
            cases.append(_build_case(reason="CRITICAL_ENTAILED_REQUIRES_ADJUDICATION", risk_tier="CRITICAL", required_lanes=["FRONTIER_ADJUDICATION"], assertion_ids=[aid], source_unit_id=uid, detail={"verdict": verdict}))

    for row in recall_rows:
        state = str(row.get("reconciliation_state") or "")
        uid = str(row.get("source_unit_id") or "") or None
        if state == "RECALL_ONLY_CANDIDATE":
            rid = str(row.get("recall_assertion_id") or "")
            rrisk, rlanes = _recall_risk_and_lanes(recall_by_id.get(rid))
            cases.append(_build_case(reason="RECALL_ONLY_CANDIDATE", risk_tier=rrisk, required_lanes=rlanes, recall_assertion_ids=[rid], source_unit_id=uid, detail={"recall_assertion_type":(recall_by_id.get(rid) or {}).get("assertion_type")}))
        elif state == "SAME_EVIDENCE_SEMANTIC_DISAGREEMENT":
            pid = str(row.get("primary_assertion_id") or "")
            rid = str(row.get("recall_assertion_id") or "")
            rrisk, rlanes = _recall_risk_and_lanes(recall_by_id.get(rid))
            pevent = event_by_assertion.get(pid) or {}
            risk = _max_risk("HIGH", rrisk, str(pevent.get("risk_tier") or "LOW"))
            lanes = list(dict.fromkeys([*(pevent.get("required_review_lanes") or []), *rlanes, "PRECISION_REVIEW", "FRONTIER_ADJUDICATION"]))
            cases.append(_build_case(reason="SAME_EVIDENCE_SEMANTIC_DISAGREEMENT", risk_tier=risk, required_lanes=lanes, assertion_ids=[pid], recall_assertion_ids=[rid], source_unit_id=uid, detail={"primary_verdict":pevent.get("verdict"),"recall_assertion_type":(recall_by_id.get(rid) or {}).get("assertion_type")}))
        # PRIMARY_ONLY and exact agreement are coverage evidence, not automatically defects.

    unique = {case["review_case_id"]: case for case in cases}
    cases = [unique[k] for k in sorted(unique)]
    reason_counts = {reason: sum(1 for case in cases if case["reason"] == reason) for reason in sorted({c["reason"] for c in cases})}
    lane_counts = {lane: sum(1 for case in cases if lane in case["required_lanes"]) for lane in sorted(ALLOWED_LANES)}
    return {
        "semantic_review_router_schema_version": ROUTER_SCHEMA_VERSION,
        "status": "PASS",
        "review_cases": cases,
        "metrics": {
            "verification_events_seen": len(events),
            "recall_reconciliation_rows_seen": len(recall_rows),
            "recall_assertions_seen": len(recall_by_id),
            "open_review_cases": len(cases),
            "reason_counts": reason_counts,
            "lane_counts": lane_counts,
            "risk_counts": {risk: sum(1 for case in cases if case["risk_tier"] == risk) for risk in RISK_ORDER},
        },
        "automatic_action_allowed": False,
        "automatic_repair_allowed": False,
        "automatic_selection_allowed": False,
        "candidate_resolution_performed": False,
        "09d_comparison_performed": False,
        "authority_granted": False,
    }


def validate_review_case(case: Mapping[str, Any]) -> list[str]:
    errors = []
    if case.get("review_case_schema_version") != REVIEW_CASE_SCHEMA_VERSION:
        errors.append("review_case_schema_version mismatch")
    if not isinstance(case.get("review_case_id"), str) or not str(case.get("review_case_id")).startswith("SEMCASE:"):
        errors.append("review_case_id invalid")
    if case.get("risk_tier") not in RISK_ORDER:
        errors.append("risk_tier invalid")
    lanes = case.get("required_lanes")
    if not isinstance(lanes, list) or any(x not in ALLOWED_LANES for x in lanes):
        errors.append("required_lanes invalid")
    for key in ("automatic_action_allowed", "automatic_repair_allowed", "automatic_selection_allowed", "candidate_resolution_allowed", "canonical_authority", "generation_eligible", "public_eligible"):
        if case.get(key) is not False:
            errors.append(f"{key} must be false")
    return errors
