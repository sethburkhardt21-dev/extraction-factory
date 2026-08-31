import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import *


def unit_text():
    text='Adults received propofol 0.5 mg/kg IV before induction.'
    return build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','section':'Methods','paragraph':2},content_text=text)


def test_source_unit_identity_is_deterministic_and_exact_text_sensitive():
    a=unit_text(); b=unit_text(); assert a['source_unit_id']==b['source_unit_id']
    c=build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','section':'Methods','paragraph':2},content_text=a['content_text']+' ')
    assert c['source_unit_id']!=a['source_unit_id']


def test_assertion_span_must_exactly_match_source_unit():
    u=unit_text(); text=u['content_text']; phrase='propofol 0.5 mg/kg IV'; start=text.index(phrase)
    a=build_assertion(source_unit=u,assertion_type='DOSING',normalized_proposition='Propofol was administered at 0.5 mg/kg IV.',evidence_span={'char_start':start,'char_end':start+len(phrase),'utf8_byte_start':len(u['content_text'][:start].encode('utf-8')),'utf8_byte_end':len(u['content_text'][:start+len(phrase)].encode('utf-8')),'text':phrase,'text_sha256':sha256_hex(phrase.encode('utf-8'))},context={'population':'adults','route':'IV'},numeric={'value':0.5,'unit':'mg/kg'},extractor_provenance={'mode':'MODEL_ASSISTED','engine':'assertion-engine','engine_version':'1','code_manifest_sha256':'c'*64,'model':'m','model_revision':'1','prompt_sha256':'b'*64})
    assert a['verification_status']=='NOT_VERIFIED' and a['canonical_authority'] is False
    bad=dict(a); bad['evidence_span']=dict(a['evidence_span']); bad['evidence_span']['text']='wrong'
    assert any('does not match source unit' in x for x in validate_assertion(bad,source_unit=u))


def test_interpretation_version_changes_without_mutating_source_unit_identity():
    u=unit_text(); phrase='propofol 0.5 mg/kg IV'; start=u['content_text'].index(phrase)
    common=dict(source_unit=u,assertion_type='DOSING',normalized_proposition='Propofol was administered at 0.5 mg/kg IV.',evidence_span={'char_start':start,'char_end':start+len(phrase),'utf8_byte_start':len(u['content_text'][:start].encode('utf-8')),'utf8_byte_end':len(u['content_text'][:start+len(phrase)].encode('utf-8')),'text':phrase,'text_sha256':sha256_hex(phrase.encode('utf-8'))},context={'route':'IV'})
    a=build_assertion(**common,extractor_provenance={'mode':'MODEL_ASSISTED','engine':'assertion-engine','engine_version':'1','code_manifest_sha256':'c'*64,'model':'A','model_revision':'1','prompt_sha256':'a'*64})
    b=build_assertion(**common,extractor_provenance={'mode':'MODEL_ASSISTED','engine':'assertion-engine','engine_version':'1','code_manifest_sha256':'c'*64,'model':'B','model_revision':'1','prompt_sha256':'b'*64})
    assert a['assertion_id']==b['assertion_id']
    assert a['interpretation_id']!=b['interpretation_id']
    assert a['source_unit_id']==b['source_unit_id']==u['source_unit_id']


def test_structured_registry_assertion_requires_exact_path():
    u=build_source_unit(source_record_key='ctg:NCT1',source_resource_id='NCT:NCT1',source_version_id='2026-01-01',source_sha256='c'*64,source_scope='REGISTRY_STRUCTURED',unit_kind='JSON_FIELD',locator={'locator_type':'JSON_PATH','json_path':'$.protocolSection.designModule.enrollmentInfo.count'},content_json=10)
    a=build_assertion(source_unit=u,assertion_type='STUDY_ENROLLMENT',normalized_proposition='The actual enrollment was 10 participants.',structured_evidence_path='$.protocolSection.designModule.enrollmentInfo.count',numeric={'value':10,'unit':'participants'},extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'ctg-structured','engine_version':'1','code_manifest_sha256':'c'*64})
    assert validate_assertion(a,source_unit=u)==[]
    bad=dict(a); bad['structured_evidence_path']='$.protocolSection.designModule.phases[0]'
    assert any('does not resolve' in x for x in validate_assertion(bad,source_unit=u))


def test_missing_evidence_closure_fails_closed():
    with pytest.raises(ValueError,match='evidence'):
        build_assertion(source_unit=unit_text(),assertion_type='EFFICACY',normalized_proposition='X worked.',extractor_provenance={'mode':'MODEL_ASSISTED','engine':'assertion-engine','engine_version':'1','code_manifest_sha256':'c'*64,'model':'x','model_revision':'1','prompt_sha256':'d'*64})

