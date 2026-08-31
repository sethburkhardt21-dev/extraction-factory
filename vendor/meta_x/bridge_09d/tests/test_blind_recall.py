import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit
from bridge_09d.assertion_engine import EngineConfig,proposal_to_assertion
from bridge_09d.blind_recall import build_blind_recall_request,reconcile_primary_recall,run_blind_recall

CFG=EngineConfig(engine='blind-recall-worker',engine_version='1',code_manifest_sha256='c'*64,mode='MODEL_ASSISTED',model='recall-x',model_revision='1',prompt_sha256='d'*64)
def unit(): return build_source_unit(source_record_key='p:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text='Propofol caused apnea and reduced blood pressure.')
def p(prop,evidence,atype): return {'assertion_type':atype,'normalized_proposition':prop,'evidence_text':evidence}

def test_blind_recall_packet_contains_no_primary_outputs():
    req=build_blind_recall_request(unit()); text=str(req)
    assert 'primary_assertions' not in text and req['recall_task']['independent_of_primary_extractor'] is True

def test_blind_recall_outputs_remain_unverified_and_non_authoritative():
    r=run_blind_recall([unit()],provider=lambda u:[p('Propofol caused apnea.','Propofol caused apnea','ADVERSE_EFFECT')],config=CFG)
    assert r['assertions'][0]['verification_status']=='NOT_VERIFIED' and r['authority_granted'] is False

def test_exact_primary_and_recall_assertion_is_coverage_agreement_not_promotion():
    u=unit(); proposal=p('Propofol caused apnea.','Propofol caused apnea','ADVERSE_EFFECT')
    a=proposal_to_assertion(u,proposal,config=CFG)
    rec=reconcile_primary_recall([a],[a])
    assert rec['counts']['PRIMARY_AND_RECALL_EXACT']==1 and rec['automatic_merge_allowed'] is False

def test_recall_only_candidate_is_preserved_for_later_review():
    u=unit(); a=proposal_to_assertion(u,p('Propofol caused apnea.','Propofol caused apnea','ADVERSE_EFFECT'),config=CFG)
    b=proposal_to_assertion(u,p('Propofol reduced blood pressure.','reduced blood pressure','TREATMENT_EFFECT'),config=CFG)
    rec=reconcile_primary_recall([a],[a,b])
    assert rec['counts']['RECALL_ONLY_CANDIDATE']==1 and rec['automatic_repair_allowed'] is False

def test_same_evidence_different_semantics_is_disagreement_not_silent_dedup():
    u=unit(); a=proposal_to_assertion(u,p('Propofol caused apnea.','Propofol caused apnea','ADVERSE_EFFECT'),config=CFG)
    b=proposal_to_assertion(u,p('Propofol was associated with apnea.','Propofol caused apnea','ADVERSE_EFFECT'),config=CFG)
    rec=reconcile_primary_recall([a],[b])
    assert rec['counts']['SAME_EVIDENCE_SEMANTIC_DISAGREEMENT']==1
