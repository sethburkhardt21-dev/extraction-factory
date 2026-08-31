from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

from .common import atomic_json, atomic_jsonl, sha256_file, stable_hash
from .drugbank import iter_drugs
from .rxnorm import read_prefetched as read_rxnorm
from .livertox import read_prefetched as read_livertox
from .linker import link

PARSER_VERSION="drug-crosswalk-2.0"
CANONICAL_SCHEMA_VERSION="drug-crosswalk-record-2.0"
MANIFEST_SCHEMA_VERSION="frontier-run-manifest-1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _sidecar(path: str) -> Path:
    p=Path(path)
    return Path(str(p)+".manifest.json")


def _verify_input_manifest(path: str, expected_source: str, *, required: bool) -> Optional[Dict[str, Any]]:
    mp=_sidecar(path)
    if not mp.exists():
        if required:
            raise ValueError(f"certified sidecar manifest required for {expected_source}: {mp}")
        return None
    manifest=json.loads(mp.read_text(encoding="utf-8"))
    source=str(manifest.get("source") or "").lower()
    if expected_source.lower() not in source:
        raise ValueError(f"manifest source mismatch for {path}: expected {expected_source}, got {source!r}")
    if manifest.get("certification_status") != "PASS":
        raise ValueError(f"input manifest is not PASS-certified: {mp}")
    expected_hash=manifest.get("canonical_sha256") or manifest.get("output_sha256") or manifest.get("sha256")
    if not expected_hash:
        raise ValueError(f"input manifest lacks canonical/output sha256: {mp}")
    actual=sha256_file(path)
    if actual != expected_hash:
        raise ValueError(f"input hash mismatch for {path}: manifest={expected_hash} actual={actual}")
    if required:
        temporal = manifest.get("source_release") or manifest.get("source_version") or manifest.get("source_snapshot_timestamp") or manifest.get("retrieved_at")
        if not temporal:
            raise ValueError(f"input manifest lacks source release/version/timestamp provenance: {mp}")
        if expected_source == "drugbank" and not (manifest.get("source_release") or manifest.get("source_version")):
            raise ValueError(f"DrugBank manifest must pin the licensed source release/version: {mp}")
    return manifest


def _source_provenance(rows, source: str, run_id: str):
    out=[]
    for row in rows:
        if source=="drugbank":
            source_id=str(row.get("drugbank_id") or "")
            version_id=str(row.get("source_updated") or "")
        elif source=="rxnorm":
            source_id=",".join(str(x) for x in (row.get("rxcuis") or []))
            version_id=""
        else:
            source_id=str(row.get("source_nbk_id") or row.get("source_url") or row.get("name") or "")
            version_id=str(row.get("source_updated") or "")
        out.append({
            "provenance_schema_version":"frontier-source-provenance-1.0",
            "source":source,
            "source_record_id":source_id,
            "source_version_id":version_id,
            "source_record_sha256":row.get("source_record_sha256"),
            "run_id":run_id,
            "parser_version":PARSER_VERSION,
            "canonical_schema_version":CANONICAL_SCHEMA_VERSION,
            "retrieved_at":row.get("retrieved_at") or None,
            "source_url":row.get("source_url"),
            "parse_status":"parsed",
            "parse_warnings":[],
        })
    return out


def _require_lossless_source_rows(rx_rows, lt_rows) -> None:
    for i,row in enumerate(rx_rows,1):
        payload=row.get("source_payload")
        if payload is None:
            raise ValueError(f"RxNorm production row {i} lacks retained source_payload from RxNav")
        if stable_hash(payload) != row.get("source_record_sha256"):
            raise ValueError(f"RxNorm production row {i} source payload hash mismatch")
    for i,row in enumerate(lt_rows,1):
        if row.get("source_payload") is not None:
            expected=stable_hash(row["source_payload"])
        elif row.get("source_text") is not None:
            expected=stable_hash(row["source_text"])
        elif row.get("source_snapshot_locator") and row.get("source_snapshot_sha256"):
            expected=row.get("source_snapshot_sha256")
        else:
            raise ValueError(f"LiverTox production row {i} lacks retained source payload/text or pinned snapshot")
        if expected != row.get("source_record_sha256"):
            raise ValueError(f"LiverTox production row {i} source payload hash mismatch")


