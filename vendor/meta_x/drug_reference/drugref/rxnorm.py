"""RxNorm resolver backed by the official RxNav REST API or real prefetched JSONL."""
from __future__ import annotations
import json, random, time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional
import requests
from .common import normalize_name, stable_hash

BASE="https://rxnav.nlm.nih.gov/REST"
TRANSIENT={429,500,502,503,504}
class RxNormClient:
    def __init__(self, base_url: str=BASE, timeout: int=30, retries: int=4, session=None):
        self.base_url=base_url.rstrip("/"); self.timeout=timeout; self.retries=retries; self.session=session or requests.Session()
    def resolve_name(self,name: str) -> Dict[str, Any]:
        if not name.strip(): raise ValueError("drug name is empty")
        url=f"{self.base_url}/rxcui.json"
        last=None
        for attempt in range(self.retries):
            try:
                r=self.session.get(url,params={"name":name,"search":"2"},headers={"Accept":"application/json"},timeout=self.timeout)
                if r.status_code in TRANSIENT:
                    if attempt==self.retries-1: r.raise_for_status()
                    retry_after=r.headers.get("Retry-After")
                    delay=None
                    if retry_after:
                        try: delay=max(0.0,float(retry_after))
                        except ValueError:
                            try:
                                dt=parsedate_to_datetime(retry_after)
                                if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                                delay=max(0.0,(dt-datetime.now(timezone.utc)).total_seconds())
                            except Exception: delay=None
                    time.sleep(delay if delay is not None else min(15,2**attempt+random.random()/2)); continue
                r.raise_for_status(); data=r.json(); ids=((data.get("idGroup") or {}).get("rxnormId") or [])
                ids=[str(x) for x in ids if str(x).isdigit()]
                return {"name":name,"name_normalized":normalize_name(name),"rxcuis":ids,"rxcui":ids[0] if len(ids)==1 else None,
                        "resolution_status":"unique" if len(ids)==1 else ("none" if not ids else "ambiguous"),
                        "source":"rxnorm_api","source_payload":data,"source_record_sha256":stable_hash(data),
                        "retrieved_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
                        "source_url":url}
            except (requests.Timeout,requests.ConnectionError) as exc:
                last=exc
                if attempt==self.retries-1: raise
                time.sleep(min(15,2**attempt+random.random()/2))
        if last: raise last
        raise RuntimeError("RxNorm retry loop exited")

def read_prefetched(path: str) -> Iterator[Dict[str, Any]]:
    with Path(path).open("r",encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            obj=json.loads(line)
            if not isinstance(obj,dict): raise ValueError("RxNorm JSONL row must be object")
            if not str(obj.get("name") or "").strip(): raise ValueError("RxNorm row requires name")
            ids=obj.get("rxcuis") or ([obj["rxcui"]] if obj.get("rxcui") else [])
            ids=[str(x) for x in ids]
            if not ids or not all(x.isdigit() for x in ids):
                raise ValueError("RxNorm row requires real numeric rxcui/rxcuis")
            obj["rxcuis"]=ids
            obj["rxcui"]=ids[0] if len(ids)==1 else None
            obj["resolution_status"]="unique" if len(ids)==1 else "ambiguous"
            obj["source"]="rxnorm_prefetched"
            source_payload=obj.get("source_payload")
            if source_payload is not None:
                obj["source_record_sha256"]=stable_hash(source_payload)
            elif not obj.get("source_record_sha256"):
                # Development compatibility only. Production validation in pipeline.py
                # requires source_payload so the exact RxNav response is retained.
                payload={k:v for k,v in obj.items() if k!="source_record_sha256"}
                obj["source_record_sha256"]=stable_hash(payload)
            yield obj
