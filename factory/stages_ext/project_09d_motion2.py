"""Build a non-writing 09D Motion-2 projection from a completed factory run.

The projection reduces friction for a future 09D-owned ingest lane. It never
inserts rows, selects canonical identities, merges entities, or promotes
assertions. v1.8 binds the exact comparison artifact bytes to the verified 09D
database hash, focused Motion-2 target contract, schema fingerprint, and
cycle-safe authority scope before the canonical CLI can call a handoff ready.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.bridge_09d import (  # noqa: E402
    inventory_schema_readonly,
    motion2_capability_readonly,
    motion2_target_contract_readonly,
)
from hermes_factory.hashing import sha256_file, sha256_text  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts)
    return f"{prefix}-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _required_without_default(columns: list[dict[str, Any]]) -> list[str]:
    return sorted(
        str(c["name"]) for c in columns
        if int(c.get("notnull") or 0) == 1 and c.get("dflt_value") is None and int(c.get("pk") or 0) == 0
    )


def _schema_mapping_plan(carrier_columns: list[dict[str, Any]], locator_columns: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe who may populate observed 09D target columns; never emit SQL."""
    carrier_names = {str(c["name"]) for c in carrier_columns}
    locator_names = {str(c["name"]) for c in locator_columns}

    carrier_mechanical = {
        "value_text": "factory.proposition",
        "ingest_locator_id": "projection.projection_locator_id -> 09D loader-assigned locator id",
    }
    carrier_must_null = {
        "source_resource_id", "parent_assertion_id", "source_locator_id", "raw_cell_id",
        "carried_status", "carried_confidence_basis", "carried_source_era",
    }
    carrier_adjudication = {"subject_entity_id", "predicate_code", "fact_family"}
    carrier_loader_owned = {
        "candidate_id", "intake_package_id", "ingest_state", "created_at", "updated_at",
        "created_by", "build_id", "run_id", "status", "review_state",
    }

    locator_mechanical = {
        "source_id": "factory.source_id",
        "source_version_id": "factory.source_version_id",
        "source_sha256": "factory.source_sha256",
        "content_sha256": "factory.content_sha256",
        "locator_json": "factory.locator (canonical JSON serialization)",
        "unit_type": "factory.unit_type",
        "content_representation": "factory.content_representation",
    }
    locator_loader_owned = {"ingest_locator_id", "created_at", "updated_at", "build_id", "run_id"}

    carrier_required = set(_required_without_default(carrier_columns))
    locator_required = set(_required_without_default(locator_columns))
    carrier_known = set(carrier_mechanical) | carrier_must_null | carrier_adjudication | carrier_loader_owned
    locator_known = set(locator_mechanical) | locator_loader_owned

    return {
        "source_assertion_candidate": {
            "mechanical": {k: v for k, v in carrier_mechanical.items() if k in carrier_names},
            "must_be_null_for_motion2_witness": sorted(carrier_must_null & carrier_names),
            "09d_adjudication_required": sorted(carrier_adjudication & carrier_names),
            "09d_loader_owned": sorted(carrier_loader_owned & carrier_names),
            "observed_unclassified_columns": sorted(carrier_names - carrier_known),
            "required_without_default": sorted(carrier_required),
            "unclassified_required_columns": sorted(carrier_required - carrier_known),
        },
        "ingest_source_locator": {
            "mechanical": {k: v for k, v in locator_mechanical.items() if k in locator_names},
            "09d_loader_owned": sorted(locator_loader_owned & locator_names),
            "observed_unclassified_columns": sorted(locator_names - locator_known),
            "required_without_default": sorted(locator_required),
            "unclassified_required_columns": sorted(locator_required - locator_known),
        },
    }


