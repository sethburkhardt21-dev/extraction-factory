"""One-unit smoke of each configured backend before authorizing a full pilot run.

The repository intentionally does not bundle copyrighted Machines source text.
Supply either --source-units or --source-pdf. For --source-pdf the hash-pinned
Machines pilot is reconstructed locally, then one source unit is sent through
the exact production provider wrapper/JSON bridge. This smoke never touches the
ledger and MUST return nonzero when any configured provider fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hermes_factory.cold_audit_semantic import build_audit_request  # noqa: E402
from hermes_factory.hashing import sha256_text  # noqa: E402
from hermes_factory.ingest import reconstruct_machines_pilot  # noqa: E402
from hermes_factory.models import AssertionCandidate, SourceUnit  # noqa: E402
from hermes_factory.semantic import build_primary_request, build_blind_request  # noqa: E402

DEFAULT_UNITS = ROOT / "PILOTS" / "MACHINES_P0299_P0301_TURN09" / "SOURCE_UNITS" / "source_units.jsonl"
SCRIPT = ROOT / "providers_ext" / "llm_provider.py"


def call(cmd: list[str], request: dict, timeout: int) -> tuple[float, dict | None, str]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        input=json.dumps(request, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    dur = time.time() - started
    if proc.returncode != 0:
        return dur, None, f"rc={proc.returncode} stderr={proc.stderr[-500:]}"
    try:
        return dur, json.loads(proc.stdout), ""
    except json.JSONDecodeError as exc:
        return dur, None, f"stdout_not_json:{exc} head={proc.stdout[:300]}"


def _first_unit(source_units: Path) -> SourceUnit:
    lines = [x for x in source_units.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not lines:
        raise RuntimeError(f"source_units_empty:{source_units}")
    return SourceUnit.from_dict(json.loads(lines[0]))


def _load_smoke_unit(source_units: str | None, source_pdf: str | None) -> SourceUnit:
    if source_units:
        p = Path(source_units)
        if not p.exists():
            raise RuntimeError(f"source_units_not_found:{p}")
        return _first_unit(p)
    if DEFAULT_UNITS.exists():
        return _first_unit(DEFAULT_UNITS)
    if not source_pdf:
        raise RuntimeError(
            "rights_safe_checkout_has_no_bundled_source_units; supply --source-pdf pointing to the "
            "hash-pinned Machines textbook or --source-units pointing to owner-controlled source units"
        )
    pdf = Path(source_pdf)
    if not pdf.exists():
        raise RuntimeError(f"source_pdf_not_found:{pdf}")
    with tempfile.TemporaryDirectory() as td:
        reconstructed = Path(td) / "machines_smoke_units.jsonl"
        reconstruct_machines_pilot(pdf, reconstructed)
        return _first_unit(reconstructed)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", default="claude:claude-opus-5", help="backend:model or 'skip'")
    ap.add_argument("--blind", default="ollama:gpt-oss:20b", help="backend:model or 'skip'")
    ap.add_argument("--audit", default="ollama:deepseek-r1:14b", help="backend:model or 'skip'")
    ap.add_argument("--source-units", help="owner-controlled source_units.jsonl; first unit is used")
    ap.add_argument("--source-pdf", help="hash-pinned Machines PDF; pilot units are reconstructed locally")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--think", choices=["false", "low", "medium", "high"],
                    help="passed to the wrapper as --ollama-think for ollama specs")
    args = ap.parse_args()
    think_flags = ["--ollama-think", args.think] if args.think else []

    try:
        unit = _load_smoke_unit(args.source_units, args.source_pdf)
    except Exception as exc:
        print(f"SMOKE_SOURCE_FAILED: {type(exc).__name__}:{exc}", file=sys.stderr)
        return 2

    def spec(value: str) -> tuple[str, str]:
        backend, sep, model = value.partition(":")
        if not sep or not backend or not model:
            raise ValueError(f"provider spec must be backend:model, got {value!r}")
        return backend, model

    print(f"unit: {unit.source_unit_id} content_chars={len(unit.content)}", flush=True)
    py = sys.executable
    backends = []
    failures = 0

    try:
        if args.primary != "skip":
            b, m = spec(args.primary)
            extra = think_flags if b == "ollama" else []
            backends.append((
                f"PRIMARY {b}/{m}",
                [py, "-B", str(SCRIPT), "--backend", b, "--model", m, "--timeout", str(args.timeout)] + extra,
                build_primary_request(unit, "CAP-SMOKE", "RUN-SMOKE"),
                args.timeout + 60,
            ))
        if args.blind != "skip":
            b, m = spec(args.blind)
            extra = think_flags if b == "ollama" else []
            backends.append((
                f"BLIND {b}/{m}",
                [py, "-B", str(SCRIPT), "--backend", b, "--model", m, "--timeout", str(args.timeout)] + extra,
                build_blind_request(unit, "CAP-SMOKE", "RUN-SMOKE"),
                args.timeout + 60,
            ))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for name, cmd, request, timeout in backends:
        try:
            dur, out, err = call(cmd, request, timeout)
        except Exception as exc:
            print(f"{name}: TIMEOUT/ERROR — {type(exc).__name__}:{exc}", flush=True)
            failures += 1
            continue
        if out is None:
            print(f"{name}: FAILED after {dur:.1f}s — {err}", flush=True)
            failures += 1
            continue
        receipt = out.get("provider_receipt", {})
        assertions = out.get("assertions", [])
        print(
            f"{name}: {dur:.1f}s emitted={len(assertions)} "
            f"rejected={receipt.get('rejected_count')} attempts={receipt.get('attempts')}",
            flush=True,
        )
        for rj in (out.get("provider_diagnostics", {}).get("rejected") or [])[:3]:
            print(f"   rejected[{rj.get('ordinal')}] {rj.get('reason')}: {rj.get('evidence_head', '')[:120]}", flush=True)
        if assertions:
            a = assertions[0]
            print(f"   sample proposition: {a['proposition'][:140]}", flush=True)
            print(f"   sample evidence:    {a['evidence'][:140]}", flush=True)

    if args.audit != "skip":
        try:
            audit_backend, audit_model = spec(args.audit)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        first_sentence = unit.content.split(". ")[0]
        evidence = first_sentence if first_sentence.endswith(".") else first_sentence + "."
        if evidence not in unit.content:
            evidence = unit.content[: min(len(unit.content), 300)]
        cand = AssertionCandidate(
            candidate_id="CAND-SMOKE",
            source_unit_id=unit.source_unit_id,
            source_id=unit.source_id,
            source_version_id=unit.source_version_id,
            source_sha256=unit.source_sha256,
            locator=unit.locator,
            evidence=evidence,
            evidence_sha256=sha256_text(evidence),
            proposition=evidence,
            originating_capsule_id="CAP-SMOKE",
            originating_run_id="RUN-SMOKE",
            parent_artifact_sha256="GENESIS",
        )
        audit_req = build_audit_request(cand, unit, "RUN-SMOKE")
        extra = think_flags if audit_backend == "ollama" else []
        try:
            dur, out, err = call(
                [py, "-B", str(SCRIPT), "--backend", audit_backend, "--model", audit_model,
                 "--timeout", str(args.timeout)] + extra,
                audit_req,
                args.timeout + 60,
            )
        except Exception as exc:
            print(f"COLD_AUDIT {audit_model}: TIMEOUT/ERROR — {type(exc).__name__}:{exc}", flush=True)
            failures += 1
        else:
            if out is None:
                print(f"COLD_AUDIT {audit_model}: FAILED after {dur:.1f}s — {err}", flush=True)
                failures += 1
            else:
                print(f"COLD_AUDIT {audit_model}: {dur:.1f}s verdict={json.dumps(out.get('verdict'))[:300]}", flush=True)

    if failures:
        print(f"SMOKE_FAILED configured_provider_failures={failures}", file=sys.stderr)
        return 1
    print("SMOKE_PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
