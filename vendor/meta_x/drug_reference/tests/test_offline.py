import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent))
from drugref.drugbank import iter_drugs
from drugref.rxnorm import RxNormClient, read_prefetched
from drugref.livertox import read_prefetched as read_livertox
from drugref.linker import link

XML='''<?xml version="1.0"?><drugbank xmlns="http://www.drugbank.ca"><drug updated="2024-01-01"><drugbank-id primary="true">DB00001</drugbank-id><name>Alpha Drug</name><groups><group>approved</group></groups><synonyms><synonym>Alpha</synonym></synonyms></drug><drug><drugbank-id primary="true">DB00002</drugbank-id><name>Beta Drug</name></drug></drugbank>'''
class Resp:
    status_code=200; headers={}
    def raise_for_status(self): pass
    def json(self): return {"idGroup":{"rxnormId":["12345"]}}
class Session:
    def get(self,*a,**k): return Resp()

def test_streaming_drugbank(tmp_path):
    p=tmp_path/'db.xml'; p.write_text(XML)
    rows=list(iter_drugs(str(p)))
    assert [r['drugbank_id'] for r in rows]==['DB00001','DB00002']
    assert rows[0]['synonyms']==['Alpha']

def test_rxnorm_uses_returned_identifier_not_python_hash():
    row=RxNormClient(session=Session()).resolve_name('Alpha Drug')
    assert row['rxcui']=='12345' and row['resolution_status']=='unique'
    assert row['source_payload']=={'idGroup':{'rxnormId':['12345']}}
    from drugref.common import stable_hash
    assert row['source_record_sha256']==stable_hash(row['source_payload'])

def test_prefetched_sources_fail_closed(tmp_path):
    rx=tmp_path/'rx.jsonl'; rx.write_text(json.dumps({'name':'Alpha Drug','rxcui':'not-real'})+'\n')
    try: list(read_prefetched(str(rx))); assert False
    except ValueError: pass
    lt=tmp_path/'lt.jsonl'; lt.write_text(json.dumps({'name':'Alpha Drug','livertox_likelihood':'A'})+'\n')
    try: list(read_livertox(str(lt))); assert False
    except ValueError: pass

def test_linker_does_not_guess_ambiguous_match():
    db=[{'name':'Alpha Drug','drugbank_id':'DB00001'}]
    rx=[{'name':'Alpha Drug','rxcui':'1'},{'name':'alpha drug','rxcui':'2'}]
    out=link(db,rx,[])[0]
    assert out['rxnorm'] is None and out['linkage']['rxnorm_status']=='ambiguous'

def test_drugbank_hash_covers_record_content(tmp_path):
    p=tmp_path/'a.xml'; p.write_text(XML)
    first=list(iter_drugs(str(p)))[0]['source_record_sha256']
    p.write_text(XML.replace('<name>Alpha Drug</name>','<name>Alpha Drug</name><description>changed</description>'))
    second=list(iter_drugs(str(p)))[0]['source_record_sha256']
    assert first != second


def test_linker_can_use_drugbank_synonym_without_guessing():
    db=[{'name':'Alpha Drug','synonyms':['Alpha'],'drugbank_id':'DB00001'}]
    rx=[{'name':'Alpha','rxcui':'1','source_record_sha256':'a'}]
    out=link(db,rx,[])[0]
    assert out['rxnorm']['rxcui']=='1'
    assert out['linkage']['rxnorm_status']=='matched'


def _write_valid_drug_inputs(tmp_path):
    from drugref.common import sha256_file, stable_hash
    db=tmp_path/'db.xml'; db.write_text(XML)
    rx_payload={'idGroup':{'rxnormId':['12345']}}
    rx_row={'name':'Alpha Drug','rxcui':'12345','source_payload':rx_payload,
            'source_record_sha256':stable_hash(rx_payload),'retrieved_at':'2026-08-29T12:00:00Z'}
    rx=tmp_path/'rx.jsonl'; rx.write_text(json.dumps(rx_row)+'\n')
    lt_text='LiverTox source capture for Alpha Drug; NBK548561; likelihood A.'
    lt_row={'name':'Alpha Drug','source_nbk_id':'NBK548561','livertox_likelihood':'A',
            'source_text':lt_text,'source_record_sha256':stable_hash(lt_text),
            'retrieved_at':'2026-08-29T12:00:00Z'}
    lt=tmp_path/'lt.jsonl'; lt.write_text(json.dumps(lt_row)+'\n')
    manifests={
        db:{'source':'drugbank','certification_status':'PASS','canonical_sha256':sha256_file(db),
            'source_release':'test-release-2024-01'},
        rx:{'source':'rxnorm','certification_status':'PASS','canonical_sha256':sha256_file(rx),
            'source_snapshot_timestamp':'2026-08-29T12:00:00Z'},
        lt:{'source':'livertox','certification_status':'PASS','canonical_sha256':sha256_file(lt),
            'source_snapshot_timestamp':'2026-08-29T12:00:00Z'},
    }
    for path, manifest in manifests.items():
        Path(str(path)+'.manifest.json').write_text(json.dumps(manifest))
    return db,rx,lt


def test_pipeline_requires_certified_sidecars_by_default(tmp_path):
    from drugref.pipeline import run
    db=tmp_path/'db.xml'; db.write_text(XML)
    rx=tmp_path/'rx.jsonl'; rx.write_text(json.dumps({'name':'Alpha Drug','rxcui':'12345'})+'\n')
    lt=tmp_path/'lt.jsonl'; lt.write_text(json.dumps({'name':'Alpha Drug','source_nbk_id':'NBK548561'})+'\n')
    import pytest
    with pytest.raises(ValueError, match='certified sidecar manifest required'):
        run(str(db),str(rx),str(lt),str(tmp_path/'out.jsonl'))


