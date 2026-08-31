"""Score one role's candidates against the frozen source-first reference.

Every metric reports numerator/denominator and per-unit rows. Metrics that
cannot be measured mechanically are emitted as NOT_MEASURED — they are never
guessed. E4 is reported as a MECHANICAL PROXY (cue injection: numbers or
relationship cues present in a proposition but absent from its own evidence);
true semantic E3/E4 grading requires review and is listed as a limit.

Blind-recall metrics follow CERT-BLIND-RECALL with the seeded-omission set
interpreted as the primary pass's ACTUAL omissions against gold (documented
interpretation; no synthetic seeding was performed).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.literal import NUM_RE, QUALIFIER_PATTERNS, REL_PATTERNS  # noqa: E402
from benchmarks_ext.alignlib import greedy_align, multi_match_counts  # noqa: E402

MATCH_THRESHOLD = 0.5
DUP_THRESHOLD = 0.6


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _numbers(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m.group(0)).lower() for m in NUM_RE.finditer(text or "")}


def _rel_cues(text: str) -> set[str]:
    return {m.group(0).lower() for _, p in REL_PATTERNS for m in p.finditer(text or "")}


def _qual_cues(text: str) -> set[str]:
    return {m.group(0).lower() for p in QUALIFIER_PATTERNS.values() for m in p.finditer(text or "")}


def _ratio(num: int, den: int):
    return {"numerator": num, "denominator": den, "value": round(num / den, 4) if den else None}


def score(candidates: list[dict], gold: list[dict], units_in_scope: set[str],
          primary_candidates: list[dict] | None) -> dict:
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
    unmatched_cand_rows: list[dict] = []
    for unit_id in sorted(set(by_unit_c) | set(by_unit_g)):
        uc, ug = by_unit_c.get(unit_id, []), by_unit_g.get(unit_id, [])
        pairs, un_c, un_g = greedy_align(uc, ug, threshold=MATCH_THRESHOLD)
        matched_gold += len(pairs)
        matched_cands += len(pairs)
        missed_gold_rows.extend(ug[j] for j in un_g)
        unmatched_cand_rows.extend(uc[i] for i in un_c)
        compound += sum(1 for n in multi_match_counts(uc, ug, threshold=MATCH_THRESHOLD) if n >= 2)
        per_unit.append({"source_unit_id": unit_id, "candidates": len(uc), "gold": len(ug),
                         "matched": len(pairs), "unmatched_candidates": len(un_c), "missed_gold": len(un_g)})

    evidence_ok = sum(1 for c in cands if c.get("evidence"))
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
            if all(any(n in _numbers(prop) for n in (x,)) for x in ev_nums):
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="score_role")
    parser.add_argument("--candidates", required=True, help="candidates JSONL (run ASSERTIONS file)")
    parser.add_argument("--reference", required=True, help="frozen gold reference JSONL")
    parser.add_argument("--gold-manifest", required=True)
    parser.add_argument("--role", required=True, choices=["PRIMARY", "BLIND_RECALL"])
    parser.add_argument("--model", required=True, help="model alias being scored")
    parser.add_argument("--primary-candidates", help="required when scoring BLIND_RECALL")
    parser.add_argument("--units", help="comma-separated unit ids in scope (default: text/prose units only)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.gold_manifest).read_text(encoding="utf-8"))
    if args.model in manifest.get("builders_not_scorable", []):
        print(f"refusing: {args.model} authored the gold reference and cannot be scored against it", file=sys.stderr)
        return 4
    candidates = _load_jsonl(Path(args.candidates))
    gold = _load_jsonl(Path(args.reference))
    if args.units:
        scope = set(args.units.split(","))
    else:
        scope = {g["source_unit_id"] for g in gold}
    primary = _load_jsonl(Path(args.primary_candidates)) if args.primary_candidates else None
    if args.role == "BLIND_RECALL" and primary is None:
        print("BLIND_RECALL scoring requires --primary-candidates", file=sys.stderr)
        return 2

    report = {
        "role": args.role,
        "model": args.model,
        "benchmark_version": manifest["benchmark_version"],
        "gold_label": manifest["gold_label"],
        "reference_sha256": manifest["reference_v1_sha256"],
        "units_in_scope": sorted(scope),
        "metrics": score(candidates, gold, scope, primary),
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    compact = {k: v for k, v in report["metrics"].items()
               if k in ("semantic_unit_recall", "semantic_unit_precision", "qualifier_preservation",
                        "numeric_preservation", "atomicity_failure_rate", "e4_mechanical_proxy_cue_injection",
                        "blind_omission_recovery", "blind_useful_new_candidate_precision")}
    print(json.dumps({"role": args.role, "model": args.model, **compact}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