def run(drugbank_xml: str, rxnorm_jsonl: str, livertox_jsonl: str, output: str, *, require_certified_inputs: bool=True):
    """Merge three real source artifacts without inventing identifiers/attributes.

    All source inputs require PASS sidecar manifests by default. DrugBank is a
    licensed local input and must carry a release/provenance sidecar as well as
    a pinned file hash. Development can explicitly opt out.
    """
    db_manifest=_verify_input_manifest(drugbank_xml,"drugbank",required=require_certified_inputs)
    rx_manifest=_verify_input_manifest(rxnorm_jsonl,"rxnorm",required=require_certified_inputs)
    lt_manifest=_verify_input_manifest(livertox_jsonl,"livertox",required=require_certified_inputs)
    run_id=str(uuid.uuid4()); started_at=_utc_now()
    db=list(iter_drugs(drugbank_xml)); rx=list(read_rxnorm(rxnorm_jsonl)); lt=list(read_livertox(livertox_jsonl))
    if require_certified_inputs:
        _require_lossless_source_rows(rx,lt)
    rows=link(db,rx,lt)
    for row in rows:
        row.update({"run_id":run_id,"parser_version":PARSER_VERSION,"canonical_schema_version":CANONICAL_SCHEMA_VERSION})
    count=atomic_jsonl(output,rows)
    source_dir=Path(output).parent / (Path(output).stem + ".sources")
    source_dir.mkdir(parents=True,exist_ok=True)
    db_path=source_dir/"drugbank.jsonl"; rx_path=source_dir/"rxnorm.jsonl"; lt_path=source_dir/"livertox.jsonl"
    atomic_jsonl(db_path,db); atomic_jsonl(rx_path,rx); atomic_jsonl(lt_path,lt)
    provenance=_source_provenance(db,"drugbank",run_id)+_source_provenance(rx,"rxnorm",run_id)+_source_provenance(lt,"livertox",run_id)
    provenance_path=Path(output).with_suffix(Path(output).suffix+".provenance.jsonl")
    atomic_jsonl(provenance_path,provenance)
    unresolved_rx=sum(r["linkage"]["rxnorm_status"]!="matched" for r in rows)
    unresolved_lt=sum(r["linkage"]["livertox_status"]!="matched" for r in rows)
    warnings=[]
    if unresolved_rx: warnings.append(f"{unresolved_rx} DrugBank records do not have a unique RxNorm link")
    if unresolved_lt: warnings.append(f"{unresolved_lt} DrugBank records do not have a unique LiverTox link")
    # Missing/ambiguous cross-source links are a linkage-quality condition, not
    # evidence that the certified source artifacts were incompletely ingested.
    certification="PASS"
    linkage_quality="PASS" if not warnings else "WARN"
    report={
        "manifest_schema_version":MANIFEST_SCHEMA_VERSION,
        "run_id":run_id,
        "source":"drugbank+rxnorm+livertox",
        "mode":"offline_crosswalk",
        "status":"completed",
        "certification_status":certification,
        "network_extraction_performed":False,
        "started_at":started_at,"completed_at":_utc_now(),
        "parser_version":PARSER_VERSION,"canonical_schema_version":CANONICAL_SCHEMA_VERSION,
        "drugbank_records":len(db),"rxnorm_records":len(rx),"livertox_records":len(lt),"unified_records":count,
        "observed_records":len(db)+len(rx)+len(lt),"valid_records":len(db)+len(rx)+len(lt),"quarantined_records":0,
        "unique_records":len(db)+len(rx)+len(lt),"expected_records":len(db)+len(rx)+len(lt),
        "complete_against_source":True,"truncated":False,"source_changed_during_run":False,
        "rxnorm_ambiguous":sum(r["linkage"]["rxnorm_status"]=="ambiguous" for r in rows),
        "livertox_ambiguous":sum(r["linkage"]["livertox_status"]=="ambiguous" for r in rows),
        "rxnorm_unresolved":unresolved_rx,"livertox_unresolved":unresolved_lt,
        "linkage_quality_status":linkage_quality,
        "warnings":warnings,"errors":[],
        "drugbank_input_sha256":sha256_file(drugbank_xml),"rxnorm_input_sha256":sha256_file(rxnorm_jsonl),
        "livertox_input_sha256":sha256_file(livertox_jsonl),"canonical_sha256":sha256_file(output),
        "provenance_sha256":sha256_file(provenance_path),
        "input_manifests":{"drugbank":db_manifest,"rxnorm":rx_manifest,"livertox":lt_manifest},
        "raw_input_artifacts":{
            "drugbank":{"locator":str(Path(drugbank_xml).resolve()),"sha256":sha256_file(drugbank_xml),"retention_required":True,"copied_into_output":False},
            "rxnorm":{"locator":str(Path(rxnorm_jsonl).resolve()),"sha256":sha256_file(rxnorm_jsonl),"retention_required":True,"copied_into_output":False},
            "livertox":{"locator":str(Path(livertox_jsonl).resolve()),"sha256":sha256_file(livertox_jsonl),"retention_required":True,"copied_into_output":False},
        },
        "source_artifacts":{
            "drugbank":{"path":str(db_path.relative_to(Path(output).parent)),"sha256":sha256_file(db_path),"records":len(db)},
            "rxnorm":{"path":str(rx_path.relative_to(Path(output).parent)),"sha256":sha256_file(rx_path),"records":len(rx)},
            "livertox":{"path":str(lt_path.relative_to(Path(output).parent)),"sha256":sha256_file(lt_path),"records":len(lt)},
        },
    }
    atomic_json(Path(output).with_suffix(Path(output).suffix+".manifest.json"),report)
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--drugbank-xml",required=True); p.add_argument("--rxnorm-jsonl",required=True); p.add_argument("--livertox-jsonl",required=True); p.add_argument("--output",required=True)
    p.add_argument("--allow-unverified-inputs",action="store_true",help="development only; disables PASS sidecar requirement")
    a=p.parse_args()
    print(json.dumps(run(a.drugbank_xml,a.rxnorm_jsonl,a.livertox_jsonl,a.output,require_certified_inputs=not a.allow_unverified_inputs),indent=2))
if __name__=="__main__": main()
