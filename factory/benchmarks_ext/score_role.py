"""Score one semantic role against frozen source-first gold.

Scoring is fail-closed and source-bound. The scorer verifies the gold manifest,
source-unit bytes, gold-reference bytes, candidate worker identity, candidate
source identity, and exact evidence substrings before computing metrics. A score
report contains hashes for every benchmark input so certification can recompute
and compare the report instead of trusting hand-edited JSON.

E3 remains NOT_MEASURED. E4 remains a mechanical cue-injection proxy.
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

from hermes_factory.literal import NUM_RE, QUALIFIER_PATTERNS, REL_PATTERNS  # noqa: E402
from hermes_factory.model_registry import load_registry, resolve_model_identity  # noqa: E402
from hermes_factory.models import SourceUnit  # noqa: E402
from benchmarks_ext.alignlib import greedy_align, multi_match_counts  # noqa: E402

MATCH_THRESHOLD = 0.5
DUP_THRESHOLD = 0.6
DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"
SCORE_SCHEMA = "hermes-role-score-1.1"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _numbers(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m.group(0)).lower() for m in NUM_RE.finditer(text or "")}


def _rel_cues(text: str) -> set[str]:
    return {m.group(0).lower() for _, p in REL_PATTERNS for m in p.finditer(text or "")}


def _qual_cues(text: str) -> set[str]:
    return {m.group(0).lower() for p in QUALIFIER_PATTERNS.values() for m in p.finditer(text or "")}


def _ratio(num: int, den: int):
    return {"numerator": num, "denominator": den, "value": round(num / den, 4) if den else None}


def _candidate_provider_model(candidates: list[dict], *, expected_model: str | None = None,
                              label: str = "candidate") -> tuple[str, str]:
    seen: set[tuple[str, str]] = set()
    incomplete = 0
    for row in candidates:
        worker = row.get("worker_identity")
        if not isinstance(worker, dict):
            continue
        provider = str(worker.get("provider") or "").upper().strip()
        model = str(worker.get("model_alias") or "").strip()
        if provider or model:
            if not provider or not model:
                incomplete += 1
            else:
                seen.add((provider, model))
    if incomplete:
        raise ValueError(f"{label}_worker_identity_incomplete:{incomplete}")
    if not seen:
        raise ValueError(f"{label}_worker_identity_missing")
    if len(seen) != 1:
        raise ValueError(f"{label}_worker_identity_mixed:{sorted(seen)}")
    provider, model = next(iter(seen))
    if expected_model is not None and model != expected_model:
        raise ValueError(f"{label}_model_argument_mismatch:{expected_model}!={model}")
    return provider, model


def validate_scoring_independence(candidates: list[dict], manifest: dict, registry: dict,
                                  *, expected_model: str | None = None,
                                  label: str = "scored") -> dict:
    groups = manifest.get("gold_construction_independence_groups")
    if not isinstance(groups, list) or not groups or any(not isinstance(x, str) or not x for x in groups):
        raise ValueError("gold_manifest_missing_construction_independence_groups")
    if len(groups) != len(set(groups)):
        raise ValueError(f"gold_manifest_construction_groups_not_distinct:{groups}")
    provider, model = _candidate_provider_model(candidates, expected_model=expected_model, label=label)
    blocked_models = set(manifest.get("gold_construction_models_not_scorable") or manifest.get("builders_not_scorable") or [])
    if model in blocked_models:
        raise ValueError(f"{label}_model_authored_gold:{model}")
    try:
        identity = resolve_model_identity(registry, provider, model)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{label}_model_identity_invalid:{provider}|{model}:{exc}") from exc
    if not identity.get("empirical_semantic_model"):
        raise ValueError(f"{label}_model_not_empirical:{provider}|{model}")
    group = str(identity.get("independence_group") or "")
    if group in set(groups):
        raise ValueError(f"{label}_independence_group_authored_gold:{group}")
    return identity


def load_source_units_verified(path: Path, manifest: dict) -> tuple[dict[str, SourceUnit], str]:
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    measured = sha256_text(raw)
    expected_file = str(manifest.get("source_units_sha256") or "")
    if not expected_file or measured != expected_file:
        raise ValueError(f"source_units_sha256_mismatch:{measured}!={expected_file}")
    rows = [SourceUnit.from_dict(json.loads(line)) for line in raw.splitlines() if line.strip()]
    if not rows:
        raise ValueError("source_units_empty")
    by_id = {u.source_unit_id: u for u in rows}
    if len(by_id) != len(rows):
        raise ValueError("source_units_duplicate_ids")
    expected_hashes = manifest.get("source_unit_content_sha256")
    if not isinstance(expected_hashes, dict) or set(expected_hashes) != set(by_id):
        raise ValueError("source_unit_hash_manifest_set_mismatch")
    source_pdf_sha = str(manifest.get("source_pdf_sha256") or "")
    for uid, unit in by_id.items():
        actual_content = sha256_text(unit.content or "")
        if actual_content != str(expected_hashes.get(uid)):
            raise ValueError(f"source_unit_content_hash_mismatch:{uid}")
        if actual_content != str(unit.content_sha256 or ""):
            raise ValueError(f"source_unit_declared_hash_mismatch:{uid}")
        if source_pdf_sha and str(unit.source_sha256 or "") != source_pdf_sha:
            raise ValueError(f"source_unit_source_sha_mismatch:{uid}")
    return by_id, measured


def load_reference_verified(path: Path, manifest: dict,
                            source_by_id: dict[str, SourceUnit]) -> tuple[list[dict], str]:
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    measured = sha256_text(raw)
    expected = str(manifest.get("scoring_reference_sha256") or manifest.get("reference_v1_sha256") or "")
    if not expected or measured != expected:
        raise ValueError(f"gold_reference_sha256_mismatch:{measured}!={expected}")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not rows:
        raise ValueError("gold_reference_empty")
    builder_map = {
        "A": (str((manifest.get("builder_a") or {}).get("backend") or "").lower(),
              str((manifest.get("builder_a") or {}).get("model") or "")),
        "B": (str((manifest.get("builder_b") or {}).get("backend") or "").lower(),
              str((manifest.get("builder_b") or {}).get("model") or "")),
    }
    for idx, row in enumerate(rows):
        uid = str(row.get("source_unit_id") or "")
        unit = source_by_id.get(uid)
        if unit is None:
            raise ValueError(f"gold_reference_unknown_source_unit:{idx}:{uid}")
        proposition = row.get("proposition")
        evidence = row.get("evidence")
        if not isinstance(proposition, str) or not proposition.strip():
            raise ValueError(f"gold_reference_proposition_invalid:{idx}")
        if not isinstance(evidence, str) or not evidence or evidence not in unit.content:
            raise ValueError(f"gold_reference_evidence_not_exact_source_substring:{idx}:{uid}")
        expected_gold_id = "GOLD-" + sha256_text(uid + "|" + proposition + "|" + evidence)[:20]
        if row.get("gold_id") != expected_gold_id:
            raise ValueError(f"gold_reference_id_mismatch:{idx}:{uid}")
        builder = str(row.get("builder") or "")
        if builder not in builder_map:
            raise ValueError(f"gold_reference_builder_invalid:{idx}:{builder}")
        expected_backend, expected_model = builder_map[builder]
        if str(row.get("backend") or "").lower() != expected_backend or str(row.get("model") or "") != expected_model:
            raise ValueError(f"gold_reference_builder_lineage_mismatch:{idx}:{builder}")
    return rows, measured


def validate_candidates_against_source(candidates: list[dict], source_by_id: dict[str, SourceUnit],
                                       *, label: str) -> None:
    if not candidates:
        raise ValueError(f"{label}_candidate_file_empty")
    seen_ids: set[str] = set()
    for idx, row in enumerate(candidates):
        cid = str(row.get("candidate_id") or "")
        if not cid:
            raise ValueError(f"{label}_candidate_id_missing:{idx}")
        if cid in seen_ids:
            raise ValueError(f"{label}_duplicate_candidate_id:{cid}")
        seen_ids.add(cid)
        uid = str(row.get("source_unit_id") or "")
        unit = source_by_id.get(uid)
        if unit is None:
            raise ValueError(f"{label}_unknown_source_unit:{cid}:{uid}")
        if str(row.get("source_sha256") or "") != str(unit.source_sha256 or ""):
            raise ValueError(f"{label}_source_sha_mismatch:{cid}")
        evidence = row.get("evidence")
        if not isinstance(evidence, str) or not evidence or evidence not in unit.content:
            raise ValueError(f"{label}_evidence_not_exact_source_substring:{cid}")
        if str(row.get("evidence_sha256") or "") != sha256_text(evidence):
            raise ValueError(f"{label}_evidence_sha256_mismatch:{cid}")


def score(candidates: list[dict], gold: list[dict], units_in_scope: set[str],
          primary_candidates: list[dict] | None, source_by_id: dict[str, SourceUnit]) -> dict:
    cands = [c for c in candidates if c["source_unit_id"] in units_in_scope]
    gold_rows = [g for g in gold if g["source_unit_id"] in units_in_scope]
    per_unit = []
    matched_gold = 0
    matched_cands = 0
    by_unit_c: dict[str, list[dict]] = defaultdict(list)
    by_unit_g: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        by_unit_c[c["source_unit_id"]].append(c)
    for g in gold_rows:
        by_unit_g[g["source_unit_id"]].append(g)
    compound = 0
    missed_gold_rows: list[dict] = []
    for unit_id in sorted(set(by_unit_c) | set(by_unit_g)):
        uc, ug = by_unit_c.get(unit_id, []), by_unit_g.get(unit_id, [])
        pairs, un_c, un_g = greedy_align(uc, ug, threshold=MATCH_THRESHOLD)
        matched_gold += len(pairs)
        matched_cands += len(pairs)
        missed_gold_rows.extend(ug[j] for j in un_g)
        compound += sum(1 for n in multi_match_counts(uc, ug, threshold=MATCH_THRESHOLD) if n >= 2)
        per_unit.append({"source_unit_id": unit_id, "candidates": len(uc), "gold": len(ug),
                         "matched": len(pairs), "unmatched_candidates": len(un_c), "missed_gold": len(un_g)})

    evidence_ok = sum(
        1 for c in cands
        if isinstance(c.get("evidence"), str)
        and c["source_unit_id"] in source_by_id
        and c["evidence"] in source_by_id[c["source_unit_id"]].content
    )
    qual_applicable = 0
    qual_preserved = 0
    num_applicable = 0
    num_preserved = 0
    cue_injections = []
    for c in cands:
        ev, prop = c.get("evidence") or "", c.get("proposition") or ""
        ev_quals = _qual_cues(ev)
        if ev_quals:
            qual_applicable += 1
            if all(q in prop.lower() for q in ev_quals):
                qual_preserved += 1
        ev_nums = _numbers(ev)
        if ev_nums:
            num_applicable += 1
            if all(n in _numbers(prop) for n in ev_nums):
                num_preserved += 1
        injected_numbers = _numbers(prop) - _numbers(ev)
        injected_rels = _rel_cues(prop) - _rel_cues(ev)
        if injected_numbers or injected_rels:
            cue_injections.append({"candidate_id": c.get("candidate_id"),
                                   "injected_numbers": sorted(injected_numbers),
                                   "injected_relationship_cues": sorted(injected_rels)})

    result = {
        "semantic_unit_recall": _ratio(matched_gold, len(gold_rows)),
        "semantic_unit_precision": _ratio(matched_cands, len(cands)),
        "evidence_fidelity_exact_substring": _ratio(evidence_ok, len(cands)),
        "qualifier_preservation": _ratio(qual_preserved, qual_applicable),
        "numeric_preservation": _ratio(num_preserved, num_applicable),
        "atomicity_failure_rate": _ratio(compound, len(cands)),
        "e4_mechanical_proxy_cue_injection": _ratio(len(cue_injections), len(cands)),
        "e4_semantic": "NOT_MEASURED (requires human/frontier review of flagged rows)",
        "e3_clinically_material_distortion": "NOT_MEASURED (requires clinical review)",
        "cue_injection_rows": cue_injections,
        "missed_gold_sample": [g["proposition"][:160] for g in missed_gold_rows[:15]],
        "per_unit": per_unit,
        "alignment_threshold": MATCH_THRESHOLD,
    }

    if primary_candidates is not None:
        prim = [c for c in primary_candidates if c["source_unit_id"] in units_in_scope]
        by_unit_p: dict[str, list[dict]] = defaultdict(list)
        for p in prim:
            by_unit_p[p["source_unit_id"]].append(p)
        primary_missed: list[dict] = []
        for unit_id, ug in by_unit_g.items():
            _, _, un_g = greedy_align(by_unit_p.get(unit_id, []), ug, threshold=MATCH_THRESHOLD)
            primary_missed.extend(ug[j] for j in un_g)
        recovered = 0
        for unit_id in {g["source_unit_id"] for g in primary_missed}:
            miss_u = [g for g in primary_missed if g["source_unit_id"] == unit_id]
            pairs, _, _ = greedy_align(by_unit_c.get(unit_id, []), miss_u, threshold=MATCH_THRESHOLD)
            recovered += len(pairs)
        new_cands: list[dict] = []
        for unit_id, uc in by_unit_c.items():
            _, un_c, _ = greedy_align(uc, by_unit_p.get(unit_id, []), threshold=DUP_THRESHOLD)
            new_cands.extend(uc[i] for i in un_c)
        new_matching_gold = 0
        for unit_id in {c["source_unit_id"] for c in new_cands}:
            nc_u = [c for c in new_cands if c["source_unit_id"] == unit_id]
            pairs, _, _ = greedy_align(nc_u, by_unit_g.get(unit_id, []), threshold=MATCH_THRESHOLD)
            new_matching_gold += len(pairs)
        result["blind_omission_recovery"] = _ratio(recovered, len(primary_missed))
        result["blind_useful_new_candidate_precision"] = _ratio(new_matching_gold, len(new_cands))
        result["blind_interpretation_note"] = (
            "Seeded-omission set = gold assertions the primary pass actually missed "
            "(no synthetic seeding); useful-new = blind candidates not duplicating primary (>=0.6) that match gold."
        )
    return result


def build_score_report(*, candidates_path: Path, reference_path: Path, gold_manifest_path: Path,
                       source_units_path: Path, registry_path: Path, role: str, model: str,
                       units_in_scope: set[str] | None,
                       primary_candidates_path: Path | None = None) -> dict[str, Any]:
    manifest = json.loads(Path(gold_manifest_path).read_text(encoding="utf-8"))
    if manifest.get("benchmark_version") != "MACHINES_P0299_P0301_SOURCE_FIRST_v1":
        raise ValueError(f"benchmark_version_invalid:{manifest.get('benchmark_version')}")
    if manifest.get("gold_label") != "MECHANICALLY_CHECKED":
        raise ValueError(f"gold_label_invalid:{manifest.get('gold_label')}")
    source_by_id, source_units_sha = load_source_units_verified(Path(source_units_path), manifest)
    gold, reference_sha = load_reference_verified(Path(reference_path), manifest, source_by_id)
    candidates = _load_jsonl(Path(candidates_path))
    validate_candidates_against_source(candidates, source_by_id, label="scored")
    registry = load_registry(Path(registry_path))
    scored_identity = validate_scoring_independence(candidates, manifest, registry, expected_model=model, label="scored")

    scope = set(units_in_scope) if units_in_scope is not None else {g["source_unit_id"] for g in gold}
    unknown_scope = sorted(scope - set(source_by_id))
    if unknown_scope:
        raise ValueError(f"scope_contains_unknown_source_units:{unknown_scope}")
    if not scope:
        raise ValueError("scope_empty")

    primary = None
    primary_identity = None
    primary_sha = None
    if primary_candidates_path is not None:
        primary = _load_jsonl(Path(primary_candidates_path))
        validate_candidates_against_source(primary, source_by_id, label="primary_baseline")
        primary_identity = validate_scoring_independence(primary, manifest, registry, label="primary_baseline")
        primary_sha = sha256_file(Path(primary_candidates_path))
    if role == "BLIND_RECALL" and primary is None:
        raise ValueError("BLIND_RECALL_requires_primary_candidates")
    if role == "BLIND_RECALL" and primary_identity is not None and (
        str(primary_identity.get("independence_group")) == str(scored_identity.get("independence_group"))
    ):
        raise ValueError(
            f"blind_and_primary_share_independence_group:{scored_identity.get('independence_group')}"
        )

    return {
        "score_schema_version": SCORE_SCHEMA,
        "role": role,
        "model": model,
        "scored_identity": scored_identity,
        "primary_baseline_identity": primary_identity,
        "gold_construction_independence_groups": manifest.get("gold_construction_independence_groups"),
        "benchmark_version": manifest["benchmark_version"],
        "gold_label": manifest["gold_label"],
        "reference_sha256": reference_sha,
        "source_units_sha256": source_units_sha,
        "candidate_file_sha256": sha256_file(Path(candidates_path)),
        "primary_candidate_file_sha256": primary_sha,
        "gold_manifest_sha256": sha256_file(Path(gold_manifest_path)),
        "registry_sha256": sha256_file(Path(registry_path)),
        "units_in_scope": sorted(scope),
        "benchmark_inputs_verified": True,
        "metrics": score(candidates, gold, scope, primary, source_by_id),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="score_role")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--gold-manifest", required=True)
    parser.add_argument("--source-units", required=True, help="exact source_units.jsonl used to build gold")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--role", required=True, choices=["PRIMARY", "BLIND_RECALL"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--primary-candidates", help="required when scoring BLIND_RECALL")
    parser.add_argument("--units", help="comma-separated unit ids in scope; default all gold units")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    scope = set(args.units.split(",")) if args.units else None
    try:
        report = build_score_report(
            candidates_path=Path(args.candidates), reference_path=Path(args.reference),
            gold_manifest_path=Path(args.gold_manifest), source_units_path=Path(args.source_units),
            registry_path=Path(args.registry), role=args.role, model=args.model,
            units_in_scope=scope,
            primary_candidates_path=Path(args.primary_candidates) if args.primary_candidates else None,
        )
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"refusing invalid/unbound benchmark score: {exc}", file=sys.stderr)
        return 4

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    compact = {k: v for k, v in report["metrics"].items()
               if k in ("semantic_unit_recall", "semantic_unit_precision", "qualifier_preservation",
                        "numeric_preservation", "atomicity_failure_rate", "e4_mechanical_proxy_cue_injection",
                        "blind_omission_recovery", "blind_useful_new_candidate_precision")}
    print(json.dumps({
        "role": args.role,
        "model": args.model,
        "scored_independence_group": report["scored_identity"].get("independence_group"),
        "benchmark_inputs_verified": True,
        **compact,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
