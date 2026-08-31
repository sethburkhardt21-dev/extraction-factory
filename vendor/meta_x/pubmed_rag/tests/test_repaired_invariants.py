from pathlib import Path
import sys
import json
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def test_no_untrusted_generated_corpus_in_production_root():
    for name in [
        "anesthesia_corpus.jsonl","anesthesia_corpus_embedded.jsonl",
        "embeddings_2d.json","embeddings_meta.json","anesthesia_full_metadata_SAMPLE.jsonl"
    ]:
        assert not (ROOT/name).exists()
    rag=ROOT/"anesthesia_rag_pipeline"
    for name in ["deduped_corpus.jsonl","rag_test_results.json","pipeline_summary.json"]:
        assert not (rag/name).exists()


def test_legacy_parallel_stacks_are_not_active_production():
    archived=ROOT/"archive_not_production"/"legacy_parallel_stacks_2026-08-29"
    assert archived.exists()
    for name in [
        "pubmed_client.py", "pubmed_client_hardened.py", "ingestion_pipeline.py",
        "incremental_update_pipeline.py", "production_pipeline.py", "embedding_engine.py",
    ]:
        assert not (ROOT/name).exists(), name
    assert not (ROOT/"anesthesia_rag_pipeline").exists()


def test_canonical_pubmed_network_client_requires_contact_email():
    from pubmed_anesthesia_extraction import RateLimitConfig, RateLimitedPubMedClient
    with pytest.raises(ValueError, match="real contact email"):
        RateLimitedPubMedClient(RateLimitConfig(email=""))


def test_source_extraction_requirements_do_not_force_embedding_stack():
    req=(ROOT/"requirements.txt").read_text()
    assert "requests" in req and "pydantic" in req
    for token in ("sentence-transformers", "torch", "transformers", "faiss"):
        assert token not in req
    assert (ROOT/"requirements-enrichment.txt").exists()


def test_production_python_has_no_hardcoded_mnt_data_paths_or_fake_contacts():
    bad=[]
    for p in ROOT.rglob("*.py"):
        if "archive_not_production" in p.parts or "tests" in p.parts:
            continue
        text=p.read_text(errors="replace")
        for token in ("/mnt/data", "research@example.edu", "anesthesia.pipeline@example.com", "ragpipeline@example.com"):
            if token in text:
                bad.append((str(p.relative_to(ROOT)),token))
    assert not bad, bad


def test_pubmed_complete_search_partitions_over_10k_without_truncation():
    from datetime import datetime
    from pubmed_anesthesia_extraction import RateLimitedPubMedClient

    class FakeClient(RateLimitedPubMedClient):
        def __init__(self):
            self.by_day = {
                "2020/01/01": [str(i) for i in range(1, 3001)],
                "2020/01/02": [str(i) for i in range(3001, 6001)],
                "2020/01/03": [str(i) for i in range(6001, 9001)],
                "2020/01/04": [str(i) for i in range(9001, 12001)],
            }
        def esearch(self, query, retmax=10000, retstart=0, sort="relevance", mindate=None, maxdate=None):
            start=datetime.strptime(mindate, "%Y/%m/%d").date()
            end=datetime.strptime(maxdate, "%Y/%m/%d").date()
            ids=[]
            for d, vals in self.by_day.items():
                day=datetime.strptime(d, "%Y/%m/%d").date()
                if start <= day <= end:
                    ids.extend(vals)
            return {"count": str(len(ids)), "idlist": [] if retmax == 0 else ids[:retmax]}

    ids, meta = FakeClient().esearch_all(
        "anesthesia", mindate="2020/01/01", maxdate="2020/01/04"
    )
    assert len(ids) == 12000
    assert len(set(ids)) == 12000
    assert meta["truncated"] is False
    assert meta["segments"] >= 2


def test_pubmed_complete_search_fails_if_one_day_exceeds_10k():
    from pubmed_anesthesia_extraction import RateLimitedPubMedClient

    class FakeClient(RateLimitedPubMedClient):
        def __init__(self): pass
        def esearch(self, query, retmax=10000, retstart=0, sort="relevance", mindate=None, maxdate=None):
            return {"count": "10001", "idlist": []}

    with pytest.raises(RuntimeError, match="one day still exceeds"):
        FakeClient().esearch_all(
            "broad query", mindate="2020/01/01", maxdate="2020/01/01"
        )


