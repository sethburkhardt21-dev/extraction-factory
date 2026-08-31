import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canonical.clinicaltrials.models import parse_study
from canonical.clinicaltrials.extractor import ExtractionConfig, MassExtractor
from canonical.clinicaltrials.client import ApiVersionInfo

SAMPLE = {
 "protocolSection": {
  "identificationModule": {"nctId":"NCT04368728","briefTitle":"Test"},
  "statusModule": {"overallStatus":"COMPLETED","lastUpdateSubmitDate":"2024-01-02","lastUpdatePostDateStruct":{"date":"2024-01-05"}},
  "designModule": {"phases":["PHASE2","PHASE3"],"studyType":"INTERVENTIONAL","enrollmentInfo":{"count":10,"type":"ACTUAL"}},
  "conditionsModule": {"conditions":["COVID-19"]}
 },
 "hasResults": False
}

def test_parser_preserves_phases_and_false():
    s=parse_study(SAMPLE)
    assert s.phase == ["PHASE2","PHASE3"]
    assert s.has_results is False
    assert s.last_update_post_date == "2024-01-05"

class FakeClient:
    def __init__(self): self.calls=0
    def fetch_version(self): return ApiVersionInfo("2.0.5","2026-08-28T09:00:06",{})
    def fetch_page(self, token, cfg):
        self.calls += 1
        if token is None: return {"studies":[SAMPLE],"nextPageToken":"next","totalCount":2}
        other=json.loads(json.dumps(SAMPLE)); other["protocolSection"]["identificationModule"]["nctId"]="NCT00000002"
        return {"studies":[other],"totalCount":2}

def test_paginated_checkpoint_and_finalize(tmp_path):
    ex=MassExtractor(ExtractionConfig(tmp_path, page_size=1000), client=FakeClient())
    result=ex.run()
    assert result["records"] == 2
    assert result["complete_against_total"] is True
    assert not (tmp_path/"checkpoint.json").exists()
    lines=(tmp_path/"canonical/studies_canonical.jsonl").read_text().splitlines()
    assert len(lines)==2

def test_resume_discards_orphan_page_after_crash(tmp_path):
    # Simulate page 0 being written but process dying before checkpoint. Without
    # reconciliation, a restart can treat its IDs as seen and overwrite it empty.
    ex=MassExtractor(ExtractionConfig(tmp_path, page_size=1000), client=FakeClient())
    ex._write_page_atomic(ex.raw_pages/"00000000.jsonl", [SAMPLE])
    ex._write_page_atomic(ex.canon_pages/"00000000.jsonl", [parse_study(SAMPLE).to_dict(False)])
    result=ex.run()
    assert result["records"] == 2
    rows=[json.loads(x) for x in (tmp_path/"canonical/studies_canonical.jsonl").read_text().splitlines()]
    assert {r["nct_id"] for r in rows} == {"NCT04368728","NCT00000002"}


def test_checkpoint_query_fingerprint_prevents_cross_query_resume(tmp_path):
    a=MassExtractor(ExtractionConfig(tmp_path, query="AREA[Condition]cancer"), client=FakeClient())
    a._save_checkpoint(next_page_token="x", next_page_index=1)
    b=MassExtractor(ExtractionConfig(tmp_path, query="AREA[Condition]Alzheimer"), client=FakeClient())
    try:
        b.run()
        assert False, "expected mismatched checkpoint rejection"
    except RuntimeError as e:
        assert "different query" in str(e)


def test_source_drift_is_visible_and_not_certified_pass(tmp_path):
    class DriftClient(FakeClient):
        def __init__(self): super().__init__(); self.version_calls=0
        def fetch_version(self):
            self.version_calls += 1
            ts="2026-08-28T09:00:06" if self.version_calls==1 else "2026-08-29T09:00:00"
            return ApiVersionInfo("2.0.5",ts,{})
    result=MassExtractor(ExtractionConfig(tmp_path), client=DriftClient()).run()
    assert result["source_changed_during_run"] is True
    assert result["snapshot_consistent"] is False
    assert result["certification_status"] == "WARN"


def test_canonical_rows_include_source_provenance(tmp_path):
    MassExtractor(ExtractionConfig(tmp_path), client=FakeClient()).run()
    row=json.loads((tmp_path/"canonical/studies_canonical.jsonl").read_text().splitlines()[0])
    assert len(row["source_record_sha256"]) == 64
    assert row["source_data_timestamp"] == "2026-08-28T09:00:06"
    assert row["source_api_version"] == "2.0.5"
    assert row["parser_version"].startswith("ctg-canonical-")


def test_storage_ddl_matches_canonical_provenance_fields():
    from canonical.clinicaltrials.storage import generate_bigquery_ddl, generate_postgres_ddl
    for ddl in (generate_bigquery_ddl(), generate_postgres_ddl()):
        for field in ("source_record_sha256","source_data_timestamp","source_api_version","parser_version","last_update_post_date"):
            assert field in ddl

