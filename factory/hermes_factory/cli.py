from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path

from .build_integrity import certify_build, write_current_manifest
from .controller import run_factory
from .ledger import Ledger
from .ingest import ingest_pdf, reconstruct_machines_pilot
from .package import build_offline_package, verify_offline_package
from .preflight import run_preflight
from .providers.command import JSONCommandProvider
from .providers.fixture import DeterministicFixtureProvider
from .runtime_lock import write_runtime_lock
from .model_registry import load_registry, resolve_model_identity
from .test_runner import run_tests


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _provider_from_args(args, role: str):
    prefix = {"PRIMARY": "primary", "BLIND_RECALL": "blind", "COLD_AUDIT": "cold"}[role]
    if args.mode == "offline-fixture":
        # No fixture cold auditor exists: a fixture cannot audit semantics, so the
        # gate must stay BLOCKED_EXTERNAL rather than pretend.
        return None if role == "COLD_AUDIT" else DeterministicFixtureProvider(role=role)
    command = getattr(args, prefix + "_command")
    if not command:
        if role == "COLD_AUDIT":
            return None
        raise SystemExit(f"{role} provider command required for mode {args.mode}")
    local = bool(getattr(args, prefix + "_local") or args.local_provider)
    provider_name = getattr(args, prefix + "_provider")
    model_alias = getattr(args, prefix + "_model")
    registry = load_registry(project_root() / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json")
    resolved = resolve_model_identity(registry, provider_name, model_alias)
    declared_family = getattr(args, prefix + "_family")
    if declared_family not in (None, "", "UNCONFIGURED", resolved["underlying_family"]):
        raise SystemExit(
            f"declared model family {declared_family!r} conflicts with authoritative registry "
            f"family {resolved['underlying_family']!r} for {provider_name}|{model_alias}"
        )
    return JSONCommandProvider(
        command,
        provider=resolved["provider"],
        model_alias=model_alias,
        underlying_family=resolved["underlying_family"],
        observed_version=getattr(args, prefix + "_version"),
        role=role,
        timeout_seconds=args.provider_timeout,
        network_required=not local,
        certification_status="UNBENCHMARKED",
        empirical_semantic_model=resolved["empirical_semantic_model"],
    )


def cmd_test(args):
    report = run_tests(project_root())
    print(json.dumps({"overall": report["overall"], "duration_seconds": report["duration_seconds"]}, indent=2))
    return 0 if report["overall"] == "PASS" else 1


def cmd_verify(args):
    report = run_preflight(project_root(), run_tests=not args.skip_tests)
    print((project_root() / "CURRENT" / "PREFLIGHT.txt").read_text(encoding="utf-8"))
    return 0 if report["overall"] == "PASS" else 1


def cmd_certify(args):
    root = project_root()
    test_report = root / "CURRENT" / "TEST_REPORT.json"
    if not test_report.exists() or args.rerun_tests:
        report = run_tests(root)
        if report["overall"] != "PASS":
            print("Tests failed; refusing certification", file=sys.stderr)
            return 1
    lock = root / "CURRENT" / "RUNTIME_LOCK.json"
    if not lock.exists() or args.refresh_runtime_lock:
        write_runtime_lock(lock)
    cert_dir = root / "CURRENT" / "CERTIFICATIONS"
    cert_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(cert_dir.glob("CERTIFIED_BUILD_MANIFEST_*.json"))
    target = cert_dir / f"CERTIFIED_BUILD_MANIFEST_{len(existing)+1:04d}.json"
    cert = certify_build(root, target, test_report_path=test_report,
                         parent_certification_id=None if not existing else json.loads(existing[-1].read_text())["certification_id"])
    canonical = root / "CURRENT" / "CERTIFIED_BUILD_MANIFEST.json"
    shutil.copy2(target, canonical)
    write_current_manifest(root, root / "CURRENT" / "CURRENT_BUILD_MANIFEST.json")
    print(json.dumps({"certification_id": cert["certification_id"], "manifest_sha256": cert["production_code_manifest_sha256"], "path": str(target)}, indent=2))
    return 0


def cmd_run(args):
    root = project_root()
    ingestion = None
    if args.pilot == "machines":
        source_units = root / "PILOTS" / "MACHINES_P0299_P0301_TURN09" / "SOURCE_UNITS" / "source_units.jsonl"
        source_pdf = Path(args.source_pdf) if args.source_pdf else Path("/mnt/data/Machines Textbook.pdf")
        source_sha = "379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197"
        if not source_pdf.exists():
            source_pdf = None
        if not source_units.exists():
            if source_pdf is None:
                raise SystemExit(
                    "Machines pilot source units are not bundled. Supply --source-pdf pointing to the hash-pinned "
                    "Machines textbook so pages 299-301 can be reconstructed locally."
                )
            ingest_dir = Path(args.output or (root / "OUTPUTS")) / "INGESTED_SOURCE_UNITS"
            ingest_dir.mkdir(parents=True, exist_ok=True)
            source_units = ingest_dir / "MACHINES_P0299_P0301_reconstructed.jsonl"
            ingestion = reconstruct_machines_pilot(source_pdf, source_units)
    else:
        source_pdf = Path(args.source_pdf) if args.source_pdf else None
        if args.source_units:
            source_units = Path(args.source_units)
            source_sha = args.source_sha256
        elif source_pdf:
            ingest_dir = Path(args.output or (root / "OUTPUTS")) / "INGESTED_SOURCE_UNITS"
            ingest_dir.mkdir(parents=True, exist_ok=True)
            source_units = ingest_dir / (source_pdf.stem.replace(" ", "_") + "_source_units.jsonl")
            ingestion = ingest_pdf(source_pdf, source_units, page_spec=args.pages, source_id=args.source_id)
            source_sha = ingestion["source_sha256"]
        else:
            raise SystemExit("Provide --source-units or --source-pdf unless --pilot machines")
    if args.profile:
        args.workers = {"SAFE_4":4,"BALANCED_8":8,"HIGH_12":12}[args.profile]
    primary = _provider_from_args(args, "PRIMARY")
    blind = _provider_from_args(args, "BLIND_RECALL")
    cold = _provider_from_args(args, "COLD_AUDIT")
    output = Path(args.output or (root / "OUTPUTS"))
    result = run_factory(
        project_root=root,
        source_units_path=source_units,
        primary_provider=primary,
        blind_provider=blind,
        output_root=output,
        source_pdf=source_pdf,
        source_expected_sha256=source_sha,
        database_09d=Path(args.database_09d) if args.database_09d else None,
        cold_audit_rate=args.cold_audit_rate,
        mode=args.mode.upper().replace("-", "_"),
        execution_mode=args.execution_mode,
        workers=args.workers,
        cold_audit_provider=cold,
    )
    if ingestion is not None:
        result["ingestion"] = ingestion
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_status(args):
    run_dir = Path(args.run_dir)
    ledger_path = run_dir / "STATE" / "ledger.sqlite"
    if not ledger_path.exists():
        raise SystemExit("ledger.sqlite not found")
    ledger = Ledger(ledger_path)
    snap = ledger.snapshot()
    ledger.close()
    readiness = None
    rp = run_dir / "VALIDATION" / "readiness.json"
    if rp.exists(): readiness = json.loads(rp.read_text(encoding="utf-8"))
    counts = {}
    for w in snap["work_items"]:
        counts[w["state"]] = counts.get(w["state"], 0) + 1
    print(json.dumps({"run_dir": str(run_dir), "work_state_counts": counts,
                      "event_chain_valid": snap["event_chain_valid"], "state_reconciliation_valid": snap["state_reconciliation_valid"],
                      "readiness": readiness}, indent=2))
    return 0


def cmd_resume(args):
    run_dir = Path(args.run_dir)
    ledger = Ledger(run_dir / "STATE" / "ledger.sqlite")
    expired = ledger.expire_leases()
    snap = ledger.snapshot()
    ledger.close()
    ready = [x["work_id"] for x in snap["work_items"] if x["state"] == "READY"]
    print(json.dumps({
        "expired_leases_requeued": expired,
        "ready_work": ready,
        "event_chain_valid": snap["event_chain_valid"],
        "state_reconciliation_valid": snap["state_reconciliation_valid"],
        "note": "State recovery is complete. Semantic redispatch requires rerunning with the configured provider; accepted work is never overwritten.",
    }, indent=2))
    return 0 if snap["event_chain_valid"] and snap["state_reconciliation_valid"] else 1


def cmd_package(args):
    run_dir = Path(args.run_dir)
    readiness = json.loads((run_dir / "VALIDATION" / "readiness.json").read_text(encoding="utf-8"))
    zip_path = Path(args.output or (run_dir.parent / f"{readiness['status']}_{run_dir.name}.zip"))
    result = build_offline_package(run_dir, zip_path, package_status=readiness["status"])
    print(json.dumps(result, indent=2))
    return 0


def cmd_verify_package(args):
    result = verify_offline_package(Path(args.zip_path))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def cmd_ingest_pdf(args):
    root = project_root()
    output = Path(args.output or (root / "OUTPUTS" / (Path(args.source_pdf).stem.replace(" ", "_") + "_source_units.jsonl")))
    result = ingest_pdf(Path(args.source_pdf), output, page_spec=args.pages, source_id=args.source_id)
    print(json.dumps(result, indent=2))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="hermes_factory", description="Hermes Extraction Factory advanced runtime")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("test"); t.set_defaults(func=cmd_test)
    ing = sub.add_parser("ingest-pdf")
    ing.add_argument("source_pdf")
    ing.add_argument("--pages")
    ing.add_argument("--source-id")
    ing.add_argument("--output")
    ing.set_defaults(func=cmd_ingest_pdf)
    v = sub.add_parser("verify"); v.add_argument("--skip-tests", action="store_true"); v.set_defaults(func=cmd_verify)
    c = sub.add_parser("certify-build"); c.add_argument("--rerun-tests", action="store_true"); c.add_argument("--refresh-runtime-lock", action="store_true"); c.set_defaults(func=cmd_certify)

    r = sub.add_parser("run")
    r.add_argument("--pilot", choices=["machines"])
    r.add_argument("--source-units")
    r.add_argument("--source-pdf")
    r.add_argument("--source-sha256")
    r.add_argument("--pages", help="PDF pages such as 1-20,25,30-32 for automatic ingestion")
    r.add_argument("--source-id")
    r.add_argument("--database-09d")
    r.add_argument("--output")
    r.add_argument("--cold-audit-rate", type=float, default=0.25)
    r.add_argument("--execution-mode", choices=["LOCAL_ONLY","CLOUD_MODEL","HYBRID"], default="LOCAL_ONLY")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--profile", choices=["SAFE_4","BALANCED_8","HIGH_12"])
    r.add_argument("--mode", choices=["offline-fixture", "external-command"], default="offline-fixture")
    r.add_argument("--primary-command")
    r.add_argument("--blind-command")
    r.add_argument("--primary-provider", default="UNCONFIGURED")
    r.add_argument("--primary-model", default="UNCONFIGURED")
    r.add_argument("--primary-family", default="UNCONFIGURED")
    r.add_argument("--primary-version", default="UNKNOWN")
    r.add_argument("--blind-provider", default="UNCONFIGURED")
    r.add_argument("--blind-model", default="UNCONFIGURED")
    r.add_argument("--blind-family", default="UNCONFIGURED")
    r.add_argument("--blind-version", default="UNKNOWN")
    r.add_argument("--cold-command")
    r.add_argument("--cold-provider", default="UNCONFIGURED")
    r.add_argument("--cold-model", default="UNCONFIGURED")
    r.add_argument("--cold-family", default="UNCONFIGURED")
    r.add_argument("--cold-version", default="UNKNOWN")
    r.add_argument("--local-provider", action="store_true")
    r.add_argument("--primary-local", action="store_true")
    r.add_argument("--blind-local", action="store_true")
    r.add_argument("--cold-local", action="store_true")
    r.add_argument("--provider-timeout", type=int, default=600,
                   help="seconds the controller waits on one provider command (wrapper timeouts should be lower)")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("status"); s.add_argument("--run-dir", required=True); s.set_defaults(func=cmd_status)
    rr = sub.add_parser("resume"); rr.add_argument("--run-dir", required=True); rr.set_defaults(func=cmd_resume)
    pk = sub.add_parser("package"); pk.add_argument("--run-dir", required=True); pk.add_argument("--output"); pk.set_defaults(func=cmd_package)
    vp = sub.add_parser("verify-package"); vp.add_argument("zip_path"); vp.set_defaults(func=cmd_verify_package)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)
