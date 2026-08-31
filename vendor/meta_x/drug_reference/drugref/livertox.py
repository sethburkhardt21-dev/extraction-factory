"""LiverTox structured-record ingestion.

No medical attributes are invented. Production input must be a real locally
captured record with source provenance. This module intentionally does not turn
a drug-name list into guessed likelihood categories or injury patterns.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterator
from .common import stable_hash

ALLOWED={"A","B","C","D","E","A*","B*","C*","D*","E*"}
def read_prefetched(path: str) -> Iterator[Dict[str, Any]]:
    with Path(path).open("r",encoding="utf-8") as f:
        for line_no,line in enumerate(f,1):
            if not line.strip(): continue
            obj=json.loads(line)
            if not isinstance(obj,dict): raise ValueError(f"LiverTox line {line_no}: object required")
            if not obj.get("name"): raise ValueError(f"LiverTox line {line_no}: missing name")
            if not obj.get("source_url") and not obj.get("source_nbk_id"):
                raise ValueError(f"LiverTox line {line_no}: source_url or source_nbk_id required")
            likelihood=obj.get("livertox_likelihood")
            if likelihood is not None and likelihood not in ALLOWED:
                raise ValueError(f"LiverTox line {line_no}: invalid likelihood {likelihood!r}")
            obj["source"]="livertox_prefetched"
            if obj.get("source_payload") is not None:
                obj["source_record_sha256"]=stable_hash(obj["source_payload"])
            elif obj.get("source_text") is not None:
                obj["source_record_sha256"]=stable_hash(obj["source_text"])
            elif not obj.get("source_record_sha256"):
                # Development compatibility only. Production validation requires
                # a retained source payload/text or an independently pinned snapshot.
                payload={k:v for k,v in obj.items() if k!="source_record_sha256"}
                obj["source_record_sha256"]=stable_hash(payload)
            yield obj
