from pathlib import Path
import json, hashlib, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parent
PREF=ROOT/"PREFLIGHT"; PREF.mkdir(exist_ok=True)
checks=[]
def add(n,s,d=""): checks.append({"check":n,"status":s,"detail":d})

def run(name,cmd):
    r=subprocess.run(cmd,capture_output=True,text=True)
    add(name,"PASS" if r.returncode==0 else "FAIL_BLOCKING",(r.stdout+r.stderr).strip())

# Existing Turn09 checks
for rel in [
"FREEZE/FACTORY_V1_FREEZE_MANIFEST.json",
"IMPLEMENTATION/IMPLEMENTATION_MATURITY_MATRIX_v0_1.json",
"CONTRACTS/EVIDENCE_SUBSTRATE_v0_1/EVIDENCE_SUBSTRATE_CONTRACT_v0_1.json",
"PILOTS/MACHINES_P0299_P0301_TURN09/SOURCE/source_identity.json",
"PILOTS/MACHINES_P0299_P0301_TURN09/SOURCE_UNITS/source_unit_manifest.json",
"RUNTIME_REFERENCE_v1/schemas/BUZZ_SIDECAR_REQUEST_SCHEMA.json"]:
    try:
        json.loads((ROOT/rel).read_text(encoding="utf-8")); add("json:"+rel,"PASS")
    except Exception as e: add("json:"+rel,"FAIL_BLOCKING",str(e))

run("schema_coverage",[sys.executable,str(ROOT/"VALIDATORS/SCHEMA_COVERAGE_v0_1/validate_schema_coverage.py"),
                       str(ROOT/"VALIDATORS/SCHEMA_COVERAGE_v0_1/SCHEMA_COVERAGE_CONTRACT_v0_1.json")])
run("turn08_mutations",[sys.executable,str(ROOT/"VALIDATORS/TURN08_VALIDATION_SUITE_v0_1/test_mutations.py")])
run("turn10_runtime_tests",[sys.executable,str(ROOT/"RUNTIME_REFERENCE_v1/tests/test_runtime.py")])
run("turn10_real_source_mutations",[sys.executable,str(ROOT/"VALIDATORS/TURN10_RUNTIME/test_real_source_mutations.py")])

# all blind pilot capsules must pass inspection
blind_validator=ROOT/"VALIDATORS/TURN10_RUNTIME/validate_blind_capsule.py"
for capname in ["W2_PRIMARY","W2_BLIND_RECALL","W1_NUMERIC_LITERAL","W1_QUALIFIER_LITERAL"]:
    run("blindness:"+capname,[sys.executable,str(blind_validator),str(ROOT/f"PILOTS/MACHINES_P0299_P0301_TURN09/CAPSULES/{capname}")])

# Boundary context existence and ownership discipline
sid=json.loads((ROOT/"PILOTS/MACHINES_P0299_P0301_TURN09/SOURCE/source_identity.json").read_text())
ok=sid.get("boundary_context_pdf_pages")==[298,302] and sid.get("pilot_scope_pdf_pages")==[299,300,301]
add("pilot_boundary_scope","PASS" if ok else "FAIL_BLOCKING")

# Freeze claim boundary
freeze=json.loads((ROOT/"FREEZE/FACTORY_V1_FREEZE_MANIFEST.json").read_text())
ok=(freeze["architecture_status"]=="FROZEN_V1" and
    freeze["semantic_factory_status"]=="NOT_EMPIRICALLY_CERTIFIED" and
    freeze["production_status"]=="BLOCKED_PENDING_EMPIRICAL_GATES")
add("freeze_claim_boundary","PASS" if ok else "FAIL_BLOCKING")

overall="PASS" if all(c["status"]=="PASS" for c in checks) else "FAIL_BLOCKING"
report={
    "preflight_version":"1.0-turn10",
    "overall":overall,
    "architecture_status":"FROZEN_V1",
    "reference_runtime_status":"OFFLINE_CERTIFIED",
    "semantic_factory_status":"NOT_EMPIRICALLY_CERTIFIED",
    "production_status":"BLOCKED_PENDING_EMPIRICAL_GATES",
    "checks":checks
}
(PREF/"PREFLIGHT.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
lines=[
"HERMES EXTRACTION FACTORY v1 PREFLIGHT",
f"OVERALL: {overall}",
"ARCHITECTURE: FROZEN_V1",
"REFERENCE RUNTIME: OFFLINE_CERTIFIED",
"SEMANTIC FACTORY: NOT_EMPIRICALLY_CERTIFIED",
"PRODUCTION: BLOCKED_PENDING_EMPIRICAL_GATES",
""
]+[f"{c['status']}: {c['check']} {c['detail']}".rstrip() for c in checks]
(PREF/"PREFLIGHT.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
print("HERMES FACTORY v1 PREFLIGHT:",overall)
for c in checks: print(c["status"]+":",c["check"])
raise SystemExit(0 if overall=="PASS" else 1)
