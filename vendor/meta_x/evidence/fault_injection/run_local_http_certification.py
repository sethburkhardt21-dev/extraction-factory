#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys, threading, time, hashlib, tempfile, shutil
from copy import deepcopy
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
CTG_ROOT=ROOT/'clinicaltrials'
if str(CTG_ROOT) not in sys.path: sys.path.insert(0,str(CTG_ROOT))

import requests
from canonical.clinicaltrials.client import ClinicalTrialsClient
from canonical.clinicaltrials.extractor import ExtractionConfig, MassExtractor
from preprints.src.medrxiv_biorxiv.client import FetchConfig as PreprintFetchConfig, fetch_interval
from preprints.src.pipeline import run_extraction as run_preprint
from pubmed_rag.pubmed_anesthesia_extraction import RateLimitConfig, RateLimitedPubMedClient, PubMedSourceExtractor
from pubmed_rag.run_pubmed import run as run_pubmed
from warehouse.project import project_run
from frontier_core.readiness import code_manifest, file_sha256

OUT=ROOT/'evidence'/'fault_injection'
RUNS=OUT/'runs'
RUNS.mkdir(parents=True,exist_ok=True)

SAMPLE = {
 "protocolSection": {
  "identificationModule": {"nctId":"NCT04368728","briefTitle":"Test"},
  "statusModule": {"overallStatus":"COMPLETED","lastUpdateSubmitDate":"2024-01-02","lastUpdatePostDateStruct":{"date":"2024-01-05"}},
  "designModule": {"phases":["PHASE2","PHASE3"],"studyType":"INTERVENTIONAL","enrollmentInfo":{"count":10,"type":"ACTUAL"}},
  "conditionsModule": {"conditions":["COVID-19"]}
 },
 "hasResults": False
}

def ctg(nct):
    x=deepcopy(SAMPLE); x['protocolSection']['identificationModule']['nctId']=nct; return x

