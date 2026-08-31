"""Executable semantic-control plane over immutable extraction evidence.

The factory composes independent verification, optional blind recall, deterministic
reconciliation, and review routing. It is deliberately not an authority plane.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping, Optional

from .assertion_engine import EngineConfig
from .blind_recall import RecallProposalProvider, run_blind_recall, reconcile_primary_recall
from .semantic_router import route_semantic_review
from .verifier import ReviewerProvider, VerifierConfig, verify_assertions

SEMANTIC_FACTORY_SCHEMA_VERSION = "frontier-semantic-factory-1.0"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _run_id(payload: Mapping[str, Any]) -> str:
    return "SEMRUN:" + hashlib.sha256(_canonical(payload)).hexdigest()[:32]


def run_semantic_factory(
    *,
    primary_assertions: Iterable[Mapping[str, Any]],
    source_units: Iterable[Mapping[str, Any]],
    verifier_config: VerifierConfig,
    reviewer: Optional[ReviewerProvider] = None,
    recall_provider: Optional[RecallProposalProvider] = None,
    recall_config: Optional[EngineConfig] = None,
) -> Dict[str, Any]:
    primary_assertions = list(primary_assertions)
    source_units = list(source_units)

    verification = verify_assertions(primary_assertions, source_units, config=verifier_config, reviewer=reviewer)

    recall = None
    reconciliation = None
    recall_assertions = []
    if recall_provider is not None:
        if recall_config is None:
            raise ValueError("recall_config required when recall_provider is supplied")
        if recall_config.code_manifest_sha256 != verifier_config.code_manifest_sha256:
            raise ValueError("primary verifier and recall lane must bind the same estate code hash")
        recall = run_blind_recall(source_units, provider=recall_provider, config=recall_config)
        recall_assertions = list(recall.get("assertions") or [])
        reconciliation = reconcile_primary_recall(primary_assertions, recall_assertions)
        recall = {**recall, "reconciliation": reconciliation}

    routing = route_semantic_review(
        verification_events=verification.get("verification_events") or [],
        recall_reconciliation=reconciliation,
        recall_assertions=recall_assertions,
    )

    identity = {
        "code_manifest_sha256": verifier_config.code_manifest_sha256,
        "primary_assertion_interpretation_ids": sorted(str(a.get("interpretation_id")) for a in primary_assertions),
        "verification_ids": sorted(str(e.get("verification_id")) for e in verification.get("verification_events") or []),
        "recall_interpretation_ids": sorted(str(a.get("interpretation_id")) for a in recall_assertions),
        "review_case_ids": sorted(str(c.get("review_case_id")) for c in routing.get("review_cases") or []),
    }
    semantic_run_id = _run_id(identity)

    verifier_events = list(verification.get("verification_events") or [])
    metrics = {
        "primary_assertions": len(primary_assertions),
        "verification_events": len(verifier_events),
        "semantically_ready_assertions": sum(1 for e in verifier_events if e.get("downstream_semantic_ready") is True),
        "entailed_but_not_ready": sum(1 for e in verifier_events if e.get("verdict") == "ENTAILED" and e.get("downstream_semantic_ready") is not True),
        "not_entailed": sum(1 for e in verifier_events if e.get("verdict") == "NOT_ENTAILED"),
        "ambiguous_or_partial": sum(1 for e in verifier_events if e.get("verdict") in {"AMBIGUOUS", "PARTIAL"}),
        "recall_lane_run": recall is not None,
        "recall_assertions": len(recall_assertions),
        "recall_only_candidates": int(((reconciliation or {}).get("counts") or {}).get("RECALL_ONLY_CANDIDATE", 0)),
        "same_evidence_semantic_disagreements": int(((reconciliation or {}).get("counts") or {}).get("SAME_EVIDENCE_SEMANTIC_DISAGREEMENT", 0)),
        "open_review_cases": int((routing.get("metrics") or {}).get("open_review_cases", 0)),
        "frontier_adjudication_cases": sum(1 for c in routing.get("review_cases") or [] if "FRONTIER_ADJUDICATION" in c.get("required_lanes", [])),
    }

    return {
        "semantic_factory_schema_version": SEMANTIC_FACTORY_SCHEMA_VERSION,
        "semantic_run_id": semantic_run_id,
        "status": "PASS" if verification.get("status") == "PASS" and (recall is None or recall.get("status") == "PASS") else "PASS_WITH_QUARANTINE",
        "code_manifest_sha256": verifier_config.code_manifest_sha256,
        "verification": verification,
        "blind_recall": recall,
        "semantic_routing": routing,
        "metrics": metrics,
        "primary_assertions_mutated": False,
        "recall_assertions_are_unverified": True if recall is not None else None,
        "automatic_repair_allowed": False,
        "automatic_selection_allowed": False,
        "candidate_resolution_performed": False,
        "09d_comparison_performed": False,
        "canonical_authority": False,
        "generation_eligible": False,
        "public_eligible": False,
        "mass_extraction_authorized": False,
    }
