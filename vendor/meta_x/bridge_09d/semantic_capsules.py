"""Deterministic semantic specialist capsules used by the independent verifier.

These checks are deliberately conservative. They can detect hard contradictions,
missing bindings, and escalation conditions; they are not allowed to manufacture
semantic entailment for free-text claims.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

CAPSULE_SCHEMA_VERSION = "frontier-semantic-capsules-1.1"
FINDING_STATES = {"PASS", "WARN", "FAIL", "NOT_APPLICABLE"}
SEVERITIES = {"INFO", "LOW", "MODERATE", "HIGH", "CRITICAL"}
RISK_LEVELS = {"LOW", "MODERATE", "HIGH", "CRITICAL"}

HIGH_RISK_ASSERTION_TYPES = {
    "DOSING", "ADMINISTRATION", "CONCENTRATION", "CONTRAINDICATION", "WARNING", "PRECAUTION",
    "ADVERSE_EFFECT", "DRUG_INTERACTION", "DIAGNOSTIC_THRESHOLD", "LAB_VALUE",
    "PROCEDURAL_RECOMMENDATION", "MONITORING_RECOMMENDATION", "MORTALITY",
    "SAFETY", "ROUTE_APPLICABILITY", "CLINICAL_VALUE", "GUIDELINE_RECOMMENDATION",
}
CRITICAL_NUMERIC_TYPES = {"DOSING", "CONCENTRATION", "DIAGNOSTIC_THRESHOLD", "LAB_VALUE", "CLINICAL_VALUE"}
RELATIONSHIP_TYPES = {
    "RISK_ASSOCIATION", "TREATMENT_EFFECT", "COMPARATIVE_EFFECTIVENESS", "CAUSATION",
    "ASSOCIATION", "DRUG_INTERACTION", "SUBGROUP_EFFECT", "POPULATION_SPECIFIC",
    "NEGATIVE_FINDING", "NO_EFFECT", "EFFICACY", "SAFETY", "MORTALITY", "MORBIDITY",
}

_SUPERSCRIPT_MAP = str.maketrans({
    "⁰":"0","¹":"1","²":"2","³":"3","⁴":"4","⁵":"5","⁶":"6","⁷":"7","⁸":"8","⁹":"9",
    "⁺":"+","⁻":"-","⁽":"(","⁾":")",
})
_SUBSCRIPT_MAP = str.maketrans({"₀":"0","₁":"1","₂":"2","₃":"3","₄":"4","₅":"5","₆":"6","₇":"7","₈":"8","₉":"9","₊":"+","₋":"-"})
_VULGAR = {"¼":"1/4","½":"1/2","¾":"3/4","⅐":"1/7","⅑":"1/9","⅒":"1/10","⅓":"1/3","⅔":"2/3","⅕":"1/5","⅖":"2/5","⅗":"3/5","⅘":"4/5","⅙":"1/6","⅚":"5/6","⅛":"1/8","⅜":"3/8","⅝":"5/8","⅞":"7/8"}

_ROUTE_SYNONYMS = {
    "IV": {"iv", "intravenous", "intravenously"},
    "PO": {"po", "oral", "orally", "by mouth"},
    "IM": {"im", "intramuscular", "intramuscularly"},
    "SC": {"sc", "sq", "subcutaneous", "subcutaneously"},
    "SL": {"sl", "sublingual", "sublingually"},
    "IN": {"intranasal", "intranasally"},
    "EPIDURAL": {"epidural", "epidurally"},
    "INTRATHECAL": {"intrathecal", "intrathecally", "it"},
    "INHALED": {"inhaled", "inhalation", "inhalational"},
    "TOPICAL": {"topical", "topically"},
}

_NEGATION_RE = re.compile(r"\b(no|not|none|without|neither|nor|didn['’]?t|doesn['’]?t|wasn['’]?t|were[n]?['’]?t|failed to|lack(?:ed|s|ing)?)\b", re.I)
_UNCERTAINTY_RE = re.compile(r"\b(may|might|could|can|possibly|potentially|suggest(?:s|ed)?|appears?|likely|unlikely|uncertain|associated with|correlat(?:e|ed|ion))\b", re.I)
_CAUSAL_RE = re.compile(r"\b(causes?|caused|causing|leads? to|result(?:s|ed)? in|produces?|produced|prevents?|prevented|reduces?|reduced|increases?|increased)\b", re.I)
_ASSOCIATION_RE = re.compile(r"\b(associated with|association|correlat(?:e|ed|ion)|linked to|relationship with)\b", re.I)
_DIRECTION_UP_RE = re.compile(r"\b(increas(?:e|es|ed|ing)|higher|greater|elevat(?:e|ed|ion)|rise|rose)\b", re.I)
_DIRECTION_DOWN_RE = re.compile(r"\b(decreas(?:e|es|ed|ing)|lower|less|reduc(?:e|es|ed|tion)|decline|fell|fall)\b", re.I)
_NO_EFFECT_RE = re.compile(r"\b(no (?:significant )?(?:difference|effect|change)|did not (?:change|improve|reduce|increase)|not significantly different|equivalent|noninferior|non-inferior)\b", re.I)


def _finding(code: str, state: str, severity: str, detail: str, **extra: Any) -> Dict[str, Any]:
    if state not in FINDING_STATES: raise ValueError(state)
    if severity not in SEVERITIES: raise ValueError(severity)
    return {"code": code, "state": state, "severity": severity, "detail": detail, **extra}


def canonical_semantic_text(text: str) -> str:
    """Comparison-only normalization; never used for source/assertion identity."""
    text = unicodedata.normalize("NFC", str(text or ""))
    for k,v in _VULGAR.items(): text=text.replace(k,v)
    # Preserve the meaning of superscripts by inserting ^ before a superscript run.
    text=re.sub(r"([0-9.])([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)", lambda m: m.group(1)+"^"+m.group(2).translate(_SUPERSCRIPT_MAP), text)
    text=text.translate(_SUBSCRIPT_MAP)
    text=text.replace("μ","µ").replace("×","x").replace("−","-").replace("–","-")
    return re.sub(r"\s+"," ",text).strip().lower()


def _evidence_text(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> str:
    span=assertion.get("evidence_span")
    if isinstance(span,Mapping) and isinstance(span.get("text"),str): return span["text"]
    if source_unit.get("content_representation")=="JSON":
        v=source_unit.get("content_json")
        if isinstance(v,bool): return "true" if v else "false"
        if v is None: return "null"
        if isinstance(v,(dict,list)):
            import json
            return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
        return str(v)
    return str(source_unit.get("content_text") or "")


def _full_unit_text(source_unit: Mapping[str,Any]) -> str:
    if source_unit.get("content_representation")=="TEXT": return str(source_unit.get("content_text") or "")
    return _evidence_text({},source_unit)


def _format_number(value: Any) -> Optional[str]:
    if isinstance(value,bool) or not isinstance(value,(int,float)): return None
    if isinstance(value,float):
        if not math.isfinite(value): return None
        if value.is_integer(): return str(int(value))
        return format(value,".15g")
    return str(value)


def _numeric_candidates(text: str) -> List[str]:
    t=canonical_semantic_text(text)
    # Fractions, scientific notation, exponents, decimals/integers, ranges.
    pattern=re.compile(r"(?<![a-z0-9])(?:\d+(?:\.\d+)?\s*x\s*10\^[+-]?\d+|\d+(?:\.\d+)?\^[+-]?\d+|\d+(?:\.\d+)?e[+-]?\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?)(?![a-z0-9])",re.I)
    return [re.sub(r"\s+","",m.group(0)) for m in pattern.finditer(t)]


def _numeric_token_value(token: str) -> Optional[float]:
    t=re.sub(r"\s+","",canonical_semantic_text(token))
    try:
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?/[+-]?\d+(?:\.\d+)?",t):
            a,b=t.split("/",1); return float(a)/float(b)
        m=re.fullmatch(r"([+-]?\d+(?:\.\d+)?)(?:x)?10\^([+-]?\d+)",t)
        if m: return float(m.group(1))*(10.0**int(m.group(2)))
        m=re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\^([+-]?\d+)",t)
        if m: return float(m.group(1))**int(m.group(2))
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?e[+-]?\d+",t,re.I): return float(t)
        return float(t)
    except Exception: return None

def _value_present(value: Any, text: str) -> bool:
    target=_format_number(value)
    if target is None: return True
    nums=_numeric_candidates(text)
    if target in nums: return True
    try:
        tv=float(target)
        for n in nums:
            nv=_numeric_token_value(n)
            if nv is not None and abs(nv-tv) <= max(1e-12,abs(tv)*1e-12): return True
    except Exception: pass
    return False

def _canonical_unit(unit: str) -> str:
    u=canonical_semantic_text(unit).replace("microgram","µg").replace("micrograms","µg")
    u=u.replace(" mcg"," µg").replace("mcg","µg").replace(" per ","/").replace("per ","/")
    u=u.replace("·"," ").replace("*"," ")
    # Convert denominator exponent notation: mg kg^-1 min^-1 -> mg/kg/min.
    parts=[]
    for tok in re.split(r"\s+",u.strip()):
        m=re.fullmatch(r"([a-zµ%]+)\^-1",tok)
        parts.append("/"+m.group(1) if m else tok)
    u="".join(parts).replace("//","/")
    return u.replace(" ","")

def _unit_variants(unit: str) -> set[str]:
    u=_canonical_unit(unit)
    variants={u,u.replace("µ","u"),u.replace("µ","mc") if "µ" in u else u}
    if u=="participants": variants|={"participants","subjects","patients","people","individuals"}
    return {x for x in variants if x}


def numeric_binding_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    numeric=assertion.get("numeric")
    evidence=_evidence_text(assertion,source_unit); unit_text=_full_unit_text(source_unit)
    if not isinstance(numeric,Mapping) or not numeric:
        # Literal numeric census is separate from semantic parameter binding. A
        # high-risk numeric proposition is not allowed to evade specialist checks
        # merely by omitting the structured numeric object.
        prop_nums=_numeric_candidates(str(assertion.get("normalized_proposition") or ""))
        ev_nums=_numeric_candidates(evidence)
        if prop_nums and assertion.get("assertion_type") in CRITICAL_NUMERIC_TYPES:
            return _finding("NUMERIC_BINDING","FAIL","CRITICAL","numeric-bearing high-risk assertion lacks structured numeric binding",proposition_numbers=prop_nums,evidence_numbers=ev_nums,binding_missing=True)
        if prop_nums and not set(prop_nums).issubset(set(ev_nums)):
            return _finding("NUMERIC_BINDING","WARN","HIGH","proposition contains numeric tokens not present in cited evidence and has no structured numeric binding",proposition_numbers=prop_nums,evidence_numbers=ev_nums,binding_missing=True)
        if prop_nums:
            return _finding("NUMERIC_BINDING","WARN","MODERATE","numeric tokens are present but semantic numeric parameter binding is absent",proposition_numbers=prop_nums,evidence_numbers=ev_nums,binding_missing=True)
        return _finding("NUMERIC_BINDING","NOT_APPLICABLE","INFO","no literal numeric claim detected")
    failures=[]; warnings=[]
    if "value" in numeric and not _value_present(numeric.get("value"),evidence):
        failures.append(f"numeric.value {numeric.get('value')!r} absent from cited evidence")
    # ranges
    for key in ("min","max","lower","upper"):
        if key in numeric and numeric.get(key) is not None and not _value_present(numeric.get(key),evidence):
            failures.append(f"numeric.{key} {numeric.get(key)!r} absent from cited evidence")
    unit=numeric.get("unit")
    if isinstance(unit,str) and unit.strip():
        # Structured scalar fields may carry their semantic unit in the controlled
        # schema mapping rather than inside the literal JSON value (e.g. CTG
        # enrollment count -> participants). The independent structured
        # re-derivation verifies that mapping later; do not fabricate a text-unit
        # failure here.
        if source_unit.get("content_representation") != "JSON":
            ev=_canonical_unit(evidence); full=_canonical_unit(unit_text)
            if not any(v in ev for v in _unit_variants(unit)):
                if any(v in full for v in _unit_variants(unit)): warnings.append("unit is present in source unit but outside cited span")
                else: failures.append(f"numeric.unit {unit!r} absent from source unit")
    if failures:
        return _finding("NUMERIC_BINDING","FAIL","CRITICAL" if assertion.get("assertion_type") in CRITICAL_NUMERIC_TYPES else "HIGH","; ".join(failures),failures=failures,warnings=warnings)
    if warnings:
        return _finding("NUMERIC_BINDING","WARN","MODERATE","; ".join(warnings),warnings=warnings)
    return _finding("NUMERIC_BINDING","PASS","INFO","structured numeric value/unit are source-bound")


def _route_mentions(route: str, text: str) -> bool:
    canonical=canonical_semantic_text(text)
    key=str(route).strip().upper()
    terms=_ROUTE_SYNONYMS.get(key,{str(route).lower()})
    for term in terms:
        # Short route acronyms need boundaries.
        if len(term)<=3 and term.isalpha():
            if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])",canonical): return True
        elif term in canonical: return True
    return False


def _detected_routes(text: str) -> set[str]:
    out=set()
    for route,terms in _ROUTE_SYNONYMS.items():
        if any(_route_mentions(route,text) for _ in [0]): out.add(route)
    return out



def negation_preservation_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    evidence=_evidence_text(assertion,source_unit); prop=str(assertion.get("normalized_proposition") or "")
    if source_unit.get("content_representation")=="JSON" and isinstance(source_unit.get("content_json"),bool):
        # Boolean structured semantics are validated by exact schema re-derivation; lexical negation is not meaningful here.
        return _finding("NEGATION_PRESERVATION","PASS","INFO","structured boolean polarity delegated to exact schema re-derivation")
    ev_neg=bool(_NEGATION_RE.search(evidence)); prop_neg=bool(_NEGATION_RE.search(prop)); declared=bool(assertion.get("negated"))
    if prop_neg != declared:
        return _finding("NEGATION_PRESERVATION","FAIL","HIGH","assertion negated flag disagrees with proposition surface")
    if ev_neg and not prop_neg:
        return _finding("NEGATION_PRESERVATION","FAIL","HIGH","source negation was dropped from proposition")
    if prop_neg and not ev_neg and not _NEGATION_RE.search(_full_unit_text(source_unit)):
        return _finding("NEGATION_PRESERVATION","FAIL","HIGH","negative proposition lacks negative source evidence")
    return _finding("NEGATION_PRESERVATION","PASS","INFO","negation/polarity preserved")


def certainty_modality_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    evidence=_evidence_text(assertion,source_unit); prop=str(assertion.get("normalized_proposition") or "")
    if source_unit.get("content_representation")=="JSON":
        return _finding("CERTAINTY_MODALITY","NOT_APPLICABLE","INFO","structured scalar has no free-text epistemic modality")
    ev_uncertain=bool(_UNCERTAINTY_RE.search(evidence)); prop_uncertain=bool(_UNCERTAINTY_RE.search(prop))
    if ev_uncertain and not prop_uncertain:
        return _finding("CERTAINTY_MODALITY","FAIL","HIGH","proposition strengthens hedged/uncertain source language")
    if prop_uncertain and not ev_uncertain:
        return _finding("CERTAINTY_MODALITY","WARN","LOW","proposition adds uncertainty not explicit in cited evidence")
    return _finding("CERTAINTY_MODALITY","PASS","INFO","certainty/modality not strengthened")


def conditionality_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    evidence=_evidence_text(assertion,source_unit); prop=str(assertion.get("normalized_proposition") or "")
    if source_unit.get("content_representation")=="JSON":
        return _finding("CONDITIONALITY","NOT_APPLICABLE","INFO","structured scalar conditionality delegated to schema semantics")
    cond_re=re.compile(r"\b(if|unless|only when|only in|in patients with|for patients with|among patients with|when|provided that)\b",re.I)
    ev_cond=bool(cond_re.search(evidence) or cond_re.search(_full_unit_text(source_unit)))
    prop_cond=bool(cond_re.search(prop)); declared=bool(assertion.get("conditional"))
    if ev_cond and not (prop_cond or declared):
        return _finding("CONDITIONALITY","FAIL","HIGH","source condition was dropped from proposition")
    if prop_cond and not ev_cond:
        return _finding("CONDITIONALITY","FAIL","HIGH","proposition introduces a condition absent from source evidence")
    if declared and not prop_cond:
        return _finding("CONDITIONALITY","WARN","LOW","conditional flag set but proposition does not surface the condition")
    return _finding("CONDITIONALITY","PASS","INFO","conditionality preserved")

def qualifier_scope_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    evidence=_evidence_text(assertion,source_unit); full=_full_unit_text(source_unit)
    prop=str(assertion.get("normalized_proposition") or "")
    if source_unit.get("content_representation")=="JSON":
        return _finding("QUALIFIER_SCOPE","PASS","INFO","structured scalar qualifier semantics are delegated to exact schema re-derivation",observed={"structured":True})
    context=assertion.get("context") if isinstance(assertion.get("context"),Mapping) else {}
    failures=[]; warnings=[]; observed={}
    ev_neg=bool(_NEGATION_RE.search(evidence)); prop_neg=bool(_NEGATION_RE.search(prop)); declared=bool(assertion.get("negated"))
    observed["evidence_negation"]=ev_neg; observed["proposition_negation"]=prop_neg; observed["declared_negated"]=declared
    # Only call a hard failure when evidence is explicitly negated but the assertion represents a positive claim, or vice versa.
    if ev_neg and not (prop_neg or declared): failures.append("evidence is explicitly negated but assertion is positive")
    if (prop_neg or declared) and not ev_neg and not _NEGATION_RE.search(full): failures.append("assertion is negated but source unit has no detected negation")
    route=context.get("route")
    detected_prop=_detected_routes(prop); detected_source=_detected_routes(evidence) | _detected_routes(full)
    observed["detected_proposition_routes"]=sorted(detected_prop); observed["detected_source_routes"]=sorted(detected_source)
    if isinstance(route,str) and route.strip():
        if not _route_mentions(route,evidence):
            if _route_mentions(route,full): warnings.append("route qualifier occurs in source unit but outside cited evidence span")
            elif _route_mentions(route,prop): failures.append(f"route qualifier {route!r} is asserted in proposition but absent from source unit")
            else: warnings.append(f"route qualifier {route!r} is structured context but not locally recoverable from source unit")
    elif detected_prop:
        # If the proposition itself makes route part of the claim, that route must
        # be structurally bound rather than left buried in prose.
        msg="route appears in proposition but assertion.context.route is missing"
        if assertion.get("assertion_type") in {"DOSING","ADMINISTRATION","ROUTE_APPLICABILITY","CONCENTRATION"}: failures.append(msg)
        else: warnings.append(msg)
    pop=context.get("population")
    if isinstance(pop,str) and pop.strip():
        cp=canonical_semantic_text(pop); cf=canonical_semantic_text(full)
        if cp not in cf: warnings.append(f"population qualifier {pop!r} not textually recoverable from source unit")
    timing=context.get("timing")
    if isinstance(timing,str) and timing.strip() and canonical_semantic_text(timing) not in canonical_semantic_text(full):
        warnings.append(f"timing qualifier {timing!r} not textually recoverable from source unit")
    ev_uncertain=bool(_UNCERTAINTY_RE.search(evidence)); prop_uncertain=bool(_UNCERTAINTY_RE.search(prop)); prop_causal=bool(_CAUSAL_RE.search(prop)); observed["evidence_uncertainty"]=ev_uncertain; observed["proposition_uncertainty"]=prop_uncertain
    if ev_uncertain and prop_causal and not prop_uncertain: warnings.append("proposition may overstate uncertain/associational evidence")
    if failures: return _finding("QUALIFIER_SCOPE","FAIL","HIGH","; ".join(failures),failures=failures,warnings=warnings,observed=observed)
    if warnings: return _finding("QUALIFIER_SCOPE","WARN","MODERATE","; ".join(warnings),warnings=warnings,observed=observed)
    return _finding("QUALIFIER_SCOPE","PASS","INFO","no deterministic qualifier contradiction detected",observed=observed)


def table_binding_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    if str(source_unit.get("source_scope") or "") != "TABLE":
        return _finding("TABLE_BINDING","NOT_APPLICABLE","INFO","source unit is not a table cell")
    locator=source_unit.get("locator") if isinstance(source_unit.get("locator"),Mapping) else {}
    if locator.get("locator_type") != "TABLE_CELL":
        return _finding("TABLE_BINDING","FAIL","HIGH","table-scope source unit lacks TABLE_CELL locator")
    row=locator.get("row_index"); col=locator.get("col_index")
    if not isinstance(row,int) or not isinstance(col,int):
        return _finding("TABLE_BINDING","FAIL","HIGH","table cell lacks deterministic row/column coordinates")
    headers=[str(x).strip() for x in (locator.get("header_refs") or []) if str(x).strip()]
    context=assertion.get("context") if isinstance(assertion.get("context"),Mapping) else {}
    claimed=[]
    for key in ("table_header","column_header","row_header"):
        value=context.get(key)
        if isinstance(value,str) and value.strip(): claimed.append((key,value.strip()))
    failures=[]
    canon_headers={canonical_semantic_text(x) for x in headers}
    for key,value in claimed:
        if canonical_semantic_text(value) not in canon_headers:
            failures.append(f"asserted {key} {value!r} is not bound to retained table headers")
    if failures:
        return _finding("TABLE_BINDING","FAIL","HIGH","; ".join(failures),headers=headers,row_index=row,col_index=col)
    numeric=isinstance(assertion.get("numeric"),Mapping) and bool(assertion.get("numeric"))
    if numeric and not headers:
        return _finding("TABLE_BINDING","WARN","MODERATE","numeric table assertion lacks retained row/column header semantics",headers=headers,row_index=row,col_index=col)
    return _finding("TABLE_BINDING","PASS","INFO","table cell is position-bound with retained header context",headers=headers,row_index=row,col_index=col)



def visual_binding_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    """Fail closed when a FIGURE unit contains caption text but no inspected visual payload.

    The current evidence plane preserves figure captions, not the figure pixels/plot geometry.
    Caption-grounded text can still be entailed by the caption, but visual semantics such as
    plotted trends, bar heights, image findings, or values read from the graphic require a
    separate visual specialist before downstream semantic readiness.
    """
    if str(source_unit.get("source_scope") or "") != "FIGURE":
        return _finding("VISUAL_BINDING","NOT_APPLICABLE","INFO","source unit is not figure evidence")
    locator=source_unit.get("locator") if isinstance(source_unit.get("locator"),Mapping) else {}
    if locator.get("locator_type") != "FIGURE":
        return _finding("VISUAL_BINDING","FAIL","HIGH","figure-scope source unit lacks FIGURE locator")
    context=assertion.get("context") if isinstance(assertion.get("context"),Mapping) else {}
    visual_claim=bool(context.get("visual_semantics_required"))
    prop=canonical_semantic_text(str(assertion.get("normalized_proposition") or ""))
    visual_terms=("curve","graph","figure","image","scan","plot","bar","panel","radiograph","ultrasound","mri","ct ","trend")
    if not visual_claim:
        visual_claim=any(term in prop for term in visual_terms)
    if visual_claim:
        return _finding("VISUAL_BINDING","WARN","HIGH","claim depends on visual semantics but current source unit contains caption text only; image/plot payload has not been independently inspected",visual_payload_available=False)
    return _finding("VISUAL_BINDING","WARN","MODERATE","figure evidence is caption-only; downstream semantic readiness requires explicit visual review before treating the figure as fully inspected",visual_payload_available=False)

def relationship_semantics_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any]) -> Dict[str,Any]:
    at=str(assertion.get("assertion_type") or "")
    prop=str(assertion.get("normalized_proposition") or ""); evidence=_evidence_text(assertion,source_unit); full=_full_unit_text(source_unit)
    if at not in RELATIONSHIP_TYPES and not (_CAUSAL_RE.search(prop) or _ASSOCIATION_RE.search(prop) or _DIRECTION_UP_RE.search(prop) or _DIRECTION_DOWN_RE.search(prop)):
        return _finding("RELATIONSHIP_SEMANTICS","NOT_APPLICABLE","INFO","no relationship semantics routed")
    failures=[]; warnings=[]
    e_assoc=bool(_ASSOCIATION_RE.search(evidence) or _ASSOCIATION_RE.search(full)); p_causal=bool(_CAUSAL_RE.search(prop))
    if e_assoc and p_causal and at=="CAUSATION": failures.append("causal claim is supported only by associational wording")
    elif e_assoc and p_causal: warnings.append("causal wording may overstate associational source language")
    e_up=bool(_DIRECTION_UP_RE.search(evidence) or _DIRECTION_UP_RE.search(full)); e_down=bool(_DIRECTION_DOWN_RE.search(evidence) or _DIRECTION_DOWN_RE.search(full)); e_none=bool(_NO_EFFECT_RE.search(evidence) or _NO_EFFECT_RE.search(full))
    p_up=bool(_DIRECTION_UP_RE.search(prop)); p_down=bool(_DIRECTION_DOWN_RE.search(prop)); p_none=bool(_NO_EFFECT_RE.search(prop) or at in {"NEGATIVE_FINDING","NO_EFFECT"})
    if e_up and not e_down and p_down: failures.append("directionality reversal: source increase vs proposition decrease")
    if e_down and not e_up and p_up: failures.append("directionality reversal: source decrease vs proposition increase")
    if e_none and (p_up or p_down) and not p_none: failures.append("source states no effect/difference but proposition asserts direction")
    if p_none and not e_none and (e_up or e_down): warnings.append("no-effect proposition conflicts with directional source language")
    if failures: return _finding("RELATIONSHIP_SEMANTICS","FAIL","HIGH","; ".join(failures),failures=failures,warnings=warnings)
    if warnings: return _finding("RELATIONSHIP_SEMANTICS","WARN","MODERATE","; ".join(warnings),warnings=warnings)
    return _finding("RELATIONSHIP_SEMANTICS","PASS","INFO","no deterministic relationship contradiction detected")


def atomicity_check(assertion: Mapping[str,Any]) -> Dict[str,Any]:
    text=str(assertion.get("normalized_proposition") or "").strip()
    if not text: return _finding("ATOMICITY","FAIL","HIGH","empty proposition")
    # Assertion engine already blocks semicolons/newlines. Catch conjunction-heavy multi-predicate claims conservatively.
    predicates=len(re.findall(r"\b(?:and|but|whereas|while|however)\b",text,re.I))
    if predicates>=1: return _finding("ATOMICITY","WARN","MODERATE","proposition may bundle multiple independently auditable clauses")
    return _finding("ATOMICITY","PASS","INFO","no obvious compound-claim signal")


def provenance_check(assertion: Mapping[str,Any], source_unit: Mapping[str,Any], contract_errors: Sequence[str]) -> Dict[str,Any]:
    if contract_errors:
        return _finding("PROVENANCE_CLOSURE","FAIL","CRITICAL","; ".join(contract_errors[:10]),errors=list(contract_errors[:20]))
    missing=[]
    for k in ("source_sha256","source_unit_sha256","source_unit_id","source_resource_id","source_version_id"):
        if not assertion.get(k): missing.append(k)
    if not assertion.get("evidence_span") and not assertion.get("structured_evidence_path"): missing.append("evidence_locator")
    if missing: return _finding("PROVENANCE_CLOSURE","FAIL","CRITICAL","missing provenance dimensions: "+", ".join(missing),missing=missing)
    return _finding("PROVENANCE_CLOSURE","PASS","INFO","assertion is cryptographically bound to a validated source unit")


def risk_route(assertion: Mapping[str,Any], source_unit: Mapping[str,Any], findings: Sequence[Mapping[str,Any]]) -> Dict[str,Any]:
    at=str(assertion.get("assertion_type") or "")
    scope=str(source_unit.get("source_scope") or "")
    numeric=isinstance(assertion.get("numeric"),Mapping) and bool(assertion.get("numeric"))
    risk="LOW"; reasons=[]; required=["PROVENANCE_CLOSURE","QUALIFIER_SCOPE","ATOMICITY"]
    if numeric or at in CRITICAL_NUMERIC_TYPES:
        required.append("NUMERIC_BINDING")
    if at in RELATIONSHIP_TYPES:
        required.append("RELATIONSHIP_SEMANTICS")
    if scope=="TABLE":
        required.append("TABLE_BINDING")
    if scope=="FIGURE":
        required.append("VISUAL_BINDING")
    if at in HIGH_RISK_ASSERTION_TYPES:
        risk="HIGH"; reasons.append("high-risk clinical assertion type")
    elif at in RELATIONSHIP_TYPES or numeric:
        risk="MODERATE"; reasons.append("semantic relationship or numeric claim")
    if numeric and at in CRITICAL_NUMERIC_TYPES:
        risk="CRITICAL"; reasons.append("high-risk numeric clinical claim")
    if scope in {"TABLE","FIGURE"} and risk in {"LOW","MODERATE"}:
        risk="HIGH"; reasons.append("table/figure context requires specialist binding")
    if scope in {"ABSTRACT_ONLY","ABSTRACT_WITHIN_FULLTEXT"}:
        if risk=="LOW": risk="MODERATE"
        elif risk=="MODERATE": risk="HIGH"
        reasons.append("abstract-scope evidence")
    if scope=="REGISTRY_STRUCTURED" and risk=="LOW":
        risk="MODERATE"; reasons.append("structured registry semantic binding")
    hard_fail=any(f.get("state")=="FAIL" and f.get("severity") in {"HIGH","CRITICAL"} for f in findings)
    warns=any(f.get("state")=="WARN" for f in findings)
    if hard_fail: reasons.append("deterministic specialist failure")
    if warns: reasons.append("unresolved specialist warning")
    # High/critical claims require an independent semantic reviewer even when deterministic checks are clean.
    reviewer_required=risk in {"HIGH","CRITICAL"}
    frontier_adjudication_required=risk=="CRITICAL" or hard_fail
    return {
        "risk_level":risk,"risk_reasons":reasons,"required_specialists":sorted(set(required)),
        "blind_semantic_reviewer_required":reviewer_required,
        "frontier_adjudication_required":frontier_adjudication_required,
        "automatic_selection_allowed":False,
    }


def run_specialist_capsules(assertion: Mapping[str,Any], source_unit: Mapping[str,Any], *, contract_errors: Sequence[str]=()) -> Dict[str,Any]:
    findings=[
        provenance_check(assertion,source_unit,contract_errors),
        numeric_binding_check(assertion,source_unit),
        negation_preservation_check(assertion,source_unit),
        certainty_modality_check(assertion,source_unit),
        conditionality_check(assertion,source_unit),
        qualifier_scope_check(assertion,source_unit),
        table_binding_check(assertion,source_unit),
        visual_binding_check(assertion,source_unit),
        relationship_semantics_check(assertion,source_unit),
        atomicity_check(assertion),
    ]
    route=risk_route(assertion,source_unit,findings)
    return {"capsule_schema_version":CAPSULE_SCHEMA_VERSION,"findings":findings,"risk_route":route}
