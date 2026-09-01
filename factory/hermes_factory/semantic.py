from __future__ import annotations

from typing import Any, Dict, List

from .blindness import build_blind_worker_request
from .hashing import sha256_json, sha256_text
from .identity import stable_candidate_identities
from .models import AssertionCandidate, SourceUnit, WorkerIdentity
from .providers.base import SemanticProvider


OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["assertions"],
    "assertion_required": ["proposition", "evidence"],
    "assertion_optional": [
        "subject",
        "predicate",
        "object_value",
        "numeric_values",
        "qualifiers",
        "polarity",
        "certainty",
        "conditionality",
        "temporality",
        "comparison",
        "relationship_direction",
        "uncertainty_flags",
        "table_binding_state",
        "visual_binding_state",
    ],
    "structured_field_policy": (
        "Populate subject/predicate/object and typed qualifiers only when explicitly supported by the source. "
        "Use source-faithful labels, not invented canonical IDs or 09D predicate codes."
    ),
    "authority": "candidate_only_noncanonical",
}

PRIMARY_INSTRUCTIONS = (
    "Extract atomic source-grounded propositions only. Preserve negation, qualifiers, uncertainty, "
    "conditionality, directionality, units and ranges. Evidence must be exact source text. Do not "
    "infer unsupported facts. Emit uncertainty instead of guessing. When the source makes the structure "
    "explicit, also populate source-faithful subject, predicate and object_value fields so downstream "
    "identity/conflict review can compare like with like. Never invent canonical entity IDs, predicate "
    "codes, package IDs or promotion decisions. All output is noncanonical."
)

BLIND_INSTRUCTIONS = (
    "Independently enumerate atomic source-grounded propositions from the supplied source only. "
    "You have no access to peer outputs. Preserve exact evidence, negation, qualifiers, uncertainty, "
    "conditionality, directionality, units and ranges. When explicit in the source, populate source-faithful "
    "subject, predicate and object_value fields. Never invent canonical IDs, predicate codes or downstream "
    "09D decisions. Do not infer unsupported facts."
)


def build_primary_request(unit: SourceUnit, capsule_id: str, run_id: str, source_class: str = "S1") -> Dict[str, Any]:
    return {
        "request_schema_version": "hermes-worker-request-1.2",
        "task_role": "PRIMARY",
        "work_class": "W2",
        "source_class": source_class,
        "capsule_id": capsule_id,
        "run_id": run_id,
        "source_unit": unit.to_dict(),
        "boundary_context": {},
        "task_instructions": PRIMARY_INSTRUCTIONS,
        "output_schema": OUTPUT_SCHEMA,
        "provider_constraints": {
            "canonicalization_allowed": False,
            "canonical_id_assignment_allowed": False,
            "09d_write_allowed": False,
        },
    }


def build_blind_request(unit: SourceUnit, capsule_id: str, run_id: str, source_class: str = "S1", **potentially_contaminated: Any) -> Dict[str, Any]:
    raw = {
        "request_schema_version": "hermes-worker-request-1.2",
        "task_role": "BLIND_RECALL",
        "work_class": "W2",
        "source_class": source_class,
        "capsule_id": capsule_id,
        "run_id": run_id,
        "source_unit": unit.to_dict(),
        "boundary_context": {},
        "task_instructions": BLIND_INSTRUCTIONS,
        "output_schema": OUTPUT_SCHEMA,
        "provider_constraints": {
            "canonicalization_allowed": False,
            "canonical_id_assignment_allowed": False,
            "09d_write_allowed": False,
        },
    }
    raw.update(potentially_contaminated)
    return build_blind_worker_request(raw)


def _candidate_id(run_id: str, unit_id: str, role: str, proposition: str, evidence: str, ordinal: int) -> str:
    seed = f"{run_id}|{unit_id}|{role}|{ordinal}|{proposition}|{evidence}"
    return "CAND-" + sha256_text(seed)[:24]


