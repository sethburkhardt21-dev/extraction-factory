from __future__ import annotations
import hashlib
from typing import Iterable, List
from .models import AssertionCandidate, SourceUnit


def deterministic_sample(candidates: Iterable[AssertionCandidate], rate: float, seed: str = "HERMES-COLD-AUDIT-v1.1") -> List[AssertionCandidate]:
    if not 0 <= rate <= 1:
        raise ValueError("rate_out_of_bounds")
    out = []
    for c in candidates:
        h = hashlib.sha256((seed + "|" + c.candidate_id).encode()).hexdigest()
        x = int(h[:8], 16) / 0xFFFFFFFF
        if x < rate:
            out.append(c)
    return out


def deterministic_cold_audit(candidates: Iterable[AssertionCandidate], units: Iterable[SourceUnit], rate: float = 0.1) -> dict:
    units_by_id = {u.source_unit_id: u for u in units}
    sample = deterministic_sample(candidates, rate)
    findings = []
    for c in sample:
        u = units_by_id.get(c.source_unit_id)
        flags = []
        if not u:
            flags.append("UNKNOWN_SOURCE_UNIT")
        elif c.evidence not in u.content:
            flags.append("EVIDENCE_NOT_EXACT_SOURCE")
        if c.canonical_state != "NON_CANONICAL":
            flags.append("ILLEGAL_CANONICAL_STATE")
        if flags:
            findings.append({"candidate_id": c.candidate_id, "flags": flags})
    return {
        "audit_type": "DETERMINISTIC_COLD_AUDIT_MECHANICS",
        "semantic_independent_model_used": False,
        "sampling_rate": rate,
        "sample_count": len(sample),
        "finding_count": len(findings),
        "findings": findings,
        "status": "PASS" if not findings else "FAIL_REVIEW_REQUIRED",
        "claim_boundary": "This proves cold-audit selection/integrity mechanics only, not independent semantic model review.",
    }
