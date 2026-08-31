import hashlib, importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location("v", Path(__file__).parent/"validator_skeleton.py")
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)

def sha(s): return hashlib.sha256(s.encode()).hexdigest()

# MUT-001 wrong source SHA
assert v.val_source_sha(b"abc", "0"*64)["result"]=="FAIL_BLOCKING"

# positive source SHA
assert v.val_source_sha(b"abc", hashlib.sha256(b"abc").hexdigest())["result"]=="PASS"

# MUT-007 duplicate ID
assert v.val_id_unique([{"candidate_id":"a"},{"candidate_id":"a"}])["result"]=="FAIL_BLOCKING"

# MUT-002 fabricated evidence hash
r={"candidate_id":"a","evidence":"source text","evidence_sha256":sha("different"),"originating_capsule_id":"c","originating_run_id":"r","parent_artifact_sha256":"p"}
assert v.val_evidence_hash(r)["result"]=="FAIL_BLOCKING"

# MUT-008 broken lineage
assert v.val_lineage({"candidate_id":"a"})["result"]=="FAIL_BLOCKING"

# MUT-009 stale CAS
assert v.val_cas(3,4)["result"]=="FAIL_BLOCKING"

# MUT-011 false FRONTIER_READY
state={"required_gate_results":{"source":"PASS","visual":"NOT_RUN"},"bounded_queue_for":{}}
assert v.derive_frontier_ready(state)["derived_frontier_ready"] is False

print("TURN08 mutation skeleton tests: PASS")