def test_pubmed_capped_search_is_explicitly_truncated():
    from pubmed_anesthesia_extraction import RateLimitedPubMedClient

    class FakeClient(RateLimitedPubMedClient):
        def __init__(self): pass
        def esearch(self, query, retmax=10000, retstart=0, sort="relevance", mindate=None, maxdate=None):
            return {"count": "12000", "idlist": [str(i) for i in range(1, retmax + 1)] if retmax else []}

    ids, meta = FakeClient().esearch_all(
        "broad query", mindate="2020/01/01", maxdate="2020/12/31", max_ids=5000
    )
    assert len(ids) == 5000
    assert meta["expected_count"] == 12000
    assert meta["truncated"] is True


def test_pubmed_efetch_reconciliation_fails_closed(monkeypatch):
    from types import SimpleNamespace
    import pubmed_anesthesia_extraction as mod

    class FakeClient:
        def esearch_all(self, *args, **kwargs):
            return ["1", "2"], {"expected_count": 2, "retrieved_count": 2, "truncated": False}
        def efetch_xml(self, *args, **kwargs):
            return "<xml/>"

    monkeypatch.setattr(mod, "parse_pubmed_xml", lambda xml, **kwargs: [SimpleNamespace(pmid="1", doi=None, title="one")])
    extractor = mod.PubMedSourceExtractor(FakeClient())
    with pytest.raises(RuntimeError, match="EFetch reconciliation failed"):
        extractor.extract_max(
            query_overrides=["q"], mindate="2020/01/01", maxdate="2020/01/02",
                    )


def test_pubmed_parser_records_raw_xml_provenance_hash():
    import hashlib
    from pubmed_anesthesia_extraction import parse_pubmed_xml
    xml = '''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12345</PMID><Article><ArticleTitle>Test anesthesia record</ArticleTitle><Journal><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">12345</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''
    records = parse_pubmed_xml(xml)
    assert len(records) == 1
    rec = records[0]
    assert rec.raw_xml and "<PMID>12345</PMID>" in rec.raw_xml
    assert rec.source_record_sha256 == hashlib.sha256(rec.raw_xml.encode("utf-8")).hexdigest()
    assert rec.retrieved_at is not None


def test_pubmed_distinct_pmids_with_same_title_are_preserved(monkeypatch):
    from types import SimpleNamespace
    import pubmed_anesthesia_extraction as mod

    class FakeClient:
        def esearch_all(self, *args, **kwargs):
            return ["1", "2"], {"expected_count": 2, "retrieved_count": 2, "truncated": False}
        def efetch_xml(self, *args, **kwargs):
            return "<xml/>"

    recs = [
        SimpleNamespace(pmid="1", doi=None, title="Same title", retrieval_queries=[], retrieval_query=None, run_id=None),
        SimpleNamespace(pmid="2", doi=None, title="Same title", retrieval_queries=[], retrieval_query=None, run_id=None),
    ]
    monkeypatch.setattr(mod, "parse_pubmed_xml", lambda xml, **kwargs: recs)
    out = mod.PubMedSourceExtractor(FakeClient()).extract_max(
        query_overrides=["q"], mindate="2020/01/01", maxdate="2020/01/02"
    )
    assert [r.pmid for r in out] == ["1", "2"]

def test_pubmed_source_schema_contains_no_enrichment_state_and_preserves_metadata():
    from pubmed_anesthesia_extraction import parse_pubmed_xml
    xml = '''<PubmedArticleSet><PubmedArticle>
    <MedlineCitation><PMID>24680</PMID><Article>
      <ArticleTitle>Metadata preservation test</ArticleTitle>
      <Journal><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue></Journal>
      <AuthorList><Author><LastName>Smith</LastName><ForeName>Alex</ForeName>
        <AffiliationInfo><Affiliation>Department A</Affiliation></AffiliationInfo>
        <AffiliationInfo><Affiliation>Institute B</Affiliation></AffiliationInfo>
        <Identifier Source="ORCID">0000-0001-2345-6789</Identifier>
      </Author></AuthorList>
      <Language>eng</Language>
    </Article>
    <MeshHeadingList><MeshHeading><DescriptorName UI="D000001" MajorTopicYN="N">Anesthesia</DescriptorName>
      <QualifierName UI="Q1" MajorTopicYN="N">methods</QualifierName>
      <QualifierName UI="Q2" MajorTopicYN="Y">adverse effects</QualifierName>
    </MeshHeading></MeshHeadingList></MedlineCitation>
    <PubmedData><PublicationStatus>ppublish</PublicationStatus><ArticleIdList>
      <ArticleId IdType="pubmed">24680</ArticleId><ArticleId IdType="doi">10.1/example</ArticleId>
    </ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''
    [rec] = parse_pubmed_xml(xml)
    forbidden={'embedding_input_text','embedding_model','embedding_model_revision','embedding_dim','embedding_normalized','embedding_hash','embedding_vector','anesthesia_classification','anesthesia_subspecialty','dedup_key_title_norm','dedup_key_doi_norm','duplicate_of','is_duplicate'}
    assert forbidden.isdisjoint(set(type(rec).model_fields))
    assert rec.authors[0].affiliations == ["Department A", "Institute B"]
    assert rec.authors[0].identifiers["ORCID"] == "0000-0001-2345-6789"
    assert len(rec.mesh_headings[0].qualifiers) == 2
    assert rec.mesh_headings[0].major_topic is True
    assert rec.languages == ["eng"]
    assert rec.article_ids["doi"] == "10.1/example"
    assert rec.publication_status == "ppublish"


