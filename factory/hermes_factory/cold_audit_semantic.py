"""Independent semantic cold audit over sampled union candidates.

The auditor is a SemanticProvider whose request role is COLD_AUDIT. Sampling is
deterministic but risk-stratified so scarce audit calls preferentially cover
tables/figures, numeric claims, and uncertainty-bearing candidates before the
remaining hash-selected population. Independence remains mandatory and is
measured by the protected registry independence group, not merely by a display
or underlying-family label. Family-only arguments remain as a backward-
compatible fallback for fixture/unit-test callers.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List

from .cold_audit import deterministic_sample
from .hashing import sha256_json, sha256_text
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


def _risk_stratified_sample(candidates: List[AssertionCandidate], units_by_id: Dict[str, SourceUnit],
                            rate: float, max_sample: int) -> tuple[List[AssertionCandidate], int]:
    """Keep deterministic sample volume while preferentially auditing high-risk strata."""
    baseline = deterministic_sample(candidates, rate, seed=SEMANTIC_SEED)
    target = min(max_sample, max(len(baseline), 1 if candidates else 0))
    baseline_ids = {c.candidate_id for c in baseline}

    def priority(c: AssertionCandidate):
        unit = units_by_id.get(c.source_unit_id)
        rep = str(getattr(unit, "content_representation", "") or "").upper()
        table_visual = rep in {"TABLE", "FIGURE"}
        numeric = bool(c.numeric_values)
        uncertainty = bool(c.uncertainty_flags)
        tie = sha256_text(SEMANTIC_SEED + "|" + c.candidate_id)
        return (0 if table_visual else 1, 0 if numeric else 1, 0 if uncertainty else 1,
                0 if c.candidate_id in baseline_ids else 1, tie)

    ordered = sorted(candidates, key=priority)
    return ordered[:target], len(baseline)


def run_semantic_cold_audit(
    provider: SemanticProvider,
    candidates: Iterable[AssertionCandidate],
    units: Iterable[SourceUnit],
    *,
    rate: float,
    run_id: str,
    primary_family: str,
    blind_family: str,
    primary_independence_group: str | None = None,
    blind_independence_group: str | None = None,
    auditor_independence_group: str | None = None,
    max_sample: int = 40,
    concurrency: int = 1,
) -> Dict[str, Any]:
    units_by_id = {u.source_unit_id: u for u in units}
    candidate_list = list(candidates)
    sample, baseline_count = _risk_stratified_sample(candidate_list, units_by_id, rate, max_sample)
    identity = provider.identity()
    auditor_family = identity.underlying_family
    primary_group = str(primary_independence_group or primary_family or "")
    blind_group = str(blind_independence_group or blind_family or "")
    auditor_group = str(auditor_independence_group or auditor_family or "")
    independent = (
        auditor_group not in ("", "UNCONFIGURED")
        and primary_group not in ("", "UNCONFIGURED")
        and blind_group not in ("", "UNCONFIGURED")
        and auditor_group != primary_group
        and auditor_group != blind_group
    )

    def audit_one(candidate: AssertionCandidate) -> Dict[str, Any]:
        unit = units_by_id.get(candidate.source_unit_id)
        record: Dict[str, Any] = {
            "candidate_id": candidate.candidate_id,
            "source_unit_id": candidate.source_unit_id,
            "origin_pass": candidate.origin_pass,
            "risk_strata": {
                "representation": str(getattr(unit, "content_representation", "") or "") if unit else None,
                "numeric": bool(candidate.numeric_values),
                "uncertainty": bool(candidate.uncertainty_flags),
            },
        }
        if unit is None:
            record["error"] = "unknown_source_unit"
            return record
        request = build_audit_request(candidate, unit, run_id)
        record["request_sha256"] = sha256_json(request)
        try:
            output = provider.execute(request)
            verdict = _normalize_verdict(output)
            record["verdict"] = verdict
            record["output_sha256"] = sha256_json(output)
            if isinstance(output, dict) and output.get("provider_receipt") is not None:
                record["provider_receipt"] = output.get("provider_receipt")
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}:{exc}"[:1000]
        return record

    concurrency = max(1, int(concurrency))
    records_by_id: Dict[str, Dict[str, Any]] = {}
    if concurrency == 1:
        for candidate in sample:
            records_by_id[candidate.candidate_id] = audit_one(candidate)
    else:
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="hermes-cold-audit") as pool:
            future_map = {pool.submit(audit_one, c): c.candidate_id for c in sample}
            for fut in as_completed(future_map):
                records_by_id[future_map[fut]] = fut.result()
    audited = [records_by_id[c.candidate_id] for c in sample]
    errors = [r for r in audited if r.get("error")]
    disagreements = [r for r in audited if not r.get("error") and not (r.get("verdict") or {}).get("supported", False)]

    if not independent:
        status = "FAIL_INDEPENDENCE"
    elif errors or disagreements or not audited:
        status = "FAIL_REVIEW_REQUIRED"
    else:
        status = "PASS"
    return {
        "audit_type": "INDEPENDENT_SEMANTIC_COLD_AUDIT",
        "semantic_independent_model_used": True,
        "auditor_identity": identity.to_dict(),
        "auditor_independent_family": independent,
        "auditor_independent_group": independent,
        "auditor_independence_group": auditor_group,
        "primary_family": primary_family,
        "blind_family": blind_family,
        "primary_independence_group": primary_group,
        "blind_independence_group": blind_group,
        "sampling_rate": rate,
        "sampling_seed": SEMANTIC_SEED,
        "sampling_strategy": "DETERMINISTIC_RISK_STRATIFIED_TABLE_VISUAL_NUMERIC_UNCERTAINTY_FIRST",
        "baseline_hash_sample_count": baseline_count,
        "sample_truncated_to": max_sample if len(candidate_list) > max_sample else None,
        "sample_count": len(sample),
        "audit_concurrency": concurrency,
        "audited_count": len(audited),
        "disagreement_count": len(disagreements),
        "error_count": len(errors),
        "disagreements": disagreements,
        "errors": errors,
        "audited": audited,
        "status": status,
        "claim_boundary": (
            "A PASS here means the deterministic risk-stratified sample survived independent same-source "
            "skeptical review by a different protected-registry independence group. It is not a proof of "
            "full-corpus correctness and never promotes any candidate to canonical."
        ),
    }
