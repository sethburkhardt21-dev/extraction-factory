import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit,build_assertion,sha256_hex
from bridge_09d.assertion_verifier import VerifierConfig,verify_assertion

GOLD=json.loads((Path(__file__).parent/'fixtures/semantic_gold/CASES.json').read_text())
CFG=VerifierConfig(engine='semantic-gold-verifier',engine_version='1',code_manifest_sha256='c'*64,mode='MODEL_ASSISTED',model='gold-reviewer',model_revision='1',prompt_sha256='d'*64)
DCFG=VerifierConfig(engine='semantic-gold-verifier',engine_version='1',code_manifest_sha256='c'*64,mode='DETERMINISTIC_REVIEW')
RISK_ORDER={'LOW':0,'MODERATE':1,'HIGH':2,'CRITICAL':3}

def reviewer(case):
    return lambda req:{'verdict':case['reviewer'],'rationale':'Hand-authored gold reviewer outcome.','confidence':'HIGH','resolved_warning_codes':case.get('resolved',[])}

def make_text(case):
    u=build_source_unit(source_record_key='gold:'+case['id'],source_resource_id='GOLD:'+case['id'],source_version_id='1',source_sha256='a'*64,
        source_scope=case.get('scope','FULL_TEXT'),unit_kind=case.get('kind','TEXT'),locator={'locator_type':'TABLE_CELL','row_index':1,'col_index':1} if case.get('scope')=='TABLE' else {'locator_type':'PARAGRAPH','paragraph':1},content_text=case['text'])
    start=case['text'].index(case['evidence']); end=start+len(case['evidence'])
    span={'char_start':start,'char_end':end,'utf8_byte_start':len(case['text'][:start].encode()),'utf8_byte_end':len(case['text'][:end].encode()),'text':case['evidence'],'text_sha256':sha256_hex(case['evidence'].encode())}
    a=build_assertion(source_unit=u,assertion_type=case['type'],normalized_proposition=case['proposition'],evidence_span=span,numeric=case.get('numeric'),context=case.get('context',{}),negated=case.get('negated',False),extractor_provenance={'mode':'MODEL_ASSISTED','engine':'gold-extractor','engine_version':'1','code_manifest_sha256':'b'*64,'model':'hidden-primary','model_revision':'1','prompt_sha256':'e'*64})
    return u,a

def test_hand_authored_text_semantic_gold_cases():
    failures=[]
    for case in GOLD['cases']:
        u,a=make_text(case); ev=verify_assertion(a,u,config=CFG,reviewer=reviewer(case))
        if ev['verdict']!=case['expected']: failures.append((case['id'],'verdict',case['expected'],ev['verdict'],ev.get('decision_basis')))
        if ev['downstream_semantic_ready'] is not case['ready']: failures.append((case['id'],'ready',case['ready'],ev['downstream_semantic_ready'],ev.get('review_state')))
        if 'risk' in case and ev['specialist_capsules']['risk_route']['risk_level']!=case['risk']: failures.append((case['id'],'risk',case['risk'],ev['specialist_capsules']['risk_route']['risk_level'],''))
        if 'minimum_risk' in case and RISK_ORDER[ev['specialist_capsules']['risk_route']['risk_level']]<RISK_ORDER[case['minimum_risk']]: failures.append((case['id'],'minimum_risk',case['minimum_risk'],ev['specialist_capsules']['risk_route']['risk_level'],''))
    assert not failures, failures

def test_hand_authored_structured_semantic_gold_cases():
    failures=[]
    for case in GOLD['structured_cases']:
        u=build_source_unit(source_record_key='gold:'+case['id'],source_resource_id='GOLD:'+case['id'],source_version_id='1',source_sha256='f'*64,source_scope='REGISTRY_STRUCTURED',unit_kind='JSON_FIELD',locator={'locator_type':'JSON_PATH','json_path':case['path']},content_json=case['value'])
        a=build_assertion(source_unit=u,assertion_type=case['type'],normalized_proposition=case['proposition'],structured_evidence_path=case['path'],numeric=case.get('numeric'),extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'gold-ctg','engine_version':'1','code_manifest_sha256':'b'*64})
        ev=verify_assertion(a,u,config=DCFG)
        if ev['verdict']!=case['expected']: failures.append((case['id'],case['expected'],ev['verdict'],ev.get('decision_basis')))
    assert not failures, failures
