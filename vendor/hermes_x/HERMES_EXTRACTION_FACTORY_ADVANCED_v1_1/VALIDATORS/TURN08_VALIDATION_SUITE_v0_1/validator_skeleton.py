import hashlib, json
from pathlib import Path

PASS="PASS"
FAIL_BLOCKING="FAIL_BLOCKING"
FAIL_REVIEW_REQUIRED="FAIL_REVIEW_REQUIRED"

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def val_source_sha(source_bytes: bytes, expected_sha: str):
    got=sha256_bytes(source_bytes)
    return {"validator":"VAL-SOURCE-SHA","result":PASS if got==expected_sha else FAIL_BLOCKING,"expected":expected_sha,"actual":got}

def val_id_unique(records):
    ids=[r.get("candidate_id") for r in records]
    ok = None not in ids and len(ids)==len(set(ids))
    return {"validator":"VAL-ID-UNIQUE","result":PASS if ok else FAIL_BLOCKING}

def val_evidence_hash(record):
    evidence=record.get("evidence","")
    expected=record.get("evidence_sha256","")
    got=sha256_bytes(evidence.encode("utf-8"))
    return {"validator":"VAL-EVIDENCE-HASH","result":PASS if got==expected else FAIL_BLOCKING,"expected":expected,"actual":got}

def val_lineage(record):
    required=["originating_capsule_id","originating_run_id","parent_artifact_sha256"]
    ok=all(bool(record.get(k)) for k in required)
    return {"validator":"VAL-LINEAGE","result":PASS if ok else FAIL_BLOCKING}

def val_cas(expected_parent_version, current_parent_version):
    return {"validator":"VAL-CAS-VERSION","result":PASS if expected_parent_version==current_parent_version else FAIL_BLOCKING}

def derive_frontier_ready(state):
    required = state.get("required_gate_results",{})
    blockers=[k for k,v in required.items() if v in ("FAIL_BLOCKING","NOT_RUN")]
    unresolved_review=[k for k,v in required.items() if v=="FAIL_REVIEW_REQUIRED" and not state.get("bounded_queue_for",{}).get(k)]
    ready = not blockers and not unresolved_review
    return {"validator":"VAL-PACKAGE-CLAIMS","derived_frontier_ready":ready,"blockers":blockers,"unresolved_review":unresolved_review}
