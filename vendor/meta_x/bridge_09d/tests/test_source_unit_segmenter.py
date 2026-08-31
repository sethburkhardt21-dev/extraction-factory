import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pytest

from bridge_09d.source_units import (
    acquire_http_fulltext, acquire_pmc_oai_fulltext, acquire_preprint_jats, persist_fulltext_artifact, pmc_oai_getrecord_url, rights_decision,
    segment_artifact_jats, segment_jats_xml, segment_monograph_text, segment_pubmed_abstract,
    segment_structured_json, validate_fulltext_artifact,
)

JATS = b'''<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
 <front><article-meta><title-group><article-title>Example</article-title></title-group>
 <abstract><p>Abstract finding one.</p><p>Abstract finding two.</p></abstract></article-meta></front>
 <body>
  <sec><title>Methods</title><p>Adults received propofol 0.5 mg/kg IV.</p></sec>
  <sec><title>Results</title><p>Mean arterial pressure decreased.</p>
   <table-wrap><caption><p>Hemodynamic outcomes</p></caption><table><tbody><tr><th>Outcome</th><td>MAP</td><td>65 mmHg</td></tr></tbody></table></table-wrap>
   <fig><caption><p>Blood pressure over time</p></caption></fig>
  </sec>
 </body>
</article>'''

OAI = b'''<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><GetRecord><record><metadata>''' + JATS.split(b'?>',1)[1] + b'''</metadata></record></GetRecord></OAI-PMH>'''


def common_kwargs():
    import hashlib
    return dict(source_record_key='pubmed:33301246', source_resource_id='PMCID:123456', source_version_id='1', source_sha256=hashlib.sha256(JATS).hexdigest(), publication_year=2020, edition_or_version='1')


def test_jats_segmentation_is_deterministic_and_typed():
    a=segment_jats_xml(xml_payload=JATS,**common_kwargs())
    b=segment_jats_xml(xml_payload=JATS,**common_kwargs())
    assert [u['source_unit_id'] for u in a]==[u['source_unit_id'] for u in b]
    assert len({u['source_unit_id'] for u in a})==len(a)
    assert any(u['source_scope']=='FULL_TEXT' and '0.5 mg/kg' in (u.get('content_text') or '') for u in a)
    assert any(u['unit_kind']=='TABLE_CELL' and u['content_text']=='65 mmHg' for u in a)
    assert any(u['unit_kind']=='FIGURE_CAPTION' and 'Blood pressure' in u['content_text'] for u in a)
    assert all((u.get('metadata') or {}).get('segmenter_version') for u in a)


def test_pmc_oai_wrapper_yields_jats_units():
    kw=common_kwargs(); kw['source_sha256']=__import__('hashlib').sha256(OAI).hexdigest(); rows=segment_jats_xml(xml_payload=OAI,**kw)
    assert any('Abstract finding one.' in (u.get('content_text') or '') for u in rows)
    assert any('Mean arterial pressure decreased.' in (u.get('content_text') or '') for u in rows)


def test_pubmed_without_fulltext_is_explicit_abstract_only():
    rec={'pmid':'1','version':'1','source_record_sha256':'b'*64,'abstract_sections':[{'label':'BACKGROUND','text':'Background text.'},{'label':'RESULTS','text':'Result text.'}], 'pub_date':{'parsed_date':'2025-01-02'}}
    rows=segment_pubmed_abstract(record=rec,source_record_key='pubmed:1')
    assert len(rows)==2
    assert {u['source_scope'] for u in rows}=={'ABSTRACT_ONLY'}
    assert all((u['metadata'] or {}).get('fallback_reason')=='FULL_TEXT_NOT_PROVIDED' for u in rows)
    assert all(u['publication_year']==2025 for u in rows)


