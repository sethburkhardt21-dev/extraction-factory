"""Independent blind-recall lane for semantic coverage auditing.

Recall workers see immutable source units, never the primary extractor's outputs.
Their assertions remain NOT_VERIFIED and are reconciled only as coverage evidence;
they cannot directly repair, promote, or overwrite primary assertions.
"""
from __future__ import annotations

import hashlib,json
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

from .assertion_engine import EngineConfig, build_model_request, extract_assertions

RecallProposalProvider=Callable[[Mapping[str,Any]],Sequence[Mapping[str,Any]]]

RECALL_SCHEMA_VERSION="frontier-blind-recall-1.0"


def build_blind_recall_request(source_unit:Mapping[str,Any])->Dict[str,Any]:
    req=build_model_request(source_unit)
    req["recall_task"]={
        "independent_of_primary_extractor":True,
        "enumerate_all_clinically_meaningful_atomic_assertions":True,
        "do_not_infer_missing_context":True,
        "preserve_numeric_qualifier_relationship_context":True,
        "authority_granted":False,
    }
    blob=json.dumps(req,sort_keys=True)
    for forbidden in ("primary_assertions","extractor_provenance","interpretation_id"):
        if forbidden in blob: raise RuntimeError(f"blind recall request leaked {forbidden}")
    return req


def run_blind_recall(source_units:Iterable[Mapping[str,Any]],*,provider:RecallProposalProvider,config:EngineConfig)->Dict[str,Any]:
    # The recall provider receives a purpose-built blind packet, never a primary assertion
    # or extractor interpretation. The assertion engine still owns conversion, IDs, and
    # authority-state enforcement.
    def blind_provider(unit:Mapping[str,Any]):
        return provider(build_blind_recall_request(unit))
    result=extract_assertions(source_units,provider=blind_provider,config=config)
    result={**result,"blind_recall_schema_version":RECALL_SCHEMA_VERSION,"independent_of_primary_extractor":True,
            "recall_outputs_are_unverified":True,"primary_mutation_performed":False,"authority_granted":False}
    return result


def _evidence_key(a:Mapping[str,Any]):
    span=a.get("evidence_span")
    if isinstance(span,Mapping): ev=("TEXT",span.get("text_sha256"),span.get("char_start"),span.get("char_end"))
    else: ev=("STRUCTURED",a.get("structured_evidence_path"))
    return (a.get("source_unit_id"),a.get("assertion_type"),ev)


def reconcile_primary_recall(primary_assertions:Iterable[Mapping[str,Any]],recall_assertions:Iterable[Mapping[str,Any]])->Dict[str,Any]:
    primary=list(primary_assertions); recall=list(recall_assertions)
    p_by_id={str(a.get("assertion_id")):a for a in primary}; r_by_id={str(a.get("assertion_id")):a for a in recall}
    p_evidence={}; r_evidence={}
    for a in primary: p_evidence.setdefault(_evidence_key(a),[]).append(a)
    for a in recall: r_evidence.setdefault(_evidence_key(a),[]).append(a)
    rows=[]
    for aid in sorted(set(p_by_id)&set(r_by_id)):
        rows.append({"reconciliation_state":"PRIMARY_AND_RECALL_EXACT","assertion_id":aid,"source_unit_id":p_by_id[aid].get("source_unit_id"),"automatic_action":False})
    matched_p=set(p_by_id)&set(r_by_id); matched_r=set(matched_p)
    # Same exact evidence/type but a different normalized proposition is a semantic disagreement, not a dedup.
    for key in sorted(set(p_evidence)&set(r_evidence),key=str):
        for p in p_evidence[key]:
            for r in r_evidence[key]:
                if p.get("assertion_id")==r.get("assertion_id"): continue
                rows.append({"reconciliation_state":"SAME_EVIDENCE_SEMANTIC_DISAGREEMENT","primary_assertion_id":p.get("assertion_id"),"recall_assertion_id":r.get("assertion_id"),"source_unit_id":p.get("source_unit_id"),"automatic_action":False})
                matched_p.add(str(p.get("assertion_id"))); matched_r.add(str(r.get("assertion_id")))
    for aid,a in sorted(p_by_id.items()):
        if aid not in matched_p: rows.append({"reconciliation_state":"PRIMARY_ONLY","primary_assertion_id":aid,"source_unit_id":a.get("source_unit_id"),"automatic_action":False})
    for aid,a in sorted(r_by_id.items()):
        if aid not in matched_r: rows.append({"reconciliation_state":"RECALL_ONLY_CANDIDATE","recall_assertion_id":aid,"source_unit_id":a.get("source_unit_id"),"automatic_action":False})
    counts={s:sum(1 for r in rows if r["reconciliation_state"]==s) for s in sorted({r["reconciliation_state"] for r in rows})}
    return {"blind_recall_schema_version":RECALL_SCHEMA_VERSION,"rows":rows,"counts":counts,
            "automatic_merge_allowed":False,"automatic_repair_allowed":False,"authority_granted":False}