def normalize_provider_output(
    output: Dict[str, Any],
    unit: SourceUnit,
    capsule_id: str,
    run_id: str,
    worker: WorkerIdentity,
    origin_pass: str,
    parent_artifact_sha256: str = "GENESIS",
) -> List[AssertionCandidate]:
    if not isinstance(output, dict) or not isinstance(output.get("assertions"), list):
        raise ValueError("provider_output_missing_assertions")
    candidates: List[AssertionCandidate] = []
    for ordinal, raw in enumerate(output["assertions"]):
        if not isinstance(raw, dict):
            raise ValueError("provider_assertion_not_object")
        proposition = str(raw.get("proposition") or "").strip()
        evidence = str(raw.get("evidence") or "").strip()
        if not proposition or not evidence:
            raise ValueError("provider_assertion_missing_proposition_or_evidence")
        if evidence not in unit.content:
            raise ValueError(f"evidence_not_exact_source_substring:{unit.source_unit_id}:{ordinal}")

        evidence_sha = sha256_text(evidence)
        identity_payload = {
            "source_unit_id": unit.source_unit_id,
            "source_id": unit.source_id,
            "source_version_id": unit.source_version_id,
            "source_sha256": unit.source_sha256,
            "locator": unit.locator,
            "evidence_sha256": evidence_sha,
            "proposition": proposition,
            "subject": raw.get("subject"),
            "predicate": raw.get("predicate"),
            "object_value": raw.get("object_value"),
            "numeric_values": list(raw.get("numeric_values") or []),
            "qualifiers": list(raw.get("qualifiers") or []),
            "polarity": str(raw.get("polarity") or "AFFIRMATIVE"),
            "certainty": str(raw.get("certainty") or "ASSERTED"),
            "conditionality": raw.get("conditionality"),
            "temporality": raw.get("temporality"),
            "comparison": raw.get("comparison"),
            "relationship_direction": raw.get("relationship_direction"),
        }
        witness_sha, claim_sha = stable_candidate_identities(identity_payload)

        candidate = AssertionCandidate(
            candidate_id=_candidate_id(run_id, unit.source_unit_id, origin_pass, proposition, evidence, ordinal),
            source_unit_id=unit.source_unit_id,
            source_id=unit.source_id,
            source_version_id=unit.source_version_id,
            source_sha256=unit.source_sha256,
            locator=unit.locator,
            evidence=evidence,
            evidence_sha256=evidence_sha,
            proposition=proposition,
            subject=raw.get("subject"),
            predicate=raw.get("predicate"),
            object_value=raw.get("object_value"),
            numeric_values=list(raw.get("numeric_values") or []),
            qualifiers=list(raw.get("qualifiers") or []),
            polarity=str(raw.get("polarity") or "AFFIRMATIVE"),
            certainty=str(raw.get("certainty") or "ASSERTED"),
            conditionality=raw.get("conditionality"),
            temporality=raw.get("temporality"),
            comparison=raw.get("comparison"),
            relationship_direction=raw.get("relationship_direction"),
            table_binding_state=str(raw.get("table_binding_state") or ("REQUIRES_REVIEW" if unit.content_representation == "TABLE" else "NOT_APPLICABLE")),
            visual_binding_state=str(raw.get("visual_binding_state") or ("CAPTION_ONLY_OR_UNREVIEWED" if unit.content_representation == "FIGURE" else "NOT_APPLICABLE")),
            cross_page_state="CROSS_PAGE" if len(unit.locator.get("pdf_pages", [])) > 1 else "LOCAL",
            originating_capsule_id=capsule_id,
            originating_run_id=run_id,
            parent_artifact_sha256=parent_artifact_sha256,
            worker_identity=worker.to_dict(),
            origin_pass=origin_pass,
            uncertainty_flags=list(raw.get("uncertainty_flags") or []),
            stable_witness_sha256=witness_sha,
            stable_claim_sha256=claim_sha,
            metadata={
                "provider_output_hash": sha256_json(raw),
                "09d_projection_identity_version": "stable-candidate-identity-1.0",
            },
        )
        errors = candidate.validate_invariants()
        if errors:
            raise ValueError(f"candidate_invariant_failure:{candidate.candidate_id}:{errors}")
        candidates.append(candidate)
    return candidates


def execute_primary(provider: SemanticProvider, unit: SourceUnit, capsule_id: str, run_id: str, source_class: str = "S1") -> tuple[List[AssertionCandidate], Dict[str, Any]]:
    request = build_primary_request(unit, capsule_id, run_id, source_class)
    output = provider.execute(request)
    worker = provider.identity()
    candidates = normalize_provider_output(output, unit, capsule_id, run_id, worker, "PRIMARY")
    receipt = {
        "run_id": run_id,
        "capsule_id": capsule_id,
        "role": "PRIMARY",
        "worker_identity": worker.to_dict(),
        "request_sha256": sha256_json(request),
        "output_sha256": sha256_json(output),
        "empirical_semantic_model": provider.is_empirical_semantic_provider(),
        "candidate_count": len(candidates),
        "provider_receipt": output.get("provider_receipt") if isinstance(output, dict) else None,
    }
    return candidates, receipt


def execute_blind(provider: SemanticProvider, unit: SourceUnit, capsule_id: str, run_id: str, source_class: str = "S1") -> tuple[List[AssertionCandidate], Dict[str, Any]]:
    request = build_blind_request(unit, capsule_id, run_id, source_class)
    output = provider.execute(request)
    worker = provider.identity()
    candidates = normalize_provider_output(output, unit, capsule_id, run_id, worker, "BLIND_RECALL")
    receipt = {
        "run_id": run_id,
        "capsule_id": capsule_id,
        "role": "BLIND_RECALL",
        "worker_identity": worker.to_dict(),
        "request_sha256": sha256_json(request),
        "output_sha256": sha256_json(output),
        "empirical_semantic_model": provider.is_empirical_semantic_provider(),
        "candidate_count": len(candidates),
        "blindness_enforced_by": "POSITIVE_ALLOWLIST",
        "provider_receipt": output.get("provider_receipt") if isinstance(output, dict) else None,
    }
    return candidates, receipt