def test_structured_json_segmentation_has_canonical_leaf_paths():
    obj={'z':1,'protocolSection':{'designModule':{'phases':['PHASE2','PHASE3'],'enrollmentInfo':{'count':46969,'type':'ACTUAL'}}}}
    rows=segment_structured_json(value=obj,source_record_key='ctg:n',source_resource_id='NCT:n',source_version_id='v',source_sha256='c'*64)
    paths=[u['locator']['json_path'] for u in rows]
    assert '$.protocolSection.designModule.enrollmentInfo.count' in paths
    assert '$.protocolSection.designModule.phases[0]' in paths
    assert '$.protocolSection.designModule.phases[1]' in paths
    assert paths==[u['locator']['json_path'] for u in segment_structured_json(value=obj,source_record_key='ctg:n',source_resource_id='NCT:n',source_version_id='v',source_sha256='c'*64)]


def test_monograph_segmentation_preserves_exact_paragraph_substrings():
    text='First paragraph line 1.\nline 2.\n\nSecond paragraph.'
    rows=segment_monograph_text(text=text,source_record_key='lt:1',source_resource_id='NBK:1',source_version_id='v',source_sha256='d'*64)
    assert [u['content_text'] for u in rows]==['First paragraph line 1.\nline 2.','Second paragraph.']
    for u in rows:
        loc=u['locator']; assert text[loc['char_start']:loc['char_end']]==u['content_text']


def test_preprint_rights_keep_tdm_and_redistribution_separate():
    no_reuse=rights_decision(source='medrxiv',license_code='cc_no',basis_url='https://www.medrxiv.org/tdm')
    assert no_reuse['text_mining_allowed'] is True
    assert no_reuse['redistribution_status']=='PERMISSION_REQUIRED'
    assert no_reuse['commercial_reuse_allowed'] is False
    ccby=rights_decision(source='biorxiv',license_code='cc_by',basis_url='https://www.biorxiv.org/tdm')
    assert ccby['text_mining_allowed'] is True and ccby['commercial_reuse_allowed'] is True


def test_pmc_oai_url_uses_current_identifier_shape():
    url=pmc_oai_getrecord_url('PMC12124693')
    assert 'pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/' in url
    assert 'oai%3Apubmedcentral.nih.gov%3A12124693' in url
    assert 'metadataPrefix=pmc' in url


