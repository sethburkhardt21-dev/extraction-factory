"""Executable end-to-end smoke for a clean rights-safe checkout.

This harness proves deterministic plumbing and fail-closed behavior without
claiming semantic-model quality or using the proprietary 09D r3 database. It:

1. creates a tiny synthetic PDF with extractable text;
2. runs the full unit suite, certifies the exact checkout, and verifies preflight;
3. executes the canonical run_appliance entrypoint through the real external
   command bridge using the non-empirical echo backend;
4. checks ledger status/resume, packaged run summary, archive verification, and
   tamper rejection;
5. runs provider-wrapper smoke against the produced source units;
6. creates a synthetic Motion-2-compatible 09D database, proves it remains byte
   unchanged, runs comparison with explicit target-drift allowance, and proves
   strict Motion-2 projection fails closed against the unpinned target;
7. packages and verifies the resulting review artifacts again.

A PASS here is infrastructure evidence only. Real semantic quality and strict
positive 09D authority binding still require the owner-supplied Machines PDF,
real model providers, and the pinned sealed r3 database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], *, cwd: Path = ROOT, expect: int | set[int] = 0) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    allowed = {expect} if isinstance(expect, int) else set(expect)
    if p.returncode not in allowed:
        raise RuntimeError(
            f"command_failed rc={p.returncode} expected={sorted(allowed)}\n"
            f"cmd={' '.join(cmd)}\nstdout={p.stdout[-5000:]}\nstderr={p.stderr[-5000:]}"
        )
    return p


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_minimal_pdf(path: Path) -> None:
    text = (
        "Synthetic validation source. Desflurane MAC is 6.4 percent at 25 C. "
        "Atmospheric pressure is 760 mmHg. Increasing temperature increases vapor pressure."
    )
    stream = f"BT /F1 11 Tf 72 720 Td ({_pdf_escape(text)}) Tj ET\n".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects)+1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    path.write_bytes(bytes(out))


def create_synthetic_09d(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE ingest_source_locator(
                ingest_locator_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                locator_json TEXT NOT NULL
            );
            CREATE TABLE source_assertion_candidate(
                candidate_id TEXT PRIMARY KEY,
                subject_entity_id TEXT,
                predicate_code TEXT,
                value_text TEXT,
                fact_family TEXT,
                source_resource_id TEXT,
                ingest_locator_id TEXT,
                parent_assertion_id TEXT,
                source_locator_id TEXT,
                raw_cell_id TEXT,
                carried_status TEXT,
                carried_confidence_basis TEXT,
                carried_source_era TEXT,
                CONSTRAINT source_assertion_candidate_witness_by_kind CHECK(
                     (source_resource_id IS NOT NULL AND ingest_locator_id IS NULL)
                  OR (source_resource_id IS NULL AND ingest_locator_id IS NOT NULL
                      AND parent_assertion_id IS NULL AND source_locator_id IS NULL
                      AND raw_cell_id IS NULL AND carried_status IS NULL
                      AND carried_confidence_basis IS NULL AND carried_source_era IS NULL)
                )
            );
            CREATE TABLE entity_name(
                canonical_id TEXT,
                name_text TEXT,
                normalized_name TEXT,
                is_searchable INTEGER
            );
            CREATE INDEX idx_candidate_subject_predicate
              ON source_assertion_candidate(subject_entity_id, predicate_code);
            """
        )
        conn.execute("INSERT INTO entity_name VALUES('DES','Desflurane','desflurane',1)")
        conn.execute(
            "INSERT INTO source_assertion_candidate("
            "candidate_id,subject_entity_id,predicate_code,value_text,fact_family,source_resource_id"
            ") VALUES('M1','DES','drug.mac','MAC is 6.4% at 25 C','drug','SRC1')"
        )
        conn.commit()
    finally:
        conn.close()


def _latest_run(runs: Path) -> Path:
    rows = [p for p in runs.glob("HERMES-*") if p.is_dir()]
    if not rows:
        raise RuntimeError("no_run_directory_created")
    return max(rows, key=lambda p: p.stat().st_mtime_ns)


