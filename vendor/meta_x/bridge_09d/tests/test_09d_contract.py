import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from bridge_09d.package import candidate_id, source_identity_sha256, validate_candidate, build_audit_package


def test_candidate_identity_matches_09d_separator_contract():
    table='frontier.drug_source_record'; key='drugbank:DB00001'
    sha=source_identity_sha256(table,key)
    assert candidate_id(table,key)=='CAND:'+sha[:32]
    assert len(sha)==64


def test_candidate_authority_fails_closed():
    table='frontier.drug_source_record'; key='drugbank:DB1'; sha=source_identity_sha256(table,key)
    good={'candidate_id':'CAND:'+sha[:32],'source_table':table,'source_key':key,'source_identity_sha256':sha,'state':'REGISTERED','legacy_entity_id':None,
          'automatic_identity_merge_allowed':False,'automatic_selection_allowed':False,'canonical_internal_eligible':False,'generation_eligible':False,'public_eligible':False}
    assert validate_candidate(good)==[]
    bad=dict(good); bad['generation_eligible']=True
    assert any('generation_eligible' in x for x in validate_candidate(bad))


def test_external_audit_package_is_non_insertable_and_incomplete_by_design(tmp_path):
    wh=tmp_path/'wh'; wh.mkdir()
    (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    for name in ('source_record','source_observation','run_artifact'):
        (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    out=tmp_path/'audit'; m=build_audit_package(wh,out,authority_reference=auth)
    assert m['direct_09d_insert_allowed'] is False
    assert m['current_09d_s02_direct_insert_compatible'] is False
    assert m['canonical_authority'] is False and m['public_eligible'] is False
    assert m['assertion_contract_status']=='FROZEN'
    assert m['source_unit_contract_status']=='FROZEN'
    assert m['assertion_engine_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_UNVERIFIED_OUTPUT'
    assert m['assertion_verifier_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_APPEND_ONLY'
    assert m['verification_overlay_policy']=='APPEND_ONLY_VERIF_EVENTS'
    assert m['blind_recall_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_CONTRACT_MODEL_PENDING'
    assert m['semantic_review_router_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE'
    assert m['semantic_factory_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE'
    assert m['source_unit_segmenter_status']=='IMPLEMENTED_OFFLINE_CERTIFIED'
    assert m['fulltext_acquisition_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_PUBLIC_CANARY_PENDING'
    assert m['rights_dimensions_separate'] is True
    assert m['frontier_ready'] is False
    assert (out/'source_units/source_units.jsonl').read_text()==''
    assert (out/'assertions/assertions.jsonl').read_text()==''


def test_turn3_package_carries_fulltext_rights_and_segmented_units(tmp_path):
    from bridge_09d.source_units import persist_fulltext_artifact, rights_decision, segment_artifact_jats
    wh=tmp_path/'wh'; wh.mkdir()
    (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'pubmed:1'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    xml=b'<article><body><sec><title>Results</title><p>Outcome improved.</p></sec></body></article>'
    rights=rights_decision(source='pmc',pmc_oai_fulltext_returned=True)
    art=persist_fulltext_artifact(payload=xml,output_path=tmp_path/'article.xml',source='pmc',source_resource_id='PMCID:1',source_version_id='1',source_url='https://pmc.ncbi.nlm.nih.gov/x',content_type='application/xml',rights=rights)
    units=segment_artifact_jats(artifact=art,source_record_key='pubmed:1')
    out=tmp_path/'audit'; m=build_audit_package(wh,out,authority_reference=auth,source_units=units,fulltext_artifacts=[art],rights_decisions=[rights])
    assert m['source_unit_segmenter_status']=='IMPLEMENTED_OFFLINE_CERTIFIED'
    assert m['fulltext_acquisition_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_PUBLIC_CANARY_PENDING'
    assert m['provenance_metrics']['fulltext_artifacts']==1
    assert m['provenance_metrics']['source_scope_counts']['FULL_TEXT']>=1
    assert json.loads((out/'validation/turn3_segmentation_validation.json').read_text())['status']=='PASS_TURN3_SEGMENTATION'


def test_package_rejects_source_unit_not_anchored_to_ingested_source(tmp_path):
    from bridge_09d.assertions import build_source_unit
    wh=tmp_path/'wh'; wh.mkdir(); (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'real:key'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    unit=build_source_unit(source_record_key='wrong:key',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='ABSTRACT_ONLY',unit_kind='ABSTRACT_SECTION',locator={'locator_type':'TEXT_SECTION','section':'Abstract'},content_text='x')
    with pytest.raises(ValueError,match='absent from package source_record'):
        build_audit_package(wh,tmp_path/'audit',authority_reference=auth,source_units=[unit])


def test_turn4_package_accepts_engine_result_but_keeps_every_assertion_unverified(tmp_path):
    from bridge_09d.assertions import build_source_unit
    from bridge_09d.assertion_engine import EngineConfig, extract_assertions
    wh=tmp_path/'wh'; wh.mkdir()
    (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'pubmed:1'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    unit=build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='ABSTRACT_ONLY',unit_kind='ABSTRACT_SECTION',locator={'locator_type':'TEXT_SECTION','section':'Abstract'},content_text='Propofol caused hypotension.')
    from frontier_core.readiness import code_manifest
    cfg=EngineConfig(engine='x',engine_version='1',code_manifest_sha256=code_manifest(ROOT)['sha256'],mode='MODEL_ASSISTED',model='m',model_revision='1',prompt_sha256='b'*64)
    result=extract_assertions([unit],provider=lambda u:[{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused hypotension.','evidence_text':'Propofol caused hypotension.'}],config=cfg)
    out=tmp_path/'audit'; m=build_audit_package(wh,out,authority_reference=auth,source_units=[unit],assertion_engine_result=result)
    assert m['assertion_engine_run_status']=='PASS'
    assert m['counts']['assertions']==1 and m['counts']['assertion_quarantine']==0
    assert m['provenance_metrics']['assertion_not_verified']==1
    row=json.loads((out/'assertions/assertions.jsonl').read_text().splitlines()[0])
    assert row['verification_status']=='NOT_VERIFIED' and row['canonical_authority'] is False
    assert json.loads((out/'validation/turn5_semantic_verifier_validation.json').read_text())['status']=='PASS_TURN5_SEMANTIC_VERIFIER'


def test_turn4_package_rejects_preverified_assertion(tmp_path):
    from bridge_09d.assertions import build_source_unit
    from bridge_09d.assertion_engine import EngineConfig, extract_assertions
    wh=tmp_path/'wh'; wh.mkdir(); (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n'); (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'pubmed:1'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    unit=build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='ABSTRACT_ONLY',unit_kind='ABSTRACT_SECTION',locator={'locator_type':'TEXT_SECTION','section':'Abstract'},content_text='X improved Y.')
    from frontier_core.readiness import code_manifest
    cfg=EngineConfig(engine='x',engine_version='1',code_manifest_sha256=code_manifest(ROOT)['sha256'],mode='MODEL_ASSISTED',model='m',model_revision='1',prompt_sha256='b'*64)
    result=extract_assertions([unit],provider=lambda u:[{'assertion_type':'EFFICACY','normalized_proposition':'X improved Y.','evidence_text':'X improved Y.'}],config=cfg)
    result['assertions'][0]['verification_status']='ENTAILED'
    with pytest.raises(ValueError,match='NOT_VERIFIED'):
        build_audit_package(wh,tmp_path/'audit',authority_reference=auth,source_units=[unit],assertion_engine_result=result)

def test_turn5_package_carries_append_only_verification_without_mutating_assertion(tmp_path):
    from bridge_09d.assertions import build_source_unit
    from bridge_09d.assertion_engine import EngineConfig, extract_assertions
    from bridge_09d.verifier import deterministic_verifier_config, verify_assertions
    from frontier_core.readiness import code_manifest
    wh=tmp_path/'wh'; wh.mkdir()
    (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'pubmed:1'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    unit=build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','xpath':'/article/body/sec/p'},content_text='Propofol may cause hypotension.')
    sha=code_manifest(ROOT)['sha256']
    result=extract_assertions([unit],provider=lambda u:[{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol may cause hypotension.','evidence_text':'Propofol may cause hypotension.'}],config=EngineConfig(engine='x',engine_version='1',code_manifest_sha256=sha,mode='DETERMINISTIC_PARSER'))
    verified=verify_assertions(result['assertions'],[unit],config=deterministic_verifier_config(code_manifest_sha256=sha))
    out=tmp_path/'audit'; m=build_audit_package(wh,out,authority_reference=auth,source_units=[unit],assertion_engine_result=result,verification_result=verified)
    assert m['counts']['assertions']==1 and m['counts']['verification_events']==1
    a=json.loads((out/'assertions/assertions.jsonl').read_text().splitlines()[0])
    v=json.loads((out/'verification/verification_events.jsonl').read_text().splitlines()[0])
    assert a['verification_status']=='NOT_VERIFIED'
    assert v['verdict']=='ENTAILED' and v['blind_independent_review'] is True
    assert v['canonical_authority'] is False and m['canonical_authority'] is False

def test_turn5_package_carries_blind_recall_and_semantic_review_queue(tmp_path):
    from bridge_09d.assertions import build_source_unit
    from bridge_09d.assertion_engine import EngineConfig, extract_assertions
    from bridge_09d.blind_recall import run_blind_recall, reconcile_primary_recall
    from bridge_09d.semantic_router import route_semantic_review
    from bridge_09d.verifier import deterministic_verifier_config, verify_assertions
    from frontier_core.readiness import code_manifest
    wh=tmp_path/'wh'; wh.mkdir()
    (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'pubmed:1'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    unit=build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text='Propofol caused apnea and reduced blood pressure.')
    sha=code_manifest(ROOT)['sha256']
    cfg=EngineConfig(engine='primary',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='p',model_revision='1',prompt_sha256='b'*64)
    primary=extract_assertions([unit],provider=lambda u:[{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'}],config=cfg)
    recall_cfg=EngineConfig(engine='recall',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='r',model_revision='1',prompt_sha256='c'*64)
    recall=run_blind_recall([unit],provider=lambda packet:[
        {'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'},
        {'assertion_type':'TREATMENT_EFFECT','normalized_proposition':'Propofol reduced blood pressure.','evidence_text':'reduced blood pressure'}
    ],config=recall_cfg)
    recall={**recall,'reconciliation':reconcile_primary_recall(primary['assertions'],recall['assertions'])}
    verified=verify_assertions(primary['assertions'],[unit],config=deterministic_verifier_config(code_manifest_sha256=sha))
    routed=route_semantic_review(verification_events=verified['verification_events'],recall_reconciliation=recall['reconciliation'])
    out=tmp_path/'audit'; m=build_audit_package(wh,out,authority_reference=auth,source_units=[unit],assertion_engine_result=primary,verification_result=verified,blind_recall_result=recall,semantic_routing_result=routed)
    assert m['blind_recall_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_CONTRACT_MODEL_PENDING'
    assert m['semantic_review_router_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE'
    assert m['semantic_factory_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE'
    assert m['counts']['recall_assertions']==2
    assert m['counts']['recall_reconciliation']>=2
    assert m['counts']['semantic_review_cases']>=1
    rr=[json.loads(x) for x in (out/'semantic_review/recall_reconciliation.jsonl').read_text().splitlines()]
    assert any(x['reconciliation_state']=='RECALL_ONLY_CANDIDATE' for x in rr)
    cases=[json.loads(x) for x in (out/'semantic_review/review_cases.jsonl').read_text().splitlines()]
    assert any(x['reason']=='RECALL_ONLY_CANDIDATE' for x in cases)
    assert all(x['automatic_action_allowed'] is False and x['canonical_authority'] is False for x in cases)
    assert m['canonical_authority'] is False and m['mass_extraction_authorized'] is False

def test_package_accepts_semantic_factory_as_single_semantic_control_plane_input(tmp_path):
    from bridge_09d.assertions import build_source_unit
    from bridge_09d.assertion_engine import EngineConfig,extract_assertions
    from bridge_09d.semantic_factory import run_semantic_factory
    from bridge_09d.verifier import VerifierConfig
    from frontier_core.readiness import code_manifest
    wh=tmp_path/'wh'; wh.mkdir()
    (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'pubmed:1'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    unit=build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text='Propofol caused apnea.')
    sha=code_manifest(ROOT)['sha256']
    ecfg=EngineConfig(engine='p',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='p',model_revision='1',prompt_sha256='b'*64)
    primary=extract_assertions([unit],provider=lambda u:[{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea'}],config=ecfg)
    vcfg=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='v',model_revision='1',prompt_sha256='c'*64)
    factory=run_semantic_factory(primary_assertions=primary['assertions'],source_units=[unit],verifier_config=vcfg,reviewer=lambda req:{'verdict':'ENTAILED','rationale':'Exact source entailment.','confidence':'HIGH','resolved_warning_codes':[]})
    out=tmp_path/'audit'; m=build_audit_package(wh,out,authority_reference=auth,source_units=[unit],assertion_engine_result=primary,semantic_factory_result=factory)
    assert m['semantic_factory_run_status']=='PASS'
    assert m['semantic_factory_run_id']==factory['semantic_run_id']
    assert m['counts']['verification_events']==1
    assert m['canonical_authority'] is False and m['mass_extraction_authorized'] is False

def test_turn6_package_carries_candidates_and_readonly_comparisons_without_assigning_09d_identity(tmp_path):
    import hashlib
    from bridge_09d.assertions import build_source_unit
    from bridge_09d.assertion_engine import EngineConfig,extract_assertions
    from bridge_09d.comparator_09d import SNAPSHOT_SCHEMA_VERSION
    from bridge_09d.semantic_factory import run_semantic_factory
    from bridge_09d.turn6_factory import run_turn6_audit_prep
    from bridge_09d.verifier import VerifierConfig
    from frontier_core.readiness import code_manifest
    wh=tmp_path/'wh'; wh.mkdir()
    (wh/'warehouse_projection_manifest.json').write_text(json.dumps({'validation_status':'PASS','source_manifest_sha256':'a'*64}))
    (wh/'ingestion_run.jsonl').write_text(json.dumps({'run_id':'00000000-0000-0000-0000-000000000001'})+'\n')
    (wh/'source_record.jsonl').write_text(json.dumps({'source_record_key':'pubmed:1'})+'\n')
    for name in ('source_observation','run_artifact'): (wh/f'{name}.jsonl').write_text('')
    auth=tmp_path/'auth.json'; auth.write_text(json.dumps({'mode':'READ_ONLY','write_allowed':False,'repository':'owner/repo','ref':'main','git_tree_sha':'abc'}))
    unit=build_source_unit(source_record_key='pubmed:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text='Propofol caused apnea.')
    sha=code_manifest(ROOT)['sha256']
    primary=extract_assertions([unit],provider=lambda u:[{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea.','subject_surface':'Propofol'}],config=EngineConfig(engine='p',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='p',model_revision='1',prompt_sha256='b'*64))
    sf=run_semantic_factory(primary_assertions=primary['assertions'],source_units=[unit],verifier_config=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=sha,mode='MODEL_ASSISTED',model='v',model_revision='1',prompt_sha256='c'*64),reviewer=lambda r:{'verdict':'ENTAILED','rationale':'exact','confidence':'HIGH','resolved_warning_codes':[]})
    snap={'snapshot_schema_version':SNAPSHOT_SCHEMA_VERSION,'source_kind':'SYNTHETIC_CONTRACT_FIXTURE','database_sha256':None,'entities':[{'canonical_id':'DRUG:1','owning_domain':'drug','lifecycle_status':'ACTIVE','names':[{'name_text':'Propofol','normalized_name':'propofol'}]}],'assertions':[{'assertion_id':'OLD:1','canonical_id':'DRUG:1','normalized_proposition':'Propofol caused apnea.','assertion_type':'ADVERSE_EFFECT','context':{},'numeric':None}],'assertion_schema_supported':True,'query_only':True,'mutation_performed':False}
    snap['snapshot_sha256']=hashlib.sha256(json.dumps(snap,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    t6=run_turn6_audit_prep(primary_assertions=primary['assertions'],semantic_factory_result=sf,snapshot=snap)
    out=tmp_path/'audit'; m=build_audit_package(wh,out,authority_reference=auth,source_units=[unit],assertion_engine_result=primary,semantic_factory_result=sf,turn6_result=t6)
    assert m['candidate_resolution_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE'
    assert m['09d_comparator_status']=='IMPLEMENTED_OFFLINE_CERTIFIED_REAL_DATABASE_PENDING'
    assert m['actual_09d_database_bound'] is False
    assert m['counts']['identity_candidates']==1 and m['counts']['09d_comparisons']==1
    candidate=json.loads((out/'candidates/candidates.jsonl').read_text().splitlines()[0])
    comparison=json.loads((out/'09d_comparisons/comparisons.jsonl').read_text().splitlines()[0])
    assert candidate['legacy_entity_id'] is None
    assert comparison['proposed_target_canonical_id']=='DRUG:1'
    assert comparison['classification']=='EXACT_EXISTING'
    assert comparison['canonical_authority'] is False and comparison['09d_mutation_performed'] is False
    assert m['canonical_authority'] is False and m['mass_extraction_authorized'] is False
