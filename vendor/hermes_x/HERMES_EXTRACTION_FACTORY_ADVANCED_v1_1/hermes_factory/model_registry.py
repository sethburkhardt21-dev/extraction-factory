from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

ALLOWED = {"UNBENCHMARKED", "BENCHMARKING", "CERTIFIED", "CERTIFIED_WITH_LIMITS", "REJECTED", "EXPIRED", "BLOCKED_EXTERNAL", "FIXTURE_NOT_EMPIRICAL"}


def load_registry(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def certification_key(provider: str, model_alias: str, role: str, work_class: str, source_class: str, benchmark_version: str) -> str:
    return "|".join([provider, model_alias, role, work_class, source_class, benchmark_version])


def get_status(registry: Dict[str, Any], key: str) -> str:
    value = registry.get("certifications", {}).get(key, {}).get("status", "UNBENCHMARKED")
    if value not in ALLOWED:
        raise ValueError(f"invalid_certification_status:{value}")
    return value


def is_certified(registry: Dict[str, Any], key: str) -> bool:
    return get_status(registry, key) in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}
