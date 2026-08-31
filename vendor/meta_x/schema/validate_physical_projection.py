#!/usr/bin/env python3
"""Prove that actual warehouse projector rows fit both physical backend DDLs.

This is an offline contract test. It builds rich source-shaped fixtures, runs the real
projectors, unions every emitted table/column, and requires each emitted column to
exist as a top-level column in both PostgreSQL and BigQuery schemas.
"""
from __future__ import annotations
import hashlib, json, re, sys, tempfile
from pathlib import Path
from typing import Any, Dict, Iterable

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from warehouse.project import project_ctg, project_pubmed, project_preprint, project_drug, sha256_file

PG=ROOT/'schema/frontier_postgres.sql'
BQ=ROOT/'schema/frontier_bigquery.sql'
OUT=ROOT/'schema/PHYSICAL_PROJECTION_CONTRACT.json'


def jwrite(path:Path,obj:Any):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,sort_keys=True)+'\n',encoding='utf-8')

def jlwrite(path:Path,rows:Iterable[Dict[str,Any]]):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows),encoding='utf-8')

def sha_obj(obj:Any)->str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def base_manifest(run_id:str,source:str,mode:str,parser:str,schema:str)->Dict[str,Any]:
    return {'manifest_schema_version':'frontier-run-manifest-1.0','run_id':run_id,'source':source,'mode':mode,
            'parser_version':parser,'canonical_schema_version':schema,'status':'completed','certification_status':'PASS',
            'started_at':'2026-08-29T00:00:00Z','completed_at':'2026-08-29T00:00:01Z','observed_records':1,'valid_records':1,
            'unique_records':1,'quarantined_records':0,'truncated':False,'complete_against_source':True,'source_changed_during_run':False,
            'warnings':[],'errors':[]}

