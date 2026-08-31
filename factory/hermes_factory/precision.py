from __future__ import annotations
from typing import Dict, Iterable, List
from .hashing import sha256_text
from .models import AssertionCandidate, EvidenceFamily, SourceUnit


def precision_review(candidates: Iterable[AssertionCandidate], units: Iterable[SourceUnit]) -> List[Dict]:
    units_by_id = {u.source_unit_id: u for u in units}
    results = []
    for c in candidates:
        flags = []
        unit = units_by_id.get(c.source_unit_id)
        if not unit:
            flags.append("UNKNOWN_SOURCE_UNIT")
        else:
            if c.evidence not in unit.content:
                flags.append("EVIDENCE_NOT_SOURCE_SUBSTRING")
            if sha256_text(c.evidence) != c.evidence_sha256:
                flags.append("EVIDENCE_HASH_MISMATCH")
            if c.source_sha256 != unit.source_sha256:
                flags.append("SOURCE_SHA_MISMATCH")
        flags.extend(c.validate_invariants())
        results.append({
            "candidate_id": c.candidate_id,
            "result": "PASS" if not flags else "FAIL_BLOCKING",
            "flags": flags,
            "action": "KEEP_NONCANONICAL" if not flags else "REJECT_OR_REPAIR",
        })
    return results
