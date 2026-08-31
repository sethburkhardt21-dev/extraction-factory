from pathlib import Path
import sys, json, hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from warehouse.project import stable_uuid, canonical_json_sha256, validate_references


def test_stable_keys_are_deterministic():
    assert stable_uuid('x','a',1)==stable_uuid('x','a',1)
    assert stable_uuid('x','a',1)!=stable_uuid('x','a',2)
    assert len(canonical_json_sha256({'b':2,'a':1}))==64


def test_referential_validator_catches_missing_keys():
    tables={
        'ingestion_run':[{'run_id':'r'}],
        'source_record':[{'source_record_key':'s'}],
        'source_observation':[{'run_id':'r','source_record_key':'missing'}],
        'canonical_record':[],
    }
    assert any('missing source record' in x for x in validate_references(tables))


def test_ctg_projection_from_real_offline_fixture(tmp_path):
    # Generate a source run using the real extractor with its test fake client.
    sys.path.insert(0,str(ROOT/'clinicaltrials'))
    from canonical.clinicaltrials.extractor import ExtractionConfig, MassExtractor
    from canonical.clinicaltrials.client import ApiVersionInfo
    sample={'protocolSection':{'identificationModule':{'nctId':'NCT00000001','briefTitle':'Study'},'statusModule':{'overallStatus':'COMPLETED','lastUpdatePostDateStruct':{'date':'2024-01-01'}},'designModule':{'phases':['PHASE3'],'studyType':'INTERVENTIONAL'},'conditionsModule':{'conditions':['Test']}},'hasResults':False}
    class C:
        def fetch_version(self): return ApiVersionInfo('2.0.5','2026-08-28T09:00:06',{})
        def fetch_page(self,token,cfg): return {'studies':[sample],'totalCount':1}
    run=tmp_path/'run'; MassExtractor(ExtractionConfig(run),client=C()).run()
    from warehouse.project import project_ctg, write_projection
    tables=project_ctg(run)
    assert len(tables['source_record'])==1
    assert len(tables['ctg_study_record'])==1
    assert tables['ctg_phase'][0]['phase']=='PHASE3'
    m=write_projection(tables,tmp_path/'wh',source='clinicaltrials.gov')
    assert m['validation_status']=='PASS'
    assert m['artifacts']['ctg_study_record']['records']==1


def test_pubmed_projection_from_fake_certified_run(tmp_path):
    sys.path.insert(0,str(ROOT/'pubmed_rag'))
    from datetime import datetime, timezone
    from metadata_schema import PubMedRecordFull, PubDateModel
    from run_pubmed import run
    class E:
        def extract_max(self, **kwargs):
            r=PubMedRecordFull(pmid='7',title='T',pub_date=PubDateModel(year=2024,date_source='PubDate'),run_id='00000000-0000-0000-0000-000000000007',source_record_sha256='7'*64,retrieved_at=datetime.now(timezone.utc),raw_xml='<PubmedArticle/>')
            self.last_extraction_meta={'run_id':r.run_id,'source':'pubmed','mode':'esearch_efetch_domain_candidates','status':'completed','certification_status':'PASS','started_at':'2026-08-29T00:00:00Z','completed_at':'2026-08-29T00:00:01Z','parser_version':'pubmed-canonical-3.0','canonical_schema_version':'pubmed-record-3.0','observed_records':1,'valid_records':1,'unique_records':1,'truncated':False,'complete_against_source':True,'warnings':[],'errors':[]}
            return [r]
    rd=tmp_path/'p'; run(out_dir=rd,email='x@example.org',api_key=None,mindate='2024/01/01',maxdate='2024/01/02',queries=['q'],allow_network=True,extractor_factory=E)
    from warehouse.project import project_pubmed
    t=project_pubmed(rd)
    assert len(t['pubmed_record'])==1 and len(t['pubmed_snapshot'])==1
    assert not validate_references(t)