def ctg_fixture(root:Path):
    run=root/'ctg'; rid='00000000-0000-0000-0000-000000000101'
    raw={'protocolSection':{'identificationModule':{'nctId':'NCT00000101'}}}; srcsha=sha_obj(raw)
    row={'source':'clinicaltrials.gov','nct_id':'NCT00000101','brief_title':'Rich study','official_title':'Rich official','acronym':'RICH',
         'nct_id_aliases':['NCTALIAS'],'org_study_id_info':{'id':'ORG1'},'secondary_id_infos':[{'id':'SEC1'}],'organization':{'fullName':'Org'},
         'brief_summary':'summary','detailed_description':'detail','overall_status':'RECRUITING','why_stopped':None,'expanded_access_info':{},
         'phase':['PHASE2','PHASE3'],'study_type':'INTERVENTIONAL','design':{'allocation':'RANDOMIZED'},'enrollment_count':10,'enrollment_type':'ACTUAL',
         'conditions':['Condition A'],'keywords':['keyword'],'sponsors':{'lead':{'name':'Lead','class':'INDUSTRY'},'responsible_party':{'name':'RP','class':'OTHER'},'collaborators':[{'name':'Collab','class':'NIH'}]},
         'start_date':'2024-01-01','start_date_type':'ACTUAL','primary_completion_date':'2024-02-01','primary_completion_date_type':'ACTUAL',
         'completion_date':'2024-03-01','completion_date_type':'ACTUAL','study_first_submit_date':'2023-12-01','study_first_post_date':'2023-12-02',
         'last_update_submit_date':'2024-03-02','last_update_post_date':'2024-03-03','last_update_post_date_type':'ACTUAL','eligibility':{'sex':'ALL'},
         'arms':[{'label':'Arm A','type':'EXPERIMENTAL','description':'A'}],
         'interventions':[{'type':'DRUG','name':'Drug A','description':'D','otherNames':['DA'],'armGroupLabels':['Arm A']}],
         'central_contacts':[{'name':'Contact','role':'CONTACT','affiliation':'Site','phone':'1','email':'a@example.org'}],
         'overall_officials':[{'name':'Official','role':'PRINCIPAL_INVESTIGATOR','affiliation':'Site'}],
         'locations':[{'facility':{'name':'Facility','status':'RECRUITING'},'city':'City','state':'ST','zip':'00000','country':'US','geoPoint':{'lat':1.1,'lon':2.2}}],
         'primary_outcomes':[{'measure':'Primary','description':'P','timeFrame':'1 day'}],
         'secondary_outcomes':[{'measure':'Secondary','description':'S','timeFrame':'2 days'}],
         'other_outcomes':[{'measure':'Other','description':'O','timeFrame':'3 days'}],
         'references':[{'type':'BACKGROUND','pmid':'123','citation':'Citation'}],'see_also_links':[{'label':'x','url':'https://example.org'}],
         'available_ipds':[{'type':'STUDY_PROTOCOL','url':'https://example.org/ipd','comment':'c'}],'ipd_sharing':{'ipdSharing':'YES'},'oversight':{'oversightHasDmc':True},
         'has_results':True,'is_fda_regulated_drug':True,'is_fda_regulated_device':False,'protocol_section':raw['protocolSection'],'results_section':{'x':1},
         'annotation_section':{'x':1},'document_section':{'x':1},'derived_section':{'x':1},'source_record_sha256':srcsha,'source_data_timestamp':'2026-08-28T09:00:06',
         'source_api_version':'2.0.5','retrieved_at':'2026-08-29T00:00:00Z','parser_version':'clinicaltrials-canonical-3.0','canonical_schema_version':'clinicaltrials-study-3.0'}
    prov={'source':'clinicaltrials.gov','source_record_id':row['nct_id'],'source_version_id':row['last_update_post_date'],'source_record_sha256':srcsha,'run_id':rid,
          'retrieved_at':row['retrieved_at'],'source_url':'https://clinicaltrials.gov/study/NCT00000101','transport_raw_locator':'raw/transport/page.json','parse_status':'parsed','provenance_schema_version':'frontier-source-provenance-1.0'}
    m=base_manifest(rid,'clinicaltrials.gov','api_query','clinicaltrials-canonical-3.0','clinicaltrials-study-3.0'); m.update({'source_version_start':'2026-08-28T09:00:06','source_version_end':'2026-08-28T09:00:06'})
    jwrite(run/'extraction_manifest.json',m); jlwrite(run/'canonical/studies_canonical.jsonl',[row]); jlwrite(run/'provenance/source_records.jsonl',[prov])
    bad={'raw':{'protocolSection':{}},'_validation_errors':['missing nctId'],'error_type':'ValidationError','error':'missing nctId','retrieved_at':'2026-08-29T00:00:00Z'}
    jlwrite(run/'quarantine/invalid_records.jsonl',[bad])
    return project_ctg(run)

def pubmed_fixture(root:Path):
    run=root/'pubmed'; rid='00000000-0000-0000-0000-000000000102'; raw='<PubmedArticle><PMID>102</PMID></PubmedArticle>'; srcsha=hashlib.sha256(raw.encode()).hexdigest()
    row={'source':'pubmed','pmid':'102','record_type':'journal_article','doi':'10.1/x','pmc_id':'PMC102','version':'1','title':'Title','abstract':'Abstract','abstract_sections':[{'label':'BACKGROUND','text':'A'}],
         'authors':[{'last_name':'Doe','fore_name':'Jane','initials':'J','collective_name':None,'affiliations':['Inst'],'identifiers':{'orcid':'0000'}}],
         'journal':'Journal','journal_abbrev':'J','journal_issn':'1234','volume':'1','issue':'2','pages':'3-4','pub_date':{'parsed_date':'2024-01-01','medline_date_str':None},
         'article_date':{'parsed_date':'2024-01-02'},'pubmed_pub_dates':{'pubmed':'2024-01-03'},'date_created':'2024-01-01T00:00:00Z','date_completed':'2024-01-04T00:00:00Z','date_revised':'2024-01-05T00:00:00Z',
         'publication_types':['Journal Article'],'languages':['eng'],'keywords':['kw'],'mesh_headings':[{'descriptor_name':'Thing','descriptor_ui':'D1','major_topic':True,'qualifiers':[{'name':'therapy'}]}],
         'chemicals':[{'name':'Chem'}],'grants':[{'grant_id':'G'}],'article_ids':{'doi':'10.1/x'},'references':[{'pmid':'1'}],'publication_status':'ppublish','book_metadata':{},'raw_xml':raw,
         'run_id':rid,'source_record_sha256':srcsha,'retrieved_at':'2026-08-29T00:00:00Z','retrieval_queries':['q'],'parser_version':'pubmed-canonical-3.0','canonical_schema_version':'pubmed-record-3.0'}
    prov={'source':'pubmed','source_record_id':'102','source_version_id':'1','source_record_sha256':srcsha,'run_id':rid,'retrieved_at':row['retrieved_at'],'transport_raw_locators':['raw/transport/efetch.xml'],'parse_status':'parsed','provenance_schema_version':'frontier-source-provenance-1.0'}
    m=base_manifest(rid,'pubmed','esearch_efetch_domain_candidates','pubmed-canonical-3.0','pubmed-record-3.0')
    jwrite(run/'manifest.json',m); jlwrite(run/'canonical/pubmed_records.jsonl',[row]); jlwrite(run/'provenance/source_records.jsonl',[prov])
    return project_pubmed(run)

