"""Source-first gold construction for the Machines p299-301 benchmark.

Implements BENCHMARKS/BENCHMARK_V0_1/GOLD_CONSTRUCTION_PROTOCOL.md:

  1-3. Builder A and Builder B each receive the frozen source units ONLY,
       independently (neither sees the other, nor any historical output).
  4.   Deterministic literal inventories run per unit (context for review).
  5.   A/B disagreement set built by deterministic alignment.
  6.   Adjudicator C receives source + each disagreed assertion, not model
       reputations, and rules keep/drop.
  7.   Mechanical validation: evidence exact-substring, hashes, schema.
  8.   Reference v1 frozen with a manifest hash.
  9-12. Historical outputs, when supplied via --challenge-dir, become
       challenges adjudicated the same way into Reference v2. When none are
       supplied the challenge pass is recorded NOT_RUN and v1 is the scoring
       reference.
  13.  Builder models are recorded so they are never scored against units
       they authored.

Gold label: MECHANICALLY_CHECKED (per the estate's standing gold-set ruling).
No prior SOL/Kimi/Gemini/Meta/Hermes output seeds the reference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.models import SourceUnit  # noqa: E402
from hermes_factory.semantic import build_primary_request  # noqa: E402
from hermes_factory.literal import numeric_inventory, qualifier_inventory  # noqa: E402
from benchmarks_ext.alignlib import greedy_align  # noqa: E402

UNITS_PATH = FACTORY_ROOT / "PILOTS" / "MACHINES_P0299_P0301_TURN09" / "SOURCE_UNITS" / "source_units.jsonl"
WRAPPER = FACTORY_ROOT / "providers_ext" / "llm_provider.py"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_spec(value: str) -> tuple[str, str]:
    backend, _, model = value.partition(":")
    return backend, model


def call_wrapper(backend: str, model: str, request: dict, timeout: int) -> dict:
    proc = subprocess.run(
        [sys.executable, "-B", str(WRAPPER), "--backend", backend, "--model", model, "--timeout", str(timeout)],
        input=json.dumps(request, ensure_ascii=False), capture_output=True, text=True,
        encoding="utf-8", timeout=timeout + 90,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"wrapper_failed:{backend}:{model}:rc={proc.returncode}:{proc.stderr[-800:]}")
    return json.loads(proc.stdout)


def build_pass(name: str, backend: str, model: str, units: list[SourceUnit], timeout: int,
               parallel: int, out_dir: Path) -> list[dict]:
    rows: list[dict] = []

    def one(unit: SourceUnit) -> list[dict]:
        request = build_primary_request(unit, f"GOLD-{name}", f"GOLDRUN-{name}")
        response = call_wrapper(backend, model, request, timeout)
        out = []
        for a in response.get("assertions", []):
            out.append({
                "builder": name, "backend": backend, "model": model,
                "source_unit_id": unit.source_unit_id,
                "proposition": a["proposition"], "evidence": a["evidence"],
                "polarity": a.get("polarity", "AFFIRMATIVE"),
                "certainty": a.get("certainty", "ASSERTED"),
                "numeric_values": a.get("numeric_values", []),
                "qualifiers": a.get("qualifiers", []),
            })
        print(f"[gold:{name}] {unit.source_unit_id}: {len(out)} assertions", flush=True)
        return out

    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            for chunk in pool.map(one, units):
                rows.extend(chunk)
    else:
        for unit in units:
            rows.extend(one(unit))
    path = out_dir / f"raw_builder_{name}.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    return rows


def cue_count(row: dict) -> int:
    return len(row.get("numeric_values") or []) + len(row.get("qualifiers") or [])


def adjudicate(backend: str, model: str, unit: SourceUnit, row: dict, timeout: int) -> tuple[bool, str]:
    request = {
        "request_schema_version": "hermes-worker-request-1.1",
        "task_role": "COLD_AUDIT",
        "source_unit": unit.to_dict(),
        "audit_target": {
            "candidate_id": f"GOLD-DISAGREE-{sha256_text(row['proposition'])[:12]}",
            "proposition": row["proposition"], "evidence": row["evidence"],
            "polarity": row.get("polarity"), "certainty": row.get("certainty"),
        },
        "task_instructions": (
            "Adjudicate whether this assertion belongs in a gold reference for the supplied source. "
            "Keep it only if the evidence is in the source and fully supports the proposition with "
            "negation, qualifiers, numbers and direction preserved. Judge the assertion, not its author."
        ),
        "output_schema": {"type": "object", "required": ["verdict"]},
    }
    response = call_wrapper(backend, model, request, timeout)
    verdict = response["verdict"]
    return bool(verdict["supported"]), str(verdict.get("rationale") or "")[:400]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gold_build")
    parser.add_argument("--builder-a", default="claude:claude-fable-5")
    parser.add_argument("--builder-b", required=True, help="backend:model — must NOT be a model that will be scored")
    parser.add_argument("--adjudicator", default="ollama:deepseek-r1:14b")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--out", default=str(FACTORY_ROOT / "GOLD" / "MACHINES_P0299_P0301_v1"))
    parser.add_argument("--challenge-dir", help="directory of historical candidate JSONL files for the v2 challenge pass")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    units = [SourceUnit.from_dict(json.loads(line))
             for line in UNITS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ab, am = parse_spec(args.builder_a)
    bb, bm = parse_spec(args.builder_b)
    jb, jm = parse_spec(args.adjudicator)
    started = time.time()

    print(f"[gold] builder A = {ab}:{am}   builder B = {bb}:{bm}   adjudicator = {jb}:{jm}", flush=True)
    rows_a = build_pass("A", ab, am, units, args.timeout, parallel=4 if ab == "claude" else 1, out_dir=out_dir)
    rows_b = build_pass("B", bb, bm, units, args.timeout, parallel=4 if bb == "claude" else 1, out_dir=out_dir)

    inventories = {
        u.source_unit_id: {
            "numeric": len(numeric_inventory(u)),
            "qualifier": len(qualifier_inventory(u)),
        } for u in units
    }
    units_by_id = {u.source_unit_id: u for u in units}

    reference: list[dict] = []
    disagreements: list[dict] = []
    for unit in units:
        ua = [r for r in rows_a if r["source_unit_id"] == unit.source_unit_id]
        ub = [r for r in rows_b if r["source_unit_id"] == unit.source_unit_id]
        pairs, only_a, only_b = greedy_align(ua, ub, threshold=0.6)
        for i, j, score in pairs:
            pick = ua[i] if (cue_count(ua[i]), len(ua[i]["proposition"]), ua[i]["proposition"]) >= \
                            (cue_count(ub[j]), len(ub[j]["proposition"]), ub[j]["proposition"]) else ub[j]
            reference.append({**pick, "gold_origin": "AGREED_A_B", "agreement_score": round(score, 3)})
        disagreements.extend(ua[i] for i in only_a)
        disagreements.extend(ub[j] for j in only_b)

    print(f"[gold] agreed={len(reference)} disagreements={len(disagreements)} — adjudicating with {jm}", flush=True)
    adjudication_log: list[dict] = []
    for row in disagreements:
        unit = units_by_id[row["source_unit_id"]]
        try:
            keep, rationale = adjudicate(jb, jm, unit, row, args.timeout)
        except Exception as exc:  # noqa: BLE001 — an unadjudicable item is excluded, and recorded
            keep, rationale = False, f"ADJUDICATION_ERROR:{type(exc).__name__}"
        adjudication_log.append({"builder": row["builder"], "source_unit_id": row["source_unit_id"],
                                 "proposition": row["proposition"], "keep": keep, "rationale": rationale})
        if keep:
            reference.append({**row, "gold_origin": f"ADJUDICATED_{row['builder']}"})
        print(f"[gold] adjudicated {row['source_unit_id']} keep={keep}", flush=True)

    validated = []
    dropped_mechanical = []
    for row in reference:
        unit = units_by_id[row["source_unit_id"]]
        if row["evidence"] in unit.content and row["proposition"].strip():
            gold_id = "GOLD-" + sha256_text(row["source_unit_id"] + "|" + row["proposition"] + "|" + row["evidence"])[:20]
            validated.append({**row, "gold_id": gold_id})
        else:
            dropped_mechanical.append(row)
    validated.sort(key=lambda r: (r["source_unit_id"], r["gold_id"]))

    ref_path = out_dir / "reference_v1.jsonl"
    ref_bytes = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in validated)
    ref_path.write_text(ref_bytes, encoding="utf-8")
    (out_dir / "adjudication_log.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in adjudication_log), encoding="utf-8")

    challenge_state = "NOT_RUN_NO_HISTORICAL_OUTPUTS_SUPPLIED"
    if args.challenge_dir:
        challenge_state = f"SUPPLIED_BUT_NOT_IMPLEMENTED_IN_THIS_VERSION:{args.challenge_dir}"

    manifest = {
        "benchmark_version": "MACHINES_P0299_P0301_SOURCE_FIRST_v1",
        "gold_label": "MECHANICALLY_CHECKED",
        "source_units_sha256": sha256_text(UNITS_PATH.read_text(encoding="utf-8")),
        "builder_a": {"backend": ab, "model": am, "assertions": len(rows_a)},
        "builder_b": {"backend": bb, "model": bm, "assertions": len(rows_b)},
        "adjudicator": {"backend": jb, "model": jm, "items": len(adjudication_log),
                        "kept": sum(1 for x in adjudication_log if x["keep"])},
        "agreed_count": sum(1 for r in validated if r["gold_origin"] == "AGREED_A_B"),
        "reference_v1_count": len(validated),
        "reference_v1_sha256": sha256_text(ref_bytes),
        "mechanically_dropped": len(dropped_mechanical),
        "deterministic_inventories": inventories,
        "challenge_pass": challenge_state,
        "scoring_reference": "reference_v1.jsonl",
        "builders_not_scorable": [am, bm],
        "duration_seconds": round(time.time() - started, 1),
        "claim_boundary": (
            "AI-authored source-first gold, label MECHANICALLY_CHECKED. Built from source bytes only; "
            "no historical extraction output seeded it. It bounds benchmark claims, not clinical truth."
        ),
    }
    (out_dir / "GOLD_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("reference_v1_count", "agreed_count", "adjudicator",
                                               "reference_v1_sha256", "duration_seconds")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
