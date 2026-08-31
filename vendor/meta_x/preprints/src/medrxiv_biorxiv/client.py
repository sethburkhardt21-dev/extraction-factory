"""Resilient medRxiv/bioRxiv details API client.

Important: the two official API hosts currently document different response page
sizes (30 vs 100). Pagination therefore never uses a hard-coded page size as an
end-of-data signal. The cursor advances by the number of records actually
returned and extraction ends only on an empty collection (or a trustworthy
reported total).
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, Optional

import requests
from dateutil.parser import isoparse

API_BASE = "https://api.biorxiv.org"
TRANSIENT = {429, 500, 502, 503, 504}

@dataclass(frozen=True)
class FetchConfig:
    server: str
    start_date: str
    end_date: str
    contact_email: str = ""
    rate_limit_sec: float = 1.0
    max_retries: int = 5
    timeout: int = 30
    api_base: str = API_BASE


def parse_interval(start: str, end: str) -> str:
    s = isoparse(start).date()
    e = isoparse(end).date()
    if e < s:
        raise ValueError("end before start")
    return f"{s.isoformat()}/{e.isoformat()}"


def build_url(server: str, interval: str, cursor: int = 0, api_base: str = API_BASE) -> str:
    server = server.lower().strip()
    if server not in {"biorxiv", "medrxiv"}:
        raise ValueError(f"server must be biorxiv or medrxiv, got {server!r}")
    if cursor < 0:
        raise ValueError("cursor must be >= 0")
    return f"{api_base.rstrip('/')}/details/{server}/{interval}/{cursor}"


def normalize_record(raw: Dict[str, Any], server_hint: str = "") -> Dict[str, Any]:
    doi = str(raw.get("doi") or "").strip().lower()
    version = str(raw.get("version") or "1").strip()
    source_hash = hashlib.sha256(
        json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "doi": doi,
        "server": str(raw.get("server") or server_hint).lower(),
        "title": str(raw.get("title") or "").strip(),
        "authors": raw.get("authors") or "",
        "author_corresponding": raw.get("author_corresponding") or "",
        "author_corresponding_institution": raw.get("author_corresponding_institution") or "",
        "category": raw.get("category") or "",
        "date": raw.get("date") or "",
        "version": version,
        "type": raw.get("type") or "",
        "license": raw.get("license") or "",
        "abstract": raw.get("abstract") or "",
        "funding": raw.get("funding") or [],
        "published": raw.get("published") or "",
        "jatsxml": raw.get("jatsxml") or "",
        "biorxiv_doi": raw.get("biorxiv_doi") or "",
        "medrxiv_doi": raw.get("medrxiv_doi") or "",
        "source_record_sha256": source_hash,
        "source_payload": raw,
    }


def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _request_json(session: requests.Session, url: str, headers: Dict[str, str], cfg: FetchConfig, raw_response_hook: Optional[Callable[[str, Dict[str, Any], bytes], None]] = None) -> Dict[str, Any]:
    last_exc: Optional[BaseException] = None
    for attempt in range(cfg.max_retries):
        try:
            resp = session.get(url, headers=headers, timeout=cfg.timeout)
            if resp.status_code in TRANSIENT:
                if attempt == cfg.max_retries - 1:
                    resp.raise_for_status()
                delay = _retry_after_seconds(resp.headers.get("Retry-After"))
                if delay is None:
                    delay = min(30.0, (2 ** attempt) + random.uniform(0.0, 0.5))
                time.sleep(delay)
                continue
            resp.raise_for_status()  # fail closed on non-transient 4xx
            content = getattr(resp, "content", None)
            if content is None:
                data = resp.json()
                content = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            else:
                data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("API response must be a JSON object")
            if raw_response_hook is not None:
                raw_response_hook(url, {
                    "status_code": resp.status_code,
                    "content_type": resp.headers.get("Content-Type"),
                }, bytes(content))
            return data
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt == cfg.max_retries - 1:
                raise
            time.sleep(min(30.0, (2 ** attempt) + random.uniform(0.0, 0.5)))
    if last_exc:
        raise last_exc
    raise RuntimeError("request retry loop exited without response")


def _reported_total(data: Dict[str, Any]) -> Optional[int]:
    """Best-effort total extraction; not required for correctness.

    The official API exposes paging metadata in `messages`, but the exact key
    names have varied. Only unambiguously numeric total-like keys are accepted.
    """
    messages = data.get("messages") or []
    if isinstance(messages, list) and messages:
        msg = messages[0] if isinstance(messages[0], dict) else {}
        for key in ("total", "total_count", "totalCount"):
            value = msg.get(key)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                pass
    return None


def fetch_interval(config: FetchConfig, session: Optional[requests.Session] = None, metadata: Optional[Dict[str, Any]] = None, raw_response_hook: Optional[Callable[[str, Dict[str, Any], bytes], None]] = None) -> Iterator[Dict[str, Any]]:
    interval = parse_interval(config.start_date, config.end_date)
    cursor = 0
    own_session = session is None
    session = session or requests.Session()
    headers = {
        "Accept": "application/json",
        "User-Agent": f"meta-extraction-repaired/1.0 (contact: {config.contact_email or 'unspecified'})",
    }
    metadata = metadata if metadata is not None else {}
    metadata.setdefault("pages", 0)
    metadata.setdefault("observed_records", 0)
    metadata.setdefault("reported_total", None)
    metadata.setdefault("eof_observed", False)
    metadata["interval"] = interval
    metadata["server"] = config.server
    try:
        while True:
            url = build_url(config.server, interval, cursor, config.api_base)
            data = _request_json(session, url, headers, config, raw_response_hook=raw_response_hook)
            metadata["pages"] += 1
            reported = _reported_total(data)
            if reported is not None:
                if metadata["reported_total"] is None:
                    metadata["reported_total"] = reported
                elif metadata["reported_total"] != reported:
                    metadata.setdefault("warnings", []).append(
                        f"reported total changed during pagination: {metadata['reported_total']} -> {reported}"
                    )
                    metadata["reported_total"] = reported
            collection = data.get("collection") or []
            if not isinstance(collection, list):
                raise ValueError("API `collection` must be a list")
            if not collection:
                metadata["eof_observed"] = True
                break

            for raw in collection:
                if not isinstance(raw, dict):
                    raise ValueError("API collection item must be an object")
                metadata["observed_records"] += 1
                yield normalize_record(raw, server_hint=config.server)

            previous = cursor
            cursor += len(collection)
            if cursor <= previous:
                raise RuntimeError("pagination cursor made no progress")

            # Do not use a reported total as an EOF signal. The two official
            # hosts have historically differed in paging behavior, and a stale
            # or drifting total must never silently truncate extraction. The
            # empty collection is the authoritative end-of-stream condition.
            if config.rate_limit_sec > 0:
                time.sleep(config.rate_limit_sec)
    finally:
        if own_session:
            session.close()
