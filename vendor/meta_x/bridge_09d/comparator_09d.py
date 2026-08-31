"""Strictly read-only 09D identity lookup and assertion comparison.

Actual 09D SQLite comparison is hash-bound and opened query-only. Offline tests use
an explicit synthetic snapshot contract and are never represented as a real 09D run.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .assertions import normalize_proposition
from .identity_resolution import normalize_surface

COMPARATOR_SCHEMA_VERSION = "frontier-09d-readonly-comparator-1.0"
SNAPSHOT_SCHEMA_VERSION = "frontier-09d-comparison-snapshot-1.0"
COMPARISON_SCHEMA_VERSION = "frontier-09d-assertion-comparison-1.0"
IDENTITY_LOOKUP_SCHEMA_VERSION = "frontier-09d-identity-lookup-1.0"
CLASSIFICATIONS = {
    "BLOCKED_SEMANTIC_VERIFICATION", "IDENTITY_AMBIGUOUS", "IDENTITY_NOT_FOUND",
    "EXACT_EXISTING", "SUPPORTING_EXISTING", "CONTRADICTORY", "CONTEXT_DIFFERENT",
    "NOVEL", "UNRESOLVED",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical(payload)).hexdigest()[:32]


def normalize_compare_text(text: str) -> str:
    value = normalize_proposition(text).casefold()
    value = re.sub(r"[\s\u00a0]+", " ", value).strip()
    return value


def _table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [str(r[1]) for r in con.execute(f'PRAGMA table_info("{table}")')]


def _pick(columns: Sequence[str], options: Sequence[str]) -> Optional[str]:
    for name in options:
        if name in columns:
            return name
    return None


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def build_snapshot_from_sqlite(*, sqlite_path: Path, expected_sha256: str) -> Dict[str, Any]:
    """Read actual 09D only through immutable/query-only SQLite access.

    This adapter fails closed when the required entity/name schema is unavailable.
    Assertion text is optional: if the legacy assertion table exposes no recognized text
    column, identity lookup still works and semantic comparison stays UNRESOLVED.
    """
    sqlite_path = Path(sqlite_path)
    actual_sha = sha256_file(sqlite_path)
    if actual_sha != expected_sha256:
        raise ValueError("09D SQLite SHA-256 mismatch")
    uri = f"file:{sqlite_path.resolve().as_posix()}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        if con.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise RuntimeError("09D SQLite query_only could not be established")
        tables = {str(r[0]) for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"entity", "entity_name"}.issubset(tables):
            raise ValueError("09D SQLite lacks entity/entity_name tables")
        ecols = _table_columns(con, "entity")
        ncols = _table_columns(con, "entity_name")
        eid = _pick(ecols, ("canonical_id", "entity_id")); domain = _pick(ecols, ("owning_domain", "domain")); lifecycle = _pick(ecols, ("lifecycle_status", "status"))
        neid = _pick(ncols, ("canonical_id", "entity_id")); namecol = _pick(ncols, ("name_text", "normalized_name", "name", "alias_text", "text", "display_name")); normcol = _pick(ncols, ("normalized_name",))
        if not all((eid, domain, lifecycle, neid, namecol)):
            raise ValueError("09D entity/name schema lacks required comparison columns")
        entities: Dict[str, Dict[str, Any]] = {}
        for row in con.execute(f"SELECT {_q(eid)}, {_q(domain)}, {_q(lifecycle)} FROM entity"):
            entities[str(row[0])] = {"canonical_id": str(row[0]), "owning_domain": row[1], "lifecycle_status": row[2], "names": []}
        select_name = f"SELECT {_q(neid)}, {_q(namecol)}" + (f", {_q(normcol)}" if normcol else "") + " FROM entity_name"
        for row in con.execute(select_name):
            target = entities.get(str(row[0]))
            if target is None or row[1] is None:
                continue
            raw = str(row[1]); normalized = str(row[2]) if normcol and row[2] is not None else normalize_surface(raw)
            target["names"].append({"name_text": raw, "normalized_name": normalized})
        assertions: List[Dict[str, Any]] = []
        assertion_text_column = None
        assertion_schema_supported = False
        if "assertion" in tables:
            acols = _table_columns(con, "assertion")
            aid = _pick(acols, ("assertion_id", "id"))
            textcol = _pick(acols, ("normalized_proposition", "assertion_text", "statement_text", "claim_text", "proposition", "text"))
            typecol = _pick(acols, ("assertion_type", "claim_type", "type"))
            entitycol = _pick(acols, ("canonical_id", "entity_id", "subject_entity_id"))
            assertion_text_column = textcol
            if aid and textcol:
                assertion_schema_supported = True
                cols = [aid, textcol] + ([typecol] if typecol else []) + ([entitycol] if entitycol else [])
                for row in con.execute("SELECT " + ", ".join(_q(x) for x in cols) + " FROM assertion"):
                    pos = 0; rid = row[pos]; pos += 1; text = row[pos]; pos += 1
                    atype = row[pos] if typecol else None; pos += 1 if typecol else 0
                    ent = row[pos] if entitycol else None
                    if rid is None or text is None: continue
                    assertions.append({
                        "assertion_id": str(rid), "canonical_id": str(ent) if ent is not None else None,
                        "normalized_proposition": str(text), "assertion_type": atype,
                        "context": {}, "numeric": None,
                    })
        payload = {
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
            "source_kind": "ACTUAL_09D_DATABASE_READONLY",
            "database_sha256": actual_sha,
            "entities": sorted(entities.values(), key=lambda x: x["canonical_id"]),
            "assertions": assertions,
            "assertion_schema_supported": assertion_schema_supported,
            "assertion_text_column": assertion_text_column,
            "query_only": True,
            "mutation_performed": False,
        }
        payload["snapshot_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
        return payload
    finally:
        con.close()


def validate_snapshot(snapshot: Mapping[str, Any]) -> List[str]:
    e: List[str] = []
    if snapshot.get("snapshot_schema_version") != SNAPSHOT_SCHEMA_VERSION: e.append("snapshot_schema_version mismatch")
    if snapshot.get("source_kind") not in {"ACTUAL_09D_DATABASE_READONLY", "SYNTHETIC_CONTRACT_FIXTURE"}: e.append("invalid source_kind")
    if not isinstance(snapshot.get("entities"), list): e.append("entities must be list")
    if not isinstance(snapshot.get("assertions"), list): e.append("assertions must be list")
    if snapshot.get("source_kind") == "ACTUAL_09D_DATABASE_READONLY":
        if snapshot.get("query_only") is not True or snapshot.get("mutation_performed") is not False: e.append("actual 09D snapshot must be query-only and non-mutating")
        if not re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get("database_sha256") or "")): e.append("actual 09D snapshot database_sha256 required")
    return e


def lookup_identity(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    errors = validate_snapshot(snapshot)
    if errors: raise ValueError("invalid 09D snapshot: " + "; ".join(errors))
    normalized = str(candidate.get("normalized_surface") or normalize_surface(str(candidate.get("surface_text") or "")))
    domain = candidate.get("domain")
    exact: List[Dict[str, Any]] = []
    possible: List[Dict[str, Any]] = []
    for entity in snapshot.get("entities") or []:
        if domain and entity.get("owning_domain") != domain:
            continue
        names = entity.get("names") or []
        normalized_names = {str(n.get("normalized_name") or normalize_surface(str(n.get("name_text") or ""))) for n in names if n.get("name_text") or n.get("normalized_name")}
        if normalized in normalized_names:
            exact.append({"canonical_id": entity.get("canonical_id"), "owning_domain": entity.get("owning_domain"), "lifecycle_status": entity.get("lifecycle_status"), "match_basis": "EXACT_NORMALIZED_NAME"})
        else:
            # Conservative alias candidate only: token-set exact after punctuation removal.
            key = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
            for nn in normalized_names:
                alt = re.sub(r"[^\w]+", " ", nn, flags=re.UNICODE).strip()
                if key and alt and key == alt:
                    possible.append({"canonical_id": entity.get("canonical_id"), "owning_domain": entity.get("owning_domain"), "lifecycle_status": entity.get("lifecycle_status"), "match_basis": "PUNCTUATION_NORMALIZED_ALIAS"})
                    break
    if len(exact) == 1:
        state = "EXACT_NAME_SINGLE_CANDIDATE_TARGET" if exact[0].get("lifecycle_status") in {"CANDIDATE", "QUARANTINED"} else "EXACT_NAME_SINGLE_CANONICAL_TARGET"
    elif len(exact) > 1: state = "MULTIPLE_EXACT_MATCHES"
    elif possible: state = "POSSIBLE_ALIAS_MATCHES"
    else: state = "NO_MATCH"
    payload = {"candidate_id": candidate.get("candidate_id"), "snapshot_sha256": snapshot.get("snapshot_sha256"), "state": state, "exact": exact, "possible": possible}
    return {
        "identity_lookup_schema_version": IDENTITY_LOOKUP_SCHEMA_VERSION,
        "identity_lookup_id": _id("IDLOOKUP:", payload),
        "candidate_id": candidate.get("candidate_id"), "domain": domain,
        "surface_text": candidate.get("surface_text"), "normalized_surface": normalized,
        "state": state, "exact_matches": exact, "possible_matches": possible,
        "automatic_match_allowed": False, "automatic_merge_allowed": False,
        "canonical_assignment_performed": False, "requires_review": state != "NO_MATCH",
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
    }


def _context_key(assertion: Mapping[str, Any]) -> Dict[str, Any]:
    context = dict(assertion.get("context") or {})
    # Unresolved entity surfaces are identity metadata, not a clinical comparison dimension.
    context.pop("unresolved_entity_surfaces", None)
    return {
        "context": context,
        "certainty": assertion.get("certainty"),
        "negated": bool(assertion.get("negated", False)),
        "conditional": bool(assertion.get("conditional", False)),
        "study_context": dict(assertion.get("study_context") or {}),
    }


def _numeric_equal(a: Any, b: Any) -> bool:
    if a is None and b is None: return True
    if not isinstance(a, Mapping) or not isinstance(b, Mapping): return False
    return dict(a) == dict(b)


def compare_assertion(*, assertion: Mapping[str, Any], verification_event: Mapping[str, Any],
                      identity_lookup: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    if verification_event.get("assertion_id") != assertion.get("assertion_id"):
        raise ValueError("verification event does not belong to assertion")
    comparison_eligible = verification_event.get("verdict") == "ENTAILED"
    exact_matches = list(identity_lookup.get("exact_matches") or [])
    target_id = exact_matches[0].get("canonical_id") if len(exact_matches) == 1 and identity_lookup.get("state") == "EXACT_NAME_SINGLE_CANONICAL_TARGET" else None
    classification = "UNRESOLVED"; matched: List[str] = []; reason = ""
    if not comparison_eligible:
        classification = "BLOCKED_SEMANTIC_VERIFICATION"; reason = "assertion is not independently entailed; read-only semantic comparison is blocked"
    elif identity_lookup.get("state") in {"MULTIPLE_EXACT_MATCHES", "POSSIBLE_ALIAS_MATCHES", "EXACT_NAME_SINGLE_CANDIDATE_TARGET"}:
        classification = "IDENTITY_AMBIGUOUS"; reason = "identity lookup did not yield one canonical target"
    elif identity_lookup.get("state") == "NO_MATCH":
        classification = "IDENTITY_NOT_FOUND"; reason = "no exact existing 09D identity match"
    elif not target_id:
        classification = "IDENTITY_AMBIGUOUS"; reason = "canonical target unavailable"
    else:
        pool = [x for x in snapshot.get("assertions") or [] if x.get("canonical_id") in (None, target_id)]
        same_entity = [x for x in pool if x.get("canonical_id") == target_id] or pool
        incoming_text = normalize_compare_text(str(assertion.get("normalized_proposition") or ""))
        exact_text = [x for x in same_entity if normalize_compare_text(str(x.get("normalized_proposition") or "")) == incoming_text]
        if exact_text:
            classification = "EXACT_EXISTING"; matched = [str(x.get("assertion_id")) for x in exact_text]; reason = "normalized proposition exactly matches existing assertion"
        else:
            typed = [x for x in same_entity if x.get("assertion_type") and x.get("assertion_type") == assertion.get("assertion_type")]
            if typed:
                same_context = [x for x in typed if dict(x.get("context") or {}) == _context_key(assertion)["context"]]
                same_numeric = [x for x in same_context if _numeric_equal(x.get("numeric"), assertion.get("numeric"))]
                if same_numeric:
                    classification = "SUPPORTING_EXISTING"; matched = [str(x.get("assertion_id")) for x in same_numeric]; reason = "same entity/type/context/numeric semantics with different wording"
                elif same_context and assertion.get("numeric") is not None and any(x.get("numeric") is not None for x in same_context):
                    classification = "CONTRADICTORY"; matched = [str(x.get("assertion_id")) for x in same_context]; reason = "same entity/type/context carries different numeric value"
                else:
                    classification = "CONTEXT_DIFFERENT"; matched = [str(x.get("assertion_id")) for x in typed]; reason = "same entity/type exists under different context or numeric semantics"
            elif snapshot.get("assertion_schema_supported") is True:
                classification = "NOVEL"; reason = "identity resolved and no same-type assertion exists in comparison snapshot"
            else:
                classification = "UNRESOLVED"; reason = "09D snapshot does not expose sufficient typed assertion semantics"
    if classification not in CLASSIFICATIONS: raise RuntimeError("invalid comparator classification")
    payload = {"assertion_id": assertion.get("assertion_id"), "verification_id": verification_event.get("verification_id"), "identity_lookup_id": identity_lookup.get("identity_lookup_id"), "snapshot_sha256": snapshot.get("snapshot_sha256"), "classification": classification, "matched": sorted(matched)}
    return {
        "comparison_schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_id": _id("09DCMP:", payload),
        "assertion_id": assertion.get("assertion_id"),
        "interpretation_id": assertion.get("interpretation_id"),
        "verification_id": verification_event.get("verification_id"),
        "identity_lookup_id": identity_lookup.get("identity_lookup_id"),
        "candidate_id": identity_lookup.get("candidate_id"),
        "proposed_target_canonical_id": target_id,
        "classification": classification,
        "matched_09d_assertion_ids": sorted(matched),
        "reason": reason,
        "snapshot_source_kind": snapshot.get("source_kind"),
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "09d_database_sha256": snapshot.get("database_sha256"),
        "automatic_selection_allowed": False,
        "automatic_merge_allowed": False,
        "09d_mutation_performed": False,
        "canonical_authority": False,
    }


def compare_ready_candidates(*, assertions: Iterable[Mapping[str, Any]], verification_events: Iterable[Mapping[str, Any]],
                             candidate_records: Iterable[Mapping[str, Any]], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    errors = validate_snapshot(snapshot)
    if errors: raise ValueError("invalid 09D snapshot: " + "; ".join(errors))
    amap = {str(a.get("assertion_id")): a for a in assertions}
    vmap = {str(v.get("assertion_id")): v for v in verification_events}
    candidates = list(candidate_records)
    lookups: List[Dict[str, Any]] = []
    comparisons: List[Dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda x: str(x.get("candidate_id"))):
        lookup = lookup_identity(candidate, snapshot); lookups.append(lookup)
        assertion = amap.get(str(candidate.get("assertion_id"))); verification = vmap.get(str(candidate.get("assertion_id")))
        if assertion is None or verification is None:
            continue
        comparisons.append(compare_assertion(assertion=assertion, verification_event=verification, identity_lookup=lookup, snapshot=snapshot))
    return {
        "comparator_schema_version": COMPARATOR_SCHEMA_VERSION,
        "status": "PASS",
        "snapshot_source_kind": snapshot.get("source_kind"),
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "09d_database_sha256": snapshot.get("database_sha256"),
        "actual_09d_database_bound": snapshot.get("source_kind") == "ACTUAL_09D_DATABASE_READONLY",
        "identity_lookups": lookups,
        "comparisons": comparisons,
        "metrics": {
            "candidate_lookups": len(lookups), "comparisons": len(comparisons),
            "classification_counts": {c: sum(1 for x in comparisons if x["classification"] == c) for c in sorted(CLASSIFICATIONS)},
        },
        "read_only": True,
        "09d_mutation_performed": False,
        "automatic_selection_allowed": False,
        "canonical_authority": False,
    }
