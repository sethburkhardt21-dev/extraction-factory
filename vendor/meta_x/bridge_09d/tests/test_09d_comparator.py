import hashlib,json,sqlite3,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bridge_09d.assertions import build_source_unit
from bridge_09d.assertion_engine import EngineConfig,extract_assertions
from bridge_09d.comparator_09d import SNAPSHOT_SCHEMA_VERSION,build_snapshot_from_sqlite,lookup_identity,compare_assertion,compare_ready_candidates
from bridge_09d.identity_resolution import resolve_assertion_mentions
from bridge_09d.verifier import VerifierConfig,verify_assertions

SHA='c'*64

def snapshot(assertions=None, lifecycle='ACTIVE_SOURCE_GROUNDED'):
    s={'snapshot_schema_version':SNAPSHOT_SCHEMA_VERSION,'source_kind':'SYNTHETIC_CONTRACT_FIXTURE','database_sha256':None,
       'entities':[{'canonical_id':'DRUG:1','owning_domain':'drug','lifecycle_status':lifecycle,'names':[{'name_text':'Propofol','normalized_name':'propofol'}]}],
       'assertions':assertions or [],'assertion_schema_supported':True,'query_only':True,'mutation_performed':False}
    s['snapshot_sha256']=hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return s

def make(text='Propofol was administered at 0.5 mg/kg IV.', value=0.5, route='IV'):
    u=build_source_unit(source_record_key='p:1',source_resource_id='PMID:1',source_version_id='1',source_sha256='a'*64,source_scope='FULL_TEXT',unit_kind='TEXT',locator={'locator_type':'PARAGRAPH','paragraph':1},content_text=text)
    cfg=EngineConfig(engine='p',engine_version='1',code_manifest_sha256=SHA,mode='MODEL_ASSISTED',model='m',model_revision='1',prompt_sha256='d'*64)
    a=extract_assertions([u],provider=lambda x:[{'assertion_type':'DOSING','normalized_proposition':text,'evidence_text':text,'subject_surface':'Propofol','numeric':{'value':value,'unit':'mg/kg'},'context':{'route':route}}],config=cfg)['assertions'][0]
    vcfg=VerifierConfig(engine='v',engine_version='1',code_manifest_sha256=SHA,mode='MODEL_ASSISTED',model='v',model_revision='1',prompt_sha256='e'*64)
    v=verify_assertions([a],[u],config=vcfg,reviewer=lambda r:{'verdict':'ENTAILED','rationale':'exact','confidence':'HIGH','resolved_warning_codes':[]})['verification_events'][0]
    cand=resolve_assertion_mentions(assertions=[a],verification_events=[v],origin_package_id='F')['candidate_records'][0]
    return u,a,v,cand


def test_identity_lookup_exact_name_never_auto_assigns_canonical():
    _,_,_,c=make(); r=lookup_identity(c,snapshot())
    assert r['state']=='EXACT_NAME_SINGLE_CANONICAL_TARGET'
    assert r['exact_matches'][0]['canonical_id']=='DRUG:1'
    assert r['canonical_assignment_performed'] is False and r['automatic_match_allowed'] is False


def test_candidate_target_is_not_treated_as_canonical_match():
    _,_,_,c=make(); r=lookup_identity(c,snapshot(lifecycle='CANDIDATE'))
    assert r['state']=='EXACT_NAME_SINGLE_CANDIDATE_TARGET'
    assert r['requires_review'] is True


def test_exact_existing_comparison():
    _,a,v,c=make()
    s=snapshot([{'assertion_id':'OLD:1','canonical_id':'DRUG:1','normalized_proposition':a['normalized_proposition'],'assertion_type':'DOSING','context':{'route':'IV'},'numeric':{'value':0.5,'unit':'mg/kg'}}])
    r=compare_assertion(assertion=a,verification_event=v,identity_lookup=lookup_identity(c,s),snapshot=s)
    assert r['classification']=='EXACT_EXISTING' and r['matched_09d_assertion_ids']==['OLD:1']
    assert r['09d_mutation_performed'] is False


def test_same_context_different_numeric_is_contradictory_not_averaged():
    _,a,v,c=make()
    s=snapshot([{'assertion_id':'OLD:1','canonical_id':'DRUG:1','normalized_proposition':'The propofol dose was 1 mg/kg IV.','assertion_type':'DOSING','context':{'route':'IV'},'numeric':{'value':1,'unit':'mg/kg'}}])
    r=compare_assertion(assertion=a,verification_event=v,identity_lookup=lookup_identity(c,s),snapshot=s)
    assert r['classification']=='CONTRADICTORY'
    assert r['automatic_selection_allowed'] is False


def test_different_context_is_preserved_as_context_different():
    _,a,v,c=make()
    s=snapshot([{'assertion_id':'OLD:1','canonical_id':'DRUG:1','normalized_proposition':'The propofol dose was 0.5 mg/kg PO.','assertion_type':'DOSING','context':{'route':'PO'},'numeric':{'value':0.5,'unit':'mg/kg'}}])
    r=compare_assertion(assertion=a,verification_event=v,identity_lookup=lookup_identity(c,s),snapshot=s)
    assert r['classification']=='CONTEXT_DIFFERENT'


def test_novel_requires_snapshot_assertion_schema_support():
    _,a,v,c=make(); s=snapshot([])
    r=compare_assertion(assertion=a,verification_event=v,identity_lookup=lookup_identity(c,s),snapshot=s)
    assert r['classification']=='NOVEL'
    s2=dict(s); s2['assertion_schema_supported']=False; s2['snapshot_sha256']='f'*64
    r2=compare_assertion(assertion=a,verification_event=v,identity_lookup=lookup_identity(c,s2),snapshot=s2)
    assert r2['classification']=='UNRESOLVED'


def test_readonly_sqlite_adapter_is_hash_bound_and_query_only(tmp_path):
    db=tmp_path/'09d.sqlite'; con=sqlite3.connect(db)
    con.executescript('CREATE TABLE entity(canonical_id TEXT, owning_domain TEXT, lifecycle_status TEXT); CREATE TABLE entity_name(canonical_id TEXT,name_text TEXT,normalized_name TEXT); CREATE TABLE assertion(assertion_id TEXT,canonical_id TEXT,assertion_text TEXT,assertion_type TEXT);')
    con.execute("INSERT INTO entity VALUES('DRUG:1','drug','ACTIVE')"); con.execute("INSERT INTO entity_name VALUES('DRUG:1','Propofol','propofol')"); con.execute("INSERT INTO assertion VALUES('A:1','DRUG:1','Propofol causes apnea.','ADVERSE_EFFECT')"); con.commit(); con.close()
    sha=hashlib.sha256(db.read_bytes()).hexdigest()
    s=build_snapshot_from_sqlite(sqlite_path=db,expected_sha256=sha)
    assert s['source_kind']=='ACTUAL_09D_DATABASE_READONLY' and s['query_only'] is True and s['mutation_performed'] is False
    with pytest.raises(ValueError,match='SHA-256 mismatch'):
        build_snapshot_from_sqlite(sqlite_path=db,expected_sha256='0'*64)


def test_semantically_unready_assertion_is_not_compared_as_truth():
    _,a,v,c=make(); v=dict(v); v['downstream_semantic_ready']=False; v['verdict']='PARTIAL'
    s=snapshot([]); r=compare_assertion(assertion=a,verification_event=v,identity_lookup=lookup_identity(c,s),snapshot=s)
    assert r['classification']=='BLOCKED_SEMANTIC_VERIFICATION'
