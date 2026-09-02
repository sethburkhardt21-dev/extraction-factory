"""Dimension-complete W4 COLD_AUDIT certification.

This is the authoritative v1.25 cold-audit capability benchmark. It reuses the
source/gold/version/identity machinery from certify_cold_audit.py but expands the
challenge set across every applicable semantic dimension that runtime cold audit
is instructed to judge. A certificate is eligible only when every required
challenge dimension is present and every challenge in every required dimension is
classified correctly.

The older certify_cold_audit.py remains useful for descriptive diagnostics but
its legacy entries intentionally lack the v1.25 dimension-coverage authority
fields and therefore cannot satisfy runtime COLD_AUDIT certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from benchmarks_ext.certify_cold_audit import (  # noqa: E402
    BENCHMARK_VERSION,
    DEFAULT_REGISTRY,
    _build_provider,
    build_entries,
    challenge_semantic_sha256,
    decide,
    run_challenges,
    score_results,
    validate_gold_construction_disjointness,
)
from benchmarks_ext.cold_audit_challenge_dimensions import (  # noqa: E402
    applicable_dimensions,
    build_dimension_challenges,
    coverage_summary,
)
from benchmarks_ext.score_role import load_reference_verified, load_source_units_verified, sha256_file  # noqa: E402
from hermes_factory.certification_state import aggregate_role_status, recertification_block_reason  # noqa: E402
from hermes_factory.model_registry import load_registry, observed_version_is_certifiable, resolve_model_identity  # noqa: E402
from hermes_factory.risk import classify_source_unit  # noqa: E402

DIMENSION_SCHEMA = "hermes-cold-audit-dimensions-1.0"


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dimension_gate(coverage: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if coverage.get("all_required_dimensions_covered") is not True:
        failures.append(f"missing_required_dimensions:{coverage.get('missing_required_dimensions')}")
    required = coverage.get("required_dimensions")
    per_dimension = coverage.get("per_dimension")
    if not isinstance(required, list) or not required or not isinstance(per_dimension, dict):
        failures.append("dimension_coverage_structure_invalid")
        return False, failures
    for dim in required:
        row = per_dimension.get(dim)
        if not isinstance(row, dict) or int(row.get("challenge_count") or 0) < 1:
            failures.append(f"dimension_missing_challenges:{dim}")
            continue
        if row.get("accuracy") != 1.0:
            failures.append(f"dimension_accuracy_not_1:{dim}:{row.get('accuracy')}")
    return not failures, failures


def _results_payload(results: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="certify_cold_audit_dimensions")
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

        challenges = build_dimension_challenges(gold, source_by_id)
        required_dimensions = applicable_dimensions(gold)
        results = run_challenges(provider, challenges, source_by_id)
        metrics = score_results(results)
        coverage = coverage_summary(challenges, results, required_dimensions)
        coverage_ok, coverage_failures = dimension_gate(coverage)

        status, failures = decide(
            metrics,
            version_certifiable=version_certifiable,
            version_authority_verified=version_authority_verified,
        )
        failures = [*failures, *coverage_failures]
        if not coverage_ok and status in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}:
            status = "REJECTED"

        results_out = Path(args.results_out).resolve()
        results_out.parent.mkdir(parents=True, exist_ok=True)
        results_payload = _results_payload(results)
        results_out.write_text(results_payload, encoding="utf-8")
        results_sha = hashlib.sha256(results_payload.encode("utf-8")).hexdigest()
        semantic_sha = challenge_semantic_sha256(challenges, results)
        coverage_sha = canonical_json_sha256(coverage)
        source_classes = [str(classify_source_unit(u)["source_class"]) for u in source_by_id.values()]

        entries = build_entries(
            registry=registry,
            identity=identity,
            observed_version=observed_version,
            metrics=metrics,
            results_sha256=results_sha,
            semantic_sha256=semantic_sha,
            reference_sha256=reference_sha,
            gold_manifest_sha256=sha256_file(manifest_path),
            source_units_sha256=source_units_sha,
            units_in_scope=sorted(source_by_id),
            source_classes=source_classes,
            status=status,
            failures=failures,
        )
        for entry in entries.values():
            entry["cold_audit_dimension_schema"] = DIMENSION_SCHEMA
            entry["cold_audit_dimension_coverage"] = coverage
            entry["cold_audit_dimension_coverage_sha256"] = coverage_sha
            entry["cold_audit_all_required_dimensions_covered"] = coverage.get("all_required_dimensions_covered") is True
            entry["cold_audit_all_required_dimensions_perfect"] = coverage_ok

        reactivation_blocks = {
            key: reason
            for key, entry in entries.items()
            if (reason := recertification_block_reason(registry, key, entry)) is not None
        }
        report = {
            "schema_version": "hermes-cold-audit-certification-1.2",
            "dimension_schema": DIMENSION_SCHEMA,
            "benchmark_version": BENCHMARK_VERSION,
            "status": status,
            "failures": failures,
            "metrics": metrics,
            "dimension_coverage": coverage,
            "dimension_coverage_sha256": coverage_sha,
            "challenge_count": len(challenges),
            "challenge_results_sha256": results_sha,
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
                "Passing proves perfect classification on every applicable bounded cold-audit challenge dimension "
                "for this exact governed pilot and immutable model version. It does not prove universal clinical correctness."
            ),
        }
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        if args.apply:
            if status != "CERTIFIED_WITH_LIMITS":
                print(json.dumps(report, indent=2))
                print("refusing --apply without dimension-complete provider-verified cold-audit benchmark", file=sys.stderr)
                return 6
            if reactivation_blocks:
                print(json.dumps(report, indent=2))
                print("refusing --apply because prior lifecycle invalidation blocks this benchmark evidence", file=sys.stderr)
                return 7
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
                " COLD_AUDIT W4 runtime authority requires the v1.25 dimension-complete source-first challenge benchmark, "
                "gold-family disjointness, and provider-verified immutable model version."
            ).strip()
            registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
            print(f"registry updated: {registry_path}")
            print("NOTE: registry is protected production state — rerun tests and certify-build after this change.")

        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, KeyError, json.JSONDecodeError, OSError, RuntimeError) as exc:
        print(f"dimension-complete cold-audit certification failed: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