def preprint_fixture(root:Path):
    run=root/'pp'; rid='00000000-0000-0000-0000-000000000103'; payload={'server':'medrxiv','doi':'10.1101/x','version':'1','title':'Preprint'}; srcsha=sha_obj(payload)
    row={'source':'medrxiv','server':'medrxiv','doi':'10.1101/x','version':'1','title':'Preprint','abstract':'A','authors':'A; B','author_corresponding':'A','author_corresponding_institution':'Inst','category':'medicine','date':'2024-01-01','license':'cc_by','published':'10.1/p','source_payload':payload,'source_record_sha256':srcsha,'retrieved_at':'2026-08-29T00:00:00Z','parser_version':'preprint-canonical-2.0','canonical_schema_version':'preprint-record-2.0'}
    prov={'source':'medrxiv','source_record_id':row['doi'],'source_version_id':'1','source_record_sha256':srcsha,'run_id':rid,'retrieved_at':row['retrieved_at'],'transport_raw_locator':'raw/transport/page.json','parse_status':'parsed','provenance_schema_version':'frontier-source-provenance-1.0'}
    m=base_manifest(rid,'medrxiv','details_interval','preprint-canonical-2.0','preprint-record-2.0')
    jwrite(run/'manifest.json',m); jlwrite(run/'versions.jsonl',[row]); jlwrite(run/'provenance/source_records.jsonl',[prov])
    return project_preprint(run)

def drug_fixture(root:Path):
    d=root/'drug'; d.mkdir(parents=True,exist_ok=True); rid='00000000-0000-0000-0000-000000000104'
    db={'drugbank_id':'DB1','name':'Alpha','name_normalized':'alpha','synonyms':['A'],'source_updated':'2024-01-01','source_record_sha256':'a'*64}
    rx={'rxcui':'123','name':'Alpha','name_normalized':'alpha','source_payload':{'idGroup':{'rxnormId':['123']}},'source_record_sha256':'b'*64}
    lt={'source_nbk_id':'NBK1','name':'Alpha','name_normalized':'alpha','source_text':'text','source_record_sha256':'c'*64}
    srcdir=d/'sources'; jlwrite(srcdir/'drugbank.jsonl',[db]); jlwrite(srcdir/'rxnorm.jsonl',[rx]); jlwrite(srcdir/'livertox.jsonl',[lt])
    cross={'name':'Alpha','name_normalized':'alpha','drugbank':db,'rxnorm':rx,'livertox':lt,'linkage':{'rxnorm_status':'matched','rxnorm_candidate_ids':['rxnorm:123'],'livertox_status':'matched','livertox_candidate_ids':['livertox:NBK1'],'method':'normalized_exact_primary_or_synonym'}}
    out=d/'crosswalk.jsonl'; jlwrite(out,[cross])
    prov=[]
    for source,sid,sha,ver in [('drugbank','DB1','a'*64,'2024-01-01'),('rxnorm','123','b'*64,''),('livertox','NBK1','c'*64,'')]:
        prov.append({'source':source,'source_record_id':sid,'source_version_id':ver,'source_record_sha256':sha,'run_id':rid,'retrieved_at':'2026-08-29T00:00:00Z','parse_status':'parsed','provenance_schema_version':'frontier-source-provenance-1.0'})
    jlwrite(Path(str(out)+'.provenance.jsonl'),prov)
    m=base_manifest(rid,'drugbank+rxnorm+livertox','offline_crosswalk','drug-crosswalk-2.0','drug-crosswalk-record-2.0')
    m['source_artifacts']={k:{'path':f'sources/{k}.jsonl','sha256':sha256_file(srcdir/f'{k}.jsonl'),'records':1} for k in ('drugbank','rxnorm','livertox')}
    m['raw_input_artifacts']={k:{'locator':str(srcdir/f'{k}.jsonl'),'sha256':sha256_file(srcdir/f'{k}.jsonl'),'retention_required':True,'copied_into_output':False} for k in ('drugbank','rxnorm','livertox')}
    m['input_manifests']={'drugbank':{'source_release':'r1'},'rxnorm':{'source_snapshot_timestamp':'t'},'livertox':{'source_snapshot_timestamp':'t'}}
    jwrite(Path(str(out)+'.manifest.json'),m)
    return project_drug(out)

