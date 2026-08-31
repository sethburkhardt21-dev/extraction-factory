"""Independent, blind assertion verification with specialist semantic capsules.

The verifier never mutates the source assertion and never grants canonical,
selection, generation, or public authority. Verification is append-only review
evidence suitable for later 09D audit/governance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .assertions import validate_assertion, validate_source_unit, normalize_proposition
from .assertion_engine import structured_clinicaltrials_provider
from .semantic_capsules import run_specialist_capsules

VERIFIER_SCHEMA_VERSION="frontier-assertion-verifier-1.0"
VERIFICATION_EVENT_SCHEMA_VERSION="frontier-assertion-verification-event-1.0"
REVIEWER_RESPONSE_SCHEMA_VERSION="frontier-blind-reviewer-response-1.0"
VERDICTS={"ENTAILED","NOT_ENTAILED","PARTIAL","AMBIGUOUS","PROVENANCE_INCOMPLETE"}
CONFIDENCE={"LOW","MODERATE","HIGH"}
VERIFICATION_SCHEMA_VERSION=VERIFICATION_EVENT_SCHEMA_VERSION
VERIFIER_ENGINE_SCHEMA_VERSION=VERIFIER_SCHEMA_VERSION
RISK_TIERS={"LOW","MEDIUM","HIGH","CRITICAL"}
CHECK_STATES={"PASS","FAIL","WARN","NOT_APPLICABLE"}
REVIEW_LANES={"BLIND_ENTAILMENT","NUMERIC_BINDING","QUALIFIER_SCOPE","TABLE_BINDING","VISUAL_BINDING","RELATIONSHIP_BINDING","PRECISION_REVIEW","FRONTIER_ADJUDICATION","COLD_AUDIT"}

FORBIDDEN_REVIEWER_KEYS={
    "canonical_authority","automatic_selection_allowed","canonical_internal_eligible","generation_eligible","public_eligible",
    "subject_candidate_id","object_candidate_id","candidate_id","promotion_id","resolution_id","verification_event_id",
    "extractor_provenance","extractor_model","extractor_prompt","interpretation_id","09d_decision","09d_status",
}
ALLOWED_REVIEWER_KEYS={
    "reviewer_response_schema_version","verdict","rationale","confidence","detected_issues","resolved_warning_codes",
    "qualifier_assessment","relationship_assessment","numeric_assessment","legacy_failed_dimension_codes",
}

ReviewerProvider=Callable[[Mapping[str,Any]],Mapping[str,Any]]
SemanticVerdictProvider=ReviewerProvider


def _canonical_bytes(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")

def _sha(value:Any)->str: return hashlib.sha256(value if isinstance(value,bytes) else _canonical_bytes(value)).hexdigest()

def _identity(parts:Sequence[Any])->str:
    payload=[]
    for part in parts:
        b=_canonical_bytes(part) if isinstance(part,(dict,list,tuple,bool,int,float)) or part is None else str(part).encode("utf-8")
        payload.append(str(len(b)).encode()+b":"+b)
    return hashlib.sha256(b"\x1f".join(payload)).hexdigest()

@dataclass(frozen=True)
class VerifierConfig:
    engine:str
    engine_version:str
    code_manifest_sha256:str
    mode:str="DETERMINISTIC_ONLY"
    model:Optional[str]=None
    model_revision:Optional[str]=None
    prompt_sha256:Optional[str]=None
    policy_version:str="09d-blind-semantic-review-v1"

    def provenance(self)->Dict[str,Any]:
        if not isinstance(self.engine,str) or not self.engine: raise ValueError("verifier engine required")
        if not isinstance(self.engine_version,str) or not self.engine_version: raise ValueError("verifier engine_version required")
        if not re.fullmatch(r"[0-9a-f]{64}",str(self.code_manifest_sha256 or "")): raise ValueError("verifier code_manifest_sha256 must be lowercase 64-hex")
        if self.mode not in {"DETERMINISTIC_ONLY","DETERMINISTIC_REVIEW","MODEL_ASSISTED"}: raise ValueError("verifier mode invalid")
        canonical_mode="DETERMINISTIC_REVIEW" if self.mode=="DETERMINISTIC_ONLY" else self.mode
        p={"mode":self.mode,"canonical_mode":canonical_mode,"engine":self.engine,"engine_version":self.engine_version,"code_manifest_sha256":self.code_manifest_sha256,"policy_version":self.policy_version,"blind_to_extractor":True}
        if self.mode=="MODEL_ASSISTED":
            for name,val in (("model",self.model),("model_revision",self.model_revision),("prompt_sha256",self.prompt_sha256)):
                if not isinstance(val,str) or not val: raise ValueError(f"model-assisted verifier requires {name}")
            if not re.fullmatch(r"[0-9a-f]{64}",self.prompt_sha256 or ""): raise ValueError("verifier prompt_sha256 must be lowercase 64-hex")
            p.update(model=self.model,model_revision=self.model_revision,prompt_sha256=self.prompt_sha256)
        return p


def build_blind_verifier_request(assertion:Mapping[str,Any],source_unit:Mapping[str,Any],specialist_result:Optional[Mapping[str,Any]]=None)->Dict[str,Any]:
    """Construct a reviewer packet that intentionally hides extractor identity/provenance."""
    # Cross-contract validation belongs outside the model and is not hidden.
    request={
        "verifier_request_schema_version":"frontier-blind-verifier-request-1.0",
        "claim":{
            "assertion_type":assertion.get("assertion_type"),
            "normalized_proposition":assertion.get("normalized_proposition"),
            "context":assertion.get("context") or {},
            "numeric":assertion.get("numeric"),
            "certainty":assertion.get("certainty"),
            "negated":bool(assertion.get("negated",False)),
            "conditional":bool(assertion.get("conditional",False)),
            "study_context":assertion.get("study_context") or {},
            "evidence_span":assertion.get("evidence_span"),
            "structured_evidence_path":assertion.get("structured_evidence_path"),
        },
        "source_unit":{
            "source_unit_id":source_unit.get("source_unit_id"),
            "source_scope":source_unit.get("source_scope"),
            "unit_kind":source_unit.get("unit_kind"),
            "locator":source_unit.get("locator"),
            "content_representation":source_unit.get("content_representation"),
            "content_text":source_unit.get("content_text"),
            "content_json":source_unit.get("content_json"),
            "section_context":(source_unit.get("metadata") or {}).get("section_path"),
        },
        "review_task":{
            "blind_to_extractor":True,
            "judge_only_source_entailment":True,
            "check_numeric_binding":True,
            "check_qualifier_scope":True,
            "check_negation":True,
            "check_certainty":True,
            "check_population_route_timing":True,
            "check_directionality_and_causality":True,
            "allowed_verdicts":sorted(VERDICTS-{"PROVENANCE_INCOMPLETE"}),
            "authority_granted":False,
        },
    }
    # Specialists are deterministic evidence, not extractor reasoning. Expose findings but never extractor provenance.
    if specialist_result is not None:
        request["deterministic_specialist_findings"]=[dict(x) for x in specialist_result.get("findings",[])]
        request["risk_route"]=dict(specialist_result.get("risk_route") or {})
    blob=json.loads(json.dumps(request,sort_keys=True,ensure_ascii=False))
    forbidden=json.dumps(blob,sort_keys=True)
    for token in ("extractor_provenance","interpretation_id","subject_candidate_id","object_candidate_id"):
        if token in forbidden: raise RuntimeError(f"blind verifier request leaked {token}")
    return blob


def blind_verifier_payload(assertion:Mapping[str,Any], source_unit:Mapping[str,Any])->Dict[str,Any]:
    """Compatibility alias for the canonical blind reviewer packet."""
    return build_blind_verifier_request(assertion,source_unit)


def _nested_forbidden(value:Any,path="response")->List[str]:
    hits=[]
    if isinstance(value,Mapping):
        for k,v in value.items():
            child=f"{path}.{k}"
            if str(k) in FORBIDDEN_REVIEWER_KEYS: hits.append(child)
            hits.extend(_nested_forbidden(v,child))
    elif isinstance(value,(list,tuple)):
        for i,v in enumerate(value): hits.extend(_nested_forbidden(v,f"{path}[{i}]") )
    return hits


def validate_reviewer_response(response:Mapping[str,Any])->List[str]:
    if not isinstance(response,Mapping): return ["reviewer response must be object"]
    e=[]
    extra=set(response)-ALLOWED_REVIEWER_KEYS
    if extra: e.append("reviewer response contains unknown fields: "+", ".join(sorted(extra)))
    nested=_nested_forbidden(response)
    if nested: e.append("reviewer response attempts authority/identity leakage: "+", ".join(sorted(set(nested))))
    if response.get("reviewer_response_schema_version") not in (None,REVIEWER_RESPONSE_SCHEMA_VERSION): e.append("reviewer_response_schema_version mismatch")
    verdict=response.get("verdict")
    if verdict not in VERDICTS-{"PROVENANCE_INCOMPLETE"}: e.append("reviewer verdict invalid")
    if not isinstance(response.get("rationale"),str) or not response.get("rationale"," ").strip(): e.append("reviewer rationale required")
    if response.get("confidence") not in CONFIDENCE: e.append("reviewer confidence invalid")
    for k in ("detected_issues","resolved_warning_codes"):
        if response.get(k) is not None and (not isinstance(response.get(k),list) or not all(isinstance(x,str) for x in response[k])): e.append(f"{k} must be list[str]")
    return e


def _adapt_legacy_provider_response(response:Mapping[str,Any])->Mapping[str,Any]:
    """Accept the v1 scaffold provider shape while persisting only the canonical reviewer shape."""
    if not isinstance(response,Mapping): return response
    if "rationale" in response or "confidence" in response or "reviewer_response_schema_version" in response:
        return response
    allowed={"verdict","failed_dimensions","notes"}
    extra=set(response)-allowed
    if extra:
        # Preserve extras so canonical validation rejects authority/unknown injection.
        return response
    dims=list(response.get("failed_dimensions") or [])
    code_map={"NUMERIC":"NUMERIC_BINDING","NEGATION":"NEGATION_PRESERVATION","QUALIFIER":"QUALIFIER_SCOPE","RELATIONSHIP":"RELATIONSHIP_SEMANTICS","CAUSALITY":"RELATIONSHIP_SEMANTICS","ATOMICITY":"ATOMICITY","OTHER":"OTHER"}
    return {
        "reviewer_response_schema_version":REVIEWER_RESPONSE_SCHEMA_VERSION,
        "verdict":response.get("verdict"),
        "rationale":str(response.get("notes") or "Legacy blind semantic-provider verdict."),
        "confidence":"MODERATE",
        "detected_issues":dims,
        "resolved_warning_codes":[],
        "legacy_failed_dimension_codes":[code_map.get(x,x) for x in dims],
    }



def _structured_deterministic_verdict(assertion:Mapping[str,Any],source_unit:Mapping[str,Any])->Optional[Dict[str,Any]]:
    """Re-derive the small high-precision CTG mapping independently of the extractor output."""
    if source_unit.get("content_representation")!="JSON": return None
    expected=list(structured_clinicaltrials_provider(source_unit))
    if not expected: return None
    # One scalar unit should produce at most one rule-derived fact in this provider.
    for p in expected:
        if p.get("assertion_type")!=assertion.get("assertion_type"): continue
        if normalize_proposition(str(p.get("normalized_proposition"))) != normalize_proposition(str(assertion.get("normalized_proposition"))):
            continue
        pn=p.get("numeric"); an=assertion.get("numeric")
        if pn is not None and dict(pn)!=dict(an or {}): continue
        return {"verdict":"ENTAILED","basis":"DETERMINISTIC_REDERIVATION","detail":"independent structured rule re-derived the same atomic proposition"}
    # A rule applies to this exact source field, but the assertion differs from the rule-derived fact.
    return {"verdict":"NOT_ENTAILED","basis":"DETERMINISTIC_REDERIVATION_MISMATCH","detail":"structured field maps to a different frozen proposition/type/value"}


def _specialist_index(result:Mapping[str,Any])->Dict[str,Mapping[str,Any]]:
    return {str(x.get("code")):x for x in result.get("findings",[]) if isinstance(x,Mapping)}


def _reconcile(*,assertion:Mapping[str,Any],source_unit:Mapping[str,Any],specialists:Mapping[str,Any],reviewer_response:Optional[Mapping[str,Any]],reviewer_error:Optional[str])->Dict[str,Any]:
    idx=_specialist_index(specialists); route=dict(specialists.get("risk_route") or {})
    prov=idx.get("PROVENANCE_CLOSURE")
    if prov and prov.get("state")=="FAIL":
        return {"verdict":"PROVENANCE_INCOMPLETE","decision_basis":"DETERMINISTIC_PROVENANCE_BLOCK","review_state":"BLOCKED_PROVENANCE","downstream_semantic_ready":False,"escalation_required":True}
    hard=[x for x in idx.values() if x.get("state")=="FAIL" and x.get("severity") in {"HIGH","CRITICAL"}]
    if hard:
        return {"verdict":"NOT_ENTAILED","decision_basis":"DETERMINISTIC_SPECIALIST_CONTRADICTION","review_state":"REJECTED_BY_SPECIALIST","downstream_semantic_ready":False,"escalation_required":bool(route.get("frontier_adjudication_required")),"blocking_codes":[x.get("code") for x in hard]}
    structured=_structured_deterministic_verdict(assertion,source_unit)
    if structured and structured["verdict"]=="NOT_ENTAILED":
        return {"verdict":"NOT_ENTAILED","decision_basis":structured["basis"],"review_state":"REJECTED_BY_STRUCTURED_REDERIVATION","downstream_semantic_ready":False,"escalation_required":False}
    warnings=[x for x in idx.values() if x.get("state")=="WARN"]
    required_reviewer=bool(route.get("blind_semantic_reviewer_required"))
    if reviewer_error:
        return {"verdict":"AMBIGUOUS","decision_basis":"BLIND_REVIEWER_FAILED","review_state":"REVIEWER_FAILED","downstream_semantic_ready":False,"escalation_required":True,"reviewer_error":reviewer_error}
    # Exact structured facts can be independently entailed without a semantic model if specialists are clean.
    if structured and structured["verdict"]=="ENTAILED" and not warnings:
        if route.get("frontier_adjudication_required"):
            return {"verdict":"ENTAILED","decision_basis":structured["basis"],"review_state":"FRONTIER_ADJUDICATION_REQUIRED","downstream_semantic_ready":False,"escalation_required":True}
        return {"verdict":"ENTAILED","decision_basis":structured["basis"],"review_state":"DETERMINISTIC_REVIEW_COMPLETE","downstream_semantic_ready":True,"escalation_required":False}
    if reviewer_response is None:
        # Exact literal equality can be independently proven by the verifier, but free-text
        # still is not downstream-ready without an independent blind semantic reviewer.
        if source_unit.get("content_representation")=="TEXT":
            span=assertion.get("evidence_span") or {}
            evidence=str(span.get("text") or source_unit.get("content_text") or "").strip().rstrip(".").casefold()
            prop=str(assertion.get("normalized_proposition") or "").strip().rstrip(".").casefold()
            if prop and prop==evidence:
                verdict="PARTIAL" if warnings else "ENTAILED"
                state="FRONTIER_ADJUDICATION_REQUIRED" if route.get("frontier_adjudication_required") else ("SPECIALIST_REVIEW_REQUIRED" if warnings else "DETERMINISTIC_LITERAL_ENTAILMENT")
                return {"verdict":verdict,"decision_basis":"DETERMINISTIC_LITERAL_EQUALITY_WITH_WARNINGS" if warnings else "DETERMINISTIC_LITERAL_EQUALITY","review_state":state,"downstream_semantic_ready":False,"escalation_required":bool(route.get("frontier_adjudication_required") or required_reviewer or warnings),"unresolved_warning_codes":[x.get("code") for x in warnings]}
        return {"verdict":"AMBIGUOUS","decision_basis":"NO_INDEPENDENT_SEMANTIC_REVIEW","review_state":"BLIND_REVIEW_REQUIRED" if required_reviewer else "SEMANTIC_REVIEW_NOT_RUN","downstream_semantic_ready":False,"escalation_required":required_reviewer or bool(warnings)}
    verdict=str(reviewer_response["verdict"])
    resolved=set(reviewer_response.get("resolved_warning_codes") or [])
    unresolved=[x for x in warnings if x.get("code") not in resolved]
    legacy_failed=list(reviewer_response.get("legacy_failed_dimension_codes") or [])
    if legacy_failed:
        unresolved.extend({"code":code,"state":"WARN","severity":"MODERATE","detail":"legacy reviewer reported unresolved semantic dimension"} for code in legacy_failed)
    if verdict=="ENTAILED" and unresolved:
        verdict="PARTIAL"; basis="BLIND_REVIEW_ENTAILED_WITH_UNRESOLVED_SPECIALIST_WARNINGS"
    else: basis="BLIND_INDEPENDENT_REVIEW"
    downstream=verdict=="ENTAILED" and not route.get("frontier_adjudication_required")
    state="BLIND_REVIEW_COMPLETE"
    escalation=False
    if route.get("frontier_adjudication_required"):
        state="FRONTIER_ADJUDICATION_REQUIRED"; downstream=False; escalation=True
    elif verdict in {"PARTIAL","AMBIGUOUS"}:
        state="SPECIALIST_OR_FRONTIER_REVIEW_REQUIRED"; downstream=False; escalation=True
    elif verdict=="NOT_ENTAILED":
        state="REJECTED_BY_BLIND_REVIEW"; downstream=False
    return {"verdict":verdict,"decision_basis":basis,"review_state":state,"downstream_semantic_ready":downstream,"escalation_required":escalation,"unresolved_warning_codes":[x.get("code") for x in unresolved]}


def verify_assertion(assertion:Mapping[str,Any],source_unit:Mapping[str,Any],*,config:VerifierConfig,reviewer:Optional[ReviewerProvider]=None,semantic_provider:Optional[ReviewerProvider]=None)->Dict[str,Any]:
    if reviewer is not None and semantic_provider is not None: raise ValueError("provide reviewer or semantic_provider, not both")
    if reviewer is None and semantic_provider is not None:
        legacy=semantic_provider
        reviewer=lambda req: _adapt_legacy_provider_response(legacy(req))
    uerr=validate_source_unit(source_unit)
    aerr=validate_assertion(assertion,source_unit=source_unit)
    # Assertions entering verification must remain immutable extraction artifacts.
    if assertion.get("verification_status")!="NOT_VERIFIED": aerr.append("input assertion must remain NOT_VERIFIED; verification is append-only")
    specialists=run_specialist_capsules(assertion,source_unit,contract_errors=[*uerr,*aerr])
    request=build_blind_verifier_request(assertion,source_unit,specialists)
    request_sha=_sha(request)
    reviewer_response=None; reviewer_error=None
    if reviewer is not None and not any(f.get("code")=="PROVENANCE_CLOSURE" and f.get("state")=="FAIL" for f in specialists["findings"]):
        try:
            rr=_adapt_legacy_provider_response(reviewer(request))
            errors=validate_reviewer_response(rr)
            if errors: raise ValueError("; ".join(errors))
            reviewer_response=dict(rr)
        except Exception as exc:
            reviewer_error=f"{type(exc).__name__}: {exc}"
    decision=_reconcile(assertion=assertion,source_unit=source_unit,specialists=specialists,reviewer_response=reviewer_response,reviewer_error=reviewer_error)
    prov=config.provenance()
    event_id="VERIF:"+_identity([assertion.get("assertion_id"),assertion.get("interpretation_id"),request_sha,prov,decision.get("verdict"),decision.get("decision_basis")])[:32]
    risk_level=str((specialists.get("risk_route") or {}).get("risk_level") or "LOW")
    risk_tier="MEDIUM" if risk_level=="MODERATE" else risk_level
    lanes=[]
    route=specialists.get("risk_route") or {}
    required=set(route.get("required_specialists") or [])
    if "NUMERIC_BINDING" in required: lanes.append("NUMERIC_BINDING")
    if "QUALIFIER_SCOPE" in required: lanes.append("QUALIFIER_SCOPE")
    if "RELATIONSHIP_SEMANTICS" in required: lanes.append("RELATIONSHIP_BINDING")
    if "TABLE_BINDING" in required: lanes.append("TABLE_BINDING")
    if "VISUAL_BINDING" in required: lanes.append("VISUAL_BINDING")
    if route.get("blind_semantic_reviewer_required"): lanes.append("BLIND_ENTAILMENT")
    if risk_tier in {"HIGH","CRITICAL"} or source_unit.get("source_scope") in {"ABSTRACT_ONLY","ABSTRACT_WITHIN_FULLTEXT","TABLE","FIGURE"} or any(f.get("state")=="WARN" for f in specialists.get("findings",[])): lanes.append("PRECISION_REVIEW")
    if route.get("frontier_adjudication_required"): lanes.append("FRONTIER_ADJUDICATION")
    if decision.get("verdict") in {"NOT_ENTAILED","PROVENANCE_INCOMPLETE"}: lanes.append("COLD_AUDIT")
    lanes=list(dict.fromkeys(lanes))
    checks=[]
    for finding in specialists.get("findings",[]):
        code=str(finding.get("code"))
        compat_code="RELATIONSHIP_BINDING" if code=="RELATIONSHIP_SEMANTICS" else ("PROVENANCE_CONTRACT" if code=="PROVENANCE_CLOSURE" else code)
        checks.append({"check_code":compat_code,"state":finding.get("state"),"detail":finding.get("detail"),"blocking":bool(finding.get("state")=="FAIL" and finding.get("severity") in {"HIGH","CRITICAL"})})
    # Structured semantic re-derivation remains an explicit compatibility check.
    structured=_structured_deterministic_verdict(assertion,source_unit)
    if structured is not None:
        checks.append({"check_code":"STRUCTURED_SEMANTIC_BINDING","state":"PASS" if structured.get("verdict")=="ENTAILED" else "FAIL","detail":structured.get("detail"),"blocking":structured.get("verdict")=="NOT_ENTAILED"})
    event={
        "verification_schema_version":VERIFICATION_SCHEMA_VERSION,
        "verification_event_schema_version":VERIFICATION_EVENT_SCHEMA_VERSION,
        "verification_id":event_id,"verification_event_id":event_id,
        "assertion_id":assertion.get("assertion_id"),"observed_interpretation_id":assertion.get("interpretation_id"),"interpretation_id":assertion.get("interpretation_id"),
        "source_unit_id":source_unit.get("source_unit_id"),"source_record_key":source_unit.get("source_record_key"),
        "blind_request_sha256":request_sha,"verifier_provenance":prov,
        "specialist_capsules":specialists,"checks":checks,"risk_tier":risk_tier,"required_review_lanes":lanes,
        "reviewer_response":reviewer_response,"semantic_provider_result":reviewer_response,"reviewer_error":reviewer_error,
        "blind_independent_review":True,"extractor_provenance_visible_to_semantic_provider":False,"semantic_provider_used":reviewer is not None,
        **decision,
        "canonical_authority":False,"automatic_selection_allowed":False,"canonical_internal_eligible":False,
        "generation_eligible":False,"public_eligible":False,"09d_mutation_performed":False,
        "candidate_resolution_performed":False,"09d_comparison_performed":False,
    }
    return event


def validate_verification_event(event:Mapping[str,Any],*,assertion:Optional[Mapping[str,Any]]=None,source_unit:Optional[Mapping[str,Any]]=None)->List[str]:
    e=[]
    if event.get("verification_event_schema_version")!=VERIFICATION_EVENT_SCHEMA_VERSION: e.append("verification_event_schema_version mismatch")
    if event.get("verification_schema_version")!=VERIFICATION_SCHEMA_VERSION: e.append("verification_schema_version mismatch")
    for k in ("verification_event_id","verification_id","assertion_id","interpretation_id","source_unit_id","blind_request_sha256"):
        if not isinstance(event.get(k),str) or not event.get(k): e.append(f"{k} required")
    if isinstance(event.get("blind_request_sha256"),str) and not re.fullmatch(r"[0-9a-f]{64}",event["blind_request_sha256"]): e.append("blind_request_sha256 must be lowercase 64-hex")
    if event.get("verification_id")!=event.get("verification_event_id"): e.append("verification_id/event_id mismatch")
    if event.get("verdict") not in VERDICTS: e.append("invalid verification verdict")
    if event.get("risk_tier") not in RISK_TIERS: e.append("risk_tier invalid")
    if not isinstance(event.get("required_review_lanes"),list) or any(x not in REVIEW_LANES for x in event.get("required_review_lanes",[])): e.append("required_review_lanes invalid")
    if not isinstance(event.get("checks"),list) or not event.get("checks"): e.append("checks required")
    if not isinstance(event.get("specialist_capsules"),Mapping): e.append("specialist_capsules required")
    prov=event.get("verifier_provenance")
    if not isinstance(prov,Mapping) or prov.get("blind_to_extractor") is not True: e.append("verifier provenance must prove blind_to_extractor")
    for k in ("canonical_authority","automatic_selection_allowed","canonical_internal_eligible","generation_eligible","public_eligible","09d_mutation_performed","candidate_resolution_performed","09d_comparison_performed"):
        if event.get(k) is not False: e.append(f"{k} must be false")
    if assertion is not None:
        if event.get("assertion_id")!=assertion.get("assertion_id"): e.append("assertion_id mismatch")
        if event.get("observed_interpretation_id")!=assertion.get("interpretation_id"): e.append("observed_interpretation_id mismatch")
    if source_unit is not None and event.get("source_unit_id")!=source_unit.get("source_unit_id"): e.append("source_unit_id mismatch")
    return e


def verify_assertions(assertions:Iterable[Mapping[str,Any]],source_units:Iterable[Mapping[str,Any]],*,config:VerifierConfig,reviewer:Optional[ReviewerProvider]=None,semantic_provider:Optional[ReviewerProvider]=None)->Dict[str,Any]:
    if reviewer is not None and semantic_provider is not None: raise ValueError("provide reviewer or semantic_provider, not both")
    if reviewer is None and semantic_provider is not None: reviewer=semantic_provider
    assertions=list(assertions); source_units=list(source_units)
    units={str(u.get("source_unit_id")):u for u in source_units}; events=[]; quarantine=[]
    for assertion in assertions:
        uid=str(assertion.get("source_unit_id") or ""); unit=units.get(uid)
        if unit is None:
            quarantine.append({"assertion_id":assertion.get("assertion_id"),"error":"source unit absent for verification"}); continue
        try:
            ev=verify_assertion(assertion,unit,config=config,reviewer=reviewer)
            errs=validate_verification_event(ev,assertion=assertion,source_unit=unit)
            if errs: raise ValueError("; ".join(errs))
            events.append(ev)
        except Exception as exc:
            quarantine.append({"assertion_id":assertion.get("assertion_id"),"error":f"{type(exc).__name__}: {exc}"})
    unique={e["verification_event_id"]:e for e in events}; events=[unique[k] for k in sorted(unique)]
    verdict_counts={v:sum(1 for e in events if e.get("verdict")==v) for v in sorted(VERDICTS)}
    review_state_counts={s:sum(1 for e in events if e.get("review_state")==s) for s in sorted({str(e.get("review_state")) for e in events})}
    return {
        "assertion_verifier_schema_version":VERIFIER_SCHEMA_VERSION,"verifier_engine_schema_version":VERIFIER_ENGINE_SCHEMA_VERSION,
        "status":"PASS" if not quarantine else "PASS_WITH_QUARANTINE",
        "blind_independent_review":True,"source_assertions_mutated":False,"assertions_mutated":False,"candidate_resolution_performed":False,
        "09d_comparison_performed":False,"authority_granted":False,
        "verifier_provenance":config.provenance(),"events":events,"verification_events":events,"quarantine":quarantine,
        "metrics":{"assertions_seen":len(assertions),"verification_events":len(events),"quarantine":len(quarantine),"quarantined":len(quarantine),"verdict_counts":verdict_counts,"risk_counts":{r:sum(1 for e in events if e.get("risk_tier")==r) for r in sorted(RISK_TIERS)},"review_state_counts":review_state_counts,"downstream_semantic_ready":sum(1 for e in events if e.get("downstream_semantic_ready") is True),"frontier_adjudication_required":sum(1 for e in events if e.get("review_state")=="FRONTIER_ADJUDICATION_REQUIRED")},
    }


def deterministic_verifier_config(*, code_manifest_sha256:str)->VerifierConfig:
    return VerifierConfig(engine="frontier-independent-verifier",engine_version="2.0",code_manifest_sha256=code_manifest_sha256,mode="DETERMINISTIC_ONLY")
