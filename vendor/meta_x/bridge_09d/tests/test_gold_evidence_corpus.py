from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bridge_09d.assertions import validate_source_unit
from bridge_09d.source_units import (
    segment_jats_xml,
    segment_structured_json,
    segment_monograph_text,
    segment_pubmed_abstract,
    segment_clinicaltrials_evidence,
)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _jats(body: str, *, abstract: str = "", back: str = "") -> bytes:
    return (
        '<article xmlns:mml="http://www.w3.org/1998/Math/MathML" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">'
        f'<front><article-meta>{abstract}</article-meta></front>'
        f'<body>{body}</body><back>{back}</back></article>'
    ).encode('utf-8')


def _seg(xml: bytes, key: str = 'gold:jats'):
    return segment_jats_xml(
        xml_payload=xml,
        source_record_key=key,
        source_resource_id='GOLD:JATS',
        source_version_id='1',
        source_sha256=_sha(xml),
        publication_year=2026,
        edition_or_version='1',
        source_era='2026',
    )


def _texts(rows):
    return [r.get('content_text') for r in rows if r.get('content_text') is not None]


def test_gold_01_superscript_preserves_magnitude():
    x=_jats('<sec><title>Dose</title><p>Concentration was 10<sup>6</sup> cells/mL.</p></sec>')
    assert 'Concentration was 10^6 cells/mL.' in _texts(_seg(x))


def test_gold_02_negative_superscript_is_not_subtraction():
    x=_jats('<sec><p>Affinity was 10<sup>-6</sup> M.</p></sec>')
    assert 'Affinity was 10^-6 M.' in _texts(_seg(x))


def test_gold_03_subscript_preserved():
    x=_jats('<sec><p>H<sub>2</sub>O and PaCO<sub>2</sub> were recorded.</p></sec>')
    assert 'H_2O and PaCO_2 were recorded.' in _texts(_seg(x))


def test_gold_04_mathml_msup_preserved():
    x=_jats('<sec><p>Count <inline-formula><mml:math><mml:msup><mml:mn>10</mml:mn><mml:mn>6</mml:mn></mml:msup></mml:math></inline-formula> cells.</p></sec>')
    assert any('10^6 cells' in t for t in _texts(_seg(x)))


def test_gold_05_mathml_fraction_preserved():
    x=_jats('<sec><p>Ratio <inline-formula><mml:math><mml:mfrac><mml:mn>1</mml:mn><mml:mn>3</mml:mn></mml:mfrac></mml:math></inline-formula>.</p></sec>')
    assert any('(1)/(3)' in t for t in _texts(_seg(x)))


def test_gold_06_vulgar_fraction_not_compatibility_normalized():
    x=_jats('<sec><p>Administer 2½ tablets.</p></sec>')
    assert 'Administer 2½ tablets.' in _texts(_seg(x))


def test_gold_07_xref_boundary_does_not_fuse_tokens():
    x=_jats('<sec><p>Doses: <xref rid="t1">Table 1</xref>see below.</p></sec>')
    t=_texts(_seg(x))[0]
    assert 'Table 1 see' in t and 'Table 1see' not in t


def test_gold_08_nested_list_content_is_not_double_emitted():
    x=_jats('<sec><p>Steps:<list><list-item><p>Give 4 mg IV.</p></list-item><list-item><p>Repeat in 8 h.</p></list-item></list></p></sec>')
    ts=_texts(_seg(x))
    assert sum('Give 4 mg IV.' in t for t in ts)==1
    assert sum('Repeat in 8 h.' in t for t in ts)==1


def test_gold_09_section_title_is_evidence_and_context():
    x=_jats('<sec><title>Contraindications</title><p>Do not administer in condition X.</p></sec>')
    rows=_seg(x)
    title=[r for r in rows if r.get('content_text')=='Contraindications'][0]
    p=[r for r in rows if r.get('content_text')=='Do not administer in condition X.'][0]
    assert title['locator']['section_path']==['Contraindications']
    assert p['locator']['section_path']==['Contraindications']


