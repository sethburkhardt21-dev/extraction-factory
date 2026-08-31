"""Fail-closed provisional entity/candidate resolution for 09D audit preparation.

This module creates source-mention candidates and review cases only. It never
matches, merges, promotes, or assigns canonical 09D identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .package import candidate_id, source_identity_sha256

IDENTITY_RESOLUTION_SCHEMA_VERSION = "frontier-identity-resolution-1.0"
IDENTITY_CASE_SCHEMA_VERSION = "frontier-identity-case-1.0"
ALLOWED_DOMAINS = {
    "clinical_values", "concept", "condition", "crisis_management", "drug",
    "equipment", "procedure", "regional_technique", "special_population",
}

# Only mappings that are semantically strong enough to infer a domain without a model.
_SUBJECT_DOMAIN_BY_ASSERTION_TYPE = {
    "DOSING":"drug", "ADMINISTRATION":"drug", "INDICATION":"drug",
    "CONTRAINDICATION":"drug", "WARNING":"drug", "PRECAUTION":"drug",
    "ADVERSE_EFFECT":"drug", "DRUG_INTERACTION":"drug",
    "PHARMACOKINETIC":"drug", "PHARMACODYNAMIC":"drug", "MECHANISM":"drug",
    "FORMULATION":"drug", "CONCENTRATION":"drug", "ROUTE_APPLICABILITY":"drug",
    "PROCEDURAL_RECOMMENDATION":"procedure",
}
_OBJECT_DOMAIN_BY_ASSERTION_TYPE = {"DRUG_INTERACTION":"drug"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _case_id(payload: Mapping[str, Any]) -> str:
    return "ENTITYCASE:" + hashlib.sha256(_canonical(payload)).hexdigest()[:32]


def normalize_surface(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("entity surface must be non-empty text")
    # NFC only: identity normalization must not alter superscripts/fractions/etc.
    value = unicodedata.normalize("NFC", text).casefold()
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _verification_by_assertion(events: Iterable[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for event in events:
        aid = event.get("assertion_id")
        if isinstance(aid, str) and aid:
            # Multiple verifier events are historical evidence. Turn 6 consumes only one
            # supplied current event per assertion; ties fail closed below.
            if aid in out:
                out[aid] = {"_ambiguous_multiple_events": True, "assertion_id": aid}
            else:
                out[aid] = event
    return out


def _domain_for(assertion_type: str, role: str) -> Optional[str]:
    if role == "subject":
        return _SUBJECT_DOMAIN_BY_ASSERTION_TYPE.get(assertion_type)
    if role == "object":
        return _OBJECT_DOMAIN_BY_ASSERTION_TYPE.get(assertion_type)
    return None


def _candidate_row(*, assertion: Mapping[str, Any], role: str, surface: str, domain: str,
                   origin_package_id: str, verification: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    source_table = "frontier.assertion_entity_surface"
    # Source identity is the exact mention occurrence, not a global normalized-name cluster.
    source_key = f"{assertion['assertion_id']}|{role}|{surface}"
    sha = source_identity_sha256(source_table, source_key)
    verifier_entailed = bool(verification and verification.get("verdict") == "ENTAILED")
    downstream_ready = bool(verification and verification.get("downstream_semantic_ready") is True)
    return {
        "candidate_id": candidate_id(source_table, source_key),
        "domain": domain,
        "source_table": source_table,
        "source_key": source_key,
        "source_identity_sha256": sha,
        "origin_package_id": origin_package_id,
        "state": "REGISTERED",
        "legacy_entity_id": None,
        "assertion_id": assertion.get("assertion_id"),
        "interpretation_id": assertion.get("interpretation_id"),
        "source_unit_id": assertion.get("source_unit_id"),
        "mention_role": role.upper(),
        "surface_text": surface,
        "normalized_surface": normalize_surface(surface),
        "semantic_verdict": verification.get("verdict") if verification else None,
        "semantic_ready_for_resolution": verifier_entailed,
        "downstream_semantic_ready": downstream_ready,
        "automatic_identity_merge_allowed": False,
        "automatic_selection_allowed": False,
        "canonical_internal_eligible": False,
        "generation_eligible": False,
        "public_eligible": False,
    }


def resolve_assertion_mentions(*, assertions: Iterable[Mapping[str, Any]],
                               verification_events: Iterable[Mapping[str, Any]],
                               origin_package_id: str) -> Dict[str, Any]:
    """Register unresolved mention candidates without deciding 09D identity."""
    assertions = list(assertions)
    vmap = _verification_by_assertion(verification_events)
    candidates: List[Dict[str, Any]] = []
    aliases: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    cases: List[Dict[str, Any]] = []

    for assertion in assertions:
        aid = assertion.get("assertion_id")
        context = assertion.get("context") or {}
        surfaces = context.get("unresolved_entity_surfaces") or {}
        if not isinstance(surfaces, Mapping):
            continue
        verification = vmap.get(str(aid))
        multiple_verifiers = bool(verification and verification.get("_ambiguous_multiple_events"))
        for role_key, surface in sorted(surfaces.items()):
            role = "subject" if role_key == "subject_surface" else "object" if role_key == "object_surface" else None
            if role is None or not isinstance(surface, str) or not surface.strip():
                continue
            domain = _domain_for(str(assertion.get("assertion_type") or ""), role)
            base_case = {
                "assertion_id": aid,
                "interpretation_id": assertion.get("interpretation_id"),
                "source_unit_id": assertion.get("source_unit_id"),
                "mention_role": role.upper(),
                "surface_text": surface,
                "normalized_surface": normalize_surface(surface),
                "automatic_match_allowed": False,
                "automatic_merge_allowed": False,
                "automatic_promotion_allowed": False,
                "canonical_authority": False,
            }
            if domain is None:
                payload = {**base_case, "reason": "DOMAIN_AMBIGUOUS"}
                cases.append({
                    "identity_case_schema_version": IDENTITY_CASE_SCHEMA_VERSION,
                    "identity_case_id": _case_id(payload), **payload,
                    "candidate_id": None, "domain": None,
                    "state": "DOMAIN_AMBIGUOUS", "requires_review": True,
                })
                continue
            row = _candidate_row(assertion=assertion, role=role, surface=surface, domain=domain,
                                 origin_package_id=origin_package_id, verification=None if multiple_verifiers else verification)
            candidates.append(row)
            aliases.append({
                "candidate_id": row["candidate_id"],
                "alias": surface,
                "normalized_alias": row["normalized_surface"],
                "source": "assertion_entity_surface",
                "assertion_id": aid,
            })
            links.append({
                "candidate_id": row["candidate_id"], "assertion_id": aid,
                "interpretation_id": assertion.get("interpretation_id"),
                "source_unit_id": assertion.get("source_unit_id"),
                "mention_role": role.upper(), "link_role": "MENTION_EVIDENCE",
                "automatic_action_allowed": False,
            })
            if multiple_verifiers:
                state = "SEMANTIC_VERIFICATION_AMBIGUOUS"
            elif verification is None:
                state = "SEMANTIC_VERIFICATION_MISSING"
            elif verification.get("verdict") != "ENTAILED":
                state = "SEMANTIC_NOT_READY"
            else:
                state = "REGISTERED_FOR_READONLY_LOOKUP"
            payload = {**base_case, "candidate_id": row["candidate_id"], "domain": domain, "state": state}
            cases.append({
                "identity_case_schema_version": IDENTITY_CASE_SCHEMA_VERSION,
                "identity_case_id": _case_id(payload), **payload,
                "requires_review": state != "REGISTERED_FOR_READONLY_LOOKUP",
            })

    # Deterministic exact-row dedup only. No cross-mention clustering is performed.
    candidates = [dict(x) for _, x in sorted({x["candidate_id"]: x for x in candidates}.items())]
    aliases = sorted(aliases, key=lambda x: (x["candidate_id"], x["normalized_alias"], x["assertion_id"]))
    links = sorted(links, key=lambda x: (x["candidate_id"], x["assertion_id"], x["mention_role"]))
    cases = sorted(cases, key=lambda x: x["identity_case_id"])
    return {
        "identity_resolution_schema_version": IDENTITY_RESOLUTION_SCHEMA_VERSION,
        "status": "PASS",
        "candidate_records": candidates,
        "candidate_aliases": aliases,
        "candidate_assertion_links": links,
        "identity_cases": cases,
        "metrics": {
            "assertions_seen": len(assertions),
            "candidates_registered": len(candidates),
            "domain_ambiguous": sum(1 for x in cases if x["state"] == "DOMAIN_AMBIGUOUS"),
            "semantically_ready_for_lookup": sum(1 for x in cases if x["state"] == "REGISTERED_FOR_READONLY_LOOKUP"),
            "blocked_semantic": sum(1 for x in cases if x["state"].startswith("SEMANTIC_")),
        },
        "automatic_match_allowed": False,
        "automatic_merge_allowed": False,
        "automatic_promotion_allowed": False,
        "candidate_to_canonical_assignment_performed": False,
        "canonical_authority": False,
        "09d_mutation_performed": False,
    }