def ddl_columns(path:Path)->Dict[str,set[str]]:
    text=path.read_text(encoding='utf-8')
    tables={}
    for m in re.finditer(r'CREATE TABLE IF NOT EXISTS frontier\.([a-z0-9_]+) \(\n(.*?)\n\)',text,re.S|re.I):
        name=m.group(1); cols=set()
        for line in m.group(2).splitlines():
            cm=re.match(r'^  ([a-z_][a-z0-9_]*)\s+',line,re.I)
            if cm: cols.add(cm.group(1).lower())
        tables[name]=cols
    return tables

def collect(root:Path)->Dict[str,set[str]]:
    all_tables={}
    for tables in (ctg_fixture(root),pubmed_fixture(root),preprint_fixture(root),drug_fixture(root)):
        for table,rows in tables.items():
            all_tables.setdefault(table,set())
            for row in rows: all_tables[table].update(row.keys())
    all_tables['release_snapshot']={'release_id','label','schema_version','created_at','status','manifest_sha256','manifest'}
    all_tables['release_run']={'release_id','run_id'}
    return all_tables

def main()->int:
    with tempfile.TemporaryDirectory() as td:
        emitted=collect(Path(td))
    backends={'postgres':ddl_columns(PG),'bigquery':ddl_columns(BQ)}
    missing_tables={}; missing_columns={}; details={}
    for backend,ddl in backends.items():
        missing_tables[backend]=sorted(t for t in emitted if t not in ddl)
        missing_columns[backend]={}
        details[backend]={}
        for t,cols in sorted(emitted.items()):
            dcols=ddl.get(t,set()); miss=sorted(c.lower() for c in cols if c.lower() not in dcols)
            if miss: missing_columns[backend][t]=miss
            details[backend][t]={'emitted_columns':sorted(cols),'ddl_columns':sorted(dcols),'missing_emitted_columns':miss}
    status='PASS' if not any(missing_tables.values()) and not any(missing_columns.values()) else 'FAIL'
    report={'contract_schema_version':'frontier-physical-projection-contract-1.0','status':status,
            'method':'actual rich offline projector fixtures; emitted columns must be subset of both DDLs',
            'emitted_tables':sorted(emitted),'missing_tables':missing_tables,'missing_columns':missing_columns,'backends':details}
    OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(f'PHYSICAL PROJECTION CONTRACT: {status}')
    print(f'PROJECTED TABLES: {len(emitted)}')
    for b in ('postgres','bigquery'):
        print(f'{b.upper()} missing tables: {missing_tables[b] or "none"}')
        print(f'{b.upper()} missing columns: {missing_columns[b] or "none"}')
    return 0 if status=='PASS' else 1

if __name__=='__main__': raise SystemExit(main())
