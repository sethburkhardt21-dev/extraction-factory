import copy,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit,build_assertion,sha256_hex
from bridge_09d.assertion_verifier import (
    VerifierConfig,build_blind_verifier_request,validate_reviewer_response,verify_assertion,verify_assertions
)
from bridge_09d.semantic_capsules import run_specialist_capsules

CODE='c'*64

def vcfg(rev='1',mode='MODEL_ASSISTED'):
    if mode=='DETERMINISTIC_REVIEW': return VerifierConfig(engine='frontier-verifier',engine_version='1',code_manifest_sha256=CODE,mode=mode)
    return VerifierConfig(engine='frontier-verifier',engine_version='1',code_manifest_sha256=CODE,mode=mode,model='reviewer-x',model_revision=rev,prompt_sha256='d'*64)

def reviewer(verdict='ENTAILED',confidence='HIGH',resolved=None,**extra):
    def _r(_req):
        return {'reviewer_response_schema_version':'frontier-blind-reviewer-response-1.0','verdict':verdict,'rationale':'Independent source-only review.','confidence':confidence,'resolved_warning_codes':list(resolved or []),**extra}
    return _r

def text_unit(text='Propofol 0.5 mg/kg IV was administered to adults before induction.',scope='FULL_TEXT',kind='TEXT'):
    return build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,
        source_scope=scope,unit_kind=kind,locator={'locator_type':'PARAGRAPH','section':'Methods','paragraph':1},content_text=text)

def assertion(u,prop='Propofol was administered at 0.5 mg/kg IV.',atype='DOSING',evidence='Propofol 0.5 mg/kg IV',numeric=None,context=None,negated=False):
    text=u['content_text']; start=text.index(evidence)
    span={'char_start':start,'char_end':start+len(evidence),'utf8_byte_start':len(text[:start].encode()),'utf8_byte_end':len(text[:start+len(evidence)].encode()),'text':evidence,'text_sha256':sha256_hex(evidence.encode())}
    return build_assertion(source_unit=u,assertion_type=atype,normalized_proposition=prop,evidence_span=span,numeric=numeric,
        context=context or {},negated=negated,extractor_provenance={'mode':'MODEL_ASSISTED','engine':'extractor-secret','engine_version':'9','code_manifest_sha256':'b'*64,'model':'extractor-model','model_revision':'secret','prompt_sha256':'e'*64})

def json_unit(path,value):
    return build_source_unit(source_record_key='ctg:NCT1',source_resource_id='NCT:NCT1',source_version_id='2026',source_sha256='f'*64,
        source_scope='REGISTRY_STRUCTURED',unit_kind='JSON_FIELD',locator={'locator_type':'JSON_PATH','json_path':path},content_json=value)

def json_assertion(u,atype,prop,numeric=None):
    return build_assertion(source_unit=u,assertion_type=atype,normalized_proposition=prop,structured_evidence_path=u['locator']['json_path'],numeric=numeric,
        extractor_provenance={'mode':'DETERMINISTIC_PARSER','engine':'ctg-extractor','engine_version':'1','code_manifest_sha256':'b'*64})


def test_blind_request_hides_extractor_identity_and_candidate_fields():
    u=text_unit(); a=assertion(u,numeric={'value':0.5,'unit':'mg/kg'},context={'route':'IV'})
    req=build_blind_verifier_request(a,u,run_specialist_capsules(a,u))
    blob=json.dumps(req,sort_keys=True)
    assert 'extractor-secret' not in blob and 'extractor-model' not in blob and 'interpretation_id' not in blob
    assert 'subject_candidate_id' not in blob and req['review_task']['blind_to_extractor'] is True


def test_reviewer_cannot_set_authority_or_09d_decision_even_nested():
    bad={'verdict':'ENTAILED','rationale':'x','confidence':'HIGH','qualifier_assessment':{'09d_decision':'PROMOTE'}}
    errs=validate_reviewer_response(bad)
    assert any('authority/identity leakage' in e for e in errs)


def test_structured_enrollment_is_independently_rederived_as_entailed_without_model():
    u=json_unit('$.protocolSection.designModule.enrollmentInfo.count',10)
    a=json_assertion(u,'STUDY_ENROLLMENT','The study enrollment was 10 participants.',{'value':10,'unit':'participants'})
    ev=verify_assertion(a,u,config=vcfg(mode='DETERMINISTIC_REVIEW'))
    assert ev['verdict']=='ENTAILED' and ev['decision_basis']=='DETERMINISTIC_REDERIVATION'
    assert ev['reviewer_response'] is None and ev['09d_mutation_performed'] is False


