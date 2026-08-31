import json
from pathlib import Path
import pytest
from bridge_09d.assertions import build_source_unit, build_assertion, sha256_hex
from bridge_09d.verifier import VerifierConfig, verify_assertion

CASES=json.loads((Path(__file__).parent/'fixtures/semantic_verifier/CASES.json').read_text())['cases']
CODE='c'*64
CFG=VerifierConfig(engine='semantic-gold-verifier',engine_version='1',code_manifest_sha256=CODE)

def build(case):
    if case['kind']=='text':
        u=build_source_unit(source_record_key='GOLD:'+case['id'],source_resource_id='GOLDRES:'+case['id'],source_version_id='1',source_sha256='a'*64,source_scope=case.get('scope','FULL_TEXT'),unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','xpath':'/article/body/sec/p'},content_text=case['evidence'])
        text=case['evidence']; start=0; end=len(text)
        span={'char_start':start,'char_end':end,'utf8_byte_start':0,'utf8_byte_end':len(text.encode()),'text':text,'text_sha256':sha256_hex(text.encode())}
        a=build_assertion(source_unit=u,assertion_type=case['assertion_type'],normalized_proposition=case['proposition'],evidence_span=span,numeric=case.get('numeric'),context=case.get('context'),negated=case.get('negated',False),conditional=case.get('conditional',False),extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'gold','engine_version':'1','code_manifest_sha256':CODE})
    else:
        u=build_source_unit(source_record_key='GOLD:'+case['id'],source_resource_id='GOLDRES:'+case['id'],source_version_id='1',source_sha256='b'*64,source_scope='REGISTRY_STRUCTURED',unit_kind='JSON_FIELD',locator={'locator_type':'JSON_PATH','json_path':case['path']},content_json=case['value'])
        a=build_assertion(source_unit=u,assertion_type=case['assertion_type'],normalized_proposition=case['proposition'],structured_evidence_path=case['path'],numeric=case.get('numeric'),context=case.get('context'),negated=case.get('negated',False),conditional=case.get('conditional',False),extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'gold','engine_version':'1','code_manifest_sha256':CODE})
    return u,a

@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_semantic_gold(case):
    u,a=build(case); v=verify_assertion(a,u,config=CFG)
    assert v['verdict']==case['expected_verdict']
    assert v['risk_tier']==case['expected_risk']
    if case.get('required_lane'): assert case['required_lane'] in v['required_review_lanes']
    assert v['canonical_authority'] is False and v['automatic_selection_allowed'] is False
