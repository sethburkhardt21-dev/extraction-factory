"""Dimension-aware COLD_AUDIT benchmark and certification authority.

The runtime cold auditor is instructed to judge source support, unsupported
additions/atomicity, numeric preservation, negation, qualifier strength, and
relationship direction. Certification therefore records which of those dimensions
were actually challenged and requires perfect classification on every applicable,
constructible dimension in the governed pilot.

This remains bounded evidence: a passing model is CERTIFIED_WITH_LIMITS only for
the exact source/model-version/source-class scope recorded in the registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from benchmarks_ext.cold_audit_challenge_dimensions import (  # noqa: E402
    applicable_dimensions,
    build_dimension_challenges,
    coverage_summary,
)
from benchmarks_ext.replay_authority import scoring_authority_projection, scoring_authority_sha256  # noqa: E402
from benchmarks_ext.score_role import load_reference_verified, load_source_units_verified, sha256_file  # noqa: E402
from hermes_factory.certification_state import aggregate_role_status, recertification_block_reason  # noqa: E402
from hermes_factory.cold_audit_semantic import COLD_AUDIT_INSTRUCTIONS, _normalize_verdict  # noqa: E402
from hermes_factory.hashing import sha256_json, sha256_text  # noqa: E402
from hermes_factory.model_registry import (  # noqa: E402
    certification_key,
    load_registry,
    observed_version_is_certifiable,
    resolve_model_identity,
)
from hermes_factory.providers.command import JSONCommandProvider  # noqa: E402
from hermes_factory.risk import classify_source_unit  # noqa: E402
from providers_ext.ollama_digest_guard import normalize_host, resolve_digest  # noqa: E402

BENCHMARK_VERSION = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"
DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"
OLLAMA_GUARD = FACTORY_ROOT / "providers_ext" / "ollama_digest_guard.py"
COVERAGE_SCHEMA = "hermes-cold-audit-dimension-coverage-1.0"
REPORT_SCHEMA = "hermes-cold-audit-certification-1.2"

LIMITS = [
    "COLD_AUDIT challenge corpus is the governed eight-unit Machines/Dorsch pilot only",
    "positive controls are mechanically checked source-first gold; negatives are deterministic source-bound mutations",
    "dimension coverage is explicit; unconstructible/non-applicable dimensions are not silently claimed as measured",
    "cold auditor must be disjoint from all three frozen gold-construction independence groups",
    "all challenged dimensions require 100% classification accuracy, but this does not prove full-corpus or clinical correctness",
    "certification is role=W4 and exact source/model-version/registry-identity bound",
    "automatic applied version authority is currently implemented only for digest-guarded Ollama models",
]


def validate_gold_construction_disjointness(manifest: dict, identity: dict) -> list[str]:
    groups = manifest.get("gold_construction_independence_groups")
    if not isinstance(groups, list) or len(groups) < 3:
        raise ValueError("cold_audit_gold_construction_groups_missing_or_incomplete")
    if any(not isinstance(x, str) or not x.strip() for x in groups):
        raise ValueError("cold_audit_gold_construction_group_invalid")
    normalized = [x.strip() for x in groups]
    if len(set(normalized)) != len(normalized):
        raise ValueError("cold_audit_gold_construction_groups_not_distinct")
    auditor_group = str(identity.get("independence_group") or "").strip()
    if not auditor_group:
        raise ValueError("cold_audit_identity_missing_independence_group")
    if auditor_group in set(normalized):
        raise ValueError(f"cold_audit_gold_construction_contamination:{auditor_group}")
    return sorted(normalized)


def build_challenges(gold: list[dict], source_by_id: dict) -> list[dict]:
    """Canonical v1.25 challenge generator retained under the historical API name."""
    return build_dimension_challenges(gold, source_by_id)


def build_request(challenge: dict, unit: Any, run_id: str) -> dict:
    return {
        "request_schema_version": "hermes-worker-request-1.1",
        "task_role": "COLD_AUDIT",
        "work_class": "W4",
        "source_class": str(classify_source_unit(unit)["source_class"]),
        "capsule_id": "COLD-AUDIT-CERTIFICATION",
        "run_id": run_id,
        "source_unit": unit.to_dict(),
        "audit_target": {
            "candidate_id": challenge["challenge_id"],
            "proposition": challenge["proposition"],
            "evidence": challenge["evidence"],
            "polarity": "UNSPECIFIED",
            "certainty": "UNSPECIFIED",
            "origin_pass": "CERTIFICATION_CHALLENGE",
        },
        "task_instructions": COLD_AUDIT_INSTRUCTIONS,
        "output_schema": {"type": "object", "required": ["verdict"]},
        "provider_constraints": {"canonicalization_allowed": False},
    }


def run_challenges(provider: JSONCommandProvider, challenges: list[dict], source_by_id: dict) -> list[dict]:
    run_id = "COLD-CERT-" + sha256_text(str(time.time_ns()))[:16]
    out: list[dict] = []
    for challenge in challenges:
        unit = source_by_id[challenge["source_unit_id"]]
        request = build_request(challenge, unit, run_id)
        record = {
            "challenge_id": challenge["challenge_id"],
            "source_unit_id": challenge["source_unit_id"],
            "mutation": challenge["mutation"],
            "dimension": challenge.get("dimension"),
            "expected_supported": challenge["expected_supported"],
            "request_sha256": sha256_json(request),
        }
        try:
            raw = provider.execute(request)
            verdict = _normalize_verdict(raw)
            record["actual_supported"] = verdict["supported"]
            record["correct"] = verdict["supported"] is challenge["expected_supported"]
            record["verdict"] = verdict
            record["output_sha256"] = sha256_json(raw)
            if isinstance(raw, dict) and raw.get("provider_receipt") is not None:
                record["provider_receipt"] = raw["provider_receipt"]
        except Exception as exc:
            record["correct"] = False
            record["error"] = f"{type(exc).__name__}:{exc}"[:2000]
        out.append(record)
    return out


def score_results(results: list[dict], coverage: dict | None = None) -> dict:
    positives = [r for r in results if r.get("expected_supported") is True]
    negatives = [r for r in results if r.get("expected_supported") is False]
    errors = [r for r in results if r.get("error")]
    tp = sum(1 for r in positives if r.get("actual_supported") is True and r.get("correct") is True)
    tn = sum(1 for r in negatives if r.get("actual_supported") is False and r.get("correct") is True)
    metrics = {
        "positive_control_count": len(positives),
        "negative_control_count": len(negatives),
        "positive_controls_correct": tp,
        "negative_controls_correct": tn,
        "error_count": len(errors),
        "positive_control_accuracy": tp / len(positives) if positives else None,
        "injected_error_rejection_accuracy": tn / len(negatives) if negatives else None,
        "all_challenges_correct": bool(results) and not errors and all(r.get("correct") is True for r in results),
    }
    if coverage is not None:
        metrics["dimension_coverage"] = coverage
    return metrics


def decide(metrics: dict, *, version_certifiable: bool, version_authority_verified: bool = True) -> tuple[str, list[str]]:
    failures: list[str] = []
    if metrics.get("positive_control_count", 0) < 1 or metrics.get("negative_control_count", 0) < 1:
        failures.append("challenge_classes_missing")
    if metrics.get("error_count") != 0:
        failures.append(f"provider_or_schema_errors:{metrics.get('error_count')}")
    if metrics.get("positive_control_accuracy") != 1.0:
        failures.append(f"positive_control_accuracy_not_1:{metrics.get('positive_control_accuracy')}")
    if metrics.get("injected_error_rejection_accuracy") != 1.0:
        failures.append(f"injected_error_rejection_accuracy_not_1:{metrics.get('injected_error_rejection_accuracy')}")

    coverage = metrics.get("dimension_coverage")
    if coverage is not None:
        if not isinstance(coverage, dict) or coverage.get("all_required_dimensions_covered") is not True:
            failures.append(f"required_dimension_coverage_incomplete:{(coverage or {}).get('missing_required_dimensions')}")
        per_dimension = coverage.get("per_dimension") if isinstance(coverage, dict) else None
        if not isinstance(per_dimension, dict):
            failures.append("dimension_accuracy_missing")
        else:
            for dimension in coverage.get("required_dimensions", []):
                node = per_dimension.get(dimension)
                if not isinstance(node, dict) or node.get("challenge_count", 0) < 1:
                    failures.append(f"dimension_not_challenged:{dimension}")
                elif node.get("accuracy") != 1.0:
                    failures.append(f"dimension_accuracy_not_1:{dimension}:{node.get('accuracy')}")
    if failures:
        return "REJECTED", failures
    if not version_certifiable or not version_authority_verified:
        return "BLOCKED_EXTERNAL", ["model_version_binding_not_provider_verified"]
    return "CERTIFIED_WITH_LIMITS", []


def _results_sha256(results: list[dict]) -> str:
    payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in results)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def challenge_semantic_projection(challenges: list[dict], results: list[dict]) -> list[dict]:
    result_by_id = {str(r.get("challenge_id") or ""): r for r in results}
    expected_ids = {str(c.get("challenge_id") or "") for c in challenges}
    if set(result_by_id) != expected_ids:
        raise ValueError("cold_audit_challenge_result_set_mismatch")
    projected: list[dict] = []
    for challenge in challenges:
        cid = str(challenge["challenge_id"])
        result = result_by_id[cid]
        error = str(result.get("error") or "")
        projected.append({
            "challenge_id": cid,
            "source_unit_id": str(challenge["source_unit_id"]),
            "mutation": str(challenge["mutation"]),
            "dimension": str(challenge.get("dimension") or "UNKNOWN"),
            "proposition": str(challenge["proposition"]),
            "evidence": str(challenge["evidence"]),
            "expected_supported": bool(challenge["expected_supported"]),
            "actual_supported": result.get("actual_supported") if type(result.get("actual_supported")) is bool else None,
            "correct": result.get("correct") is True,
            "error_type": error.split(":", 1)[0] if error else None,
        })
    return sorted(projected, key=lambda r: r["challenge_id"])


def challenge_semantic_sha256(challenges: list[dict], results: list[dict]) -> str:
    payload = json.dumps(
        challenge_semantic_projection(challenges, results),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def coverage_sha256(coverage: dict) -> str:
    payload = json.dumps(coverage, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_entries(*, registry: dict, identity: dict, observed_version: str, metrics: dict,
                  results_sha256: str, semantic_sha256: str,
                  reference_sha256: str, gold_manifest_sha256: str,
                  source_units_sha256: str, units_in_scope: list[str], source_classes: list[str],
                  status: str, failures: list[str]) -> dict[str, dict]:
    scored_identity = dict(identity)
    scored_identity["observed_version"] = observed_version
    scored_identity["version_binding_certifiable"] = observed_version_is_certifiable(
        str(identity.get("observed_version_policy") or ""), observed_version
    )
    score_like = {"scored_identity": scored_identity, "primary_baseline_identity": None}
    projection = scoring_authority_projection(score_like)
    authority_sha = scoring_authority_sha256(score_like)
    coverage = metrics.get("dimension_coverage")
    if not isinstance(coverage, dict):
        raise ValueError("cold_audit_dimension_coverage_missing")
    coverage_hash = coverage_sha256(coverage)
    entries: dict[str, dict] = {}
    for source_class in sorted(set(source_classes)):
        key = certification_key(
            str(identity["provider"]), str(identity["model_alias"]), "COLD_AUDIT",
            "W4", source_class, BENCHMARK_VERSION,
        )
        entries[key] = {
            "status": status,
            "decided_at_epoch": round(time.time(), 1),
            "decision_rule": "CERT-COLD-AUDIT-W4-DIMENSIONAL-STRICT",
            "measured_metrics": metrics,
            "threshold_failures": failures,
            "limits": LIMITS,
            "gold_reference_sha256": reference_sha256,
            "gold_manifest_sha256": gold_manifest_sha256,
            "source_units_sha256": source_units_sha256,
            "candidate_file_sha256": results_sha256,
            "candidate_semantic_sha256": semantic_sha256,
            "gold_label": "MECHANICALLY_CHECKED",
            "units_in_scope": sorted(units_in_scope),
            "scored_identity": scored_identity,
            "registry_authority_projection": projection,
            "registry_authority_sha256": authority_sha,
            "benchmark_inputs_verified": True,
            "cold_audit_dimension_coverage_schema": COVERAGE_SCHEMA,
            "cold_audit_dimension_coverage": coverage,
            "cold_audit_dimension_coverage_sha256": coverage_hash,
        }
    return entries


def _build_provider(args: argparse.Namespace, identity: dict) -> tuple[JSONCommandProvider, str, bool]:
    provider_name = str(identity["provider"]).upper()
    if provider_name == "OLLAMA":
        if args.provider_command:
            raise ValueError("ollama_provider_command_not_accepted:guarded_command_is_constructed_by_certifier")
        host = normalize_host(args.ollama_host)
        measured = resolve_digest(args.model, host, timeout=max(1, min(args.timeout, 30)))
        if args.observed_version and args.observed_version.strip().lower() != measured.lower():
            raise ValueError(f"ollama_observed_version_assertion_mismatch:{args.observed_version}!={measured}")
        command = [
            sys.executable, "-B", str(OLLAMA_GUARD),
            "--model", args.model,
            "--expected-digest", measured,
            "--timeout", str(max(1, args.timeout)),
            "--ollama-host", host,
            "--ollama-keep-alive", args.ollama_keep_alive,
        ]
        if args.ollama_think is not None:
            command += ["--ollama-think", args.ollama_think]
        provider = JSONCommandProvider(
            command,
            provider=provider_name, model_alias=str(identity["model_alias"]),
            underlying_family=str(identity["underlying_family"]), observed_version=measured,
            role="COLD_AUDIT", timeout_seconds=max(1, args.timeout) * 2 + 120,
            network_required=False, empirical_semantic_model=True,
        )
        return provider, measured, True

    if not args.provider_command:
        raise ValueError("non_ollama_provider_command_required_for_descriptive_benchmark")
    observed = args.observed_version.strip() if args.observed_version and args.observed_version.strip() else f"UNPINNED_ALIAS:{args.model}"
    provider = JSONCommandProvider(
        args.provider_command,
        provider=provider_name, model_alias=str(identity["model_alias"]),
        underlying_family=str(identity["underlying_family"]), observed_version=observed,
        role="COLD_AUDIT", timeout_seconds=max(1, args.timeout), network_required=True,
        empirical_semantic_model=True,
    )
    return provider, observed, False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="certify_cold_audit")
    parser.add_argument("--source-units", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--gold-manifest", required=True)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--observed-version", help="assertion only for Ollama; never its authority source")
    parser.add_argument("--provider-command", help="non-Ollama JSON stdin/stdout command; descriptive benchmark only")
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-think", choices=["false", "low", "medium", "high"])
    parser.add_argument("--ollama-keep-alive", default="30m")
    parser.add_argument("--out", required=True, help="benchmark report JSON")
    parser.add_argument("--results-out", required=True, help="per-challenge JSONL")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest_path = Path(args.gold_manifest).resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("benchmark_version") != BENCHMARK_VERSION:
            raise ValueError(f"benchmark_version_invalid:{manifest.get('benchmark_version')}")
        if manifest.get("gold_label") != "MECHANICALLY_CHECKED":
            raise ValueError(f"gold_label_invalid:{manifest.get('gold_label')}")
        source_by_id, source_units_sha = load_source_units_verified(Path(args.source_units), manifest)
        gold, reference_sha = load_reference_verified(Path(args.reference), manifest_path, manifest, source_by_id)
        registry_path = Path(args.registry).resolve()
        registry = load_registry(registry_path)
        identity = resolve_model_identity(registry, args.provider, args.model)
        if identity.get("empirical_semantic_model") is not True:
            raise ValueError("cold_audit_model_not_empirical")
        gold_groups = validate_gold_construction_disjointness(manifest, identity)

        provider, observed_version, version_authority_verified = _build_provider(args, identity)
        version_certifiable = observed_version_is_certifiable(
            str(identity.get("observed_version_policy") or ""), observed_version
        )
        challenges = build_challenges(gold, source_by_id)
        results = run_challenges(provider, challenges, source_by_id)
        required_dimensions = applicable_dimensions(gold)
        coverage = coverage_summary(challenges, results, required_dimensions)
        metrics = score_results(results, coverage)
        status, failures = decide(
            metrics,
            version_certifiable=version_certifiable,
            version_authority_verified=version_authority_verified,
        )

        results_out = Path(args.results_out).resolve()
        results_out.parent.mkdir(parents=True, exist_ok=True)
        results_payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in results)
        results_out.write_text(results_payload, encoding="utf-8")
        measured_results_sha = hashlib.sha256(results_payload.encode("utf-8")).hexdigest()
        if measured_results_sha != _results_sha256(results):
            raise ValueError("cold_audit_results_hash_internal_mismatch")
        semantic_sha = challenge_semantic_sha256(challenges, results)
        source_classes = [str(classify_source_unit(u)["source_class"]) for u in source_by_id.values()]
        entries = build_entries(
            registry=registry, identity=identity, observed_version=observed_version,
            metrics=metrics, results_sha256=measured_results_sha, semantic_sha256=semantic_sha,
            reference_sha256=reference_sha, gold_manifest_sha256=sha256_file(manifest_path),
            source_units_sha256=source_units_sha, units_in_scope=sorted(source_by_id),
            source_classes=source_classes, status=status, failures=failures,
        )
        reactivation_blocks = {
            key: reason for key, entry in entries.items()
            if (reason := recertification_block_reason(registry, key, entry)) is not None
        }
        report = {
            "schema_version": REPORT_SCHEMA,
            "benchmark_version": BENCHMARK_VERSION,
            "status": status,
            "failures": failures,
            "metrics": metrics,
            "dimension_coverage": coverage,
            "dimension_coverage_sha256": coverage_sha256(coverage),
            "challenge_count": len(challenges),
            "challenge_results_sha256": measured_results_sha,
            "challenge_semantic_sha256": semantic_sha,
            "source_units_sha256": source_units_sha,
            "reference_sha256": reference_sha,
            "gold_manifest_sha256": sha256_file(manifest_path),
            "gold_construction_independence_groups": gold_groups,
            "cold_auditor_independence_group": identity["independence_group"],
            "observed_version": observed_version,
            "version_authority_verified": version_authority_verified,
            "scored_identity": next(iter(entries.values()))["scored_identity"] if entries else None,
            "registry_keys": sorted(entries),
            "reactivation_blocks": reactivation_blocks,
            "applied": bool(args.apply and status == "CERTIFIED_WITH_LIMITS" and not reactivation_blocks),
            "claim_boundary": (
                "Passing proves perfect classification only across the explicitly recorded applicable challenge dimensions "
                "on this exact governed pilot, disjoint from its gold-construction families, on a provider-verified immutable model version."
            ),
        }
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if args.apply:
            if status != "CERTIFIED_WITH_LIMITS":
                print(json.dumps(report, indent=2)); print("refusing --apply without passing provider-verified multidimensional cold-audit benchmark", file=sys.stderr); return 6
            if reactivation_blocks:
                print(json.dumps(report, indent=2)); print("refusing --apply because prior lifecycle invalidation blocks this benchmark evidence", file=sys.stderr); return 7
            registry["benchmark_version"] = BENCHMARK_VERSION
            certs = registry.setdefault("certifications", {})
            if not isinstance(certs, dict):
                raise ValueError("registry_certifications_not_object")
            certs.update(entries)
            role_status = registry.setdefault("role_status", {})
            if not isinstance(role_status, dict):
                raise ValueError("registry_role_status_not_object")
            role_status["COLD_AUDIT_W4"] = aggregate_role_status(
                certs, role="COLD_AUDIT", work_class="W4", benchmark_version=BENCHMARK_VERSION
            )
            registry["claim_boundary"] = (
                str(registry.get("claim_boundary") or "") +
                " COLD_AUDIT W4 may be CERTIFIED_WITH_LIMITS only through the multidimensional source-first challenge benchmark with explicit coverage receipt, disjoint gold-construction groups, and provider-verified immutable version authority."
            ).strip()
            registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
            print(f"registry updated: {registry_path}")
            print("NOTE: registry is protected production state — rerun tests and certify-build after this change.")
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, KeyError, json.JSONDecodeError, OSError, RuntimeError) as exc:
        print(f"cold-audit certification failed: {exc}", file=sys.stderr)
        return 4
