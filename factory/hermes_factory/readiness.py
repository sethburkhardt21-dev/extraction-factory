from __future__ import annotations
from typing import Dict, Iterable, List
from .models import Gate, GateResult

ACCEPTABLE_DIRECT = {GateResult.PASS.value, GateResult.NOT_APPLICABLE.value}


def derive_readiness(gates: Iterable[Gate]) -> Dict:
    gates = list(gates)
    blockers = []
    review_queues = []
    for gate in gates:
        if not gate.required:
            continue
        if gate.result in ACCEPTABLE_DIRECT:
            continue
        if gate.result == GateResult.FAIL_REVIEW_REQUIRED.value and gate.bounded_queue:
            review_queues.append({"gate": gate.name, "queue": gate.bounded_queue})
            continue
        blockers.append({"gate": gate.name, "result": gate.result, "detail": gate.detail})
    frontier_ready = not blockers
    # Precedence is fail-closed. A hard integrity/runtime failure always dominates
    # external provider blockers; otherwise READY_FOR_PROVIDER could mask a broken
    # build simply because a model was also unavailable/unbenchmarked.
    hard_blocking = any(x["result"] in {GateResult.FAIL_BLOCKING.value, GateResult.NOT_RUN.value} for x in blockers)
    unbounded_review = any(x["result"] == GateResult.FAIL_REVIEW_REQUIRED.value for x in blockers)
    external_blocking = any(x["result"] == GateResult.BLOCKED_EXTERNAL.value for x in blockers)
    if frontier_ready:
        status = "FRONTIER_REVIEW_READY"
    elif hard_blocking or unbounded_review:
        status = "NOT_READY"
    elif external_blocking:
        status = "READY_FOR_PROVIDER"
    else:
        status = "NOT_READY"
    return {
        "status": status,
        "frontier_review_ready": frontier_ready,
        "blockers": blockers,
        "bounded_review_queues": review_queues,
        "gates": [g.to_dict() for g in gates],
        "claim_boundary": "FRONTIER_REVIEW_READY is mechanically derived; it does not mean every clinical assertion is proven true.",
    }


def required_gate_names() -> List[str]:
    return [
        "SOURCE_AUTHORITY", "SOURCE_HASH", "BUILD_INTEGRITY", "RUNTIME_LOCK", "SCHEMA", "PROVENANCE",
        "EVIDENCE_SPANS", "EVIDENCE_HASHES", "LINEAGE", "LEDGER_INTEGRITY", "STATE_RECONCILIATION",
        "CAS_CURRENT_STATE", "BLINDNESS", "INDEPENDENCE", "PRIMARY_PASS", "BLIND_RECALL_PASS",
        "SEMANTIC_PROVIDER_CERTIFICATION", "NUMERIC_CONTROL", "QUALIFIER_CONTROL", "RELATIONSHIP_CONTROL",
        "TABLE_VISUAL_CONTROL", "CROSS_PAGE_CONTROL", "PRECISION_REVIEW", "COLD_AUDIT_POLICY",
        "SEMANTIC_RECEIPTS", "PACKAGE_INTEGRITY", "09D_READONLY_BOUNDARY",
    ]