def test_preprint_projection_version_identity(tmp_path):
    sys.path.insert(0,str(ROOT/'preprints'))
    from src.pipeline import run_extraction
    from src.medrxiv_biorxiv.client import normalize_record
    def f(cfg):
        yield normalize_record({'doi':'10.1101/x','title':'X','version':'1','server':'medrxiv'},'medrxiv')
        yield normalize_record({'doi':'10.1101/x','title':'X2','version':'2','server':'medrxiv'},'medrxiv')
    rd=tmp_path/'pp'; m=run_extraction('medrxiv','2024-01-01','2024-01-02',str(rd),'',allow_network=True,fetcher=f)
    # Fake fetcher has no API total, so source integrity is WARN by design; projection still preserves both versions.
    from warehouse.project import project_preprint
    t=project_preprint(rd)
    assert len(t['preprint_record'])==2
    assert {r['version'] for r in t['preprint_record']}=={1,2}
    assert len(t['source_record'])==2
    assert not validate_references(t)

def test_preprint_aggregate_projection_reads_shard_provenance(tmp_path):
    from warehouse.project import project_preprint, validate_references
    root=tmp_path/'agg'; shard=root/'shards'/'2024-01-01_2024-01-31'; (shard/'provenance').mkdir(parents=True)
    row={'server':'medrxiv','doi':'10.1101/2024.01.01.123456','version':'1','title':'A','abstract':'B','source_record_sha256':'b'*64,'parser_version':'preprint-canonical-2.0','canonical_schema_version':'preprint-record-2.0','retrieved_at':'2026-08-29T00:00:00Z','source_payload':{'doi':'10.1101/2024.01.01.123456','version':'1'}}
    (root/'versions_all.jsonl').parent.mkdir(parents=True,exist_ok=True)
    (root/'versions_all.jsonl').write_text(json.dumps(row)+'\n')
    prov={'source':'medrxiv','source_record_id':row['doi'],'source_version_id':'1','source_record_sha256':'b'*64,'run_id':'00000000-0000-0000-0000-000000000003','parser_version':'preprint-canonical-2.0','canonical_schema_version':'preprint-record-2.0','retrieved_at':'2026-08-29T00:00:00Z','provenance_schema_version':'frontier-source-provenance-1.0'}
    (shard/'provenance/source_records.jsonl').write_text(json.dumps(prov)+'\n')
    manifest={'manifest_schema_version':'frontier-run-manifest-1.0','run_id':'00000000-0000-0000-0000-000000000003','source':'medrxiv','mode':'monthly_sharded_details_interval','parser_version':'preprint-canonical-2.0','canonical_schema_version':'preprint-record-2.0','status':'completed','certification_status':'PASS','started_at':'2026-08-29T00:00:00Z','completed_at':'2026-08-29T00:00:01Z','observed_records':1,'valid_records':1,'unique_records':1,'quarantined_records':0,'truncated':False,'complete_against_source':True,'source_changed_during_run':False,'shard_manifest_chain':[{'path':'shards/2024-01-01_2024-01-31'}]}
    (root/'manifest.json').write_text(json.dumps(manifest))
    t=project_preprint(root)
    assert len(t['preprint_record'])==1 and len(t['source_observation'])==1
    assert not validate_references(t)