def test_gold_10_nested_section_path_is_ordered():
    x=_jats('<sec><title>Results</title><sec><title>Hemodynamics</title><p>MAP decreased.</p></sec></sec>')
    p=[r for r in _seg(x) if r.get('content_text')=='MAP decreased.'][0]
    assert p['locator']['section_path']==['Results','Hemodynamics']


def test_gold_11_abstract_inside_fulltext_is_distinct_scope():
    x=_jats('<sec><p>Body.</p></sec>',abstract='<abstract><p>Abstract evidence.</p></abstract>')
    a=[r for r in _seg(x) if r.get('content_text')=='Abstract evidence.'][0]
    b=[r for r in _seg(x) if r.get('content_text')=='Body.'][0]
    assert a['source_scope']=='ABSTRACT_WITHIN_FULLTEXT'
    assert b['source_scope']=='FULL_TEXT'


def test_gold_12_back_matter_is_metadata_not_clinical_fulltext():
    x=_jats('<sec><p>Clinical body.</p></sec>',back='<ack><p>We thank the staff.</p></ack>')
    back=[r for r in _seg(x) if r.get('content_text')=='We thank the staff.'][0]
    assert back['source_scope']=='METADATA'


def test_gold_13_figure_caption_is_separate_figure_scope():
    x=_jats('<sec><fig id="f1"><caption><p>Kaplan-Meier survival curve.</p></caption></fig></sec>')
    r=[r for r in _seg(x) if 'Kaplan-Meier' in (r.get('content_text') or '')][0]
    assert r['source_scope']=='FIGURE' and r['unit_kind']=='FIGURE_CAPTION'


def test_gold_14_table_caption_is_table_scope():
    x=_jats('<sec><table-wrap><caption><p>Primary outcomes.</p></caption><table><tbody><tr><td>1</td></tr></tbody></table></table-wrap></sec>')
    r=[r for r in _seg(x) if r.get('content_text')=='Primary outcomes.'][0]
    assert r['source_scope']=='TABLE'


def test_gold_15_table_cell_has_column_header_context():
    x=_jats('<sec><table-wrap><table><thead><tr><th>Dose</th><th>Weight</th></tr></thead><tbody><tr><td>140 mg</td><td>70 kg</td></tr></tbody></table></table-wrap></sec>')
    dose=[r for r in _seg(x) if r.get('content_text')=='140 mg'][0]
    assert 'Dose' in dose['locator']['header_refs']
    assert dose['locator']['row_index']==0 and dose['locator']['col_index']==0


def test_gold_16_table_colspan_rowspan_are_retained():
    x=_jats('<sec><table-wrap><table><tbody><tr><td colspan="2" rowspan="3">Combined</td></tr></tbody></table></table-wrap></sec>')
    r=[r for r in _seg(x) if r.get('content_text')=='Combined'][0]
    assert r['locator']['colspan']==2 and r['locator']['rowspan']==3


def test_gold_17_unicode_micro_sign_survives_source_unit():
    x=_jats('<sec><p>Dose 5 µg/kg.</p></sec>')
    assert 'Dose 5 µg/kg.' in _texts(_seg(x))


def test_gold_18_empty_jats_paragraph_not_emitted():
    x=_jats('<sec><p>   </p><p>Real evidence.</p></sec>')
    assert _texts(_seg(x))==['Real evidence.']


def test_gold_19_source_unit_identity_changes_with_scope():
    x=_jats('<sec><p>Same text.</p></sec>')
    full=segment_jats_xml(xml_payload=x,source_record_key='gold:x',source_resource_id='RES:A',source_version_id='1',source_sha256=_sha(x),source_scope='FULL_TEXT')[0]
    other=segment_jats_xml(xml_payload=x,source_record_key='gold:x',source_resource_id='RES:A',source_version_id='1',source_sha256=_sha(x),source_scope='OTHER')[0]
    assert full['source_unit_id'] != other['source_unit_id']


