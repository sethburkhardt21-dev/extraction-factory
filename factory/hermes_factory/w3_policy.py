from __future__ import annotations

from typing import Iterable

from .models import EvidenceFamily, SourceUnit
from .risk import classify_source_unit

W3_TIER_B_FLAG = "W3_TIER_B_REVIEW_REQUIRED"


def w3_unit_ids(units: Iterable[SourceUnit]) -> set[str]:
    """Return source-unit IDs whose governed risk classification requires W3 review."""
    return {
        unit.source_unit_id
        for unit in units
        if classify_source_unit(unit).get("work_class") == "W3"
    }


def w3_family_ids(families: Iterable[EvidenceFamily], units: Iterable[SourceUnit]) -> set[str]:
    """Every evidence family from a W3 source is review-bound, even absent narrower flags."""
    ids = w3_unit_ids(units)
    return {family.family_id for family in families if family.source_unit_id in ids}


def apply_w3_tier_b_routing(routes: list[dict], families: Iterable[EvidenceFamily], units: Iterable[SourceUnit]) -> list[dict]:
    """Fail closed by forcing W3 evidence families into the bounded Tier-B review queue.

    This does not mutate assertion candidates or claim that Tier-B review occurred.
    It only prevents a W3 family from being marked LOCAL_PRECISION_COMPLETE merely
    because narrower deterministic checks did not happen to emit a W3-specific flag.
    """
    required = w3_family_ids(families, units)
    out: list[dict] = []
    for route in routes:
        row = dict(route)
        if row.get("family_id") in required:
            flags = sorted(set(list(row.get("unresolved_flags") or []) + [W3_TIER_B_FLAG]))
            row["unresolved_flags"] = flags
            row["action"] = "SPECIALIST_REVIEW_REQUIRED"
            row["reason"] = "Governed W3 source-risk classification requires Tier-B review before closure."
        out.append(row)
    return out
