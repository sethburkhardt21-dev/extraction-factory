from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, Iterable, Set

# Only these fields may enter a blind semantic worker request.
BLIND_REQUEST_ALLOWLIST: Set[str] = {
    "request_schema_version",
    "task_role",
    "work_class",
    "source_class",
    "capsule_id",
    "run_id",
    "source_unit",
    "boundary_context",
    "task_instructions",
    "output_schema",
    "provider_constraints",
}

# Defense-in-depth. The allowlist is the primary control.
FORBIDDEN_DISCLOSURE_KEYS: Set[str] = {
    "primary_assertions",
    "primary_candidates",
    "peer_output",
    "peer_outputs",
    "reference_answer",
    "reference_answers",
    "gold_value",
    "gold",
    "gold_answers",
    "canonical_answer",
    "canonical_assertions",
    "review_decision",
    "review_decisions",
    "expected_count",
    "expected_assertion_count",
    "candidate_count",
    "hidden_answer",
    "answer_key",
}


def _contains_forbidden_key(value: Any, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            kp = f"{path}.{k}" if path else str(k)
            if str(k).lower() in FORBIDDEN_DISCLOSURE_KEYS:
                hits.append(kp)
            hits.extend(_contains_forbidden_key(v, kp))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            hits.extend(_contains_forbidden_key(v, f"{path}[{i}]"))
    return hits


def build_blind_worker_request(candidate_packet: Dict[str, Any]) -> Dict[str, Any]:
    """Construct a blind request by positive allowlist, never by deleting keys.

    Unknown top-level keys are discarded. Then the resulting packet is checked
    recursively for disclosure keys, protecting against accidental nesting.
    """
    clean = {k: deepcopy(candidate_packet[k]) for k in BLIND_REQUEST_ALLOWLIST if k in candidate_packet}
    leaks = _contains_forbidden_key(clean)
    if leaks:
        raise ValueError(f"blindness_leakage_detected:{','.join(leaks)}")
    return clean


def assert_blind_request(packet: Dict[str, Any]) -> None:
    unexpected = sorted(set(packet) - BLIND_REQUEST_ALLOWLIST)
    if unexpected:
        raise ValueError(f"blind_request_unapproved_top_level_keys:{unexpected}")
    leaks = _contains_forbidden_key(packet)
    if leaks:
        raise ValueError(f"blindness_leakage_detected:{','.join(leaks)}")
