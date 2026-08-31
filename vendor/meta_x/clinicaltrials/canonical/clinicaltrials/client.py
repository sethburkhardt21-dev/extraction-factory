"""ClinicalTrials.gov API v2 client with bounded retry and bulk snapshot support."""
from __future__ import annotations
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import logging
import os
import pathlib
import random
import time
import zipfile
from typing import Any, Dict, List, Optional, Callable

import requests

from canonical.config import API_BASE, API_BULK_DOWNLOAD, API_VERSION_ENDPOINT, DEFAULT_PAGE_SIZE
from canonical.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
TRANSIENT = {429, 500, 502, 503, 504}

@dataclass(frozen=True)
class FetchConfig:
    page_size: int = DEFAULT_PAGE_SIZE
    query: Optional[str] = None
    filters: Optional[Dict[str, str]] = None
    fields: Optional[List[str]] = None
    count_total: bool = True
    sort: Optional[str] = None

@dataclass(frozen=True)
class ApiVersionInfo:
    api_version: str
    data_timestamp: str
    raw: Dict[str, Any]

class ClinicalTrialsClient:
    def __init__(self, session: Optional[requests.Session] = None, rate_per_sec: float = 2.0,
                 max_retries: int = 5, sleeper=time.sleep,
                 raw_response_hook: Optional[Callable[[str, Dict[str, Any], bytes], None]] = None):
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "clinicaltrials-canonical/2.0"})
        self.rate_limiter = RateLimiter(rate_per_sec)
        self.max_retries = max_retries
        self.sleeper = sleeper
        self.raw_response_hook = raw_response_hook

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> Optional[float]:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                dt = parsedate_to_datetime(value)
                return max(0.0, dt.timestamp() - time.time())
            except Exception:
                return None

    def _request(self, url: str, *, params: Optional[Dict[str, Any]] = None,
                 timeout: int = 60, stream: bool = False) -> requests.Response:
        last_error: Optional[BaseException] = None
        for attempt in range(self.max_retries):
            self.rate_limiter.acquire()
            try:
                response = self.session.get(url, params=params or {}, timeout=timeout, stream=stream)
                if response.status_code in TRANSIENT:
                    if attempt == self.max_retries - 1:
                        response.raise_for_status()
                    retry_after = self._retry_after_seconds(response)
                    delay = retry_after if retry_after is not None else min(60.0, (2 ** attempt) + random.random())
                    logger.warning("Transient HTTP %s; retrying in %.2fs", response.status_code, delay)
                    self.sleeper(delay)
                    continue
                response.raise_for_status()  # fail closed on non-transient 4xx
                if self.raw_response_hook is not None and not stream:
                    safe_params=dict(params or {})
                    content=response.content if getattr(response,"content",None) is not None else response.text.encode("utf-8")
                    self.raw_response_hook(url,{"params":safe_params,"status_code":response.status_code,"content_type":response.headers.get("Content-Type")},content)
                return response
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    raise
                delay = min(60.0, (2 ** attempt) + random.random())
                logger.warning("Transient network error; retrying in %.2fs: %s", delay, exc)
                self.sleeper(delay)
        raise RuntimeError("request retries exhausted") from last_error

    def fetch_version(self) -> ApiVersionInfo:
        data = self._request(API_VERSION_ENDPOINT).json()
        return ApiVersionInfo(str(data.get("apiVersion", "unknown")), str(data.get("dataTimestamp", "")), data)

    def fetch_page(self, page_token: Optional[str] = None, config: Optional[FetchConfig] = None) -> Dict[str, Any]:
        cfg = config or FetchConfig()
        if not 1 <= cfg.page_size <= 1000:
            raise ValueError("page_size must be in [1, 1000]")
        params: Dict[str, Any] = {"pageSize": cfg.page_size, "countTotal": str(cfg.count_total).lower(), "format": "json"}
        if page_token:
            params["pageToken"] = page_token
        if cfg.query:
            params["query.term"] = cfg.query
        if cfg.filters:
            for key, value in cfg.filters.items():
                params[f"filter.{key}"] = value
        if cfg.fields:
            params["fields"] = ",".join(cfg.fields)
        if cfg.sort:
            params["sort"] = cfg.sort
        return self._request(API_BASE, params=params).json()

    def fetch_study_by_nct(self, nct_id: str) -> Dict[str, Any]:
        if not nct_id or not nct_id.upper().startswith("NCT"):
            raise ValueError("invalid NCT identifier")
        return self._request(f"{API_BASE}/{nct_id.upper()}", timeout=30).json()

    def download_bulk(self, output_path: pathlib.Path) -> pathlib.Path:
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix(output_path.suffix + ".part")
        response = self._request(API_BULK_DOWNLOAD, params={"format": "json.zip"}, timeout=600, stream=True)
        with tmp.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        if not zipfile.is_zipfile(tmp):
            tmp.unlink(missing_ok=True)
            raise ValueError("bulk endpoint did not return a valid ZIP archive")
        os.replace(tmp, output_path)
        return output_path
