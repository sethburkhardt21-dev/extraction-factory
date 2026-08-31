"""Independent semantic cold audit over sampled union candidates.

This closes the gap the advanced pack left explicit: deterministic cold-audit
mechanics existed, but no real independent semantic auditor could be wired.
The auditor is any SemanticProvider whose request role is COLD_AUDIT and whose
response carries a {"verdict": {...}} object. The audit is deliberately
skeptical: a candidate counts as supported only when the auditor affirmatively
says so; parse failures and provider errors are recorded as findings, never
silently dropped.

Independence is measured, not assumed: the auditor's underlying model family
must differ from BOTH the primary and blind families for the audit to count
as independent. A same-family audit is still recorded — as reduced
independence — and cannot produce a PASS.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .cold_audit import deterministic_sample
from .hashing import sha256_json
from .models import AssertionCandidate, SourceUnit
from .providers.base import SemanticProvider

SEMANTIC_SEED = "HERMES-COLD-AUDIT-SEMANTIC-v1"

COLD_AUDIT_INSTRUCTIONS = (
    "You are an independent skeptical auditor. You receive one SOURCE unit and one "
    "candidate assertion (proposition + evidence) extracted from it by other models. "
    "Judge ONLY from the supplied source content. Answer: (1) does the evidence span, "
    "read in its source context, actually support the proposition; (2) were negation, "
    "qualifier words, numeric values/units, and relationship direction preserved from "
    "evidence to proposition; (3) is the proposition atomic and free of unsupported "
    "additions. If you are not affirmatively convinced on all three, mark it unsupported "
    "and say why. Reply with ONLY one JSON object: "
    '{"verdict": {"supported": true|false, "flags": [str], "rationale": str}}'
)


def build_audit_request(candidate: AssertionCandidate, unit: SourceUnit, run_id: str) -> Dict[str, Any]:
    return {
        "request_schema_version": "hermes-worker-request-1.1",
        "task_role": "COLD_AUDIT",
        "work_class": "AUDIT",
        "source_class": "AUDIT",
        "capsule_id": candidate.originating_capsule_id or "COLD-AUDIT",
        "run_id": run_id,
        "source_unit": unit.to_dict(),
        "audit_target": {
            "candidate_id": candidate.candidate_id,
            "proposition": candidate.proposition,
            "evidence": candidate.evidence,
            "polarity": candidate.polarity,
            "certainty": candidate.certainty,
            "origin_pass": candidate.origin_pass,
        },
        "task_instructions": COLD_AUDIT_INSTRUCTIONS,
        "output_schema": {"type": "object", "required": ["verdict"]},
        "provider_constraints": {"canonicalization_allowed": False},
    }


def _normalize_verdict(output: Any) -> Dict[str, Any]:
    if not isinstance(output, dict):
        raise ValueError("audit_output_not_object")
    verdict = output.get("verdict")
    if not isinstance(verdict, dict) or not isinstance(verdict.get("supported"), bool):
        raise ValueError("audit_output_missing_boolean_supported_verdict")
    flags = verdict.get("flags")
    return {
        "supported": verdict["supported"],
        "flags": [str(x) for x in flags] if isinstance(flags, list) else [],
        "rationale": str(verdict.get("rationale") or "")[:2000],
    }


def run_semantic_cold_audit(
    provider: SemanticProvider,
    candidates: Iterable[AssertionCandidate],
    units: Iterable[SourceUnit],
    *,
    rate: float,
    run_id: str,
    primary_family: str,
    blind_family: str,
    max_sample: int = 40,
) -> Dict[str, Any]:
    units_by_id = {u.source_unit_id: u for u in units}
    sample = deterministic_sample(candidates, rate, seed=SEMANTIC_SEED)
    truncated = len(sample) > max_sample
    sample = sample[:max_sample]
    identity = provider.identity()
    auditor_family = identity.underlying_family
    independent = (
        auditor_family not in ("", "UNCONFIGURED")
        and auditor_family != primary_family
        and auditor_family != blind_family
    )
    audited: List[Dict[str, Any]] = []
    disagreements: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for candidate in sample:
        unit = units_by_id.get(candidate.source_unit_id)
        if unit is None:
            errors.append({"candidate_id": candidate.candidate_id, "error": "unknown_source_unit"})
            continue
        request = build_audit_request(candidate, unit, run_id)
        record: Dict[str, Any] = {
            "candidate_id": candidate.candidate_id,
            "source_unit_id": candidate.source_unit_id,
            "origin_pass": candidate.origin_pass,
            "request_sha256": sha256_json(request),
        }
        try:
            output = provider.execute(request)
            verdict = _normalize_verdict(output)
            record["verdict"] = verdict
            record["output_sha256"] = sha256_json(output)
            if not verdict["supported"]:
                disagreements.append(record)
        except Exception as exc:  # noqa: BLE001 — audit failures are findings, not crashes
            record["error"] = f"{type(exc).__name__}:{exc}"[:1000]
            errors.append(record)
        audited.append(record)
    if not independent:
        status = "FAIL_INDEPENDENCE"
    elif errors:
        status = "FAIL_REVIEW_REQUIRED"
    elif disagreements:
        status = "FAIL_REVIEW_REQUIRED"
    elif not audited:
        status = "FAIL_REVIEW_REQUIRED"
    else:
        status = "PASS"
    return {
        "audit_type": "INDEPENDENT_SEMANTIC_COLD_AUDIT",
        "semantic_independent_model_used": True,
        "auditor_identity": identity.to_dict(),
        "auditor_independent_family": independent,
        "primary_family": primary_family,
        "blind_family": blind_family,
        "sampling_rate": rate,
        "sampling_seed": SEMANTIC_SEED,
        "sample_truncated_to": max_sample if truncated else None,
        "sample_count": len(sample),
        "audited_count": len(audited),
        "disagreement_count": len(disagreements),
        "error_count": len(errors),
        "disagreements": disagreements,
        "errors": errors,
        "audited": audited,
        "status": status,
        "claim_boundary": (
            "A PASS here means the sampled candidates survived independent same-source "
            "skeptical review by a different model family. It is not a proof of full-corpus "
            "correctness and never promotes any candidate to canonical."
        ),
    }