def test_gold_20_source_unit_identity_changes_with_resource():
    x=_jats('<sec><p>Same text.</p></sec>')
    a=segment_jats_xml(xml_payload=x,source_record_key='gold:x',source_resource_id='RES:A',source_version_id='1',source_sha256=_sha(x))[0]
    b=segment_jats_xml(xml_payload=x,source_record_key='gold:x',source_resource_id='RES:B',source_version_id='1',source_sha256=_sha(x))[0]
    assert a['source_unit_id'] != b['source_unit_id']


def test_gold_21_structured_json_preserves_null_false_zero_empty_string():
    obj={'null':None,'false':False,'zero':0,'empty':''}
    rows=segment_structured_json(value=obj,source_record_key='gold:j',source_resource_id='NCT:G',source_version_id='1',source_sha256='a'*64)
    by={r['locator']['json_path']:r['content_json'] for r in rows}
    assert by['$.null'] is None and by['$.false'] is False and by['$.zero']==0 and by['$.empty']==''


def test_gold_22_structured_json_preserves_empty_containers():
    rows=segment_structured_json(value={'a':[],'b':{}},source_record_key='gold:j',source_resource_id='NCT:G',source_version_id='1',source_sha256='a'*64)
    by={r['locator']['json_path']:r['content_json'] for r in rows}
    assert by['$.a']==[] and by['$.b']=={}


def test_gold_23_structured_json_odd_key_uses_unambiguous_path():
    rows=segment_structured_json(value={'a.b':{'x y':7}},source_record_key='gold:j',source_resource_id='NCT:G',source_version_id='1',source_sha256='a'*64)
    assert rows[0]['locator']['json_path']=='$["a.b"]["x y"]'


def test_gold_24_structured_array_indices_preserved():
    rows=segment_structured_json(value={'phase':['P2','P3']},source_record_key='gold:j',source_resource_id='NCT:G',source_version_id='1',source_sha256='a'*64)
    by={r['locator']['json_path']:r['content_json'] for r in rows}
    assert by['$.phase[0]']=='P2' and by['$.phase[1]']=='P3'


def test_gold_25_clinicaltrials_boolean_and_null_are_exact_units():
    raw={'hasResults':False,'protocolSection':{'statusModule':{'whyStopped':None}}}
    rows=segment_clinicaltrials_evidence(raw_record=raw,source_record_key='ctg:G',source_resource_id='NCT:G',source_version_id='2026-01-01',source_sha256='b'*64,retrieved_year=2026)
    by={r['locator']['json_path']:r['content_json'] for r in rows}
    assert by['$.hasResults'] is False
    assert by['$.protocolSection.statusModule.whyStopped'] is None


def test_gold_26_monograph_crlf_and_whitespace_blank_lines_segment():
    text='First paragraph.\r\n\r\nSecond paragraph.\n   \nThird paragraph.'
    rows=segment_monograph_text(text=text,source_record_key='gold:m',source_resource_id='BOOK:G',source_version_id='1',source_sha256='c'*64)
    assert [r['content_text'] for r in rows]==['First paragraph.','Second paragraph.','Third paragraph.']


def test_gold_27_monograph_unicode_char_and_byte_offsets_are_exact():
    text='Dose 5 µg/kg.\n\nNext.'
    rows=segment_monograph_text(text=text,source_record_key='gold:m',source_resource_id='BOOK:G',source_version_id='1',source_sha256='c'*64)
    for r in rows:
        loc=r['locator']
        assert text[loc['char_start']:loc['char_end']]==r['content_text']
        assert len(text[:loc['char_start']].encode('utf-8'))==loc['utf8_byte_start']
        assert len(text[:loc['char_end']].encode('utf-8'))==loc['utf8_byte_end']