def test_pubmed_record_retains_all_queries_that_retrieved_it(monkeypatch):
    from types import SimpleNamespace
    import pubmed_anesthesia_extraction as mod

    class FakeClient:
        def esearch_all(self, query, **kwargs):
            ids = ["1", "2"] if query == "q1" else ["2", "3"]
            return ids, {"expected_count": len(ids), "retrieved_count": len(ids), "truncated": False}
        def efetch_xml(self, *args, **kwargs):
            return "<xml/>"

    def fake_parse(_xml):
        return [
            SimpleNamespace(
                pmid=x, doi=None, title=f"title {x}", retrieval_queries=[], retrieval_query=None, run_id=None
            ) for x in ["1", "2", "3"]
        ]

    monkeypatch.setattr(mod, "parse_pubmed_xml", lambda xml, **kwargs: fake_parse(xml))
    ext = mod.PubMedSourceExtractor(FakeClient())
    out = ext.extract_max(
        query_overrides=["q1", "q2"], mindate="2025/01/01", maxdate="2025/01/02",
            )
    by_id = {r.pmid: r for r in out}
    assert by_id["1"].retrieval_queries == ["q1"]
    assert by_id["2"].retrieval_queries == ["q1", "q2"]
    assert by_id["2"].retrieval_query is None
    assert by_id["3"].retrieval_queries == ["q2"]


def test_canonical_source_extractor_has_no_classifier_or_dedup_surface():
    import inspect
    import pubmed_anesthesia_extraction as mod
    sig=inspect.signature(mod.PubMedSourceExtractor.__init__)
    assert list(sig.parameters)==['self','client']
    source=inspect.getsource(mod.PubMedSourceExtractor)
    for token in ('classifier','embedding','DedupManager','duplicate_of'):
        assert token not in source

def test_pubmed_book_article_is_preserved_not_dropped():
    from pubmed_anesthesia_extraction import parse_pubmed_xml
    xml='''<PubmedArticleSet><PubmedBookArticle><BookDocument>
      <PMID Version="1">28230950</PMID><ArticleIdList><ArticleId IdType="bookaccession">NBK401702</ArticleId></ArticleIdList>
      <Book><Publisher><PublisherName>NICE</PublisherName><PublisherLocation>London</PublisherLocation></Publisher>
      <BookTitle>Good Practice Guidance</BookTitle><PubDate><Year>2013</Year><Month>05</Month><Day>07</Day></PubDate>
      <AuthorList Type="authors"><Author><CollectiveName>National Institute for Health and Care Excellence</CollectiveName></Author></AuthorList>
      <Isbn>9781473119086</Isbn></Book><Language>eng</Language>
      <Abstract><AbstractText>Book abstract.</AbstractText></Abstract>
      <KeywordList><Keyword>guidance</Keyword></KeywordList>
    </BookDocument><PubmedBookData><PublicationStatus>ppublish</PublicationStatus><ArticleIdList>
      <ArticleId IdType="pubmed">28230950</ArticleId></ArticleIdList></PubmedBookData></PubmedBookArticle></PubmedArticleSet>'''
    [rec]=parse_pubmed_xml(xml)
    assert rec.pmid=='28230950'
    assert rec.record_type=='book_article'
    assert rec.title=='Good Practice Guidance'
    assert rec.book_metadata['publisher_name']=='NICE'
    assert rec.authors[0].collective_name=='National Institute for Health and Care Excellence'
    assert rec.languages==['eng'] and rec.keywords==['guidance']
    assert rec.raw_xml and rec.source_record_sha256