def test_ctg_projection_emits_artifact_quarantine_and_transport_lineage(tmp_path):
    from warehouse.project import project_ctg, canonical_json_sha256
    run=tmp_path/'ctglineage'; (run/'canonical').mkdir(parents=True); (run/'provenance').mkdir(); (run/'quarantine').mkdir()
    rid='00000000-0000-0000-0000-000000000020'; raw={'protocolSection':{'identificationModule':{'nctId':'NCT00000020'}}}; sha=canonical_json_sha256(raw)
    row={'source':'clinicaltrials.gov','nct_id':'NCT00000020','brief_title':'T','phase':[],'conditions':[],'source_record_sha256':sha,'last_update_post_date':'2024-01-01','source_data_timestamp':'2026-08-28T09:00:06','source_api_version':'2.0.5','retrieved_at':'2026-08-29T00:00:00Z','parser_version':'p','canonical_schema_version':'s','protocol_section':raw['protocolSection']}
    prov={'source':'clinicaltrials.gov','source_record_id':'NCT00000020','source_version_id':'2024-01-01','source_record_sha256':sha,'run_id':rid,'retrieved_at':'2026-08-29T00:00:00Z','transport_raw_locator':'raw/transport/page.json','provenance_schema_version':'frontier-source-provenance-1.0'}
    manifest={'manifest_schema_version':'frontier-run-manifest-1.0','run_id':rid,'source':'clinicaltrials.gov','mode':'api_query','parser_version':'p','canonical_schema_version':'s','status':'completed','certification_status':'PASS','started_at':'2026-08-29T00:00:00Z','completed_at':'2026-08-29T00:00:01Z','observed_records':1,'valid_records':1,'unique_records':1,'quarantined_records':1,'truncated':False,'complete_against_source':False}
    (run/'extraction_manifest.json').write_text(json.dumps(manifest)); (run/'canonical/studies_canonical.jsonl').write_text(json.dumps(row)+'\n'); (run/'provenance/source_records.jsonl').write_text(json.dumps(prov)+'\n')
    bad={'raw':{'protocolSection':{}},'_validation_errors':['missing nctId'],'error':'missing nctId'}; (run/'quarantine/invalid_records.jsonl').write_text(json.dumps(bad)+'\n')
    t=project_ctg(run)
    assert any(a['role']=='source_manifest' for a in t['run_artifact'])
    assert len(t['quarantine_record'])==1 and t['quarantine_record'][0]['error_type']=='ValidationError'
    assert t['source_observation'][0]['transport_raw_locators']==['raw/transport/page.json']


def test_pubmed_child_rows_match_physical_names(tmp_path):
    from warehouse.project import project_pubmed
    run=tmp_path/'pub'; (run/'canonical').mkdir(parents=True); (run/'provenance').mkdir()
    rid='00000000-0000-0000-0000-000000000021'; raw='<PubmedArticle/>'; sha=hashlib.sha256(raw.encode()).hexdigest()
    row={'source':'pubmed','pmid':'21','title':'T','raw_xml':raw,'source_record_sha256':sha,'retrieved_at':'2026-08-29T00:00:00Z','parser_version':'p','canonical_schema_version':'s','authors':[{'last_name':'Doe','fore_name':'J','affiliations':['X']}],'mesh_headings':[{'descriptor_name':'D','descriptor_ui':'D1','major_topic':True,'qualifiers':[{'name':'q'}]}]}
    prov={'source':'pubmed','source_record_id':'21','source_version_id':'','source_record_sha256':sha,'run_id':rid,'retrieved_at':row['retrieved_at'],'provenance_schema_version':'frontier-source-provenance-1.0'}
    manifest={'manifest_schema_version':'frontier-run-manifest-1.0','run_id':rid,'source':'pubmed','mode':'test','parser_version':'p','canonical_schema_version':'s','status':'completed','certification_status':'PASS','started_at':'2026-08-29T00:00:00Z','completed_at':'2026-08-29T00:00:01Z','observed_records':1,'valid_records':1,'unique_records':1,'quarantined_records':0,'truncated':False,'complete_against_source':True}
    (run/'manifest.json').write_text(json.dumps(manifest)); (run/'canonical/pubmed_records.jsonl').write_text(json.dumps(row)+'\n'); (run/'provenance/source_records.jsonl').write_text(json.dumps(prov)+'\n')
    t=project_pubmed(run)
    assert t['pubmed_author'][0]['payload']['last_name']=='Doe'
    assert t['pubmed_mesh_heading'][0]['descriptor_name']=='D'


def test_semantic_validator_rejects_count_and_transport_claim_drift():
    from warehouse.project import validate_projection_semantics
    tables={
        'ingestion_run':[{'run_id':'r','valid_records':2,'quarantined_records':0,'observed_records':2,'unique_records':2,'manifest':{'transport_capture_status':'PASS_EXACT_HTTP_RESPONSES'}}],
        'source_record':[{'source_record_key':'s'}],
        'canonical_record':[{'canonical_record_key':'c'}],
        'quarantine_record':[],
        'run_artifact':[{'role':'source_manifest','locator':'manifest.json'}],
        'source_observation':[],
    }
    errs=validate_projection_semantics(tables)
    assert any('valid_records=2' in e for e in errs)
    assert any('unique_records=2' in e for e in errs)
    assert any('no exact raw transport' in e for e in errs)
