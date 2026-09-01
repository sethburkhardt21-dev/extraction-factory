"""One canonical start command for the integrated frontier extraction factory.

    python run_appliance.py --profile SAFE_4 \
        --primary claude:claude-opus-5 \
        --blind   ollama:nuextract3-q8:latest \
        --cold    ollama:deepseek-r1:14b

Chain: certified Hermes runtime (register → lease → dispatch → blind allowlist →
stage → CAS commit → union → families → specialists → precision → routing →
deterministic + independent semantic cold audit → readiness) → read-only 09D
comparison → schema-aware non-writing Motion-2 projection → numeric context guard
→ final self-contained offline review ZIP.

Provider specs are backend:model (preferred) or legacy backend:model:FAMILY.
Model family/independence are resolved from the protected model registry, never
trusted from CLI text. A legacy FAMILY suffix is treated only as an assertion and
must match the registry or the run is rejected.

The operator experience: start it, leave it, return to a governed review
package whose readiness status was derived fail-closed by the factory, never
authored by a model or by this script.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parent
DEFAULT_09D = (
    FACTORY_ROOT.parents[1] / "releases" / "r3" / "Project_09D_Milestone_A_v2"
    / "Project_09D_Milestone_A_Verified_Evidence_Checkpoint_v2" / "database" / "final_s03.sqlite"
)
DEFAULT_BOOK = Path(r"C:\Users\sethb\Downloads\School Resources\Machines Textbook.pdf")


def parse_spec(value: str) -> tuple[str, str, str | None]:
    backend, sep, rest = value.partition(":")
    if not sep or not backend or not rest:
        raise SystemExit(f"provider spec must be backend:model or backend:model:FAMILY — got {value!r}")
    model, family = rest, None
    maybe_model, sep2, maybe_family = rest.rpartition(":")
    if sep2 and maybe_family and maybe_family.replace("_", "").isalnum() and maybe_family.upper() == maybe_family:
        model, family = maybe_model, maybe_family
    return backend, model, family


def provider_flags(prefix: str, spec: str, timeout: int, ollama_think: str | None = None,
                   ollama_keep_alive: str = "30m") -> list[str]:
    backend, model, family = parse_spec(spec)
    command = (
        f'"{sys.executable}" -B "{FACTORY_ROOT / "providers_ext" / "llm_provider.py"}" '
        f"--backend {backend} --model {model} --timeout {timeout}"
    )
    if backend == "ollama" and ollama_think:
        command += f" --ollama-think {ollama_think}"
    if backend == "ollama":
        command += f" --ollama-keep-alive {ollama_keep_alive}"
    flags = [
        f"--{prefix}-command", command,
        f"--{prefix}-provider", backend.upper(),
        f"--{prefix}-model", model,
        f"--{prefix}-version", "CLI_OBSERVED",
    ]
    if family:
        flags += [f"--{prefix}-family", family]
    if backend == "ollama":
        flags.append(f"--{prefix}-local")
    return flags


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="run_appliance", description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=["SAFE_4", "BALANCED_8", "HIGH_12"], default="SAFE_4")
    parser.add_argument("--primary", required=True, help="backend:model (legacy backend:model:FAMILY is verified against registry)")
    parser.add_argument("--blind", required=True, help="backend:model (legacy backend:model:FAMILY is verified against registry)")
    parser.add_argument("--cold", help="backend:model (independent cold auditor; family comes from registry)")
    parser.add_argument("--pilot", choices=["machines"], help="use the bundled Machines p299-301 pilot")
    parser.add_argument("--source-pdf")
    parser.add_argument("--pages")
    parser.add_argument("--source-id")
    parser.add_argument("--database-09d", default=str(DEFAULT_09D))
    parser.add_argument("--output", default=str(FACTORY_ROOT.parent / "runs"))
    parser.add_argument("--cold-audit-rate", type=float, default=0.25)
    parser.add_argument("--timeout-per-call", type=int, default=900)
    parser.add_argument("--ollama-think", choices=["false", "low", "medium", "high"],
                        help="thinking control applied to every ollama provider in this run")
    parser.add_argument("--provider-schedule", choices=["auto", "parallel", "phased"], default="auto",
                        help="auto phases different local models to prevent Ollama VRAM/model-swap thrash")
    parser.add_argument("--primary-concurrency", type=int)
    parser.add_argument("--blind-concurrency", type=int)
    parser.add_argument("--cold-concurrency", type=int, default=1)
    parser.add_argument("--ollama-keep-alive", default="30m")
    parser.add_argument("--skip-compare", action="store_true")
    parser.add_argument("--skip-09d-projection", action="store_true",
                        help="skip the schema-aware non-writing Motion-2 handoff projection")
    args = parser.parse_args(argv)

    started = time.time()
    run_cmd = [sys.executable, "-B", "-m", "hermes_factory", "run",
               "--mode", "external-command", "--execution-mode", "HYBRID",
               "--profile", args.profile, "--cold-audit-rate", str(args.cold_audit_rate),
               "--provider-schedule", args.provider_schedule.upper(),
               "--cold-concurrency", str(args.cold_concurrency),
               "--output", args.output]
    if args.primary_concurrency is not None:
        run_cmd += ["--primary-concurrency", str(args.primary_concurrency)]
    if args.blind_concurrency is not None:
        run_cmd += ["--blind-concurrency", str(args.blind_concurrency)]
    if args.pilot:
        run_cmd += ["--pilot", args.pilot]
        source_pdf = args.source_pdf or (str(DEFAULT_BOOK) if DEFAULT_BOOK.exists() else None)
        if source_pdf:
            run_cmd += ["--source-pdf", source_pdf]
    else:
        if not args.source_pdf:
            raise SystemExit("provide --pilot machines or --source-pdf")
        run_cmd += ["--source-pdf", args.source_pdf]
        if args.pages:
            run_cmd += ["--pages", args.pages]
        if args.source_id:
            run_cmd += ["--source-id", args.source_id]
    if args.database_09d and not args.skip_compare:
        run_cmd += ["--database-09d", args.database_09d]
    run_cmd += ["--provider-timeout", str(args.timeout_per_call + 90)]
    run_cmd += provider_flags("primary", args.primary, args.timeout_per_call, args.ollama_think, args.ollama_keep_alive)
    run_cmd += provider_flags("blind", args.blind, args.timeout_per_call, args.ollama_think, args.ollama_keep_alive)
    if args.cold:
        run_cmd += provider_flags("cold", args.cold, args.timeout_per_call, args.ollama_think, args.ollama_keep_alive)

    print(f"[appliance] launching factory run ({args.profile}) ...", flush=True)
    proc = subprocess.run(run_cmd, cwd=FACTORY_ROOT, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:], file=sys.stderr)
        print(f"[appliance] factory run FAILED rc={proc.returncode}", file=sys.stderr)
        return proc.returncode
    result = json.loads(proc.stdout[proc.stdout.index("{"):])
    run_dir = Path(result["run_dir"])
    status = result["readiness"]["status"]
    print(f"[appliance] factory run complete: {result['run_id']} status={status}", flush=True)

    comparison_summary = None
    projection_summary = None
    context_guard_summary = None
    comparison_ok = False
    if args.database_09d and not args.skip_compare:
        print("[appliance] running read-only 09D comparison ...", flush=True)
        cmp_proc = subprocess.run(
            [sys.executable, "-B", str(FACTORY_ROOT / "stages_ext" / "compare_09d.py"),
             "--run-dir", str(run_dir), "--database", args.database_09d],
            capture_output=True, text=True, encoding="utf-8")
        if cmp_proc.returncode != 0:
            print(cmp_proc.stderr[-2000:], file=sys.stderr)
            print("[appliance] 09D comparison FAILED; run artifacts remain valid without it", file=sys.stderr)
        else:
            comparison_ok = True
            comparison_summary = json.loads(
                (run_dir / "09D" / "comparison_09d_summary.json").read_text(encoding="utf-8"))
            print(f"[appliance] 09D comparison states: {comparison_summary['state_counts']}", flush=True)

    if args.database_09d and comparison_ok and not args.skip_09d_projection:
        print("[appliance] building non-writing 09D Motion-2 projection ...", flush=True)
        proj_proc = subprocess.run(
            [sys.executable, "-B", str(FACTORY_ROOT / "stages_ext" / "project_09d_motion2.py"),
             "--run-dir", str(run_dir), "--database", args.database_09d],
            capture_output=True, text=True, encoding="utf-8")
        if proj_proc.returncode != 0:
            print(proj_proc.stderr[-2000:], file=sys.stderr)
            print("[appliance] 09D projection requires review; comparison artifacts remain valid", file=sys.stderr)
        summary_path = run_dir / "09D" / "motion2_projection_summary.json"
        candidate_projection_path = run_dir / "09D" / "motion2_candidate_projection.jsonl"
        if summary_path.exists() and candidate_projection_path.exists():
            projection_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            print(f"[appliance] 09D projection: {projection_summary['projection_status']}", flush=True)

            print("[appliance] running 09D numeric context guard ...", flush=True)
            guard_proc = subprocess.run(
                [sys.executable, "-B", str(FACTORY_ROOT / "stages_ext" / "guard_09d_numeric_context.py"),
                 "--run-dir", str(run_dir)],
                capture_output=True, text=True, encoding="utf-8")
            if guard_proc.returncode != 0:
                print(guard_proc.stderr[-2000:], file=sys.stderr)
                print("[appliance] 09D numeric context guard FAILED; projection remains review-only", file=sys.stderr)
            guard_summary_path = run_dir / "09D" / "motion2_numeric_context_guard_summary.json"
            if guard_summary_path.exists():
                context_guard_summary = json.loads(guard_summary_path.read_text(encoding="utf-8"))
                projection_summary = json.loads(summary_path.read_text(encoding="utf-8"))
                print(
                    f"[appliance] 09D context guard review count: {context_guard_summary['review_required_count']}",
                    flush=True,
                )

    print("[appliance] building final offline review package ...", flush=True)
    final_zip = run_dir.parent / f"APPLIANCE_{status}_{run_dir.name}.zip"
    pkg_proc = subprocess.run(
        [sys.executable, "-B", "-m", "hermes_factory", "package",
         "--run-dir", str(run_dir), "--output", str(final_zip)],
        cwd=FACTORY_ROOT, capture_output=True, text=True, encoding="utf-8")
    package_ok = pkg_proc.returncode == 0
    verify_ok = None
    if package_ok:
        ver_proc = subprocess.run(
            [sys.executable, "-B", "-m", "hermes_factory", "verify-package", str(final_zip)],
            cwd=FACTORY_ROOT, capture_output=True, text=True, encoding="utf-8")
        verify_ok = ver_proc.returncode == 0

    outcome = {
        "run_id": result["run_id"],
        "run_dir": str(run_dir),
        "readiness_status": status,
        "readiness_blockers": result["readiness"]["blockers"],
        "bounded_review_queues": result["readiness"]["bounded_review_queues"],
        "summary": result["summary"],
        "comparison_09d": (comparison_summary or {}).get("state_counts"),
        "comparison_09d_confidence": (comparison_summary or {}).get("confidence_counts"),
        "motion2_projection_status": (projection_summary or {}).get("projection_status"),
        "motion2_projection_errors": (projection_summary or {}).get("projection_error_count"),
        "motion2_numeric_context_review_count": (context_guard_summary or {}).get("review_required_count"),
        "motion2_numeric_context_result_counts": (context_guard_summary or {}).get("result_counts"),
        "final_package": str(final_zip) if package_ok else None,
        "final_package_verified": verify_ok,
        "wall_seconds": round(time.time() - started, 1),
    }
    (run_dir / "APPLIANCE_OUTCOME.json").write_text(json.dumps(outcome, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(outcome, indent=2, ensure_ascii=False))
    return 0 if package_ok and (verify_ok is not False) else 1


if __name__ == "__main__":
    sys.exit(main())
