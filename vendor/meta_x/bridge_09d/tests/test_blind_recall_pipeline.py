import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from bridge_09d.assertions import build_source_unit
from bridge_09d.assertion_engine import EngineConfig, proposal_to_assertion
from bridge_09d.blind_recall_pipeline import run_blind_recall_pipeline
from frontier_core.readiness import code_manifest


def _unit(i:int,text:str):
    return build_source_unit(
        source_record_key=f'pubmed:{i}',source_resource_id=f'PMID:{i}',source_version_id='1',
        source_sha256=(str(i%10)*64),source_scope='FULL_TEXT',unit_kind='TEXT',
        locator={'locator_type':'PARAGRAPH','paragraph':i},content_text=text,
    )


def _write_jsonl(path:Path,rows):
    path.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows),encoding='utf-8')


def _config():
    return EngineConfig(engine='blind-recall-test',engine_version='1',code_manifest_sha256=code_manifest(ROOT)['sha256'],mode='MODEL_ASSISTED',model='recall-test',model_revision='1',prompt_sha256='d'*64)


def test_hash_bound_blind_recall_pipeline_persists_exact_and_recall_only(tmp_path):
    u1=_unit(1,'Propofol caused apnea.')
    u2=_unit(2,'Propofol reduced blood pressure.')
    units=[u1,u2]
    primary=[proposal_to_assertion(u1,{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'},config=_config())]
    up=tmp_path/'units.jsonl'; pp=tmp_path/'primary.jsonl'; out=tmp_path/'out'
    _write_jsonl(up,units); _write_jsonl(pp,primary)
    seen=[]
    def provider(packet):
        seen.append(packet)
        text=packet['source_unit']['content_text']
        if 'apnea' in text:
            return [{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'}]
        return [{'assertion_type':'TREATMENT_EFFECT','normalized_proposition':'Propofol reduced blood pressure.','evidence_text':'Propofol reduced blood pressure'}]
    result=run_blind_recall_pipeline(source_units_path=up,primary_assertions_path=pp,output_dir=out,provider=provider,config=_config())
    assert len(seen)==2
    assert all(p['recall_task']['independent_of_primary_extractor'] is True for p in seen)
    assert all('primary_assertions' not in json.dumps(p) for p in seen)
    assert result['reconciliation']['counts']['PRIMARY_AND_RECALL_EXACT']==1
    assert result['reconciliation']['counts']['RECALL_ONLY_CANDIDATE']==1
    m=json.loads((out/'manifest.json').read_text())
    assert m['primary_assertions_visible_during_recall'] is False
    assert m['recall_outputs_are_unverified'] is True
    assert m['automatic_repair_allowed'] is False
    assert m['canonical_authority'] is False
    assert (out/'recall_assertions.jsonl').is_file() and (out/'reconciliation.jsonl').is_file()


def test_blind_recall_pipeline_rejects_wrong_estate_hash(tmp_path):
    u=_unit(1,'Propofol caused apnea.')
    up=tmp_path/'units.jsonl'; pp=tmp_path/'primary.jsonl'
    _write_jsonl(up,[u]); _write_jsonl(pp,[])
    bad=EngineConfig(engine='x',engine_version='1',code_manifest_sha256='0'*64,mode='MODEL_ASSISTED',model='x',model_revision='1',prompt_sha256='d'*64)
    with pytest.raises(RuntimeError,match='code hash does not match'):
        run_blind_recall_pipeline(source_units_path=up,primary_assertions_path=pp,output_dir=tmp_path/'out',provider=lambda p:[],config=bad)


def test_blind_recall_pipeline_never_mutates_primary_file(tmp_path):
    u=_unit(1,'Propofol caused apnea.')
    cfg=_config()
    a=proposal_to_assertion(u,{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'},config=cfg)
    up=tmp_path/'units.jsonl'; pp=tmp_path/'primary.jsonl'; _write_jsonl(up,[u]); _write_jsonl(pp,[a])
    before=pp.read_bytes()
    run_blind_recall_pipeline(source_units_path=up,primary_assertions_path=pp,output_dir=tmp_path/'out',provider=lambda p:[],config=cfg)
    assert pp.read_bytes()==before
