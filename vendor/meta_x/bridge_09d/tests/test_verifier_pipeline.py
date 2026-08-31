import json
from pathlib import Path
import pytest
from bridge_09d.assertions import build_source_unit, build_assertion, sha256_hex
from bridge_09d.verifier import deterministic_verifier_config
from bridge_09d.verifier_pipeline import run_verifier_pipeline
from frontier_core.readiness import code_manifest

ROOT=Path(__file__).resolve().parents[2]

def write_jsonl(path,rows): path.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))

def make():
    u=build_source_unit(source_record_key='S:1',source_resource_id='R:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','xpath':'/a/p'},content_text='Propofol may cause hypotension.')
    t=u['content_text']; span={'char_start':0,'char_end':len(t),'utf8_byte_start':0,'utf8_byte_end':len(t.encode()),'text':t,'text_sha256':sha256_hex(t.encode())}
    a=build_assertion(source_unit=u,assertion_type='ADVERSE_EFFECT',normalized_proposition=t,evidence_span=span,extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':'c'*64})
    return u,a

def test_pipeline_persists_hash_bound_append_only_verification(tmp_path):
    u,a=make(); units=tmp_path/'units.jsonl'; assertions=tmp_path/'assertions.jsonl'; out=tmp_path/'verify'
    write_jsonl(units,[u]); write_jsonl(assertions,[a])
    sha=code_manifest(ROOT)['sha256']; r=run_verifier_pipeline(source_units_path=units,assertions_path=assertions,output_dir=out,config=deterministic_verifier_config(code_manifest_sha256=sha))
    assert r['status']=='PASS' and r['metrics']['verification_events']==1
    event=json.loads((out/'verification_events.jsonl').read_text())
    manifest=json.loads((out/'manifest.json').read_text())
    assert event['verdict']=='ENTAILED' and event['canonical_authority'] is False
    assert manifest['assertions_mutated'] is False and manifest['blind_independent_review'] is True
    assert manifest['verifier_provenance']['code_manifest_sha256']==sha

def test_pipeline_refuses_wrong_estate_hash(tmp_path):
    u,a=make(); units=tmp_path/'units.jsonl'; assertions=tmp_path/'assertions.jsonl'
    write_jsonl(units,[u]); write_jsonl(assertions,[a])
    with pytest.raises(RuntimeError,match='code hash'):
        run_verifier_pipeline(source_units_path=units,assertions_path=assertions,output_dir=tmp_path/'out',config=deterministic_verifier_config(code_manifest_sha256='0'*64))
