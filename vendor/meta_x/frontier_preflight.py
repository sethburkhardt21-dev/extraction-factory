#!/usr/bin/env python3
"""Run the full NO-NETWORK frontier preflight and freeze evidence."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json, py_compile, subprocess, sys, traceback

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from frontier_core.readiness import GateResult, code_manifest, verification_manifest, production_python_files, static_safety_scan


def command_gate(name: str, cmd: list[str], cwd: Path) -> GateResult:
    p=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True)
    detail=(p.stdout+p.stderr).strip()
    if len(detail)>5000: detail=detail[-5000:]
    return GateResult(name,p.returncode==0,detail or f"exit={p.returncode}")


def main() -> int:
    gates=[]
    compile_errors=[]
    for p in production_python_files(ROOT):
        try: py_compile.compile(str(p),doraise=True)
        except Exception as exc: compile_errors.append(f"{p.relative_to(ROOT)}: {exc}")
    gates.append(GateResult("production_python_compile",not compile_errors,f"{len(production_python_files(ROOT))} files" if not compile_errors else "; ".join(compile_errors[:20])))

    gates.extend(static_safety_scan(ROOT))
    py=sys.executable
    gates += [
        command_gate("clinicaltrials_regression_suite",[py,"-m","pytest","-q"],ROOT/"clinicaltrials"),
        command_gate("preprint_regression_suite",[py,"-m","pytest","-q"],ROOT/"preprints"),
        command_gate("drug_regression_suite",[py,"-m","pytest","-q"],ROOT/"drug_reference"),
        command_gate("pubmed_regression_suite",[py,"-m","pytest","-q"],ROOT/"pubmed_rag"),
        command_gate("pubmed_source_validator",[py,"validate.py"],ROOT/"pubmed_rag"),
        command_gate("bigquery_schema_validator",[py,"bigquery_validation_test.py"],ROOT/"pubmed_rag"),
        command_gate("warehouse_projection_suite",[py,"-m","pytest","-q","warehouse/tests"],ROOT),
        command_gate("schema_coverage_contract",[py,"schema/validate_coverage.py"],ROOT),
        command_gate("physical_projection_contract",[py,"schema/validate_physical_projection.py"],ROOT),
        command_gate("09d_alignment_contract",[py,"bridge_09d/validate_alignment.py"],ROOT),
        command_gate("09d_bridge_core_suite",[py,"-m","pytest","-q","bridge_09d/tests",
            "--ignore=bridge_09d/tests/test_assertion_contract.py",
            "--ignore=bridge_09d/tests/test_source_unit_segmenter.py",
            "--ignore=bridge_09d/tests/test_gold_evidence_corpus.py",
            "--ignore=bridge_09d/tests/test_gold_fixture_bundle.py",
            "--ignore=bridge_09d/tests/test_independent_verifier.py",
            "--ignore=bridge_09d/tests/test_semantic_verifier_gold.py",
            "--ignore=bridge_09d/tests/test_assertion_verifier.py",
            "--ignore=bridge_09d/tests/test_semantic_gold.py",
            "--ignore=bridge_09d/tests/test_blind_recall.py",
            "--ignore=bridge_09d/tests/test_verifier_pipeline.py",
            "--ignore=bridge_09d/tests/test_identity_resolution.py",
            "--ignore=bridge_09d/tests/test_09d_comparator.py",
            "--ignore=bridge_09d/tests/test_turn6_factory.py"],ROOT),
        command_gate("evidence_substrate_adversarial_suite",[py,"-m","pytest","-q","bridge_09d/tests/test_assertion_contract.py","bridge_09d/tests/test_source_unit_segmenter.py"],ROOT),
        command_gate("gold_evidence_acceptance_suite",[py,"-m","pytest","-q","bridge_09d/tests/test_gold_evidence_corpus.py","bridge_09d/tests/test_gold_fixture_bundle.py"],ROOT),
        command_gate("turn5_semantic_verification_suite",[py,"-m","pytest","-q",
            "bridge_09d/tests/test_independent_verifier.py",
            "bridge_09d/tests/test_semantic_verifier_gold.py",
            "bridge_09d/tests/test_assertion_verifier.py",
            "bridge_09d/tests/test_semantic_gold.py",
            "bridge_09d/tests/test_blind_recall.py",
            "bridge_09d/tests/test_verifier_pipeline.py"],ROOT),
        command_gate("turn6_identity_readonly_comparator_suite",[py,"-m","pytest","-q",
            "bridge_09d/tests/test_identity_resolution.py",
            "bridge_09d/tests/test_09d_comparator.py",
            "bridge_09d/tests/test_turn6_factory.py"],ROOT),
        command_gate("frontier_control_plane_suite",[py,"-m","pytest","-q","frontier_tests"],ROOT),
    ]
    cm=code_manifest(ROOT); vm=verification_manifest(ROOT)
    status="PASS" if all(g.passed for g in gates) else "FAIL"
    report={
        "preflight_schema_version":"frontier-preflight-1.0",
        "status":status,
        "network_extraction_performed":False,
        "live_source_certification":"PENDING",
        "database_execution_certification":"PENDING",
        "model_enrichment_certification":"OUT_OF_SCOPE_FOR_SOURCE_EXTRACTION",
        "production_code_manifest":cm,
        "verification_manifest":vm,
        "gates":[asdict(g) for g in gates],
    }
    (ROOT/"FRONTIER_PREFLIGHT.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    lines=[f"FRONTIER PREFLIGHT: {status}","NETWORK EXTRACTION PERFORMED: FALSE","LIVE SOURCE CERTIFICATION: PENDING","DATABASE EXECUTION CERTIFICATION: PENDING",f"PRODUCTION MANIFEST FILES: {cm['count']}",f"PRODUCTION CODE/CONTRACT MANIFEST SHA256: {cm['sha256']}",f"VERIFICATION MANIFEST FILES: {vm['count']}",f"VERIFICATION MANIFEST SHA256: {vm['sha256']}",""]
    for g in gates: lines.append(f"{'PASS' if g.passed else 'FAIL'} | {g.gate} | {g.detail}")
    (ROOT/"FRONTIER_PREFLIGHT.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines[:7]))
    return 0 if status=="PASS" else 1

if __name__=="__main__": raise SystemExit(main())
