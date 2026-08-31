import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.semantic_router import route_semantic_review,validate_review_case


def ev(aid,verdict,risk='LOW',ready=False,lanes=None,state=''):
    return {'assertion_id':aid,'source_unit_id':'UNIT:1','verdict':verdict,'risk_tier':risk,'downstream_semantic_ready':ready,'required_review_lanes':lanes or [],'review_state':state,'decision_basis':'TEST'}


def test_not_entailed_routes_to_cold_audit_without_authority():
    r=route_semantic_review(verification_events=[ev('ASSERT:1','NOT_ENTAILED','HIGH',False,['NUMERIC_BINDING'])])
    c=r['review_cases'][0]
    assert c['reason']=='ASSERTION_NOT_ENTAILED'
    assert 'COLD_AUDIT' in c['required_lanes'] and 'NUMERIC_BINDING' in c['required_lanes']
    assert c['automatic_repair_allowed'] is False and c['canonical_authority'] is False
    assert validate_review_case(c)==[]


def test_provenance_incomplete_routes_to_repair_and_cold_audit():
    r=route_semantic_review(verification_events=[ev('ASSERT:1','PROVENANCE_INCOMPLETE','LOW')])
    c=r['review_cases'][0]
    assert c['risk_tier']=='CRITICAL'
    assert c['required_lanes']==['PROVENANCE_REPAIR','COLD_AUDIT']


def test_entailed_ready_low_risk_creates_no_review_case():
    r=route_semantic_review(verification_events=[ev('ASSERT:1','ENTAILED','LOW',True,[])])
    assert r['review_cases']==[]


def test_critical_entailed_still_requires_frontier_adjudication():
    r=route_semantic_review(verification_events=[ev('ASSERT:1','ENTAILED','CRITICAL',True,[],state='DETERMINISTIC_REVIEW_COMPLETE')])
    c=r['review_cases'][0]
    assert c['reason']=='CRITICAL_ENTAILED_REQUIRES_ADJUDICATION'
    assert c['required_lanes']==['FRONTIER_ADJUDICATION']


def test_recall_only_candidate_is_review_work_not_automatic_repair():
    rec={'rows':[{'reconciliation_state':'RECALL_ONLY_CANDIDATE','recall_assertion_id':'ASSERT:R','source_unit_id':'UNIT:2'}]}
    r=route_semantic_review(verification_events=[],recall_reconciliation=rec)
    c=r['review_cases'][0]
    assert c['reason']=='RECALL_ONLY_CANDIDATE'
    assert 'BLIND_RECALL_REVIEW' in c['required_lanes']
    assert c['automatic_action_allowed'] is False


def test_same_evidence_disagreement_routes_frontier_and_preserves_both_ids():
    rec={'rows':[{'reconciliation_state':'SAME_EVIDENCE_SEMANTIC_DISAGREEMENT','primary_assertion_id':'ASSERT:P','recall_assertion_id':'ASSERT:R','source_unit_id':'UNIT:2'}]}
    r=route_semantic_review(verification_events=[],recall_reconciliation=rec)
    c=r['review_cases'][0]
    assert c['reason']=='SAME_EVIDENCE_SEMANTIC_DISAGREEMENT'
    assert c['assertion_ids']==['ASSERT:P'] and c['recall_assertion_ids']==['ASSERT:R']
    assert 'FRONTIER_ADJUDICATION' in c['required_lanes']


def test_primary_only_and_exact_recall_agreement_do_not_manufacture_defects():
    rec={'rows':[{'reconciliation_state':'PRIMARY_ONLY','primary_assertion_id':'ASSERT:P','source_unit_id':'UNIT:1'},{'reconciliation_state':'PRIMARY_AND_RECALL_EXACT','assertion_id':'ASSERT:X','source_unit_id':'UNIT:2'}]}
    r=route_semantic_review(verification_events=[],recall_reconciliation=rec)
    assert r['review_cases']==[]


def test_router_is_deterministic_and_deduplicates_identical_cases():
    e=ev('ASSERT:1','AMBIGUOUS','MEDIUM',False,['PRECISION_REVIEW'])
    a=route_semantic_review(verification_events=[e,e])
    b=route_semantic_review(verification_events=[e,e])
    assert a['review_cases']==b['review_cases'] and len(a['review_cases'])==1

def test_recall_only_critical_dose_is_not_under_routed():
    rec={'rows':[{'reconciliation_state':'RECALL_ONLY_CANDIDATE','recall_assertion_id':'ASSERT:R','source_unit_id':'UNIT:2'}]}
    recall=[{'assertion_id':'ASSERT:R','assertion_type':'DOSING','numeric':{'value':0.5,'unit':'mg/kg'}}]
    r=route_semantic_review(verification_events=[],recall_reconciliation=rec,recall_assertions=recall)
    c=r['review_cases'][0]
    assert c['risk_tier']=='CRITICAL'
    assert 'NUMERIC_BINDING' in c['required_lanes'] and 'QUALIFIER_SCOPE' in c['required_lanes']
    assert 'FRONTIER_ADJUDICATION' in c['required_lanes']


def test_same_evidence_disagreement_inherits_primary_and_recall_risk_lanes():
    rec={'rows':[{'reconciliation_state':'SAME_EVIDENCE_SEMANTIC_DISAGREEMENT','primary_assertion_id':'ASSERT:P','recall_assertion_id':'ASSERT:R','source_unit_id':'UNIT:2'}]}
    recall=[{'assertion_id':'ASSERT:R','assertion_type':'DOSING','numeric':{'value':1,'unit':'mg/kg'}}]
    primary=ev('ASSERT:P','ENTAILED','HIGH',False,['QUALIFIER_SCOPE'])
    r=route_semantic_review(verification_events=[primary],recall_reconciliation=rec,recall_assertions=recall)
    c=r['review_cases'][0]
    assert c['risk_tier']=='CRITICAL'
    assert {'QUALIFIER_SCOPE','NUMERIC_BINDING','FRONTIER_ADJUDICATION'} <= set(c['required_lanes'])