def test_structured_rule_mismatch_is_not_entailed():
    u=json_unit('$.protocolSection.designModule.enrollmentInfo.count',10)
    a=json_assertion(u,'STUDY_ENROLLMENT','The study enrollment was 11 participants.',{'value':10,'unit':'participants'})
    ev=verify_assertion(a,u,config=vcfg(mode='DETERMINISTIC_REVIEW'))
    assert ev['verdict']=='NOT_ENTAILED' and 'MISMATCH' in ev['decision_basis']


def test_free_text_without_independent_reviewer_never_self_entails():
    u=text_unit('The medication was stored at room temperature.')
    a=assertion(u,prop='The medication was stored at room temperature.',atype='OTHER_CLINICAL_ASSERTION',evidence='stored at room temperature')
    ev=verify_assertion(a,u,config=vcfg(mode='DETERMINISTIC_REVIEW'))
    assert ev['verdict']=='AMBIGUOUS' and ev['downstream_semantic_ready'] is False


def test_low_risk_blind_reviewer_can_mark_semantically_ready_but_grants_no_authority():
    u=text_unit('Apnea is defined as cessation of breathing.')
    a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is defined as cessation of breathing')
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='ENTAILED' and ev['downstream_semantic_ready'] is True
    assert ev['canonical_authority'] is False and ev['generation_eligible'] is False


def test_critical_dose_remains_frontier_adjudication_required_even_if_blind_reviewer_agrees():
    u=text_unit(); a=assertion(u,numeric={'value':0.5,'unit':'mg/kg'},context={'route':'IV'})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='ENTAILED'
    assert ev['specialist_capsules']['risk_route']['risk_level']=='CRITICAL'
    assert ev['review_state']=='FRONTIER_ADJUDICATION_REQUIRED' and ev['downstream_semantic_ready'] is False


def test_numeric_value_mismatch_overrides_optimistic_reviewer():
    u=text_unit(); a=assertion(u,prop='Propofol was administered at 5 mg/kg IV.',numeric={'value':5,'unit':'mg/kg'},context={'route':'IV'})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='NOT_ENTAILED'
    assert 'NUMERIC_BINDING' in ev.get('blocking_codes',[])


def test_numeric_unit_mismatch_overrides_reviewer():
    u=text_unit(); a=assertion(u,numeric={'value':0.5,'unit':'mcg/kg'},context={'route':'IV'})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='NOT_ENTAILED'


def test_negation_reversal_is_hard_failure():
    u=text_unit('The treatment did not reduce mortality.')
    a=assertion(u,prop='The treatment reduced mortality.',atype='MORTALITY',evidence='did not reduce mortality')
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='NOT_ENTAILED'
    assert 'QUALIFIER_SCOPE' in ev.get('blocking_codes',[])


def test_causal_overclaim_from_association_is_not_entailed_for_causation_type():
    u=text_unit('Hypotension was associated with mortality.')
    a=assertion(u,prop='Hypotension causes mortality.',atype='CAUSATION',evidence='associated with mortality')
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='NOT_ENTAILED' and 'RELATIONSHIP_SEMANTICS' in ev.get('blocking_codes',[])


def test_directionality_reversal_is_not_entailed():
    u=text_unit('Heart rate increased after treatment.')
    a=assertion(u,prop='Heart rate decreased after treatment.',atype='TREATMENT_EFFECT',evidence='Heart rate increased')
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='NOT_ENTAILED'


def test_unresolved_qualifier_warning_downgrades_reviewer_entailed_to_partial():
    u=text_unit('The dose was 5 mg.')
    a=assertion(u,prop='Adults received a dose of 5 mg.',atype='DOSING',evidence='dose was 5 mg',numeric={'value':5,'unit':'mg'},context={'population':'adults'})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict'] in {'PARTIAL','NOT_ENTAILED'}


def test_reviewer_can_resolve_noncontradictory_warning_but_not_hard_failure():
    u=text_unit('The finding was reported in the study population.')
    a=assertion(u,prop='The finding was reported in adults.',atype='OTHER_CLINICAL_ASSERTION',evidence='finding was reported',context={'population':'adults'})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer(resolved=['QUALIFIER_SCOPE']))
    assert ev['verdict']=='ENTAILED'
    # Hard numeric failure cannot be waived with resolved_warning_codes.
    u2=text_unit(); a2=assertion(u2,prop='Propofol 5 mg/kg IV was given.',numeric={'value':5,'unit':'mg/kg'},context={'route':'IV'})
    ev2=verify_assertion(a2,u2,config=vcfg(),reviewer=reviewer(resolved=['NUMERIC_BINDING']))
    assert ev2['verdict']=='NOT_ENTAILED'


