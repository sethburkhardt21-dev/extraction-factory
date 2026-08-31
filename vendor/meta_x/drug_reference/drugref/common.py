from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path
from typing import Any, Dict, Iterable


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def atomic_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> int:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+".tmp"); n=0
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n"); n+=1
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,p); return n


def sha256_file(path: str | Path) -> str:
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def atomic_json(path: str | Path, obj: Dict[str, Any]) -> None:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        json.dump(obj,f,sort_keys=True,ensure_ascii=False,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,p)
