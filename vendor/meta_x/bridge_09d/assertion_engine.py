"""Untrusted source-unit -> atomic assertion proposal engine.

Turn 4 deliberately does NOT verify semantic entailment. Providers can propose
interpretations, but this engine computes evidence bindings, IDs, provenance and
all fail-closed authority fields. Every emitted assertion is NOT_VERIFIED.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence

from .assertions import ASSERTION_TYPES, build_assertion, validate_source_unit, sha256_hex

ASSERTION_ENGINE_SCHEMA_VERSION = "frontier-assertion-engine-1.0"
PROPOSAL_SCHEMA_VERSION = "frontier-assertion-proposal-1.0"

FORBIDDEN_PROPOSAL_KEYS = {
    "assertion_id", "interpretation_id", "source_unit_id", "source_record_key",
    "source_resource_id", "source_version_id", "source_sha256", "source_unit_sha256",
    "verification_status", "automatic_selection_allowed", "canonical_authority",
    "canonical_internal_eligible", "generation_eligible", "public_eligible",
    "extractor_provenance", "subject_candidate_id", "object_candidate_id",
}

ALLOWED_PROPOSAL_KEYS = {
    "proposal_schema_version", "assertion_type", "normalized_proposition",
    "evidence_text", "char_start", "structured_evidence_path", "context", "numeric",
    "certainty", "negated", "conditional", "study_context", "subject_surface",
    "object_surface",
}


class ProposalProvider(Protocol):
    def __call__(self, source_unit: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class EngineConfig:
    engine: str
    engine_version: str
    code_manifest_sha256: str
    mode: str = "MODEL_ASSISTED"
    model: Optional[str] = None
    model_revision: Optional[str] = None
    prompt_sha256: Optional[str] = None

    def provenance(self) -> Dict[str, Any]:
        if self.mode not in {"MODEL_ASSISTED", "DETERMINISTIC_PARSER"}:
            raise ValueError("mode must be MODEL_ASSISTED or DETERMINISTIC_PARSER")
        for name,val in (("engine",self.engine),("engine_version",self.engine_version)):
            if not isinstance(val,str) or not val: raise ValueError(f"{name} must be non-empty text")
        if not re.fullmatch(r"[0-9a-f]{64}", self.code_manifest_sha256 or ""):
            raise ValueError("code_manifest_sha256 must be lowercase 64-hex")
        out={
            "mode":self.mode,
            "engine":self.engine,
            "engine_version":self.engine_version,
            "code_manifest_sha256":self.code_manifest_sha256,
        }
        if self.mode=="MODEL_ASSISTED":
            for name,val in (("model",self.model),("model_revision",self.model_revision),("prompt_sha256",self.prompt_sha256)):
                if not isinstance(val,str) or not val:
                    raise ValueError(f"model-assisted engine requires {name}")
            if not re.fullmatch(r"[0-9a-f]{64}", self.prompt_sha256 or ""):
                raise ValueError("prompt_sha256 must be lowercase 64-hex")
            out.update(model=self.model,model_revision=self.model_revision,prompt_sha256=self.prompt_sha256)
        return out


def build_model_request(source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    """Return the constrained provider input. No 09D authority state is exposed."""
    errors=validate_source_unit(source_unit)
    if errors: raise ValueError("invalid source unit: "+"; ".join(errors))
    return {
        "proposal_schema_version":PROPOSAL_SCHEMA_VERSION,
        "instruction":(
            "Return zero or more atomic clinical assertions supported only by this source unit. "
            "One proposal must contain one independently auditable proposition. Do not infer missing "
            "population, dose, route, timing, comparator, certainty, causality, or identity. For text "
            "units copy an exact evidence_text substring. For structured JSON use the exact json_path."
        ),
        "allowed_assertion_types":sorted(ASSERTION_TYPES),
        "source_unit":{
            "source_unit_id":source_unit["source_unit_id"],
            "source_scope":source_unit["source_scope"],
            "unit_kind":source_unit["unit_kind"],
            "locator":source_unit["locator"],
            "content_representation":source_unit.get("content_representation"),
            "content_text":source_unit.get("content_text"),
            "content_json":source_unit.get("content_json"),
        },
        "authority":{
            "verification":"provider_cannot_verify",
            "candidate_resolution":"provider_cannot_assign_candidate_ids",
            "canonical_authority":False,
            "automatic_selection_allowed":False,
            "generation_eligible":False,
            "public_eligible":False,
        },
    }


def _single_sentence(text: str) -> bool:
    if "\n" in text or "\r" in text or ";" in text:
        return False
    # Fail obvious multi-sentence output. Decimal points do not count as terminators here.
    endings=re.findall(r"(?<!\d)[.!?](?:\s+|$)", text.strip())
    return len(endings) <= 1


def _text_span(unit: Mapping[str,Any], proposal: Mapping[str,Any]) -> Dict[str,Any]:
    content=unit.get("content_text")
    if not isinstance(content,str): raise ValueError("text evidence requires a TEXT source unit")
    evidence=proposal.get("evidence_text")
    if not isinstance(evidence,str) or not evidence:
        raise ValueError("text proposal requires non-empty evidence_text")
    explicit=proposal.get("char_start")
    if explicit is not None:
        if not isinstance(explicit,int) or explicit<0: raise ValueError("char_start must be non-negative integer")
        start=explicit; end=start+len(evidence)
        if end>len(content) or content[start:end]!=evidence: raise ValueError("evidence_text does not match source unit at char_start")
    else:
        starts=[]; pos=0
        while True:
            i=content.find(evidence,pos)
            if i<0: break
            starts.append(i); pos=i+1
        if not starts: raise ValueError("evidence_text is not an exact source-unit substring")
        if len(starts)>1: raise ValueError("evidence_text occurs multiple times; char_start is required")
        start=starts[0]; end=start+len(evidence)
    bstart=len(content[:start].encode("utf-8")); bend=bstart+len(evidence.encode("utf-8"))
    return {"char_start":start,"char_end":end,"utf8_byte_start":bstart,"utf8_byte_end":bend,
            "text":evidence,"text_sha256":sha256_hex(evidence.encode("utf-8"))}


def _structured_path(unit: Mapping[str,Any], proposal: Mapping[str,Any]) -> str:
    if unit.get("content_representation")!="JSON": raise ValueError("structured proposal requires a JSON source unit")
    expected=(unit.get("locator") or {}).get("json_path")
    actual=proposal.get("structured_evidence_path")
    if not isinstance(actual,str) or not actual: raise ValueError("structured proposal requires structured_evidence_path")
    if not isinstance(expected,str) or actual!=expected: raise ValueError("structured_evidence_path must exactly equal source-unit json_path")
    return actual


def _nested_forbidden_keys(value: Any, *, path: str="proposal") -> List[str]:
    hits=[]
    if isinstance(value,Mapping):
        for k,v in value.items():
            key=str(k); child=f"{path}.{key}"
            if key in FORBIDDEN_PROPOSAL_KEYS or key in {"candidate_id","drug_entity_id","promotion_id","resolution_id"}:
                hits.append(child)
            hits.extend(_nested_forbidden_keys(v,path=child))
    elif isinstance(value,(list,tuple)):
        for i,v in enumerate(value): hits.extend(_nested_forbidden_keys(v,path=f"{path}[{i}]"))
    return hits


def validate_proposal(proposal: Mapping[str,Any]) -> List[str]:
    e=[]
    if not isinstance(proposal,Mapping): return ["proposal must be object"]
    extra=set(proposal)-ALLOWED_PROPOSAL_KEYS
    forbidden=set(proposal)&FORBIDDEN_PROPOSAL_KEYS
    if forbidden: e.append("proposal attempts to set engine-owned fields: "+", ".join(sorted(forbidden)))
    nested=[x for x in _nested_forbidden_keys(proposal) if x.split(".")[-1] not in forbidden]
    if nested: e.append("proposal nests forbidden authority/identity fields: "+", ".join(sorted(set(nested))))
    if extra: e.append("proposal contains unknown fields: "+", ".join(sorted(extra)))
    if proposal.get("proposal_schema_version") not in (None,PROPOSAL_SCHEMA_VERSION): e.append("proposal_schema_version mismatch")
    at=proposal.get("assertion_type")
    if at not in ASSERTION_TYPES: e.append("assertion_type is not in frozen registry")
    prop=proposal.get("normalized_proposition")
    if not isinstance(prop,str) or not prop.strip(): e.append("normalized_proposition required")
    elif len(prop)>1200: e.append("normalized_proposition exceeds 1200 characters")
    elif not _single_sentence(prop): e.append("proposal must be one atomic sentence without semicolon/newline")
    for k in ("context","numeric","study_context"):
        if proposal.get(k) is not None and not isinstance(proposal.get(k),Mapping): e.append(f"{k} must be object")
    for k in ("negated","conditional"):
        if proposal.get(k) is not None and not isinstance(proposal.get(k),bool): e.append(f"{k} must be boolean")
    return e


def proposal_to_assertion(source_unit: Mapping[str,Any], proposal: Mapping[str,Any], *, config: EngineConfig) -> Dict[str,Any]:
    errs=validate_proposal(proposal)
    if errs: raise ValueError("; ".join(errs))
    if source_unit.get("content_representation")=="TEXT":
        span=_text_span(source_unit,proposal); structured=None
        if proposal.get("structured_evidence_path") is not None: raise ValueError("text proposal cannot set structured_evidence_path")
    elif source_unit.get("content_representation")=="JSON":
        if proposal.get("evidence_text") is not None or proposal.get("char_start") is not None: raise ValueError("JSON proposal cannot set text evidence fields")
        span=None; structured=_structured_path(source_unit,proposal)
    else:
        raise ValueError("source unit content_representation must be TEXT or JSON")
    context=dict(proposal.get("context") or {})
    surfaces={k:proposal.get(k) for k in ("subject_surface","object_surface") if isinstance(proposal.get(k),str) and proposal.get(k).strip()}
    if any(str(v).startswith("CAND:") for v in surfaces.values()): raise ValueError("unresolved entity surfaces cannot masquerade as CAND identifiers")
    if surfaces: context["unresolved_entity_surfaces"]=surfaces
    row=build_assertion(
        source_unit=source_unit,
        assertion_type=str(proposal["assertion_type"]),
        normalized_proposition=str(proposal["normalized_proposition"]),
        evidence_span=span,
        structured_evidence_path=structured,
        context=context,
        numeric=dict(proposal.get("numeric") or {}) if proposal.get("numeric") is not None else None,
        certainty=proposal.get("certainty"),
        negated=bool(proposal.get("negated",False)),
        conditional=bool(proposal.get("conditional",False)),
        study_context=dict(proposal.get("study_context") or {}),
        extractor_provenance=config.provenance(),
    )
    # Turn 4 invariant: extraction can never self-verify or resolve candidates.
    if row["verification_status"]!="NOT_VERIFIED" or row.get("subject_candidate_id") is not None or row.get("object_candidate_id") is not None:
        raise RuntimeError("Turn 4 authority invariant violated")
    return row


def _qrow(unit: Mapping[str,Any], ordinal: int, *, error: str, proposal: Any=None) -> Dict[str,Any]:
    return {"source_unit_id":unit.get("source_unit_id"),"source_record_key":unit.get("source_record_key"),
            "proposal_ordinal":ordinal,"error":error,"proposal":proposal}


def extract_assertions(source_units: Iterable[Mapping[str,Any]], *, provider: ProposalProvider, config: EngineConfig) -> Dict[str,Any]:
    units=list(source_units); assertions=[]; quarantine=[]; received=0; units_with_assertions=0
    # Validate provenance before provider invocation.
    provenance=config.provenance()
    for unit in units:
        uerr=validate_source_unit(unit)
        if uerr:
            quarantine.append(_qrow(unit,-1,error="invalid source unit: "+"; ".join(uerr))); continue
        try:
            proposals=provider(unit)
        except Exception as exc:
            quarantine.append(_qrow(unit,-1,error=f"provider failure: {type(exc).__name__}: {exc}")); continue
        if proposals is None: proposals=[]
        if not isinstance(proposals,Sequence) or isinstance(proposals,(str,bytes,bytearray)):
            quarantine.append(_qrow(unit,-1,error="provider must return a sequence of proposal objects")); continue
        emitted_before=len(assertions)
        for ordinal,proposal in enumerate(proposals):
            received+=1
            try:
                row=proposal_to_assertion(unit,proposal,config=config)
                assertions.append(row)
            except Exception as exc:
                quarantine.append(_qrow(unit,ordinal,error=str(exc),proposal=dict(proposal) if isinstance(proposal,Mapping) else proposal))
        if len(assertions)>emitted_before: units_with_assertions+=1
    # Deterministic order and exact interpretation deduplication.
    unique={}
    for row in assertions: unique[(row["assertion_id"],row["interpretation_id"])]=row
    duplicate_count=len(assertions)-len(unique)
    assertions=[unique[k] for k in sorted(unique)]
    quarantine=sorted(quarantine,key=lambda x:(str(x.get("source_unit_id")),int(x.get("proposal_ordinal",-1)),str(x.get("error"))))
    metrics={
        "source_units_seen":len(units),"source_units_with_assertions":units_with_assertions,
        "proposals_received":received,"assertions_emitted":len(assertions),"proposals_quarantined":len(quarantine),
        "duplicate_interpretations_collapsed":duplicate_count,
        "verification_status_counts":{"NOT_VERIFIED":len(assertions)},
    }
    return {
        "assertion_engine_schema_version":ASSERTION_ENGINE_SCHEMA_VERSION,
        "status":"PASS" if not quarantine else "PASS_WITH_QUARANTINE",
        "semantic_verification_performed":False,
        "candidate_resolution_performed":False,
        "09d_comparison_performed":False,
        "authority_granted":False,
        "extractor_provenance":provenance,
        "metrics":metrics,"assertions":assertions,"quarantine":quarantine,
    }


def _pretty_enum(value: Any) -> str:
    return str(value).replace("_"," ").title()


def structured_clinicaltrials_provider(source_unit: Mapping[str,Any]) -> Sequence[Mapping[str,Any]]:
    """High-precision deterministic proposals for selected CTG scalar fields only.

    This intentionally does not turn every JSON leaf into a clinical assertion.
    Unknown paths return zero proposals rather than low-value field-dump claims.
    """
    if source_unit.get("content_representation")!="JSON": return []
    path=str((source_unit.get("locator") or {}).get("json_path") or "")
    value=source_unit.get("content_json")
    if value is None: return []
    base={"proposal_schema_version":PROPOSAL_SCHEMA_VERSION,"structured_evidence_path":path}
    if path.endswith(".designModule.enrollmentInfo.count") and isinstance(value,(int,float)) and not isinstance(value,bool):
        return [{**base,"assertion_type":"STUDY_ENROLLMENT","normalized_proposition":f"The study enrollment was {value} participants.","numeric":{"value":value,"unit":"participants"}}]
    if re.search(r"\.designModule\.phases\[\d+\]$",path):
        return [{**base,"assertion_type":"TRIAL_PROTOCOL_FACT","normalized_proposition":f"The study phase included {_pretty_enum(value)}."}]
    if path.endswith(".statusModule.overallStatus"):
        return [{**base,"assertion_type":"TRIAL_PROTOCOL_FACT","normalized_proposition":f"The study overall status was {_pretty_enum(value)}."}]
    if re.search(r"\.conditionsModule\.conditions\[\d+\]$",path):
        return [{**base,"assertion_type":"TRIAL_PROTOCOL_FACT","normalized_proposition":f"The study condition included {value}."}]
    if path.endswith(".hasResults") and isinstance(value,bool):
        return [{**base,"assertion_type":"TRIAL_RESULT_FACT","normalized_proposition":f"The registry indicated that posted results were {'available' if value else 'not available'}.","negated":(not value)}]
    if ".resultsSection." in path:
        return []  # Turn 4 avoids generic result semantics until type-specific mappings exist.
    return []


def deterministic_structured_config(*, code_manifest_sha256: str) -> EngineConfig:
    return EngineConfig(engine="frontier-ctg-structured-assertions",engine_version="1.0",code_manifest_sha256=code_manifest_sha256,mode="DETERMINISTIC_PARSER")
