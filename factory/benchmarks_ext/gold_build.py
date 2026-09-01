"""Source-first gold construction for the governed Machines p299-301 benchmark.

This builder is deliberately benchmark-specific and fail-closed:
- source bytes must reconstruct/contain the exact eight governed Machines units;
- Builder A, Builder B, and Adjudicator C must be registered empirical models
  from three distinct independence groups;
- historical Reference-v2 challenge expansion remains NOT_RUN and supplying
  --challenge-dir is refused rather than mislabeled as executed.

The rights-safe repository does not bundle textbook source-unit text. Supply
--source-pdf (the hash-pinned owner copy) or --source-units containing the exact
reconstructed eight units.

Gold label: MECHANICALLY_CHECKED. This is AI-authored source-first benchmark
material, not clinical ground truth.
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

from hermes_factory.ingest import (  # noqa: E402
    MACHINES_PILOT_SOURCE_SHA256,
    MACHINES_PILOT_UNIT_SPECS,
    reconstruct_machines_pilot,
)
from hermes_factory.literal import numeric_inventory, qualifier_inventory  # noqa: E402
from hermes_factory.model_registry import load_registry, resolve_model_identity  # noqa: E402
from hermes_factory.models import SourceUnit  # noqa: E402
from hermes_factory.semantic import build_primary_request  # noqa: E402
from benchmarks_ext.alignlib import greedy_align  # noqa: E402

LEGACY_UNITS_PATH = FACTORY_ROOT / "PILOTS" / "MACHINES_P0299_P0301_TURN09" / "SOURCE_UNITS" / "source_units.jsonl"
DEFAULT_REGISTRY = FACTORY_ROOT / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"
WRAPPER = FACTORY_ROOT / "providers_ext" / "llm_provider.py"
EXPECTED_UNIT_HASHES = {str(x["source_unit_id"]): str(x["content_sha256"]) for x in MACHINES_PILOT_UNIT_SPECS}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_spec(value: str) -> tuple[str, str]:
    backend, sep, model = value.partition(":")
    if not sep or not backend or not model:
        raise SystemExit(f"provider spec must be backend:model — got {value!r}")
    return backend, model


def validate_governed_machines_units(rows: list[SourceUnit]) -> None:
    """Refuse arbitrary source-unit files under the Machines benchmark label."""
    observed = {u.source_unit_id: u.content_sha256 for u in rows}
    if len(rows) != len(EXPECTED_UNIT_HASHES) or observed != EXPECTED_UNIT_HASHES:
        missing = sorted(set(EXPECTED_UNIT_HASHES) - set(observed))
        extra = sorted(set(observed) - set(EXPECTED_UNIT_HASHES))
        wrong = sorted(
            uid for uid in set(observed) & set(EXPECTED_UNIT_HASHES)
            if observed[uid] != EXPECTED_UNIT_HASHES[uid]
        )
        raise SystemExit(
            f"gold_source_not_exact_governed_machines_pilot:count={len(rows)}:"
            f"missing={missing}:extra={extra}:wrong_hash={wrong}"
        )
    bad_source = sorted(
        u.source_unit_id for u in rows if u.source_sha256 != MACHINES_PILOT_SOURCE_SHA256
    )
    if bad_source:
        raise SystemExit(f"gold_source_pdf_identity_mismatch:{bad_source}")


def load_source_units(*, source_units: str | None, source_pdf: str | None) -> tuple[list[SourceUnit], str, str]:
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
            "hash-pinned Machines textbook or --source-units pointing to the exact reconstructed pilot"
        )

    rows = [SourceUnit.from_dict(json.loads(line)) for line in raw.splitlines() if line.strip()]
    if not rows:
        raise SystemExit("source unit input is empty")
    ids = [u.source_unit_id for u in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate source_unit_id in gold source input")
    validate_governed_machines_units(rows)
    return rows, sha256_text(raw), origin


def resolve_gold_identities(registry_path: Path, specs: list[str]) -> list[dict]:
    registry = load_registry(registry_path)
    identities = []
    for spec in specs:
        backend, model = parse_spec(spec)
        try:
            row = resolve_model_identity(registry, backend.upper(), model)
        except (KeyError, ValueError) as exc:
            raise SystemExit(f"gold_model_identity_invalid:{spec}:{exc}") from exc
        if not row.get("empirical_semantic_model"):
            raise SystemExit(f"gold_model_not_empirical:{spec}")
        identities.append(row)
    groups = [str(x["independence_group"]) for x in identities]
    if len(groups) != len(set(groups)):
        raise SystemExit(f"gold_construction_independence_groups_not_distinct:{groups}")
    return identities


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
    value = json.loads(proc.stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f"wrapper_output_not_object:{backend}:{model}")
    return value


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
    parser.add_argument("--builder-a", required=True, help="registered empirical backend:model")
    parser.add_argument("--builder-b", required=True, help="registered empirical backend:model")
    parser.add_argument("--adjudicator", required=True, help="third registered empirical backend:model")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--source-units", help="owner-controlled exact Machines source_units.jsonl")
    parser.add_argument("--source-pdf", help="owner hash-pinned Machines PDF; exact pilot units are reconstructed locally")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--out", default=str(FACTORY_ROOT / "GOLD" / "MACHINES_P0299_P0301_v1"))
    parser.add_argument("--challenge-dir", help="reserved for future Reference-v2 challenge pass; currently refused fail-closed")
    parser.add_argument("--phase", choices=["build-a", "build-b", "finalize", "all"], default="all")
    parser.add_argument("--b-think", choices=["false", "low", "medium", "high"])
    parser.add_argument("--adjudicator-think", choices=["false", "low", "medium", "high"])
    args = parser.parse_args(argv)

    if args.challenge_dir:
        print(
            "refusing --challenge-dir: Reference-v2 historical challenge adjudication is not implemented in this version",
            file=sys.stderr,
        )
        return 5

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    units, source_units_sha256, source_origin = load_source_units(
        source_units=args.source_units, source_pdf=args.source_pdf,
    )
    specs = [args.builder_a, args.builder_b, args.adjudicator]
    identities = resolve_gold_identities(Path(args.registry), specs)
    ab, am = parse_spec(args.builder_a)
    bb, bm = parse_spec(args.builder_b)
    jb, jm = parse_spec(args.adjudicator)
    started = time.time()

    print(
        f"[gold] source={source_origin} units={len(units)} builder A={ab}:{am} "
        f"builder B={bb}:{bm} adjudicator={jb}:{jm} phase={args.phase}", flush=True,
    )

    def load_raw(name: str) -> list[dict]:
        path = out_dir / f"raw_builder_{name}.jsonl"
        if not path.exists():
            raise SystemExit(f"phase {args.phase} needs {path.name}; run build-{name.lower()} first")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    if args.phase in ("build-a", "all"):
        rows_a = build_pass("A", ab, am, units, args.timeout, 4 if ab == "claude" else 1, out_dir)
        if args.phase == "build-a":
            print(json.dumps({"phase": "build-a", "assertions": len(rows_a), "source_units_sha256": source_units_sha256}))
            return 0
    else:
        rows_a = load_raw("A")

    if args.phase in ("build-b", "all"):
        b_extra = ["--ollama-think", args.b_think] if (args.b_think and bb == "ollama") else None
        rows_b = build_pass("B", bb, bm, units, args.timeout, 4 if bb == "claude" else 1, out_dir, b_extra)
        if args.phase == "build-b":
            print(json.dumps({"phase": "build-b", "assertions": len(rows_b), "source_units_sha256": source_units_sha256}))
            return 0
    else:
        rows_b = load_raw("B")

    inventories = {
        u.source_unit_id: {"numeric": len(numeric_inventory(u)), "qualifier": len(qualifier_inventory(u))}
        for u in units
    }
    units_by_id = {u.source_unit_id: u for u in units}
    reference: list[dict] = []
    disagreements: list[dict] = []
    for unit in units:
        ua = [r for r in rows_a if r["source_unit_id"] == unit.source_unit_id]
        ub = [r for r in rows_b if r["source_unit_id"] == unit.source_unit_id]
        pairs, only_a, only_b = greedy_align(ua, ub, threshold=0.6)
        for i, j, score in pairs:
            pick = ua[i] if (cue_count(ua[i]), len(ua[i]["proposition"]), ua[i]["proposition"]) >= (
                cue_count(ub[j]), len(ub[j]["proposition"]), ub[j]["proposition"]
            ) else ub[j]
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
        except Exception as exc:  # noqa: BLE001
            keep, rationale = False, f"ADJUDICATION_ERROR:{type(exc).__name__}"
        adjudication_log.append({
            "builder": row["builder"], "source_unit_id": row["source_unit_id"],
            "proposition": row["proposition"], "keep": keep, "rationale": rationale,
        })
        if keep:
            reference.append({**row, "gold_origin": f"ADJUDICATED_{row['builder']}"})

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
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in adjudication_log),
        encoding="utf-8",
    )

    construction_groups = [str(x["independence_group"]) for x in identities]
    construction_models = [str(x["model_alias"]) for x in identities]
    manifest = {
        "benchmark_version": "MACHINES_P0299_P0301_SOURCE_FIRST_v1",
        "gold_label": "MECHANICALLY_CHECKED",
        "source_origin": source_origin,
        "source_pdf_sha256": MACHINES_PILOT_SOURCE_SHA256,
        "source_units_sha256": source_units_sha256,
        "source_unit_count": len(units),
        "source_unit_content_sha256": EXPECTED_UNIT_HASHES,
        "builder_a": {"backend": ab, "model": am, "assertions": len(rows_a), "identity": identities[0]},
        "builder_b": {"backend": bb, "model": bm, "assertions": len(rows_b), "identity": identities[1]},
        "adjudicator": {
            "backend": jb, "model": jm, "items": len(adjudication_log),
            "kept": sum(1 for x in adjudication_log if x["keep"]), "identity": identities[2],
        },
        "gold_construction_independence_groups": construction_groups,
        "gold_construction_models_not_scorable": construction_models,
        "builders_not_scorable": construction_models,
        "agreed_count": sum(1 for r in validated if r["gold_origin"] == "AGREED_A_B"),
        "reference_v1_count": len(validated),
        "reference_v1_sha256": sha256_text(ref_bytes),
        "scoring_reference": "reference_v1.jsonl",
        "scoring_reference_sha256": sha256_text(ref_bytes),
        "mechanically_dropped": len(dropped_mechanical),
        "deterministic_inventories": inventories,
        "challenge_pass": "NOT_RUN_REFERENCE_V2_NOT_IMPLEMENTED",
        "duration_seconds": round(time.time() - started, 1),
        "claim_boundary": (
            "AI-authored source-first gold, label MECHANICALLY_CHECKED. Exact governed Machines source bytes only; "
            "three empirical independent gold-construction families; historical challenge expansion NOT_RUN. "
            "This bounds benchmark claims, not clinical truth."
        ),
    }
    (out_dir / "GOLD_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "reference_v1_count": manifest["reference_v1_count"],
        "agreed_count": manifest["agreed_count"],
        "reference_v1_sha256": manifest["reference_v1_sha256"],
        "gold_construction_independence_groups": construction_groups,
        "duration_seconds": manifest["duration_seconds"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
