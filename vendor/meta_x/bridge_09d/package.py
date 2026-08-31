from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import uuid
from bridge_09d.assertions import validate_source_unit, validate_assertion, SOURCE_UNIT_SCHEMA_VERSION, ASSERTION_SCHEMA_VERSION
from bridge_09d.verifier import validate_verification_event, VERIFICATION_SCHEMA_VERSION
from bridge_09d.semantic_router import validate_review_case, ROUTER_SCHEMA_VERSION
from bridge_09d.source_units import validate_fulltext_artifact, validate_rights_decision, SEGMENTER_SCHEMA_VERSION, FULLTEXT_ARTIFACT_SCHEMA_VERSION, RIGHTS_SCHEMA_VERSION
from frontier_core.readiness import code_manifest

PACKAGE_SCHEMA_VERSION = "frontier-09d-external-audit-package-1.5"
PACKAGE_KIND = "FRONTIER_EXTERNAL_EVIDENCE_AUDIT"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_identity_sha256(source_table: str, source_key: str) -> str:
    if not isinstance(source_table, str) or not source_table:
        raise ValueError("source_table must be non-empty text")
    if not isinstance(source_key, str) or not source_key:
        raise ValueError("source_key must be non-empty text")
    return hashlib.sha256(source_table.encode("utf-8") + b"\x1f" + source_key.encode("utf-8")).hexdigest()


def candidate_id(source_table: str, source_key: str) -> str:
    return "CAND:" + source_identity_sha256(source_table, source_key)[:32]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out=[]
    for lineno,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        obj=json.loads(line)
        if not isinstance(obj,dict): raise ValueError(f"{path}:{lineno}: row must be object")
        out.append(obj)
    return out


def _atomic_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        json.dump(obj,f,indent=2,sort_keys=True,ensure_ascii=False); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)


def _atomic_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    rows=list(rows); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        for row in rows: f.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path); return len(rows)


def validate_candidate(row: Dict[str, Any]) -> List[str]:
    errors=[]
    table=str(row.get("source_table") or ""); key=str(row.get("source_key") or "")
    if not table or not key: return ["candidate lacks source_table/source_key"]
    expected_sha=source_identity_sha256(table,key); expected_id="CAND:"+expected_sha[:32]
    if row.get("source_identity_sha256") != expected_sha: errors.append("source_identity_sha256 mismatch")
    if row.get("candidate_id") != expected_id: errors.append("candidate_id mismatch")
    if row.get("state") != "REGISTERED": errors.append("extractor candidate state must remain REGISTERED in Turn 1 boundary")
    for field in ("automatic_identity_merge_allowed","automatic_selection_allowed","canonical_internal_eligible","generation_eligible","public_eligible"):
        if row.get(field) is not False: errors.append(f"{field} must be false")
    if row.get("legacy_entity_id") is not None: errors.append("extractor cannot assign legacy/canonical entity identity")
    return errors


