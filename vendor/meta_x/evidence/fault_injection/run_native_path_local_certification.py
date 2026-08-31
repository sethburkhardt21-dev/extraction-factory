#!/usr/bin/env python3
from __future__ import annotations
import json, sys, threading, time, hashlib, shutil
from copy import deepcopy
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parents[2]
for p in [ROOT, ROOT/'clinicaltrials']:
    if str(p) not in sys.path: sys.path.insert(0,str(p))

import requests
import canonical.clinicaltrials.client as ctg_client_mod
from canonical.clinicaltrials.extractor import ExtractionConfig, MassExtractor
import preprints.src.pipeline as pp_pipeline
from preprints.src.medrxiv_biorxiv.client import FetchConfig as RealPPFetchConfig
import pubmed_rag.run_pubmed as pubrun
from pubmed_rag.pubmed_anesthesia_extraction import RateLimitedPubMedClient as RealPubClient
from warehouse.project import project_run
from frontier_core.readiness import code_manifest

OUT=ROOT/'evidence'/'fault_injection'; RUNS=OUT/'native_path_runs'
SAMPLE={"protocolSection":{"identificationModule":{"nctId":"NCT04368728","briefTitle":"Test"},"statusModule":{"overallStatus":"COMPLETED","lastUpdatePostDateStruct":{"date":"2026-03-25"}},"designModule":{"phases":["PHASE2","PHASE3"],"studyType":"INTERVENTIONAL","enrollmentInfo":{"count":46969,"type":"ACTUAL"}},"conditionsModule":{"conditions":["COVID-19"]}},"hasResults":True}
def ctg(i): x=deepcopy(SAMPLE); x['protocolSection']['identificationModule']['nctId']=i; return x
PUBMED_XML='''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>33301246</PMID><Article><ArticleTitle>Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine</ArticleTitle><Abstract><AbstractText>Controlled local HTTP native-path fixture.</AbstractText></Abstract><Journal><JournalIssue><PubDate><Year>2020</Year><Month>Dec</Month><Day>31</Day></PubDate></JournalIssue><Title>N Engl J Med</Title></Journal></Article></MedlineCitation><PubmedData><PublicationStatus>ppublish</PublicationStatus><ArticleIdList><ArticleId IdType="pubmed">33301246</ArticleId><ArticleId IdType="doi">10.1056/NEJMoa2034577</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''
PPR=[{'title':f'Paper {i}','authors':'A; B','author_corresponding':'A','author_corresponding_institution':'U','doi':f'10.1101/local.{i:03d}','date':'2026-08-28','version':'1','type':'new results','license':'cc_by','category':'medicine','jatsxml':'','abstract':f'A{i}','published':'','server':'medRxiv'} for i in range(35)]
class S: ctg_fail=True; ctg_p2=0; pp0=0; pes=0; req=[]
st=S()
class H(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*a): pass
    def sendb(self,status,b,ctype='application/json',headers=None):
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(b)))
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(b); self.wfile.flush()
    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query); st.req.append((u.path,q))
        if u.path=='/ctg/version': return self.sendb(200,json.dumps({'apiVersion':'2.0.5','dataTimestamp':'2026-08-28T09:00:06'}).encode())
        if u.path=='/ctg/studies':
            tok=(q.get('pageToken') or [None])[0]
            if tok is None: return self.sendb(200,json.dumps({'studies':[ctg('NCT04368728'),ctg('NCT00000002')],'nextPageToken':'p2','totalCount':3}).encode())
            st.ctg_p2+=1
            if st.ctg_fail: return self.sendb(503,b'{"e":"down"}',headers={'Retry-After':'0'})
            return self.sendb(200,json.dumps({'studies':[ctg('NCT00000003')],'totalCount':3}).encode())
        if u.path.startswith('/details/medrxiv/'):
            c=int(u.path.rstrip('/').split('/')[-1])
            if c==0:
                st.pp0+=1
                if st.pp0==1: return self.sendb(429,b'{"e":"rate"}',headers={'Retry-After':'0'})
                rows=PPR[:30]
            elif c==30: rows=PPR[30:]
            else: rows=[]
            return self.sendb(200,json.dumps({'messages':[{'total':'35'}],'collection':rows}).encode())
        if u.path=='/pubmed/esearch':
            st.pes+=1
            if st.pes==1: return self.sendb(429,b'{"e":"rate"}',headers={'Retry-After':'0'})
            return self.sendb(200,json.dumps({'esearchresult':{'count':'1','idlist':['33301246']}}).encode())
        if u.path=='/pubmed/efetch': return self.sendb(200,PUBMED_XML.encode(),'application/xml')
        return self.sendb(404,b'{}')

class RewriteSession(requests.Session):
    def __init__(self,base): super().__init__(); self.base=base
    def get(self,url,*args,**kwargs):
        params=kwargs.pop('params',None)
        if 'esearch.fcgi' in url: target=self.base+'/pubmed/esearch'
        elif 'efetch.fcgi' in url: target=self.base+'/pubmed/efetch'
        else: target=url
        return super().get(target,*args,params=params,**kwargs)

def gate(rep,n,ok,d): rep['gates'].append({'gate':n,'passed':bool(ok),'detail':d}); assert ok,n

def main():
    if RUNS.exists(): shutil.rmtree(RUNS)
    RUNS.mkdir(parents=True)
    srv=ThreadingHTTPServer(('127.0.0.1',0),H); threading.Thread(target=srv.serve_forever,daemon=True).start(); base=f'http://127.0.0.1:{srv.server_address[1]}'
    rep={'evidence_schema_version':'frontier-native-path-local-http-1.0','status':'FAIL','production_code_manifest_sha256':code_manifest(ROOT)['sha256'],'public_host_canary':False,'mass_unlock_eligible':False,'gates':[]}
    # patch only endpoint/config construction, not production client/extractor behavior.
    old=(ctg_client_mod.API_VERSION_ENDPOINT,ctg_client_mod.API_BASE)
    oldpp=pp_pipeline.FetchConfig; oldpub=pubrun.RateLimitedPubMedClient
    try:
        ctg_client_mod.API_VERSION_ENDPOINT=base+'/ctg/version'; ctg_client_mod.API_BASE=base+'/ctg/studies'
        cdir=RUNS/'ctg'
        ex=MassExtractor(ExtractionConfig(cdir,page_size=2,rate_per_sec=1000))
        # make retry exhaustion immediate on injected outage so checkpoint remains.
        ex.client.max_retries=1; ex.client.sleeper=lambda _:None
        failed=False
        try: ex.run()
        except requests.HTTPError: failed=True
        gate(rep,'ctg_native_capture_crash_checkpoint',failed and (cdir/'checkpoint.json').exists() and any((cdir/'raw/transport').glob('*.json')),'native transport files + checkpoint durable')
        st.ctg_fail=False
        ex2=MassExtractor(ExtractionConfig(cdir,page_size=2,rate_per_sec=1000)); ex2.client.sleeper=lambda _:None
        cm=ex2.run(); gate(rep,'ctg_native_capture_resume_pass',cm['certification_status']=='PASS' and cm['transport_capture_status']=='PASS_EXACT_HTTP_RESPONSES' and cm['records']==3,f"{cm['certification_status']} {cm['transport_capture_status']} records={cm['records']}")
        wm=project_run('ctg',cdir,cdir/'warehouse'); gate(rep,'ctg_native_path_projection',wm['validation_status']=='PASS','PASS')

        # Preprint: patch only FetchConfig constructor so production default fetcher remains identical object => native capture enabled.
        def LocalPPFetchConfig(**kw): return RealPPFetchConfig(**kw,api_base=base,rate_limit_sec=0,max_retries=3,timeout=3)
        pp_pipeline.FetchConfig=LocalPPFetchConfig
        pdir=RUNS/'medrxiv'; pm=pp_pipeline.run_extraction('medrxiv','2026-08-28','2026-08-28',str(pdir),'test@example.org',allow_network=True)
        gate(rep,'preprint_native_capture_pass',pm['certification_status']=='PASS' and pm['transport_capture_status']=='PASS_EXACT_HTTP_RESPONSES' and pm['observed_records']==35,f"{pm['certification_status']} responses={pm['transport_response_count']}")
        gate(rep,'preprint_native_retry_429',st.pp0>=2,f'attempts={st.pp0}')
        pwm=project_run('medrxiv',pdir,pdir/'warehouse'); gate(rep,'preprint_native_path_projection',pwm['validation_status']=='PASS','PASS')

        # PubMed: retain production run() native branch; patch client constructor only to route Session locally.
        def LocalPubClient(cfg,raw_response_hook=None,session=None): return RealPubClient(cfg,raw_response_hook=raw_response_hook,session=RewriteSession(base))
        pubrun.RateLimitedPubMedClient=LocalPubClient
        udir=RUNS/'pubmed'; um=pubrun.run(out_dir=udir,email='test@example.org',api_key=None,mindate='2020/01/01',maxdate='2020/12/31',queries=['33301246[PMID]'],allow_network=True)
        gate(rep,'pubmed_native_capture_pass',um['certification_status']=='PASS' and um['transport_capture_status']=='PASS_EXACT_HTTP_RESPONSES' and um['valid_records']==1,f"{um['certification_status']} responses={um['transport_response_count']}")
        gate(rep,'pubmed_native_retry_429',st.pes>=3,f'esearch attempts={st.pes}')
        uwm=project_run('pubmed',udir,udir/'warehouse'); gate(rep,'pubmed_native_path_projection',uwm['validation_status']=='PASS','PASS')
        rep['status']='PASS'; rep['notes']=['Production native-capture branches were executed over real localhost HTTP with only endpoint/session routing patched to the controlled server.','This proves exact transport capture, retry, resume and warehouse projection mechanics, but cannot unlock mass extraction because the hosts were not the public sources.']
    finally:
        ctg_client_mod.API_VERSION_ENDPOINT,ctg_client_mod.API_BASE=old; pp_pipeline.FetchConfig=oldpp; pubrun.RateLimitedPubMedClient=oldpub; srv.shutdown(); srv.server_close()
    (OUT/'NATIVE_PATH_LOCAL_HTTP_CERTIFICATION.json').write_text(json.dumps(rep,indent=2,sort_keys=True)+'\n')
    text=['NATIVE-PATH LOCAL HTTP CERTIFICATION: '+rep['status'],f"CODE SHA256: {rep['production_code_manifest_sha256']}",'PUBLIC-HOST CANARY: FALSE','MASS UNLOCK ELIGIBLE: FALSE','']+[f"{'PASS' if g['passed'] else 'FAIL'} | {g['gate']} | {g['detail']}" for g in rep['gates']]
    (OUT/'NATIVE_PATH_LOCAL_HTTP_CERTIFICATION.txt').write_text('\n'.join(text)+'\n'); print('\n'.join(text))
if __name__=='__main__': main()