def test_gold_28_pubmed_abstract_sections_keep_labels_and_abstract_only_scope():
    record={'pmid':'1','version':'v1','source_record_sha256':'d'*64,'pub_date':{'parsed_date':'2024-01-01'},'abstract_sections':[{'label':'BACKGROUND','text':'Background text.'},{'label':'RESULTS','text':'Results text.'}]}
    rows=segment_pubmed_abstract(record=record,source_record_key='pubmed:1')
    assert [r['locator']['label'] for r in rows]==['BACKGROUND','RESULTS']
    assert {r['source_scope'] for r in rows}=={'ABSTRACT_ONLY'}
    assert {r['publication_year'] for r in rows}=={2024}


def test_gold_29_pubmed_missing_abstract_produces_no_fake_unit():
    record={'pmid':'1','version':'v1','source_record_sha256':'d'*64,'abstract':''}
    assert segment_pubmed_abstract(record=record,source_record_key='pubmed:1')==[]


def test_gold_30_every_emitted_unit_validates_against_v12_contract():
    x=_jats('<sec><title>Methods</title><p>Dose 4 mg IV.</p><table-wrap><table><tbody><tr><td>4 mg</td></tr></tbody></table></table-wrap></sec>',abstract='<abstract><p>Summary.</p></abstract>',back='<ack><p>Thanks.</p></ack>')
    rows=_seg(x)
    assert rows
    for row in rows:
        assert validate_source_unit(row)==[]
        assert row['source_unit_schema_version']=='frontier-source-unit-1.2'


def test_gold_31_wrong_jats_source_hash_fails_closed():
    x=_jats('<sec><p>Evidence.</p></sec>')
    with pytest.raises(ValueError,match='does not match'):
        segment_jats_xml(xml_payload=x,source_record_key='gold:x',source_resource_id='RES:A',source_version_id='1',source_sha256='0'*64)


def test_gold_32_non_jats_xml_fails_closed():
    with pytest.raises(ValueError,match='no JATS article'):
        segment_jats_xml(xml_payload=b'<root><p>Not JATS.</p></root>',source_record_key='gold:x',source_resource_id='RES:A',source_version_id='1')


def test_gold_33_oai_error_fails_closed():
    xml=b'<OAI-PMH><error code="cannotDisseminateFormat">not reusable</error></OAI-PMH>'
    with pytest.raises(ValueError,match='OAI error'):
        segment_jats_xml(xml_payload=xml,source_record_key='gold:x',source_resource_id='RES:A',source_version_id='1')


def test_gold_34_deterministic_jats_segmentation_replays_exact_ids():
    x=_jats('<sec><title>Results</title><p>MAP decreased by 10 mmHg.</p></sec>')
    a=_seg(x,'gold:replay'); b=_seg(x,'gold:replay')
    assert [r['source_unit_id'] for r in a]==[r['source_unit_id'] for r in b]
    assert [r['content_sha256'] for r in a]==[r['content_sha256'] for r in b]


def test_gold_35_deterministic_structured_segmentation_replays_exact_ids():
    kw=dict(source_record_key='gold:j',source_resource_id='NCT:G',source_version_id='1',source_sha256='e'*64)
    a=segment_structured_json(value={'b':2,'a':1},**kw); b=segment_structured_json(value={'a':1,'b':2},**kw)
    assert [(r['locator']['json_path'],r['source_unit_id']) for r in a]==[(r['locator']['json_path'],r['source_unit_id']) for r in b]


def test_gold_36_gold_inventory_is_deliberately_heterogeneous():
    manifest=Path(__file__).resolve().parents[2]/'evidence'/'turn4_6_gold'/'GOLD_CASE_MANIFEST.json'
    data=json.loads(manifest.read_text())
    assert data['case_count']>=36
    assert set(data['families']) >= {'JATS','STRUCTURED_JSON','MONOGRAPH','PUBMED_ABSTRACT','NEGATIVE_FAIL_CLOSED'}
    assert data['mass_extraction_authorized'] is False
