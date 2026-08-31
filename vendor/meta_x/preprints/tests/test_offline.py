import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.medrxiv_biorxiv.client import FetchConfig, build_url, fetch_interval, normalize_record, parse_interval
from src.medrxiv_biorxiv.parser import dedup_versions, latest_by_doi, validate_record
from src.pipeline import run_extraction

class Response:
    def __init__(self, payload, status=200, headers=None, raw=None):
        self.payload=payload; self.status_code=status; self.headers=headers or {}
        self.content = raw if raw is not None else json.dumps(payload,separators=(",",":")).encode()
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))
    def json(self): return self.payload
class Session:
    def __init__(self, payloads): self.payloads=list(payloads); self.urls=[]
    def get(self,url,headers=None,timeout=None): self.urls.append(url); return Response(self.payloads.pop(0))
    def close(self): pass

def rec(i, version="1"):
    return {"doi":f"10.1101/test{i}","server":"medrxiv","title":f"T{i}","abstract":"A", "version":version}

def test_pagination_does_not_assume_100_page_size():
    # Official hosts currently document different sizes (30 and 100). A short
    # first page must not be interpreted as EOF.
    s=Session([
        {"collection":[rec(i) for i in range(30)],"messages":[{"count":35,"cursor":0}]},
        {"collection":[rec(i) for i in range(30,35)],"messages":[{"count":35,"cursor":30}]},
        {"collection":[],"messages":[{"count":35,"cursor":35}]},
    ])
    cfg=FetchConfig("medrxiv","2024-01-01","2024-01-31",rate_limit_sec=0)
    rows=list(fetch_interval(cfg, session=s))
    assert len(rows)==35
    assert s.urls[1].endswith("/30") and s.urls[2].endswith("/35")

def test_version_history_and_latest_are_distinct():
    a=normalize_record({"doi":"10.1101/x","server":"medrxiv","title":"v1","version":"1"})
    b=normalize_record({"doi":"10.1101/x","server":"medrxiv","title":"v2","version":"2"})
    c=normalize_record({"doi":"10.1101/y","server":"medrxiv","title":"y","version":"1"})
    versions=dedup_versions([a,b,c,b])
    latest=latest_by_doi(versions)
    assert len(versions)==3
    assert len(latest)==2
    assert next(r for r in latest if r["doi"]=="10.1101/x")["title"]=="v2"

def test_dry_run_never_writes_synthetic_canonical_record(tmp_path):
    result=run_extraction("medrxiv","2024-01-01","2024-01-31",str(tmp_path),"",allow_network=False)
    assert result["status"]=="dry_run" and result["written"]==0
    assert not (tmp_path/"versions.jsonl").exists()

def test_pipeline_writes_raw_versions_and_latest(tmp_path):
    def fake_fetch(_cfg):
        yield normalize_record({"doi":"10.1101/x","server":"medrxiv","title":"v1","version":"1"})
        yield normalize_record({"doi":"10.1101/x","server":"medrxiv","title":"v2","version":"2"})
    result=run_extraction("medrxiv","2024-01-01","2024-01-31",str(tmp_path),"x@y",allow_network=True,fetcher=fake_fetch)
    assert result["unique_versions"]==2 and result["latest_unique_dois"]==1
    assert len((tmp_path/"versions.jsonl").read_text().splitlines())==2
    assert json.loads((tmp_path/"latest.jsonl").read_text())["version"]=="2"

def test_basic_contracts():
    assert parse_interval("2024-01-01","2024-01-31")=="2024-01-01/2024-01-31"
    assert build_url("medrxiv","2024-01-01/2024-01-31",30).endswith("/30")
    assert validate_record({"doi":"10.1101/x","server":"medrxiv","title":"x","version":"1"})==[]

def test_same_version_conflicting_content_fails_closed():
    from src.medrxiv_biorxiv.parser import dedup_versions
    a={"server":"medrxiv","doi":"10.1/x","version":"1","source_record_sha256":"aaa"}
    b={"server":"medrxiv","doi":"10.1/x","version":"1","source_record_sha256":"bbb"}
    try:
        dedup_versions([a,b])
        assert False, "expected conflict"
    except ValueError as e:
        assert "conflicting content" in str(e)


def test_invalid_records_are_quarantined_not_canonical(tmp_path):
    from src.pipeline import run_extraction
    def fetcher(cfg):
        yield {"server":"medrxiv","doi":"not-a-doi","version":"1","title":"bad","source_record_sha256":"a"*64}
        yield {"server":"medrxiv","doi":"10.1101/good","version":"1","title":"good","source_record_sha256":"b"*64}
    m=run_extraction("medrxiv","2026-01-01","2026-01-02",str(tmp_path),"",allow_network=True,fetcher=fetcher)
    assert m["records_quarantined"] == 1
    assert m["certification_status"] == "WARN"
    assert len((tmp_path/"versions.jsonl").read_text().splitlines()) == 1
    assert (tmp_path/"quarantine/invalid_records.jsonl").exists()


def test_sharded_root_manifest_chains_shard_manifests(tmp_path):
    from src.run_all import run_all
    from src.medrxiv_biorxiv.storage import atomic_write_json, atomic_write_jsonl

    def runner(server, start, end, out_dir, contact_email, allow_network=False):
        out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
        row = normalize_record({"doi": f"10.1101/{start}", "server": server, "title": start, "version": "1"})
        atomic_write_jsonl(out / "versions.jsonl", [row])
        manifest = {
            "run_id": f"run-{start}", "status": "completed", "certification_status": "PASS",
            "expected_records": 1, "observed_records": 1, "valid_records": 1,
            "records_quarantined": 0, "complete_against_source": True, "truncated": False,
            "transport_capture_status": "PASS_EXACT_HTTP_RESPONSES", "transport_response_count": 1,
        }
        atomic_write_json(out / "manifest.json", manifest)
        return manifest

    m = run_all("medrxiv", "2026-01-01", "2026-02-02", str(tmp_path), "", allow_network=True, runner=runner)
    assert m["certification_status"] == "PASS"
    assert m["shard_count"] == 2
    assert m["expected_records"] == 2 == m["observed_records"]
    assert all(x["manifest_sha256"] for x in m["shard_manifest_chain"])
    assert (tmp_path / "manifest.json").exists()


def test_preprint_client_transport_hook_preserves_exact_response_bytes():
    raw=b'{"messages":[{"total":1}],"collection":[{"doi":"10.1101/x","server":"medrxiv","title":"x","version":"1"}]}'
    empty=b'{"messages":[{"total":1}],"collection":[]}'
    s=Session([])
    s.payloads=[Response(json.loads(raw),raw=raw),Response(json.loads(empty),raw=empty)]
    def get(url,headers=None,timeout=None):
        s.urls.append(url); return s.payloads.pop(0)
    s.get=get
    captured=[]; meta={}
    cfg=FetchConfig('medrxiv','2026-01-01','2026-01-01',rate_limit_sec=0)
    rows=list(fetch_interval(cfg,session=s,metadata=meta,raw_response_hook=lambda u,m,b: captured.append((u,m,b))))
    assert len(rows)==1 and meta['eof_observed'] is True
    assert [x[2] for x in captured]==[raw,empty]
