"""Owner-machine real end-to-end validation for the Machines/09D pilot.

Unlike `validation/e2e_smoke.py`, this command requires the exact owner-held
Machines PDF, the exact pinned sealed 09D r3 database, and real registered
semantic providers. It also requires a source-first gold reference, either
existing or built from three non-scored independent provider/model families.

The command never writes to 09D. It hashes the database before and after every
real run and requires strict positive Motion-2 authority binding to the pinned
r3 target. It then scores PRIMARY and BLIND_RECALL against source-first gold,
separating W2/S1 from higher-risk/table strata, builds a contradiction review
queue, writes an owner validation report into the run, and creates a final
verified review package.

This still cannot prove E3/clinical truth or certify W3/S3 visual/table semantics
without the corresponding governed review/benchmark. Those limits are surfaced,
not converted to PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hermes_factory.ingest import reconstruct_machines_pilot  # noqa: E402
from hermes_factory.model_registry import load_registry, resolve_model_identity  # noqa: E402

EXPECTED_MACHINES_SHA256 = "379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197"
EXPECTED_09D_SHA256 = "fa7a97313dc5bbd9b2fbb61b9124a4ecef5c318ad5d070eeefe67816a210f4a3"
EXPECTED_UNIT_HASHES = {
    "SU-DORSCH-P0299-VAPORPRESSURE": "1e05a3db793673dcc457174da309a192e8c1a2e98e59cad6a14292359423954a",
    "SU-DORSCH-P0299-BOILING": "38f645b80b29d136e2ed2d695d8f5fbd8efd07735bff9b01d90fa66e95ff1d52",
    "SU-DORSCH-P0300-FIG6_1-CAPTION": "9968fd6a723d66d4e6d3840c953cb144f479c876ac4e645a4943b952cda674cf",
    "SU-DORSCH-P0300-PARTIALPRESSURE": "71451f23cea84f3656fedaee39a414b79e9c04b6d0111c7b45deaa327ef63657",
    "SU-DORSCH-P0300_0301-TABLE6_1": "ae95b47f7c945b00e151dc7184b6f2b15fb806ba5eafc679d772b68b34df6f18",
    "SU-DORSCH-P0301-VOLUMESPERCENT": "f79e7e20ef882e589bf0e164361f8f954ddf24d83a5aaabb8deb247b9930084c",
    "SU-DORSCH-P0301-EQUATION-PARTIAL": "8ba19f5ee9a8ecc5aa8c6483d9e9e97f194d65d0910113835b825c7104f47335",
    "SU-DORSCH-P0301-HEATVAP": "23fb86393c94380963b00e8704f4dc7c9e08cddbec619de781eee2da609e7373",
}
TABLE_UNIT = "SU-DORSCH-P0300_0301-TABLE6_1"
PY = sys.executable


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(cmd: list[str], *, expect: int | set[int] = 0) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    allowed = {expect} if isinstance(expect, int) else set(expect)
    if p.returncode not in allowed:
        raise RuntimeError(
            f"command_failed rc={p.returncode} expected={sorted(allowed)}\n"
            f"cmd={' '.join(cmd)}\nstdout={p.stdout[-6000:]}\nstderr={p.stderr[-6000:]}"
        )
    return p


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_spec(spec: str) -> tuple[str, str]:
    backend, sep, model = spec.partition(":")
    if not sep or not backend or not model:
        raise ValueError(f"provider spec must be backend:model — got {spec!r}")
    return backend.lower(), model


def registry_identity(registry: dict[str, Any], spec: str) -> dict[str, Any]:
    backend, model = parse_spec(spec)
    row = resolve_model_identity(registry, backend.upper(), model)
    if not row.get("empirical_semantic_model"):
        raise RuntimeError(f"non_empirical_provider_not_allowed_for_real_validation:{spec}")
    return row


def validate_independence(registry: dict[str, Any], specs: list[str], label: str) -> list[dict[str, Any]]:
    identities = [registry_identity(registry, spec) for spec in specs]
    groups = [str(x["independence_group"]) for x in identities]
    if len(groups) != len(set(groups)):
        raise RuntimeError(f"{label}_independence_groups_not_distinct:{groups}")
    return identities


def validate_gold_scoring_disjointness(manifest: dict[str, Any], scored_identities: list[dict[str, Any]]) -> dict[str, Any]:
    """Refuse scoring models from any family that participated in gold creation."""
    gold_groups = manifest.get("gold_construction_independence_groups")
    if not isinstance(gold_groups, list) or len(gold_groups) != 3 or any(not isinstance(x, str) or not x for x in gold_groups):
        raise RuntimeError("gold_manifest_missing_or_invalid_construction_independence_groups")
    if len(set(gold_groups)) != 3:
        raise RuntimeError(f"gold_manifest_construction_groups_not_distinct:{gold_groups}")
    scored_groups = [str(x.get("independence_group") or "") for x in scored_identities]
    overlap = sorted(set(gold_groups) & set(scored_groups))
    if overlap:
        raise RuntimeError(f"gold_scoring_independence_group_overlap:{overlap}")
    blocked_models = set(manifest.get("gold_construction_models_not_scorable") or manifest.get("builders_not_scorable") or [])
    scored_models = [str(x.get("model_alias") or "") for x in scored_identities]
    model_overlap = sorted(blocked_models & set(scored_models))
    if model_overlap:
        raise RuntimeError(f"gold_scoring_model_overlap:{model_overlap}")
    return {
        "gold_construction_independence_groups": list(gold_groups),
        "scored_independence_groups": scored_groups,
        "scored_models": scored_models,
        "overlap": [],
    }


def reconstruct_and_verify(pdf: Path, out_path: Path) -> tuple[list[dict[str, Any]], str]:
    reconstruct_machines_pilot(pdf, out_path)
    raw = out_path.read_text(encoding="utf-8")
    units = [json.loads(line) for line in raw.splitlines() if line.strip()]
    observed = {str(x.get("source_unit_id")): str(x.get("content_sha256")) for x in units}
    if observed != EXPECTED_UNIT_HASHES:
        missing = sorted(set(EXPECTED_UNIT_HASHES) - set(observed))
        extra = sorted(set(observed) - set(EXPECTED_UNIT_HASHES))
        wrong = sorted(k for k in set(observed) & set(EXPECTED_UNIT_HASHES) if observed[k] != EXPECTED_UNIT_HASHES[k])
        raise RuntimeError(f"machines_pilot_hash_mismatch:missing={missing}:extra={extra}:wrong={wrong}")
    for row in units:
        actual = sha256_text(str(row.get("content") or ""))
        if actual != str(row.get("content_sha256") or ""):
            raise RuntimeError(f"machines_pilot_declared_content_hash_mismatch:{row.get('source_unit_id')}")
    return units, sha256_text(raw)


def validate_gold(gold_dir: Path, source_units_sha256: str) -> tuple[Path, Path, dict[str, Any]]:
    manifest_path = gold_dir / "GOLD_MANIFEST.json"
    if not manifest_path.exists():
        raise RuntimeError(f"gold_manifest_missing:{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("benchmark_version") != "MACHINES_P0299_P0301_SOURCE_FIRST_v1":
        raise RuntimeError(f"gold_benchmark_version_invalid:{manifest.get('benchmark_version')}")
    if manifest.get("gold_label") != "MECHANICALLY_CHECKED":
        raise RuntimeError(f"gold_label_invalid:{manifest.get('gold_label')}")
    if manifest.get("source_units_sha256") != source_units_sha256:
        raise RuntimeError(
            f"gold_source_units_hash_mismatch:{manifest.get('source_units_sha256')}!={source_units_sha256}"
        )
    if manifest.get("source_pdf_sha256") != EXPECTED_MACHINES_SHA256:
        raise RuntimeError(f"gold_source_pdf_hash_invalid:{manifest.get('source_pdf_sha256')}")
    if manifest.get("source_unit_count") != 8:
        raise RuntimeError(f"gold_source_unit_count_invalid:{manifest.get('source_unit_count')}")
    if manifest.get("source_unit_content_sha256") != EXPECTED_UNIT_HASHES:
        raise RuntimeError("gold_source_unit_hash_manifest_invalid")
    groups = manifest.get("gold_construction_independence_groups")
    if not isinstance(groups, list) or len(groups) != 3 or len(set(groups)) != 3:
        raise RuntimeError(f"gold_construction_groups_invalid:{groups}")
    models = manifest.get("gold_construction_models_not_scorable") or manifest.get("builders_not_scorable")
    if not isinstance(models, list) or len(models) != 3 or len(set(models)) != 3:
        raise RuntimeError(f"gold_construction_models_invalid:{models}")
    ref_name = str(manifest.get("scoring_reference") or "reference_v1.jsonl")
    reference = gold_dir / ref_name
    if not reference.exists():
        raise RuntimeError(f"gold_reference_missing:{reference}")
    measured = sha256_text(reference.read_text(encoding="utf-8"))
    expected = manifest.get("scoring_reference_sha256") or manifest.get("reference_v1_sha256")
    if measured != expected:
        raise RuntimeError(f"gold_reference_hash_mismatch:{measured}!={expected}")
    if not jsonl(reference):
        raise RuntimeError("gold_reference_empty")
    return reference, manifest_path, manifest


def build_gold(args: argparse.Namespace, source_units: Path, gold_dir: Path, registry: dict[str, Any]) -> None:
    specs = [args.gold_builder_a, args.gold_builder_b, args.gold_adjudicator]
    if any(not x for x in specs):
        raise RuntimeError(
            "gold reference required: provide --gold-dir or all of --gold-builder-a, --gold-builder-b, --gold-adjudicator"
        )
    builder_identities = validate_independence(registry, [str(x) for x in specs], "gold_builder")
    scored_identities = [registry_identity(registry, args.primary), registry_identity(registry, args.blind)]
    prebuild_manifest = {
        "gold_construction_independence_groups": [str(x["independence_group"]) for x in builder_identities],
        "gold_construction_models_not_scorable": [str(x["model_alias"]) for x in builder_identities],
    }
    validate_gold_scoring_disjointness(prebuild_manifest, scored_identities)

    cmd = [
        PY, "-B", "benchmarks_ext/gold_build.py",
        "--builder-a", str(args.gold_builder_a),
        "--builder-b", str(args.gold_builder_b),
        "--adjudicator", str(args.gold_adjudicator),
        "--registry", str(ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"),
        "--source-units", str(source_units),
        "--timeout", str(args.timeout_per_call),
        "--out", str(gold_dir),
    ]
    if args.gold_builder_b_think:
        cmd += ["--b-think", args.gold_builder_b_think]
    if args.gold_adjudicator_think:
        cmd += ["--adjudicator-think", args.gold_adjudicator_think]
    run(cmd)


def score_role(
    *, candidates: Path, reference: Path, manifest: Path, role: str, model: str,
    out: Path, units: list[str], primary_candidates: Path | None = None,
) -> dict[str, Any]:
    cmd = [
        PY, "-B", "benchmarks_ext/score_role.py",
        "--candidates", str(candidates),
        "--reference", str(reference),
        "--gold-manifest", str(manifest),
        "--registry", str(ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"),
        "--role", role,
        "--model", model,
        "--units", ",".join(units),
        "--out", str(out),
    ]
    if primary_candidates is not None:
        cmd += ["--primary-candidates", str(primary_candidates)]
    run(cmd)
    return json.loads(out.read_text(encoding="utf-8"))


def _latest_run(output: Path) -> Path:
    rows = [p for p in output.glob("HERMES-*") if p.is_dir()]
    if not rows:
        raise RuntimeError("no_HERMES_run_directory_created")
    return max(rows, key=lambda p: p.stat().st_mtime_ns)


def _contradiction_queue(run_dir: Path) -> list[dict[str, Any]]:
    comparisons = jsonl(run_dir / "09D" / "comparison_09d.jsonl")
    candidates = {str(x.get("candidate_id")): x for x in jsonl(run_dir / "ASSERTIONS" / "union_candidates.jsonl")}
    rows = []
    for comp in comparisons:
        if comp.get("state") != "CONTRADICTION":
            continue
        top = list(comp.get("top_matches") or [])
        best = top[0] if top else {}
        if comp.get("comparison_confidence") != "HIGH":
            raise RuntimeError(f"low_confidence_contradiction_emitted:{comp.get('candidate_id')}")
        if not (best.get("subject_compatible") and best.get("predicate_compatible") and best.get("fact_family_compatible")):
            raise RuntimeError(f"unstructured_contradiction_emitted:{comp.get('candidate_id')}")
        cand = candidates.get(str(comp.get("candidate_id"))) or {}
        rows.append({
            "candidate_id": comp.get("candidate_id"),
            "source_unit_id": comp.get("source_unit_id"),
            "proposition": comp.get("proposition"),
            "evidence": cand.get("evidence"),
            "numeric_values": cand.get("numeric_values") or [],
            "comparison_confidence": comp.get("comparison_confidence"),
            "numeric_relation": comp.get("numeric_relation"),
            "reasons": comp.get("reasons") or [],
            "top_match": best,
            "manual_adjudication_required": True,
        })
    out = run_dir / "09D" / "CONTRADICTION_REVIEW_QUEUE.jsonl"
    out.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows), encoding="utf-8")
    return rows


def _metric(report: dict[str, Any], key: str) -> float | None:
    node = report.get("metrics", {}).get(key)
    return node.get("value") if isinstance(node, dict) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="owner_real_validation")
    ap.add_argument("--source-pdf", required=True)
    ap.add_argument("--database-09d", required=True)
    ap.add_argument("--primary", required=True, help="registered empirical backend:model")
    ap.add_argument("--blind", required=True, help="registered empirical backend:model; independent family")
    ap.add_argument("--cold", required=True, help="registered empirical backend:model; independent family")
    ap.add_argument("--output", default=str(ROOT.parent / "owner-validation-runs"))
    ap.add_argument("--gold-dir", help="existing frozen source-first gold directory")
    ap.add_argument("--gold-builder-a", help="backend:model used only to build gold, not scored")
    ap.add_argument("--gold-builder-b", help="backend:model used only to build gold, not scored")
    ap.add_argument("--gold-adjudicator", help="third independent backend:model for gold disagreements")
    ap.add_argument("--gold-builder-b-think", choices=["false", "low", "medium", "high"])
    ap.add_argument("--gold-adjudicator-think", choices=["false", "low", "medium", "high"])
    ap.add_argument("--ollama-think", choices=["false", "low", "medium", "high"])
    ap.add_argument("--ollama-keep-alive", default="30m")
    ap.add_argument("--timeout-per-call", type=int, default=900)
    ap.add_argument("--provider-schedule", choices=["auto", "parallel", "phased"], default="auto")
    args = ap.parse_args(argv)

    started = time.time()
    source_pdf = Path(args.source_pdf).resolve()
    database = Path(args.database_09d).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    work = output / ("VALIDATION-" + time.strftime("%Y%m%dT%H%M%S", time.gmtime()))
    work.mkdir(parents=True, exist_ok=False)

    report: dict[str, Any] = {
        "schema_version": "hermes-owner-real-validation-1.1",
        "started_epoch": started,
        "checks": {},
        "limits": [
            "E3 clinically material distortion is not mechanically measured by the current scorer.",
            "W3/S3 table/visual/cross-page semantics are measured descriptively where gold exists but have no current automatic certification threshold.",
            "Any 09D CONTRADICTION remains manually adjudicated; comparison is evidence, not truth authority.",
            "Gold label is MECHANICALLY_CHECKED and AI-authored source-first, not clinical ground truth.",
            "Historical Reference-v2 challenge expansion is NOT_RUN in the current gold builder.",
        ],
    }

    if not source_pdf.exists() or not database.exists():
        raise RuntimeError("source_pdf_or_database_missing")
    source_sha = sha256_file(source_pdf)
    db_sha = sha256_file(database)
    if source_sha != EXPECTED_MACHINES_SHA256:
        raise RuntimeError(f"machines_pdf_sha256_mismatch:{source_sha}")
    if db_sha != EXPECTED_09D_SHA256:
        raise RuntimeError(f"09d_r3_sha256_mismatch:{db_sha}")
    report["checks"]["exact_source_pdf_hash"] = "PASS"
    report["checks"]["exact_09d_r3_hash"] = "PASS"

    reconstructed = work / "machines_source_units.jsonl"
    units, source_units_sha = reconstruct_and_verify(source_pdf, reconstructed)
    report["checks"]["exact_eight_source_units"] = "PASS"
    report["source_unit_count"] = len(units)
    report["source_units_sha256"] = source_units_sha

    registry_path = ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"
    registry = load_registry(registry_path)
    role_identities = validate_independence(registry, [args.primary, args.blind, args.cold], "semantic_roles")
    scored_identities = role_identities[:2]
    report["provider_identities"] = role_identities
    report["checks"]["provider_identity_and_independence"] = "PASS"

    run([PY, "-B", "-m", "hermes_factory", "test"])
    run([PY, "-B", "-m", "hermes_factory", "certify-build", "--rerun-tests", "--refresh-runtime-lock"])
    run([PY, "-B", "-m", "hermes_factory", "verify"])
    report["checks"]["tests_certification_preflight"] = "PASS"

    smoke_cmd = [
        PY, "-B", "providers_ext/smoke_providers.py",
        "--source-pdf", str(source_pdf),
        "--primary", args.primary,
        "--blind", args.blind,
        "--audit", args.cold,
        "--timeout", str(args.timeout_per_call),
    ]
    if args.ollama_think:
        smoke_cmd += ["--think", args.ollama_think]
    smoke = run(smoke_cmd)
    report["checks"]["real_provider_smoke"] = "PASS"
    report["provider_smoke_stdout_tail"] = smoke.stdout[-3000:]

    gold_dir = Path(args.gold_dir).resolve() if args.gold_dir else work / "GOLD"
    if not args.gold_dir:
        build_gold(args, reconstructed, gold_dir, registry)
    reference, gold_manifest_path, gold_manifest = validate_gold(gold_dir, source_units_sha)
    gold_guard = validate_gold_scoring_disjointness(gold_manifest, scored_identities)
    report["checks"]["source_first_gold_integrity"] = "PASS"
    report["checks"]["gold_scoring_family_disjointness"] = "PASS"
    report["gold"] = {
        "directory": str(gold_dir),
        "reference": str(reference),
        "reference_sha256": gold_manifest.get("scoring_reference_sha256") or gold_manifest.get("reference_v1_sha256"),
        "reference_count": len(jsonl(reference)),
        "gold_label": gold_manifest.get("gold_label"),
        "challenge_pass": gold_manifest.get("challenge_pass"),
        "builders_not_scorable": gold_manifest.get("builders_not_scorable"),
        "independence_guard": gold_guard,
    }

    db_before = sha256_file(database)
    appliance_cmd = [
        PY, "-B", "run_appliance.py",
        "--profile", "SAFE_4",
        "--pilot", "machines",
        "--source-pdf", str(source_pdf),
        "--database-09d", str(database),
        "--primary", args.primary,
        "--blind", args.blind,
        "--cold", args.cold,
        "--timeout-per-call", str(args.timeout_per_call),
        "--provider-schedule", args.provider_schedule,
        "--ollama-keep-alive", args.ollama_keep_alive,
        "--output", str(output),
    ]
    if args.ollama_think:
        appliance_cmd += ["--ollama-think", args.ollama_think]
    appliance = run(appliance_cmd)
    run_dir = _latest_run(output)
    db_after = sha256_file(database)
    if db_after != db_before:
        raise RuntimeError(f"09d_database_bytes_changed:{db_before}!={db_after}")
    report["checks"]["09d_byte_immutability_during_real_run"] = "PASS"
    report["appliance_stdout_tail"] = appliance.stdout[-5000:]

    outcome_path = run_dir / "APPLIANCE_OUTCOME.json"
    summary_path = run_dir / "APPLIANCE_RUN_SUMMARY.json"
    if not outcome_path.exists() or not summary_path.exists():
        raise RuntimeError("real_appliance_outcome_or_summary_missing")
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if outcome.get("final_package_verified") is not True:
        raise RuntimeError("real_appliance_package_not_verified")
    if run_summary.get("09d_comparison_completed") is not True:
        raise RuntimeError("real_09d_comparison_not_completed")
    core_summary = run_summary.get("summary") or {}
    if core_summary.get("semantic_empirical") is not True:
        raise RuntimeError("real_run_not_marked_semantic_empirical")
    if int(core_summary.get("source_unit_count") or 0) != 8:
        raise RuntimeError(f"real_run_source_unit_count_invalid:{core_summary.get('source_unit_count')}")
    if int(core_summary.get("primary_candidate_count") or 0) <= 0 or int(core_summary.get("blind_candidate_count") or 0) <= 0:
        raise RuntimeError("real_provider_candidate_output_empty")
    report["checks"]["real_eight_unit_semantic_appliance"] = "PASS"
    report["core_readiness_status"] = run_summary.get("readiness_status")

    comparison_summary = json.loads((run_dir / "09D" / "comparison_09d_summary.json").read_text(encoding="utf-8"))
    if comparison_summary.get("database_matches_declared_target") is not True:
        raise RuntimeError("comparison_did_not_verify_pinned_09d_target")
    if comparison_summary.get("database_sha256_measured") != EXPECTED_09D_SHA256:
        raise RuntimeError("comparison_measured_wrong_09d_hash")
    if comparison_summary.get("carrier_scope") != "MOTION1_AUTHORITY" or comparison_summary.get("cycle_safe_authority_comparison") is not True:
        raise RuntimeError("comparison_not_cycle_safe_motion1_authority")
    capability = comparison_summary.get("motion2_capability") or {}
    if capability.get("carrier_partition_valid") is not True:
        raise RuntimeError("09d_carrier_witness_partition_invalid")
    report["checks"]["real_09d_comparison_target_and_cycle_safety"] = "PASS"

    projection_summary = json.loads((run_dir / "09D" / "motion2_projection_summary.json").read_text(encoding="utf-8"))
    if projection_summary.get("authority_binding_enforced") is not True:
        raise RuntimeError("motion2_authority_binding_not_enforced")
    if projection_summary.get("authority_binding_verified") is not True:
        raise RuntimeError(
            f"motion2_positive_authority_binding_failed:{projection_summary.get('projection_errors')}"
        )
    report["checks"]["positive_strict_motion2_authority_binding"] = "PASS"
    report["motion2_projection_status"] = projection_summary.get("projection_status")
    report["motion2_projection_errors"] = projection_summary.get("projection_errors") or []
    report["motion2_target_contract_sha256"] = projection_summary.get("motion2_target_contract_sha256")
    report["authority_context_id"] = projection_summary.get("authority_context_id")

    context_summary = json.loads((run_dir / "09D" / "motion2_numeric_context_guard_summary.json").read_text(encoding="utf-8"))
    report["numeric_context_guard"] = context_summary
    report["checks"]["numeric_context_guard_executed"] = "PASS"

    contradictions = _contradiction_queue(run_dir)
    report["contradiction_count"] = len(contradictions)
    report["manual_contradiction_review_required"] = bool(contradictions)
    report["checks"]["contradictions_structurally_gated"] = "PASS"

    risk = json.loads((run_dir / "SOURCE" / "risk_classification.json").read_text(encoding="utf-8"))
    w2s1 = sorted(uid for uid, row in risk.items() if row.get("work_class") == "W2" and row.get("source_class") == "S1")
    higher_risk = sorted(set(risk) - set(w2s1))
    if not w2s1:
        raise RuntimeError("no_W2_S1_units_available_for_certification_benchmark")
    report["benchmark_strata"] = {"W2_S1": w2s1, "higher_risk": higher_risk}

    bench = run_dir / "BENCHMARK"
    bench.mkdir(exist_ok=True)
    primary_model = parse_spec(args.primary)[1]
    blind_model = parse_spec(args.blind)[1]
    primary_path = run_dir / "ASSERTIONS" / "primary_candidates.jsonl"
    blind_path = run_dir / "ASSERTIONS" / "blind_recall_candidates.jsonl"

    p_w2 = score_role(
        candidates=primary_path, reference=reference, manifest=gold_manifest_path,
        role="PRIMARY", model=primary_model, out=bench / "primary_W2_S1.json",
        units=w2s1,
    )
    b_w2 = score_role(
        candidates=blind_path, reference=reference, manifest=gold_manifest_path,
        role="BLIND_RECALL", model=blind_model, out=bench / "blind_W2_S1.json",
        units=w2s1, primary_candidates=primary_path,
    )
    report["checks"]["W2_S1_primary_blind_scored"] = "PASS"

    cert = run([
        PY, "-B", "benchmarks_ext/certify_roles.py",
        "--primary-score", str(bench / "primary_W2_S1.json"),
        "--blind-score", str(bench / "blind_W2_S1.json"),
        "--primary-provider", parse_spec(args.primary)[0].upper(),
        "--blind-provider", parse_spec(args.blind)[0].upper(),
    ])
    (bench / "provisional_certification_dry_run.txt").write_text(cert.stdout, encoding="utf-8")
    report["provisional_certification_dry_run"] = cert.stdout.strip()

    report["W2_S1_metrics"] = {
        "primary": {
            "recall": _metric(p_w2, "semantic_unit_recall"),
            "precision": _metric(p_w2, "semantic_unit_precision"),
            "evidence_fidelity": _metric(p_w2, "evidence_fidelity_exact_substring"),
            "qualifier_preservation": _metric(p_w2, "qualifier_preservation"),
            "numeric_preservation": _metric(p_w2, "numeric_preservation"),
            "atomicity_failure_rate": _metric(p_w2, "atomicity_failure_rate"),
            "e4_proxy": _metric(p_w2, "e4_mechanical_proxy_cue_injection"),
        },
        "blind": {
            "recall": _metric(b_w2, "semantic_unit_recall"),
            "precision": _metric(b_w2, "semantic_unit_precision"),
            "omission_recovery": _metric(b_w2, "blind_omission_recovery"),
            "useful_new_precision": _metric(b_w2, "blind_useful_new_candidate_precision"),
            "e4_proxy": _metric(b_w2, "e4_mechanical_proxy_cue_injection"),
        },
    }

    if higher_risk:
        p_hi = score_role(
            candidates=primary_path, reference=reference, manifest=gold_manifest_path,
            role="PRIMARY", model=primary_model, out=bench / "primary_HIGHER_RISK.json",
            units=higher_risk,
        )
        b_hi = score_role(
            candidates=blind_path, reference=reference, manifest=gold_manifest_path,
            role="BLIND_RECALL", model=blind_model, out=bench / "blind_HIGHER_RISK.json",
            units=higher_risk, primary_candidates=primary_path,
        )
        report["higher_risk_metrics"] = {
            "units": higher_risk,
            "primary_recall": _metric(p_hi, "semantic_unit_recall"),
            "primary_precision": _metric(p_hi, "semantic_unit_precision"),
            "blind_recall": _metric(b_hi, "semantic_unit_recall"),
            "blind_precision": _metric(b_hi, "semantic_unit_precision"),
            "certification": "NOT_AUTOMATICALLY_CERTIFIED_W3_S3",
        }
        report["checks"]["higher_risk_scored_descriptively"] = "PASS"

    if any(x.get("source_unit_id") == TABLE_UNIT for x in jsonl(reference)):
        p_table = score_role(
            candidates=primary_path, reference=reference, manifest=gold_manifest_path,
            role="PRIMARY", model=primary_model, out=bench / "primary_TABLE6_1.json",
            units=[TABLE_UNIT],
        )
        b_table = score_role(
            candidates=blind_path, reference=reference, manifest=gold_manifest_path,
            role="BLIND_RECALL", model=blind_model, out=bench / "blind_TABLE6_1.json",
            units=[TABLE_UNIT], primary_candidates=primary_path,
        )
        report["table_6_1_metrics"] = {
            "primary_recall": _metric(p_table, "semantic_unit_recall"),
            "primary_precision": _metric(p_table, "semantic_unit_precision"),
            "blind_recall": _metric(b_table, "semantic_unit_recall"),
            "blind_precision": _metric(b_table, "semantic_unit_precision"),
            "certification": "NOT_AUTOMATICALLY_CERTIFIED_TABLE_VISUAL_BINDING",
        }
        report["checks"]["table_6_1_scored_separately"] = "PASS"

    report["semantic_cold_audit_status"] = core_summary.get("semantic_cold_audit_status")
    report["provider_telemetry"] = core_summary.get("provider_telemetry")
    report["09d_state_counts"] = comparison_summary.get("state_counts")
    report["09d_confidence_counts"] = comparison_summary.get("confidence_counts")
    report["core_package"] = outcome.get("final_package")
    report["core_package_verified"] = outcome.get("final_package_verified")
    report["run_dir"] = str(run_dir)
    report["database_sha256_before_after"] = db_before
    report["finished_epoch"] = time.time()
    report["overall"] = "EXECUTED_AND_MEASURED_WITH_EXPLICIT_LIMITS"

    owner_report = run_dir / "OWNER_REAL_VALIDATION_REPORT.json"
    owner_report.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    final_validation_zip = output / f"OWNER_VALIDATED_{run_dir.name}.zip"
    run([PY, "-B", "-m", "hermes_factory", "package", "--run-dir", str(run_dir), "--output", str(final_validation_zip)])
    verify = run([PY, "-B", "-m", "hermes_factory", "verify-package", str(final_validation_zip)])
    validation_package_sha = sha256_file(final_validation_zip)
    if sha256_file(database) != db_before:
        raise RuntimeError("09d_database_changed_during_benchmark_or_packaging")

    outcome2 = {
        "schema_version": "hermes-owner-real-validation-outcome-1.1",
        "run_dir": str(run_dir),
        "owner_validation_report": str(owner_report),
        "owner_validation_package": str(final_validation_zip),
        "owner_validation_package_sha256": validation_package_sha,
        "package_verifier_stdout": verify.stdout.strip(),
        "09d_database_sha256_unchanged": db_before,
        "overall": report["overall"],
    }
    (run_dir / "OWNER_REAL_VALIDATION_OUTCOME.json").write_text(
        json.dumps(outcome2, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({**outcome2, "checks": report["checks"], "limits": report["limits"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
