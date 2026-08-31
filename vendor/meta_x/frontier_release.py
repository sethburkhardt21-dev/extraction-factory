#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from frontier_core.readiness import file_sha256
from warehouse.project import atomic_json, atomic_jsonl
SCHEMA='frontier-research-ingestion-snapshot-2.0'
def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def csha(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_projection(d:Path):
    mp=d/'warehouse_projection_manifest.json'
    ep=d/'orchestration_evidence.json'
    if not mp.is_file(): raise RuntimeError(f'projection manifest missing: {mp}')
    if not ep.is_file(): raise RuntimeError(f'orchestration evidence missing: {ep}')
    m=json.loads(mp.read_text()); e=json.loads(ep.read_text())
    if e.get('orchestration_mode') != 'full': raise RuntimeError('release inputs must come from full extraction, not canary')
    if e.get('orchestration_status') != 'PASS': raise RuntimeError('release input orchestration is not PASS')
    if e.get('transport_certified') is not True or not str(e.get('transport_capture_status') or '').startswith('PASS_EXACT_'):
        raise RuntimeError('release input lacks exact native transport certification')
    if e.get('warehouse_projection_manifest_sha256') != file_sha256(mp): raise RuntimeError('orchestration evidence projection hash mismatch')
    if e.get('source_manifest_sha256') != m.get('source_manifest_sha256'): raise RuntimeError('orchestration evidence source manifest hash mismatch')
    if m.get('validation_status')!='PASS': raise RuntimeError(f'projection is not PASS: {d}')
    for name,a in (m.get('artifacts') or {}).items():
        p=d/a['path']
        if not p.is_file() or file_sha256(p)!=a.get('sha256'): raise RuntimeError(f'projection artifact hash mismatch: {p}')
    ip=d/'ingestion_run.jsonl'; rows=[json.loads(x) for x in ip.read_text().splitlines() if x.strip()]
    if len(rows)!=1: raise RuntimeError(f'projection must contain exactly one ingestion_run: {d}')
    r=rows[0]
    promotable=(r.get('status')=='completed' and r.get('certification_status')=='PASS' and r.get('truncated') is False and r.get('complete_against_source') is True and int(r.get('quarantined_records') or 0)==0 and r.get('source_changed_during_run') in (False,None))
    if not promotable: raise RuntimeError(f'run is not promotable: {r.get("source")} {r.get("run_id")}')
    return m,r,file_sha256(mp),e,file_sha256(ep)

def create_release(projections:list[Path], output:Path, label:str, required:list[str]):
    if output.exists() and any(output.iterdir()): raise RuntimeError(f'release output must be empty: {output}')
    checked=[]
    for d in projections:
        m,r,sha,e,evidence_sha=verify_projection(d); checked.append({'source':r['source'],'run_id':r['run_id'],'projection_manifest_sha256':sha,'source_manifest_sha256':m.get('source_manifest_sha256'),'orchestration_evidence_sha256':evidence_sha,'production_code_manifest_sha256':e.get('production_code_manifest_sha256')})
    sources={x['source'] for x in checked}; missing=[s for s in required if s not in sources]
    if missing: raise RuntimeError('required release source(s) missing: '+', '.join(missing))
    if len({x['run_id'] for x in checked})!=len(checked): raise RuntimeError('duplicate run_id in release inputs')
    source_names=[x['source'] for x in checked]
    if len(set(source_names))!=len(source_names): raise RuntimeError('release contains multiple promoted runs for the same source')
    release_id=str(uuid.uuid4()); created=now()
    body={'release_schema_version':SCHEMA,'release_id':release_id,'label':label,'created_at':created,'status':'certified_research_ingestion','release_class':'RESEARCH_INGESTION_SNAPSHOT','runs':sorted(checked,key=lambda x:(x['source'],x['run_id'])),'required_sources':sorted(required),'direct_09d_insert_allowed':False,'canonical_authority':False,'automatic_selection_allowed':False,'canonical_internal_eligible':False,'generation_eligible':False,'public_eligible':False}
    body['manifest_sha256']=csha(body)
    output.mkdir(parents=True,exist_ok=True); atomic_json(output/'release_manifest.json',body)
    atomic_jsonl(output/'release_snapshot.jsonl',[{'release_id':release_id,'label':label,'schema_version':SCHEMA,'created_at':created,'status':'certified_research_ingestion','manifest_sha256':body['manifest_sha256'],'manifest':body}])
    atomic_jsonl(output/'release_run.jsonl',[{'release_id':release_id,'run_id':x['run_id']} for x in body['runs']])
    return body

def main():
    p=argparse.ArgumentParser(); p.add_argument('--projection',type=Path,action='append',required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--label',required=True); p.add_argument('--require-source',action='append',default=[])
    a=p.parse_args(); print(json.dumps(create_release(a.projection,a.output,a.label,a.require_source),indent=2,sort_keys=True))
if __name__=='__main__': main()