def test_pubmed_cli_is_network_locked_by_default(tmp_path):
    from run_pubmed import run
    result=run(out_dir=tmp_path/'run',email='',api_key=None,mindate='2020/01/01',maxdate='2020/01/02',queries=['q'],allow_network=False)
    assert result['status']=='dry_run'
    assert result['certification_status']=='PENDING'
    assert result['network_extraction_performed'] is False
    assert not (tmp_path/'run').exists()


def test_pubmed_cli_writes_manifest_and_provenance_with_fake_extractor(tmp_path):
    from datetime import datetime, timezone
    from metadata_schema import PubMedRecordFull, PubDateModel
    from run_pubmed import run

    class FakeExtractor:
        def extract_max(self, **kwargs):
            rec=PubMedRecordFull(
                pmid='123', title='Source test', pub_date=PubDateModel(year=2024,month=1,day=1,date_source='PubDate'),
                run_id='00000000-0000-0000-0000-000000000123', source_url='https://pubmed.ncbi.nlm.nih.gov/123/',
                source_record_sha256='a'*64, retrieved_at=datetime.now(timezone.utc), raw_xml='<PubmedArticle />'
            )
            self.last_extraction_meta={
                'run_id':rec.run_id,'source':'pubmed','mode':'esearch_efetch_domain_candidates','status':'completed',
                'certification_status':'PASS','started_at':'2026-08-29T00:00:00Z','completed_at':'2026-08-29T00:00:01Z',
                'parser_version':'pubmed-canonical-3.0','canonical_schema_version':'pubmed-record-3.0',
                'observed_records':1,'valid_records':1,'unique_records':1,'truncated':False,'complete_against_source':True,
                'warnings':[],'errors':[],
            }
            return [rec]

    result=run(out_dir=tmp_path/'run',email='real@example.org',api_key=None,mindate='2024/01/01',maxdate='2024/01/02',queries=['q'],allow_network=True,extractor_factory=FakeExtractor)
    assert result['certification_status']=='PASS_TEST_INJECTED'
    assert result['network_extraction_performed'] is True
    assert len(result['canonical_sha256'])==64
    assert (tmp_path/'run/manifest.json').exists()
    assert (tmp_path/'run/raw/pubmed_source_records.jsonl').exists()
    assert (tmp_path/'run/provenance/source_records.jsonl').exists()
    assert (tmp_path/'run/raw/transport_index.jsonl').exists()
    assert result['transport_capture_status']=='TEST_INJECTED_NO_NATIVE_TRANSPORT_CAPTURE'
    raw=json.loads((tmp_path/'run/raw/pubmed_source_records.jsonl').read_text().splitlines()[0])
    assert raw['pmid']=='123' and raw['raw_xml']=='<PubmedArticle />'
    assert result['raw_sha256'] != result['canonical_sha256']


def test_pubmed_strict_parser_fails_closed_on_malformed_xml():
    from pubmed_anesthesia_extraction import parse_pubmed_xml
    import pytest
    malformed='<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID>'
    with pytest.raises(ValueError, match='XML document parse failed'):
        parse_pubmed_xml(malformed, strict=True)

def test_pubmed_non_strict_parser_can_quarantine_by_omission_for_tooling():
    from pubmed_anesthesia_extraction import parse_pubmed_xml
    malformed='<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID>'
    assert parse_pubmed_xml(malformed, strict=False)==[]


def test_pubmed_client_transport_hook_retains_exact_http_bytes_without_api_key():
    from pubmed_anesthesia_extraction import RateLimitConfig, RateLimitedPubMedClient
    captured=[]
    class Resp:
        status_code=200
        headers={'Content-Type':'application/json'}
        content=b'{"esearchresult":{"count":"1","idlist":["123"]}}'
        text=content.decode()
        def json(self): return json.loads(self.text)
        def raise_for_status(self): pass
    class Session:
        headers={}
        def get(self,*a,**k): return Resp()
    cfg=RateLimitConfig(email='real@example.org',api_key='SECRET',base_delay=0.001,with_key_delay=0.001)
    c=RateLimitedPubMedClient(cfg,raw_response_hook=lambda kind,meta,content: captured.append((kind,meta,content)),session=Session())
    result=c.esearch('x',retmax=1)
    assert result['idlist']==['123']
    assert captured[0][0]=='esearch' and captured[0][2]==Resp.content
    assert 'api_key' not in captured[0][1]['params']
    assert b'SECRET' not in captured[0][2]
