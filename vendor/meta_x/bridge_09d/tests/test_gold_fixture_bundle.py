from __future__ import annotations
import hashlib,json
from pathlib import Path
from bridge_09d.source_units import segment_jats_xml,segment_structured_json,segment_clinicaltrials_evidence,segment_monograph_text,segment_pubmed_abstract

FIX=Path(__file__).parent/'fixtures'/'gold_evidence'
EXP=json.loads((FIX/'EXPECTED.json').read_text(encoding='utf-8'))['fixtures']

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def jats(name):
 p=FIX/name; b=p.read_bytes()
 return segment_jats_xml(xml_payload=b,source_record_key='gold:'+name,source_resource_id='GOLD:'+name,source_version_id='1',source_sha256=sha(p),publication_year=2026,edition_or_version='1',source_era='2026')

def test_fixture_hashes_are_pinned():
 for name,e in EXP.items(): assert sha(FIX/name)==e['sha256']

def test_numeric_fixture_matches_hand_authored_expectations():
 rows=jats('clinical_numeric_markup.xml'); texts=[r.get('content_text') for r in rows]
 for t in EXP['clinical_numeric_markup.xml']['required_text']: assert t in texts
 assert set(EXP['clinical_numeric_markup.xml']['required_scopes']) <= {r['source_scope'] for r in rows}

def test_context_fixture_matches_hand_authored_expectations():
 rows=jats('context_structure.xml'); texts=[r.get('content_text') for r in rows if r.get('content_text')]
 e=EXP['context_structure.xml']
 for t in e['required_text']: assert t in texts
 for text,scope in e['required_scope_by_text'].items(): assert [r for r in rows if r.get('content_text')==text][0]['source_scope']==scope
 for needle,maxn in e['max_occurrences'].items(): assert sum(needle in t for t in texts)<=maxn

def test_table_figure_fixture_matches_hand_authored_expectations():
 rows=jats('tables_figures.xml'); e=EXP['tables_figures.xml']
 for text,scope in e['required_scope_by_text'].items(): assert [r for r in rows if r.get('content_text')==text][0]['source_scope']==scope
 dose=[r for r in rows if r.get('content_text')=='140 mg'][0]
 assert dose['locator']['row_index']==0 and dose['locator']['col_index']==0 and 'Dose' in dose['locator']['header_refs']
 comb=[r for r in rows if r.get('content_text')=='Combined cell'][0]
 assert comb['locator']['colspan']==2 and comb['locator']['rowspan']==2

def test_inline_boundary_fixture_matches_hand_authored_expectations():
 rows=jats('inline_boundaries.xml'); texts=[r.get('content_text') for r in rows if r.get('content_text')]; joined='\n'.join(texts); e=EXP['inline_boundaries.xml']
 for t in e['required_text']: assert t in texts
 for bad in e['forbidden_text']: assert bad not in joined

def test_clinicaltrials_fixture_matches_hand_authored_expectations():
 p=FIX/'clinicaltrials_edge.json'; obj=json.loads(p.read_text())
 rows=segment_clinicaltrials_evidence(raw_record=obj,source_record_key='ctg:GOLD',source_resource_id='NCT:GOLD',source_version_id='1',source_sha256=sha(p),retrieved_year=2026)
 by={r['locator']['json_path']:r['content_json'] for r in rows}
 for path,val in EXP['clinicaltrials_edge.json']['required_paths'].items(): assert by[path]==val

def test_odd_key_fixture_matches_hand_authored_expectations():
 p=FIX/'structured_odd_keys.json'; obj=json.loads(p.read_text())
 rows=segment_structured_json(value=obj,source_record_key='gold:odd',source_resource_id='JSON:GOLD',source_version_id='1',source_sha256=sha(p))
 by={r['locator']['json_path']:r['content_json'] for r in rows}
 for path,val in EXP['structured_odd_keys.json']['required_paths'].items(): assert by[path]==val

def test_monograph_fixture_matches_hand_authored_expectations():
 p=FIX/'monograph_crlf.txt'; text=p.read_text(encoding='utf-8',newline='')
 rows=segment_monograph_text(text=text,source_record_key='gold:m',source_resource_id='BOOK:GOLD',source_version_id='1',source_sha256=sha(p))
 assert [r['content_text'] for r in rows]==EXP['monograph_crlf.txt']['paragraphs']
 for r in rows:
  l=r['locator']; assert text[l['char_start']:l['char_end']]==r['content_text']; assert len(text[:l['char_start']].encode())==l['utf8_byte_start']; assert len(text[:l['char_end']].encode())==l['utf8_byte_end']

def test_pubmed_abstract_fixture_matches_hand_authored_expectations():
 p=FIX/'pubmed_abstract.json'; rec=json.loads(p.read_text())
 rows=segment_pubmed_abstract(record=rec,source_record_key='pubmed:GOLD1'); e=EXP['pubmed_abstract.json']
 assert [r['locator']['label'] for r in rows]==e['labels']; assert {r['source_scope'] for r in rows}=={e['scope']}; assert {r['publication_year'] for r in rows}=={e['publication_year']}