def _comparison_bundle(run_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    rows = _read_jsonl(run_dir / "09D" / "comparison_09d.jsonl")
    summary = _read_json(run_dir / "09D" / "comparison_09d_summary.json")
    return ({str(r.get("candidate_id")): r for r in rows if r.get("candidate_id")}, summary)


def _authority_binding(
    run_dir: Path,
    comparison_summary: dict[str, Any],
    capability: dict[str, Any],
    target_contract: dict[str, Any],
) -> dict[str, Any]:
    """Bind exact comparison bytes to the target identity claimed by its summary."""
    comparison_path = run_dir / "09D" / "comparison_09d.jsonl"
    summary_path = run_dir / "09D" / "comparison_09d_summary.json"
    measured_db_hash = comparison_summary.get("database_sha256_measured")
    target_match = comparison_summary.get("database_matches_declared_target") is True
    summary_schema = comparison_summary.get("schema_fingerprint_sha256")
    current_schema = capability.get("schema_fingerprint_sha256")
    summary_contract = (comparison_summary.get("motion2_capability") or {}).get("motion2_target_contract_sha256")
    current_contract = target_contract.get("motion2_target_contract_sha256")
    scope = comparison_summary.get("carrier_scope")
    cycle_safe = comparison_summary.get("cycle_safe_authority_comparison") is True
    comparator_version = (comparison_summary.get("comparator_target") or {}).get("comparator_target_version")
    declared_expected_hash = (comparison_summary.get("comparator_target") or {}).get("expected_db_sha256")

    checks = {
        "database_hash_verified": bool(target_match and measured_db_hash and measured_db_hash != "NOT_MEASURED"),
        "measured_hash_matches_declared_target": bool(
            measured_db_hash and declared_expected_hash and measured_db_hash == declared_expected_hash
        ),
        "schema_fingerprint_matches_current_target": bool(summary_schema and summary_schema == current_schema),
        "motion2_target_contract_matches_current_target": bool(summary_contract and summary_contract == current_contract),
        "cycle_safe_motion1_authority_scope": bool(cycle_safe and scope == "MOTION1_AUTHORITY"),
        "comparison_artifacts_present": comparison_path.exists() and summary_path.exists(),
    }
    verified = all(checks.values())
    context = {
        "database_sha256": measured_db_hash,
        "schema_fingerprint_sha256": current_schema,
        "motion2_target_contract_sha256": current_contract,
        "carrier_scope": scope,
        "comparator_target_version": comparator_version,
        "comparison_jsonl_sha256": sha256_file(comparison_path) if comparison_path.exists() else None,
        "comparison_summary_sha256": sha256_file(summary_path) if summary_path.exists() else None,
    }
    return {
        "binding_schema_version": "09d-authority-binding-1.0",
        "verified": verified,
        "checks": checks,
        "authority_context": context,
        "authority_context_id": "09DAUTH-" + _stable_hash(context)[:24],
        "claim_boundary": (
            "This binds comparison artifacts to the verified target identity and cycle-safe scope. "
            "It does not authorize a 09D write, merge, canonicalization, migration, or release."
        ),
    }


def build_projection(
    run_dir: Path,
    database: Path,
    *,
    require_verified_target: bool = False,
) -> dict[str, Any]:
    """Build the projection. Canonical CLI sets require_verified_target=True.

    The default remains False for synthetic/unit-test callers that intentionally
    do not possess the pinned r3 bytes; the returned summary records whether the
    strict authority binding was enforced and verified.
    """
    run_dir = Path(run_dir)
    database = Path(database)
    candidates = _read_jsonl(run_dir / "ASSERTIONS" / "union_candidates.jsonl")
    source_units = _read_jsonl(run_dir / "SOURCE" / "source_units.jsonl")
    comparisons, comparison_summary = _comparison_bundle(run_dir)

    schema = inventory_schema_readonly(database)
    capability = motion2_capability_readonly(database)
    target_contract = motion2_target_contract_readonly(database)
    authority_binding = _authority_binding(run_dir, comparison_summary, capability, target_contract)
    table_schema = schema.get("schema", {})
    carrier_columns = table_schema.get("source_assertion_candidate", [])
    locator_columns = table_schema.get("ingest_source_locator", [])
    mapping_plan = _schema_mapping_plan(carrier_columns, locator_columns)

    comparison_scope = comparison_summary.get("carrier_scope")
    cycle_safe_comparison = comparison_summary.get("cycle_safe_authority_comparison") is True
    target_contract_sha = target_contract.get("motion2_target_contract_sha256")
    authority_context_id = authority_binding.get("authority_context_id")
    strict_target_ok = authority_binding.get("verified") is True
    trusted_comparison = cycle_safe_comparison and (strict_target_ok or not require_verified_target)

    source_by_id = {str(u.get("source_unit_id")): u for u in source_units}
    locator_rows: list[dict[str, Any]] = []
    locator_id_by_unit: dict[str, str] = {}
    projection_errors: list[dict[str, Any]] = []

    if candidates and not comparisons:
        projection_errors.append({"code": "09D_COMPARISON_RECEIPTS_MISSING"})
    elif comparisons and not cycle_safe_comparison:
        projection_errors.append({
            "code": "09D_COMPARISON_NOT_CYCLE_SAFE",
            "carrier_scope": comparison_scope,
            "required_scope": "MOTION1_AUTHORITY",
        })
    if require_verified_target and not strict_target_ok:
        projection_errors.append({
            "code": "09D_COMPARISON_AUTHORITY_BINDING_FAILED",
            "failed_checks": sorted(k for k, v in authority_binding.get("checks", {}).items() if not v),
        })

    for unit in source_units:
        unit_id = str(unit.get("source_unit_id") or "")
        projection_id = _stable_id(
            "09DLOC", str(unit.get("source_sha256") or ""), unit_id,
            json.dumps(unit.get("locator") or {}, sort_keys=True, separators=(",", ":")),
        )
        locator_id_by_unit[unit_id] = projection_id
        locator_rows.append({
            "projection_locator_id": projection_id,
            "source_unit_id": unit_id,
            "source_id": unit.get("source_id"),
            "source_version_id": unit.get("source_version_id"),
            "source_sha256": unit.get("source_sha256"),
            "content_sha256": unit.get("content_sha256"),
            "unit_type": unit.get("unit_type"),
            "content_representation": unit.get("content_representation"),
            "locator": unit.get("locator") or {},
            "09d_motion2_target_contract_sha256": target_contract_sha,
            "09d_authority_context_id": authority_context_id,
            "target_table": "ingest_source_locator",
            "target_columns_observed": sorted(str(c["name"]) for c in locator_columns),
            "direct_insert_allowed": False,
        })

    projected_candidates: list[dict[str, Any]] = []
    state_counts: dict[str, int] = defaultdict(int)
    disposition_counts: dict[str, int] = defaultdict(int)
    single_entity_resolution = 0
    exact_predicate_resolution = 0

    for candidate in candidates:
        cid = str(candidate.get("candidate_id") or "")
        unit_id = str(candidate.get("source_unit_id") or "")
        unit = source_by_id.get(unit_id)
        evidence = str(candidate.get("evidence") or "")
        evidence_ok = bool(unit) and evidence in str(unit.get("content") or "") and sha256_text(evidence) == candidate.get("evidence_sha256")
        if not evidence_ok:
            projection_errors.append({"candidate_id": cid, "code": "EVIDENCE_PROJECTION_INTEGRITY_FAILED"})

        comparison = comparisons.get(cid) or {}
        subject_resolution = comparison.get("subject_resolution") or {}
        resolved_ids = list(subject_resolution.get("resolved_entity_ids") or [])
        subject_ambiguous = bool(subject_resolution.get("ambiguous")) or len(resolved_ids) > 1
        predicate_resolution = comparison.get("predicate_resolution") or {}
        top_matches = list(comparison.get("top_matches") or [])
        compatible_top = [
            m for m in top_matches
            if trusted_comparison
            and m.get("subject_compatible") and m.get("predicate_compatible")
            and m.get("fact_family_compatible", True)
            and m.get("witness_kind") == "MOTION1_SOURCE_WITNESSED"
        ]

        if len(resolved_ids) == 1 and not subject_ambiguous and trusted_comparison:
            single_entity_resolution += 1
        if predicate_resolution.get("mode") in {
            "EXACT_CODE_OR_LABEL", "UNIQUE_FAMILY_PREDICATE_TAIL", "UNIQUE_GLOBAL_PREDICATE_TAIL"
        } and trusted_comparison:
            exact_predicate_resolution += 1

        identity_candidates = []
        seen = set()
        if trusted_comparison:
            for entity_id in resolved_ids:
                key = str(entity_id)
                if key not in seen:
                    seen.add(key)
                    identity_candidates.append({
                        "subject_entity_id": entity_id,
                        "basis": subject_resolution.get("mode"),
                        "ambiguous_source_resolution": subject_ambiguous,
                        "selection_authorized": False,
                    })
        for match in compatible_top:
            entity_id = match.get("subject_entity_id")
            key = str(entity_id)
            if entity_id is not None and key not in seen:
                seen.add(key)
                identity_candidates.append({
                    "subject_entity_id": entity_id,
                    "basis": "MOTION1_COMPARATOR_TOP_MATCH",
                    "score": match.get("score"),
                    "selection_authorized": False,
                })

        predicate_candidates = []
        seen_pred = set()
        for match in compatible_top:
            code = match.get("predicate_code")
            if code and str(code) not in seen_pred:
                seen_pred.add(str(code))
                predicate_candidates.append({
                    "predicate_code": code,
                    "basis": predicate_resolution.get("mode") or "MOTION1_COMPARATOR_TOP_MATCH",
                    "score": match.get("score"),
                    "selection_authorized": False,
                })

        identity_state = (
            "UNIQUE_SUGGESTION" if len(identity_candidates) == 1 and not subject_ambiguous
            else "AMBIGUOUS" if identity_candidates
            else "UNRESOLVED"
        )
        predicate_state = "SUGGESTED" if predicate_candidates else "UNRESOLVED"
        state = comparison.get("state") or "NOT_COMPARED"
        state_counts[state] += 1

        loader_disposition = (
            "READY_FOR_09D_ADJUDICATION"
            if evidence_ok and trusted_comparison and comparison
            else "REVIEW_REQUIRED"
        )
        disposition_counts[loader_disposition] += 1

        projection_id = _stable_id("09DCAND", cid, str(candidate.get("source_sha256") or ""), str(candidate.get("evidence_sha256") or ""))
        projected_candidates.append({
            "projection_candidate_id": projection_id,
            "factory_candidate_id": cid,
            "projection_locator_id": locator_id_by_unit.get(unit_id),
            "source_unit_id": unit_id,
            "source_id": candidate.get("source_id"),
            "source_version_id": candidate.get("source_version_id"),
            "source_sha256": candidate.get("source_sha256"),
            "locator": candidate.get("locator") or {},
            "evidence": evidence,
            "evidence_sha256": candidate.get("evidence_sha256"),
            "evidence_projection_integrity": "PASS" if evidence_ok else "FAIL",
            "proposition": candidate.get("proposition"),
            "subject_text": candidate.get("subject"),
            "predicate_text": candidate.get("predicate"),
            "object_value": candidate.get("object_value"),
            "numeric_values": candidate.get("numeric_values") or [],
            "qualifiers": candidate.get("qualifiers") or [],
            "polarity": candidate.get("polarity"),
            "certainty": candidate.get("certainty"),
            "conditionality": candidate.get("conditionality"),
            "temporality": candidate.get("temporality"),
            "comparison": candidate.get("comparison"),
            "relationship_direction": candidate.get("relationship_direction"),
            "uncertainty_flags": candidate.get("uncertainty_flags") or [],
            "review_state": candidate.get("review_state"),
            "canonical_state": candidate.get("canonical_state"),
            "model_lineage": candidate.get("worker_identity") or {},
            "origin_pass": candidate.get("origin_pass"),
            "09d_comparison_state": state,
            "09d_comparison_confidence": comparison.get("comparison_confidence"),
            "09d_comparison_carrier_scope": comparison_scope,
            "09d_cycle_safe_authority_comparison": cycle_safe_comparison,
            "09d_motion2_target_contract_sha256": target_contract_sha,
            "09d_authority_context_id": authority_context_id,
            "09d_authority_binding_verified": strict_target_ok,
            "subject_identity_resolution_state": identity_state,
            "predicate_identity_resolution_state": predicate_state,
            "subject_identity_candidates": identity_candidates,
            "predicate_identity_candidates": predicate_candidates,
            "loader_disposition": loader_disposition,
            "target_table": "source_assertion_candidate",
            "target_columns_observed": sorted(str(c["name"]) for c in carrier_columns),
            "automatic_identity_merge_allowed": False,
            "automatic_canonicalization_allowed": False,
            "direct_insert_allowed": False,
        })

    required_tables_ok = bool(capability.get("required_tables_present"))
    witness_ok = bool(
        capability.get("motion2_witness_columns_present")
        and capability.get("motion2_witness_constraint_present")
        and capability.get("carrier_partition_valid")
    )
    evidence_ok_all = not any(e.get("code") == "EVIDENCE_PROJECTION_INTEGRITY_FAILED" for e in projection_errors)
    mapping_gaps = (
        mapping_plan["source_assertion_candidate"]["unclassified_required_columns"]
        or mapping_plan["ingest_source_locator"]["unclassified_required_columns"]
    )
    comparison_ok = not candidates or (bool(comparisons) and trusted_comparison)

    if not (required_tables_ok and witness_ok and evidence_ok_all and comparison_ok):
        projection_status = "PROJECTION_REVIEW_REQUIRED"
    elif mapping_gaps:
        projection_status = "SCHEMA_COMPATIBLE_MAPPING_GAPS"
    else:
        projection_status = "SCHEMA_COMPATIBLE_NEEDS_GOVERNED_09D_LOADER"

    summary = {
        "stage": "READ_ONLY_09D_MOTION2_PROJECTION",
        "projection_schema_version": "09d-motion2-projection-1.8",
        "projection_status": projection_status,
        "database": str(database),
        "database_schema_fingerprint_sha256": capability.get("schema_fingerprint_sha256"),
        "motion2_target_contract_sha256": target_contract_sha,
        "authority_context_id": authority_context_id,
        "authority_binding_enforced": require_verified_target,
        "authority_binding_verified": strict_target_ok,
        "motion2_capability": capability,
        "comparison_scope": comparison_scope,
        "cycle_safe_authority_comparison": cycle_safe_comparison,
        "source_unit_count": len(source_units),
        "candidate_count": len(candidates),
        "comparison_state_counts": dict(sorted(state_counts.items())),
        "loader_disposition_counts": dict(sorted(disposition_counts.items())),
        "single_entity_resolution_candidate_count": single_entity_resolution,
        "resolved_predicate_candidate_count": exact_predicate_resolution,
        "projection_error_count": len(projection_errors),
        "projection_errors": projection_errors,
        "target_schema_fit": {
            "source_assertion_candidate_required_without_default": _required_without_default(carrier_columns),
            "ingest_source_locator_required_without_default": _required_without_default(locator_columns),
            "mapping_plan": mapping_plan,
        },
        "governance": {
            "direct_09d_insert_allowed": False,
            "automatic_canonicalization_allowed": False,
            "automatic_identity_merge_allowed": False,
            "automatic_release_allowed": False,
            "automatic_schema_migration_allowed": False,
            "identity_and_predicate_candidates_are_suggestions_only": True,
            "comparison_authority_must_exclude_prior_motion2_rows": True,
            "canonical_cli_requires_verified_target_hash_and_contract_binding": True,
        },
        "claim_boundary": (
            "This projection is a governed handoff envelope, not SQL and not an insertion plan. "
            "The canonical CLI requires the comparison to have verified the declared database hash and binds "
            "the exact comparison bytes to the current schema/target contract before exposing identity suggestions."
        ),
    }
    return {
        "locator_rows": locator_rows,
        "candidate_rows": projected_candidates,
        "target_contract": target_contract,
        "authority_binding": authority_binding,
        "summary": summary,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="project_09d_motion2")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    projection = build_projection(run_dir, Path(args.database), require_verified_target=True)
    out_dir = run_dir / "09D"
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "motion2_locator_projection.jsonl", projection["locator_rows"])
    _write_jsonl(out_dir / "motion2_candidate_projection.jsonl", projection["candidate_rows"])
    (out_dir / "motion2_target_contract.json").write_text(
        json.dumps(projection["target_contract"], indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "motion2_authority_binding.json").write_text(
        json.dumps(projection["authority_binding"], indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "motion2_projection_summary.json").write_text(
        json.dumps(projection["summary"], indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({
        "projection_status": projection["summary"]["projection_status"],
        "authority_binding_verified": projection["summary"]["authority_binding_verified"],
        "authority_context_id": projection["summary"]["authority_context_id"],
        "motion2_target_contract_sha256": projection["summary"]["motion2_target_contract_sha256"],
        "comparison_scope": projection["summary"]["comparison_scope"],
        "cycle_safe_authority_comparison": projection["summary"]["cycle_safe_authority_comparison"],
        "source_unit_count": projection["summary"]["source_unit_count"],
        "candidate_count": projection["summary"]["candidate_count"],
        "projection_error_count": projection["summary"]["projection_error_count"],
    }, indent=2))
    return 0 if projection["summary"]["projection_error_count"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
