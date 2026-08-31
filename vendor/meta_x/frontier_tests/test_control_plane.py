from pathlib import Path
from types import SimpleNamespace
import json, sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import frontier_orchestrator as orch
from frontier_release import create_release, verify_projection
from warehouse.project import atomic_json, atomic_jsonl, sha256_file

def args(tmp_path, **kw):
    base=dict(source='ctg',mode='canary',output_root=tmp_path/'runs',execute=False,preflight=None,canary_cert=None,query=None,page_size=1000,ctg_bulk=False,mindate=None,maxdate=None,start=None,end=None,email='')
    base.update(kw); return SimpleNamespace(**base)

def test_orchestrator_is_no_network_dry_run(tmp_path):
    r=orch.run_orchestration(args(tmp_path))
    assert r['status']=='dry_run' and r['network_extraction_performed'] is False
    assert not (tmp_path/'runs').exists()

def test_full_requires_canary_even_after_preflight(monkeypatch,tmp_path):
    monkeypatch.setattr(orch,'require_frontier_preflight',lambda p,r:{'production_code_manifest':{'sha256':'x'}})
    with pytest.raises(RuntimeError,match='canary-cert'):
        orch.run_orchestration(args(tmp_path,mode='full',execute=True,preflight=tmp_path/'p.json'))

def test_canary_certificate_is_code_bound(tmp_path):
    p=tmp_path/'c.json'; p.write_text(json.dumps({'status':'PASS','source':'ctg','transport':'native_http','mass_unlock_eligible':True,'production_code_manifest_sha256':'old'}))
    with pytest.raises(RuntimeError,match='code changed'):
        orch._canary_cert(p,'ctg','new')

def make_projection(root:Path, *, source='clinicaltrials.gov', cert='PASS', complete=True, quarantine=0, truncated=False, changed=False):
    root.mkdir(parents=True)
    run={'run_id':'00000000-0000-0000-0000-000000000001','source':source,'status':'completed','certification_status':cert,'truncated':truncated,'complete_against_source':complete,'quarantined_records':quarantine,'source_changed_during_run':changed}
    atomic_jsonl(root/'ingestion_run.jsonl',[run])
    atomic_jsonl(root/'source_record.jsonl',[])
    arts={}
    for p in [root/'ingestion_run.jsonl',root/'source_record.jsonl']:
        arts[p.stem]={'path':p.name,'records':1 if p.name.startswith('ingestion') else 0,'sha256':sha256_file(p)}
    pm={'validation_status':'PASS','source_manifest_sha256':'a'*64,'artifacts':arts}
    atomic_json(root/'warehouse_projection_manifest.json',pm)
    psha=sha256_file(root/'warehouse_projection_manifest.json')
    atomic_json(root/'orchestration_evidence.json',{'evidence_schema_version':'frontier-orchestration-evidence-1.0','source':'ctg','orchestration_mode':'full','orchestration_status':'PASS','transport_capture_status':'PASS_EXACT_HTTP_RESPONSES','transport_certified':True,'source_run_id':run['run_id'],'production_code_manifest_sha256':'c'*64,'preflight_sha256':'d'*64,'source_manifest_sha256':'a'*64,'warehouse_projection_manifest_sha256':psha})
    return root

def test_release_accepts_only_promotable_projection(tmp_path):
    p=make_projection(tmp_path/'p')
    r=create_release([p],tmp_path/'release','r1',['clinicaltrials.gov'])
    assert r['status']=='certified_research_ingestion' and r['release_class']=='RESEARCH_INGESTION_SNAPSHOT' and len(r['runs'])==1
    assert r['direct_09d_insert_allowed'] is False and r['canonical_authority'] is False and r['public_eligible'] is False
    assert (tmp_path/'release/release_snapshot.jsonl').exists()

def test_release_rejects_canary_projection(tmp_path):
    p=make_projection(tmp_path/'canary')
    e=json.loads((p/'orchestration_evidence.json').read_text()); e['orchestration_mode']='canary'; atomic_json(p/'orchestration_evidence.json',e)
    with pytest.raises(RuntimeError,match='full extraction'): verify_projection(p)

