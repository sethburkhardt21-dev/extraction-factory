"""Source-first qualification benchmark for the independent COLD_AUDIT role.

The live factory requires a certified independent cold auditor before a clean
semantic audit can satisfy readiness. This benchmark makes that gate reachable
without weakening it. It derives supported cases from the frozen source-first
gold and unsupported cases from deterministic, auditable mutations of those
same source-bound assertions. No outside medical truth is introduced.

The score is descriptive until `certify_cold_audit.py` independently replays the
case/verdict artifacts and applies the threshold policy. The auditor must also be
from a protected-registry independence group that did not construct the gold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from benchmarks_ext.replay_authority import scoring_authority_projection  # noqa: E402
from benchmarks_ext.score_role import (  # noqa: E402
    load_reference_verified,
    load_source_units_verified,
    sha256_file,
    sha256_text,
)
from hermes_factory.cold_audit_semantic import COLD_AUDIT_INSTRUCTIONS, _normalize_verdict  # noqa: E402
from hermes_factory.model_registry import (  # noqa: E402
    load_registry,
    observed_version_is_certifiable,
    resolve_model_identity,
)
from hermes_factory.providers.command import JSONCommandProvider  # noqa: E402

SCORE_SCHEMA = "hermes-cold-audit-score-1.0"
CASE_SCHEMA = "hermes-cold-audit-case-1.0"
VERDICT_SCHEMA = "hermes-cold-audit-verdict-1.0"
BENCHMARK_VERSION = "MACHINES_P0299_P0301_SOURCE_FIRST_v1"
DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"
NUMERIC_RE = re.compile(r"(?<![A-Za-z0-9_.])(\d+(?:\.\d+)?)(?![A-Za-z0-9_.])")
QUALIFIER_RE = re.compile(r"\b(may|might|can|could|usually|typically|approximately|about|roughly)\b", re.I)
RELATION_REPLACEMENTS = (
    (re.compile(r"\bincreases?\b", re.I), "decreases"),
    (re.compile(r"\bdecreases?\b", re.I), "increases"),
    (re.compile(r"\bhigher\b", re.I), "lower"),
    (re.compile(r"\blower\b", re.I), "higher"),
    (re.compile(r"\bgreater\b", re.I), "less"),
    (re.compile(r"\bless\b", re.I), "greater"),
)


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows), encoding="utf-8")


def _ratio(num: int, den: int) -> dict[str, Any]:
    return {"numerator": num, "denominator": den, "value": round(num / den, 4) if den else None}


def _numeric_mutation(text: str) -> str | None:
    match = NUMERIC_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    try:
        value = float(raw)
    except ValueError:
        return None
    if "." in raw:
        decimals = len(raw.split(".", 1)[1])
        replacement = f"{value + 1.0:.{decimals}f}"
    else:
        replacement = str(int(value) + 1)
    if replacement == raw:
        return None
    return text[:match.start(1)] + replacement + text[match.end(1):]


def mutation_options(proposition: str) -> list[tuple[str, str]]:
    """Return deterministic unsupported mutations without changing evidence bytes."""
    out: list[tuple[str, str]] = []
    numeric = _numeric_mutation(proposition)
    if numeric and numeric != proposition:
        out.append(("NUMERIC_VALUE_CHANGED", numeric))

    for pattern, replacement in RELATION_REPLACEMENTS:
        if pattern.search(proposition):
            mutated = pattern.sub(replacement, proposition, count=1)
            if mutated != proposition:
                out.append(("RELATIONSHIP_REVERSED", mutated))
            break

    qualifier = QUALIFIER_RE.search(proposition)
    if qualifier:
        mutated = (proposition[:qualifier.start()] + proposition[qualifier.end():]).replace("  ", " ").strip()
        if mutated and mutated != proposition:
            out.append(("QUALIFIER_DROPPED", mutated))

    if re.search(r"\bnot\b", proposition, re.I):
        mutated = re.sub(r"\bnot\b\s*", "", proposition, count=1, flags=re.I).replace("  ", " ").strip()
        if mutated and mutated != proposition:
            out.append(("NEGATION_FLIPPED", mutated))
    else:
        out.append(("NEGATION_INJECTED", "It is not true that " + proposition[0].lower() + proposition[1:] if proposition else proposition))

    addition = proposition.rstrip()
    if addition:
        if addition[-1] not in ".!?":
            addition += "."
        addition += " This relationship is universal and has no exceptions."
        out.append(("UNSUPPORTED_ADDITION", addition))

    dedup: list[tuple[str, str]] = []
    seen = set()
    for kind, value in out:
        key = (kind, value)
        if key not in seen and value and value != proposition:
            dedup.append(key)
            seen.add(key)
    return dedup


def _case_id(source_unit_id: str, gold_id: str, expected_supported: bool, mutation_type: str, proposition: str, evidence: str) -> str:
    raw = "|".join([source_unit_id, gold_id, str(expected_supported), mutation_type, proposition, evidence])
    return "COLDCASE-" + sha256_text(raw)[:24]


def build_cases(gold: list[dict[str, Any]], *, max_positive: int = 32, max_negative: int = 32) -> list[dict[str, Any]]:
    if max_positive < 1 or max_negative < 1:
        raise ValueError("cold_case_limits_must_be_positive")
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in gold:
        by_unit[str(row["source_unit_id"])].append(row)
    if max_positive < len(by_unit):
        raise ValueError(f"max_positive_must_cover_all_source_units:{max_positive}<{len(by_unit)}")

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    # First guarantee at least one supported case from every governed source unit.
    for uid in sorted(by_unit):
        row = min(by_unit[uid], key=lambda r: sha256_text(str(r.get("gold_id") or "")))
        selected.append(row); selected_ids.add(str(row["gold_id"]))
    remaining = sorted(
        [r for r in gold if str(r.get("gold_id")) not in selected_ids],
        key=lambda r: sha256_text(str(r.get("gold_id") or "")),
    )
    selected.extend(remaining[:max(0, max_positive - len(selected))])

    cases: list[dict[str, Any]] = []
    for row in selected:
        uid = str(row["source_unit_id"]); gid = str(row["gold_id"])
        proposition = str(row["proposition"]); evidence = str(row["evidence"])
        cases.append({
            "case_schema_version": CASE_SCHEMA,
            "case_id": _case_id(uid, gid, True, "SOURCE_FIRST_GOLD_SUPPORTED", proposition, evidence),
            "source_unit_id": uid,
            "gold_id": gid,
            "expected_supported": True,
            "mutation_type": "SOURCE_FIRST_GOLD_SUPPORTED",
            "proposition": proposition,
            "evidence": evidence,
            "polarity": "AFFIRMATIVE",
            "certainty": "ASSERTED",
        })

    mutation_pool: list[dict[str, Any]] = []
    for row in selected:
        uid = str(row["source_unit_id"]); gid = str(row["gold_id"])
        evidence = str(row["evidence"]); proposition = str(row["proposition"])
        for kind, mutated in mutation_options(proposition):
            mutation_pool.append({
                "case_schema_version": CASE_SCHEMA,
                "case_id": _case_id(uid, gid, False, kind, mutated, evidence),
                "source_unit_id": uid,
                "gold_id": gid,
                "expected_supported": False,
                "mutation_type": kind,
                "proposition": mutated,
                "evidence": evidence,
                "polarity": "NEGATIVE" if kind in {"NEGATION_INJECTED", "NEGATION_FLIPPED"} else "AFFIRMATIVE",
                "certainty": "ASSERTED",
            })

    # Guarantee one negative from every source unit when possible.
    negatives: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()
    for uid in sorted(by_unit):
        options = [x for x in mutation_pool if x["source_unit_id"] == uid]
        if options:
            row = min(options, key=lambda x: sha256_text(str(x["case_id"])))
            negatives.append(row); chosen_ids.add(str(row["case_id"]))
    if max_negative < len(negatives):
        raise ValueError(f"max_negative_must_cover_all_source_units:{max_negative}<{len(negatives)}")

    # Then guarantee mutation-type diversity before hash-filling the budget.
    for kind in sorted({str(x["mutation_type"]) for x in mutation_pool}):
        if len(negatives) >= max_negative:
            break
        if any(x["mutation_type"] == kind for x in negatives):
            continue
        options = [x for x in mutation_pool if x["mutation_type"] == kind and x["case_id"] not in chosen_ids]
        if options:
            row = min(options, key=lambda x: sha256_text(str(x["case_id"])))
            negatives.append(row); chosen_ids.add(str(row["case_id"]))

    remainder = sorted(
        [x for x in mutation_pool if x["case_id"] not in chosen_ids],
        key=lambda x: sha256_text(str(x["case_id"])),
    )
    negatives.extend(remainder[:max(0, max_negative - len(negatives))])
    cases.extend(negatives)
    return sorted(cases, key=lambda x: str(x["case_id"]))


def cold_case_semantic_sha256(cases: list[dict[str, Any]]) -> str:
    projection = [{
        "source_unit_id": str(x.get("source_unit_id") or ""),
        "gold_id": str(x.get("gold_id") or ""),
        "expected_supported": bool(x.get("expected_supported")),
        "mutation_type": str(x.get("mutation_type") or ""),
        "proposition": str(x.get("proposition") or ""),
        "evidence": str(x.get("evidence") or ""),
    } for x in cases]
    return _canonical_sha(sorted(projection, key=lambda x: _canonical_sha(x)))


def validate_cases(cases: list[dict[str, Any]], source_by_id: dict, gold: list[dict[str, Any]]) -> None:
    if not cases:
        raise ValueError("cold_cases_empty")
    gold_by_id = {str(x.get("gold_id")): x for x in gold}
    seen: set[str] = set()
    positive_units: set[str] = set(); negative_units: set[str] = set()
    for case in cases:
        cid = str(case.get("case_id") or "")
        if not cid or cid in seen:
            raise ValueError(f"cold_case_id_missing_or_duplicate:{cid}")
        seen.add(cid)
        if case.get("case_schema_version") != CASE_SCHEMA:
            raise ValueError(f"cold_case_schema_invalid:{cid}")
        uid = str(case.get("source_unit_id") or "")
        unit = source_by_id.get(uid)
        if unit is None:
            raise ValueError(f"cold_case_unknown_source_unit:{cid}:{uid}")
        gid = str(case.get("gold_id") or "")
        gold_row = gold_by_id.get(gid)
        if gold_row is None or str(gold_row.get("source_unit_id")) != uid:
            raise ValueError(f"cold_case_gold_binding_invalid:{cid}:{gid}")
        evidence = str(case.get("evidence") or "")
        if not evidence or evidence not in unit.content or evidence != str(gold_row.get("evidence") or ""):
            raise ValueError(f"cold_case_evidence_invalid:{cid}")
        expected = case.get("expected_supported")
        if type(expected) is not bool:
            raise ValueError(f"cold_case_expected_supported_not_boolean:{cid}")
        proposition = str(case.get("proposition") or "")
        mutation_type = str(case.get("mutation_type") or "")
        expected_id = _case_id(uid, gid, expected, mutation_type, proposition, evidence)
        if cid != expected_id:
            raise ValueError(f"cold_case_id_mismatch:{cid}")
        if expected:
            positive_units.add(uid)
            if mutation_type != "SOURCE_FIRST_GOLD_SUPPORTED" or proposition != str(gold_row.get("proposition") or ""):
                raise ValueError(f"cold_positive_not_exact_gold:{cid}")
        else:
            negative_units.add(uid)
            if mutation_type == "SOURCE_FIRST_GOLD_SUPPORTED" or proposition == str(gold_row.get("proposition") or ""):
                raise ValueError(f"cold_negative_not_mutated:{cid}")
    all_units = set(source_by_id)
    if positive_units != all_units:
        raise ValueError(f"cold_positive_source_coverage_incomplete:{sorted(all_units-positive_units)}")
    if negative_units != all_units:
        raise ValueError(f"cold_negative_source_coverage_incomplete:{sorted(all_units-negative_units)}")


def build_request(case: dict[str, Any], unit: Any) -> dict[str, Any]:
    return {
        "request_schema_version": "hermes-worker-request-1.1",
        "task_role": "COLD_AUDIT",
        "work_class": "AUDIT",
        "source_class": "AUDIT",
        "capsule_id": "COLD-BENCHMARK",
        "run_id": "COLD-BENCHMARK",
        "source_unit": unit.to_dict(),
        "audit_target": {
            "candidate_id": case["case_id"],
            "proposition": case["proposition"],
            "evidence": case["evidence"],
            "polarity": case.get("polarity", "AFFIRMATIVE"),
            "certainty": case.get("certainty", "ASSERTED"),
            "origin_pass": "COLD_BENCHMARK",
        },
        "task_instructions": COLD_AUDIT_INSTRUCTIONS,
        "output_schema": {"type": "object", "required": ["verdict"]},
        "provider_constraints": {"canonicalization_allowed": False},
    }


def execute_cases(cases: list[dict[str, Any]], source_by_id: dict, provider: JSONCommandProvider) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        request = build_request(case, source_by_id[case["source_unit_id"]])
        row = {
            "verdict_schema_version": VERDICT_SCHEMA,
            "case_id": case["case_id"],
            "source_unit_id": case["source_unit_id"],
            "expected_supported": case["expected_supported"],
            "mutation_type": case["mutation_type"],
            "request_sha256": _canonical_sha(request),
        }
        try:
            output = provider.execute(request)
            verdict = _normalize_verdict(output)
            row["observed_supported"] = verdict["supported"]
            row["flags"] = verdict["flags"]
            row["rationale"] = verdict["rationale"]
            row["output_sha256"] = _canonical_sha(output)
            row["provider_receipt"] = output.get("provider_receipt") if isinstance(output, dict) else None
            row["correct"] = verdict["supported"] is case["expected_supported"]
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}:{exc}"[:2000]
            row["correct"] = False
        rows.append(row)
    return rows


def score_verdicts(cases: list[dict[str, Any]], verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    by_case = {str(x.get("case_id")): x for x in cases}
    if len(by_case) != len(cases):
        raise ValueError("cold_cases_duplicate_ids")
    verdict_map = {str(x.get("case_id")): x for x in verdicts}
    if len(verdict_map) != len(verdicts) or set(verdict_map) != set(by_case):
        raise ValueError("cold_verdict_case_set_mismatch")
    positive = negative = tp = tn = errors = 0
    mutation_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    source_units = set()
    for cid, case in by_case.items():
        row = verdict_map[cid]
        source_units.add(str(case["source_unit_id"]))
        if row.get("verdict_schema_version") != VERDICT_SCHEMA:
            raise ValueError(f"cold_verdict_schema_invalid:{cid}")
        if bool(row.get("expected_supported")) != bool(case["expected_supported"]):
            raise ValueError(f"cold_verdict_expected_label_mismatch:{cid}")
        error = bool(row.get("error"))
        if error:
            errors += 1
        observed = row.get("observed_supported")
        if not error and type(observed) is not bool:
            raise ValueError(f"cold_verdict_supported_not_boolean:{cid}")
        if case["expected_supported"]:
            positive += 1
            if not error and observed is True:
                tp += 1
        else:
            negative += 1
            kind = str(case["mutation_type"])
            mutation_totals[kind][1] += 1
            if not error and observed is False:
                tn += 1
                mutation_totals[kind][0] += 1
    correct = tp + tn
    total = positive + negative
    return {
        "supported_case_recall": _ratio(tp, positive),
        "unsupported_case_rejection": _ratio(tn, negative),
        "overall_accuracy": _ratio(correct, total),
        "provider_error_rate": _ratio(errors, total),
        "source_unit_coverage": {"covered": len(source_units), "total": len(source_units), "value": 1.0 if source_units else None},
        "case_counts": {"supported": positive, "unsupported": negative, "total": total},
        "mutation_rejection": {kind: _ratio(values[0], values[1]) for kind, values in sorted(mutation_totals.items())},
    }


def _scored_identity(registry: dict[str, Any], manifest: dict[str, Any], provider: str, model: str, observed_version: str) -> dict[str, Any]:
    identity = dict(resolve_model_identity(registry, provider.upper(), model))
    if identity.get("empirical_semantic_model") is not True:
        raise ValueError(f"cold_auditor_not_empirical:{provider}|{model}")
    gold_groups = manifest.get("gold_construction_independence_groups")
    if not isinstance(gold_groups, list) or not gold_groups:
        raise ValueError("gold_manifest_missing_construction_independence_groups")
    if str(identity.get("independence_group")) in set(map(str, gold_groups)):
        raise ValueError(f"cold_auditor_independence_group_authored_gold:{identity.get('independence_group')}")
    identity["observed_version"] = observed_version
    identity["version_binding_certifiable"] = observed_version_is_certifiable(
        str(identity.get("observed_version_policy") or ""), observed_version
    )
    return identity


def build_report_from_artifacts(*, cases_path: Path, verdicts_path: Path, source_units_path: Path,
                                reference_path: Path, gold_manifest_path: Path, registry_path: Path,
                                provider: str, model: str, observed_version: str) -> dict[str, Any]:
    manifest = json.loads(Path(gold_manifest_path).read_text(encoding="utf-8"))
    if manifest.get("benchmark_version") != BENCHMARK_VERSION:
        raise ValueError(f"benchmark_version_invalid:{manifest.get('benchmark_version')}")
    if manifest.get("gold_label") != "MECHANICALLY_CHECKED":
        raise ValueError(f"gold_label_invalid:{manifest.get('gold_label')}")
    source_by_id, source_units_sha = load_source_units_verified(source_units_path, manifest)
    gold, reference_sha = load_reference_verified(reference_path, gold_manifest_path, manifest, source_by_id)
    cases = _load_jsonl(cases_path); verdicts = _load_jsonl(verdicts_path)
    validate_cases(cases, source_by_id, gold)
    metrics = score_verdicts(cases, verdicts)
    registry = load_registry(registry_path)
    identity = _scored_identity(registry, manifest, provider, model, observed_version)
    report = {
        "score_schema_version": SCORE_SCHEMA,
        "role": "COLD_AUDIT",
        "model": model,
        "scored_identity": identity,
        "primary_baseline_identity": None,
        "benchmark_version": manifest["benchmark_version"],
        "gold_label": manifest["gold_label"],
        "reference_sha256": reference_sha,
        "source_units_sha256": source_units_sha,
        "gold_manifest_sha256": sha256_file(gold_manifest_path),
        "registry_sha256": sha256_file(registry_path),
        "candidate_file_sha256": sha256_file(cases_path),
        "candidate_semantic_sha256": cold_case_semantic_sha256(cases),
        "cold_benchmark_cases_sha256": sha256_file(cases_path),
        "cold_benchmark_verdicts_sha256": sha256_file(verdicts_path),
        "units_in_scope": sorted(source_by_id),
        "benchmark_inputs_verified": True,
        "input_paths": {
            "cases": str(Path(cases_path).resolve()),
            "verdicts": str(Path(verdicts_path).resolve()),
            "source_units": str(Path(source_units_path).resolve()),
            "reference": str(Path(reference_path).resolve()),
            "gold_manifest": str(Path(gold_manifest_path).resolve()),
            "registry": str(Path(registry_path).resolve()),
        },
        "metrics": metrics,
    }
    report["registry_authority_projection"] = scoring_authority_projection(report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cold_audit_score")
    parser.add_argument("--source-units", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--gold-manifest", required=True)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--command", required=True, help="JSON stdin/stdout semantic provider command")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--version", required=True, help="observed immutable model version/digest")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--max-positive", type=int, default=32)
    parser.add_argument("--max-negative", type=int, default=32)
    parser.add_argument("--cases-out", required=True)
    parser.add_argument("--verdicts-out", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(Path(args.gold_manifest).read_text(encoding="utf-8"))
        source_by_id, _ = load_source_units_verified(Path(args.source_units), manifest)
        gold, _ = load_reference_verified(Path(args.reference), Path(args.gold_manifest), manifest, source_by_id)
        cases = build_cases(gold, max_positive=args.max_positive, max_negative=args.max_negative)
        validate_cases(cases, source_by_id, gold)
        _write_jsonl(Path(args.cases_out), cases)
        registry = load_registry(Path(args.registry))
        identity = _scored_identity(registry, manifest, args.provider, args.model, args.version)
        provider = JSONCommandProvider(
            args.command,
            provider=args.provider.upper(),
            model_alias=args.model,
            underlying_family=str(identity["underlying_family"]),
            observed_version=args.version,
            role="COLD_AUDIT",
            timeout_seconds=args.timeout + 60,
            network_required=not args.local,
            empirical_semantic_model=True,
        )
        verdicts = execute_cases(cases, source_by_id, provider)
        _write_jsonl(Path(args.verdicts_out), verdicts)
        report = build_report_from_artifacts(
            cases_path=Path(args.cases_out), verdicts_path=Path(args.verdicts_out),
            source_units_path=Path(args.source_units), reference_path=Path(args.reference),
            gold_manifest_path=Path(args.gold_manifest), registry_path=Path(args.registry),
            provider=args.provider, model=args.model, observed_version=args.version,
        )
    except (ValueError, KeyError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"cold audit benchmark refused: {exc}", file=sys.stderr)
        return 4
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "role": "COLD_AUDIT",
        "model": args.model,
        "observed_version": args.version,
        "version_binding_certifiable": report["scored_identity"].get("version_binding_certifiable"),
        "metrics": report["metrics"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