def test_utf8_byte_offsets_are_independently_verified():
    text='Dose was 5 µg/kg IV.'
    u=build_source_unit(source_record_key='pubmed:unicode',source_resource_id='PMID:unicode',source_version_id='1',source_sha256='e'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','section':'Results','paragraph':1},content_text=text)
    phrase='5 µg/kg'; start=text.index(phrase); end=start+len(phrase)
    span={'char_start':start,'char_end':end,'utf8_byte_start':len(text[:start].encode()),'utf8_byte_end':len(text[:end].encode()),'text':phrase,'text_sha256':sha256_hex(phrase.encode())}
    a=build_assertion(source_unit=u,assertion_type='DOSING',normalized_proposition='The dose was 5 µg/kg IV.',evidence_span=span,context={'route':'IV'},extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':'f'*64})
    assert validate_assertion(a,source_unit=u)==[]
    bad=dict(a); bad['evidence_span']=dict(span); bad['evidence_span']['utf8_byte_end']-=1
    assert any('UTF-8 byte offsets' in x for x in validate_assertion(bad,source_unit=u))


def test_unknown_assertion_type_is_rejected_by_frozen_registry():
    u=unit_text(); phrase='propofol'; start=u['content_text'].index(phrase)
    span={'char_start':start,'char_end':start+len(phrase),'utf8_byte_start':start,'utf8_byte_end':start+len(phrase),'text':phrase,'text_sha256':sha256_hex(phrase.encode())}
    with pytest.raises(ValueError,match='controlled registry'):
        build_assertion(source_unit=u,assertion_type='MADE_UP_TYPE',normalized_proposition='Propofol was mentioned.',evidence_span=span,extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':'f'*64})


def test_proposition_normalization_preserves_clinical_numeric_semantics():
    assert normalize_proposition('10⁶ cells/mL') == '10⁶ cells/mL'
    assert normalize_proposition('10⁻⁶ M') == '10⁻⁶ M'
    assert normalize_proposition('dose 2½ tablets') == 'dose 2½ tablets'
    assert normalize_proposition('⅓ dose') == '⅓ dose'
    assert normalize_proposition('10⁶') != normalize_proposition('106')


def test_out_of_range_evidence_span_fails_closed_and_unbound_validation_is_explicit():
    u=unit_text(); fake='Give 400 mg morphine IV.'
    row={
      'assertion_schema_version':ASSERTION_SCHEMA_VERSION,'assertion_id':'ASSERT:x','interpretation_id':'INTERP:x',
      'source_unit_id':u['source_unit_id'],'source_record_key':u['source_record_key'],'source_resource_id':u['source_resource_id'],
      'source_version_id':u['source_version_id'],'source_sha256':u['source_sha256'],'source_unit_sha256':u['content_sha256'],
      'source_scope':u['source_scope'],'locator':u['locator'],'normalized_proposition':'Morphine 400 mg IV.','assertion_type':'DOSING',
      'evidence_span':{'char_start':9000,'char_end':9000+len(fake),'utf8_byte_start':9000,'utf8_byte_end':9000+len(fake.encode()),'text':fake,'text_sha256':sha256_hex(fake.encode())},
      'structured_evidence_path':None,'extractor_provenance':{'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':'f'*64},
      'verification_status':'NOT_VERIFIED','automatic_selection_allowed':False,'canonical_authority':False,'canonical_internal_eligible':False,'generation_eligible':False,'public_eligible':False,
    }
    assert any('outside source unit' in x for x in validate_assertion(row,source_unit=u))
    assert any('unbound assertion' in x for x in validate_assertion(row))


def test_source_unit_v12_identity_binds_scope_resource_and_source_hash():
    common=dict(source_record_key='pubmed:1',source_version_id='1',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text='same')
    a=build_source_unit(**common,source_resource_id='PMID:1',source_sha256='a'*64,source_scope='FULL_TEXT')
    b=build_source_unit(**common,source_resource_id='PMID:2',source_sha256='a'*64,source_scope='FULL_TEXT')
    c=build_source_unit(**common,source_resource_id='PMID:1',source_sha256='b'*64,source_scope='FULL_TEXT')
    d=build_source_unit(**common,source_resource_id='PMID:1',source_sha256='a'*64,source_scope='ABSTRACT_ONLY')
    assert len({x['source_unit_id'] for x in (a,b,c,d)})==4


def test_source_unit_v11_requires_content_representation_but_v10_can_infer():
    u=unit_text(); u['source_unit_schema_version']='frontier-source-unit-1.1'; u.pop('content_representation')
    assert any('content_representation required' in x for x in validate_source_unit(u))
