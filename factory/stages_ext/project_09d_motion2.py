"""Build a deterministic, non-writing 09D Motion-2 compatibility envelope.

This stage does NOT insert into 09D. It transforms factory candidates into a
stable candidate-review envelope shaped around the current 09D candidate and
Motion-2 witness contracts. Fields that can only be assigned by downstream 09D
intake/L15 remain explicitly unresolved rather than guessed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.contract_09d import verify_09d_contract  # noqa: E402
from hermes_factory.hashing import sha256_json  # noqa: E402


PROJECTION_VERSION = "09d-motion2-candidate-envelope-1.0"
SOURCE_TABLE = "extraction_factory.motion2_candidate"


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip().lower()
    return text or None


def _stable_identities(candidate: Dict[str, Any]) -> tuple[str, str]:
    witness = {
        "source_sha256": candidate.get("source_sha256"),
        "source_id": candidate.get("source_id"),
        "source_version_id": candidate.get("source_version_id"),
        "source_unit_id": candidate.get("source_unit_id"),
        "locator": candidate.get("locator") or {},
        "evidence_sha256": candidate.get("evidence_sha256"),
    }
    witness_sha = sha256_json(witness)
    structured = {
        "subject": _norm(candidate.get("subject")),
        "predicate": _norm(candidate.get("predicate")),
        "object_value": _norm(candidate.get("object_value")),
        "polarity": _norm(candidate.get("polarity")),
        "certainty": _norm(candidate.get("certainty")),
        "conditionality": _norm(candidate.get("conditionality")),
        "temporality": _norm(candidate.get("temporality")),
        "comparison": _norm(candidate.get("comparison")),
        "relationship_direction": _norm(candidate.get("relationship_direction")),
        "qualifiers": sorted(_norm(x) for x in (candidate.get("qualifiers") or []) if _norm(x)),
        "numeric_values": candidate.get("numeric_values") or [],
    }
    # Prefer source-grounded structured identity so different model phrasings can
    # converge. If structured subject/predicate are absent, proposition text is
    # the fallback discriminator rather than pretending semantic identity exists.
    if not structured["subject"] or not structured["predicate"]:
        structured["proposition_fallback"] = _norm(candidate.get("proposition"))
    claim_sha = sha256_json({"witness_sha256": witness_sha, "claim": structured})
    return witness_sha, claim_sha


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _route_map(run_dir: Path) -> dict[str, dict]:
    families = _load_jsonl(run_dir / "FAMILIES" / "evidence_families.jsonl")
    routes = {r.get("family_id"): r for r in _load_jsonl(run_dir / "REVIEW" / "routes.jsonl")}
    out: dict[str, dict] = {}
    for family in families:
        route = routes.get(family.get("family_id")) or {
            "action": "REVIEW_REQUIRED",
            "unresolved_flags": ["ROUTE_MISSING"],
        }
        for cid in family.get("member_candidate_ids") or []:
            out[str(cid)] = route
    return out


def build_projection(run_dir: Path, database: Path | None = None) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    union_path = run_dir / "ASSERTIONS" / "union_candidates.jsonl"
    if not union_path.exists():
        raise FileNotFoundError(f"union candidates not found: {union_path}")
    candidates = _load_jsonl(union_path)
    route_by_candidate = _route_map(run_dir)

    contract_report = None
    if database is not None:
        contract_report = verify_09d_contract(Path(database), verify_identity=True, strict_counts=True)
        if not contract_report["ok"]:
            raise RuntimeError("09d_contract_failed:" + ";".join(contract_report["errors"]))

    grouped: dict[str, list[dict]] = defaultdict(list)
    witness_by_claim: dict[str, str] = {}
    for candidate in candidates:
        witness_sha, claim_sha = _stable_identities(candidate)
        grouped[claim_sha].append(candidate)
        witness_by_claim[claim_sha] = witness_sha

    rows: list[dict] = []
    collision_errors: list[str] = []
    for claim_sha in sorted(grouped):
        members = grouped[claim_sha]
        representative = sorted(members, key=lambda x: str(x.get("candidate_id")))[0]
        routes = [route_by_candidate.get(str(c.get("candidate_id")), {}) for c in members]
        route_actions = sorted({str(r.get("action") or "REVIEW_REQUIRED") for r in routes})
        unresolved_flags = sorted({str(flag) for r in routes for flag in (r.get("unresolved_flags") or [])})
        local_precision_complete = bool(route_actions) and route_actions == ["LOCAL_PRECISION_COMPLETE"]
        metadata = representative.get("metadata") or {}
        domain = metadata.get("domain") or metadata.get("domain_hint") or "UNRESOLVED"
        registry_candidate_id = "CAND:" + claim_sha[:40]
        source_key = "MOTION2:" + claim_sha
        rows.append({
            "projection_version": PROJECTION_VERSION,
            "factory_candidate_ids": sorted(str(c.get("candidate_id")) for c in members),
            "factory_origin_passes": sorted({str(c.get("origin_pass")) for c in members}),
            "stable_witness_sha256": witness_by_claim[claim_sha],
            "stable_claim_sha256": claim_sha,
            "candidate_registry": {
                "candidate_id": registry_candidate_id,
                "domain": domain,
                "source_table": SOURCE_TABLE,
                "source_key": source_key,
                "source_identity_sha256": claim_sha,
                "origin_package_id": None,
                "state": "REGISTERED",
                "legacy_entity_id": None,
            },
            "source_assertion_candidate_motion2_template": {
                "source_resource_id": None,
                "ingest_locator_id": None,
                "parent_assertion_id": None,
                "source_locator_id": None,
                "raw_cell_id": None,
                "carried_status": None,
                "carried_confidence_basis": None,
                "carried_source_era": None,
            },
            "source_grounding": {
                "source_id": representative.get("source_id"),
                "source_version_id": representative.get("source_version_id"),
                "source_sha256": representative.get("source_sha256"),
                "source_unit_id": representative.get("source_unit_id"),
                "locator": representative.get("locator") or {},
                "evidence_sha256": representative.get("evidence_sha256"),
                "proposition": representative.get("proposition"),
                "subject": representative.get("subject"),
                "predicate": representative.get("predicate"),
                "object_value": representative.get("object_value"),
                "numeric_values": representative.get("numeric_values") or [],
                "qualifiers": representative.get("qualifiers") or [],
                "polarity": representative.get("polarity"),
            },
            "factory_review": {
                "route_actions": route_actions,
                "unresolved_flags": unresolved_flags,
                "local_precision_complete": local_precision_complete,
            },
            "09d_intake_readiness": {
                "candidate_review_exportable": True,
                "recommended_disposition": "REGISTER" if local_precision_complete else "DEFER_FOR_REVIEW",
                "insert_ready": False,
                "missing_downstream_assignments": [
                    "candidate_registry.origin_package_id",
                    "candidate_registry.domain" if domain == "UNRESOLVED" else None,
                    "source_assertion_candidate.ingest_locator_id",
                ],
                "requires_l15_dry_run": True,
                "automatic_insert_allowed": False,
                "automatic_match_allowed": False,
                "automatic_promotion_allowed": False,
                "automatic_canonicalization_allowed": False,
                "automatic_selection_allowed": False,
            },
        })
        rows[-1]["09d_intake_readiness"]["missing_downstream_assignments"] = [
            x for x in rows[-1]["09d_intake_readiness"]["missing_downstream_assignments"] if x
        ]

    # Candidate-registry source identity is UNIQUE. Any duplicate registry ID with
    # differing source identity would make the envelope unsafe to hand downstream.
    by_registry_id: dict[str, str] = {}
    for row in rows:
        rid = row["candidate_registry"]["candidate_id"]
        identity = row["candidate_registry"]["source_identity_sha256"]
        previous = by_registry_id.setdefault(rid, identity)
        if previous != identity:
            collision_errors.append(f"candidate_registry_id_collision:{rid}")

    out_dir = run_dir / "09D"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "motion2_candidate_envelope.jsonl"
    with out_path.with_suffix(out_path.suffix + ".tmp").open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
    out_path.with_suffix(out_path.suffix + ".tmp").replace(out_path)

    summary = {
        "projection_version": PROJECTION_VERSION,
        "factory_candidate_count": len(candidates),
        "stable_projected_candidate_count": len(rows),
        "deduplicated_factory_candidate_count": len(candidates) - len(rows),
        "local_precision_complete_count": sum(1 for r in rows if r["factory_review"]["local_precision_complete"]),
        "defer_for_review_count": sum(1 for r in rows if not r["factory_review"]["local_precision_complete"]),
        "collision_errors": collision_errors,
        "09d_contract_verified": bool(contract_report and contract_report.get("ok")),
        "insert_ready_count": 0,
        "automatic_insert_allowed": False,
        "automatic_promotion_allowed": False,
        "claim_boundary": (
            "This is a deterministic candidate-review projection only. It deliberately leaves 09D-owned "
            "package and ingest-locator identities unresolved and emits no SQL writes. Downstream L15 must "
            "perform a dry-run against a copy of the declared parent before any future ingest package exists."
        ),
    }
    summary_path = out_dir / "motion2_candidate_envelope_summary.json"
    tmp = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(summary_path)
    if contract_report is not None:
        contract_path = out_dir / "09d_contract_projection_preflight.json"
        tmp = contract_path.with_suffix(contract_path.suffix + ".tmp")
        tmp.write_text(json.dumps(contract_report, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(contract_path)
    if collision_errors:
        raise RuntimeError("09d_projection_collision:" + ";".join(collision_errors))
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="project_09d_motion2")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--database")
    args = p.parse_args(argv)
    try:
        summary = build_projection(Path(args.run_dir), Path(args.database) if args.database else None)
    except Exception as exc:
        print(f"09D Motion-2 projection failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
