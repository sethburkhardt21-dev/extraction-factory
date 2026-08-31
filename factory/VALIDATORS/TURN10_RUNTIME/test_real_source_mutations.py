from pathlib import Path
import json, hashlib, tempfile, shutil, subprocess, sys

ROOT=Path(__file__).resolve().parents[2]
pilot=ROOT/"PILOTS/MACHINES_P0299_P0301_TURN09"

# 1) Source-unit content hash corruption is detectable
units=[json.loads(x) for x in (pilot/"SOURCE_UNITS/source_units.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
u=units[0].copy()
u["content"]=u["content"]+" fabricated"
assert hashlib.sha256(u["content"].encode("utf-8")).hexdigest()!=u["content_sha256"]

# 2) Blind capsule clean fixture passes
validator=ROOT/"VALIDATORS/TURN10_RUNTIME/validate_blind_capsule.py"
clean=pilot/"CAPSULES/W2_BLIND_RECALL"
r=subprocess.run([sys.executable,str(validator),str(clean)],capture_output=True,text=True)
assert r.returncode==0

# 3) Inject answer key into a copy and ensure fail
with tempfile.TemporaryDirectory() as td:
    dst=Path(td)/"cap"
    shutil.copytree(clean,dst)
    (dst/"SOURCE/answer_key.json").write_text("{}")
    r=subprocess.run([sys.executable,str(validator),str(dst)],capture_output=True,text=True)
    assert r.returncode!=0

print("TURN10_REAL_SOURCE_MUTATIONS: PASS")
