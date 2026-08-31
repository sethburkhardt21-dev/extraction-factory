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


def identity_key(provider: str, model_alias: str) -> str:
    return "|".join([str(provider).upper(), str(model_alias)])


def resolve_model_identity(registry: Dict[str, Any], provider: str, model_alias: str) -> Dict[str, Any]:
    key = identity_key(provider, model_alias)
    row = registry.get("model_identities", {}).get(key)
    if not isinstance(row, dict):
        raise KeyError(f"unregistered_model_identity:{key}")
    family = str(row.get("underlying_family") or "").strip()
    if not family:
        raise ValueError(f"registered_model_missing_family:{key}")
    return {
        "provider": str(provider).upper(),
        "model_alias": model_alias,
        "underlying_family": family,
        "empirical_semantic_model": bool(row.get("empirical_semantic_model", True)),
        "independence_group": str(row.get("independence_group") or family),
        "observed_version_policy": str(row.get("observed_version_policy") or "CLI_OBSERVED"),
    }
