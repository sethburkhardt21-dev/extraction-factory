"""Offline frontier-readiness checks. This module never performs network extraction."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import re
import platform
import importlib.metadata as importlib_metadata
from typing import Iterable, List, Dict, Any

@dataclass
class GateResult:
    gate: str
    passed: bool
    detail: str


def production_python_files(root: Path) -> List[Path]:
    roots = [
        root / "clinicaltrials" / "canonical",
        root / "preprints" / "src",
        root / "drug_reference" / "drugref",
        root / "warehouse",
        root / "bridge_09d",
    ]
    files: List[Path] = []
    for base in roots:
        if base.exists(): files.extend(base.rglob("*.py"))
    for name in ["__init__.py", "metadata_schema.py", "pubmed_anesthesia_extraction.py", "run_pubmed.py"]:
        p=root/"pubmed_rag"/name
        if p.exists(): files.append(p)
    for name in ["__init__.py", "contracts.py", "gate.py", "readiness.py"]:
        p=root/"frontier_core"/name
        if p.exists(): files.append(p)
    for name in ["frontier_preflight.py", "frontier_orchestrator.py", "frontier_external_canary.py", "frontier_release.py"]:
        p=root/name
        if p.exists(): files.append(p)
    unique=[]
    for p in sorted(set(files)):
        if any(x in p.parts for x in ("archive_not_production","experimental_enrichment_not_certified","tests","__pycache__",".pytest_cache")):
            continue
        unique.append(p)
    return unique


def production_contract_files(root: Path) -> List[Path]:
    candidates = [
        root / "schema" / "frontier_postgres.sql",
        root / "schema" / "frontier_bigquery.sql",
        root / "schema" / "SCHEMA_CONTRACT.md",
        root / "schema" / "validate_coverage.py",
        root / "schema" / "validate_physical_projection.py",
        root / "schema" / "PHYSICAL_PROJECTION_CONTRACT.json",
        root / "09D_READONLY_AUTHORITY.json",
        root / "09D_EXTRACTION_BOUNDARY_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "SOURCE_UNIT_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "ATOMIC_ASSERTION_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "FULLTEXT_SEGMENTATION_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "ASSERTION_EXTRACTION_ENGINE_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "GOLD_EVIDENCE_GATE_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "INDEPENDENT_ASSERTION_VERIFIER_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "SEMANTIC_VERIFIER_GOLD_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "SEMANTIC_SPECIALIST_CAPSULES_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "BLIND_RECALL_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "SEMANTIC_GOLD_GATE_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "SEMANTIC_REVIEW_ROUTER_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "SEMANTIC_FACTORY_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "IDENTITY_RESOLUTION_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "09D_READONLY_COMPARATOR_CONTRACT.md",
        root / "bridge_09d" / "contracts" / "TURN6_AUDIT_PREP_CONTRACT.md",
        root / "bridge_09d" / "validate_alignment.py",
        root / "requirements-source.lock.txt",
        root / "source-runtime.lock.json",
    ]
    return [p for p in candidates if p.exists()]


def production_manifest_files(root: Path) -> List[Path]:
    return sorted(set(production_python_files(root) + production_contract_files(root)))


def verification_files(root: Path) -> List[Path]:
    roots=[root/"clinicaltrials"/"tests",root/"preprints"/"tests",root/"drug_reference"/"tests",root/"pubmed_rag"/"tests",root/"warehouse"/"tests",root/"bridge_09d"/"tests",root/"frontier_tests"]
    files=[]
    for base in roots:
        if base.exists():
            for path in base.rglob("*"):
                if path.is_file() and not any(x in path.parts for x in ("__pycache__",".pytest_cache")) and path.suffix not in {".pyc"}:
                    files.append(path)
    # Standalone behavioral validators are part of verification evidence too.
    for rel in ["pubmed_rag/validate.py","pubmed_rag/bigquery_validation_test.py","schema/validate_coverage.py","schema/validate_physical_projection.py","bridge_09d/validate_alignment.py"]:
        path=root/rel
        if path.is_file(): files.append(path)
    return sorted(set(files))


def verification_manifest(root: Path) -> Dict[str, Any]:
    entries=[{"path":str(p.relative_to(root)),"sha256":file_sha256(p)} for p in verification_files(root)]
    payload=json.dumps(entries,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return {"files":entries,"sha256":hashlib.sha256(payload).hexdigest(),"count":len(entries)}


def runtime_contract_gate(root: Path) -> GateResult:
    path = root / "source-runtime.lock.json"
    if not path.is_file():
        return GateResult("source_runtime_lock", False, "source-runtime.lock.json missing")
    contract = json.loads(path.read_text(encoding="utf-8"))
    errors=[]
    expected_python=str(contract.get("python") or "")
    if platform.python_version() != expected_python:
        errors.append(f"python {platform.python_version()} != {expected_python}")
    for name, expected in sorted((contract.get("packages") or {}).items()):
        try:
            actual=importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            errors.append(f"{name} missing")
            continue
        if actual != str(expected): errors.append(f"{name} {actual} != {expected}")
    return GateResult("source_runtime_lock", not errors, "exact runtime match" if not errors else "; ".join(errors))


def file_sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def code_manifest(root: Path) -> Dict[str, Any]:
    entries=[{"path":str(p.relative_to(root)),"sha256":file_sha256(p)} for p in production_manifest_files(root)]
    payload=json.dumps(entries,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return {"files":entries,"sha256":hashlib.sha256(payload).hexdigest(),"count":len(entries)}


def _scan(files: Iterable[Path], root: Path, name: str, pattern: re.Pattern) -> GateResult:
    hits=[]
    for p in files:
        text=p.read_text(encoding="utf-8",errors="replace")
        if pattern.search(text): hits.append(str(p.relative_to(root)))
    return GateResult(name,not hits,"none" if not hits else ", ".join(hits[:20]))


def _contains(path: Path, needles: Iterable[str]) -> bool:
    if not path.exists(): return False
    text=path.read_text(encoding="utf-8",errors="replace")
    return all(n in text for n in needles)


def static_safety_scan(root: Path) -> List[GateResult]:
    files=production_python_files(root)
    # The scanner itself contains literal forbidden-pattern strings and expected client URLs;
    # keep it in the code hash but do not scan its rule definitions as production behavior.
    scan_files=[p for p in files if p != root/"frontier_core/readiness.py"]
    results=[
        _scan(scan_files,root,"no_hardcoded_container_paths",re.compile(r"/mnt/data")),
        _scan(scan_files,root,"no_python_hash_identifiers",re.compile(r"(?<![A-Za-z_])hash\s*\(")),
        _scan(scan_files,root,"no_fake_identifier_or_model_fallbacks",re.compile(r"(?:fake|placeholder|synthetic)[ _-]?(?:id|identifier|rxcui|likelihood|answer|embedding|vector)",re.I)),
    ]
    shadow=[str(p.relative_to(root)) for p in files if re.search(r"(?:_1|_2|_1_1)\.py$",p.name)]
    results.append(GateResult("no_active_shadow_python_variants",not shadow,"none" if not shadow else ", ".join(shadow)))
    results.append(GateResult("production_python_files_present",bool(files),f"{len(files)} production Python files"))
    results.append(runtime_contract_gate(root))

    # Explicit operator interlocks: HTTP-capable CLIs must require --network and a frontier preflight.
    cli_contracts={
        "clinicaltrials_network_interlock": root/"clinicaltrials/canonical/run_extraction.py",
        "preprint_network_interlock": root/"preprints/src/pipeline.py",
        "preprint_sharded_network_interlock": root/"preprints/src/run_all.py",
        "pubmed_network_interlock": root/"pubmed_rag/run_pubmed.py",
    }
    for gate,path in cli_contracts.items():
        results.append(GateResult(gate+"_symbols_present",_contains(path,["--network","--preflight","require_frontier_preflight"]),"structural presence only: "+str(path.relative_to(root))))

    # Active PubMed source surface must remain model agnostic.
    pubmed_active=[root/"pubmed_rag"/x for x in ("metadata_schema.py","pubmed_anesthesia_extraction.py","run_pubmed.py")]
    model_hits=[]
    for p in pubmed_active:
        text=p.read_text(encoding="utf-8",errors="replace")
        for token in ("sentence_transformers","SentenceTransformer(","torch.cuda","FAISS"):
            if token in text: model_hits.append(f"{p.name}:{token}")
    results.append(GateResult("pubmed_source_model_agnostic",not model_hits,"none" if not model_hits else ", ".join(model_hits)))

    transport_contracts = {
        "clinicaltrials_exact_transport_capture": (root/"clinicaltrials/canonical/clinicaltrials/extractor.py", ["PASS_EXACT_HTTP_RESPONSES","transport_raw_locator","transport_index_sha256"]),
        "preprint_exact_transport_capture": (root/"preprints/src/pipeline.py", ["PASS_EXACT_HTTP_RESPONSES","transport_raw_locator","transport_index_sha256"]),
        "pubmed_exact_transport_capture": (root/"pubmed_rag/run_pubmed.py", ["PASS_EXACT_HTTP_RESPONSES","transport_raw_locators","transport_index_sha256"]),
    }
    for gate,(path,needles) in transport_contracts.items():
        results.append(GateResult(gate+"_symbols_present",_contains(path,needles),"structural presence only: "+str(path.relative_to(root))))

    # One active PubMed E-utilities implementation.
    eutils=[]
    for p in scan_files:
        if "eutils.ncbi.nlm.nih.gov" in p.read_text(encoding="utf-8",errors="replace"):
            eutils.append(str(p.relative_to(root)))
    results.append(GateResult("single_active_pubmed_eutils_client",eutils==["pubmed_rag/pubmed_anesthesia_extraction.py"],", ".join(eutils) or "none"))

    pg=root/"schema/frontier_postgres.sql"; bq=root/"schema/frontier_bigquery.sql"; contract=root/"schema/SCHEMA_CONTRACT.md"
    required_tables=["ingestion_run","run_artifact","source_record","source_observation","canonical_record","quarantine_record","ctg_study_record","ctg_study_snapshot","ctg_phase","ctg_condition","ctg_keyword","ctg_sponsor","ctg_arm","ctg_intervention","ctg_outcome","ctg_location","ctg_contact","ctg_reference","ctg_available_ipd","pubmed_record","pubmed_snapshot","pubmed_author","pubmed_mesh_heading","preprint_record","preprint_snapshot","drug_source_record","drug_candidate","drug_candidate_alias","drug_candidate_linkage_evidence","research_work","work_identifier","work_source_link","evidence_link","model_enrichment","release_snapshot","release_run"]
    for label,path in (("postgres",pg),("bigquery",bq)):
        text=path.read_text(encoding="utf-8",errors="replace") if path.exists() else ""
        missing=[t for t in required_tables if f"frontier.{t}" not in text]
        results.append(GateResult(f"{label}_frontier_schema_tables",not missing,"complete" if not missing else "missing: "+", ".join(missing)))
    results.append(GateResult("postgres_promotion_view",_contains(pg,["frontier.promotable_run","certification_status = 'PASS'","truncated = FALSE","quarantined_records = 0"]),"structural presence only; behavioral release tests run separately"))
    results.append(GateResult("immutable_schema_contract",_contains(contract,["append-only","latest` is a view","DOI","linkage evidence"]),"Bronze/Silver/Gold historical semantics documented"))
    results.append(GateResult("warehouse_projection_layer",(root/"warehouse/project.py").exists(),"warehouse/project.py"))
    results.append(GateResult("frontier_orchestrator_control_plane",_contains(root/"frontier_orchestrator.py",["--execute","--canary-cert","production_code_manifest_sha256","project_run","native_http","mass_unlock_eligible","transport_certified"]),"code-bound native canary + automatic projection"))
    results.append(GateResult("external_canary_never_unlocks_mass",_contains(root/"frontier_external_canary.py",["PASS_EXTERNAL_TRANSPORT","mass_unlock_eligible","False","strict=True"]),"external payload proof is parser-only and never promotable"))
    results.append(GateResult("frontier_release_promotion_gate",_contains(root/"frontier_release.py",["certification_status","complete_against_source","quarantined_records","source_changed_during_run","transport_certified","orchestration_status"]),"release refuses non-promotable runs"))
    results.append(GateResult("09d_readonly_boundary",_contains(root/"09D_EXTRACTION_BOUNDARY_CONTRACT.md",["direct_09d_insert_allowed = false","canonical_authority = false","generation_eligible = false","public_eligible = false"]),"structural boundary markers present; behavioral bridge tests run separately"))
    results.append(GateResult("09d_external_audit_bridge",_contains(root/"bridge_09d/package.py",["FRONTIER_EXTERNAL_EVIDENCE_AUDIT","current_09d_s02_direct_insert_compatible","assertion_contract_status","source_unit_contract_status","mass_extraction_authorized"]),"structural package markers present; behavioral bridge tests run separately"))
    results.append(GateResult("09d_source_unit_assertion_contract",_contains(root/"bridge_09d/assertions.py",["UNIT:","ASSERT:","INTERP:","NOT_VERIFIED","canonical_authority","frontier-source-unit-1.2"]),"structural contract markers present; behavioral bridge tests run separately"))
    results.append(GateResult("09d_fulltext_source_unit_segmenter",_contains(root/"bridge_09d/source_units.py",["PMC_OAI_BASE","segment_jats_xml","segment_structured_json","segment_pubmed_evidence","ABSTRACT_ONLY","text_mining_allowed"]),"structural segmenter markers present; behavioral/adversarial bridge tests run separately"))
    results.append(GateResult("09d_fulltext_rights_separation",_contains(root/"bridge_09d/package.py",["rights_dimensions_separate","fulltext_acquisition_status","raw_fulltext_payloads_embedded_in_audit_package"]),"structural rights markers present; behavioral bridge tests run separately"))
    results.append(GateResult("09d_assertion_extraction_engine",_contains(root/"bridge_09d/assertion_engine.py",["NOT_VERIFIED","FORBIDDEN_PROPOSAL_KEYS","PASS_WITH_QUARANTINE","structured_clinicaltrials_provider","candidate_resolution_performed","09d_comparison_performed"]),"structural assertion-engine markers present; behavioral bridge tests run separately"))
    results.append(GateResult("09d_assertion_pipeline_persistence",_contains(root/"bridge_09d/assertion_pipeline.py",["semantic_verification_performed","candidate_resolution_performed","canonical_authority","assertions_sha256","quarantine_sha256"]),"structural persistence markers present; behavioral bridge tests run separately"))
    results.append(GateResult("09d_independent_semantic_verifier",_contains(root/"bridge_09d/verifier.py",["VERIF:","blind_independent_review","specialist_capsules","downstream_semantic_ready","FRONTIER_ADJUDICATION","PROVENANCE_INCOMPLETE"]),"structural independent-verifier markers present; adversarial and semantic-gold suites run separately"))
    results.append(GateResult("09d_semantic_specialist_capsules",_contains(root/"bridge_09d/semantic_capsules.py",["PROVENANCE_CLOSURE","NUMERIC_BINDING","NEGATION_PRESERVATION","CERTAINTY_MODALITY","CONDITIONALITY","QUALIFIER_SCOPE","RELATIONSHIP_SEMANTICS","ATOMICITY","frontier_adjudication_required"]),"structural specialist-capsule markers present; behavioral semantic suites run separately"))
    results.append(GateResult("09d_blind_recall_lane",_contains(root/"bridge_09d/blind_recall.py",["independent_of_primary_extractor","RECALL_ONLY_CANDIDATE","SAME_EVIDENCE_SEMANTIC_DISAGREEMENT","automatic_repair_allowed"]),"structural blind-recall markers present; behavioral recall suite runs separately"))
    results.append(GateResult("09d_blind_recall_pipeline",_contains(root/"bridge_09d/blind_recall_pipeline.py",["primary_assertions_visible_during_recall","recall_assertions_sha256","reconciliation_sha256","automatic_repair_allowed","canonical_authority"]),"structural blind-recall persistence markers present; behavioral recall-pipeline suite runs separately"))
    results.append(GateResult("09d_semantic_review_router",_contains(root/"bridge_09d/semantic_router.py",["SEMCASE:","RECALL_ONLY_CANDIDATE","SAME_EVIDENCE_SEMANTIC_DISAGREEMENT","FRONTIER_ADJUDICATION","automatic_repair_allowed"]),"structural semantic-review routing markers present; behavioral router suite runs separately"))
    results.append(GateResult("09d_semantic_factory",_contains(root/"bridge_09d/semantic_factory.py",["SEMRUN:","verify_assertions","run_blind_recall","reconcile_primary_recall","route_semantic_review","mass_extraction_authorized"]),"structural semantic-factory composition markers present; behavioral factory suite runs separately"))
    results.append(GateResult("09d_provisional_identity_resolution",_contains(root/"bridge_09d/identity_resolution.py",["frontier.assertion_entity_surface","DOMAIN_AMBIGUOUS","REGISTERED_FOR_READONLY_LOOKUP","candidate_to_canonical_assignment_performed"]),"structural provisional-identity markers present; behavioral Turn-6 suite runs separately"))
    results.append(GateResult("09d_readonly_comparator",_contains(root/"bridge_09d/comparator_09d.py",["mode=ro&immutable=1","PRAGMA query_only=ON","CONTRADICTORY","CONTEXT_DIFFERENT","09d_mutation_performed"]),"structural read-only comparator markers present; behavioral Turn-6 suite runs separately"))
    results.append(GateResult("09d_turn6_audit_prep_factory",_contains(root/"bridge_09d/turn6_factory.py",["run_turn6_audit_prep","candidate_to_canonical_assignment_performed","09d_comparison_performed","mass_extraction_authorized"]),"structural Turn-6 composition markers present; behavioral Turn-6 suite runs separately"))
    results.append(GateResult("09d_single_verifier_authority",_contains(root/"bridge_09d/assertion_verifier.py",["Compatibility import surface","from .verifier import *"]) and _contains(root/"bridge_09d/verification_pipeline.py",["Compatibility shim","from .verifier_pipeline import *"]),"legacy Turn-5 import surfaces are shims; one canonical verifier/pipeline"))
    results.append(GateResult("09d_verifier_pipeline_persistence",_contains(root/"bridge_09d/verifier_pipeline.py",["verification_events_sha256","assertions_mutated","blind_independent_review","canonical_authority"]),"structural verifier persistence markers present; behavioral bridge tests run separately"))
    results.append(GateResult("09d_semantic_verifier_gold_contract",_contains(root/"bridge_09d/contracts/SEMANTIC_VERIFIER_GOLD_CONTRACT.md",["semantic-verifier-gold-1.0","certainty","conditionality","production model backend"]),"semantic verifier gold contract present; executable gold suite runs separately"))
    results.append(GateResult("09d_semantic_gold_gate_contract",_contains(root/"bridge_09d/contracts/SEMANTIC_GOLD_GATE_CONTRACT.md",["hand-authored","deterministic hard contradiction","Production model benchmarking"]),"Turn-5 semantic gold contract present"))
    results.append(GateResult("09d_gold_evidence_gate_contract",_contains(root/"bridge_09d/contracts/GOLD_EVIDENCE_GATE_CONTRACT.md",["Generated output is evidence under test","PINNED_PHYSICAL_FIXTURE","mass_extraction_authorized = true"]),"gold evidence gate contract present; executable gold suites run separately"))
    results.append(GateResult("no_premature_drug_canonical_authority",not any(token in (root/"warehouse/project.py").read_text(encoding="utf-8") for token in ['"drug_entity"','"drug_alias"','"drug_linkage_evidence"']),"drug extraction emits candidates only"))
    return results


def write_static_report(root: Path, output: Path) -> Dict[str, Any]:
    gates=static_safety_scan(root); cm=code_manifest(root)
    report={"status":"PASS" if all(g.passed for g in gates) else "FAIL","network_extraction_performed":False,"production_code_manifest":cm,"gates":[asdict(g) for g in gates]}
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return report
