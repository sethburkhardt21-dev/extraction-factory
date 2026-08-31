import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit
from bridge_09d.assertion_engine import EngineConfig,extract_assertions
from bridge_09d.identity_resolution import resolve_assertion_mentions
from bridge_09d.verifier import VerifierConfig,verify_assertions

SHA='c'*64

def _unit(text='Propofol was administered at 0.5 mg/kg IV.'):
    return build_source_unit(source_record_key='p:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text=text)

def _assertion(unit, at='DOSING', surface='Propofol'):
    cfg=EngineConfig(engine='p',engine_version='1',code_manifest_sha256=SHA,mode='MODEL_ASSISTED',model='m',model_revision='1',prompt_sha256='d'*64)
    return extract_assertions([unit],provider=lambda u:[{'assertion_type':at,'normalized_proposition':'Propofol was administered at 0.5 mg/kg IV.','evidence_text':'Propofol was administered at 0.5 mg/kg IV.','subject_surface':surface,'numeric':{'value':0.5,'unit':'mg/kg'},'context':{'route':'IV'}}],config=cfg)['assertions'][0]

def _verified(assertion,unit,ready=True):
    cfg=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=SHA,mode='MODEL_ASSISTED',model='v',model_revision='1',prompt_sha256='e'*64)
    response={'verdict':'ENTAILED' if ready else 'PARTIAL','rationale':'test','confidence':'HIGH','resolved_warning_codes':[]}
    return verify_assertions([assertion],[unit],config=cfg,reviewer=lambda req:response)['verification_events'][0]


def test_drug_mention_registers_source_occurrence_candidate_without_canonical_assignment():
    u=_unit(); a=_assertion(u); v=_verified(a,u)
    r=resolve_assertion_mentions(assertions=[a],verification_events=[v],origin_package_id='FRONTIER:test')
    assert r['metrics']['candidates_registered']==1
    c=r['candidate_records'][0]
    assert c['candidate_id'].startswith('CAND:') and c['domain']=='drug'
    assert c['state']=='REGISTERED' and c['legacy_entity_id'] is None
    assert c['semantic_ready_for_resolution'] is True
    assert r['candidate_to_canonical_assignment_performed'] is False
    assert r['canonical_authority'] is False


def test_ambiguous_assertion_domain_creates_review_case_but_no_candidate():
    u=_unit(); a=_assertion(u,at='ASSOCIATION'); v=_verified(a,u)
    r=resolve_assertion_mentions(assertions=[a],verification_events=[v],origin_package_id='FRONTIER:test')
    assert r['candidate_records']==[]
    assert r['identity_cases'][0]['state']=='DOMAIN_AMBIGUOUS'


def test_semantically_unready_claim_can_be_registered_but_not_resolution_ready():
    u=_unit(); a=_assertion(u); v=_verified(a,u,ready=False)
    r=resolve_assertion_mentions(assertions=[a],verification_events=[v],origin_package_id='FRONTIER:test')
    c=r['candidate_records'][0]
    assert c['semantic_ready_for_resolution'] is False
    assert r['identity_cases'][0]['state']=='SEMANTIC_NOT_READY'


def test_same_surface_in_two_assertions_does_not_silently_cluster_candidates():
    u1=_unit(); a1=_assertion(u1)
    u2=build_source_unit(source_record_key='p:2',source_resource_id='PMID:2',source_version_id='1',source_sha256='b'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text='Propofol was administered at 0.5 mg/kg IV.')
    a2=_assertion(u2)
    v1=_verified(a1,u1); v2=_verified(a2,u2)
    r=resolve_assertion_mentions(assertions=[a1,a2],verification_events=[v1,v2],origin_package_id='FRONTIER:test')
    assert len(r['candidate_records'])==2
    assert len({x['candidate_id'] for x in r['candidate_records']})==2
    assert all(x['automatic_identity_merge_allowed'] is False for x in r['candidate_records'])