def test_http_acquisition_requires_network_and_preserves_exact_bytes(tmp_path):
    class H(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Type','application/xml'); self.send_header('Content-Length',str(len(JATS))); self.end_headers(); self.wfile.write(JATS)
    srv=ThreadingHTTPServer(('127.0.0.1',0),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{srv.server_address[1]}/article.xml'
    rights=rights_decision(source='pmc',pmc_oai_fulltext_returned=True,basis_url='local-fixture')
    try:
        with pytest.raises(RuntimeError,match='locked'):
            acquire_http_fulltext(url=url,output_path=tmp_path/'x.xml',source='pmc',source_resource_id='PMCID:1',source_version_id='1',rights=rights,allow_network=False)
        art=acquire_http_fulltext(url=url,output_path=tmp_path/'x.xml',source='pmc',source_resource_id='PMCID:1',source_version_id='1',rights=rights,allow_network=True,allow_local_test_host=True)
        assert (tmp_path/'x.xml').read_bytes()==JATS
        assert validate_fulltext_artifact(art,require_local_file=True)==[]
        rows=segment_artifact_jats(artifact=art,source_record_key='pubmed:1')
        assert rows and all(u['source_sha256']==art['artifact_sha256'] for u in rows)
    finally:
        srv.shutdown(); srv.server_close()


def test_tampered_fulltext_artifact_is_rejected(tmp_path):
    rights=rights_decision(source='pmc',pmc_oai_fulltext_returned=True)
    art=persist_fulltext_artifact(payload=JATS,output_path=tmp_path/'x.xml',source='pmc',source_resource_id='PMCID:1',source_version_id='1',source_url='https://pmc.ncbi.nlm.nih.gov/x',content_type='application/xml',rights=rights)
    (tmp_path/'x.xml').write_bytes(b'tampered')
    assert any('hash mismatch' in e for e in validate_fulltext_artifact(art,require_local_file=True))
    with pytest.raises(ValueError,match='hash mismatch'):
        segment_artifact_jats(artifact=art,source_record_key='pubmed:1')


def test_structured_json_literal_null_is_exactly_representable():
    rows=segment_structured_json(value={'a':None},source_record_key='ctg:null',source_resource_id='NCT:null',source_version_id='v',source_sha256='e'*64)
    assert len(rows)==1
    assert rows[0]['content_representation']=='JSON'
    assert rows[0]['content_json'] is None
    assert rows[0]['locator']['json_path']=='$.a'


def test_pmc_source_specific_acquirer_requires_real_jats_payload(tmp_path):
    class Resp:
        status_code=200; headers={'Content-Type':'application/xml'}; content=OAI
        def raise_for_status(self): pass
    class Sess:
        def get(self,*args,**kwargs): return Resp()
    art=acquire_pmc_oai_fulltext(pmcid='PMC12124693',output_path=tmp_path/'pmc.xml',source_version_id='1',allow_network=True,session=Sess())
    assert art['text_mining_allowed'] is True
    assert art['source_resource_id']=='PMCID:12124693'
    assert (tmp_path/'pmc.xml').read_bytes()==OAI

def test_pmc_source_specific_acquirer_rejects_oai_error(tmp_path):
    class Resp:
        status_code=200; headers={'Content-Type':'application/xml'}; content=b'<OAI-PMH><error code="cannotDisseminateFormat">no full text</error></OAI-PMH>'
        def raise_for_status(self): pass
    class Sess:
        def get(self,*args,**kwargs): return Resp()
    with pytest.raises(ValueError,match='OAI error'):
        acquire_pmc_oai_fulltext(pmcid='PMC12124693',output_path=tmp_path/'pmc.xml',source_version_id='1',allow_network=True,session=Sess())

def test_preprint_specific_acquirer_retains_no_reuse_separately_from_tdm(tmp_path):
    class Resp:
        status_code=200; headers={'Content-Type':'application/xml'}; content=JATS
        def raise_for_status(self): pass
    class Sess:
        def get(self,*args,**kwargs): return Resp()
    art=acquire_preprint_jats(jats_url='https://www.medrxiv.org/content/early/x.source.xml',server='medrxiv',doi='10.1101/x',version='2',license_code='cc_no',output_path=tmp_path/'m.xml',allow_network=True,session=Sess())
    assert art['text_mining_allowed'] is True
    assert art['redistribution_status']=='PERMISSION_REQUIRED'
    assert (tmp_path/'m.xml').read_bytes()==JATS


def test_pubmed_evidence_scope_switches_only_when_verified_fulltext_artifact_exists(tmp_path):
    from bridge_09d.source_units import segment_pubmed_evidence
    record={'pmid':'1','pmc_id':'PMC1','version':'1','source_record_sha256':'a'*64,'abstract':'Only abstract.','pub_date':{'parsed_date':'2020-01-01'}}
    abstract_units=segment_pubmed_evidence(record=record,source_record_key='pubmed:1')
    assert {u['source_scope'] for u in abstract_units}=={'ABSTRACT_ONLY'}
    rights=rights_decision(source='pmc',pmc_oai_fulltext_returned=True)
    art=persist_fulltext_artifact(payload=JATS,output_path=tmp_path/'f.xml',source='pmc',source_resource_id='PMCID:1',source_version_id='1',source_url='https://pmc.ncbi.nlm.nih.gov/f',content_type='application/xml',rights=rights)
    full_units=segment_pubmed_evidence(record=record,source_record_key='pubmed:1',fulltext_artifact=art)
    assert any(u['source_scope']=='FULL_TEXT' for u in full_units)
    assert all((u.get('metadata') or {}).get('fulltext_artifact_sha256')==art['artifact_sha256'] for u in full_units)


def test_preprint_without_jats_never_claims_fulltext():
    from bridge_09d.source_units import segment_preprint_evidence
    rec={'doi':'10.1101/x','version':'2','server':'medrxiv','date':'2025-01-01','abstract':'Preprint abstract.','source_record_sha256':'b'*64}
    units=segment_preprint_evidence(record=rec,source_record_key='medrxiv:10.1101/x:2')
    assert len(units)==1 and units[0]['source_scope']=='ABSTRACT_ONLY'


def test_clinicaltrials_wrapper_preserves_registry_scope_and_null():
    from bridge_09d.source_units import segment_clinicaltrials_evidence
    raw={'protocolSection':{'statusModule':{'whyStopped':None},'designModule':{'enrollmentInfo':{'count':10}}}}
    units=segment_clinicaltrials_evidence(raw_record=raw,source_record_key='ctg:NCT1',source_resource_id='NCT:NCT1',source_version_id='2025-01-01',source_sha256='c'*64,retrieved_year=2026)
    assert {u['source_scope'] for u in units}=={'REGISTRY_STRUCTURED'}
    null=[u for u in units if u['locator']['json_path'].endswith('whyStopped')][0]
    assert null['content_json'] is None and null['content_representation']=='JSON'


def test_jats_segmenter_rejects_wrong_source_hash():
    kw=common_kwargs(); kw['source_sha256']='0'*64
    with pytest.raises(ValueError,match='does not match'):
        segment_jats_xml(xml_payload=JATS,**kw)

ADVERSARIAL_JATS = b'''<article xmlns:mml="http://www.w3.org/1998/Math/MathML"><front><article-meta><abstract><p>Abstract 10<sup>6</sup> cells.</p></abstract></article-meta></front><body><sec><title>Contraindications</title><p>Give <bold>10</bold><sup>6</sup> CFU and H<sub>2</sub>O.</p><p>Math <inline-formula><mml:math><mml:msup><mml:mn>10</mml:mn><mml:mn>6</mml:mn></mml:msup></mml:math></inline-formula> cells.</p><p>Recommended steps:<list><list-item><p>Give 4 mg IV.</p></list-item><list-item><p>Repeat in 8 h.</p></list-item></list></p><table-wrap><table><thead><tr><th>Dose</th><th>Weight</th></tr></thead><tbody><tr><td>140 mg</td><td>70 kg</td></tr></tbody></table></table-wrap></sec></body><back><ack><p>We thank the nursing staff.</p></ack></back></article>'''


def test_jats_preserves_superscript_subscript_math_and_section_context():
    import hashlib
    rows=segment_jats_xml(xml_payload=ADVERSARIAL_JATS,source_record_key='pubmed:a',source_resource_id='PMCID:A',source_version_id='1',source_sha256=hashlib.sha256(ADVERSARIAL_JATS).hexdigest())
    texts=[u.get('content_text') for u in rows if u.get('content_text')]
    assert any('10^6 CFU' in t and 'H_2O' in t for t in texts)
    assert any('10^6 cells' in t for t in texts)
    title=[u for u in rows if u.get('content_text')=='Contraindications']
    assert title and title[0]['locator']['section_path']==['Contraindications']
    body=[u for u in rows if '10^6 CFU' in (u.get('content_text') or '')][0]
    assert body['locator']['section_path']==['Contraindications']
    assert (body['metadata'] or {}).get('normalized_xml_fragment_sha256')


def test_jats_nested_paragraphs_are_not_duplicated():
    import hashlib
    rows=segment_jats_xml(xml_payload=ADVERSARIAL_JATS,source_record_key='pubmed:a',source_resource_id='PMCID:A',source_version_id='1',source_sha256=hashlib.sha256(ADVERSARIAL_JATS).hexdigest())
    assert sum('Give 4 mg IV.' in (u.get('content_text') or '') for u in rows)==1
    assert sum('Repeat in 8 h.' in (u.get('content_text') or '') for u in rows)==1


def test_abstract_inside_fulltext_and_back_matter_have_distinct_scopes():
    import hashlib
    rows=segment_jats_xml(xml_payload=ADVERSARIAL_JATS,source_record_key='pubmed:a',source_resource_id='PMCID:A',source_version_id='1',source_sha256=hashlib.sha256(ADVERSARIAL_JATS).hexdigest())
    abstract=[u for u in rows if 'Abstract 10^6 cells.' in (u.get('content_text') or '')][0]
    back=[u for u in rows if 'We thank the nursing staff.' in (u.get('content_text') or '')][0]
    assert abstract['source_scope']=='ABSTRACT_WITHIN_FULLTEXT'
    assert back['source_scope']=='METADATA'


def test_table_cells_carry_row_column_and_header_context():
    import hashlib
    rows=segment_jats_xml(xml_payload=ADVERSARIAL_JATS,source_record_key='pubmed:a',source_resource_id='PMCID:A',source_version_id='1',source_sha256=hashlib.sha256(ADVERSARIAL_JATS).hexdigest())
    dose=[u for u in rows if u.get('content_text')=='140 mg'][0]
    assert dose['locator']['row_index']==0 and dose['locator']['col_index']==0
    assert 'Dose' in dose['locator']['header_refs']
    assert dose['locator']['colspan']==1 and dose['locator']['rowspan']==1


def test_html_content_type_and_localhost_fail_closed(tmp_path):
    class Resp:
        status_code=200; headers={'Content-Type':'text/html'}; content=b'<html>paywall</html>'
        def raise_for_status(self): pass
    class Sess:
        def get(self,*args,**kwargs): return Resp()
    rights=rights_decision(source='pmc',pmc_oai_fulltext_returned=True)
    with pytest.raises(RuntimeError,match='local test host'):
        acquire_http_fulltext(url='http://127.0.0.1/x',output_path=tmp_path/'x',source='pmc',source_resource_id='PMCID:1',source_version_id='1',rights=rights,allow_network=True,session=Sess())
    with pytest.raises(RuntimeError,match='content type'):
        acquire_http_fulltext(url='http://127.0.0.1/x',output_path=tmp_path/'x',source='pmc',source_resource_id='PMCID:1',source_version_id='1',rights=rights,allow_network=True,session=Sess(),allow_local_test_host=True)


def test_monograph_crlf_and_whitespace_blank_lines_preserve_offsets():
    text='Para one.\r\n\r\nPara two.\n   \nPara three µg.'
    rows=segment_monograph_text(text=text,source_record_key='lt:x',source_resource_id='NBK:x',source_version_id='1',source_sha256='a'*64)
    assert [u['content_text'] for u in rows]==['Para one.','Para two.','Para three µg.']
    for u in rows:
        loc=u['locator']; assert text[loc['char_start']:loc['char_end']]==u['content_text']
        assert len(text[:loc['char_start']].encode())==loc['utf8_byte_start']
        assert len(text[:loc['char_end']].encode())==loc['utf8_byte_end']


def test_structured_json_preserves_empty_containers_as_evidence():
    rows=segment_structured_json(value={'empty_list':[],'empty_obj':{}},source_record_key='ctg:e',source_resource_id='NCT:e',source_version_id='1',source_sha256='b'*64)
    by={u['locator']['json_path']:u['content_json'] for u in rows}
    assert by['$.empty_list']==[] and by['$.empty_obj']=={}


def test_pubmed_and_preprint_fulltext_identifier_binding(tmp_path):
    rights=rights_decision(source='pmc',pmc_oai_fulltext_returned=True)
    art=persist_fulltext_artifact(payload=JATS,output_path=tmp_path/'f.xml',source='pmc',source_resource_id='PMCID:1',source_version_id='1',source_url='https://pmc.ncbi.nlm.nih.gov/f',content_type='application/xml',rights=rights)
    from bridge_09d.source_units import segment_pubmed_evidence,segment_preprint_evidence
    with pytest.raises(ValueError,match='does not match'):
        segment_pubmed_evidence(record={'pmid':'1','pmc_id':'PMC2','source_record_sha256':'a'*64},source_record_key='pubmed:1',fulltext_artifact=art)
    part=persist_fulltext_artifact(payload=JATS,output_path=tmp_path/'p.xml',source='medrxiv',source_resource_id='DOI:10.1101/x',source_version_id='1',source_url='https://www.medrxiv.org/x',content_type='application/xml',rights=rights_decision(source='medrxiv',license_code='cc_by'))
    with pytest.raises(ValueError,match='does not match'):
        segment_preprint_evidence(record={'doi':'10.1101/y','version':'1','source_record_sha256':'b'*64},source_record_key='med:y',fulltext_artifact=part)
