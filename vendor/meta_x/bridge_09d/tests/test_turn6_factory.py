import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit
from bridge_09d.assertion_engine import EngineConfig,extract_assertions
from bridge_09d.comparator_09d import SNAPSHOT_SCHEMA_VERSION
from bridge_09d.semantic_factory import run_semantic_factory
from bridge_09d.turn6_factory import run_turn6_audit_prep
from bridge_09d.verifier import VerifierConfig

SHA='c'*64

def test_turn6_factory_registers_candidate_and_compares_readonly_without_authority():
    u=build_source_unit(source_record_key='p:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text='Propofol caused apnea.')
    ec=EngineConfig(engine='p',engine_version='1',code_manifest_sha256=SHA,mode='MODEL_ASSISTED',model='p',model_revision='1',prompt_sha256='d'*64)
    a=extract_assertions([u],provider=lambda x:[{'assertion_type':'ADVERSE_EFFECT','normalized_proposition':'Propofol caused apnea.','evidence_text':'Propofol caused apnea.','subject_surface':'Propofol'}],config=ec)['assertions']
    vc=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=SHA,mode='MODEL_ASSISTED',model='v',model_revision='1',prompt_sha256='e'*64)
    sf=run_semantic_factory(primary_assertions=a,source_units=[u],verifier_config=vc,reviewer=lambda r:{'verdict':'ENTAILED','rationale':'exact','confidence':'HIGH','resolved_warning_codes':[]})
    snap={'snapshot_schema_version':SNAPSHOT_SCHEMA_VERSION,'source_kind':'SYNTHETIC_CONTRACT_FIXTURE','database_sha256':None,'entities':[{'canonical_id':'DRUG:1','owning_domain':'drug','lifecycle_status':'ACTIVE','names':[{'name_text':'Propofol','normalized_name':'propofol'}]}],'assertions':[{'assertion_id':'OLD:1','canonical_id':'DRUG:1','normalized_proposition':'Propofol caused apnea.','assertion_type':'ADVERSE_EFFECT','context':{},'numeric':None}],'assertion_schema_supported':True,'query_only':True,'mutation_performed':False}
    snap['snapshot_sha256']=hashlib.sha256(json.dumps(snap,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    r=run_turn6_audit_prep(primary_assertions=a,semantic_factory_result=sf,snapshot=snap)
    assert r['candidate_resolution_performed'] is True and r['09d_comparison_performed'] is True
    assert r['candidate_to_canonical_assignment_performed'] is False and r['09d_mutation_performed'] is False
    assert r['09d_comparison']['comparisons'][0]['classification']=='EXACT_EXISTING'
    assert r['canonical_authority'] is False and r['mass_extraction_authorized'] is False
