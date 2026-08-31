#!/usr/bin/env python3
"""Transport-neutral parser/schema conformance evidence.

This tool NEVER authorizes mass extraction. It validates a retained payload that
was acquired outside the native source client against the exact production code
identified by a PASS frontier preflight. Its certificate is intentionally
ineligible for the orchestrator's full-extraction gate.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from frontier_core.gate import require_frontier_preflight
from frontier_core.readiness import file_sha256
from warehouse.project import canonical_json_sha256

SCHEMA_VERSION='frontier-external-canary-1.0'

def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def atomic_json(path:Path,obj:Dict[str,Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,sort_keys=True,ensure_ascii=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def _payload_sha(path:Path) -> str:
    return file_sha256(path)

def _ctg(payload:Path) -> List[Dict[str,Any]]:
    from clinicaltrials.canonical.clinicaltrials.models import parse_study, CANONICAL_SCHEMA_VERSION
    obj=json.loads(payload.read_text(encoding='utf-8'))
    raws=obj.get('studies') if isinstance(obj,dict) and isinstance(obj.get('studies'),list) else [obj]
    if not raws: raise ValueError('ClinicalTrials external payload contains no studies')
    out=[]
    for raw in raws:
        if not isinstance(raw,dict): raise ValueError('ClinicalTrials study payload must be an object')
        rec=parse_study(raw).to_dict(include_raw=True)
        # Lossless invariant: top-level source sections consumed by the parser remain retained.
        for src_key,canon_key in [('protocolSection','protocol_section'),('resultsSection','results_section'),('annotationSection','annotation_section'),('documentSection','document_section'),('derivedSection','derived_section')]:
            if src_key in raw and rec.get(canon_key)!=(raw.get(src_key) or {}):
                raise ValueError(f'ClinicalTrials lossless section mismatch: {src_key}')
        out.append({'source_record_id':rec['nct_id'],'canonical_schema_version':CANONICAL_SCHEMA_VERSION,'canonical_sha256':canonical_json_sha256(rec),'phase':rec.get('phase'),'overall_status':rec.get('overall_status'),'has_results':rec.get('has_results')})
    return out

def _preprint(payload:Path, source:str) -> List[Dict[str,Any]]:
    from preprints.src.medrxiv_biorxiv.client import normalize_record
    obj=json.loads(payload.read_text(encoding='utf-8'))
    collection=obj.get('collection') if isinstance(obj,dict) else None
    if not isinstance(collection,list) or not collection: raise ValueError('preprint external payload contains no collection records')
    out=[]; identities=set()
    for raw in collection:
        rec=normalize_record(raw,server_hint=source)
        ident=(rec['server'],rec['doi'],str(rec['version']))
        if ident in identities: raise ValueError(f'duplicate preprint identity in payload: {ident}')
        identities.add(ident)
        if rec.get('source_payload') != raw: raise ValueError(f'preprint source payload was not retained for {ident}')
        out.append({'source_record_id':'|'.join(ident),'canonical_sha256':canonical_json_sha256(rec),'title':rec.get('title'),'posted_date':rec.get('date')})
    return out

def _pubmed(payload:Path) -> List[Dict[str,Any]]:
    from pubmed_rag.pubmed_anesthesia_extraction import parse_pubmed_xml
    xml=payload.read_text(encoding='utf-8')
    records=parse_pubmed_xml(xml,strict=True)
    if not records: raise ValueError('PubMed external payload parsed zero records')
    out=[]
    for rec in records:
        d=rec.model_dump(mode='json') if hasattr(rec,'model_dump') else rec.dict()
        if not rec.raw_xml or len(str(rec.source_record_sha256 or ''))!=64:
            raise ValueError(f'PubMed record {rec.pmid} lacks retained raw XML/hash')
        out.append({'source_record_id':str(rec.pmid),'canonical_sha256':canonical_json_sha256(d),'title':rec.title,'record_type':rec.record_type})
    return out

def certify(source:str,payload:Path,preflight:Path,output:Path,*,source_url:str,retrieved_at:str,evidence_class:str='raw_payload') -> Dict[str,Any]:
    if evidence_class not in {'raw_payload','reconstructed_live_shape'}:
        raise ValueError('unsupported evidence_class')
    pre=require_frontier_preflight(preflight,ROOT)
    code_sha=pre['production_code_manifest']['sha256']
    if source=='ctg': records=_ctg(payload)
    elif source in {'medrxiv','biorxiv'}: records=_preprint(payload,source)
    elif source=='pubmed': records=_pubmed(payload)
    else: raise ValueError(source)
    cert={
        'external_canary_schema_version':SCHEMA_VERSION,
        'status':'PASS_EXTERNAL_TRANSPORT' if evidence_class=='raw_payload' else 'PASS_LIVE_SCHEMA_CONFORMANCE',
        'source':source,
        'transport':'external_payload',
        'evidence_class':evidence_class,
        'mass_unlock_eligible':False,
        'certified_at':now(),
        'retrieved_at':retrieved_at,
        'source_url':source_url,
        'payload_path':str(payload),
        'payload_sha256':_payload_sha(payload),
        'payload_bytes':payload.stat().st_size,
        'production_code_manifest_sha256':code_sha,
        'preflight_sha256':file_sha256(preflight),
        'records_validated':len(records),
        'source_record_ids':[r['source_record_id'] for r in records],
        'record_summaries':records,
        'schema_conformance_status':'PASS',
        'note':'This evidence validates parser/source-shape compatibility only and can never authorize a mass extraction. A same-code native_http canary remains mandatory.'
    }
    atomic_json(output,cert)
    return cert

def main():
    p=argparse.ArgumentParser(description='Validate externally acquired source payloads against the frozen production parser. Never unlocks mass extraction.')
    p.add_argument('--source',choices=['ctg','pubmed','medrxiv','biorxiv'],required=True)
    p.add_argument('--payload',type=Path,required=True); p.add_argument('--preflight',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-url',required=True); p.add_argument('--retrieved-at',required=True)
    p.add_argument('--evidence-class',choices=['raw_payload','reconstructed_live_shape'],default='raw_payload')
    a=p.parse_args(); print(json.dumps(certify(a.source,a.payload,a.preflight,a.output,source_url=a.source_url,retrieved_at=a.retrieved_at,evidence_class=a.evidence_class),indent=2,sort_keys=True))
if __name__=='__main__': main()
