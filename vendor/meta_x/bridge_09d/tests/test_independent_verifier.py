from bridge_09d.assertions import build_source_unit, build_assertion, sha256_hex
from bridge_09d.verifier import (
    VerifierConfig, verify_assertion, verify_assertions, validate_verification_event,
    blind_verifier_payload
)

CODE='c'*64
CFG=VerifierConfig(engine='blind-verifier',engine_version='1',code_manifest_sha256=CODE)

def text_unit(text, *, scope='FULL_TEXT', section=None):
    return build_source_unit(
        source_record_key='SRC:1',source_resource_id='PMID:1',source_version_id='V1',source_sha256='a'*64,
        source_scope=scope,unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','xpath':'/article/body/sec/p', 'section_path':section or []},
        content_text=text
    )

def text_assertion(unit, proposition, *, evidence=None, at='OTHER_CLINICAL_ASSERTION', numeric=None, context=None, negated=False):
    evidence = unit['content_text'] if evidence is None else evidence
    start=unit['content_text'].index(evidence); end=start+len(evidence)
    span={'char_start':start,'char_end':end,'utf8_byte_start':len(unit['content_text'][:start].encode()),'utf8_byte_end':len(unit['content_text'][:end].encode()),'text':evidence,'text_sha256':sha256_hex(evidence.encode())}
    return build_assertion(source_unit=unit,assertion_type=at,normalized_proposition=proposition,evidence_span=span,numeric=numeric,context=context,negated=negated,extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':CODE})

def structured_unit(value, path='$.protocolSection.designModule.enrollmentInfo.count'):
    return build_source_unit(source_record_key='CTG:1',source_resource_id='NCT:1',source_version_id='V1',source_sha256='b'*64,source_scope='REGISTRY_STRUCTURED',unit_kind='JSON_FIELD',locator={'locator_type':'JSON_PATH','json_path':path},content_json=value)

def test_exact_text_is_entailed_but_non_authoritative():
    u=text_unit('Propofol may cause hypotension.')
    a=text_assertion(u,'Propofol may cause hypotension.')
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='ENTAILED'
    assert v['canonical_authority'] is False and v['automatic_selection_allowed'] is False
    assert not validate_verification_event(v,assertion=a,source_unit=u)

def test_paraphrase_without_independent_semantic_provider_is_ambiguous():
    u=text_unit('Propofol may cause hypotension.')
    a=text_assertion(u,'Propofol can lower blood pressure.')
    assert verify_assertion(a,u,config=CFG)['verdict']=='AMBIGUOUS'

def test_numeric_mismatch_is_hard_not_entailed():
    u=text_unit('Ondansetron 4 mg IV was administered.')
    a=text_assertion(u,'Ondansetron 40 mg IV was administered.',at='DOSING',numeric={'value':40,'unit':'mg'},context={'route':'IV'})
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='NOT_ENTAILED'
    assert any(c['check_code']=='NUMERIC_BINDING' and c['state']=='FAIL' for c in v['checks'])

def test_semantic_provider_cannot_override_numeric_failure():
    u=text_unit('Ondansetron 4 mg IV was administered.')
    a=text_assertion(u,'Ondansetron 40 mg IV was administered.',at='DOSING',numeric={'value':40,'unit':'mg'},context={'route':'IV'})
    v=verify_assertion(a,u,config=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=CODE,mode='MODEL_ASSISTED',model='m',model_revision='r',prompt_sha256='d'*64),semantic_provider=lambda payload:{'verdict':'ENTAILED','failed_dimensions':[]})
    assert v['verdict']=='NOT_ENTAILED'

def test_negation_mismatch_is_hard_failure():
    u=text_unit('The intervention reduced nausea.')
    a=text_assertion(u,'The intervention did not reduce nausea.',negated=True)
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='NOT_ENTAILED'
    assert any(c['check_code']=='NEGATION_PRESERVATION' and c['state']=='FAIL' for c in v['checks'])