PUBMED_XML='''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>33301246</PMID><Article><ArticleTitle>Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine</ArticleTitle><Abstract><AbstractText>Mock transport fixture for network-path certification.</AbstractText></Abstract><Journal><JournalIssue><PubDate><Year>2020</Year><Month>Dec</Month><Day>31</Day></PubDate></JournalIssue><Title>N Engl J Med</Title></Journal></Article></MedlineCitation><PubmedData><PublicationStatus>ppublish</PublicationStatus><ArticleIdList><ArticleId IdType="pubmed">33301246</ArticleId><ArticleId IdType="doi">10.1056/NEJMoa2034577</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''

PREPRINT_ROWS=[]
for i in range(35):
    PREPRINT_ROWS.append({
        'title':f'Fixture paper {i}','authors':'A, A.; B, B.','author_corresponding':'A A',
        'author_corresponding_institution':'Fixture University','doi':f'10.1101/fixture.{i:04d}',
        'date':'2026-08-28','version':'1','type':'new results','license':'cc_by','category':'medicine',
        'jatsxml':f'https://example.invalid/{i}.xml','abstract':f'Fixture abstract {i}','funder':'NA','published':'NA','server':'medRxiv'
    })

class State:
    ctg_fail_second=True
    ctg_page2_attempts=0
    pubmed_esearch_attempts=0
    preprint_page0_attempts=0
    requests=[]
STATE=State()

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args): pass
    def _send(self, status, body:bytes, ctype='application/json', extra=None):
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body)))
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body); self.wfile.flush()
    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query)
        STATE.requests.append({'path':u.path,'query':q,'ts':time.time()})
        if u.path=='/ctg/version':
            self._send(200,json.dumps({'apiVersion':'2.0.5','dataTimestamp':'2026-08-28T09:00:06'}).encode()); return
        if u.path=='/ctg/studies':
            token=(q.get('pageToken') or [None])[0]
            if token is None:
                body={'studies':[ctg('NCT04368728'),ctg('NCT00000002')],'nextPageToken':'p2','totalCount':3}
                self._send(200,json.dumps(body).encode()); return
            if token=='p2':
                STATE.ctg_page2_attempts += 1
                if STATE.ctg_fail_second:
                    self._send(503,b'{"error":"injected crash"}',extra={'Retry-After':'0'}); return
                self._send(200,json.dumps({'studies':[ctg('NCT00000003')],'totalCount':3}).encode()); return
        if u.path=='/pubmed/esearch':
            STATE.pubmed_esearch_attempts += 1
            if STATE.pubmed_esearch_attempts==1:
                self._send(429,b'{"error":"rate"}',extra={'Retry-After':'0'}); return
            body={'esearchresult':{'count':'1','retmax':'1','retstart':'0','idlist':['33301246']}}
            self._send(200,json.dumps(body).encode()); return
        if u.path=='/pubmed/efetch':
            self._send(200,PUBMED_XML.encode(),'application/xml'); return
        if u.path.startswith('/details/medrxiv/'):
            cursor=int(u.path.rstrip('/').split('/')[-1])
            if cursor==0:
                STATE.preprint_page0_attempts += 1
                if STATE.preprint_page0_attempts==1:
                    self._send(429,b'{"error":"rate"}',extra={'Retry-After':'0'}); return
                rows=PREPRINT_ROWS[:30]
            elif cursor==30: rows=PREPRINT_ROWS[30:]
            else: rows=[]
            body={'messages':[{'status':'ok','cursor':str(cursor),'count':len(rows),'total':'35'}],'collection':rows}
            self._send(200,json.dumps(body).encode()); return
        self._send(404,b'{}')

class RewriteSession(requests.Session):
    def __init__(self, base, kind): super().__init__(); self.base=base; self.kind=kind
    def get(self,url,*args,**kwargs):
        params=kwargs.pop('params',None)
        if self.kind=='ctg':
            if url.rstrip('/').endswith('/version'): target=self.base+'/ctg/version'
            elif '/studies' in url: target=self.base+'/ctg/studies'
            else: target=url
        elif self.kind=='pubmed':
            target=self.base+('/pubmed/esearch' if 'esearch.fcgi' in url else '/pubmed/efetch')
        else: target=url
        return super().get(target,*args,params=params,**kwargs)

def sha(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def atomic(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    if RUNS.exists(): shutil.rmtree(RUNS)
    RUNS.mkdir(parents=True)
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler); port=srv.server_address[1]; base=f'http://127.0.0.1:{port}'
    th=threading.Thread(target=srv.serve_forever,daemon=True); th.start()
    report={'evidence_schema_version':'frontier-local-http-certification-1.0','production_code_manifest_sha256':code_manifest(ROOT)['sha256'],'public_source_native_canary':False,'mass_unlock_eligible':False,'base':base,'gates':[]}
    def gate(name, passed, detail): report['gates'].append({'gate':name,'passed':bool(passed),'detail':detail}); assert passed, f'{name}: {detail}'
    try:
        # CTG: actual requests -> localhost, hard failure after committed first page, then resume.
        ctg_dir=RUNS/'ctg'
        raw=[]
        def hook(url,meta,payload): raw.append({'url':url,'meta':meta,'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)})
        sess1=RewriteSession(base,'ctg')
        cli1=ClinicalTrialsClient(session=sess1,rate_per_sec=1000,max_retries=1,sleeper=lambda _:None,raw_response_hook=hook)
        ex1=MassExtractor(ExtractionConfig(ctg_dir,page_size=2),client=cli1)
        failed=False
        try: ex1.run()
        except requests.HTTPError: failed=True
        gate('ctg_forced_interruption_after_page1',failed and (ctg_dir/'checkpoint.json').exists() and (ctg_dir/'commits/00000000.json').exists(),'page 0 durable; checkpoint retained after injected 503')
        cp=json.loads((ctg_dir/'checkpoint.json').read_text())
        gate('ctg_checkpoint_points_to_page2',cp.get('next_page_index')==1 and cp.get('next_page_token')=='p2',str(cp))
        STATE.ctg_fail_second=False
        sess2=RewriteSession(base,'ctg')
        cli2=ClinicalTrialsClient(session=sess2,rate_per_sec=1000,max_retries=2,sleeper=lambda _:None,raw_response_hook=hook)
        result=MassExtractor(ExtractionConfig(ctg_dir,page_size=2),client=cli2).run()
        rows=[json.loads(x) for x in (ctg_dir/'canonical/studies_canonical.jsonl').read_text().splitlines() if x.strip()]
        gate('ctg_resume_exactly_once',result.get('records')==3 and len(rows)==3 and len({r['nct_id'] for r in rows})==3 and not (ctg_dir/'checkpoint.json').exists(),f"records={result.get('records')} ids={[r['nct_id'] for r in rows]}")
        wm=project_run('ctg',ctg_dir,ctg_dir/'warehouse')
        gate('ctg_warehouse_projection_after_resume',wm.get('validation_status')=='PASS',str(wm.get('validation_errors')))
        gate('ctg_http_transport_hook_exercised',len(raw)>=4,f'{len(raw)} successful HTTP responses captured by client hook')

        # Preprint: actual requests to localhost, injected 429, 30+5+empty pagination.
        pp_dir=RUNS/'medrxiv'
        def pp_fetch(cfg,metadata=None):
            local=PreprintFetchConfig(server=cfg.server,start_date=cfg.start_date,end_date=cfg.end_date,contact_email=cfg.contact_email,rate_limit_sec=0,max_retries=3,timeout=3,api_base=base)
            return fetch_interval(local,metadata=metadata)
        pm=run_preprint('medrxiv','2026-08-28','2026-08-28',str(pp_dir),'test@example.org',allow_network=True,fetcher=pp_fetch)
        gate('preprint_short_page_not_eof',pm.get('observed_records')==35 and pm.get('unique_records')==35,f"observed={pm.get('observed_records')}")
        gate('preprint_429_retry_exercised',STATE.preprint_page0_attempts>=2,f'attempts={STATE.preprint_page0_attempts}')
        pwm=project_run('medrxiv',pp_dir,pp_dir/'warehouse')
        gate('preprint_warehouse_projection',pwm.get('validation_status')=='PASS',str(pwm.get('validation_errors')))

        # PubMed: actual requests to localhost, first ESearch 429, then EFetch XML, full run + warehouse.
        pub_dir=RUNS/'pubmed'
        def factory():
            cfg=RateLimitConfig(email='test@example.org',max_retries=3,base_delay=0.001,with_key_delay=0.001)
            return PubMedSourceExtractor(RateLimitedPubMedClient(cfg,session=RewriteSession(base,'pubmed')))
        pub=run_pubmed(out_dir=pub_dir,email='test@example.org',api_key=None,mindate='2020/01/01',maxdate='2020/12/31',queries=['33301246[PMID]'],allow_network=True,extractor_factory=factory)
        gate('pubmed_429_retry_exercised',STATE.pubmed_esearch_attempts>=3,f'esearch attempts={STATE.pubmed_esearch_attempts} (count + retrieval with one injected 429)')
        gate('pubmed_esearch_efetch_reconciled',pub.get('valid_records')==1 and pub.get('complete_against_source') is True,f"valid={pub.get('valid_records')} complete={pub.get('complete_against_source')}")
        pfile=pub_dir/'canonical/pubmed_records.jsonl'; prow=json.loads(pfile.read_text().splitlines()[0])
        gate('pubmed_raw_xml_hash_present',len(str(prow.get('source_record_sha256') or ''))==64 and '33301246' in (prow.get('raw_xml') or ''),'raw XML + source SHA retained')
        pubwm=project_run('pubmed',pub_dir,pub_dir/'warehouse')
        gate('pubmed_warehouse_projection',pubwm.get('validation_status')=='PASS',str(pubwm.get('validation_errors')))

        report['request_count']=len(STATE.requests); report['status']='PASS' if all(g['passed'] for g in report['gates']) else 'FAIL'
        report['notes']=[
            'All HTTP calls in this certification used the production requests-based clients against a controlled localhost fault-injection server.',
            'This is empirical network/retry/resume certification, but it is NOT a public-host native canary and cannot unlock mass extraction.',
            'Public-host native canaries remain blocked by runtime DNS.'
        ]
    finally:
        srv.shutdown(); srv.server_close()
    path=OUT/'LOCAL_HTTP_CERTIFICATION.json'; atomic(path,report)
    txt=['LOCAL HTTP FAULT-INJECTION CERTIFICATION: '+report['status'],f"PRODUCTION CODE SHA256: {report['production_code_manifest_sha256']}",'MASS UNLOCK ELIGIBLE: FALSE','']
    txt += [f"{'PASS' if g['passed'] else 'FAIL'} | {g['gate']} | {g['detail']}" for g in report['gates']]
    (OUT/'LOCAL_HTTP_CERTIFICATION.txt').write_text('\n'.join(txt)+'\n',encoding='utf-8')
    print('\n'.join(txt))

if __name__=='__main__': main()
