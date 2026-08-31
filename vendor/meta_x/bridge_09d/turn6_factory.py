"""Turn-6 audit-preparation plane: semantic evidence -> candidates -> read-only 09D compare."""
from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping

from .identity_resolution import resolve_assertion_mentions
from .comparator_09d import compare_ready_candidates

TURN6_FACTORY_SCHEMA_VERSION = "frontier-turn6-audit-prep-1.0"


def run_turn6_audit_prep(*, primary_assertions: Iterable[Mapping[str, Any]], semantic_factory_result: Mapping[str, Any],
                         snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    assertions = list(primary_assertions)
    if semantic_factory_result.get("primary_assertions_mutated") is not False:
        raise ValueError("semantic factory must preserve primary assertions")
    for key in ("automatic_repair_allowed", "automatic_selection_allowed", "candidate_resolution_performed", "09d_comparison_performed", "canonical_authority", "generation_eligible", "public_eligible", "mass_extraction_authorized"):
        if semantic_factory_result.get(key) is not False:
            raise ValueError(f"semantic factory authority invariant failed: {key}")
    verification_events = list(((semantic_factory_result.get("verification") or {}).get("verification_events")) or [])
    identity = resolve_assertion_mentions(assertions=assertions, verification_events=verification_events,
                                          origin_package_id=f"FRONTIER:{semantic_factory_result.get('semantic_run_id')}")
    comparison = compare_ready_candidates(assertions=assertions, verification_events=verification_events,
                                          candidate_records=identity["candidate_records"], snapshot=snapshot)
    return {
        "turn6_factory_schema_version": TURN6_FACTORY_SCHEMA_VERSION,
        "status": "PASS",
        "identity_resolution": identity,
        "09d_comparison": comparison,
        "candidate_resolution_performed": True,
        "candidate_to_canonical_assignment_performed": False,
        "09d_comparison_performed": True,
        "09d_mutation_performed": False,
        "automatic_match_allowed": False,
        "automatic_merge_allowed": False,
        "automatic_promotion_allowed": False,
        "automatic_selection_allowed": False,
        "canonical_authority": False,
        "generation_eligible": False,
        "public_eligible": False,
        "mass_extraction_authorized": False,
    }
