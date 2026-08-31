import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit
from bridge_09d.assertion_engine import EngineConfig,extract_assertions
from bridge_09d.semantic_factory import run_semantic_factory
from bridge_09d.verifier import VerifierConfig


def unit(text='Propofol caused apnea and the dose was 0.5 mg/kg IV.'):
    return build_source_unit(source_record_key='p:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text=text)

def primary(u,sha='c'*64):
    cfg=EngineConfig(engine='primary',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='p',model_revision='1',prompt_sha256='d'*64)
    return extract_assertions([u],provider=lambda x:[{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'}],config=cfg)['assertions']

def vcfg(sha='c'*64): return VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='vr',model_revision='1',prompt_sha256='e'*64)
def rcfg(sha='c'*64): return EngineConfig(engine='r',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='rr',model_revision='1',prompt_sha256='f'*64)
def reviewer(req): return {'verdict':'ENTAILED','rationale':'Exact source entailment.','confidence':'HIGH','resolved_warning_codes':[]}


def test_factory_composes_verification_recall_and_routing_without_authority():
    u=unit(); a=primary(u)
    result=run_semantic_factory(primary_assertions=a,source_units=[u],verifier_config=vcfg(),reviewer=reviewer,recall_config=rcfg(),recall_provider=lambda packet:[
        {'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'},
        {'assertion_type':'DOSING','normalized_proposition':'The propofol dose was 0.5 mg/kg IV.','evidence_text':'dose was 0.5 mg/kg IV','numeric':{'value':0.5,'unit':'mg/kg'},'context':{'route':'IV'}}
    ])
    assert result['verification']['verification_events'][0]['verdict']=='ENTAILED'
    assert result['blind_recall']['reconciliation']['counts']['RECALL_ONLY_CANDIDATE']==1
    cases=result['semantic_routing']['review_cases']
    dose=[c for c in cases if c['reason']=='RECALL_ONLY_CANDIDATE'][0]
    assert dose['risk_tier']=='CRITICAL' and 'FRONTIER_ADJUDICATION' in dose['required_lanes']
    assert result['primary_assertions_mutated'] is False
    assert result['automatic_repair_allowed'] is False and result['canonical_authority'] is False
    assert result['mass_extraction_authorized'] is False


def test_factory_without_recall_does_not_claim_recall_certification():
    u=unit('Propofol caused apnea.'); a=primary(u)
    r=run_semantic_factory(primary_assertions=a,source_units=[u],verifier_config=vcfg(),reviewer=reviewer)
    assert r['blind_recall'] is None and r['metrics']['recall_lane_run'] is False
    assert r['recall_assertions_are_unverified'] is None


def test_factory_rejects_recall_verifier_code_hash_split():
    u=unit(); a=primary(u)
    with pytest.raises(ValueError,match='same estate code hash'):
        run_semantic_factory(primary_assertions=a,source_units=[u],verifier_config=vcfg('c'*64),reviewer=reviewer,recall_config=rcfg('d'*64),recall_provider=lambda p:[])


def test_factory_run_id_is_deterministic_for_same_semantic_outputs():
    u=unit('Propofol caused apnea.'); a=primary(u)
    x=run_semantic_factory(primary_assertions=a,source_units=[u],verifier_config=vcfg(),reviewer=reviewer)
    y=run_semantic_factory(primary_assertions=a,source_units=[u],verifier_config=vcfg(),reviewer=reviewer)
    assert x['semantic_run_id']==y['semantic_run_id']
