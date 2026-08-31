"""Persistence boundary for Turn-4 assertion extraction."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, os
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .assertion_engine import EngineConfig, ProposalProvider, extract_assertions, structured_clinicaltrials_provider, deterministic_structured_config
from frontier_core.readiness import code_manifest

PIPELINE_MANIFEST_VERSION="frontier-assertion-pipeline-1.0"

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


def run_assertion_pipeline(*, source_units_path:Path, output_dir:Path, provider:ProposalProvider, config:EngineConfig)->Dict[str,Any]:
    source_units_path=Path(source_units_path); output_dir=Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()): raise RuntimeError(f"assertion output must be empty: {output_dir}")
    if not source_units_path.is_file(): raise FileNotFoundError(source_units_path)
    estate_root=Path(__file__).resolve().parents[1]
    current_code_sha=code_manifest(estate_root)["sha256"]
    if config.code_manifest_sha256 != current_code_sha:
        raise RuntimeError(f"assertion config code hash does not match running estate: config={config.code_manifest_sha256} current={current_code_sha}")
    units=read_jsonl(source_units_path); output_dir.mkdir(parents=True,exist_ok=True)
    result=extract_assertions(units,provider=provider,config=config)
    assertions_path=output_dir/"assertions.jsonl"; quarantine_path=output_dir/"quarantine.jsonl"
    atomic_jsonl(assertions_path,result["assertions"]); atomic_jsonl(quarantine_path,result["quarantine"])
    manifest={
        "assertion_pipeline_manifest_version":PIPELINE_MANIFEST_VERSION,
        "created_at":utc_now(),"status":result["status"],
        "source_units_path":str(source_units_path),"source_units_sha256":sha256_file(source_units_path),
        "assertions_path":"assertions.jsonl","assertions_sha256":sha256_file(assertions_path),
        "quarantine_path":"quarantine.jsonl","quarantine_sha256":sha256_file(quarantine_path),
        "semantic_verification_performed":False,"candidate_resolution_performed":False,"09d_comparison_performed":False,
        "canonical_authority":False,"automatic_selection_allowed":False,"generation_eligible":False,"public_eligible":False,
        "extractor_provenance":result["extractor_provenance"],"metrics":result["metrics"],
    }
    atomic_json(output_dir/"manifest.json",manifest)
    return {**result,"pipeline_manifest":manifest}


def run_ctg_structured_pipeline(*,source_units_path:Path,output_dir:Path,code_manifest_sha256:str)->Dict[str,Any]:
    return run_assertion_pipeline(source_units_path=source_units_path,output_dir=output_dir,
        provider=structured_clinicaltrials_provider,config=deterministic_structured_config(code_manifest_sha256=code_manifest_sha256))
