"""One canonical start command for the integrated governed extraction factory.

The core factory owns source/build/runtime/ledger/readiness authority. When 09D
comparison is requested, sealed-target verification, read-only comparison and a
non-writing Motion-2 candidate projection are mandatory appliance stages. A
failure in any requested post-stage downgrades the appliance outcome and cannot
be hidden behind a green core status.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from hermes_factory.hashing import sha256_file
from hermes_factory.package import build_offline_package, verify_offline_package

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


def provider_flags(
    prefix: str,
    spec: str,
    timeout: int,
    ollama_think: str | None = None,
    ollama_keep_alive: str = "30m",
) -> list[str]:
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


def _last_json_object(text: str) -> dict[str, Any]:
    """Parse the final complete JSON object without trusting the first '{'."""
    decoder = json.JSONDecoder()
    positions = [i for i, char in enumerate(text) if char == "{"]
    for start in reversed(positions):
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and not text[start + end:].strip():
            return value
    raise ValueError("no_terminal_json_object_in_factory_stdout")


def _run_stage(command: list[str], *, cwd: Path | None = None) -> tuple[bool, str, str]:
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode == 0, proc.stdout, proc.stderr


def _appliance_status(core_status: str, required_stage_failures: list[dict]) -> str:
    if required_stage_failures:
        return "NOT_READY"
    return core_status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="run_appliance", description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=["SAFE_4", "BALANCED_8", "HIGH_12"], default="SAFE_4")
    parser.add_argument("--primary", required=True, help="backend:model (legacy backend:model:FAMILY is verified against registry)")
    parser.add_argument("--blind", required=True, help="backend:model (legacy backend:model:FAMILY is verified against registry)")
    parser.add_argument("--cold", help="backend:model (independent cold auditor; family comes from registry)")
    parser.add_argument("--pilot", choices=["machines"], help="use the governed Machines p299-301 pilot")
    parser.add_argument("--source-pdf")
    parser.add_argument("--pages")
    parser.add_argument("--source-id")
    parser.add_argument("--database-09d", default=str(DEFAULT_09D))
    parser.add_argument("--output", default=str(FACTORY_ROOT.parent / "runs"))
    parser.add_argument("--cold-audit-rate", type=float, default=0.25)
    parser.add_argument("--timeout-per-call", type=int, default=900)
    parser.add_argument("--ollama-think", choices=["false", "low", "medium", "high"],
                        help="thinking control applied to every Ollama provider in this run")
    parser.add_argument("--provider-schedule", choices=["auto", "parallel", "phased"], default="auto",
                        help="auto phases different local models to prevent Ollama VRAM/model-swap thrash")
    parser.add_argument("--primary-concurrency", type=int)
    parser.add_argument("--blind-concurrency", type=int)
    parser.add_argument("--cold-concurrency", type=int, default=1)
    parser.add_argument("--ollama-keep-alive", default="30m")
    parser.add_argument("--skip-compare", action="store_true",
                        help="explicitly omit all 09D comparison/projection stages; no 09D gate is claimed")
    args = parser.parse_args(argv)

    started = time.time()
    requested_09d = bool(args.database_09d and not args.skip_compare)
    controller_timeout = int(args.timeout_per_call) + 90
    lease_ttl = max(1200, controller_timeout + 300)
    run_cmd = [
        sys.executable, "-B", "-m", "hermes_factory", "run",
        "--mode", "external-command", "--execution-mode", "HYBRID",
        "--profile", args.profile,
        "--cold-audit-rate", str(args.cold_audit_rate),
        "--provider-schedule", args.provider_schedule.upper(),
        "--cold-concurrency", str(args.cold_concurrency),
        "--provider-timeout", str(controller_timeout),
        "--lease-ttl-seconds", str(lease_ttl),
        "--output", args.output,
    ]
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
    if requested_09d:
        # The v1.4 controller verifies sealed identity/schema/witness partition
        # here, before a single provider process is allowed to start.
        run_cmd += ["--database-09d", args.database_09d]
    run_cmd += provider_flags("primary", args.primary, args.timeout_per_call, args.ollama_think, args.ollama_keep_alive)
    run_cmd += provider_flags("blind", args.blind, args.timeout_per_call, args.ollama_think, args.ollama_keep_alive)
    if args.cold:
        run_cmd += provider_flags("cold", args.cold, args.timeout_per_call, args.ollama_think, args.ollama_keep_alive)

    print(f"[appliance] launching governed factory run ({args.profile}) ...", flush=True)
    ok, stdout, stderr = _run_stage(run_cmd, cwd=FACTORY_ROOT)
    if not ok:
        print(stdout[-4000:])
        print(stderr[-4000:], file=sys.stderr)
        print("[appliance] factory run FAILED; no post-stage can upgrade it", file=sys.stderr)
        return 2
    try:
        result = _last_json_object(stdout)
    except Exception as exc:
        print(f"[appliance] cannot parse governed factory result: {exc}", file=sys.stderr)
        return 2
    run_dir = Path(result["run_dir"])
    core_status = result["readiness"]["status"]
    print(f"[appliance] core complete: {result['run_id']} status={core_status}", flush=True)

    required_stage_failures: list[dict] = []
    comparison_summary = None
    projection_summary = None
    if requested_09d:
        print("[appliance] running mandatory read-only 09D comparison ...", flush=True)
        cmp_ok, cmp_out, cmp_err = _run_stage([
            sys.executable, "-B", str(FACTORY_ROOT / "stages_ext" / "compare_09d.py"),
            "--run-dir", str(run_dir), "--database", args.database_09d,
        ])
        if not cmp_ok:
            required_stage_failures.append({
                "stage": "READ_ONLY_09D_COMPARISON",
                "error": cmp_err[-4000:] or cmp_out[-4000:],
            })
            print("[appliance] mandatory 09D comparison FAILED", file=sys.stderr)
        else:
            comparison_summary = json.loads(
                (run_dir / "09D" / "comparison_09d_summary.json").read_text(encoding="utf-8")
            )
            print(f"[appliance] 09D conflict outcomes: {comparison_summary['conflict_outcome_counts']}", flush=True)

        print("[appliance] building mandatory non-writing Motion-2 candidate envelope ...", flush=True)
        proj_ok, proj_out, proj_err = _run_stage([
            sys.executable, "-B", str(FACTORY_ROOT / "stages_ext" / "project_09d_motion2.py"),
            "--run-dir", str(run_dir), "--database", args.database_09d,
        ])
        if not proj_ok:
            required_stage_failures.append({
                "stage": "09D_MOTION2_CANDIDATE_PROJECTION",
                "error": proj_err[-4000:] or proj_out[-4000:],
            })
            print("[appliance] mandatory Motion-2 projection FAILED", file=sys.stderr)
        else:
            projection_summary = json.loads(
                (run_dir / "09D" / "motion2_candidate_envelope_summary.json").read_text(encoding="utf-8")
            )
            print(
                f"[appliance] Motion-2 review envelope: {projection_summary['stable_projected_candidate_count']} stable candidates",
                flush=True,
            )

    status = _appliance_status(core_status, required_stage_failures)
    final_name = (
        f"APPLIANCE_FRONTIER_REVIEW_READY_{run_dir.name}.zip"
        if status == "FRONTIER_REVIEW_READY" else
        f"APPLIANCE_READY_FOR_PROVIDER_{run_dir.name}.zip"
        if status == "READY_FOR_PROVIDER" else
        f"APPLIANCE_REVIEW_PACKAGE_{run_dir.name}.zip"
    )
    final_zip = run_dir.parent / final_name

    # This outcome is written BEFORE packaging so the package cannot claim a
    # status without containing the evidence that derived it.
    outcome = {
        "run_id": result["run_id"],
        "run_dir": str(run_dir),
        "core_readiness_status": core_status,
        "appliance_readiness_status": status,
        "required_09d_stages": requested_09d,
        "required_stage_failures": required_stage_failures,
        "readiness_blockers": result["readiness"]["blockers"],
        "bounded_review_queues": result["readiness"]["bounded_review_queues"],
        "summary": result["summary"],
        "comparison_09d": (comparison_summary or {}).get("state_counts"),
        "conflict_outcomes_09d": (comparison_summary or {}).get("conflict_outcome_counts"),
        "motion2_projection": projection_summary,
        "lease_ttl_seconds": lease_ttl,
        "provider_controller_timeout_seconds": controller_timeout,
        "intended_final_package": str(final_zip),
        "automatic_insert_allowed": False,
        "automatic_promotion_allowed": False,
        "automatic_canonicalization_allowed": False,
        "automatic_selection_allowed": False,
        "wall_seconds_before_packaging": round(time.time() - started, 1),
    }
    outcome_path = run_dir / "APPLIANCE_OUTCOME.json"
    tmp = outcome_path.with_suffix(outcome_path.suffix + ".tmp")
    tmp.write_text(json.dumps(outcome, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(outcome_path)

    print(f"[appliance] building package with appliance status={status} ...", flush=True)
    try:
        package = build_offline_package(run_dir, final_zip, package_status=status)
        verification = verify_offline_package(final_zip)
    except Exception as exc:
        print(f"[appliance] final package failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    if not verification["ok"]:
        print(f"[appliance] final package verification failed: {verification['errors']}", file=sys.stderr)
        return 3

    # External receipt is intentionally outside the ZIP because a ZIP cannot
    # contain its own final hash without changing that hash.
    receipt = {
        "run_id": result["run_id"],
        "appliance_readiness_status": status,
        "package_path": str(final_zip),
        "package_sha256": sha256_file(final_zip),
        "package_verified": True,
        "package_manifest_status": status,
        "required_stage_failures": required_stage_failures,
        "wall_seconds": round(time.time() - started, 1),
    }
    receipt_path = final_zip.with_suffix(final_zip.suffix + ".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"outcome": outcome, "package_receipt": receipt}, indent=2, ensure_ascii=False))

    # A requested 09D stage failure is a real appliance failure even though the
    # review package is preserved for forensic inspection.
    return 0 if not required_stage_failures else 4


if __name__ == "__main__":
    sys.exit(main())