def test_pipeline_rejects_sidecar_hash_mismatch(tmp_path):
    from drugref.pipeline import run
    db,rx,lt=_write_valid_drug_inputs(tmp_path)
    mp=Path(str(rx)+'.manifest.json')
    m=json.loads(mp.read_text()); m['canonical_sha256']='0'*64; mp.write_text(json.dumps(m))
    import pytest
    with pytest.raises(ValueError, match='input hash mismatch'):
        run(str(db),str(rx),str(lt),str(tmp_path/'out.jsonl'))


def test_pipeline_accepts_hash_pinned_inputs_and_emits_provenance(tmp_path):
    from drugref.pipeline import run
    db,rx,lt=_write_valid_drug_inputs(tmp_path)
    out=tmp_path/'out.jsonl'
    m=run(str(db),str(rx),str(lt),str(out))
    assert m['network_extraction_performed'] is False
    assert m['input_manifests']['drugbank']['certification_status']=='PASS'
    assert m['input_manifests']['rxnorm']['certification_status']=='PASS'
    assert m['canonical_sha256']
    assert Path(str(out)+'.provenance.jsonl').exists()
    assert all((out.parent / v['path']).exists() for v in m['source_artifacts'].values())
    assert all(not Path(v['path']).is_absolute() for v in m['source_artifacts'].values())


def test_allow_unverified_inputs_is_explicit_dev_escape_hatch(tmp_path):
    from drugref.pipeline import run
    db=tmp_path/'db.xml'; db.write_text(XML)
    rx=tmp_path/'rx.jsonl'; rx.write_text(json.dumps({'name':'Alpha Drug','rxcui':'12345'})+'\n')
    lt=tmp_path/'lt.jsonl'; lt.write_text(json.dumps({'name':'Alpha Drug','source_nbk_id':'NBK548561'})+'\n')
    m=run(str(db),str(rx),str(lt),str(tmp_path/'out.jsonl'),require_certified_inputs=False)
    assert m['input_manifests']=={'drugbank':None,'rxnorm':None,'livertox':None}


def test_ambiguous_linkage_retains_candidate_identities():
    db=[{'name':'Alpha Drug','drugbank_id':'DB00001'}]
    rx=[{'name':'Alpha Drug','rxcui':'1'},{'name':'alpha drug','rxcui':'2'}]
    out=link(db,rx,[])[0]
    assert out['linkage']['rxnorm_status']=='ambiguous'
    assert out['linkage']['rxnorm_candidate_ids']==['rxnorm:1','rxnorm:2']


def test_pipeline_rejects_rxnorm_without_retained_api_payload(tmp_path):
    from drugref.pipeline import run
    from drugref.common import sha256_file
    import pytest
    db,rx,lt=_write_valid_drug_inputs(tmp_path)
    rx.write_text(json.dumps({'name':'Alpha Drug','rxcui':'12345','source_record_sha256':'0'*64})+'\n')
    mp=Path(str(rx)+'.manifest.json'); m=json.loads(mp.read_text()); m['canonical_sha256']=sha256_file(rx); mp.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='lacks retained source_payload'):
        run(str(db),str(rx),str(lt),str(tmp_path/'out.jsonl'))

def test_pipeline_rejects_livertox_without_lossless_capture(tmp_path):
    from drugref.pipeline import run
    from drugref.common import sha256_file
    import pytest
    db,rx,lt=_write_valid_drug_inputs(tmp_path)
    lt.write_text(json.dumps({'name':'Alpha Drug','source_nbk_id':'NBK548561','source_record_sha256':'0'*64})+'\n')
    mp=Path(str(lt)+'.manifest.json'); m=json.loads(mp.read_text()); m['canonical_sha256']=sha256_file(lt); mp.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='lacks retained source payload/text or pinned snapshot'):
        run(str(db),str(rx),str(lt),str(tmp_path/'out.jsonl'))

def test_drugbank_production_manifest_requires_release_version(tmp_path):
    from drugref.pipeline import run
    import pytest
    db,rx,lt=_write_valid_drug_inputs(tmp_path)
    mp=Path(str(db)+'.manifest.json'); m=json.loads(mp.read_text()); m.pop('source_release'); m['retrieved_at']='2026-08-29T12:00:00Z'; mp.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='must pin the licensed source release/version'):
        run(str(db),str(rx),str(lt),str(tmp_path/'out.jsonl'))

def test_pipeline_manifest_pins_required_raw_inputs(tmp_path):
    from drugref.pipeline import run
    from drugref.common import sha256_file
    db,rx,lt=_write_valid_drug_inputs(tmp_path)
    out=tmp_path/'out.jsonl'; m=run(str(db),str(rx),str(lt),str(out))
    for key,path in [('drugbank',db),('rxnorm',rx),('livertox',lt)]:
        a=m['raw_input_artifacts'][key]
        assert a['sha256']==sha256_file(path)
        assert a['retention_required'] is True
        assert a['copied_into_output'] is False

def test_exact_cross_source_link_does_not_claim_calibrated_confidence():
    from drugref.linker import link
    db=[{'drugbank_id':'DB1','name':'Alpha Drug','name_normalized':'alpha drug','synonyms':[]}]
    rx=[{'rxcui':'1','name':'Alpha Drug','name_normalized':'alpha drug'}]
    lt=[]
    row=link(db,rx,lt)[0]
    assert row['linkage']['rxnorm_status']=='matched'
    assert row['linkage']['rxnorm_confidence'] is None
    assert row['linkage']['confidence_policy']=='UNSCORED_EXACT_CANDIDATE_LINK'