def test_reviewer_failure_is_ambiguous_not_pass():
    u=text_unit('Apnea is cessation of breathing.'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing')
    def broken(_): raise RuntimeError('offline')
    ev=verify_assertion(a,u,config=vcfg(),reviewer=broken)
    assert ev['verdict']=='AMBIGUOUS' and ev['review_state']=='REVIEWER_FAILED'


def test_invalid_reviewer_response_fails_closed():
    u=text_unit('Apnea is cessation of breathing.'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing')
    ev=verify_assertion(a,u,config=vcfg(),reviewer=lambda req:{'verdict':'ENTAILED','confidence':'HIGH','rationale':'x','public_eligible':True})
    assert ev['verdict']=='AMBIGUOUS' and ev['reviewer_error']


def test_verification_event_is_deterministic_for_same_reviewer_and_config():
    u=text_unit('Apnea is cessation of breathing.'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing')
    e1=verify_assertion(a,u,config=vcfg('1'),reviewer=reviewer()); e2=verify_assertion(a,u,config=vcfg('1'),reviewer=reviewer())
    assert e1['verification_event_id']==e2['verification_event_id']


def test_verifier_revision_changes_review_event_not_assertion():
    u=text_unit('Apnea is cessation of breathing.'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing')
    original=copy.deepcopy(a)
    e1=verify_assertion(a,u,config=vcfg('1'),reviewer=reviewer()); e2=verify_assertion(a,u,config=vcfg('2'),reviewer=reviewer())
    assert e1['verification_event_id']!=e2['verification_event_id'] and a==original


def test_tampered_source_binding_becomes_provenance_incomplete():
    u=text_unit('Apnea is cessation of breathing.'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing')
    bad=dict(a); bad['source_sha256']='9'*64
    ev=verify_assertion(bad,u,config=vcfg(),reviewer=reviewer())
    assert ev['verdict']=='PROVENANCE_INCOMPLETE' and ev['review_state']=='BLOCKED_PROVENANCE'


def test_abstract_scope_raises_at_least_moderate_risk():
    u=text_unit('Apnea is cessation of breathing.',scope='ABSTRACT_ONLY'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing')
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['specialist_capsules']['risk_route']['risk_level'] in {'MODERATE','HIGH','CRITICAL'}


def test_table_scope_routes_to_high_risk_context_review():
    u=build_source_unit(source_record_key='p:1',source_resource_id='PMID:2',source_version_id='1',source_sha256='a'*64,source_scope='TABLE',unit_kind='TABLE_CELL',locator={'locator_type':'TABLE_CELL','row_index':1,'col_index':2},content_text='5 mg')
    a=assertion(u,prop='The dose was 5 mg.',atype='DOSING',evidence='5 mg',numeric={'value':5,'unit':'mg'})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    assert ev['specialist_capsules']['risk_route']['risk_level'] in {'HIGH','CRITICAL'}


def test_specialist_capsules_have_independent_numeric_qualifier_relationship_and_provenance_results():
    u=text_unit(); a=assertion(u,numeric={'value':0.5,'unit':'mg/kg'},context={'route':'IV'})
    r=run_specialist_capsules(a,u)
    codes={x['code'] for x in r['findings']}
    assert {'PROVENANCE_CLOSURE','NUMERIC_BINDING','QUALIFIER_SCOPE','RELATIONSHIP_SEMANTICS','ATOMICITY'} <= codes


def test_batch_verifier_never_mutates_assertions_and_keeps_quarantine_explicit():
    u=text_unit('Apnea is cessation of breathing.'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing'); before=copy.deepcopy(a)
    r=verify_assertions([a],[u],config=vcfg(),reviewer=reviewer())
    assert r['status']=='PASS' and r['events'] and a==before
    r2=verify_assertions([a],[],config=vcfg(),reviewer=reviewer())
    assert r2['status']=='PASS_WITH_QUARANTINE' and not r2['events']


def test_verification_pipeline_is_code_hash_bound_and_persists_append_only_events(tmp_path):
    from bridge_09d.verification_pipeline import run_verification_pipeline
    from frontier_core.readiness import code_manifest
    u=text_unit('Apnea is cessation of breathing.'); a=assertion(u,prop='Apnea is cessation of breathing.',atype='DEFINITION',evidence='Apnea is cessation of breathing')
    ap=tmp_path/'assertions.jsonl'; up=tmp_path/'units.jsonl'; ap.write_text(json.dumps(a)+'\n'); up.write_text(json.dumps(u)+'\n')
    current=code_manifest(ROOT)['sha256']
    cfg=VerifierConfig(engine='frontier-verifier',engine_version='1',code_manifest_sha256=current,mode='MODEL_ASSISTED',model='r',model_revision='1',prompt_sha256='d'*64)
    result=run_verification_pipeline(assertions_path=ap,source_units_path=up,output_dir=tmp_path/'out',config=cfg,reviewer=reviewer())
    m=json.loads((tmp_path/'out/manifest.json').read_text())
    assert m['blind_independent_review'] is True and m['canonical_authority'] is False
    assert json.loads((tmp_path/'out/verification_events.jsonl').read_text().splitlines()[0])['verdict']=='ENTAILED'
    bad=VerifierConfig(engine='x',engine_version='1',code_manifest_sha256='0'*64,mode='DETERMINISTIC_REVIEW')
    with pytest.raises(RuntimeError,match='code hash does not match'):
        run_verification_pipeline(assertions_path=ap,source_units_path=up,output_dir=tmp_path/'bad',config=bad)

def test_numeric_specialist_equates_scientific_notation_and_vulgar_fraction_without_corrupting_identity():
    u=text_unit('Concentration was 10⁻⁶ M and one-half dose was ½ mg.')
    a=assertion(u,prop='The concentration was 1e-6 M.',atype='CONCENTRATION',evidence='10⁻⁶ M',numeric={'value':1e-6,'unit':'M'})
    r=run_specialist_capsules(a,u); n=next(x for x in r['findings'] if x['code']=='NUMERIC_BINDING')
    assert n['state']=='PASS'
    a2=assertion(u,prop='The dose was 0.5 mg.',atype='DOSING',evidence='½ mg',numeric={'value':0.5,'unit':'mg'})
    n2=next(x for x in run_specialist_capsules(a2,u)['findings'] if x['code']=='NUMERIC_BINDING')
    assert n2['state']=='PASS'


def test_numeric_specialist_normalizes_microgram_and_denominator_exponent_units_for_comparison_only():
    u=text_unit('Infusion rate was 5 µg kg^-1 min^-1.')
    a=assertion(u,prop='The infusion rate was 5 mcg/kg/min.',atype='DOSING',evidence='5 µg kg^-1 min^-1',numeric={'value':5,'unit':'mcg/kg/min'})
    n=next(x for x in run_specialist_capsules(a,u)['findings'] if x['code']=='NUMERIC_BINDING')
    assert n['state']=='PASS'

def test_high_risk_numeric_claim_cannot_evade_numeric_binding_by_omitting_numeric_object():
    u=text_unit(); a=assertion(u,prop='Propofol was administered at 0.5 mg/kg IV.',numeric=None,context={'route':'IV'})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer(resolved=['NUMERIC_BINDING']))
    assert ev['verdict']=='NOT_ENTAILED' and 'NUMERIC_BINDING' in ev.get('blocking_codes',[])


def test_route_in_high_risk_proposition_must_be_structurally_bound():
    u=text_unit(); a=assertion(u,prop='Propofol was administered at 0.5 mg/kg IV.',numeric={'value':0.5,'unit':'mg/kg'},context={})
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer(resolved=['QUALIFIER_SCOPE']))
    assert ev['verdict']=='NOT_ENTAILED' and 'QUALIFIER_SCOPE' in ev.get('blocking_codes',[])

def test_table_numeric_without_headers_routes_table_binding_warning_and_precision_review():
    u=build_source_unit(source_record_key='t:1',source_resource_id='T:1',source_version_id='1',source_sha256='a'*64,source_scope='TABLE',unit_kind='TABLE_CELL',locator={'locator_type':'TABLE_CELL','jats_xpath':'/article/table/tr/td','row_index':1,'col_index':1,'header_refs':[],'colspan':1,'rowspan':1},content_text='140 mg')
    a=build_assertion(source_unit=u,assertion_type='CLINICAL_VALUE',normalized_proposition='The value was 140 mg.',evidence_span={'char_start':0,'char_end':6,'utf8_byte_start':0,'utf8_byte_end':6,'text':'140 mg','text_sha256':sha256_hex(b'140 mg')},numeric={'value':140,'unit':'mg'},extractor_provenance={'mode':'MODEL_ASSISTED','engine':'x','engine_version':'1','code_manifest_sha256':'b'*64,'model':'m','model_revision':'1','prompt_sha256':'c'*64})
    ev=verify_assertion(a,u,config=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256='d'*64,mode='MODEL_ASSISTED',model='r',model_revision='1',prompt_sha256='e'*64),reviewer=lambda req:{'verdict':'ENTAILED','rationale':'Cell text matches.','confidence':'HIGH','resolved_warning_codes':[]})
    finding={x['code']:x for x in ev['specialist_capsules']['findings']}['TABLE_BINDING']
    assert finding['state']=='WARN'
    assert 'TABLE_BINDING' in ev['required_review_lanes'] and 'PRECISION_REVIEW' in ev['required_review_lanes']
    assert ev['downstream_semantic_ready'] is False


def test_table_claimed_header_must_match_retained_header_context():
    u=build_source_unit(source_record_key='t:1',source_resource_id='T:1',source_version_id='1',source_sha256='a'*64,source_scope='TABLE',unit_kind='TABLE_CELL',locator={'locator_type':'TABLE_CELL','jats_xpath':'/article/table/tr/td','row_index':1,'col_index':1,'header_refs':['Dose'],'colspan':1,'rowspan':1},content_text='140 mg')
    a=build_assertion(source_unit=u,assertion_type='CLINICAL_VALUE',normalized_proposition='The mortality value was 140 mg.',evidence_span={'char_start':0,'char_end':6,'utf8_byte_start':0,'utf8_byte_end':6,'text':'140 mg','text_sha256':sha256_hex(b'140 mg')},numeric={'value':140,'unit':'mg'},context={'column_header':'Mortality'},extractor_provenance={'mode':'MODEL_ASSISTED','engine':'x','engine_version':'1','code_manifest_sha256':'b'*64,'model':'m','model_revision':'1','prompt_sha256':'c'*64})
    ev=verify_assertion(a,u,config=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256='d'*64,mode='DETERMINISTIC_REVIEW'))
    finding={x['code']:x for x in ev['specialist_capsules']['findings']}['TABLE_BINDING']
    assert finding['state']=='FAIL' and ev['verdict']=='NOT_ENTAILED'

def test_figure_caption_only_requires_visual_binding_and_cannot_be_semantically_ready_without_visual_review():
    u=build_source_unit(source_record_key='fig:1',source_resource_id='FIG:1',source_version_id='1',source_sha256='a'*64,source_scope='FIGURE',unit_kind='FIGURE_CAPTION',locator={'locator_type':'FIGURE','jats_xpath':'/article/body/fig[1]/caption[1]'},content_text='Kaplan-Meier survival curve by treatment group.')
    a=build_assertion(source_unit=u,assertion_type='OUTCOME',normalized_proposition='The figure shows a Kaplan-Meier survival curve by treatment group.',evidence_span={'char_start':0,'char_end':47,'utf8_byte_start':0,'utf8_byte_end':47,'text':'Kaplan-Meier survival curve by treatment group.','text_sha256':sha256_hex(b'Kaplan-Meier survival curve by treatment group.')},context={'visual_semantics_required':True},extractor_provenance={'mode':'MODEL_ASSISTED','engine':'x','engine_version':'1','code_manifest_sha256':'b'*64,'model':'m','model_revision':'1','prompt_sha256':'c'*64})
    ev=verify_assertion(a,u,config=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256='d'*64,mode='MODEL_ASSISTED',model='r',model_revision='1',prompt_sha256='e'*64),reviewer=lambda req:{'verdict':'ENTAILED','rationale':'Caption text matches.','confidence':'HIGH','resolved_warning_codes':[]})
    finding={x['code']:x for x in ev['specialist_capsules']['findings']}['VISUAL_BINDING']
    assert finding['state']=='WARN'
    assert 'VISUAL_BINDING' in ev['required_review_lanes']
    assert ev['verdict']=='PARTIAL' and ev['downstream_semantic_ready'] is False


def test_nonfigure_source_does_not_route_visual_binding():
    u=text_unit(); a=assertion(u)
    ev=verify_assertion(a,u,config=vcfg(),reviewer=reviewer())
    finding={x['code']:x for x in ev['specialist_capsules']['findings']}['VISUAL_BINDING']
    assert finding['state']=='NOT_APPLICABLE'
    assert 'VISUAL_BINDING' not in ev['required_review_lanes']
