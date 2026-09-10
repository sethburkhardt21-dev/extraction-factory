from __future__ import annotations
from collections import defaultdict
from typing import Dict, Iterable, List
from .models import EvidenceFamily, SpecialistReceipt

HARD_P0 = {
    "SOURCE_SHA_MISMATCH", "EVIDENCE_HASH_MISMATCH", "LEDGER_INTEGRITY_FAILURE",
    "BUILD_INTEGRITY_FAILURE", "AUTHORITY_BOUNDARY_VIOLATION", "SOURCE_RISK_METADATA_CONFLICT",
}

HARD_W3_CODES = {
    "UNBOUND_NUMERIC", "TABLE_BINDING_REQUIRES_SEMANTIC_OR_VISUAL_REVIEW",
    "IMAGE_AVAILABLE_NOT_MODEL_REVIEWED", "CROSS_PAGE_SEMANTIC_REVIEW_REQUIRED",
    "DIRECTION_CUE_LOST", "QUALIFIER_NOT_PRESERVED", "W3_TIER_B_REVIEW_REQUIRED",
}


def _flag_code(flag: str) -> str:
    """Extract the semantic failure code from legacy serialized specialist flags.

    Existing receipts use both `CODE:detail` and `candidate:cue:CODE`. Routing must
    reason over the failure code, never string prefix position.
    """
    parts = str(flag).split(":")
    for code in HARD_W3_CODES | HARD_P0:
        if code in parts:
            return code
    if parts and parts[0] == "UNBOUND_NUMERIC":
        return "UNBOUND_NUMERIC"
    return parts[-1] if parts else str(flag)


def _source_risk_codes(family: EvidenceFamily) -> set[str]:
    """Convert governed candidate-stamped source risk into routing authority.

    Missing metadata is tolerated for legacy fixture/test candidates, but a live
    family explicitly stamped W3 can never be locally closed. Conflicting risk
    stamps inside one exact-evidence family are an integrity failure.
    """
    metadata = family.metadata if isinstance(family.metadata, dict) else {}
    work_class = metadata.get("source_risk_work_class")
    source_class = metadata.get("source_risk_source_class")
    if work_class == "CONFLICT" or source_class == "CONFLICT":
        return {"SOURCE_RISK_METADATA_CONFLICT"}
    if work_class == "W3":
        return {"W3_TIER_B_REVIEW_REQUIRED"}
    return set()


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
        flag_codes = {_flag_code(flag) for flag in flags} | _source_risk_codes(f)
        if "W3_TIER_B_REVIEW_REQUIRED" in flag_codes:
            flags.append("W3_TIER_B_REVIEW_REQUIRED")
        if flag_codes & HARD_W3_CODES:
            priority = "P1"
            action = "SPECIALIST_REVIEW_REQUIRED"
            reason = "hard W3 semantic binding trigger"
        if flag_codes & HARD_P0:
            priority = "P0"
            action = "FAIL_BLOCKING"
            reason = "authority/integrity hard stop"
        if "UNSUPPORTED" in outcomes and action != "FAIL_BLOCKING":
            priority = "P1"
            action = "FRONTIER_OR_HUMAN_ADJUDICATION"
            reason = "unsupported candidate family"
        metadata = f.metadata if isinstance(f.metadata, dict) else {}
        routes.append({
            "family_id": f.family_id,
            "priority": priority,
            "action": action,
            "reason": reason,
            "unresolved_flags": sorted(set(flags)),
            "unresolved_codes": sorted(flag_codes),
            "source_risk_work_class": metadata.get("source_risk_work_class"),
            "source_risk_source_class": metadata.get("source_risk_source_class"),
            "experimental_soft_thresholds_used": False,
        })
    return routes
