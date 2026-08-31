"""Persistence boundary for independent Turn-5 semantic verification."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from .verifier import VerifierConfig, SemanticVerdictProvider, verify_assertions
from frontier_core.readiness import code_manifest

PIPELINE_MANIFEST_VERSION="frontier-verifier-pipeline-1.0"

def utc_now()->str: return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def read_jsonl(path:Path):
    rows=[]
    for lineno,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        obj=json.loads(line)
        if not isinstance(obj,dict): raise ValueError(f"{path}:{lineno}: row must be object")
        rows.append(obj)
    return rows

def atomic_jsonl(path:Path,rows:Sequence[Mapping[str,Any]])->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        for row in rows: f.write(json.dumps(dict(row),sort_keys=True,ensure_ascii=False)+"\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def atomic_json(path:Path,obj:Mapping[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        json.dump(dict(obj),f,indent=2,sort_keys=True,ensure_ascii=False); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)


def run_verifier_pipeline(*, source_units_path:Path, assertions_path:Path, output_dir:Path,
                          config:VerifierConfig, semantic_provider:Optional[SemanticVerdictProvider]=None, reviewer:Optional[SemanticVerdictProvider]=None)->Dict[str,Any]:
    if semantic_provider is not None and reviewer is not None: raise ValueError("provide semantic_provider or reviewer, not both")
    if semantic_provider is None: semantic_provider=reviewer
    source_units_path=Path(source_units_path); assertions_path=Path(assertions_path); output_dir=Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()): raise RuntimeError(f"verification output must be empty: {output_dir}")
    if not source_units_path.is_file(): raise FileNotFoundError(source_units_path)
    if not assertions_path.is_file(): raise FileNotFoundError(assertions_path)
    estate_root=Path(__file__).resolve().parents[1]
    current_sha=code_manifest(estate_root)["sha256"]
    if config.code_manifest_sha256!=current_sha:
        raise RuntimeError(f"verifier config code hash does not match running estate: config={config.code_manifest_sha256} current={current_sha}")
    units=read_jsonl(source_units_path); assertions=read_jsonl(assertions_path)
    output_dir.mkdir(parents=True,exist_ok=True)
    result=verify_assertions(assertions,units,config=config,semantic_provider=semantic_provider)
    events_path=output_dir/"verification_events.jsonl"; quarantine_path=output_dir/"quarantine.jsonl"
    atomic_jsonl(events_path,result["verification_events"]); atomic_jsonl(quarantine_path,result["quarantine"])
    manifest={
        "verifier_pipeline_manifest_version":PIPELINE_MANIFEST_VERSION,
        "created_at":utc_now(),"status":result["status"],
        "source_units_path":str(source_units_path),"source_units_sha256":sha256_file(source_units_path),
        "assertions_path":str(assertions_path),"assertions_sha256":sha256_file(assertions_path),
        "verification_events_path":"verification_events.jsonl","verification_events_sha256":sha256_file(events_path),
        "quarantine_path":"quarantine.jsonl","quarantine_sha256":sha256_file(quarantine_path),
        "assertions_mutated":False,"candidate_resolution_performed":False,"09d_comparison_performed":False,
        "canonical_authority":False,"automatic_selection_allowed":False,"generation_eligible":False,"public_eligible":False,
        "blind_independent_review":True,"verifier_provenance":result["verifier_provenance"],"metrics":result["metrics"],
    }
    atomic_json(output_dir/"manifest.json",manifest)
    return {**result,"pipeline_manifest":manifest}
