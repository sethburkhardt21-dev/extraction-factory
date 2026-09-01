"""Apply provisional W2/S1 role certification to verified benchmark scores.

A score JSON is not authority by itself. `--verify-inputs` recomputes PRIMARY and
BLIND_RECALL reports from the exact source units, gold reference, gold manifest,
registry and candidate files and requires byte-for-byte deterministic report
equality. `--apply` is refused unless this recomputation succeeds.

Current thresholds:
  PRIMARY: recall>=.94, precision>=.93, exact-source evidence fidelity=1.00,
           qualifier preservation>=.95 where applicable, E4 proxy=0.
  BLIND:   omission recovery>=.50, useful-new precision>=.70, E4 proxy=0.

E3 remains unmeasured and W3/S3 remains outside this certification scope, so a
passing role is at most CERTIFIED_WITH_LIMITS.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.risk import classify_source_unit  # noqa: E402
from benchmarks_ext.score_role import (  # noqa: E402
    build_score_report,
    load_source_units_verified,
    sha256_file,
)

BENCHMARK_VERSION = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"
DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"

STANDING_LIMITS = [
    "E3 (clinically material distortion) not measured — requires clinical/frontier review",
    "E4 measured by mechanical cue-injection proxy only, not semantic review",
    "benchmark corpus = 8 source units from one source (Machines/Dorsch p299-301), certification scope W2/S1 only",
    "W3/S3 table, figure/visual, equation and cross-page semantic binding NOT certified by this rule",
    "gold reference is AI-authored source-first, label MECHANICALLY_CHECKED",
]


def _value(metrics: dict, key: str):
    node = metrics.get(key)
    return node.get("value") if isinstance(node, dict) else None


def decide_primary(metrics: dict) -> tuple[str, list[str]]:
    checks = {
        "recall>=0.94": (_value(metrics, "semantic_unit_recall"), 0.94),
        "precision>=0.93": (_value(metrics, "semantic_unit_precision"), 0.93),
        "evidence_fidelity==1.00": (_value(metrics, "evidence_fidelity_exact_substring"), 1.0),
        "qualifier_preservation>=0.95": (_value(metrics, "qualifier_preservation"), 0.95),
        "e4_proxy==0": (1.0 - (_value(metrics, "e4_mechanical_proxy_cue_injection") or 0.0), 1.0),
    }
    failures = []
    for name, (measured, floor) in checks.items():
        if measured is None:
            if "qualifier" in name:
                continue
            failures.append(f"{name}: NOT_MEASURED")
        elif measured + 1e-9 < floor:
            failures.append(f"{name}: measured {measured:.4f}")
    return ("CERTIFIED_WITH_LIMITS" if not failures else "REJECTED"), failures


def decide_blind(metrics: dict) -> tuple[str, list[str]]:
    checks = {
        "omission_recovery>=0.50": (_value(metrics, "blind_omission_recovery"), 0.50),
        "useful_new_precision>=0.70": (_value(metrics, "blind_useful_new_candidate_precision"), 0.70),
        "e4_proxy==0": (1.0 - (_value(metrics, "e4_mechanical_proxy_cue_injection") or 0.0), 1.0),
    }
    failures = []
    for name, (measured, floor) in checks.items():
        if measured is None:
            failures.append(f"{name}: NOT_MEASURED")
        elif measured + 1e-9 < floor:
            failures.append(f"{name}: measured {measured:.4f}")
    return ("CERTIFIED_WITH_LIMITS" if not failures else "REJECTED"), failures


def expected_w2s1_scope(source_units_path: Path, manifest: dict) -> list[str]:
    source_by_id, _ = load_source_units_verified(source_units_path, manifest)
    return sorted(
        uid for uid, unit in source_by_id.items()
        if classify_source_unit(unit).get("work_class") == "W2"
        and classify_source_unit(unit).get("source_class") == "S1"
    )


def recompute_and_verify_score(*, score_path: Path, candidates_path: Path,
                               reference_path: Path, gold_manifest_path: Path,
                               source_units_path: Path, registry_path: Path,
                               role: str, primary_candidates_path: Path | None = None) -> tuple[dict, dict]:
    stored = json.loads(Path(score_path).read_text(encoding="utf-8"))
    if stored.get("role") != role:
        raise ValueError(f"score_role_mismatch:{stored.get('role')}!={role}")
    model = str(stored.get("model") or "")
    if not model:
        raise ValueError("score_model_missing")
    scope = stored.get("units_in_scope")
    if not isinstance(scope, list) or not scope or any(not isinstance(x, str) or not x for x in scope):
        raise ValueError("score_scope_invalid")
    recomputed = build_score_report(
        candidates_path=candidates_path,
        reference_path=reference_path,
        gold_manifest_path=gold_manifest_path,
        source_units_path=source_units_path,
        registry_path=registry_path,
        role=role,
        model=model,
        units_in_scope=set(scope),
        primary_candidates_path=primary_candidates_path,
    )
    if stored != recomputed:
        changed = sorted(k for k in set(stored) | set(recomputed) if stored.get(k) != recomputed.get(k))
        raise ValueError(f"score_report_does_not_match_recomputation:{changed}")
    receipt = {
        "score_path": str(score_path),
        "score_sha256": sha256_file(score_path),
        "candidate_file_sha256": recomputed["candidate_file_sha256"],
        "primary_candidate_file_sha256": recomputed.get("primary_candidate_file_sha256"),
        "source_units_sha256": recomputed["source_units_sha256"],
        "reference_sha256": recomputed["reference_sha256"],
        "gold_manifest_sha256": recomputed["gold_manifest_sha256"],
        "registry_sha256": recomputed["registry_sha256"],
        "recomputed_equal": True,
    }
    return recomputed, receipt


def verify_score_pair(*, primary_score_path: Path, blind_score_path: Path,
                      primary_candidates_path: Path, blind_candidates_path: Path,
                      reference_path: Path, gold_manifest_path: Path,
                      source_units_path: Path, registry_path: Path) -> tuple[dict, dict, dict[str, Any]]:
    manifest = json.loads(Path(gold_manifest_path).read_text(encoding="utf-8"))
    if manifest.get("benchmark_version") != BENCHMARK_VERSION:
        raise ValueError(f"benchmark_version_mismatch:{manifest.get('benchmark_version')}")
    expected_scope = expected_w2s1_scope(source_units_path, manifest)
    if not expected_scope:
        raise ValueError("expected_W2_S1_scope_empty")

    primary, p_receipt = recompute_and_verify_score(
        score_path=primary_score_path, candidates_path=primary_candidates_path,
        reference_path=reference_path, gold_manifest_path=gold_manifest_path,
        source_units_path=source_units_path, registry_path=registry_path,
        role="PRIMARY",
    )
    blind, b_receipt = recompute_and_verify_score(
        score_path=blind_score_path, candidates_path=blind_candidates_path,
        reference_path=reference_path, gold_manifest_path=gold_manifest_path,
        source_units_path=source_units_path, registry_path=registry_path,
        role="BLIND_RECALL", primary_candidates_path=primary_candidates_path,
    )
    if primary.get("units_in_scope") != expected_scope or blind.get("units_in_scope") != expected_scope:
        raise ValueError(
            f"certification_scope_must_equal_all_W2_S1_units:expected={expected_scope}:"
            f"primary={primary.get('units_in_scope')}:blind={blind.get('units_in_scope')}"
        )
    shared_fields = ["benchmark_version", "gold_label", "reference_sha256", "source_units_sha256", "gold_manifest_sha256"]
    for field in shared_fields:
        if primary.get(field) != blind.get(field):
            raise ValueError(f"primary_blind_benchmark_input_mismatch:{field}")
    if blind.get("primary_candidate_file_sha256") != primary.get("candidate_file_sha256"):
        raise ValueError("blind_primary_baseline_file_does_not_match_primary_score")
    if blind.get("primary_baseline_identity") != primary.get("scored_identity"):
        raise ValueError("blind_primary_baseline_identity_does_not_match_primary_score")
    receipt = {
        "verification_schema_version": "hermes-role-certification-input-verification-1.0",
        "recomputation_verified": True,
        "W2_S1_scope": expected_scope,
        "primary": p_receipt,
        "blind": b_receipt,
    }
    return primary, blind, receipt


def build_entry(score: dict, role: str, status: str, failures: list[str], verification: dict | None) -> dict:
    metrics = score["metrics"]
    compact = {key: node for key, node in metrics.items() if isinstance(node, dict) and "value" in node}
    return {
        "status": status,
        "decided_at_epoch": round(time.time(), 1),
        "decision_rule": "CERT-W2-S1" if role == "PRIMARY" else "CERT-BLIND-RECALL",
        "measured_metrics": compact,
        "threshold_failures": failures,
        "limits": STANDING_LIMITS,
        "gold_reference_sha256": score["reference_sha256"],
        "gold_manifest_sha256": score.get("gold_manifest_sha256"),
        "source_units_sha256": score.get("source_units_sha256"),
        "candidate_file_sha256": score.get("candidate_file_sha256"),
        "gold_label": score["gold_label"],
        "units_in_scope": score["units_in_scope"],
        "scored_identity": score.get("scored_identity"),
        "benchmark_inputs_verified": bool(verification and verification.get("recomputation_verified")),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="certify_roles")
    parser.add_argument("--primary-score", required=True)
    parser.add_argument("--blind-score", required=True)
    parser.add_argument("--primary-provider", help="optional assertion; actual provider comes from verified score identity")
    parser.add_argument("--blind-provider", help="optional assertion; actual provider comes from verified score identity")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--verify-inputs", action="store_true", help="recompute both score reports from exact benchmark inputs")
    parser.add_argument("--source-units")
    parser.add_argument("--reference")
    parser.add_argument("--gold-manifest")
    parser.add_argument("--primary-candidates")
    parser.add_argument("--blind-candidates")
    parser.add_argument("--apply", action="store_true", help="write registry; requires successful --verify-inputs")
    args = parser.parse_args(argv)

    required_paths = [args.source_units, args.reference, args.gold_manifest, args.primary_candidates, args.blind_candidates]
    if args.apply and not args.verify_inputs:
        print("refusing --apply without --verify-inputs recomputation", file=sys.stderr)
        return 3
    if args.verify_inputs and any(not x for x in required_paths):
        print("--verify-inputs requires --source-units --reference --gold-manifest --primary-candidates --blind-candidates", file=sys.stderr)
        return 3

    verification = None
    try:
        if args.verify_inputs:
            primary, blind, verification = verify_score_pair(
                primary_score_path=Path(args.primary_score), blind_score_path=Path(args.blind_score),
                primary_candidates_path=Path(args.primary_candidates), blind_candidates_path=Path(args.blind_candidates),
                reference_path=Path(args.reference), gold_manifest_path=Path(args.gold_manifest),
                source_units_path=Path(args.source_units), registry_path=Path(args.registry),
            )
        else:
            primary = json.loads(Path(args.primary_score).read_text(encoding="utf-8"))
            blind = json.loads(Path(args.blind_score).read_text(encoding="utf-8"))
            for score in (primary, blind):
                if score.get("benchmark_version") != BENCHMARK_VERSION:
                    raise ValueError(f"benchmark version mismatch: {score.get('benchmark_version')}")
    except (ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
        print(f"certification input verification failed: {exc}", file=sys.stderr)
        return 4

    p_identity = primary.get("scored_identity") or {}
    b_identity = blind.get("scored_identity") or {}
    p_provider = str(p_identity.get("provider") or "")
    b_provider = str(b_identity.get("provider") or "")
    if not p_provider or not b_provider:
        print("score reports missing scored provider identity", file=sys.stderr)
        return 4
    if args.primary_provider and args.primary_provider.upper() != p_provider.upper():
        print(f"primary provider assertion mismatch:{args.primary_provider}!={p_provider}", file=sys.stderr)
        return 4
    if args.blind_provider and args.blind_provider.upper() != b_provider.upper():
        print(f"blind provider assertion mismatch:{args.blind_provider}!={b_provider}", file=sys.stderr)
        return 4

    p_status, p_fail = decide_primary(primary["metrics"])
    b_status, b_fail = decide_blind(blind["metrics"])

    registry_path = Path(args.registry)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["benchmark_version"] = BENCHMARK_VERSION
    certs = registry.setdefault("certifications", {})

    def key(provider: str, model: str, role: str) -> str:
        return "|".join([provider.upper(), model, role, "W2", "S1", BENCHMARK_VERSION])

    changes = {
        key(p_provider, primary["model"], "PRIMARY"): build_entry(primary, "PRIMARY", p_status, p_fail, verification),
        key(b_provider, blind["model"], "BLIND_RECALL"): build_entry(blind, "BLIND_RECALL", b_status, b_fail, verification),
    }
    certs.update(changes)
    role_status = registry.setdefault("role_status", {})
    role_status["PRIMARY_W2"] = p_status
    role_status["BLIND_RECALL_W2"] = b_status
    registry["claim_boundary"] = (
        "Certifications are model/role/work-class/source-class/benchmark specific. Applied certification requires "
        "source-bound deterministic score recomputation. W3/S3 table-visual/equation/cross-page semantics, "
        "PRECISION_REVIEW and COLD_AUDIT remain outside this certification."
    )

    output = {
        "primary": {"model": primary["model"], "provider": p_provider, "status": p_status, "failures": p_fail},
        "blind": {"model": blind["model"], "provider": b_provider, "status": b_status, "failures": b_fail},
        "registry_keys_written": sorted(changes),
        "input_recomputation_verified": bool(verification),
        "verification": verification,
        "applied": bool(args.apply),
    }
    print(json.dumps(output, indent=2))
    if args.apply:
        registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
        print(f"registry updated: {registry_path}")
        print("NOTE: registry is protected production state — rerun tests and certify-build after this change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
