from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple
import uuid

WAREHOUSE_PROJECTION_VERSION = "frontier-warehouse-projection-1.0"
KEY_NAMESPACE = uuid.UUID("8a77fa1d-b934-4c8d-97e1-6e4f9d9d0f51")
VOLATILE_CANONICAL_FIELDS = {
    "run_id", "retrieved_at", "source", "source_url", "source_record_sha256",
    "source_data_timestamp", "source_api_version", "parser_version", "canonical_schema_version",
    "retrieval_query", "retrieval_queries",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_uuid(kind: str, *parts: Any) -> str:
    payload = "|".join([kind] + [str(x or "") for x in parts])
    return str(uuid.uuid5(KEY_NAMESPACE, payload))


def canonical_json_sha256(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _media_type(path: Path) -> str | None:
    suffixes="".join(path.suffixes).lower()
    if suffixes.endswith(".jsonl"): return "application/x-ndjson"
    if suffixes.endswith(".json"): return "application/json"
    if suffixes.endswith(".xml"): return "application/xml"
    if suffixes.endswith(".zip"): return "application/zip"
    if suffixes.endswith(".sql"): return "text/sql"
    return None


def _artifact_row(run_id: str, role: str, locator: str, sha256: str, *, path: Path | None=None, record_count: int | None=None, created_at: str | None=None, metadata: Dict[str, Any] | None=None) -> Dict[str, Any]:
    if len(str(sha256 or "")) != 64:
        raise ValueError(f"artifact lacks SHA-256: role={role} locator={locator}")
    return {
        "artifact_id": stable_uuid("run_artifact", run_id, role, locator, sha256),
        "run_id": run_id,
        "role": role,
        "locator": locator,
        "media_type": _media_type(path or Path(locator)),
        "sha256": sha256,
        "byte_size": path.stat().st_size if path is not None and path.is_file() else None,
        "record_count": record_count,
        "created_at": created_at or utc_now(),
        "metadata": metadata or {},
    }


def _resolve_artifact_path(run_dir: Path, locator: str) -> Path:
    p=Path(locator)
    if p.is_absolute():
        try:
            p.relative_to(run_dir)
        except ValueError:
            return p
        return p
    return run_dir/p


def _manifest_artifact_rows(manifest: Dict[str, Any], run_dir: Path, manifest_path: Path) -> List[Dict[str, Any]]:
    """Project cryptographically bound run artifacts, including exact HTTP payloads."""
    run_id=str(manifest["run_id"]); created=manifest.get("completed_at") or manifest.get("started_at") or utc_now()
    rows=[]; seen=set()
    def add(role: str, locator: str, sha: str | None=None, count: int | None=None, metadata: Dict[str, Any] | None=None):
        path=_resolve_artifact_path(run_dir,locator)
        if sha is None and path.is_file(): sha=sha256_file(path)
        if not sha: return
        key=(role,locator,sha)
        if key in seen: return
        seen.add(key)
        rows.append(_artifact_row(run_id,role,locator,str(sha),path=path if path.is_file() else None,record_count=count,created_at=created,metadata=metadata))

    add("source_manifest",str(manifest_path.relative_to(run_dir)),sha256_file(manifest_path),metadata={"manifest_schema_version":manifest.get("manifest_schema_version")})
    for role,spec in (manifest.get("artifacts") or {}).items():
        if isinstance(spec,str):
            add(str(role),spec,manifest.get(f"{role}_sha256"))
        elif isinstance(spec,dict) and spec.get("path"):
            locator=str(spec["path"]); path=Path(locator)
            if path.is_absolute():
                try: locator=str(path.relative_to(run_dir))
                except ValueError: locator=str(path)
            add(str(role),locator,spec.get("sha256"),spec.get("records"),{k:v for k,v in spec.items() if k not in {"path","sha256","records"}})
    transport_index=manifest.get("transport_index")
    if transport_index and not any(r[0]=="transport_index" for r in seen):
        add("transport_index",str(transport_index),manifest.get("transport_index_sha256"),manifest.get("transport_response_count"))
    bulk_sha=manifest.get("bulk_zip_sha256")
    if bulk_sha:
        add("raw_bulk_archive","bulk/studies.json.zip",bulk_sha,manifest.get("bulk_archive_json_files"))

    # Exact response payloads are individually promoted from the retained transport index.
    index_candidates=[]
    if transport_index:
        index_candidates.append(_resolve_artifact_path(run_dir,str(transport_index)))
    art=(manifest.get("artifacts") or {}).get("transport_index")
    if isinstance(art,dict) and art.get("path"):
        index_candidates.append(_resolve_artifact_path(run_dir,str(art["path"])))
    for idx_path in index_candidates:
        if not idx_path.is_file(): continue
        for entry in read_jsonl(idx_path):
            locator=str(entry.get("path") or "")
            sha=str(entry.get("sha256") or "")
            if locator and sha:
                add("raw_transport",locator,sha,None,{"kind":entry.get("kind"),"url":entry.get("url"),"request":entry.get("request")})

    # Aggregate preprint runs chain shard manifests/artifacts instead of flattening them away.
    for shard in manifest.get("shard_manifest_chain") or []:
        shard_rel=str(shard.get("path") or "")
        shard_manifest=run_dir/shard_rel/"manifest.json"
        if not shard_manifest.is_file(): continue
        sm=json.loads(shard_manifest.read_text(encoding="utf-8"))
        add("shard_manifest",str(shard_manifest.relative_to(run_dir)),sha256_file(shard_manifest),metadata={"shard_run_id":sm.get("run_id")})
        for child in _manifest_artifact_rows(sm,shard_manifest.parent,shard_manifest):
            child_locator=str((Path(shard_rel)/child["locator"]).as_posix()) if not Path(child["locator"]).is_absolute() else child["locator"]
            add("shard_"+child["role"],child_locator,child["sha256"],child.get("record_count"),{"shard_run_id":sm.get("run_id"),**(child.get("metadata") or {})})
    return rows


def _source_id_from_quarantine(row: Dict[str, Any]) -> str | None:
    for key in ("source_record_id","nct_id","pmid","doi"):
        if row.get(key): return str(row[key])
    raw=row.get("raw")
    if isinstance(raw,dict):
        ident=((raw.get("protocolSection") or {}).get("identificationModule") or {}).get("nctId")
        if ident: return str(ident)
        for key in ("pmid","doi"):
            if raw.get(key): return str(raw[key])
    return None


def _quarantine_rows(run_id: str, source: str, paths: Iterable[Path], *, root: Path) -> List[Dict[str, Any]]:
    out=[]
    for path in paths:
        if not path.is_file(): continue
        for ordinal,row in enumerate(read_jsonl(path)):
            raw=row.get("raw") if "raw" in row else row
            validation=row.get("_validation_errors")
            err_type=row.get("error_type") or ("ValidationError" if validation else "SourceParseError")
            err=row.get("error") or ("; ".join(map(str,validation)) if isinstance(validation,list) else str(validation or "quarantined source record"))
            sha=str(row.get("source_record_sha256") or "") or (canonical_json_sha256(raw) if raw is not None else None)
            rel=str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            out.append({
                "quarantine_id":stable_uuid("quarantine",run_id,rel,ordinal,sha or ""),
                "run_id":run_id,"source":source,"source_record_id":_source_id_from_quarantine(row),
                "source_record_sha256":sha,"archive_member":row.get("archive_name"),"raw_locator":f"{rel}#row={ordinal}",
                "raw_payload":raw if isinstance(raw,(dict,list)) else None,"raw_text":raw if isinstance(raw,str) else None,
                "raw_base64":row.get("raw_base64"),"error_type":str(err_type),"error_message":str(err),
                "quarantined_at":row.get("retrieved_at") or utc_now(),"metadata":{"source_run_id":row.get("run_id"),"validation_errors":validation},
            })
    return out


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{lineno}: JSONL row must be object")
            out.append(obj)
    return out


def atomic_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False, default=str) + "\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    return len(rows)


def atomic_json(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(obj), f, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _canonical_content(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if k not in VOLATILE_CANONICAL_FIELDS}


def _manifest_to_ingestion_run(manifest: Dict[str, Any]) -> Dict[str, Any]:
    required = ["run_id", "source", "mode", "parser_version", "canonical_schema_version", "manifest_schema_version"]
    missing = [k for k in required if not manifest.get(k)]
    if missing:
        raise ValueError(f"run manifest missing required fields: {missing}")
    return {
        "run_id": manifest["run_id"],
        "source": manifest["source"],
        "mode": manifest["mode"],
        "parser_version": manifest["parser_version"],
        "canonical_schema_version": manifest["canonical_schema_version"],
        "manifest_schema_version": manifest["manifest_schema_version"],
        "started_at": manifest.get("started_at") or utc_now(),
        "completed_at": manifest.get("completed_at"),
        "status": manifest.get("status", "completed"),
        "certification_status": manifest.get("certification_status", "PENDING"),
        "source_version_start": manifest.get("source_version_start") or manifest.get("data_timestamp_start"),
        "source_version_end": manifest.get("source_version_end") or manifest.get("data_timestamp_end"),
        "source_changed_during_run": manifest.get("source_changed_during_run"),
        "query": manifest.get("query"),
        "query_fingerprint": manifest.get("query_fingerprint"),
        "expected_records": manifest.get("expected_records", manifest.get("expected_total")),
        "observed_records": int(manifest.get("observed_records", 0) or 0),
        "valid_records": int(manifest.get("valid_records", manifest.get("records", 0)) or 0),
        "quarantined_records": int(manifest.get("quarantined_records", manifest.get("records_quarantined", 0)) or 0),
        "unique_records": int(manifest.get("unique_records", manifest.get("valid_records", 0)) or 0),
        "truncated": bool(manifest.get("truncated", manifest.get("truncated_by_max", False))),
        "complete_against_source": manifest.get("complete_against_source", manifest.get("complete_against_total")),
        "raw_sha256": manifest.get("raw_sha256"),
        "canonical_sha256": manifest.get("canonical_sha256"),
        "quarantine_sha256": manifest.get("quarantine_sha256"),
        "provenance_sha256": manifest.get("provenance_sha256"),
        "warnings": manifest.get("warnings") or [],
        "errors": manifest.get("errors") or [],
        "artifacts": manifest.get("artifacts") or manifest.get("source_artifacts") or {},
        "manifest": manifest,
    }


def _core_rows(manifest: Dict[str, Any], canonical_rows: List[Dict[str, Any]], provenance_rows: List[Dict[str, Any]]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, str]]:
    run_id = str(manifest["run_id"])
    prov_by_id: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for p in provenance_rows:
        key = (str(p.get("source_record_id") or ""), str(p.get("source_version_id") or ""), str(p.get("source_record_sha256") or ""))
        prov_by_id[key] = p

    source_records: Dict[str, Dict[str, Any]] = {}
    observations: Dict[str, Dict[str, Any]] = {}
    canonical_records: Dict[str, Dict[str, Any]] = {}
    canonical_key_by_source_id: Dict[str, str] = {}

    for row in canonical_rows:
        source = str(row.get("source") or manifest.get("source") or "")
        source_id = str(row.get("nct_id") or row.get("pmid") or row.get("doi") or row.get("source_id") or "")
        version_id = str(row.get("version") or row.get("last_update_post_date") or "")
        source_sha = str(row.get("source_record_sha256") or "")
        candidates = [
            (source_id, version_id, source_sha),
            (source_id, "", source_sha),
        ]
        prov = next((prov_by_id[k] for k in candidates if k in prov_by_id), None)
        if prov:
            source = str(prov.get("source") or source)
            source_id = str(prov.get("source_record_id") or source_id)
            version_id = str(prov.get("source_version_id") or version_id)
            source_sha = str(prov.get("source_record_sha256") or source_sha)
        if not source_id:
            raise ValueError("canonical row has no source identity")
        if len(source_sha) != 64:
            raise ValueError(f"canonical source record {source}:{source_id} lacks SHA-256")
        source_key = stable_uuid("source_record", source, source_id, version_id, source_sha)
        first_seen = (prov or {}).get("retrieved_at") or row.get("retrieved_at") or manifest.get("started_at") or utc_now()
        source_records[source_key] = {
            "source_record_key": source_key,
            "source": source,
            "source_record_id": source_id,
            "source_version_id": version_id,
            "source_record_sha256": source_sha,
            "first_seen_at": first_seen,
            "source_url": (prov or {}).get("source_url") or row.get("source_url"),
            "metadata": {},
        }
        observations[source_key] = {
            "run_id": run_id,
            "source_record_key": source_key,
            "retrieved_at": first_seen,
            "source_version": (prov or {}).get("source_version"),
            "source_updated_at": (prov or {}).get("source_updated_at"),
            "raw_locator": (prov or {}).get("raw_locator"),
            "transport_raw_locators": (prov or {}).get("transport_raw_locators") or ([
                (prov or {}).get("transport_raw_locator")
            ] if (prov or {}).get("transport_raw_locator") else []),
            "parse_status": (prov or {}).get("parse_status", "parsed"),
            "parse_warnings": (prov or {}).get("parse_warnings") or [],
            "provenance_schema_version": (prov or {}).get("provenance_schema_version", "frontier-source-provenance-1.0"),
            "provenance": prov or {},
        }
        content = _canonical_content(row)
        canonical_sha = canonical_json_sha256(content)
        parser_version = str(row.get("parser_version") or manifest.get("parser_version"))
        schema_version = str(row.get("canonical_schema_version") or manifest.get("canonical_schema_version"))
        canonical_key = stable_uuid("canonical_record", source_key, parser_version, schema_version, canonical_sha)
        canonical_records[canonical_key] = {
            "canonical_record_key": canonical_key,
            "source_record_key": source_key,
            "parser_version": parser_version,
            "canonical_schema_version": schema_version,
            "canonical_sha256": canonical_sha,
            "canonical_locator": None,
            "created_at": first_seen,
            "validation_status": "PASS",
            "validation_warnings": [],
        }
        # source IDs are unique inside CTG/PubMed and preprint versioned rows use server|doi|version below.
        canonical_key_by_source_id[source_id] = canonical_key

    tables = {
        "ingestion_run": [_manifest_to_ingestion_run(manifest)],
        "source_record": list(source_records.values()),
        "source_observation": list(observations.values()),
        "canonical_record": list(canonical_records.values()),
        "run_artifact": [],
        "quarantine_record": [],
    }
    return tables, canonical_key_by_source_id


def _loc_geo(loc: Dict[str, Any]) -> Tuple[Any, Any]:
    geo = loc.get("geoPoint") or {}
    return geo.get("lat"), geo.get("lon")


def project_ctg(run_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    manifest = json.loads((run_dir / "extraction_manifest.json").read_text(encoding="utf-8"))
    canonical = read_jsonl(run_dir / "canonical" / "studies_canonical.jsonl")
    provenance = read_jsonl(run_dir / "provenance" / "source_records.jsonl")
    tables, keys = _core_rows(manifest, canonical, provenance)
    study_rows=[]; snapshots=[]
    phase=[]; condition=[]; keyword=[]; sponsor=[]; arm=[]; intervention=[]; outcome=[]; location=[]; contact=[]; reference=[]; ipd=[]
    for row in canonical:
        key=keys[row["nct_id"]]
        study_rows.append({
            "canonical_record_key":key,"nct_id":row["nct_id"],"brief_title":row.get("brief_title") or "",
            "official_title":row.get("official_title"),"acronym":row.get("acronym"),"nct_id_aliases":row.get("nct_id_aliases") or [],
            "org_study_id_info":row.get("org_study_id_info") or {},"secondary_id_infos":row.get("secondary_id_infos") or [],
            "organization":row.get("organization") or {},"brief_summary":row.get("brief_summary"),"detailed_description":row.get("detailed_description"),
            "overall_status":row.get("overall_status"),"why_stopped":row.get("why_stopped"),"expanded_access_info":row.get("expanded_access_info") or {},
            "study_type":row.get("study_type"),"design":row.get("design") or {},"enrollment_count":row.get("enrollment_count"),"enrollment_type":row.get("enrollment_type"),
            "start_date":row.get("start_date"),"start_date_type":row.get("start_date_type"),"primary_completion_date":row.get("primary_completion_date"),
            "primary_completion_date_type":row.get("primary_completion_date_type"),"completion_date":row.get("completion_date"),"completion_date_type":row.get("completion_date_type"),
            "study_first_submit_date":row.get("study_first_submit_date"),"study_first_post_date":row.get("study_first_post_date"),"last_update_submit_date":row.get("last_update_submit_date"),
            "last_update_post_date":row.get("last_update_post_date"),"last_update_post_date_type":row.get("last_update_post_date_type"),"eligibility":row.get("eligibility") or {},
            "ipd_sharing":row.get("ipd_sharing") or {},"oversight":row.get("oversight") or {},"has_results":row.get("has_results"),
            "is_fda_regulated_drug":row.get("is_fda_regulated_drug"),"is_fda_regulated_device":row.get("is_fda_regulated_device"),
            "protocol_raw":row.get("protocol_section") or {},"results_raw":row.get("results_section") or {},"annotation_raw":row.get("annotation_section") or {},
            "document_raw":row.get("document_section") or {},"derived_raw":row.get("derived_section") or {},
            # BigQuery nested convenience fields. PostgreSQL loaders omit these extras.
            "phases":row.get("phase") or [],"conditions":row.get("conditions") or [],"keywords":row.get("keywords") or [],"sponsors":row.get("sponsors") or {},
            "arms":row.get("arms") or [],"interventions":row.get("interventions") or [],"contacts":{"central":row.get("central_contacts") or [],"officials":row.get("overall_officials") or []},
            "locations":row.get("locations") or [],"primary_outcomes":row.get("primary_outcomes") or [],"secondary_outcomes":row.get("secondary_outcomes") or [],
            "other_outcomes":row.get("other_outcomes") or [],"references":row.get("references") or [],"see_also_links":row.get("see_also_links") or [],"available_ipds":row.get("available_ipds") or [],
        })
        snapshots.append({"run_id":manifest["run_id"],"nct_id":row["nct_id"],"canonical_record_key":key,"source_data_timestamp":row.get("source_data_timestamp"),"source_api_version":row.get("source_api_version"),"retrieved_at":row.get("retrieved_at")})
        phase += [{"canonical_record_key":key,"phase":x} for x in row.get("phase") or []]
        condition += [{"canonical_record_key":key,"ordinal":i,"condition":x} for i,x in enumerate(row.get("conditions") or [])]
        keyword += [{"canonical_record_key":key,"ordinal":i,"keyword":x} for i,x in enumerate(row.get("keywords") or [])]
        sp=row.get("sponsors") or {}
        if sp.get("lead"):
            x=sp["lead"]; sponsor.append({"canonical_record_key":key,"sponsor_role":"lead","ordinal":0,"name":x.get("name"),"agency_class":x.get("class"),"payload":x})
        if sp.get("responsible_party"):
            x=sp["responsible_party"]; sponsor.append({"canonical_record_key":key,"sponsor_role":"responsible_party","ordinal":0,"name":x.get("name"),"agency_class":x.get("class"),"payload":x})
        for i,x in enumerate(sp.get("collaborators") or []): sponsor.append({"canonical_record_key":key,"sponsor_role":"collaborator","ordinal":i,"name":x.get("name"),"agency_class":x.get("class"),"payload":x})
        for i,x in enumerate(row.get("arms") or []): arm.append({"canonical_record_key":key,"ordinal":i,"label":x.get("label"),"arm_type":x.get("type"),"description":x.get("description"),"payload":x})
        for i,x in enumerate(row.get("interventions") or []): intervention.append({"canonical_record_key":key,"ordinal":i,"intervention_type":x.get("type"),"name":x.get("name"),"description":x.get("description"),"other_names":x.get("otherNames") or [],"arm_group_labels":x.get("armGroupLabels") or [],"payload":x})
        for typ, field in [("primary","primary_outcomes"),("secondary","secondary_outcomes"),("other","other_outcomes")]:
            for i,x in enumerate(row.get(field) or []): outcome.append({"canonical_record_key":key,"outcome_type":typ,"ordinal":i,"measure":x.get("measure"),"description":x.get("description"),"time_frame":x.get("timeFrame"),"payload":x})
        for i,x in enumerate(row.get("locations") or []):
            facility=x.get("facility") or {}; lat,lon=_loc_geo(x)
            location.append({"canonical_record_key":key,"ordinal":i,"facility":facility.get("name") if isinstance(facility,dict) else facility,"status":facility.get("status") if isinstance(facility,dict) else None,"city":x.get("city"),"state":x.get("state"),"zip":x.get("zip"),"country":x.get("country"),"latitude":lat,"longitude":lon,"payload":x})
        for typ,field in [("central","central_contacts"),("official","overall_officials")]:
            for i,x in enumerate(row.get(field) or []): contact.append({"canonical_record_key":key,"contact_type":typ,"ordinal":i,"name":x.get("name"),"role":x.get("role"),"affiliation":x.get("affiliation"),"phone":x.get("phone"),"email":x.get("email"),"payload":x})
        for i,x in enumerate(row.get("references") or []): reference.append({"canonical_record_key":key,"reference_type":x.get("type") or "reference","ordinal":i,"pmid":x.get("pmid"),"citation":x.get("citation"),"payload":x})
        for i,x in enumerate(row.get("available_ipds") or []): ipd.append({"canonical_record_key":key,"ordinal":i,"ipd_type":x.get("type"),"url":x.get("url"),"comment":x.get("comment"),"payload":x})
    tables.update({"ctg_study_record":study_rows,"ctg_study_snapshot":snapshots,"ctg_phase":phase,"ctg_condition":condition,"ctg_keyword":keyword,"ctg_sponsor":sponsor,"ctg_arm":arm,"ctg_intervention":intervention,"ctg_outcome":outcome,"ctg_location":location,"ctg_contact":contact,"ctg_reference":reference,"ctg_available_ipd":ipd})
    tables["run_artifact"]=_manifest_artifact_rows(manifest,run_dir,run_dir/"extraction_manifest.json")
    tables["quarantine_record"]=_quarantine_rows(manifest["run_id"],"clinicaltrials.gov",[run_dir/"quarantine/invalid_records.jsonl"],root=run_dir)
    return tables


def project_pubmed(run_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    manifest=json.loads((run_dir/"manifest.json").read_text(encoding="utf-8"))
    canonical=read_jsonl(run_dir/"canonical/pubmed_records.jsonl")
    provenance=read_jsonl(run_dir/"provenance/source_records.jsonl")
    tables,keys=_core_rows(manifest,canonical,provenance)
    recs=[]; snaps=[]; authors=[]; mesh=[]
    for row in canonical:
        key=keys[str(row["pmid"])]
        pd=row.get("pub_date") or {}; ad=row.get("article_date") or {}
        recs.append({"canonical_record_key":key,"pmid":str(row["pmid"]),"record_type":row.get("record_type") or "journal_article","doi":row.get("doi"),"pmcid":row.get("pmc_id"),"version":row.get("version"),"title":row.get("title") or "","abstract":row.get("abstract") or "","abstract_sections":row.get("abstract_sections") or [],"journal":row.get("journal"),"journal_abbrev":row.get("journal_abbrev"),"journal_issn":row.get("journal_issn"),"volume":row.get("volume"),"issue":row.get("issue"),"pages":row.get("pages"),"publication_date":pd.get("parsed_date"),"medline_date":pd.get("medline_date_str"),"article_date":ad.get("parsed_date"),"pubmed_dates":row.get("pubmed_pub_dates") or {},"date_created":row.get("date_created"),"date_completed":row.get("date_completed"),"date_revised":row.get("date_revised"),"publication_types":row.get("publication_types") or [],"languages":row.get("languages") or [],"keywords":row.get("keywords") or [],"chemicals":row.get("chemicals") or [],"grants":row.get("grants") or [],"article_ids":row.get("article_ids") or {},"references":row.get("references") or [],"publication_status":row.get("publication_status"),"book_metadata":row.get("book_metadata") or {},"raw_xml":row.get("raw_xml") or ""})
        snaps.append({"run_id":manifest["run_id"],"pmid":str(row["pmid"]),"canonical_record_key":key,"retrieved_at":row.get("retrieved_at"),"retrieval_queries":row.get("retrieval_queries") or []})
        for i,a in enumerate(row.get("authors") or []): authors.append({"canonical_record_key":key,"ordinal":i,"family_name":a.get("last_name"),"given_name":a.get("fore_name"),"initials":a.get("initials"),"collective_name":a.get("collective_name"),"affiliations":a.get("affiliations") or ([a.get("affiliation")] if a.get("affiliation") else []),"identifiers":a.get("identifiers") or {},"payload":a})
        for i,m in enumerate(row.get("mesh_headings") or []): mesh.append({"canonical_record_key":key,"ordinal":i,"descriptor_name":m.get("descriptor_name"),"descriptor_ui":m.get("descriptor_ui"),"major_topic":bool(m.get("major_topic")),"qualifiers":m.get("qualifiers") or []})
    tables.update({"pubmed_record":recs,"pubmed_snapshot":snaps,"pubmed_author":authors,"pubmed_mesh_heading":mesh})
    tables["run_artifact"]=_manifest_artifact_rows(manifest,run_dir,run_dir/"manifest.json")
    tables["quarantine_record"]=[]
    return tables


def project_preprint(run_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    manifest=json.loads((run_dir/"manifest.json").read_text(encoding="utf-8"))
    canonical_path = run_dir/"versions.jsonl"
    provenance_paths: List[Path] = [run_dir/"provenance/source_records.jsonl"]
    if not canonical_path.exists() and (run_dir/"versions_all.jsonl").exists():
        canonical_path = run_dir/"versions_all.jsonl"
        provenance_paths = []
        for shard in manifest.get("shard_manifest_chain") or []:
            shard_path = run_dir / str(shard.get("path") or "")
            pp = shard_path / "provenance/source_records.jsonl"
            if not pp.is_file():
                raise FileNotFoundError(f"aggregate preprint shard provenance missing: {pp}")
            provenance_paths.append(pp)
    canonical=read_jsonl(canonical_path)
    provenance=[]
    for pp in provenance_paths:
        if pp.is_file(): provenance.extend(read_jsonl(pp))
    # preprints need version-aware source identity in the generic core map
    tables,_=_core_rows(manifest,canonical,provenance)
    prov_index={(str(p.get("source_record_id")),str(p.get("source_version_id")),str(p.get("source_record_sha256"))):p for p in provenance}
    recs=[]; snaps=[]
    for row in canonical:
        server=str(row.get("server") or manifest["source"]); doi=str(row["doi"]); ver=str(row.get("version") or "1"); sha=str(row["source_record_sha256"])
        prov=prov_index[(doi,ver,sha)]
        sk=stable_uuid("source_record",server,doi,ver,sha)
        content=_canonical_content(row); csha=canonical_json_sha256(content)
        ck=stable_uuid("canonical_record",sk,row.get("parser_version") or manifest["parser_version"],row.get("canonical_schema_version") or manifest["canonical_schema_version"],csha)
        recs.append({"canonical_record_key":ck,"server":server,"doi":doi,"version":int(ver),"title":row.get("title") or "","abstract":row.get("abstract"),"authors":row.get("authors"),"author_corresponding":row.get("author_corresponding"),"author_corresponding_institution":row.get("author_corresponding_institution"),"category":row.get("category"),"posted_date":row.get("date"),"license":row.get("license"),"published_doi":row.get("published"),"source_payload":row.get("source_payload") or row.get("source_record") or row})
        snaps.append({"run_id":manifest["run_id"],"server":server,"doi":doi,"version":int(ver),"canonical_record_key":ck,"retrieved_at":prov.get("retrieved_at")})
    tables.update({"preprint_record":recs,"preprint_snapshot":snaps})
    tables["run_artifact"]=_manifest_artifact_rows(manifest,run_dir,run_dir/"manifest.json")
    qpaths=[run_dir/"quarantine/invalid_records.jsonl"]
    for shard in manifest.get("shard_manifest_chain") or []:
        qpaths.append(run_dir/str(shard.get("path") or "")/"quarantine/invalid_records.jsonl")
    tables["quarantine_record"]=_quarantine_rows(manifest["run_id"],str(manifest.get("source") or "preprint"),qpaths,root=run_dir)
    return tables


def validate_references(tables: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    errors=[]
    run_ids={r["run_id"] for r in tables.get("ingestion_run",[])}
    source_keys={r["source_record_key"] for r in tables.get("source_record",[])}
    canon_keys={r["canonical_record_key"] for r in tables.get("canonical_record",[])}
    for r in tables.get("source_observation",[]):
        if r["run_id"] not in run_ids: errors.append(f"source_observation missing run {r['run_id']}")
        if r["source_record_key"] not in source_keys: errors.append(f"source_observation missing source record {r['source_record_key']}")
    for r in tables.get("canonical_record",[]):
        if r["source_record_key"] not in source_keys: errors.append(f"canonical_record missing source record {r['source_record_key']}")
    for table, rows in tables.items():
        if table in {"canonical_record","source_record","source_observation","ingestion_run","run_artifact","quarantine_record"}: continue
        for r in rows:
            ck=r.get("canonical_record_key")
            if ck and ck not in canon_keys: errors.append(f"{table} missing canonical record {ck}")
            rid=r.get("run_id")
            if rid and rid not in run_ids: errors.append(f"{table} missing run {rid}")
    return errors


def validate_projection_semantics(tables: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """Cross-check warehouse rows against the source run's own accounting/provenance claims."""
    errors=[]
    runs=tables.get("ingestion_run",[])
    if len(runs)!=1:
        return [f"projection must contain exactly one ingestion_run, found {len(runs)}"]
    run=runs[0]
    valid=len(tables.get("canonical_record",[])); sources=len(tables.get("source_record",[])); quarantine=len(tables.get("quarantine_record",[]))
    declared_valid=int(run.get("valid_records") or 0); declared_quarantine=int(run.get("quarantined_records") or 0); declared_observed=int(run.get("observed_records") or 0); declared_unique=int(run.get("unique_records") or 0)
    if declared_valid != valid: errors.append(f"valid_records={declared_valid} but canonical_record rows={valid}")
    if declared_quarantine != quarantine: errors.append(f"quarantined_records={declared_quarantine} but quarantine_record rows={quarantine}")
    if declared_unique != sources: errors.append(f"unique_records={declared_unique} but source_record rows={sources}")
    if declared_observed < valid + quarantine: errors.append(f"observed_records={declared_observed} is less than valid+quarantine={valid+quarantine}")
    artifacts=tables.get("run_artifact",[])
    roles={str(a.get("role") or "") for a in artifacts}; locators={str(a.get("locator") or "") for a in artifacts}
    if artifacts and "source_manifest" not in roles: errors.append("run_artifact rows exist but source_manifest artifact is missing")
    manifest=run.get("manifest") or {}
    transport_status=str(manifest.get("transport_capture_status") or "")
    if transport_status.startswith("PASS_EXACT_"):
        if not any("raw_transport" in r or r=="raw_bulk_archive" for r in roles):
            errors.append(f"{transport_status} declared but no exact raw transport/bulk run_artifact exists")
    for obs in tables.get("source_observation",[]):
        for locator in obs.get("transport_raw_locators") or []:
            base=str(locator).split("#",1)[0]
            if base and base not in locators:
                errors.append(f"source_observation transport locator is not represented in run_artifact: {locator}")
    return errors


def write_projection(tables: Dict[str, List[Dict[str, Any]]], output_dir: Path, *, source: str, source_manifest_sha256: str | None=None) -> Dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"warehouse projection output must be empty: {output_dir}")
    output_dir.mkdir(parents=True,exist_ok=True)
    errors=validate_references(tables)
    if errors: raise ValueError("warehouse referential validation failed: " + "; ".join(errors[:10]))
    semantic_errors=validate_projection_semantics(tables)
    if semantic_errors: raise ValueError("warehouse semantic validation failed: " + "; ".join(semantic_errors[:10]))
    artifacts={}
    for table in sorted(tables):
        path=output_dir/f"{table}.jsonl"; count=atomic_jsonl(path,tables[table])
        artifacts[table]={"path":path.name,"records":count,"sha256":sha256_file(path)}
    manifest={"projection_version":WAREHOUSE_PROJECTION_VERSION,"source":source,"created_at":utc_now(),"source_manifest_sha256":source_manifest_sha256,"validation_status":"PASS","referential_errors":[],"artifacts":artifacts}
    atomic_json(output_dir/"warehouse_projection_manifest.json",manifest)
    return manifest


def project_run(kind: str, run_dir: Path, output_dir: Path) -> Dict[str, Any]:
    kind=kind.lower()
    if kind=="ctg":
        tables=project_ctg(run_dir); source_manifest=run_dir/"extraction_manifest.json"; source="clinicaltrials.gov"
    elif kind=="pubmed":
        tables=project_pubmed(run_dir); source_manifest=run_dir/"manifest.json"; source="pubmed"
    elif kind in {"medrxiv","biorxiv","preprint"}:
        tables=project_preprint(run_dir); source_manifest=run_dir/"manifest.json"; source=kind
    else:
        raise ValueError(f"unsupported source projection: {kind}")
    return write_projection(tables,output_dir,source=source,source_manifest_sha256=sha256_file(source_manifest))


def _drug_source_identity(source: str, row: Dict[str, Any]) -> Tuple[str, str]:
    if source == "drugbank":
        return str(row.get("drugbank_id") or ""), str(row.get("source_updated") or "")
    if source == "rxnorm":
        ids = row.get("rxcuis") or ([row.get("rxcui")] if row.get("rxcui") else [])
        return ",".join(sorted(str(x) for x in ids if x)), ""
    if source == "livertox":
        return str(row.get("source_nbk_id") or row.get("source_url") or row.get("name") or ""), str(row.get("source_updated") or "")
    raise ValueError(source)


def project_drug(crosswalk_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    manifest_path=Path(str(crosswalk_path)+".manifest.json")
    provenance_path=Path(str(crosswalk_path)+".provenance.jsonl")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    crosswalk=read_jsonl(crosswalk_path)
    provenance=read_jsonl(provenance_path)
    prov_by_source_id={(str(p.get("source")),str(p.get("source_record_id"))):p for p in provenance}

    source_records=[]; observations=[]; canonical_records=[]; drug_source=[]
    canonical_key_by_identity: Dict[Tuple[str,str],str]={}
    manifest_dir=manifest_path.parent
    for source in ("drugbank","rxnorm","livertox"):
        art=(manifest.get("source_artifacts") or {}).get(source) or {}
        path=Path(str(art.get("path") or ""))
        if not path.is_absolute(): path=manifest_dir/path
        if not path.is_file():
            raise FileNotFoundError(f"drug source artifact missing for {source}: {path}")
        if art.get("sha256") and sha256_file(path)!=art["sha256"]:
            raise ValueError(f"drug source artifact hash mismatch: {source}")
        rows=read_jsonl(path)
        for row in rows:
            source_id,version_id=_drug_source_identity(source,row)
            if not source_id: raise ValueError(f"{source} source row lacks identity")
            sha=str(row.get("source_record_sha256") or canonical_json_sha256(row))
            if len(sha)!=64: raise ValueError(f"{source}:{source_id} lacks source SHA")
            sk=stable_uuid("source_record",source,source_id,version_id,sha)
            p=prov_by_source_id.get((source,source_id),{})
            seen=p.get("retrieved_at") or manifest.get("started_at") or utc_now()
            source_records.append({"source_record_key":sk,"source":source,"source_record_id":source_id,"source_version_id":version_id,"source_record_sha256":sha,"first_seen_at":seen,"source_url":p.get("source_url") or row.get("source_url"),"metadata":{}})
            observations.append({"run_id":manifest["run_id"],"source_record_key":sk,"retrieved_at":seen,"source_version":None,"source_updated_at":p.get("source_updated_at"),"raw_locator":p.get("raw_locator") or str(art.get("path") or ""),"transport_raw_locators":p.get("transport_raw_locators") or ([p.get("transport_raw_locator")] if p.get("transport_raw_locator") else []),"parse_status":"parsed","parse_warnings":[],"provenance_schema_version":p.get("provenance_schema_version","frontier-source-provenance-1.0"),"provenance":p})
            csha=canonical_json_sha256(row)
            ck=stable_uuid("canonical_record",sk,manifest["parser_version"],manifest["canonical_schema_version"],csha)
            canonical_records.append({"canonical_record_key":ck,"source_record_key":sk,"parser_version":manifest["parser_version"],"canonical_schema_version":manifest["canonical_schema_version"],"canonical_sha256":csha,"canonical_locator":str(art.get("path") or path),"created_at":seen,"validation_status":"PASS","validation_warnings":[]})
            preferred=row.get("name")
            normalized=row.get("name_normalized") or (str(preferred).casefold().strip() if preferred else None)
            drug_source.append({"canonical_record_key":ck,"source":source,"source_id":source_id,"preferred_name":preferred,"normalized_name":normalized,"payload":row})
            canonical_key_by_identity[(source,source_id)]=ck

    candidates_out=[]; aliases=[]; evidence=[]
    for row in crosswalk:
        db=row.get("drugbank") or {}; dbid=str(db.get("drugbank_id") or "")
        if not dbid: raise ValueError("crosswalk row missing DrugBank source identity")
        # 09D authority boundary: source identity is never canonical identity.
        source_table="frontier.drug_source_record"
        source_key=f"drugbank:{dbid}"
        source_identity_sha=hashlib.sha256(source_table.encode("utf-8") + b"\x1f" + source_key.encode("utf-8")).hexdigest()
        candidate_id="CAND:" + source_identity_sha[:32]
        name=str(row.get("name") or db.get("name") or "")
        norm=str(row.get("name_normalized") or "")
        db_ck=canonical_key_by_identity.get(("drugbank",dbid))
        if not db_ck: raise ValueError(f"DrugBank candidate source record not found: {dbid}")
        candidates_out.append({
            "candidate_id":candidate_id,
            "domain":"drug",
            "source_table":source_table,
            "source_key":source_key,
            "source_identity_sha256":source_identity_sha,
            "origin_package_id":f"FRONTIER:{manifest['run_id']}",
            "state":"REGISTERED",
            "legacy_entity_id":None,
            "source_canonical_record_key":db_ck,
            "preferred_name":name,
            "normalized_name":norm,
            "created_at":manifest.get("completed_at") or utc_now(),
            "automatic_identity_merge_allowed":False,
            "automatic_selection_allowed":False,
            "canonical_internal_eligible":False,
            "generation_eligible":False,
            "public_eligible":False,
        })
        for alias in [name]+[str(x) for x in db.get("synonyms") or []]:
            if alias.strip(): aliases.append({"candidate_id":candidate_id,"alias":alias,"normalized_alias":alias.casefold().strip(),"source":"drugbank"})
        linkage=row.get("linkage") or {}
        for source,status_key,candidate_key in [("rxnorm","rxnorm_status","rxnorm_candidate_ids"),("livertox","livertox_status","livertox_candidate_ids")]:
            status=str(linkage.get(status_key) or "missing")
            source_candidates=list(linkage.get(candidate_key) or [])
            linked_ck=None; source_id=None
            if status=="matched":
                matched=row.get(source) or {}
                source_id,_=_drug_source_identity(source,matched)
                linked_ck=canonical_key_by_identity.get((source,source_id))
            evidence.append({"linkage_id":stable_uuid("drug_candidate_linkage",candidate_id,source,source_id or "",status,canonical_json_sha256(source_candidates)),"candidate_id":candidate_id,"canonical_record_key":linked_ck,"source":source,"source_id":source_id,"status":status,"method":linkage.get("method") or "normalized_exact_primary_or_synonym","confidence":linkage.get(f"{source}_confidence"),"candidate_count":len(source_candidates),"evidence":{"candidate_ids":source_candidates,"aliases_considered":linkage.get("aliases_considered") or []},"created_at":manifest.get("completed_at") or utc_now()})
    # Drug artifacts include derived crosswalk/provenance, per-source normalized captures, and
    # cryptographically pinned raw inputs. Licensed artifacts may remain external by design;
    # the locator + SHA-256 + retention metadata is still first-class lineage.
    created=manifest.get("completed_at") or manifest.get("started_at") or utc_now()
    artifacts=[]
    artifacts.append(_artifact_row(manifest["run_id"],"source_manifest",manifest_path.name,sha256_file(manifest_path),path=manifest_path,created_at=created,metadata={"manifest_schema_version":manifest.get("manifest_schema_version")}))
    artifacts.append(_artifact_row(manifest["run_id"],"canonical_crosswalk",crosswalk_path.name,sha256_file(crosswalk_path),path=crosswalk_path,record_count=len(crosswalk),created_at=created))
    artifacts.append(_artifact_row(manifest["run_id"],"source_provenance",provenance_path.name,sha256_file(provenance_path),path=provenance_path,record_count=len(provenance),created_at=created))
    for source,spec in (manifest.get("source_artifacts") or {}).items():
        locator=str(spec.get("path") or "")
        if not locator: continue
        path=manifest_dir/locator if not Path(locator).is_absolute() else Path(locator)
        artifacts.append(_artifact_row(manifest["run_id"],f"normalized_source_{source}",locator,str(spec.get("sha256") or sha256_file(path)),path=path if path.is_file() else None,record_count=spec.get("records"),created_at=created))
    for source,spec in (manifest.get("raw_input_artifacts") or {}).items():
        locator=str(spec.get("locator") or "")
        if not locator: continue
        path=Path(locator)
        artifacts.append(_artifact_row(manifest["run_id"],f"raw_input_{source}",locator,str(spec.get("sha256") or (sha256_file(path) if path.is_file() else "")),path=path if path.is_file() else None,created_at=created,metadata={"retention_required":bool(spec.get("retention_required")),"copied_into_output":bool(spec.get("copied_into_output")),"input_manifest":(manifest.get("input_manifests") or {}).get(source)}))
    return {
        "ingestion_run":[_manifest_to_ingestion_run(manifest)],
        "run_artifact":artifacts,"quarantine_record":[],
        "source_record":source_records,"source_observation":observations,"canonical_record":canonical_records,
        "drug_source_record":drug_source,"drug_candidate":candidates_out,"drug_candidate_alias":aliases,"drug_candidate_linkage_evidence":evidence,
    }
