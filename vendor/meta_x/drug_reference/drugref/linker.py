from __future__ import annotations
from typing import Any, Dict, Iterable, List
from .common import normalize_name, stable_hash


def _index(rows: Iterable[Dict[str,Any]]) -> Dict[str,List[Dict[str,Any]]]:
    out: Dict[str,List[Dict[str,Any]]] = {}
    for r in rows:
        key=normalize_name(str(r.get("name") or ""))
        if key: out.setdefault(key,[]).append(r)
    return out


def _identity(row: Dict[str, Any], source: str) -> str:
    if source == "rxnorm":
        ids = row.get("rxcuis") or ([row.get("rxcui")] if row.get("rxcui") else [])
        if ids:
            return "rxnorm:" + ",".join(sorted(str(x) for x in ids))
    if source == "livertox":
        if row.get("source_nbk_id"):
            return "livertox:" + str(row["source_nbk_id"])
        if row.get("source_url"):
            return "livertox:" + str(row["source_url"])
    return str(row.get("source_record_sha256") or stable_hash(row))


def _candidate_rows(index: Dict[str,List[Dict[str,Any]]], names: List[str], source: str) -> List[Dict[str,Any]]:
    unique: Dict[str,Dict[str,Any]] = {}
    for name in names:
        for row in index.get(normalize_name(name),[]):
            unique[_identity(row, source)] = row
    return [unique[k] for k in sorted(unique)]


def _candidate_ids(rows: List[Dict[str, Any]], source: str) -> List[str]:
    return [_identity(r, source) for r in rows]


def link(drugbank_rows: Iterable[Dict[str,Any]], rxnorm_rows: Iterable[Dict[str,Any]], livertox_rows: Iterable[Dict[str,Any]]):
    """Conservative exact alias linkage with explicit candidate evidence.

    A match is accepted only when normalized primary/synonym aliases resolve to
    exactly one distinct source identity. Ambiguous candidates are retained in
    linkage evidence instead of being guessed or discarded.
    """
    rx=_index(rxnorm_rows); lt=_index(livertox_rows)
    result=[]
    seen_db=set()
    for db in drugbank_rows:
        dbid=str(db.get("drugbank_id") or "")
        if not dbid:
            raise ValueError("DrugBank record missing primary drugbank_id")
        if dbid in seen_db:
            raise ValueError(f"duplicate DrugBank primary identifier: {dbid}")
        seen_db.add(dbid)
        primary=str(db.get("name") or "")
        if not primary.strip():
            raise ValueError(f"DrugBank record {dbid} missing name")
        aliases=[primary]+[str(x) for x in (db.get("synonyms") or []) if str(x).strip()]
        normalized_aliases=sorted(set(normalize_name(x) for x in aliases if normalize_name(x)))
        rxc=_candidate_rows(rx,aliases,"rxnorm"); ltc=_candidate_rows(lt,aliases,"livertox")
        rx_status="matched" if len(rxc)==1 else ("missing" if not rxc else "ambiguous")
        lt_status="matched" if len(ltc)==1 else ("missing" if not ltc else "ambiguous")
        row={
            "name":db.get("name"),
            "name_normalized":normalize_name(primary),
            "drugbank":db,
            "rxnorm":rxc[0] if len(rxc)==1 else None,
            "livertox":ltc[0] if len(ltc)==1 else None,
            "linkage":{
                "method":"normalized_exact_primary_or_synonym","confidence_policy":"UNSCORED_EXACT_CANDIDATE_LINK",
                "aliases_considered":normalized_aliases,
                "rxnorm_candidates":len(rxc),
                "livertox_candidates":len(ltc),
                "rxnorm_candidate_ids":_candidate_ids(rxc,"rxnorm"),
                "livertox_candidate_ids":_candidate_ids(ltc,"livertox"),
                "rxnorm_status":rx_status,
                "livertox_status":lt_status,
                "rxnorm_confidence":None,
                "livertox_confidence":None,
            },
        }
        row["linkage_record_sha256"] = stable_hash(row["linkage"])
        result.append(row)
    return result