def test_paginated_max_is_explicitly_truncated_even_without_next_token(tmp_path):
    class OnePageClient(FakeClient):
        def fetch_page(self, token, cfg):
            other=json.loads(json.dumps(SAMPLE)); other["protocolSection"]["identificationModule"]["nctId"]="NCT00000002"
            return {"studies":[SAMPLE, other], "totalCount":2}
    result=MassExtractor(ExtractionConfig(tmp_path, max_studies=1), client=OnePageClient()).run()
    assert result["records"] == 1
    assert result["expected_total"] == 2
    assert result["truncated_by_max"] is True
    assert result["certification_status"] == "TRUNCATED"
    assert result["complete_against_total"] is False
    assert not (tmp_path/"checkpoint.json").exists()


def test_checkpoint_identity_includes_max_studies(tmp_path):
    a=MassExtractor(ExtractionConfig(tmp_path, max_studies=5), client=FakeClient())
    a._save_checkpoint(next_page_token="x", next_page_index=1)
    b=MassExtractor(ExtractionConfig(tmp_path, max_studies=10), client=FakeClient())
    try:
        b.run()
        assert False, "expected mismatched checkpoint rejection"
    except RuntimeError as e:
        assert "different query" in str(e)


def test_bulk_zip_is_parsed_and_count_certified(tmp_path):
    import zipfile
    class BulkClient(FakeClient):
        def download_bulk(self, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            other=json.loads(json.dumps(SAMPLE)); other["protocolSection"]["identificationModule"]["nctId"]="NCT00000002"
            with zipfile.ZipFile(output_path, "w") as zf:
                zf.writestr("a/NCT04368728.json", json.dumps(SAMPLE))
                zf.writestr("b/NCT00000002.json", json.dumps(other))
            return output_path
    result=MassExtractor(ExtractionConfig(tmp_path, use_bulk=True), client=BulkClient()).run()
    assert result["method"] == "bulk_json_zip"
    assert result["records"] == 2
    assert result["expected_total"] == 2
    assert result["bulk_archive_json_files"] == 2
    assert result["complete_against_total"] is True
    assert result["certification_status"] == "PASS"
    assert len(result["bulk_zip_sha256"]) == 64


def _seed_committed_checkpoint(tmp_path, *, data_timestamp="2026-08-28T09:00:06"):
    ex=MassExtractor(ExtractionConfig(tmp_path), client=FakeClient())
    source_version=ApiVersionInfo("2.0.5",data_timestamp,{})
    parsed=parse_study(SAMPLE)
    row,prov=ex._canonical_and_provenance(SAMPLE,parsed,source_version,"seed-run","2026-08-28T10:00:00Z")
    ex._commit_page(0,[SAMPLE],[row],[],[prov],next_page_token="next")
    ex._save_checkpoint(
        run_id="seed-run", next_page_token="next", next_page_index=1,
        expected_total=2, observed_records=1, valid_records=1, quarantined_records=0,
        data_timestamp_start=data_timestamp, api_version_start="2.0.5",
    )
    return ex


def test_resume_rejects_source_revision_change_since_checkpoint(tmp_path):
    _seed_committed_checkpoint(tmp_path)
    class NewRevisionClient(FakeClient):
        def fetch_version(self):
            return ApiVersionInfo("2.0.5","2026-08-29T09:00:00",{})
    import pytest
    with pytest.raises(RuntimeError, match="dataTimestamp changed since checkpoint"):
        MassExtractor(ExtractionConfig(tmp_path),client=NewRevisionClient()).run()


def test_resume_detects_tampered_committed_page(tmp_path):
    ex=_seed_committed_checkpoint(tmp_path)
    (ex.raw_pages/"00000000.jsonl").write_text('{"tampered":true}\n')
    import pytest
    with pytest.raises(RuntimeError, match="committed page integrity failure"):
        MassExtractor(ExtractionConfig(tmp_path),client=FakeClient()).run()


def test_invalid_source_record_is_quarantined_and_blocks_pass(tmp_path):
    class InvalidClient(FakeClient):
        def fetch_page(self, token, cfg):
            return {"studies":[{"protocolSection": {}}],"totalCount":1}
    result=MassExtractor(ExtractionConfig(tmp_path),client=InvalidClient()).run()
    assert result["observed_records"]==1
    assert result["valid_records"]==0
    assert result["quarantined_records"]==1
    assert result["certification_status"]=="WARN"
    q=json.loads((tmp_path/"quarantine/invalid_records.jsonl").read_text())
    assert "missing NCTId" in q["error"]
    assert q["raw"]["protocolSection"]=={}


def test_lossless_projection_retains_high_value_and_future_sections():
    rich=json.loads(json.dumps(SAMPLE))
    p=rich["protocolSection"]
    p["identificationModule"].update({"acronym":"TEST","nctIdAliases":["NCTALIAS"]})
    p["armsInterventionsModule"]={
        "armGroups":[{"label":"Arm A","type":"EXPERIMENTAL"}],
        "interventions":[{"type":"DRUG","name":"Example","armGroupLabels":["Arm A"]}],
    }
    p["outcomesModule"]={
        "primaryOutcomes":[{"measure":"Primary"}],
        "secondaryOutcomes":[{"measure":"Secondary"}],
        "otherOutcomes":[{"measure":"Exploratory"}],
    }
    p["referencesModule"]={
        "references":[{"pmid":"123456","type":"BACKGROUND"}],
        "seeAlsoLinks":[{"label":"Protocol","url":"https://example.org"}],
        "availIpds":[{"type":"STUDY_PROTOCOL","url":"https://example.org/protocol"}],
    }
    p["ipdSharingStatementModule"]={"ipdSharing":"YES","description":"Available"}
    rich["resultsSection"]={"participantFlowModule":{"groups":[]}}
    rich["annotationSection"]={"annotationModule":{"unpostedAnnotation":{"unpostedResponsibleParty":"x"}}}
    rich["documentSection"]={"largeDocumentModule":{"largeDocs":[]}}
    rich["derivedSection"]={"miscInfoModule":{"versionHolder":"2026"}}
    rec=parse_study(rich)
    assert rec.acronym=="TEST" and rec.nct_id_aliases==["NCTALIAS"]
    assert rec.arms[0]["label"]=="Arm A"
    assert rec.other_outcomes[0]["measure"]=="Exploratory"
    assert rec.references[0]["pmid"]=="123456"
    assert rec.available_ipds[0]["type"]=="STUDY_PROTOCOL"
    assert rec.ipd_sharing["ipdSharing"]=="YES"
    assert rec.results_section and rec.annotation_section and rec.document_section and rec.derived_section


def test_bulk_malformed_member_preserves_lossless_bytes_in_quarantine(tmp_path):
    import base64, hashlib, zipfile
    bad=b'{"protocolSection": invalid json}'
    class BulkClient(FakeClient):
        def download_bulk(self, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(output_path,"w") as zf:
                zf.writestr("bad.json",bad)
            return output_path
    result=MassExtractor(ExtractionConfig(tmp_path,use_bulk=True),client=BulkClient()).run()
    assert result["quarantined_records"]==1
    assert result["certification_status"]=="WARN"
    q=json.loads((tmp_path/"quarantine/invalid_records.jsonl").read_text())
    assert base64.b64decode(q["raw_base64"])==bad
    assert q["source_record_sha256"]==hashlib.sha256(bad).hexdigest()


def test_cli_network_locked_without_explicit_flag(tmp_path):
    import subprocess, sys
    root=Path(__file__).resolve().parents[1]
    proc=subprocess.run(
        [sys.executable, 'canonical/run_extraction.py', '--output', str(tmp_path/'run')],
        cwd=root, text=True, capture_output=True,
    )
    assert proc.returncode == 2
    assert 'network extraction is locked' in proc.stderr


def test_cli_save_ddl_is_offline_safe(tmp_path):
    import subprocess, sys
    root=Path(__file__).resolve().parents[1]
    proc=subprocess.run(
        [sys.executable, 'canonical/run_extraction.py', '--save-ddl', '--output', str(tmp_path/'run')],
        cwd=root, text=True, capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path/'run/ddl/bigquery_studies.sql').exists()


def test_client_raw_response_hook_preserves_exact_bytes():
    from canonical.clinicaltrials.client import ClinicalTrialsClient
    payload=b'{"studies":[],"totalCount":0}'
    class Resp:
        status_code=200
        headers={"Content-Type":"application/json"}
        content=payload
        text=payload.decode()
        def raise_for_status(self): pass
        def json(self): return json.loads(self.content)
    class Sess:
        headers={}
        def get(self,url,params=None,timeout=None,stream=False): return Resp()
    captured=[]
    c=ClinicalTrialsClient(session=Sess(),rate_per_sec=1000,sleeper=lambda _:None,raw_response_hook=lambda u,m,b: captured.append((u,m,b)))
    out=c.fetch_page()
    assert out["totalCount"]==0
    assert captured[0][2] is payload or captured[0][2]==payload
    assert captured[0][1]["params"]["pageSize"]==1000


def test_committed_page_transport_hash_is_verified(tmp_path):
    ex=MassExtractor(ExtractionConfig(tmp_path),client=FakeClient())
    transport=tmp_path/'raw/transport/00000000_studies_page.json'
    transport.parent.mkdir(parents=True,exist_ok=True); transport.write_bytes(b'{}')
    row,prov=ex._canonical_and_provenance(SAMPLE,parse_study(SAMPLE),ApiVersionInfo('2.0.5','x',{}),'r','t','raw/transport/00000000_studies_page.json')
    ex._commit_page(0,[SAMPLE],[row],[],[prov],next_page_token=None,transport_raw_locator='raw/transport/00000000_studies_page.json')
    transport.write_bytes(b'{"tampered":true}')
    import pytest
    with pytest.raises(RuntimeError,match='transport integrity failure'):
        ex._verify_committed_pages(1)
