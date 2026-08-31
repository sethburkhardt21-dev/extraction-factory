import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit
from bridge_09d.assertion_engine import (
    EngineConfig, build_model_request, extract_assertions, proposal_to_assertion,
    structured_clinicaltrials_provider, deterministic_structured_config,
)

CODE='c'*64; PROMPT='p'.encode().hex()  # not used; helper below

def model_cfg(revision='1'):
    return EngineConfig(engine='frontier-assertion-provider',engine_version='1.0',code_manifest_sha256=CODE,
                        mode='MODEL_ASSISTED',model='model-x',model_revision=revision,prompt_sha256='b'*64)

def text_unit(text='Adults received propofol 0.5 mg/kg IV before induction.'):
    return build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,
        source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','section':'Methods','paragraph':2},content_text=text)

def json_unit(path,value):
    return build_source_unit(source_record_key='ctg:NCT1',source_resource_id='NCT:NCT1',source_version_id='2026-01-01',source_sha256='d'*64,
        source_scope='REGISTRY_STRUCTURED',unit_kind='JSON_FIELD',locator={'locator_type':'JSON_PATH','json_path':path},content_json=value)


def test_model_request_exposes_evidence_but_no_authority_mutation_surface():
    req=build_model_request(text_unit())
    assert req['source_unit']['content_text'].startswith('Adults received')
    assert req['authority']['canonical_authority'] is False
    assert 'subject_candidate_id' not in req['source_unit'] and 'object_candidate_id' not in req['source_unit']


def test_exact_text_proposal_becomes_not_verified_assertion_with_engine_owned_offsets():
    u=text_unit(); proposal={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered at 0.5 mg/kg IV.',
        'evidence_text':'propofol 0.5 mg/kg IV','numeric':{'value':0.5,'unit':'mg/kg'},'context':{'route':'IV'}}
    a=proposal_to_assertion(u,proposal,config=model_cfg())
    assert a['verification_status']=='NOT_VERIFIED'
    assert a['evidence_span']['text']=='propofol 0.5 mg/kg IV'
    assert a['evidence_span']['char_start']==u['content_text'].index('propofol')
    assert a['subject_candidate_id'] is None and a['canonical_authority'] is False


def test_repeated_evidence_requires_explicit_start():
    u=text_unit('Dose 5 mg. Later dose 5 mg.')
    p={'assertion_type':'DOSING','normalized_proposition':'A dose of 5 mg was reported.','evidence_text':'5 mg'}
    with pytest.raises(ValueError,match='multiple times'): proposal_to_assertion(u,p,config=model_cfg())
    p['char_start']=u['content_text'].rindex('5 mg')
    assert proposal_to_assertion(u,p,config=model_cfg())['evidence_span']['char_start']==p['char_start']


def test_provider_cannot_set_verification_authority_or_candidate_ids():
    u=text_unit(); p={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol',
        'verification_status':'ENTAILED','generation_eligible':True,'subject_candidate_id':'CAND:x'}
    with pytest.raises(ValueError,match='engine-owned fields'): proposal_to_assertion(u,p,config=model_cfg())


