"""Build a non-writing 09D Motion-2 projection from a completed factory run.

This stage exists to reduce friction for the future governed 09D ingest lane.
It does NOT insert rows, select canonical identities, merge entities, or promote
assertions. It introspects the sealed target schema read-only and emits a
self-contained projection envelope describing what can be mapped mechanically
and what still requires 09D-side adjudication.
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

from hermes_factory.bridge_09d import inventory_schema_readonly, motion2_capability_readonly  # noqa: E402
from hermes_factory.hashing import sha256_text  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts)
    return f"{prefix}-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _required_without_default(columns: list[dict[str, Any]]) -> list[str]:
    return sorted(
        str(c["name"]) for c in columns
        if int(c.get("notnull") or 0) == 1 and c.get("dflt_value") is None and int(c.get("pk") or 0) == 0
    )


def _schema_mapping_plan(carrier_columns: list[dict[str, Any]], locator_columns: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify observed target columns by who is allowed to populate them.

    This is descriptive, not executable SQL. Unknown required columns are made
    explicit so a future 09D-owned loader cannot silently drop them.
    """
    carrier_names = {str(c["name"]) for c in carrier_columns}
    locator_names = {str(c["name"]) for c in locator_columns}

    carrier_mechanical = {
        "value_text": "factory.proposition",
        "ingest_locator_id": "projection.projection_locator_id -> 09D loader assigned locator id",
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


def _comparison_by_candidate(run_dir: Path) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(run_dir / "09D" / "comparison_09d.jsonl")
    return {str(r.get("candidate_id")): r for r in rows if r.get("candidate_id")}


def build_projection(run_dir: Path, database: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    database = Path(database)
    candidates = _read_jsonl(run_dir / "ASSERTIONS" / "union_candidates.jsonl")
    source_units = _read_jsonl(run_dir / "SOURCE" / "source_units.jsonl")
    comparisons = _comparison_by_candidate(run_dir)

    schema = inventory_schema_readonly(database)
    capability = motion2_capability_readonly(database)
    table_schema = schema.get("schema", {})
    carrier_columns = table_schema.get("source_assertion_candidate", [])
    locator_columns = table_schema.get("ingest_source_locator", [])
    mapping_plan = _schema_mapping_plan(carrier_columns, locator_columns)

    source_by_id = {str(u.get("source_unit_id")): u for u in source_units}
    locator_rows: list[dict[str, Any]] = []
    locator_id_by_unit: dict[str, str] = {}
    projection_errors: list[dict[str, Any]] = []

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
            "target_table": "ingest_source_locator",
            "target_columns_observed": sorted(str(c["name"]) for c in locator_columns),
            "direct_insert_allowed": False,
        })

    projected_candidates: list[dict[str, Any]] = []
    state_counts: dict[str, int] = defaultdict(int)
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
        predicate_resolution = comparison.get("predicate_resolution") or {}
        top_matches = list(comparison.get("top_matches") or [])
        compatible_top = [m for m in top_matches if m.get("subject_compatible") and m.get("predicate_compatible") and m.get("fact_family_compatible", True)]

        if len(resolved_ids) == 1:
            single_entity_resolution += 1
        if predicate_resolution.get("mode") == "EXACT_CODE_OR_LABEL":
            exact_predicate_resolution += 1

        identity_candidates = []
        seen = set()
        for entity_id in resolved_ids:
            if entity_id not in seen:
                seen.add(entity_id)
                identity_candidates.append({"subject_entity_id": entity_id, "basis": subject_resolution.get("mode"), "selection_authorized": False})
        for match in compatible_top:
            entity_id = match.get("subject_entity_id")
            if entity_id is not None and str(entity_id) not in seen:
                seen.add(str(entity_id))
                identity_candidates.append({
                    "subject_entity_id": entity_id,
                    "basis": "COMPARATOR_TOP_MATCH",
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
                    "basis": predicate_resolution.get("mode") or "COMPARATOR_TOP_MATCH",
                    "score": match.get("score"),
                    "selection_authorized": False,
                })

        state = comparison.get("state") or "NOT_COMPARED"
        state_counts[state] += 1
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
            "subject_identity_candidates": identity_candidates,
            "predicate_identity_candidates": predicate_candidates,
            "target_table": "source_assertion_candidate",
            "target_columns_observed": sorted(str(c["name"]) for c in carrier_columns),
            "automatic_identity_merge_allowed": False,
            "automatic_canonicalization_allowed": False,
            "direct_insert_allowed": False,
        })

    required_tables_ok = bool(capability.get("required_tables_present"))
    witness_ok = bool(capability.get("motion2_witness_columns_present") and capability.get("motion2_witness_constraint_present"))
    evidence_ok_all = not projection_errors
    mapping_gaps = (
        mapping_plan["source_assertion_candidate"]["unclassified_required_columns"]
        or mapping_plan["ingest_source_locator"]["unclassified_required_columns"]
    )
    if not (required_tables_ok and witness_ok and evidence_ok_all):
        projection_status = "PROJECTION_REVIEW_REQUIRED"
    elif mapping_gaps:
        projection_status = "SCHEMA_COMPATIBLE_MAPPING_GAPS"
    else:
        projection_status = "SCHEMA_COMPATIBLE_NEEDS_GOVERNED_09D_LOADER"

    summary = {
        "stage": "READ_ONLY_09D_MOTION2_PROJECTION",
        "projection_status": projection_status,
        "database": str(database),
        "database_schema_fingerprint_sha256": capability.get("schema_fingerprint_sha256"),
        "motion2_capability": capability,
        "source_unit_count": len(source_units),
        "candidate_count": len(candidates),
        "comparison_state_counts": dict(sorted(state_counts.items())),
        "single_entity_resolution_candidate_count": single_entity_resolution,
        "exact_predicate_resolution_candidate_count": exact_predicate_resolution,
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
            "identity_and_predicate_candidates_are_suggestions_only": True,
        },
        "claim_boundary": (
            "This projection is a governed handoff envelope, not SQL and not an insertion plan. "
            "A future 09D-owned loader/adjudicator must assign target-native IDs, validate required columns, "
            "resolve identities/predicates, and enforce 09D governance before any Motion-2 mutation."
        ),
    }
    return {
        "locator_rows": locator_rows,
        "candidate_rows": projected_candidates,
        "summary": summary,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="project_09d_motion2")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    projection = build_projection(run_dir, Path(args.database))
    out_dir = run_dir / "09D"
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "motion2_locator_projection.jsonl", projection["locator_rows"])
    _write_jsonl(out_dir / "motion2_candidate_projection.jsonl", projection["candidate_rows"])
    (out_dir / "motion2_projection_summary.json").write_text(
        json.dumps(projection["summary"], indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({
        "projection_status": projection["summary"]["projection_status"],
        "source_unit_count": projection["summary"]["source_unit_count"],
        "candidate_count": projection["summary"]["candidate_count"],
        "projection_error_count": projection["summary"]["projection_error_count"],
    }, indent=2))
    return 0 if projection["summary"]["projection_error_count"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