def test_release_rejects_truncated_or_quarantined(tmp_path):
    p=make_projection(tmp_path/'bad',truncated=True)
    with pytest.raises(RuntimeError,match='not promotable'): verify_projection(p)
    p2=make_projection(tmp_path/'bad2',quarantine=1)
    with pytest.raises(RuntimeError,match='not promotable'): verify_projection(p2)

def test_release_requires_named_sources(tmp_path):
    p=make_projection(tmp_path/'p')
    with pytest.raises(RuntimeError,match='missing'): create_release([p],tmp_path/'release','r1',['pubmed'])

def test_release_rejects_multiple_runs_for_same_source(tmp_path):
    p1=make_projection(tmp_path/'p1')
    p2=make_projection(tmp_path/'p2')
    rows=[json.loads(x) for x in (p2/'ingestion_run.jsonl').read_text().splitlines() if x.strip()]
    rows[0]['run_id']='00000000-0000-0000-0000-000000000002'; atomic_jsonl(p2/'ingestion_run.jsonl',rows)
    pm=json.loads((p2/'warehouse_projection_manifest.json').read_text()); pm['artifacts']['ingestion_run']['sha256']=sha256_file(p2/'ingestion_run.jsonl'); atomic_json(p2/'warehouse_projection_manifest.json',pm)
    e=json.loads((p2/'orchestration_evidence.json').read_text()); e['source_run_id']=rows[0]['run_id']; e['warehouse_projection_manifest_sha256']=sha256_file(p2/'warehouse_projection_manifest.json'); atomic_json(p2/'orchestration_evidence.json',e)
    with pytest.raises(RuntimeError,match='same source'): create_release([p1,p2],tmp_path/'release','r1',[])


def test_external_transport_canary_cannot_unlock_mass_extraction(tmp_path):
    p=tmp_path/'external.json'
    p.write_text(json.dumps({
        'status':'PASS_EXTERNAL_TRANSPORT','source':'ctg','transport':'external_payload',
        'mass_unlock_eligible':False,'production_code_manifest_sha256':'same'
    }))
    with pytest.raises(RuntimeError,match='not PASS'):
        orch._canary_cert(p,'ctg','same')

def test_pass_labeled_non_native_canary_still_cannot_unlock_mass_extraction(tmp_path):
    p=tmp_path/'external-pass.json'
    p.write_text(json.dumps({
        'status':'PASS','source':'ctg','transport':'external_payload',
        'mass_unlock_eligible':False,'production_code_manifest_sha256':'same'
    }))
    with pytest.raises(RuntimeError,match='native_http'):
        orch._canary_cert(p,'ctg','same')

def test_external_canary_contract_is_permanently_non_unlocking():
    text=(ROOT/'frontier_external_canary.py').read_text()
    assert "'mass_unlock_eligible':False" in text
    assert "transport':'external_payload'" in text

def test_external_canary_parses_lossless_ctg_fixture(tmp_path):
    import frontier_external_canary as ext
    p=tmp_path/'ctg.json'
    p.write_text(json.dumps({
        'protocolSection':{
            'identificationModule':{'nctId':'NCT00000001','briefTitle':'T'},
            'designModule':{'studyType':'INTERVENTIONAL','phases':['PHASE2','PHASE3']},
            'statusModule':{'overallStatus':'COMPLETED'},
        },
        'resultsSection':{'participantFlowModule':{'groups':[]}},
        'hasResults':False,
    }))
    rows=ext._ctg(p)
    assert rows[0]['source_record_id']=='NCT00000001'
    assert rows[0]['phase']==['PHASE2','PHASE3']
    assert rows[0]['has_results'] is False


