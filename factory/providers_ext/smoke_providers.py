"""One-unit smoke of each real backend before authorizing a full pilot run.

Reads the first pilot source unit, sends a PRIMARY request to each configured
backend, and a COLD_AUDIT request to the auditor backend, printing durations,
emitted/rejected counts, and a sample assertion. Exercises the same wrapper
script and JSON bridge the factory run will use. Never touches the ledger.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hermes_factory.models import SourceUnit  # noqa: E402
from hermes_factory.semantic import build_primary_request, build_blind_request  # noqa: E402
from hermes_factory.cold_audit_semantic import build_audit_request  # noqa: E402
from hermes_factory.models import AssertionCandidate  # noqa: E402

UNITS = ROOT / "PILOTS" / "MACHINES_P0299_P0301_TURN09" / "SOURCE_UNITS" / "source_units.jsonl"
SCRIPT = ROOT / "providers_ext" / "llm_provider.py"


def call(cmd: list[str], request: dict, timeout: int) -> tuple[float, dict | None, str]:
    started = time.time()
    proc = subprocess.run(cmd, input=json.dumps(request, ensure_ascii=False),
                          capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    dur = time.time() - started
    if proc.returncode != 0:
        return dur, None, f"rc={proc.returncode} stderr={proc.stderr[-500:]}"
    try:
        return dur, json.loads(proc.stdout), ""
    except json.JSONDecodeError as exc:
        return dur, None, f"stdout_not_json:{exc} head={proc.stdout[:300]}"


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", default="claude:claude-opus-5", help="backend:model or 'skip'")
    ap.add_argument("--blind", default="ollama:gpt-oss:20b", help="backend:model or 'skip'")
    ap.add_argument("--audit", default="ollama:deepseek-r1:14b", help="backend:model or 'skip'")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    def spec(value: str):
        backend, _, model = value.partition(":")
        return backend, model

    unit_raw = json.loads(UNITS.read_text(encoding="utf-8").splitlines()[0])
    unit = SourceUnit.from_dict(unit_raw)
    print(f"unit: {unit.source_unit_id} content_chars={len(unit.content)}", flush=True)
    py = sys.executable

    backends = []
    if args.primary != "skip":
        b, m = spec(args.primary)
        backends.append((f"PRIMARY {b}/{m}", [py, "-B", str(SCRIPT), "--backend", b, "--model", m, "--timeout", str(args.timeout)],
                         build_primary_request(unit, "CAP-SMOKE", "RUN-SMOKE"), args.timeout + 60))
    if args.blind != "skip":
        b, m = spec(args.blind)
        backends.append((f"BLIND {b}/{m}", [py, "-B", str(SCRIPT), "--backend", b, "--model", m, "--timeout", str(args.timeout)],
                         build_blind_request(unit, "CAP-SMOKE", "RUN-SMOKE"), args.timeout + 60))
    results = {}
    for name, cmd, request, timeout in backends:
        try:
            dur, out, err = call(cmd, request, timeout)
        except Exception as exc:  # subprocess.TimeoutExpired etc — keep probing the rest
            print(f"{name}: TIMEOUT/ERROR — {type(exc).__name__}", flush=True)
            results[name] = None
            continue
        if out is None:
            print(f"{name}: FAILED after {dur:.1f}s — {err}", flush=True)
            results[name] = None
            continue
        receipt = out.get("provider_receipt", {})
        assertions = out.get("assertions", [])
        print(f"{name}: {dur:.1f}s emitted={len(assertions)} rejected={receipt.get('rejected_count')} attempts={receipt.get('attempts')}", flush=True)
        if assertions:
            a = assertions[0]
            print(f"   sample proposition: {a['proposition'][:140]}", flush=True)
            print(f"   sample evidence:    {a['evidence'][:140]}", flush=True)
        results[name] = (dur, len(assertions))

    if args.audit == "skip":
        return 0
    audit_backend, audit_model = spec(args.audit)
    cand = AssertionCandidate(
        candidate_id="CAND-SMOKE", source_unit_id=unit.source_unit_id, source_id=unit.source_id,
        source_version_id=unit.source_version_id, source_sha256=unit.source_sha256, locator=unit.locator,
        evidence=unit.content.split(". ")[0] + ".", evidence_sha256="0" * 64,
        proposition=unit.content.split(". ")[0] + ".",
        originating_capsule_id="CAP-SMOKE", originating_run_id="RUN-SMOKE", parent_artifact_sha256="GENESIS",
    )
    audit_req = build_audit_request(cand, unit, "RUN-SMOKE")
    try:
        dur, out, err = call([py, "-B", str(SCRIPT), "--backend", audit_backend, "--model", audit_model, "--timeout", str(args.timeout)],
                             audit_req, args.timeout + 60)
    except Exception as exc:
        print(f"COLD_AUDIT {audit_model}: TIMEOUT/ERROR — {type(exc).__name__}", flush=True)
        return 0
    if out is None:
        print(f"COLD_AUDIT {audit_model}: FAILED after {dur:.1f}s — {err}", flush=True)
    else:
        print(f"COLD_AUDIT {audit_model}: {dur:.1f}s verdict={json.dumps(out.get('verdict'))[:300]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