def validate_package_manifest(manifest: Dict[str, Any]) -> List[str]:
    errors=[]
    exact={
        "package_kind": PACKAGE_KIND,
        "direct_09d_insert_allowed": False,
        "canonical_authority": False,
        "automatic_selection_allowed": False,
        "canonical_internal_eligible": False,
        "generation_eligible": False,
        "public_eligible": False,
        "mass_extraction_authorized": False,
    }
    for key,val in exact.items():
        if manifest.get(key) != val: errors.append(f"{key} must equal {val!r}")
    if manifest.get("current_09d_s02_direct_insert_compatible") is not False:
        errors.append("current S02 direct-insert compatibility must be false")
    if manifest.get("assertion_contract_status") != "FROZEN": errors.append("assertion contract must be FROZEN")
    if manifest.get("source_unit_contract_status") != "FROZEN": errors.append("source unit contract must be FROZEN")
    if manifest.get("assertion_engine_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_UNVERIFIED_OUTPUT": errors.append("assertion extraction engine status mismatch")
    if manifest.get("assertion_verifier_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_APPEND_ONLY": errors.append("assertion verifier status mismatch for Turn 5")
    if manifest.get("assertion_output_policy") != "EXTRACTOR_ASSERTIONS_REMAIN_NOT_VERIFIED": errors.append("extractor assertions must remain NOT_VERIFIED")
    if manifest.get("verification_overlay_policy") != "APPEND_ONLY_VERIF_EVENTS": errors.append("verification must be append-only overlay")
    if manifest.get("semantic_specialist_lanes_status") != "IMPLEMENTED_OFFLINE_CERTIFIED": errors.append("semantic specialist lanes status mismatch")
    if manifest.get("risk_router_status") != "IMPLEMENTED_OFFLINE_CERTIFIED": errors.append("risk router status mismatch")
    if manifest.get("semantic_gold_gate_status") != "PASS_OFFLINE_HAND_AUTHORED_CONTRACT": errors.append("semantic gold gate status mismatch")
    if manifest.get("blind_recall_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_CONTRACT_MODEL_PENDING": errors.append("blind recall status mismatch")
    if manifest.get("semantic_review_router_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE": errors.append("semantic review router status mismatch")
    if manifest.get("semantic_factory_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE": errors.append("semantic factory status mismatch")
    if manifest.get("single_semantic_verifier_authority") is not True: errors.append("single semantic verifier authority must be true")
    if manifest.get("source_unit_segmenter_status") != "IMPLEMENTED_OFFLINE_CERTIFIED": errors.append("source unit segmenter must be IMPLEMENTED_OFFLINE_CERTIFIED in Turn 3")
    if manifest.get("fulltext_acquisition_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_PUBLIC_CANARY_PENDING": errors.append("full-text acquisition status mismatch for Turn 3")
    if manifest.get("rights_dimensions_separate") is not True: errors.append("rights dimensions must remain separate")
    if manifest.get("candidate_resolution_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE": errors.append("candidate resolution status mismatch")
    if manifest.get("09d_comparator_status") != "IMPLEMENTED_OFFLINE_CERTIFIED_REAL_DATABASE_PENDING": errors.append("09D comparator status mismatch")
    if manifest.get("candidate_to_canonical_assignment_performed") is not False: errors.append("candidate-to-canonical assignment must remain false")
    if manifest.get("09d_mutation_performed") is not False: errors.append("09D mutation must remain false")
    return errors


def build_audit_package(warehouse_dir: Path, output_dir: Path, *, authority_reference: Path, source_units: Optional[Iterable[Dict[str,Any]]]=None, assertions: Optional[Iterable[Dict[str,Any]]]=None, assertion_engine_result: Optional[Dict[str,Any]]=None, verification_result: Optional[Dict[str,Any]]=None, blind_recall_result: Optional[Dict[str,Any]]=None, semantic_routing_result: Optional[Dict[str,Any]]=None, semantic_factory_result: Optional[Dict[str,Any]]=None, turn6_result: Optional[Dict[str,Any]]=None, fulltext_artifacts: Optional[Iterable[Dict[str,Any]]]=None, rights_decisions: Optional[Iterable[Dict[str,Any]]]=None) -> Dict[str, Any]:
    warehouse_dir=Path(warehouse_dir); output_dir=Path(output_dir); authority_reference=Path(authority_reference)
    if output_dir.exists() and any(output_dir.iterdir()): raise RuntimeError(f"audit package output must be empty: {output_dir}")
    if not (warehouse_dir/"warehouse_projection_manifest.json").is_file(): raise FileNotFoundError("warehouse projection manifest missing")
    authority=json.loads(authority_reference.read_text(encoding="utf-8"))
    if authority.get("mode")!="READ_ONLY" or authority.get("write_allowed") is not False: raise ValueError("09D authority reference is not read-only")
    projection=json.loads((warehouse_dir/"warehouse_projection_manifest.json").read_text(encoding="utf-8"))
    if projection.get("validation_status")!="PASS": raise ValueError("warehouse projection is not PASS")
    runs=_read_jsonl(warehouse_dir/"ingestion_run.jsonl")
    if len(runs)!=1: raise ValueError("warehouse must contain exactly one ingestion_run")
    sources=_read_jsonl(warehouse_dir/"source_record.jsonl")
    observations=_read_jsonl(warehouse_dir/"source_observation.jsonl")
    artifacts=_read_jsonl(warehouse_dir/"run_artifact.jsonl")
    candidates=[]
    for name in ("drug_candidate.jsonl",): candidates.extend(_read_jsonl(warehouse_dir/name))
    candidate_aliases=[]
    for name in ("drug_candidate_alias.jsonl",): candidate_aliases.extend(_read_jsonl(warehouse_dir/name))
    candidate_linkage=[]
    for name in ("drug_candidate_linkage_evidence.jsonl",): candidate_linkage.extend(_read_jsonl(warehouse_dir/name))
    identity_cases=[]
    candidate_assertion_links=[]
    identity_lookups=[]
    comparison_rows=[]
    if turn6_result is not None:
        for key in ("candidate_to_canonical_assignment_performed","09d_mutation_performed","automatic_match_allowed","automatic_merge_allowed","automatic_promotion_allowed","automatic_selection_allowed","canonical_authority","generation_eligible","public_eligible","mass_extraction_authorized"):
            if turn6_result.get(key) is not False: raise ValueError(f"Turn 6 result must have {key}=false")
        if turn6_result.get("candidate_resolution_performed") is not True or turn6_result.get("09d_comparison_performed") is not True:
            raise ValueError("Turn 6 result must explicitly perform candidate resolution and read-only 09D comparison")
        ident=turn6_result.get("identity_resolution") or {}; comp=turn6_result.get("09d_comparison") or {}
        mention_candidates=list(ident.get("candidate_records") or [])
        candidates.extend(mention_candidates)
        candidate_aliases.extend(list(ident.get("candidate_aliases") or []))
        candidate_assertion_links=list(ident.get("candidate_assertion_links") or [])
        identity_cases=list(ident.get("identity_cases") or [])
        identity_lookups=list(comp.get("identity_lookups") or [])
        comparison_rows=list(comp.get("comparisons") or [])
        if comp.get("read_only") is not True or comp.get("09d_mutation_performed") is not False:
            raise ValueError("Turn 6 comparator must be read-only and non-mutating")
        if comp.get("automatic_selection_allowed") is not False or comp.get("canonical_authority") is not False:
            raise ValueError("Turn 6 comparator cannot grant selection/canonical authority")
    candidate_errors=[]
    seen_candidate_ids=set()
    for row in candidates:
        candidate_errors.extend(f"{row.get('candidate_id')}: {x}" for x in validate_candidate(row))
        cid=row.get("candidate_id")
        if cid in seen_candidate_ids: candidate_errors.append(f"duplicate candidate_id in package: {cid}")
        seen_candidate_ids.add(cid)
    if candidate_errors: raise ValueError("candidate authority validation failed: "+"; ".join(candidate_errors[:20]))
    output_dir.mkdir(parents=True,exist_ok=True)
    source_units=list(source_units or [])
    if semantic_factory_result is not None:
        if verification_result is not None or blind_recall_result is not None or semantic_routing_result is not None:
            raise ValueError("provide semantic_factory_result or its component semantic results, not both")
        for key in ("primary_assertions_mutated","automatic_repair_allowed","automatic_selection_allowed","candidate_resolution_performed","09d_comparison_performed","canonical_authority","generation_eligible","public_eligible","mass_extraction_authorized"):
            if semantic_factory_result.get(key) is not False: raise ValueError(f"semantic factory result must have {key}=false")
        current_code_sha=code_manifest(Path(__file__).resolve().parents[1])["sha256"]
        if semantic_factory_result.get("code_manifest_sha256") != current_code_sha: raise ValueError("semantic factory result code hash does not match current estate")
        verification_result=semantic_factory_result.get("verification")
        blind_recall_result=semantic_factory_result.get("blind_recall")
        semantic_routing_result=semantic_factory_result.get("semantic_routing")
    if assertion_engine_result is not None and assertions is not None:
        raise ValueError("provide either assertions or assertion_engine_result, not both")
    assertions=list((assertion_engine_result or {}).get("assertions") or assertions or [])
    assertion_quarantine=list((assertion_engine_result or {}).get("quarantine") or [])
    if assertion_engine_result is not None:
        for key in ("semantic_verification_performed","candidate_resolution_performed","09d_comparison_performed","authority_granted"):
            if assertion_engine_result.get(key) is not False: raise ValueError(f"Turn 4 assertion engine result must have {key}=false")
        current_code_sha=code_manifest(Path(__file__).resolve().parents[1])["sha256"]
        claimed=((assertion_engine_result.get("extractor_provenance") or {}).get("code_manifest_sha256"))
        if claimed != current_code_sha: raise ValueError("assertion engine result code hash does not match current estate")
    verification_events=list((verification_result or {}).get("verification_events") or [])
    verification_quarantine=list((verification_result or {}).get("quarantine") or [])
    if verification_result is not None:
        for key in ("assertions_mutated","candidate_resolution_performed","09d_comparison_performed","authority_granted"):
            if verification_result.get(key) is not False: raise ValueError(f"Turn 5 verification result must have {key}=false")
        if verification_result.get("blind_independent_review") is not True: raise ValueError("Turn 5 verifier must be blind/independent")
        current_code_sha=code_manifest(Path(__file__).resolve().parents[1])["sha256"]
        claimed=((verification_result.get("verifier_provenance") or {}).get("code_manifest_sha256"))
        if claimed != current_code_sha: raise ValueError("verification result code hash does not match current estate")
    recall_assertions=list((blind_recall_result or {}).get("assertions") or [])
    recall_quarantine=list((blind_recall_result or {}).get("quarantine") or [])
    recall_reconciliation=dict((blind_recall_result or {}).get("reconciliation") or {})
    recall_reconciliation_rows=list(recall_reconciliation.get("rows") or [])
    if blind_recall_result is not None:
        for key in ("primary_mutation_performed","authority_granted"):
            if blind_recall_result.get(key) is not False: raise ValueError(f"blind recall result must have {key}=false")
        if blind_recall_result.get("independent_of_primary_extractor") is not True: raise ValueError("blind recall must be independent of primary extractor")
        current_code_sha=code_manifest(Path(__file__).resolve().parents[1])["sha256"]
        claimed=((blind_recall_result.get("extractor_provenance") or {}).get("code_manifest_sha256"))
        if claimed != current_code_sha: raise ValueError("blind recall result code hash does not match current estate")
        if recall_reconciliation.get("automatic_merge_allowed") is not False or recall_reconciliation.get("automatic_repair_allowed") is not False:
            raise ValueError("blind recall reconciliation cannot auto-merge or auto-repair")
    review_cases=list((semantic_routing_result or {}).get("review_cases") or [])
    if semantic_routing_result is not None:
        for key in ("automatic_action_allowed","automatic_repair_allowed","automatic_selection_allowed","candidate_resolution_performed","09d_comparison_performed","authority_granted"):
            if semantic_routing_result.get(key) is not False: raise ValueError(f"semantic routing result must have {key}=false")
        if semantic_routing_result.get("semantic_review_router_schema_version") != ROUTER_SCHEMA_VERSION: raise ValueError("semantic routing schema mismatch")
    fulltext_artifacts=list(fulltext_artifacts or [])
    rights_decisions=list(rights_decisions or [])
    unit_by_id={}
    source_record_keys={str(r.get("source_record_key") or "") for r in sources}
    contract_errors=[]
    for row in fulltext_artifacts:
        contract_errors.extend(f"fulltext artifact {row.get('source_resource_id')}: {x}" for x in validate_fulltext_artifact(row, require_local_file=True))
    for row in rights_decisions:
        contract_errors.extend(f"rights decision {row.get('source')}: {x}" for x in validate_rights_decision(row))
    for row in source_units:
        errs=validate_source_unit(row)
        if str(row.get("source_record_key") or "") not in source_record_keys:
            errs.append("source_record_key is absent from package source_record set")
        contract_errors.extend(f"source_unit {row.get('source_unit_id')}: {x}" for x in errs)
        if not errs: unit_by_id[row['source_unit_id']]=row
    assertion_by_id={}
    for row in assertions:
        unit=unit_by_id.get(row.get('source_unit_id'))
        if unit is None: contract_errors.append(f"assertion {row.get('assertion_id')}: source unit absent from package")
        else:
            contract_errors.extend(f"assertion {row.get('assertion_id')}: {x}" for x in validate_assertion(row,source_unit=unit))
            if row.get("verification_status") != "NOT_VERIFIED": contract_errors.append(f"assertion {row.get('assertion_id')}: Turn 4 packages accept NOT_VERIFIED assertions only")
            if row.get("subject_candidate_id") is not None or row.get("object_candidate_id") is not None: contract_errors.append(f"assertion {row.get('assertion_id')}: extractor cannot resolve candidate IDs")
            assertion_by_id[row.get("assertion_id")]=row
    recall_assertion_by_id={}
    for row in recall_assertions:
        unit=unit_by_id.get(row.get("source_unit_id"))
        if unit is None: contract_errors.append(f"recall assertion {row.get('assertion_id')}: source unit absent from package")
        else:
            contract_errors.extend(f"recall assertion {row.get('assertion_id')}: {x}" for x in validate_assertion(row,source_unit=unit))
            if row.get("verification_status") != "NOT_VERIFIED": contract_errors.append(f"recall assertion {row.get('assertion_id')}: must remain NOT_VERIFIED")
            if row.get("subject_candidate_id") is not None or row.get("object_candidate_id") is not None: contract_errors.append(f"recall assertion {row.get('assertion_id')}: recall cannot resolve candidate IDs")
            recall_assertion_by_id[row.get("assertion_id")]=row
    for row in recall_reconciliation_rows:
        if row.get("automatic_action") is not False: contract_errors.append("blind recall reconciliation automatic_action must be false")
        state=row.get("reconciliation_state")
        if state not in {"PRIMARY_AND_RECALL_EXACT","SAME_EVIDENCE_SEMANTIC_DISAGREEMENT","PRIMARY_ONLY","RECALL_ONLY_CANDIDATE"}: contract_errors.append(f"invalid recall reconciliation state: {state}")
    for case in review_cases:
        contract_errors.extend(f"semantic review {case.get('review_case_id')}: {x}" for x in validate_review_case(case))
        for aid in case.get("assertion_ids") or []:
            if aid not in assertion_by_id: contract_errors.append(f"semantic review {case.get('review_case_id')}: primary assertion {aid} absent")
        for aid in case.get("recall_assertion_ids") or []:
            if aid not in recall_assertion_by_id: contract_errors.append(f"semantic review {case.get('review_case_id')}: recall assertion {aid} absent")
    for event in verification_events:
        assertion=assertion_by_id.get(event.get("assertion_id"))
        if assertion is None:
            contract_errors.append(f"verification {event.get('verification_id')}: assertion absent from package")
            continue
        unit=unit_by_id.get(assertion.get("source_unit_id"))
        contract_errors.extend(f"verification {event.get('verification_id')}: {x}" for x in validate_verification_event(event,assertion=assertion,source_unit=unit))
    if contract_errors: raise ValueError("Turn 5 source-unit/assertion/verification/full-text contract validation failed: "+"; ".join(contract_errors[:30]))
    counts={
        "source_records":_atomic_jsonl(output_dir/"sources/source_records.jsonl",sources),
        "source_observations":_atomic_jsonl(output_dir/"sources/source_observations.jsonl",observations),
        "run_artifacts":_atomic_jsonl(output_dir/"sources/run_artifacts.jsonl",artifacts),
        "fulltext_artifacts":_atomic_jsonl(output_dir/"sources/fulltext_artifacts.jsonl",fulltext_artifacts),
        "rights_decisions":_atomic_jsonl(output_dir/"rights/rights_decisions.jsonl",rights_decisions),
        "source_units":_atomic_jsonl(output_dir/"source_units/source_units.jsonl",source_units),
        "candidates":_atomic_jsonl(output_dir/"candidates/candidates.jsonl",candidates),
        "candidate_aliases":_atomic_jsonl(output_dir/"candidates/candidate_aliases.jsonl",candidate_aliases),
        "candidate_linkage_evidence":_atomic_jsonl(output_dir/"candidates/candidate_linkage_evidence.jsonl",candidate_linkage),
        "candidate_assertion_links":_atomic_jsonl(output_dir/"candidates/candidate_assertion_links.jsonl",candidate_assertion_links),
        "identity_resolution_cases":_atomic_jsonl(output_dir/"candidates/identity_resolution_cases.jsonl",identity_cases),
        "identity_lookups":_atomic_jsonl(output_dir/"09d_comparisons/identity_lookups.jsonl",identity_lookups),
        "assertions":_atomic_jsonl(output_dir/"assertions/assertions.jsonl",assertions),
        "assertion_quarantine":_atomic_jsonl(output_dir/"assertions/extraction_quarantine.jsonl",assertion_quarantine),
        "verification_events":_atomic_jsonl(output_dir/"verification/verification_events.jsonl",verification_events),
        "verification_quarantine":_atomic_jsonl(output_dir/"verification/verification_quarantine.jsonl",verification_quarantine),
        "recall_assertions":_atomic_jsonl(output_dir/"semantic_review/recall_assertions.jsonl",recall_assertions),
        "recall_quarantine":_atomic_jsonl(output_dir/"semantic_review/recall_quarantine.jsonl",recall_quarantine),
        "recall_reconciliation":_atomic_jsonl(output_dir/"semantic_review/recall_reconciliation.jsonl",recall_reconciliation_rows),
        "semantic_review_cases":_atomic_jsonl(output_dir/"semantic_review/review_cases.jsonl",review_cases),
        "09d_comparisons":_atomic_jsonl(output_dir/"09d_comparisons/comparisons.jsonl",comparison_rows),
        "conflicts":_atomic_jsonl(output_dir/"conflicts/conflicts.jsonl",[]),
    }
    counts["identity_candidates"] = sum(1 for x in candidates if x.get("source_table")=="frontier.assertion_entity_surface")
    provenance_metrics={
        "source_units":len(source_units),
        "source_unit_locator_closed":sum(1 for u in source_units if isinstance(u.get("locator"),dict) and u.get("locator")),
        "source_unit_raw_hash_closed":sum(1 for u in source_units if u.get("content_sha256")),
        "source_unit_publication_year_closed":sum(1 for u in source_units if u.get("publication_year") is not None),
        "source_unit_edition_version_closed":sum(1 for u in source_units if u.get("edition_or_version")),
        "source_unit_source_era_closed":sum(1 for u in source_units if u.get("source_era")),
        "assertions":len(assertions),
        "assertion_evidence_closed":sum(1 for a in assertions if (a.get("source_unit_id") in unit_by_id and not validate_assertion(a,source_unit=unit_by_id[a.get("source_unit_id")]))) ,
        "assertion_verified_entailed":sum(1 for v in verification_events if v.get("verdict")=="ENTAILED"),
        "assertion_not_verified":sum(1 for a in assertions if a.get("verification_status")=="NOT_VERIFIED"),
        "verification_events":len(verification_events),
        "recall_assertions":len(recall_assertions),
        "recall_reconciliation_counts":dict(recall_reconciliation.get("counts") or {}),
        "semantic_review_cases":len(review_cases),
        "identity_candidates":len([x for x in candidates if x.get("source_table")=="frontier.assertion_entity_surface"]),
        "identity_resolution_cases":len(identity_cases),
        "09d_identity_lookups":len(identity_lookups),
        "09d_comparisons":len(comparison_rows),
        "09d_comparison_classification_counts":{c:sum(1 for x in comparison_rows if x.get("classification")==c) for c in sorted({str(x.get("classification")) for x in comparison_rows if x.get("classification")})},
        "semantic_review_reason_counts":dict((semantic_routing_result or {}).get("metrics",{}).get("reason_counts",{})),
        "verification_verdict_counts":{v:sum(1 for e in verification_events if e.get("verdict")==v) for v in ("ENTAILED","NOT_ENTAILED","PARTIAL","AMBIGUOUS","PROVENANCE_INCOMPLETE")},
        "verification_risk_counts":{r:sum(1 for e in verification_events if e.get("risk_tier")==r) for r in ("LOW","MEDIUM","HIGH","CRITICAL")},
        "assertion_extraction_quarantined":len(assertion_quarantine),
        "fulltext_artifacts":len(fulltext_artifacts),
        "fulltext_artifact_hash_closed":sum(1 for a in fulltext_artifacts if a.get("artifact_sha256")),
        "fulltext_text_mining_allowed":sum(1 for a in fulltext_artifacts if a.get("text_mining_allowed") is True),
        "rights_decisions":len(rights_decisions),
        "rights_text_mining_known":sum(1 for r in rights_decisions if r.get("text_mining_allowed") is not None),
        "rights_redistribution_known":sum(1 for r in rights_decisions if r.get("redistribution_status") not in (None,"UNKNOWN")),
        "source_scope_counts":{scope:sum(1 for u in source_units if u.get("source_scope")==scope) for scope in sorted({u.get("source_scope") for u in source_units if u.get("source_scope")})},
    }
    package_identity={
        "source_projection_manifest_sha256":sha256_file(warehouse_dir/"warehouse_projection_manifest.json"),
        "production_code_manifest_sha256":code_manifest(Path(__file__).resolve().parents[1])["sha256"],
        "assertion_interpretation_ids":sorted(str(a.get("interpretation_id")) for a in assertions),
        "verification_ids":sorted(str(v.get("verification_id")) for v in verification_events),
        "recall_interpretation_ids":sorted(str(a.get("interpretation_id")) for a in recall_assertions),
        "semantic_review_case_ids":sorted(str(c.get("review_case_id")) for c in review_cases),
        "identity_case_ids":sorted(str(c.get("identity_case_id")) for c in identity_cases),
        "identity_lookup_ids":sorted(str(c.get("identity_lookup_id")) for c in identity_lookups),
        "09d_comparison_ids":sorted(str(c.get("comparison_id")) for c in comparison_rows),
    }
    package_id="AUDIT09D:"+hashlib.sha256(json.dumps(package_identity,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest()[:32]
    manifest={
        "audit_package_schema_version":PACKAGE_SCHEMA_VERSION,
        "package_id":package_id,
        "package_kind":PACKAGE_KIND,
        "created_at":utc_now(),
        "source_run_id":runs[0].get("run_id"),
        "source_projection_manifest_sha256":sha256_file(warehouse_dir/"warehouse_projection_manifest.json"),
        "09d_authority_reference_sha256":sha256_file(authority_reference),
        "09d_repository":authority.get("repository"),
        "09d_ref":authority.get("ref"),
        "09d_git_tree_sha":authority.get("git_tree_sha"),
        "direct_09d_insert_allowed":False,
        "current_09d_s02_direct_insert_compatible":False,
        "current_09d_s02_incompatibility_reason":"implemented lane_package_intake.package_kind accepts only FROZEN_PARENT_BACKFILL",
        "canonical_authority":False,
        "automatic_selection_allowed":False,
        "canonical_internal_eligible":False,
        "generation_eligible":False,
        "public_eligible":False,
        "mass_extraction_authorized":False,
        "source_unit_schema_version":SOURCE_UNIT_SCHEMA_VERSION,
        "assertion_schema_version":ASSERTION_SCHEMA_VERSION,
        "verification_schema_version":VERIFICATION_SCHEMA_VERSION,
        "source_unit_segmenter_schema_version":SEGMENTER_SCHEMA_VERSION,
        "fulltext_artifact_schema_version":FULLTEXT_ARTIFACT_SCHEMA_VERSION,
        "rights_schema_version":RIGHTS_SCHEMA_VERSION,
        "source_unit_contract_status":"FROZEN",
        "assertion_contract_status":"FROZEN",
        "assertion_engine_status":"IMPLEMENTED_OFFLINE_CERTIFIED_UNVERIFIED_OUTPUT",
        "assertion_verifier_status":"IMPLEMENTED_OFFLINE_CERTIFIED_APPEND_ONLY",
        "assertion_output_policy":"EXTRACTOR_ASSERTIONS_REMAIN_NOT_VERIFIED",
        "verification_overlay_policy":"APPEND_ONLY_VERIF_EVENTS",
        "semantic_specialist_lanes_status":"IMPLEMENTED_OFFLINE_CERTIFIED",
        "risk_router_status":"IMPLEMENTED_OFFLINE_CERTIFIED",
        "semantic_gold_gate_status":"PASS_OFFLINE_HAND_AUTHORED_CONTRACT",
        "blind_recall_status":"IMPLEMENTED_OFFLINE_CERTIFIED_CONTRACT_MODEL_PENDING",
        "blind_recall_reconciliation_status":"IMPLEMENTED_OFFLINE_CERTIFIED",
        "blind_recall_run_status":(blind_recall_result or {}).get("status","NOT_RUN_IN_PACKAGE"),
        "blind_recall_metrics":(blind_recall_result or {}).get("metrics",{}),
        "semantic_review_router_status":"IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE",
        "semantic_review_router_run_status":(semantic_routing_result or {}).get("status","NOT_RUN_IN_PACKAGE"),
        "semantic_factory_status":"IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE",
        "semantic_factory_run_status":(semantic_factory_result or {}).get("status","NOT_RUN_IN_PACKAGE"),
        "semantic_factory_run_id":(semantic_factory_result or {}).get("semantic_run_id"),
        "semantic_review_router_metrics":(semantic_routing_result or {}).get("metrics",{}),
        "single_semantic_verifier_authority":True,
        "blind_semantic_provider_status":"INTERFACE_IMPLEMENTED_BACKEND_NOT_CERTIFIED",
        "verification_run_status":(verification_result or {}).get("status","NOT_RUN_IN_PACKAGE"),
        "verification_metrics":(verification_result or {}).get("metrics",{}),
        "assertion_engine_run_status":(assertion_engine_result or {}).get("status","NOT_RUN_IN_PACKAGE"),
        "assertion_engine_metrics":(assertion_engine_result or {}).get("metrics",{}),
        "deterministic_structured_assertion_provider_status":"IMPLEMENTED_OFFLINE_CERTIFIED",
        "general_text_assertion_provider_status":"INTERFACE_IMPLEMENTED_BACKEND_NOT_CERTIFIED",
        "source_unit_segmenter_status":"IMPLEMENTED_OFFLINE_CERTIFIED",
        "source_unit_layer_status":"IMPLEMENTED_OFFLINE_CERTIFIED",
        "fulltext_acquisition_status":"IMPLEMENTED_OFFLINE_CERTIFIED_PUBLIC_CANARY_PENDING",
        "fulltext_public_host_canary_status":"PENDING",
        "rights_dimensions_separate":True,
        "raw_fulltext_payloads_embedded_in_audit_package":False,
        "candidate_resolution_status":"IMPLEMENTED_OFFLINE_CERTIFIED_NONAUTHORITATIVE",
        "candidate_resolution_run_status":(turn6_result or {}).get("status","NOT_RUN_IN_PACKAGE"),
        "candidate_to_canonical_assignment_performed":False,
        "09d_comparator_status":"IMPLEMENTED_OFFLINE_CERTIFIED_REAL_DATABASE_PENDING",
        "09d_comparator_run_status":((turn6_result or {}).get("09d_comparison") or {}).get("status","NOT_RUN_IN_PACKAGE"),
        "09d_comparator_source_kind":((turn6_result or {}).get("09d_comparison") or {}).get("snapshot_source_kind"),
        "actual_09d_database_bound":bool(((turn6_result or {}).get("09d_comparison") or {}).get("actual_09d_database_bound",False)),
        "09d_database_sha256":((turn6_result or {}).get("09d_comparison") or {}).get("09d_database_sha256"),
        "09d_mutation_performed":False,
        "conflict_engine_status":"NOT_IMPLEMENTED",
        "frontier_ready":False,
        "provenance_metrics":provenance_metrics,
        "counts":counts,
    }
    errs=validate_package_manifest(manifest)
    if errs: raise ValueError("package manifest authority validation failed: "+"; ".join(errs))
    _atomic_json(output_dir/"manifest.json",manifest)
    validation={"status":"PASS_TURN6_READONLY_COMPARATOR" if turn6_result is not None else "PASS_TURN5_SEMANTIC_VERIFIER","candidate_errors":[],"package_manifest_errors":[],"source_unit_assertion_contract_errors":contract_errors,"source_unit_contract_frozen":True,"assertion_contract_frozen":True,"source_unit_segmenter_complete":True,"fulltext_acquisition_offline_certified":True,"public_host_fulltext_canary_complete":False,"assertion_engine_complete":True,"assertion_verifier_complete":True,"assertions_must_remain_not_verified":True,"verification_events_append_only":True,"blind_recall_non_authoritative":True,"semantic_review_router_non_authoritative":True,"direct_09d_insert_allowed":False}
    _atomic_json(output_dir/"validation/turn5_semantic_verifier_validation.json",validation)
    if turn6_result is not None:
        _atomic_json(output_dir/"validation/turn6_readonly_comparator_validation.json",{
            "status":"PASS_TURN6_READONLY_COMPARATOR",
            "candidate_resolution_performed":True,
            "candidate_to_canonical_assignment_performed":False,
            "09d_comparison_performed":True,
            "09d_mutation_performed":False,
            "actual_09d_database_bound":bool(((turn6_result.get("09d_comparison") or {}).get("actual_09d_database_bound",False))),
            "direct_09d_insert_allowed":False,
        })
    # Keep the Turn-3 segmentation proof as a compatibility artifact for readers that
    # only need the evidence-unit/full-text gate.
    turn3_validation={"status":"PASS_TURN3_SEGMENTATION","source_unit_segmenter_complete":True,"fulltext_acquisition_offline_certified":True,"public_host_fulltext_canary_complete":False,"direct_09d_insert_allowed":False}
    _atomic_json(output_dir/"validation/turn3_segmentation_validation.json",turn3_validation)
    return manifest
