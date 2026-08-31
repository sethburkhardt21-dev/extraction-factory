#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, sys, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from frontier_core.gate import require_frontier_preflight
from frontier_core.readiness import code_manifest, file_sha256
from warehouse.project import project_run

ORCHESTRATOR_SCHEMA_VERSION='frontier-orchestration-1.0'
CANARY_SCHEMA_VERSION='frontier-canary-certification-1.1'

def utc_now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def atomic_json(p:Path,obj):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp')
    with t.open('w',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(t,p)

def _read_manifest(source:str,run_dir:Path):
    p=run_dir/('extraction_manifest.json' if source=='ctg' else 'manifest.json')
    if not p.is_file(): raise RuntimeError(f'source manifest missing after execution: {p}')
    return p,json.loads(p.read_text(encoding='utf-8'))

def _canary_cert(path:Path, source:str, expected_code_sha:str):
    if not path.is_file(): raise RuntimeError(f'canary certificate not found: {path}')
    c=json.loads(path.read_text(encoding='utf-8'))
    if c.get('status')!='PASS' or c.get('source')!=source: raise RuntimeError('canary certificate is not PASS for requested source')
    if c.get('transport')!='native_http' or c.get('mass_unlock_eligible') is not True:
        raise RuntimeError('full extraction requires a native_http canary explicitly eligible to unlock mass extraction')
    if c.get('production_code_manifest_sha256')!=expected_code_sha: raise RuntimeError('production code changed since canary certification')
    return c

def _transport_certified(manifest:dict) -> bool:
    return str(manifest.get('transport_capture_status') or '').startswith('PASS_EXACT_')

def build_command(a, run_dir:Path, preflight:Path):
    py=sys.executable
    if a.source=='ctg':
        cmd=[py,str(ROOT/'clinicaltrials/canonical/run_extraction.py'),'--output',str(run_dir),'--network','--preflight',str(preflight)]
        queries=list(a.query or [])
        if len(queries)>1: raise RuntimeError('ClinicalTrials orchestration accepts exactly one --query expression per run')
        if a.mode=='canary':
            cmd += ['--query',queries[0] if queries else 'AREA[NCTId]NCT04368728','--page-size','1000']
        else:
            if queries: cmd += ['--query',queries[0],'--page-size',str(a.page_size)]
            else: cmd += ['--bulk']
        return cmd
    if a.source=='pubmed':
        if not a.email or '@' not in a.email: raise RuntimeError('--email with a real contact address is required for PubMed native HTTP execution')
        mindate=a.mindate or ('1900/01/01' if a.mode=='canary' else None)
        maxdate=a.maxdate or ('2100/01/01' if a.mode=='canary' else None)
        if not mindate or not maxdate: raise RuntimeError('--mindate and --maxdate are required for full PubMed extraction')
        cmd=[py,str(ROOT/'pubmed_rag/run_pubmed.py'),'--out-dir',str(run_dir),'--network','--preflight',str(preflight),'--mindate',mindate,'--maxdate',maxdate]
        queries=a.query or (['33301246[PMID]'] if a.mode=='canary' else [])
        for q in queries: cmd += ['--query',q]
        if a.email: cmd += ['--email',a.email]
        return cmd
    if a.source in {'medrxiv','biorxiv'}:
        if not a.email or '@' not in a.email: raise RuntimeError('--email with a real contact address is required for preprint native HTTP execution')
        script='pipeline.py' if a.mode=='canary' else 'run_all.py'
        if a.mode=='canary':
            day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat(); start=a.start or day; end=a.end or start
        else:
            start=a.start; end=a.end
            if not start or not end: raise RuntimeError('--start and --end are required for full preprint extraction')
        cmd=[py,str(ROOT/f'preprints/src/{script}'),'--server',a.source,'--start',start,'--end',end,'--out-dir',str(run_dir),'--network','--preflight',str(preflight)]
        if a.email: cmd += ['--contact-email',a.email]
        return cmd
    raise ValueError(a.source)

def run_orchestration(a):
    if not a.execute:
        return {'status':'dry_run','network_extraction_performed':False,'source':a.source,'mode':a.mode,'note':'No HTTP performed. Re-run with --execute after PASS preflight.'}
    if not a.preflight: raise RuntimeError('--preflight required with --execute')
    pre=require_frontier_preflight(a.preflight,ROOT); code_sha=pre['production_code_manifest']['sha256']
    if a.mode=='full':
        if not a.canary_cert: raise RuntimeError('--canary-cert required for full extraction')
        _canary_cert(a.canary_cert,a.source,code_sha)
    run_id=str(uuid.uuid4()); started_at=utc_now(); run_dir=a.output_root/a.source/f'{a.mode}-{run_id}'
    if run_dir.exists(): raise RuntimeError(f'run directory already exists: {run_dir}')
    run_dir.parent.mkdir(parents=True,exist_ok=True)
    cmd=build_command(a,run_dir,a.preflight)
    env=os.environ.copy()
    proc=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,env=env)
    orchestration={'orchestration_schema_version':ORCHESTRATOR_SCHEMA_VERSION,'orchestration_id':run_id,'source':a.source,'mode':a.mode,'started_at':started_at,'network_extraction_performed':True,'production_code_manifest_sha256':code_sha,'preflight_sha256':file_sha256(a.preflight),'source_run_dir':str(run_dir),'command_exit_code':proc.returncode,'stdout_tail':proc.stdout[-4000:],'stderr_tail':proc.stderr[-4000:]}
    if proc.returncode!=0:
        orchestration.update(status='FAIL',error='source command failed'); atomic_json(run_dir.parent/f'{run_id}.orchestration.json',orchestration); raise RuntimeError(f'source command failed: {proc.stderr[-2000:]}')
    mp,manifest=_read_manifest(a.source,run_dir); orchestration['source_manifest_sha256']=file_sha256(mp); orchestration['source_certification_status']=manifest.get('certification_status')
    if manifest.get('status')=='completed':
        wh=run_dir/'warehouse'; wm=project_run(a.source,run_dir,wh)
        projection_sha=file_sha256(wh/'warehouse_projection_manifest.json')
        orchestration['warehouse_projection_manifest_sha256']=projection_sha; orchestration['warehouse_validation_status']=wm.get('validation_status')
        evidence={'evidence_schema_version':'frontier-orchestration-evidence-1.0','source':a.source,'orchestration_mode':a.mode,'source_run_id':manifest.get('run_id'),'production_code_manifest_sha256':code_sha,'preflight_sha256':file_sha256(a.preflight),'source_manifest_sha256':orchestration['source_manifest_sha256'],'warehouse_projection_manifest_sha256':projection_sha}
        atomic_json(wh/'orchestration_evidence.json',evidence)
        orchestration['orchestration_evidence_sha256']=file_sha256(wh/'orchestration_evidence.json')
    else: orchestration['warehouse_validation_status']='NOT_PROJECTED_SOURCE_NOT_COMPLETED'
    source_nonempty=int(manifest.get('valid_records',manifest.get('records',0)) or 0)>0
    transport_status=str(manifest.get('transport_capture_status') or '')
    transport_ok=_transport_certified(manifest)
    orchestration['transport_capture_status']=transport_status
    orchestration['transport_certified']=transport_ok
    orchestration['status']='PASS' if manifest.get('certification_status')=='PASS' and transport_ok and orchestration.get('warehouse_validation_status')=='PASS' and (a.mode!='canary' or source_nonempty) else 'NONPROMOTABLE'
    if a.mode=='canary' and not source_nonempty: orchestration['canary_rejection_reason']='canary returned zero valid records; parser path was not exercised'
    if manifest.get('status')=='completed' and (run_dir/'warehouse/orchestration_evidence.json').is_file():
        evidence_path=run_dir/'warehouse/orchestration_evidence.json'
        evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
        evidence.update({
            'orchestration_status':orchestration['status'],
            'transport_capture_status':transport_status,
            'transport_certified':transport_ok,
        })
        atomic_json(evidence_path,evidence)
        orchestration['orchestration_evidence_sha256']=file_sha256(evidence_path)
    orchestration['completed_at']=utc_now(); op=run_dir/'orchestration_manifest.json'; atomic_json(op,orchestration)
    if a.mode=='canary' and orchestration['status']=='PASS':
        cert={'canary_schema_version':CANARY_SCHEMA_VERSION,'status':'PASS','source':a.source,'transport':'native_http','mass_unlock_eligible':True,'certified_at':utc_now(),'production_code_manifest_sha256':code_sha,'preflight_sha256':file_sha256(a.preflight),'source_manifest_sha256':orchestration['source_manifest_sha256'],'warehouse_projection_manifest_sha256':orchestration['warehouse_projection_manifest_sha256'],'source_run_id':manifest.get('run_id')}
        cp=a.output_root/'canary_certifications'/f'{a.source}.json'; atomic_json(cp,cert); orchestration['canary_certificate']=str(cp)
        atomic_json(op,orchestration)
    return orchestration

def main():
    p=argparse.ArgumentParser(description='Frontier extraction control plane. Dry-run by default; full mode requires code-bound canary certification.')
    p.add_argument('--source',choices=['ctg','pubmed','medrxiv','biorxiv'],required=True); p.add_argument('--mode',choices=['canary','full'],required=True)
    p.add_argument('--output-root',type=Path,required=True); p.add_argument('--execute',action='store_true'); p.add_argument('--preflight',type=Path); p.add_argument('--canary-cert',type=Path)
    p.add_argument('--query',action='append'); p.add_argument('--page-size',type=int,default=1000); p.add_argument('--ctg-bulk',action='store_true')
    p.add_argument('--mindate'); p.add_argument('--maxdate'); p.add_argument('--start'); p.add_argument('--end'); p.add_argument('--email',default='')
    a=p.parse_args(); print(json.dumps(run_orchestration(a),indent=2,sort_keys=True))
if __name__=='__main__': main()