def test_external_canary_parses_preprint_versions_without_collapsing(tmp_path):
    import frontier_external_canary as ext
    p=tmp_path/'preprint.json'
    p.write_text(json.dumps({'messages':[{'status':'ok'}],'collection':[
        {'server':'medrxiv','doi':'10.1101/x','version':'1','title':'v1','date':'2026-01-01'},
        {'server':'medrxiv','doi':'10.1101/x','version':'2','title':'v2','date':'2026-01-02'},
    ]}))
    rows=ext._preprint(p,'medrxiv')
    assert [r['source_record_id'] for r in rows]==['medrxiv|10.1101/x|1','medrxiv|10.1101/x|2']


def test_external_canary_pubmed_uses_strict_raw_xml_path(tmp_path):
    import frontier_external_canary as ext
    p=tmp_path/'pubmed.xml'
    p.write_text('<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12345</PMID><Article><ArticleTitle>T</ArticleTitle><Journal><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">12345</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>')
    rows=ext._pubmed(p)
    assert rows[0]['source_record_id']=='12345'


def test_transport_certification_rejects_injected_capture():
    assert orch._transport_certified({'transport_capture_status':'PASS_EXACT_HTTP_RESPONSES'}) is True
    assert orch._transport_certified({'transport_capture_status':'PASS_EXACT_BULK_ZIP_PLUS_HTTP_VERSION_RESPONSES'}) is True
    assert orch._transport_certified({'transport_capture_status':'TEST_INJECTED_NO_NATIVE_TRANSPORT_CAPTURE'}) is False


def test_release_rejects_missing_transport_certification(tmp_path):
    p=make_projection(tmp_path/'p')
    e=json.loads((p/'orchestration_evidence.json').read_text())
    e['transport_certified']=False
    atomic_json(p/'orchestration_evidence.json',e)
    with pytest.raises(RuntimeError,match='transport certification'):
        verify_projection(p)


def test_ctg_custom_query_builds_scalar_subprocess_argument(tmp_path):
    a=args(tmp_path,source='ctg',mode='canary',query=['AREA[NCTId]NCT04368728'])
    cmd=orch.build_command(a,tmp_path/'run',tmp_path/'preflight.json')
    i=cmd.index('--query')
    assert cmd[i+1]=='AREA[NCTId]NCT04368728' and isinstance(cmd[i+1],str)


def test_ctg_rejects_multiple_query_expressions_per_run(tmp_path):
    a=args(tmp_path,source='ctg',mode='full',query=['A','B'])
    with pytest.raises(RuntimeError,match='exactly one'):
        orch.build_command(a,tmp_path/'run',tmp_path/'preflight.json')


def test_pubmed_canary_uses_known_stable_pmid(tmp_path):
    a=args(tmp_path,source='pubmed',mode='canary',email='operator@example.org')
    cmd=orch.build_command(a,tmp_path/'run',tmp_path/'preflight.json')
    assert '33301246[PMID]' in cmd


def test_pubmed_and_preprint_native_commands_require_contact_email(tmp_path):
    with pytest.raises(RuntimeError,match='contact address'):
        orch.build_command(args(tmp_path,source='pubmed',mode='canary',email=''),tmp_path/'p',tmp_path/'preflight.json')
    with pytest.raises(RuntimeError,match='contact address'):
        orch.build_command(args(tmp_path,source='medrxiv',mode='canary',email=''),tmp_path/'m',tmp_path/'preflight.json')


def test_postgres_release_status_accepts_research_ingestion_snapshot():
    ddl=(ROOT/'schema/frontier_postgres.sql').read_text()
    assert "certified_research_ingestion" in ddl

def test_frontier_gate_binds_verification_manifest(monkeypatch,tmp_path):
    import json
    import frontier_core.gate as gate
    p=tmp_path/'preflight.json'
    p.write_text(json.dumps({'status':'PASS','network_extraction_performed':False,'production_code_manifest':{'sha256':'code'},'verification_manifest':{'sha256':'tests'}}))
    monkeypatch.setattr(gate,'code_manifest',lambda root:{'sha256':'code'})
    monkeypatch.setattr(gate,'verification_manifest',lambda root:{'sha256':'changed'})
    with pytest.raises(RuntimeError,match='verification suite changed'):
        gate.require_frontier_preflight(p,tmp_path)
