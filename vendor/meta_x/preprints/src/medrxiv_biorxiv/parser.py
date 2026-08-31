"""Validation and deterministic version resolution for preprints."""
from __future__ import annotations
from typing import Any, Dict, Iterable, Iterator, List, Tuple


def version_number(rec: Dict[str, Any]) -> int:
    try:
        return int(str(rec.get("version") or "1"))
    except (TypeError, ValueError):
        return 1


def record_identity(rec: Dict[str, Any]) -> Tuple[str, str, int]:
    return (
        str(rec.get("server") or "").lower(),
        str(rec.get("doi") or "").lower(),
        version_number(rec),
    )


def dedup_versions(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove exact logical duplicate versions but retain version history."""
    chosen: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    for rec in records:
        key = record_identity(rec)
        if not key[1]:
            continue
        old = chosen.get(key)
        if old is None:
            chosen[key] = rec
            continue
        old_hash = str(old.get("source_record_sha256", ""))
        new_hash = str(rec.get("source_record_sha256", ""))
        if old_hash == new_hash:
            continue
        raise ValueError(f"conflicting content for identical preprint version {key}: {old_hash} != {new_hash}")
    return [chosen[k] for k in sorted(chosen)]


def latest_by_doi(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for rec in records:
        server = str(rec.get("server") or "").lower()
        doi = str(rec.get("doi") or "").lower()
        if not doi:
            continue
        key = (server, doi)
        old = latest.get(key)
        if old is None or version_number(rec) > version_number(old):
            latest[key] = rec
        elif version_number(rec) == version_number(old):
            old_hash = str(old.get("source_record_sha256", ""))
            new_hash = str(rec.get("source_record_sha256", ""))
            if old_hash != new_hash:
                raise ValueError(f"conflicting content for latest preprint version {key}: {old_hash} != {new_hash}")
    return [latest[k] for k in sorted(latest)]


def validate_record(rec: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    doi = str(rec.get("doi") or "")
    if not doi:
        errors.append("missing doi")
    elif not doi.startswith("10."):
        errors.append(f"invalid doi prefix: {doi}")
    if not str(rec.get("server") or ""):
        errors.append("missing server")
    if not str(rec.get("title") or "").strip():
        errors.append("missing title")
    try:
        if version_number(rec) < 1:
            errors.append("version must be >= 1")
    except Exception:
        errors.append("invalid version")
    return errors
