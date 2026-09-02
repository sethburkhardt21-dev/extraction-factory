"""Apply provisional W2/S1 role certification to verified benchmark scores.

A score JSON is not authority by itself. New score reports are self-describing:
they carry exact input paths and hashes. This command automatically recomputes
such reports from source units, gold, registry, and candidate files. Explicit
`--verify-inputs` paths remain supported. `--apply` is refused unless exact
recomputation succeeds.

Passing W2/S1 roles are at most CERTIFIED_WITH_LIMITS because E3 and W3/S3 are
outside the mechanically measured scope. A passing score is additionally blocked
from certification when the exact model version/weights are not immutably bound.
Whole-registry SHA remains provenance telemetry; replay authority is the exact
resolved model identity projection actually consumed by the scorer.

Lifecycle invalidation uses canonical score-relevant candidate semantics for new
certificates. Candidate IDs, run IDs, file ordering, and unused metadata therefore
cannot manufacture fresh evidence. v1.21 file fingerprints remain migration
compatible. RETIRED certification keys are terminal.
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

from hermes_factory.candidate_semantics import candidate_semantic_sha256_from_path  # noqa: E402
from hermes_factory.certification_state import aggregate_role_status, recertification_block_reason  # noqa: E402
from hermes_factory.risk import classify_source_unit  # noqa: E402
from benchmarks_ext.replay_authority import (  # noqa: E402
    scoring_authority_projection,
    scoring_authority_sha256,
    verify_replay_equivalence,
)
from benchmarks_ext.score_role import build_score_report, load_source_units_verified, sha256_file  # noqa: E402

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


def apply_version_binding_gate(score: dict, status: str, failures: list[str]) -> tuple[str, list[str]]:
    """A metrics pass cannot become a reusable certificate without immutable model identity."""
    if status not in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}:
        return status, failures
    identity = score.get("scored_identity") or {}
    if identity.get("version_binding_certifiable") is True:
        return status, failures
    policy = str(identity.get("observed_version_policy") or "MISSING")
    observed = str(identity.get("observed_version") or "MISSING")
    reason = f"model_version_binding_not_certifiable:policy={policy}:observed={observed}"
    return "BLOCKED_EXTERNAL", [*failures, reason]


def expected_w2s1_scope(source_units_path: Path, manifest: dict) -> list[str]:
    source_by_id, _ = load_source_units_verified(source_units_path, manifest)
    out = []
    for uid, unit in source_by_id.items():
        risk = classify_source_unit(unit)
        if risk.get("work_class") == "W2" and risk.get("source_class") == "S1":
            out.append(uid)
    return sorted(out)


def recompute_and_verify_score(*, score_path: Path, candidates_path: Path, reference_path: Path,
                               gold_manifest_path: Path, source_units_path: Path, registry_path: Path,
                               role: str, primary_candidates_path: Path | None = None) -> tuple[dict, dict]:
    stored = json.loads(Path(score_path).read_text(encoding="utf-8"))
    if stored.get("role") != role:
        raise ValueError(f"score_role_mismatch:{stored.get('role')}!={role}")
    model = str(stored.get("model") or "")
    scope = stored.get("units_in_scope")
    if not model:
        raise ValueError("score_model_missing")
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
    replay = verify_replay_equivalence(stored, recomputed)
    return recomputed, {
        "score_path": str(Path(score_path).resolve()),
        "score_sha256": sha256_file(score_path),
        "candidate_file_sha256": recomputed["candidate_file_sha256"],
        "primary_candidate_file_sha256": recomputed.get("primary_candidate_file_sha256"),
        "source_units_sha256": recomputed["source_units_sha256"],
        "reference_sha256": recomputed["reference_sha256"],
        "gold_manifest_sha256": recomputed["gold_manifest_sha256"],
        **replay,
    }


def verify_score_pair(*, primary_score_path: Path, blind_score_path: Path, primary_candidates_path: Path,
                      blind_candidates_path: Path, reference_path: Path, gold_manifest_path: Path,
                      source_units_path: Path, registry_path: Path) -> tuple[dict, dict, dict[str, Any]]:
    manifest = json.loads(Path(gold_manifest_path).read_text(encoding="utf-8"))
    if manifest.get("benchmark_version") != BENCHMARK_VERSION:
        raise ValueError(f"benchmark_version_mismatch:{manifest.get('benchmark_version')}")
    expected_scope = expected_w2s1_scope(source_units_path, manifest)
    if not expected_scope:
        raise ValueError("expected_W2_S1_scope_empty")
    primary, p_receipt = recompute_and_verify_score(
        score_path=primary_score_path,
        candidates_path=primary_candidates_path,
        reference_path=reference_path,
        gold_manifest_path=gold_manifest_path,
        source_units_path=source_units_path,
        registry_path=registry_path,
        role="PRIMARY",
    )
    blind, b_receipt = recompute_and_verify_score(
        score_path=blind_score_path,
        candidates_path=blind_candidates_path,
        reference_path=reference_path,
        gold_manifest_path=gold_manifest_path,
        source_units_path=source_units_path,
        registry_path=registry_path,
        role="BLIND_RECALL",
        primary_candidates_path=primary_candidates_path,
    )
    if primary.get("units_in_scope") != expected_scope or blind.get("units_in_scope") != expected_scope:
        raise ValueError(
            f"certification_scope_must_equal_all_W2_S1_units:expected={expected_scope}:"
            f"primary={primary.get('units_in_scope')}:blind={blind.get('units_in_scope')}"
        )
    for field in ["benchmark_version", "gold_label", "reference_sha256", "source_units_sha256", "gold_manifest_sha256"]:
        if primary.get(field) != blind.get(field):
            raise ValueError(f"primary_blind_benchmark_input_mismatch:{field}")
    if blind.get("primary_candidate_file_sha256") != primary.get("candidate_file_sha256"):
        raise ValueError("blind_primary_baseline_file_does_not_match_primary_score")
    if blind.get("primary_baseline_identity") != primary.get("scored_identity"):
        raise ValueError("blind_primary_baseline_identity_does_not_match_primary_score")
    return primary, blind, {
        "verification_schema_version": "hermes-role-certification-input-verification-1.4",
        "recomputation_verified": True,
        "W2_S1_scope": expected_scope,
        "primary": p_receipt,
        "blind": b_receipt,
    }


def auto_paths(primary_score_path: Path, blind_score_path: Path) -> dict[str, Path] | None:
    """Recover exact benchmark inputs from self-describing score receipts."""
    try:
        p = json.loads(Path(primary_score_path).read_text(encoding="utf-8"))
        b = json.loads(Path(blind_score_path).read_text(encoding="utf-8"))
        pp = p.get("input_paths")
        bp = b.get("input_paths")
        if not isinstance(pp, dict) or not isinstance(bp, dict):
            return None
        shared = ["reference", "gold_manifest", "source_units", "registry"]
        if any(not pp.get(k) or pp.get(k) != bp.get(k) for k in shared):
            return None
        if not pp.get("candidates") or not bp.get("candidates") or bp.get("primary_candidates") != pp.get("candidates"):
            return None
        return {
            "source_units": Path(pp["source_units"]),
            "reference": Path(pp["reference"]),
            "gold_manifest": Path(pp["gold_manifest"]),
            "registry": Path(pp["registry"]),
            "primary_candidates": Path(pp["candidates"]),
            "blind_candidates": Path(bp["candidates"]),
        }
    except Exception:
        return None


def _bound_semantic_digest(score: dict, *, path_key: str, file_sha_key: str) -> str | None:
    paths = score.get("input_paths")
    if not isinstance(paths, dict) or not paths.get(path_key):
        return None
    expected_file_sha = score.get(file_sha_key)
    if not isinstance(expected_file_sha, str) or len(expected_file_sha) != 64:
        raise ValueError(f"semantic_digest_expected_file_sha_missing:{file_sha_key}")
    path = Path(paths[path_key])
    measured = sha256_file(path)
    if measured != expected_file_sha:
        raise ValueError(f"semantic_digest_candidate_file_changed_after_score:{path_key}:{measured}!={expected_file_sha}")
    scope = score.get("units_in_scope")
    if not isinstance(scope, list) or not scope:
        raise ValueError("semantic_digest_score_scope_invalid")
    return candidate_semantic_sha256_from_path(path, units_in_scope=scope)


def build_entry(score: dict, role: str, status: str, failures: list[str], verification: dict | None) -> dict:
    compact = {key: node for key, node in score["metrics"].items() if isinstance(node, dict) and "value" in node}
    authority_projection = scoring_authority_projection(score)
    candidate_semantic_sha = _bound_semantic_digest(
        score, path_key="candidates", file_sha_key="candidate_file_sha256"
    )
    primary_semantic_sha = None
    if role == "BLIND_RECALL":
        primary_semantic_sha = _bound_semantic_digest(
            score, path_key="primary_candidates", file_sha_key="primary_candidate_file_sha256"
        )
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
        "primary_candidate_file_sha256": score.get("primary_candidate_file_sha256"),
        "candidate_semantic_sha256": candidate_semantic_sha,
        "primary_candidate_semantic_sha256": primary_semantic_sha,
        "gold_label": score["gold_label"],
        "units_in_scope": score["units_in_scope"],
        "scored_identity": score.get("scored_identity"),
        "registry_authority_projection": authority_projection,
        "registry_authority_sha256": scoring_authority_sha256(score),
        "benchmark_inputs_verified": bool(verification and verification.get("recomputation_verified")),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="certify_roles")
    parser.add_argument("--primary-score", required=True)
    parser.add_argument("--blind-score", required=True)
    parser.add_argument("--primary-provider", help="optional assertion; actual provider comes from verified score identity")
    parser.add_argument("--blind-provider", help="optional assertion; actual provider comes from verified score identity")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--verify-inputs", action="store_true")
    parser.add_argument("--source-units")
    parser.add_argument("--reference")
    parser.add_argument("--gold-manifest")
    parser.add_argument("--primary-candidates")
    parser.add_argument("--blind-candidates")
    parser.add_argument("--apply", action="store_true", help="write registry; exact score recomputation is mandatory")
    args = parser.parse_args(argv)

    explicit_values = [args.source_units, args.reference, args.gold_manifest, args.primary_candidates, args.blind_candidates]
    paths = None
    if any(explicit_values):
        if any(not x for x in explicit_values):
            print("explicit verification requires all benchmark input paths", file=sys.stderr)
            return 3
        paths = {
            "source_units": Path(args.source_units),
            "reference": Path(args.reference),
            "gold_manifest": Path(args.gold_manifest),
            "registry": Path(args.registry),
            "primary_candidates": Path(args.primary_candidates),
            "blind_candidates": Path(args.blind_candidates),
        }
    else:
        paths = auto_paths(Path(args.primary_score), Path(args.blind_score))
    must_verify = args.verify_inputs or args.apply or paths is not None
    if (args.verify_inputs or args.apply) and paths is None:
        print("score reports are not self-describing and no complete verification inputs were supplied", file=sys.stderr)
        return 3

    verification = None
    try:
        if must_verify and paths is not None:
            if Path(args.registry).resolve() != paths["registry"].resolve():
                raise ValueError(f"registry_path_mismatch:{Path(args.registry).resolve()}!={paths['registry'].resolve()}")
            primary, blind, verification = verify_score_pair(
                primary_score_path=Path(args.primary_score),
                blind_score_path=Path(args.blind_score),
                primary_candidates_path=paths["primary_candidates"],
                blind_candidates_path=paths["blind_candidates"],
                reference_path=paths["reference"],
                gold_manifest_path=paths["gold_manifest"],
                source_units_path=paths["source_units"],
                registry_path=paths["registry"],
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

    if args.apply and verification is None:
        print("refusing --apply without successful input recomputation", file=sys.stderr)
        return 3
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
    p_status, p_fail = apply_version_binding_gate(primary, p_status, p_fail)
    b_status, b_fail = apply_version_binding_gate(blind, b_status, b_fail)

    registry_path = Path(args.registry)
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["benchmark_version"] = BENCHMARK_VERSION
        certs = registry.setdefault("certifications", {})
        if not isinstance(certs, dict):
            raise ValueError("registry_certifications_not_object")

        def key(provider: str, model: str, role: str) -> str:
            return "|".join([provider.upper(), model, role, "W2", "S1", BENCHMARK_VERSION])

        changes = {
            key(p_provider, primary["model"], "PRIMARY"): build_entry(primary, "PRIMARY", p_status, p_fail, verification),
            key(b_provider, blind["model"], "BLIND_RECALL"): build_entry(blind, "BLIND_RECALL", b_status, b_fail, verification),
        }
        reactivation_blocks = {
            cert_key: reason
            for cert_key, entry in changes.items()
            if (reason := recertification_block_reason(registry, cert_key, entry)) is not None
        }
    except (ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
        print(f"certification registry policy verification failed: {exc}", file=sys.stderr)
        return 5

    output = {
        "primary": {
            "model": primary["model"],
            "provider": p_provider,
            "status": p_status,
            "failures": p_fail,
            "observed_version": p_identity.get("observed_version"),
            "registry_authority_sha256": scoring_authority_sha256(primary),
            "candidate_semantic_sha256": next(iter(changes.values())).get("candidate_semantic_sha256") if changes else None,
        },
        "blind": {
            "model": blind["model"],
            "provider": b_provider,
            "status": b_status,
            "failures": b_fail,
            "observed_version": b_identity.get("observed_version"),
            "registry_authority_sha256": scoring_authority_sha256(blind),
            "candidate_semantic_sha256": changes.get(key(b_provider, blind["model"], "BLIND_RECALL"), {}).get("candidate_semantic_sha256"),
            "primary_candidate_semantic_sha256": changes.get(key(b_provider, blind["model"], "BLIND_RECALL"), {}).get("primary_candidate_semantic_sha256"),
        },
        "registry_keys_written": sorted(changes) if not reactivation_blocks else [],
        "reactivation_blocks": reactivation_blocks,
        "input_recomputation_verified": bool(verification),
        "verification": verification,
        "applied": bool(args.apply and not reactivation_blocks),
    }

    if args.apply and reactivation_blocks:
        print(json.dumps(output, indent=2))
        print("refusing --apply because benchmark evidence was previously invalidated by certification lifecycle policy", file=sys.stderr)
        return 6

    certs.update(changes)
    role_status = registry.setdefault("role_status", {})
    if not isinstance(role_status, dict):
        print("certification registry policy verification failed: registry_role_status_not_object", file=sys.stderr)
        return 5
    role_status["PRIMARY_W2"] = aggregate_role_status(
        certs, role="PRIMARY", work_class="W2", benchmark_version=BENCHMARK_VERSION
    )
    role_status["BLIND_RECALL_W2"] = aggregate_role_status(
        certs, role="BLIND_RECALL", work_class="W2", benchmark_version=BENCHMARK_VERSION
    )
    registry["claim_boundary"] = (
        "Certifications are model-version/role/work/source/benchmark specific. Applied certification requires "
        "source-bound deterministic score recomputation, immutable model-version binding, preserved scoring-authority "
        "identity, and semantic benchmark evidence not previously invalidated by a lifecycle action. Candidate/run IDs, "
        "row order, and unused metadata cannot manufacture freshness. Whole-registry SHA is provenance telemetry. "
        "v1.21 file fingerprints remain migration compatible; RETIRED keys remain terminal. W3/S3, PRECISION_REVIEW and "
        "COLD_AUDIT remain outside this certification."
    )
    print(json.dumps(output, indent=2))
    if args.apply:
        registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
        print(f"registry updated: {registry_path}")
        print("NOTE: registry is protected production state — rerun tests and certify-build after this change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
