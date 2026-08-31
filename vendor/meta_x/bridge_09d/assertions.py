from __future__ import annotations

import hashlib, json, re, unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

SOURCE_UNIT_SCHEMA_VERSION = "frontier-source-unit-1.2"
SUPPORTED_SOURCE_UNIT_SCHEMA_VERSIONS = {"frontier-source-unit-1.0", "frontier-source-unit-1.1", SOURCE_UNIT_SCHEMA_VERSION}
_MISSING = object()
ASSERTION_SCHEMA_VERSION = "frontier-atomic-assertion-1.0"

SOURCE_SCOPES = {"FULL_TEXT","ABSTRACT_ONLY","ABSTRACT_WITHIN_FULLTEXT","REGISTRY_STRUCTURED","TABLE","FIGURE","MONOGRAPH","METADATA","OTHER"}
UNIT_KINDS = {"TEXT","TABLE_CELL","TABLE_ROW","FIGURE_CAPTION","STRUCTURED_FIELD","XML_ELEMENT","JSON_FIELD","ABSTRACT_SECTION","OTHER"}
VERIFICATION_STATES = {"NOT_VERIFIED","ENTAILED","NOT_ENTAILED","PARTIAL","AMBIGUOUS","PROVENANCE_INCOMPLETE"}
LOCATOR_TYPES = {"TEXT_SECTION","PARAGRAPH","JATS_XPATH","JSON_PATH","TABLE_CELL","TABLE_ROW","FIGURE","MONOGRAPH_SECTION","OTHER"}
ASSERTION_TYPES = {
 "DOSING","ADMINISTRATION","INDICATION","CONTRAINDICATION","WARNING","PRECAUTION","ADVERSE_EFFECT","DRUG_INTERACTION",
 "PHARMACOKINETIC","PHARMACODYNAMIC","MECHANISM","PHYSIOLOGY","PATHOPHYSIOLOGY","DIAGNOSTIC_THRESHOLD","LAB_VALUE",
 "PROCEDURAL_RECOMMENDATION","MONITORING_RECOMMENDATION","RISK_ASSOCIATION","OUTCOME","EFFICACY","SAFETY","MORTALITY","MORBIDITY",
 "INCIDENCE","PREVALENCE","SENSITIVITY","SPECIFICITY","PREDICTIVE_VALUE","TREATMENT_EFFECT","COMPARATIVE_EFFECTIVENESS",
 "NEGATIVE_FINDING","NONINFERIORITY","EQUIVALENCE","NO_EFFECT","SUBGROUP_EFFECT","POPULATION_SPECIFIC","TEMPORAL_FINDING",
 "CAUSATION","ASSOCIATION","EXPERT_RECOMMENDATION","GUIDELINE_RECOMMENDATION","TRIAL_PROTOCOL_FACT","TRIAL_RESULT_FACT",
 "STUDY_ENROLLMENT","SOURCE_VARIANT","DEFINITION","TAXONOMY_CLASSIFICATION","FORMULATION","CONCENTRATION","ROUTE_APPLICABILITY",
 "CLINICAL_VALUE","OTHER_CLINICAL_ASSERTION"
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(parts: Iterable[Any]) -> str:
    encoded=[]
    for p in parts:
        if isinstance(p,(dict,list,tuple,bool,int,float)) or p is None:
            b=canonical_json_bytes(p)
        else:
            b=str(p).encode("utf-8")
        encoded.append(str(len(b)).encode("ascii")+b":"+b)
    return sha256_hex(b"\x1f".join(encoded))


def source_content_sha256(*, content_text: Optional[str]=None, content_json: Any=_MISSING) -> str:
    text_given = content_text is not None
    json_given = content_json is not _MISSING
    if text_given == json_given:
        raise ValueError("exactly one of content_text or content_json is required")
    if text_given:
        return sha256_hex(content_text.encode("utf-8"))
    return sha256_hex(canonical_json_bytes(content_json))


def _source_unit_id_v1(*, source_record_key: str, source_version_id: str, unit_kind: str,
                       locator: Mapping[str,Any], content_sha256: str) -> str:
    return "UNIT:"+_identity([source_record_key,source_version_id,unit_kind,dict(locator),content_sha256])[:32]


def source_unit_id(*, source_record_key: str, source_resource_id: str, source_version_id: str,
                   source_sha256: str, source_scope: str, unit_kind: str,
                   locator: Mapping[str,Any], content_sha256: str) -> str:
    """v1.2 identity binds the immutable source artifact and evidence scope.

    A FULL_TEXT unit and an ABSTRACT_ONLY unit can never share an identity merely
    because their derived text, locator, and source-record key happen to match.
    """
    digest=_identity([source_record_key,source_resource_id,source_version_id,source_sha256,source_scope,unit_kind,dict(locator),content_sha256])
    return "UNIT:"+digest[:32]


def normalize_proposition(text: str) -> str:
    if not isinstance(text,str) or not text.strip():
        raise ValueError("normalized proposition must be non-empty text")
    # NFC preserves clinically meaningful compatibility distinctions such as
    # superscripts, subscripts, and vulgar fractions. NFKC is forbidden here.
    return re.sub(r"\s+"," ",unicodedata.normalize("NFC",text)).strip()


def assertion_id(*, source_unit_id_value: str, evidence_identity: Mapping[str,Any], assertion_type: str,
                 proposition: str, context: Mapping[str,Any]) -> str:
    digest=_identity([source_unit_id_value,dict(evidence_identity),assertion_type,normalize_proposition(proposition),dict(context)])
    return "ASSERT:"+digest[:32]


def interpretation_id(*, assertion_id_value: str, extractor_provenance: Mapping[str,Any]) -> str:
    return "INTERP:"+_identity([assertion_id_value,dict(extractor_provenance)])[:32]


def build_source_unit(*, source_record_key: str, source_resource_id: str, source_version_id: str, source_sha256: str,
                      source_scope: str, unit_kind: str, locator: Mapping[str,Any], content_text: Optional[str]=None,
                      content_json: Any=_MISSING, parent_unit_id: Optional[str]=None, ordinal: Optional[int]=None,
                      publication_year: Optional[int]=None, edition_or_version: Optional[str]=None, source_era: Optional[str]=None,
                      metadata: Optional[Mapping[str,Any]]=None) -> Dict[str,Any]:
    content_sha=source_content_sha256(content_text=content_text,content_json=content_json)
    uid=source_unit_id(source_record_key=source_record_key,source_resource_id=source_resource_id,
                       source_version_id=source_version_id,source_sha256=source_sha256,source_scope=source_scope,
                       unit_kind=unit_kind,locator=locator,content_sha256=content_sha)
    row={
      "source_unit_schema_version":SOURCE_UNIT_SCHEMA_VERSION,"source_unit_id":uid,
      "source_record_key":source_record_key,"source_resource_id":source_resource_id,"source_version_id":source_version_id,
      "source_sha256":source_sha256,"source_scope":source_scope,"unit_kind":unit_kind,"locator":dict(locator),
      "content_sha256":content_sha,"content_representation":"TEXT" if content_text is not None else "JSON",
      "content_text":content_text,"content_json":None if content_json is _MISSING else content_json,"parent_unit_id":parent_unit_id,
      "ordinal":ordinal,"publication_year":publication_year,"edition_or_version":edition_or_version,"source_era":source_era,
      "metadata":dict(metadata or {}),
    }
    errors=validate_source_unit(row)
    if errors: raise ValueError("invalid source unit: "+"; ".join(errors))
    return row


def validate_source_unit(row: Mapping[str,Any]) -> List[str]:
    e=[]
    version=row.get("source_unit_schema_version")
    if version not in SUPPORTED_SOURCE_UNIT_SCHEMA_VERSIONS:
        e.append("source_unit_schema_version mismatch")
    for k in ("source_record_key","source_resource_id","source_version_id"):
        if not isinstance(row.get(k),str) or not row.get(k): e.append(f"{k} must be non-empty text")
    sha=row.get("source_sha256")
    if not isinstance(sha,str) or not re.fullmatch(r"[0-9a-f]{64}",sha): e.append("source_sha256 must be lowercase 64-hex")
    if row.get("source_scope") not in SOURCE_SCOPES: e.append("invalid source_scope")
    if row.get("unit_kind") not in UNIT_KINDS: e.append("invalid unit_kind")
    loc=row.get("locator")
    if not isinstance(loc,dict) or not loc: e.append("locator must be non-empty object")
    elif loc.get("locator_type") not in LOCATOR_TYPES: e.append("locator.locator_type invalid or missing")
    rep=row.get("content_representation")
    # v1.1+ explicitly separated missing JSON from literal JSON null. Only v1.0 may infer.
    if version == "frontier-source-unit-1.0" and rep is None:
        rep = "TEXT" if row.get("content_text") is not None else "JSON"
    elif version in {"frontier-source-unit-1.1",SOURCE_UNIT_SCHEMA_VERSION} and rep is None:
        e.append("content_representation required for source-unit schema >=1.1")
    try:
        if rep == "TEXT": expected_content=source_content_sha256(content_text=row.get("content_text"))
        elif rep == "JSON": expected_content=source_content_sha256(content_json=row.get("content_json"))
        else: raise ValueError("content_representation must be TEXT or JSON")
    except Exception as exc:
        e.append(str(exc)); expected_content=None
    if expected_content and row.get("content_sha256")!=expected_content: e.append("content_sha256 mismatch")
    if expected_content and isinstance(loc,dict) and row.get("source_record_key") and row.get("source_version_id") and row.get("unit_kind"):
        if version in {"frontier-source-unit-1.0","frontier-source-unit-1.1"}:
            exp=_source_unit_id_v1(source_record_key=str(row["source_record_key"]),source_version_id=str(row["source_version_id"]),unit_kind=str(row["unit_kind"]),locator=loc,content_sha256=expected_content)
        else:
            exp=source_unit_id(source_record_key=str(row["source_record_key"]),source_resource_id=str(row.get("source_resource_id") or ""),
                               source_version_id=str(row["source_version_id"]),source_sha256=str(row.get("source_sha256") or ""),
                               source_scope=str(row.get("source_scope") or ""),unit_kind=str(row["unit_kind"]),locator=loc,content_sha256=expected_content)
        if row.get("source_unit_id")!=exp: e.append("source_unit_id mismatch")
    return e


_JSON_TOKEN_RE=re.compile(r'''(?:^\$)|(?:\.([A-Za-z_][A-Za-z0-9_]*))|(?:\[(\d+)\])|(?:\["((?:[^"\\]|\\.)*)"\])''')

def _json_path_tokens(path: str) -> Tuple[Any,...]:
    if not isinstance(path,str) or not path.startswith("$"):
        raise ValueError("structured_evidence_path must use canonical absolute JSON path beginning with $")
    pos=0; out=[]
    for m in _JSON_TOKEN_RE.finditer(path):
        if m.start()!=pos: raise ValueError("structured_evidence_path is not canonical JSON path syntax")
        pos=m.end()
        if m.group(0)=="$": continue
        if m.group(1) is not None: out.append(m.group(1))
        elif m.group(2) is not None: out.append(int(m.group(2)))
        else: out.append(json.loads('"'+m.group(3)+'"'))
    if pos!=len(path): raise ValueError("structured_evidence_path is not canonical JSON path syntax")
    return tuple(out)


def _resolve_structured_path(source_unit: Mapping[str,Any], path: str) -> Tuple[Any,bool]:
    locator=(source_unit.get("locator") or {})
    base=str(locator.get("json_path") or "")
    if not base: return None,False
    try:
        base_tokens=_json_path_tokens(base); target_tokens=_json_path_tokens(path)
    except ValueError:
        return None,False
    if target_tokens[:len(base_tokens)]!=base_tokens: return None,False
    cur=source_unit.get("content_json")
    for token in target_tokens[len(base_tokens):]:
        try:
            if isinstance(token,int) and isinstance(cur,list): cur=cur[token]
            elif isinstance(token,str) and isinstance(cur,dict): cur=cur[token]
            else: return None,False
        except (IndexError,KeyError,TypeError): return None,False
    return cur,True


def build_assertion(*, source_unit: Mapping[str,Any], assertion_type: str, normalized_proposition: str,
                    evidence_span: Optional[Mapping[str,Any]]=None, structured_evidence_path: Optional[str]=None,
                    context: Optional[Mapping[str,Any]]=None, subject_candidate_id: Optional[str]=None,
                    object_candidate_id: Optional[str]=None, numeric: Optional[Mapping[str,Any]]=None,
                    certainty: Optional[str]=None, negated: bool=False, conditional: bool=False,
                    study_context: Optional[Mapping[str,Any]]=None, extractor_provenance: Mapping[str,Any]|None=None) -> Dict[str,Any]:
    su_errors=validate_source_unit(source_unit)
    if su_errors: raise ValueError("source unit invalid: "+"; ".join(su_errors))
    context=dict(context or {}); study_context=dict(study_context or {}); numeric=dict(numeric or {}) if numeric is not None else None
    if evidence_span is None and not structured_evidence_path: raise ValueError("assertion requires text evidence span or structured evidence path")
    evidence_identity={"span":dict(evidence_span) if evidence_span is not None else None,"structured_path":structured_evidence_path}
    aid=assertion_id(source_unit_id_value=str(source_unit["source_unit_id"]),evidence_identity=evidence_identity,assertion_type=assertion_type,proposition=normalized_proposition,context={"clinical":context,"numeric":numeric,"certainty":certainty,"negated":negated,"conditional":conditional,"study":study_context})
    prov=dict(extractor_provenance or {})
    iid=interpretation_id(assertion_id_value=aid,extractor_provenance=prov)
    row={
      "assertion_schema_version":ASSERTION_SCHEMA_VERSION,"assertion_id":aid,"interpretation_id":iid,
      "source_unit_id":source_unit["source_unit_id"],"source_record_key":source_unit["source_record_key"],
      "source_resource_id":source_unit["source_resource_id"],"source_version_id":source_unit["source_version_id"],
      "source_sha256":source_unit["source_sha256"],"source_unit_sha256":source_unit["content_sha256"],
      "source_scope":source_unit["source_scope"],"locator":source_unit["locator"],
      "publication_year":source_unit.get("publication_year"),"edition_or_version":source_unit.get("edition_or_version"),"source_era":source_unit.get("source_era"),
      "evidence_span":dict(evidence_span) if evidence_span is not None else None,"structured_evidence_path":structured_evidence_path,
      "normalized_proposition":normalize_proposition(normalized_proposition),"assertion_type":assertion_type,
      "subject_candidate_id":subject_candidate_id,"object_candidate_id":object_candidate_id,"context":context,"numeric":numeric,
      "certainty":certainty,"negated":bool(negated),"conditional":bool(conditional),"study_context":study_context,
      "verification_status":"NOT_VERIFIED","automatic_selection_allowed":False,"canonical_authority":False,
      "canonical_internal_eligible":False,"generation_eligible":False,"public_eligible":False,
      "extractor_provenance":prov,
    }
    errors=validate_assertion(row,source_unit=source_unit)
    if errors: raise ValueError("invalid assertion: "+"; ".join(errors))
    return row


def validate_assertion(row: Mapping[str,Any], *, source_unit: Optional[Mapping[str,Any]]=None) -> List[str]:
    e=[]
    if row.get("assertion_schema_version")!=ASSERTION_SCHEMA_VERSION: e.append("assertion_schema_version mismatch")
    for k in ("assertion_id","interpretation_id","source_unit_id","source_record_key","source_resource_id","source_version_id","normalized_proposition","assertion_type"):
        if not isinstance(row.get(k),str) or not row.get(k): e.append(f"{k} must be non-empty text")
    if isinstance(row.get("assertion_type"),str) and row.get("assertion_type") not in ASSERTION_TYPES: e.append("assertion_type is not in frozen controlled registry")
    for k in ("source_sha256","source_unit_sha256"):
        if not isinstance(row.get(k),str) or not re.fullmatch(r"[0-9a-f]{64}",str(row.get(k) or "")): e.append(f"{k} must be lowercase 64-hex")
    if row.get("source_scope") not in SOURCE_SCOPES: e.append("invalid source_scope")
    span=row.get("evidence_span"); structured=row.get("structured_evidence_path")
    if span is None and not structured: e.append("evidence closure missing")
    if span is not None and structured: e.append("assertion cannot use both text span and structured evidence path")
    if source_unit is None:
        e.append("unbound assertion: source unit not supplied")
    if span is not None:
        if not isinstance(span,dict): e.append("evidence_span must be object")
        else:
            start,end,text=span.get("char_start"),span.get("char_end"),span.get("text")
            valid_offsets=isinstance(start,int) and isinstance(end,int) and start>=0 and end>start
            if not valid_offsets: e.append("invalid evidence span character offsets")
            if not isinstance(text,str) or not text: e.append("evidence_span.text required")
            if isinstance(text,str) and text and span.get("text_sha256") != sha256_hex(text.encode("utf-8")): e.append("evidence_span.text_sha256 mismatch")
            if source_unit is not None:
                unit_text=source_unit.get("content_text")
                if not isinstance(unit_text,str):
                    e.append("text evidence span requires TEXT source unit")
                elif valid_offsets:
                    if end>len(unit_text):
                        e.append("evidence span outside source unit content")
                    else:
                        if unit_text[start:end] != text: e.append("evidence span text does not match source unit")
                        prefix=unit_text[:start].encode("utf-8"); evidence=unit_text[start:end].encode("utf-8")
                        if span.get("utf8_byte_start") != len(prefix) or span.get("utf8_byte_end") != len(prefix)+len(evidence): e.append("evidence span UTF-8 byte offsets mismatch")
    if structured:
        if not isinstance(structured,str):
            e.append("structured_evidence_path must be text")
        elif source_unit is not None:
            resolved,ok=_resolve_structured_path(source_unit,structured)
            if not ok: e.append("structured_evidence_path does not resolve against source unit")
            numeric=row.get("numeric")
            if ok and isinstance(numeric,dict) and "value" in numeric and isinstance(resolved,(int,float)) and not isinstance(resolved,bool):
                if numeric.get("value")!=resolved: e.append("numeric.value does not match structured source value")
    prov=row.get("extractor_provenance")
    if not isinstance(prov,dict): e.append("extractor_provenance must be object")
    else:
        mode=prov.get("mode")
        if mode not in {"DETERMINISTIC_PARSER","MODEL_ASSISTED"}: e.append("extractor_provenance.mode invalid")
        for key in ("engine","engine_version","code_manifest_sha256"):
            if not isinstance(prov.get(key),str) or not prov.get(key): e.append(f"extractor_provenance.{key} required")
        if isinstance(prov.get("code_manifest_sha256"),str) and not re.fullmatch(r"[0-9a-f]{64}",prov["code_manifest_sha256"]): e.append("extractor_provenance.code_manifest_sha256 must be lowercase 64-hex")
        if mode=="MODEL_ASSISTED":
            for key in ("model","model_revision","prompt_sha256"):
                if not isinstance(prov.get(key),str) or not prov.get(key): e.append(f"model-assisted provenance requires {key}")
            if isinstance(prov.get("prompt_sha256"),str) and not re.fullmatch(r"[0-9a-f]{64}",prov["prompt_sha256"]): e.append("prompt_sha256 must be lowercase 64-hex")
    if row.get("verification_status") not in VERIFICATION_STATES: e.append("invalid verification_status")
    for k in ("automatic_selection_allowed","canonical_authority","canonical_internal_eligible","generation_eligible","public_eligible"):
        if row.get(k) is not False: e.append(f"{k} must be false")
    if source_unit is not None:
        mappings=(("source_unit_id","source_unit_id"),("source_record_key","source_record_key"),("source_resource_id","source_resource_id"),("source_version_id","source_version_id"),("source_sha256","source_sha256"),("source_unit_sha256","content_sha256"),("source_scope","source_scope"))
        for ak,sk in mappings:
            if row.get(ak)!=source_unit.get(sk): e.append(f"{ak} does not match source unit")
    return e