def test_causal_overclaim_is_rejected():
    u=text_unit('Exposure was associated with postoperative nausea.')
    a=text_assertion(u,'Exposure caused postoperative nausea.',at='CAUSATION')
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='NOT_ENTAILED'
    assert any(c['check_code']=='RELATIONSHIP_BINDING' and c['state']=='FAIL' for c in v['checks'])

def test_structured_registry_exact_fact_is_entailed():
    u=structured_unit(120)
    a=build_assertion(source_unit=u,assertion_type='STUDY_ENROLLMENT',normalized_proposition='The study enrollment was 120 participants.',structured_evidence_path=u['locator']['json_path'],numeric={'value':120,'unit':'participants'},extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':CODE})
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='ENTAILED'
    assert any(c['check_code']=='NUMERIC_BINDING' and c['state']=='PASS' for c in v['checks'])

def test_dosing_numeric_routes_to_frontier_even_when_entailed():
    u=text_unit('Ondansetron 4 mg IV was administered.')
    a=text_assertion(u,'Ondansetron 4 mg IV was administered.',at='DOSING',numeric={'value':4,'unit':'mg'},context={'route':'IV'})
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='ENTAILED'
    assert v['risk_tier']=='CRITICAL'
    assert 'NUMERIC_BINDING' in v['required_review_lanes'] and 'FRONTIER_ADJUDICATION' in v['required_review_lanes']

def test_abstract_only_escalates_risk():
    u=text_unit('Treatment was associated with lower mortality.',scope='ABSTRACT_ONLY')
    a=text_assertion(u,'Treatment was associated with lower mortality.',at='ASSOCIATION')
    v=verify_assertion(a,u,config=CFG)
    assert v['risk_tier']=='HIGH' and 'PRECISION_REVIEW' in v['required_review_lanes']

def test_qualifier_not_locally_grounded_prevents_clean_entailment_with_provider():
    u=text_unit('Ondansetron 4 mg was administered.')
    a=text_assertion(u,'Ondansetron 4 mg was administered.',at='DOSING',numeric={'value':4,'unit':'mg'},context={'route':'IV'})
    cfg=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=CODE,mode='MODEL_ASSISTED',model='m',model_revision='r',prompt_sha256='d'*64)
    v=verify_assertion(a,u,config=cfg,semantic_provider=lambda payload:{'verdict':'ENTAILED','failed_dimensions':[]})
    assert v['verdict']=='PARTIAL'
    assert any(c['check_code']=='QUALIFIER_SCOPE' and c['state']=='WARN' for c in v['checks'])

def test_provider_is_blind_to_extractor_provenance_and_identity():
    u=text_unit('Propofol may cause hypotension.')
    a=text_assertion(u,'Propofol can lower blood pressure.')
    seen={}
    def provider(payload):
        seen.update(payload)
        assert 'extractor_provenance' not in payload and 'interpretation_id' not in payload and 'assertion_id' not in payload
        return {'verdict':'ENTAILED','failed_dimensions':[]}
    cfg=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=CODE,mode='MODEL_ASSISTED',model='m',model_revision='r',prompt_sha256='d'*64)
    v=verify_assertion(a,u,config=cfg,semantic_provider=provider)
    assert v['blind_independent_review'] is True and seen

def test_provider_cannot_inject_authority_fields():
    u=text_unit('Propofol may cause hypotension.')
    a=text_assertion(u,'Propofol can lower blood pressure.')
    cfg=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=CODE,mode='MODEL_ASSISTED',model='m',model_revision='r',prompt_sha256='d'*64)
    v=verify_assertion(a,u,config=cfg,semantic_provider=lambda p:{'verdict':'ENTAILED','failed_dimensions':[],'canonical_authority':True})
    assert v['verdict']=='AMBIGUOUS' and v['review_state']=='REVIEWER_FAILED'
    assert v['canonical_authority'] is False

