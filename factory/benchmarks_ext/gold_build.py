"""Source-first gold construction for the Machines p299-301 benchmark.

Implements the executable portion of BENCHMARKS/BENCHMARK_V0_1/GOLD_CONSTRUCTION_PROTOCOL.md:

  1-3. Builder A and Builder B each receive the frozen source units ONLY,
       independently (neither sees the other, nor any historical output).
  4.   Deterministic literal inventories run per unit (context for review).
  5.   A/B disagreement set built by deterministic alignment.
  6.   Adjudicator C receives source + each disagreed assertion, not model
       reputations, and rules keep/drop.
  7.   Mechanical validation: evidence exact-substring, hashes, schema.
  8.   Reference v1 frozen with a manifest hash.
  9.   Historical challenge expansion is NOT implemented in this version.
       Supplying --challenge-dir therefore fails closed instead of implying the
       challenge pass ran.
 10.   Builder models are recorded so they are never scored against a gold
       reference they authored.

The rights-safe repository does not bundle textbook source-unit text. Supply
--source-pdf (the hash-pinned owner copy) or --source-units. The legacy bundled
path is used only if it genuinely exists in an owner-controlled checkout.

Gold label: MECHANICALLY_CHECKED (per the estate's standing gold-set ruling).
No prior SOL/Kimi/Gemini/Meta/Hermes output seeds Reference v1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY_ROOT))

from hermes_factory.ingest import reconstruct_machines_pilot  # noqa: E402
from hermes_factory.models import SourceUnit  # noqa: E402
from hermes_factory.semantic import build_primary_request  # noqa: E402
from hermes_factory.literal import numeric_inventory, qualifier_inventory  # noqa: E402
from benchmarks_ext.alignlib import greedy_align  # noqa: E402

LEGACY_UNITS_PATH = FACTORY_ROOT / "PILOTS" / "MACHINES_P0299_P0301_TURN09" / "SOURCE_UNITS" / "source_units.jsonl"
WRAPPER = FACTORY_ROOT / "providers_ext" / "llm_provider.py"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_spec(value: str) -> tuple[str, str]:
    backend, sep, model = value.partition(":")
    if not sep or not backend or not model:
        raise SystemExit(f"provider spec must be backend:model — got {value!r}")
    return backend, model


def load_source_units(*, source_units: str | None, source_pdf: str | None) -> tuple[list[SourceUnit], str, str]:
    """Load gold-builder source without requiring copyrighted bytes in git."""
    raw: str
    origin: str
    if source_units:
        path = Path(source_units).resolve()
        if not path.exists():
            raise SystemExit(f"source units not found: {path}")
        raw = path.read_text(encoding="utf-8")
        origin = f"OWNER_SOURCE_UNITS:{path}"
    elif LEGACY_UNITS_PATH.exists():
        raw = LEGACY_UNITS_PATH.read_text(encoding="utf-8")
        origin = f"OWNER_CHECKOUT_LEGACY_SOURCE_UNITS:{LEGACY_UNITS_PATH}"
    elif source_pdf:
        pdf = Path(source_pdf).resolve()
        if not pdf.exists():
            raise SystemExit(f"source PDF not found: {pdf}")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "machines_source_units.jsonl"
            reconstruct_machines_pilot(pdf, path)
            raw = path.read_text(encoding="utf-8")
        origin = f"OWNER_HASH_PINNED_PDF_RECONSTRUCTION:{pdf}"
    else:
        raise SystemExit(
            "rights-safe checkout contains no textbook source units; provide --source-pdf pointing to the "
            "hash-pinned Machines textbook or --source-units pointing to owner-controlled source units"
        )

    rows = [SourceUnit.from_dict(json.loads(line)) for line in raw.splitlines() if line.strip()]
    if not rows:
        raise SystemExit("source unit input is empty")
    ids = [u.source_unit_id for u in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate source_unit_id in gold source input")
    return rows, sha256_text(raw), origin


def call_wrapper(backend: str, model: str, request: dict, timeout: int,
                 extra_args: list[str] | None = None) -> dict:
    proc = subprocess.run(
        [sys.executable, "-B", str(WRAPPER), "--backend", backend, "--model", model,
         "--timeout", str(timeout)] + list(extra_args or []),
        input=json.dumps(request, ensure_ascii=False), capture_output=True, text=True,
        encoding="utf-8", timeout=timeout + 90,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"wrapper_failed:{backend}:{model}:rc={proc.returncode}:{proc.stderr[-800:]}")
    return json.loads(proc.stdout)


def build_pass(name: str, backend: str, model: str, units: list[SourceUnit], timeout: int,
               parallel: int, out_dir: Path, extra_args: list[str] | None = None) -> list[dict]:
    rows: list[dict] = []

    def one(unit: SourceUnit) -> list[dict]:
        request = build_primary_request(unit, f"GOLD-{name}", f"GOLDRUN-{name}")
        response = call_wrapper(backend, model, request, timeout, extra_args)
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


def adjudicate(backend: str, model: str, unit: SourceUnit, row: dict, timeout: int,
               extra_args: list[str] | None = None) -> tuple[bool, str]:
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
    response = call_wrapper(backend, model, request, timeout, extra_args)
    verdict = response["verdict"]
    return bool(verdict["supported"]), str(verdict.get("rationale") or "")[:400]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gold_build")
    parser.add_argument("--builder-a", default="claude:claude-fable-5")
    parser.add_argument("--builder-b", required=True, help="backend:model — must NOT be a model that will be scored")
    parser.add_argument("--adjudicator", default="ollama:deepseek-r1:14b")
    parser.add_argument("--source-units", help="owner-controlled source_units.jsonl")
    parser.add_argument("--source-pdf", help="owner hash-pinned Machines PDF; exact pilot units are reconstructed locally")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--out", default=str(FACTORY_ROOT / "GOLD" / "MACHINES_P0299_P0301_v1"))
    parser.add_argument("--challenge-dir", help="reserved for future Reference-v2 challenge pass; currently refused fail-closed")
    parser.add_argument("--phase", choices=["build-a", "build-b", "finalize", "all"], default="all",
                        help="run one phase; build phases persist raw_builder_X.jsonl, finalize reuses them")
    parser.add_argument("--b-think", choices=["false", "low", "medium", "high"],
                        help="--ollama-think for builder B (reasoning models like gpt-oss)")
    parser.add_argument("--adjudicator-think", choices=["false", "low", "medium", "high"],
                        help="--ollama-think for the adjudicator")
    args = parser.parse_args(argv)

    if args.challenge_dir:
        print(
            "refusing --challenge-dir: Reference-v2 historical challenge adjudication is not implemented in this version; "
            "do not label it as executed",
            file=sys.stderr,
        )
        return 5

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    units, source_units_sha256, source_origin = load_source_units(
        source_units=args.source_units,
        source_pdf=args.source_pdf,
    )
    ab, am = parse_spec(args.builder_a)
    bb, bm = parse_spec(args.builder_b)
    jb, jm = parse_spec(args.adjudicator)
    if (ab.upper(), am) == (bb.upper(), bm):
        print("builder A and builder B must be different provider/model identities", file=sys.stderr)
        return 6
    if (jb.upper(), jm) in {(ab.upper(), am), (bb.upper(), bm)}:
        print("adjudicator must be a different provider/model identity from both builders", file=sys.stderr)
        return 6
    started = time.time()

    print(
        f"[gold] source={source_origin} units={len(units)} builder A={ab}:{am} "
        f"builder B={bb}:{bm} adjudicator={jb}:{jm} phase={args.phase}",
        flush=True,
    )

    def load_raw(name: str) -> list[dict]:
        path = out_dir / f"raw_builder_{name}.jsonl"
        if not path.exists():
            raise SystemExit(f"phase {args.phase} needs {path.name}; run build-{name.lower()} first")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    if args.phase in ("build-a", "all"):
        rows_a = build_pass("A", ab, am, units, args.timeout, parallel=4 if ab == "claude" else 1, out_dir=out_dir)
        if args.phase == "build-a":
            print(json.dumps({"phase": "build-a", "assertions": len(rows_a), "source_units_sha256": source_units_sha256}))
            return 0
    else:
        rows_a = load_raw("A")
    if args.phase in ("build-b", "all"):
        b_extra = ["--ollama-think", args.b_think] if (args.b_think and bb == "ollama") else None
        rows_b = build_pass("B", bb, bm, units, args.timeout, parallel=4 if bb == "claude" else 1,
                            out_dir=out_dir, extra_args=b_extra)
        if args.phase == "build-b":
            print(json.dumps({"phase": "build-b", "assertions": len(rows_b), "source_units_sha256": source_units_sha256}))
            return 0
    else:
        rows_b = load_raw("B")

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
    j_extra = ["--ollama-think", args.adjudicator_think] if (args.adjudicator_think and jb == "ollama") else None
    for row in disagreements:
        unit = units_by_id[row["source_unit_id"]]
        try:
            keep, rationale = adjudicate(jb, jm, unit, row, args.timeout, j_extra)
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

    manifest = {
        "benchmark_version": "MACHINES_P0299_P0301_SOURCE_FIRST_v1",
        "gold_label": "MECHANICALLY_CHECKED",
        "source_origin": source_origin,
        "source_units_sha256": source_units_sha256,
        "source_unit_count": len(units),
        "builder_a": {"backend": ab, "model": am, "assertions": len(rows_a)},
        "builder_b": {"backend": bb, "model": bm, "assertions": len(rows_b)},
        "adjudicator": {"backend": jb, "model": jm, "items": len(adjudication_log),
                        "kept": sum(1 for x in adjudication_log if x["keep"])},
        "agreed_count": sum(1 for r in validated if r["gold_origin"] == "AGREED_A_B"),
        "reference_v1_count": len(validated),
        "reference_v1_sha256": sha256_text(ref_bytes),
        "mechanically_dropped": len(dropped_mechanical),
        "deterministic_inventories": inventories,
        "challenge_pass": "NOT_RUN_REFERENCE_V2_NOT_IMPLEMENTED",
        "scoring_reference": "reference_v1.jsonl",
        "scoring_reference_sha256": sha256_text(ref_bytes),
        "builders_not_scorable": [am, bm],
        "duration_seconds": round(time.time() - started, 1),
        "claim_boundary": (
            "AI-authored source-first gold, label MECHANICALLY_CHECKED. Built from source bytes only; "
            "no historical extraction output seeded Reference v1. Historical challenge expansion is NOT_RUN. "
            "This bounds benchmark claims, not clinical truth."
        ),
    }
    (out_dir / "GOLD_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("reference_v1_count", "agreed_count", "adjudicator",
                                               "reference_v1_sha256", "source_unit_count", "duration_seconds")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