def test_atomicity_guard_rejects_obvious_compound_multisentence_output():
    u=text_unit(); p={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered. Blood pressure fell.','evidence_text':'propofol'}
    with pytest.raises(ValueError,match='one atomic sentence'): proposal_to_assertion(u,p,config=model_cfg())


def test_json_proposal_must_use_exact_frozen_source_unit_path():
    u=json_unit('$.protocolSection.designModule.enrollmentInfo.count',10)
    p={'assertion_type':'STUDY_ENROLLMENT','normalized_proposition':'The study enrollment was 10 participants.','structured_evidence_path':'$.wrong'}
    with pytest.raises(ValueError,match='exactly equal'): proposal_to_assertion(u,p,config=model_cfg())


def test_structured_ctg_provider_emits_selected_high_precision_facts_only():
    units=[
        json_unit('$.protocolSection.designModule.enrollmentInfo.count',46969),
        json_unit('$.protocolSection.designModule.phases[0]','PHASE2'),
        json_unit('$.protocolSection.statusModule.overallStatus','COMPLETED'),
        json_unit('$.protocolSection.identificationModule.briefTitle','A title'),
        json_unit('$.protocolSection.statusModule.whyStopped',None),
    ]
    r=extract_assertions(units,provider=structured_clinicaltrials_provider,config=deterministic_structured_config(code_manifest_sha256=CODE))
    assert r['status']=='PASS'
    assert r['metrics']['assertions_emitted']==3
    assert {a['assertion_type'] for a in r['assertions']}=={'STUDY_ENROLLMENT','TRIAL_PROTOCOL_FACT'}
    assert all(a['verification_status']=='NOT_VERIFIED' for a in r['assertions'])


def test_bad_provider_outputs_are_quarantined_not_silently_dropped():
    u=text_unit()
    def provider(_):
        return [
            {'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol'},
            {'assertion_type':'NOT_A_TYPE','normalized_proposition':'Bad.','evidence_text':'propofol'},
        ]
    r=extract_assertions([u],provider=provider,config=model_cfg())
    assert r['status']=='PASS_WITH_QUARANTINE'
    assert r['metrics']['assertions_emitted']==1 and r['metrics']['proposals_quarantined']==1
    assert 'frozen registry' in r['quarantine'][0]['error']


def test_provider_exception_becomes_quarantine_and_does_not_grant_pass_evidence():
    def provider(_): raise RuntimeError('provider unavailable')
    r=extract_assertions([text_unit()],provider=provider,config=model_cfg())
    assert r['assertions']==[] and len(r['quarantine'])==1
    assert 'provider failure' in r['quarantine'][0]['error']


def test_same_evidence_proposal_and_provenance_is_deterministic():
    u=text_unit(); p={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol'}
    a=proposal_to_assertion(u,p,config=model_cfg('1')); b=proposal_to_assertion(u,p,config=model_cfg('1'))
    assert (a['assertion_id'],a['interpretation_id'])==(b['assertion_id'],b['interpretation_id'])


def test_model_revision_changes_interpretation_not_assertion_identity():
    u=text_unit(); p={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol'}
    a=proposal_to_assertion(u,p,config=model_cfg('1')); b=proposal_to_assertion(u,p,config=model_cfg('2'))
    assert a['assertion_id']==b['assertion_id'] and a['interpretation_id']!=b['interpretation_id']


def test_unresolved_entity_surfaces_are_not_candidate_ids():
    u=text_unit(); p={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol','subject_surface':'propofol'}
    a=proposal_to_assertion(u,p,config=model_cfg())
    assert a['subject_candidate_id'] is None
    assert a['context']['unresolved_entity_surfaces']['subject_surface']=='propofol'


def test_assertion_pipeline_persists_hash_bound_unverified_outputs(tmp_path):
    from bridge_09d.assertion_pipeline import run_assertion_pipeline
    u=text_unit(); src=tmp_path/'units.jsonl'; src.write_text(json.dumps(u)+'\n')
    out=tmp_path/'out'
    result=run_assertion_pipeline(source_units_path=src,output_dir=out,
        provider=lambda unit:[{'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol'}],config=EngineConfig(engine='frontier-assertion-provider',engine_version='1.0',code_manifest_sha256=__import__('frontier_core.readiness',fromlist=['code_manifest']).code_manifest(ROOT)['sha256'],mode='MODEL_ASSISTED',model='model-x',model_revision='1',prompt_sha256='b'*64))
    m=json.loads((out/'manifest.json').read_text())
    assert m['status']=='PASS' and m['semantic_verification_performed'] is False
    assert m['canonical_authority'] is False and m['metrics']['assertions_emitted']==1
    assert json.loads((out/'assertions.jsonl').read_text().splitlines()[0])['verification_status']=='NOT_VERIFIED'


def test_nested_authority_or_candidate_fields_are_rejected():
    u=text_unit(); p={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol','context':{'nested':{'generation_eligible':True}}}
    with pytest.raises(ValueError,match='nests forbidden'): proposal_to_assertion(u,p,config=model_cfg())


def test_candidate_like_surface_cannot_masquerade_as_resolved_identity():
    u=text_unit(); p={'assertion_type':'DOSING','normalized_proposition':'Propofol was administered.','evidence_text':'propofol','subject_surface':'CAND:deadbeef'}
    with pytest.raises(ValueError,match='masquerade'): proposal_to_assertion(u,p,config=model_cfg())


def test_assertion_pipeline_rejects_claimed_code_hash_not_matching_running_estate(tmp_path):
    from bridge_09d.assertion_pipeline import run_assertion_pipeline
    u=text_unit(); src=tmp_path/'units.jsonl'; src.write_text(json.dumps(u)+'\n')
    with pytest.raises(RuntimeError,match='code hash does not match'):
        run_assertion_pipeline(source_units_path=src,output_dir=tmp_path/'out',provider=lambda unit:[],config=model_cfg())