def test_verification_id_is_deterministic_and_verifier_versioned():
    u=text_unit('Propofol may cause hypotension.')
    a=text_assertion(u,'Propofol may cause hypotension.')
    v1=verify_assertion(a,u,config=CFG); v2=verify_assertion(a,u,config=CFG)
    assert v1['verification_id']==v2['verification_id']
    cfg2=VerifierConfig(engine='blind-verifier',engine_version='2',code_manifest_sha256=CODE)
    assert verify_assertion(a,u,config=cfg2)['verification_id']!=v1['verification_id']

def test_batch_verifier_quarantines_missing_source_units():
    u=text_unit('Propofol may cause hypotension.')
    a=text_assertion(u,'Propofol may cause hypotension.')
    r=verify_assertions([a],[],config=CFG)
    assert r['status']=='PASS_WITH_QUARANTINE' and r['metrics']['quarantined']==1

def test_unknown_structured_path_is_not_auto_entailed():
    u=structured_unit('blue',path='$.arbitrary.color')
    a=build_assertion(source_unit=u,assertion_type='TRIAL_PROTOCOL_FACT',normalized_proposition='The sky was blue.',structured_evidence_path=u['locator']['json_path'],extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':CODE})
    assert verify_assertion(a,u,config=CFG)['verdict']=='AMBIGUOUS'

def test_controlled_structured_path_rejects_wrong_semantics():
    u=structured_unit(120)
    a=build_assertion(source_unit=u,assertion_type='TRIAL_PROTOCOL_FACT',normalized_proposition='The study dose was 120 mg.',structured_evidence_path=u['locator']['json_path'],extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'x','engine_version':'1','code_manifest_sha256':CODE})
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='NOT_ENTAILED'
    assert any(c['check_code']=='STRUCTURED_SEMANTIC_BINDING' and c['state']=='FAIL' for c in v['checks'])

def test_hedged_source_cannot_be_strengthened():
    u=text_unit('The drug may reduce nausea.')
    a=text_assertion(u,'The drug reduces nausea.')
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='NOT_ENTAILED'
    assert any(c['check_code']=='CERTAINTY_MODALITY' and c['state']=='FAIL' for c in v['checks'])

def test_source_condition_cannot_be_dropped():
    u=text_unit('In patients with renal failure, reduce the dose.')
    a=text_assertion(u,'Reduce the dose.',at='DOSING')
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='NOT_ENTAILED'
    assert any(c['check_code']=='CONDITIONALITY' and c['state']=='FAIL' for c in v['checks'])

def test_numeric_prefix_does_not_allow_4_to_match_40():
    u=text_unit('Ondansetron 40 mg IV was administered.')
    a=text_assertion(u,'Ondansetron 4 mg IV was administered.',at='DOSING',numeric={'value':4,'unit':'mg'},context={'route':'IV'})
    assert verify_assertion(a,u,config=CFG)['verdict']=='NOT_ENTAILED'

def test_microgram_unit_aliases_are_equivalent_for_binding():
    u=text_unit('Fentanyl 50 µg IV was administered.')
    a=text_assertion(u,'Fentanyl 50 µg IV was administered.',at='DOSING',numeric={'value':50,'unit':'mcg'},context={'route':'IV'})
    v=verify_assertion(a,u,config=CFG)
    assert v['verdict']=='ENTAILED'
    assert any(c['check_code']=='NUMERIC_BINDING' and c['state']=='PASS' for c in v['checks'])

def test_provider_failed_dimensions_downgrade_entailed_to_partial():
    u=text_unit('Propofol may cause hypotension.')
    a=text_assertion(u,'Propofol can lower blood pressure.')
    cfg=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=CODE,mode='MODEL_ASSISTED',model='m',model_revision='r',prompt_sha256='d'*64)
    v=verify_assertion(a,u,config=cfg,semantic_provider=lambda p:{'verdict':'ENTAILED','failed_dimensions':['QUALIFIER']})
    assert v['verdict']=='PARTIAL'