def _tamper_package(good_zip: Path, out_zip: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with zipfile.ZipFile(good_zip) as z:
            z.extractall(root)
        bundle = next(p for p in root.iterdir() if p.is_dir())
        target = bundle / "APPLIANCE_RUN_SUMMARY.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        data["tampered"] = True
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(bundle.rglob("*")):
                if p.is_file():
                    z.write(p, Path(bundle.name) / p.relative_to(bundle))


def validate(work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    runs = work_dir / "runs"
    runs.mkdir(exist_ok=True)
    pdf = work_dir / "synthetic_validation.pdf"
    write_minimal_pdf(pdf)

    report: dict[str, Any] = {
        "schema_version": "hermes-e2e-validation-1.0",
        "started_unix": time.time(),
        "python": sys.version,
        "checks": {},
        "claim_boundary": (
            "Synthetic/echo validation proves deterministic end-to-end plumbing and fail-closed behavior only. "
            "It does not certify semantic precision/recall or positive strict binding to the sealed 09D r3 database."
        ),
    }

    run([PY, "-B", "-m", "hermes_factory", "test"])
    report["checks"]["unit_tests"] = "PASS"

    cert = run([PY, "-B", "-m", "hermes_factory", "certify-build", "--rerun-tests", "--refresh-runtime-lock"])
    report["checks"]["certify_build"] = "PASS"
    report["certification_stdout_tail"] = cert.stdout[-1500:]

    run([PY, "-B", "-m", "hermes_factory", "verify"])
    report["checks"]["preflight_verify"] = "PASS"

    appliance = run([
        PY, "-B", "run_appliance.py",
        "--profile", "SAFE_4",
        "--source-pdf", str(pdf),
        "--pages", "1",
        "--source-id", "SYNTHETIC_E2E",
        "--primary", "echo:echo",
        "--blind", "echo:echo",
        "--cold", "echo:echo",
        "--timeout-per-call", "30",
        "--skip-compare",
        "--output", str(runs),
    ])
    report["checks"]["canonical_appliance_echo"] = "PASS"
    report["appliance_stdout_tail"] = appliance.stdout[-2500:]

    run_dir = _latest_run(runs)
    outcome_path = run_dir / "APPLIANCE_OUTCOME.json"
    summary_path = run_dir / "APPLIANCE_RUN_SUMMARY.json"
    if not outcome_path.exists() or not summary_path.exists():
        raise RuntimeError("appliance_summary_or_outcome_missing")
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    if outcome.get("final_package_verified") is not True:
        raise RuntimeError(f"appliance_package_not_verified:{outcome.get('final_package_verified')}")
    package = Path(outcome["final_package"])
    if not package.exists():
        raise RuntimeError("appliance_package_missing")
    with zipfile.ZipFile(package) as z:
        names = set(z.namelist())
        expected_summary = f"{run_dir.name}/APPLIANCE_RUN_SUMMARY.json"
        if expected_summary not in names:
            raise RuntimeError("packaged_appliance_run_summary_missing")
    report["checks"]["packaged_run_summary"] = "PASS"

    run([PY, "-B", "-m", "hermes_factory", "status", "--run-dir", str(run_dir)])
    run([PY, "-B", "-m", "hermes_factory", "resume", "--run-dir", str(run_dir)])
    report["checks"]["ledger_status_and_resume"] = "PASS"

    run([PY, "-B", "-m", "hermes_factory", "verify-package", str(package)])
    tampered = work_dir / "tampered.zip"
    _tamper_package(package, tampered)
    tamper = run([PY, "-B", "-m", "hermes_factory", "verify-package", str(tampered)], expect=1)
    if "package_hash_mismatch" not in tamper.stdout and "package_size_mismatch" not in tamper.stdout:
        raise RuntimeError("tamper_rejection_did_not_report_manifest_mismatch")
    report["checks"]["package_tamper_rejected"] = "PASS"

    source_units = run_dir / "SOURCE" / "source_units.jsonl"
    run([
        PY, "-B", "providers_ext/smoke_providers.py",
        "--source-units", str(source_units),
        "--primary", "echo:echo",
        "--blind", "echo:echo",
        "--audit", "echo:echo",
        "--timeout", "30",
    ])
    report["checks"]["provider_wrapper_smoke"] = "PASS"

    db = work_dir / "synthetic_09d.sqlite"
    create_synthetic_09d(db)
    db_before = sha256_file(db)
    run([
        PY, "-B", "stages_ext/compare_09d.py",
        "--run-dir", str(run_dir),
        "--database", str(db),
        "--allow-target-drift",
    ])
    db_after_compare = sha256_file(db)
    if db_after_compare != db_before:
        raise RuntimeError("09d_database_changed_during_comparison")
    report["checks"]["09d_comparison_read_only"] = "PASS"

    projection = run([
        PY, "-B", "stages_ext/project_09d_motion2.py",
        "--run-dir", str(run_dir),
        "--database", str(db),
    ], expect=4)
    projection_summary = json.loads(
        (run_dir / "09D" / "motion2_projection_summary.json").read_text(encoding="utf-8")
    )
    if projection_summary.get("projection_status") != "PROJECTION_REVIEW_REQUIRED":
        raise RuntimeError(f"untrusted_target_did_not_fail_closed:{projection_summary.get('projection_status')}")
    if projection_summary.get("authority_binding", {}).get("verified") is True:
        raise RuntimeError("synthetic_unpinned_09d_was_incorrectly_authority_verified")
    report["checks"]["strict_09d_target_binding_fail_closed"] = "PASS"
    report["projection_stdout_tail"] = projection.stdout[-1000:]

    run([PY, "-B", "stages_ext/guard_09d_numeric_context.py", "--run-dir", str(run_dir)])
    if sha256_file(db) != db_before:
        raise RuntimeError("09d_database_changed_during_projection_or_context_guard")
    report["checks"]["09d_projection_and_context_guard_read_only"] = "PASS"

    repack = work_dir / "review_artifacts.zip"
    run([PY, "-B", "-m", "hermes_factory", "package", "--run-dir", str(run_dir), "--output", str(repack)])
    run([PY, "-B", "-m", "hermes_factory", "verify-package", str(repack)])
    report["checks"]["repackaged_09d_review_artifacts_verified"] = "PASS"

    report["run_dir"] = str(run_dir)
    report["core_readiness_status"] = outcome.get("readiness_status")
    report["initial_package"] = str(package)
    report["initial_package_sha256"] = sha256_file(package)
    report["review_package"] = str(repack)
    report["review_package_sha256"] = sha256_file(repack)
    report["synthetic_09d_sha256"] = db_before
    report["finished_unix"] = time.time()
    report["overall"] = "PASS"
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", help="persistent output directory; default is temporary")
    args = ap.parse_args(argv)
    if args.work_dir:
        work = Path(args.work_dir).resolve()
        report = validate(work)
        out = work / "E2E_VALIDATION_REPORT.json"
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    with tempfile.TemporaryDirectory() as td:
        report = validate(Path(td))
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
