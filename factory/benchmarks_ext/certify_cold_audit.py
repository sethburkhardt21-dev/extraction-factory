"""Certify the independent COLD_AUDIT role from replay-verifiable benchmark artifacts.

This closes the readiness reachability gap without weakening the cold-audit gate.
The certifier never trusts a hand-edited score JSON: it rebuilds the report from
the frozen source-first gold, deterministic cold benchmark cases, and recorded
verdict artifacts, then applies fixed thresholds and model-version authority.

The auditor task itself is generic skeptical review, but the current runtime keys
certification by source W/S stratum. One verified qualification decision is
therefore projected into only the exact W/S strata and source units present in
the benchmark. This does not broaden PRIMARY/BLIND extraction certification.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from benchmarks_ext.cold_audit_score import BENCHMARK_VERSION, build_report_from_artifacts  # noqa: E402
from benchmarks_ext.replay_authority import (  # noqa: E402
    scoring_authority_projection,
    scoring_authority_sha256,
    verify_replay_equivalence,
)
from benchmarks_ext.score_role import load_source_units_verified  # noqa: E402
from hermes_factory.certification_state import recertification_block_reason  # noqa: E402
from hermes_factory.model_registry import load_registry  # noqa: E402
from hermes_factory.risk import classify_source_unit  # noqa: E402

DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"
DECISION_RULE = "CERT-COLD-AUDIT-v1"
LIMITS = [
    "qualification corpus = frozen Machines/Dorsch p299-301 source-first gold plus deterministic unsupported mutations",
    "supported positives inherit AI-authored source-first gold label MECHANICALLY_CHECKED; this is not independent clinical truth",
    "negative cases test preservation/adversarial detection, not every possible hallucination class",
    "certificate is exact source, model-version, protected-identity, benchmark, W/S-stratum and unit scoped",
    "runtime still requires auditor independence from the active PRIMARY and BLIND_RECALL groups",
    "a clean cold audit is sampled review evidence and never canonicalizes an assertion",
]


def _value(metrics: dict, key: str) -> float | None:
    node = metrics.get(key)
    value = node.get("value") if isinstance(node, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def decide(metrics: dict, units_in_scope: list[str]) -> tuple[str, list[str]]:
    failures: list[str] = []
    counts = metrics.get("case_counts") if isinstance(metrics, dict) else None
    if not isinstance(counts, dict):
        failures.append("case_counts_missing")
        counts = {}
    supported = int(counts.get("supported") or 0)
    unsupported = int(counts.get("unsupported") or 0)
    if supported < max(8, len(units_in_scope)):
        failures.append(f"supported_case_count_too_small:{supported}")
    if unsupported < max(8, len(units_in_scope)):
        failures.append(f"unsupported_case_count_too_small:{unsupported}")

    checks = {
        "supported_recall>=0.95": (_value(metrics, "supported_case_recall"), 0.95),
        "unsupported_rejection>=0.95": (_value(metrics, "unsupported_case_rejection"), 0.95),
        "overall_accuracy>=0.95": (_value(metrics, "overall_accuracy"), 0.95),
    }
    for label, (value, floor) in checks.items():
        if value is None:
            failures.append(f"{label}:NOT_MEASURED")
        elif value + 1e-9 < floor:
            failures.append(f"{label}:measured={value:.4f}")
    error_rate = _value(metrics, "provider_error_rate")
    if error_rate is None:
        failures.append("provider_error_rate:NOT_MEASURED")
    elif error_rate > 1e-12:
        failures.append(f"provider_error_rate_must_be_zero:measured={error_rate:.4f}")

    mutation = metrics.get("mutation_rejection")
    if not isinstance(mutation, dict) or len(mutation) < 3:
        failures.append(f"mutation_type_coverage_too_small:{len(mutation) if isinstance(mutation, dict) else 0}")
    else:
        for kind in ("NUMERIC_VALUE_CHANGED", "RELATIONSHIP_REVERSED", "QUALIFIER_DROPPED"):
            node = mutation.get(kind)
            if isinstance(node, dict) and int(node.get("denominator") or 0) > 0:
                value = node.get("value")
                if not isinstance(value, (int, float)) or float(value) + 1e-9 < 0.90:
                    failures.append(f"{kind}_rejection>=0.90:measured={value}")

    return ("CERTIFIED_WITH_LIMITS" if not failures else "REJECTED"), failures


def apply_version_gate(score: dict, status: str, failures: list[str]) -> tuple[str, list[str]]:
    if status not in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}:
        return status, failures
    identity = score.get("scored_identity") or {}
    if identity.get("version_binding_certifiable") is True:
        return status, failures
    return "BLOCKED_EXTERNAL", [
        *failures,
        "model_version_binding_not_certifiable:"
        f"policy={identity.get('observed_version_policy')}:observed={identity.get('observed_version')}",
    ]


def auto_paths(score_path: Path) -> dict[str, Path] | None:
    try:
        score = json.loads(Path(score_path).read_text(encoding="utf-8"))
        paths = score.get("input_paths")
        required = ["cases", "verdicts", "source_units", "reference", "gold_manifest", "registry"]
        if not isinstance(paths, dict) or any(not paths.get(k) for k in required):
            return None
        return {k: Path(paths[k]) for k in required}
    except Exception:
        return None


def recompute_and_verify(score_path: Path, paths: dict[str, Path]) -> tuple[dict, dict[str, Any]]:
    stored = json.loads(Path(score_path).read_text(encoding="utf-8"))
    if stored.get("role") != "COLD_AUDIT":
        raise ValueError(f"cold_score_role_invalid:{stored.get('role')}")
    identity = stored.get("scored_identity")
    if not isinstance(identity, dict):
        raise ValueError("cold_score_identity_missing")
    provider = str(identity.get("provider") or "")
    model = str(identity.get("model_alias") or stored.get("model") or "")
    version = str(identity.get("observed_version") or "")
    if not provider or not model or not version:
        raise ValueError("cold_score_identity_incomplete")
    recomputed = build_report_from_artifacts(
        cases_path=paths["cases"], verdicts_path=paths["verdicts"],
        source_units_path=paths["source_units"], reference_path=paths["reference"],
        gold_manifest_path=paths["gold_manifest"], registry_path=paths["registry"],
        provider=provider, model=model, observed_version=version,
    )
    replay = verify_replay_equivalence(stored, recomputed)
    return recomputed, {
        "verification_schema_version": "hermes-cold-audit-certification-input-verification-1.1",
        "recomputation_verified": True,
        "cases_sha256": recomputed["cold_benchmark_cases_sha256"],
        "verdicts_sha256": recomputed["cold_benchmark_verdicts_sha256"],
        **replay,
    }


def build_entry(score: dict, status: str, failures: list[str], verification: dict,
                *, units_in_scope: list[str]) -> dict[str, Any]:
    projection = scoring_authority_projection(score)
    return {
        "status": status,
        "decided_at_epoch": round(time.time(), 1),
        "decision_rule": DECISION_RULE,
        "measured_metrics": score["metrics"],
        "threshold_failures": failures,
        "limits": LIMITS,
        "gold_reference_sha256": score["reference_sha256"],
        "gold_manifest_sha256": score["gold_manifest_sha256"],
        "source_units_sha256": score["source_units_sha256"],
        # Shared lifecycle policy names this field candidate_file_sha256; for
        # COLD_AUDIT it identifies the deterministic benchmark-case artifact.
        "candidate_file_sha256": score["cold_benchmark_cases_sha256"],
        "candidate_semantic_sha256": score["candidate_semantic_sha256"],
        "cold_benchmark_cases_sha256": score["cold_benchmark_cases_sha256"],
        "cold_benchmark_verdicts_sha256": score["cold_benchmark_verdicts_sha256"],
        "gold_label": score["gold_label"],
        "units_in_scope": sorted(units_in_scope),
        "scored_identity": score["scored_identity"],
        "registry_authority_projection": projection,
        "registry_authority_sha256": scoring_authority_sha256(score),
        "benchmark_inputs_verified": bool(verification.get("recomputation_verified")),
    }


def risk_scopes(source_units_path: Path, manifest_path: Path) -> dict[tuple[str, str], list[str]]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    source_by_id, _ = load_source_units_verified(source_units_path, manifest)
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for uid, unit in source_by_id.items():
        risk = classify_source_unit(unit)
        grouped[(str(risk["work_class"]), str(risk["source_class"]))].append(uid)
    return {key: sorted(value) for key, value in sorted(grouped.items())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="certify_cold_audit")
    parser.add_argument("--score", required=True)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--cases")
    parser.add_argument("--verdicts")
    parser.add_argument("--source-units")
    parser.add_argument("--reference")
    parser.add_argument("--gold-manifest")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    explicit = [args.cases, args.verdicts, args.source_units, args.reference, args.gold_manifest]
    if any(explicit):
        if any(not x for x in explicit):
            print("explicit cold verification requires all benchmark artifact paths", file=sys.stderr)
            return 3
        paths = {
            "cases": Path(args.cases), "verdicts": Path(args.verdicts),
            "source_units": Path(args.source_units), "reference": Path(args.reference),
            "gold_manifest": Path(args.gold_manifest), "registry": Path(args.registry),
        }
    else:
        paths = auto_paths(Path(args.score))
        if paths is None:
            print("cold score is not self-describing and no complete verification inputs were supplied", file=sys.stderr)
            return 3
        paths["registry"] = Path(args.registry)

    try:
        score, verification = recompute_and_verify(Path(args.score), paths)
        status, failures = decide(score["metrics"], list(score["units_in_scope"]))
        status, failures = apply_version_gate(score, status, failures)
        identity = score["scored_identity"]
        provider = str(identity["provider"]); model = str(identity["model_alias"])
        scopes = risk_scopes(paths["source_units"], paths["gold_manifest"])
        if not scopes:
            raise ValueError("cold_certification_risk_scopes_empty")
        registry_path = Path(args.registry)
        registry = load_registry(registry_path)
        proposed: dict[str, dict[str, Any]] = {}
        key_statuses: dict[str, str] = {}
        for (work_class, source_class), units in scopes.items():
            key = "|".join([provider, model, "COLD_AUDIT", work_class, source_class, BENCHMARK_VERSION])
            entry = build_entry(score, status, failures, verification, units_in_scope=units)
            reason = recertification_block_reason(registry, key, entry)
            if reason and entry["status"] in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}:
                entry["status"] = "BLOCKED_EXTERNAL"
                entry["threshold_failures"] = [*entry["threshold_failures"], reason]
            proposed[key] = entry
            key_statuses[key] = str(entry["status"])

        authoritative = all(x in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"} for x in key_statuses.values())
        overall_status = status if authoritative else (
            "REJECTED" if any(x == "REJECTED" for x in key_statuses.values()) else "BLOCKED_EXTERNAL"
        )
        output = {
            "role": "COLD_AUDIT",
            "provider": provider,
            "model": model,
            "observed_version": identity.get("observed_version"),
            "status": overall_status,
            "base_decision_status": status,
            "failures": failures,
            "certification_keys": key_statuses,
            "risk_scopes": {f"{w}|{s}": units for (w, s), units in scopes.items()},
            "input_recomputation_verified": True,
            "verification": verification,
            "applied": bool(args.apply),
        }
        if args.apply:
            certs = registry.setdefault("certifications", {})
            if not isinstance(certs, dict):
                raise ValueError("registry_certifications_not_object")
            certs.update(proposed)
            registry["benchmark_version"] = BENCHMARK_VERSION
            registry.setdefault("role_status", {})["COLD_AUDIT"] = overall_status
            registry["cold_audit_claim_boundary"] = (
                "COLD_AUDIT qualification is one source-first skeptical-review benchmark projected only into the "
                "exact source W/S strata present in its source scope. Runtime still enforces source-unit membership, "
                "model-version authority, protected identity, and independence from active primary/blind groups. "
                "It does not certify PRIMARY/BLIND W3 extraction or canonical medical truth."
            )
            registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            print(f"registry updated: {registry_path}", file=sys.stderr)
            print("NOTE: registry is protected production state — rerun tests and certify-build after this change.", file=sys.stderr)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0 if overall_status in {"CERTIFIED", "CERTIFIED_WITH_LIMITS", "BLOCKED_EXTERNAL", "REJECTED"} else 4
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"cold certification refused: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
