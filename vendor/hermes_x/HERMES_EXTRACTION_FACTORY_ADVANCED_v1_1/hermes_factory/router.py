from __future__ import annotations
from collections import defaultdict
from typing import Dict, Iterable, List
from .models import EvidenceFamily, SpecialistReceipt

HARD_P0 = {
    "SOURCE_SHA_MISMATCH", "EVIDENCE_HASH_MISMATCH", "LEDGER_INTEGRITY_FAILURE",
    "BUILD_INTEGRITY_FAILURE", "AUTHORITY_BOUNDARY_VIOLATION",
}

HARD_W3_PREFIXES = (
    "UNBOUND_NUMERIC", "TABLE_BINDING", "IMAGE_AVAILABLE", "CROSS_PAGE",
    "DIRECTION_CUE_LOST", "QUALIFIER_NOT_PRESERVED",
)


def route_families(families: Iterable[EvidenceFamily], receipts: Iterable[SpecialistReceipt]) -> List[Dict]:
    by_family: Dict[str, List[SpecialistReceipt]] = defaultdict(list)
    for r in receipts:
        by_family[r.family_id].append(r)
    routes = []
    for f in families:
        rs = by_family.get(f.family_id, [])
        flags = [flag for r in rs for flag in r.unresolved_flags]
        outcomes = [r.outcome for r in rs]
        priority = "P2"
        action = "LOCAL_PRECISION_COMPLETE"
        reason = "deterministic checks supported or no higher-risk trigger"
        if any(any(flag.startswith(prefix) for prefix in HARD_W3_PREFIXES) for flag in flags):
            priority = "P1"
            action = "SPECIALIST_REVIEW_REQUIRED"
            reason = "hard W3 semantic binding trigger"
        if any(flag in HARD_P0 for flag in flags):
            priority = "P0"
            action = "FAIL_BLOCKING"
            reason = "authority/integrity hard stop"
        if "UNSUPPORTED" in outcomes:
            priority = "P1"
            action = "FRONTIER_OR_HUMAN_ADJUDICATION"
            reason = "unsupported candidate family"
        routes.append({
            "family_id": f.family_id,
            "priority": priority,
            "action": action,
            "reason": reason,
            "unresolved_flags": sorted(set(flags)),
            "experimental_soft_thresholds_used": False,
        })
    return routes
