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
    """Resolve one protected model identity with no permissive defaults.

    The registry is an authority boundary. Missing empirical status or missing
    independence group must fail closed rather than silently treating an
    incomplete row as an empirical/independent model.
    """
    key = identity_key(provider, model_alias)
    identities = registry.get("model_identities")
    if not isinstance(identities, dict):
        raise ValueError("registry_model_identities_not_object")
    row = identities.get(key)
    if not isinstance(row, dict):
        raise KeyError(f"unregistered_model_identity:{key}")

    family_raw = row.get("underlying_family")
    if not isinstance(family_raw, str) or not family_raw.strip():
        raise ValueError(f"registered_model_missing_family:{key}")
    family = family_raw.strip()

    if "empirical_semantic_model" not in row:
        raise ValueError(f"registered_model_missing_empirical_status:{key}")
    empirical = row.get("empirical_semantic_model")
    if type(empirical) is not bool:
        raise ValueError(f"registered_model_empirical_status_not_boolean:{key}")

    group_raw = row.get("independence_group")
    if not isinstance(group_raw, str) or not group_raw.strip():
        raise ValueError(f"registered_model_missing_independence_group:{key}")
    independence_group = group_raw.strip()

    policy_raw = row.get("observed_version_policy", "CLI_OBSERVED")
    if not isinstance(policy_raw, str) or not policy_raw.strip():
        raise ValueError(f"registered_model_observed_version_policy_invalid:{key}")

    return {
        "provider": str(provider).upper(),
        "model_alias": model_alias,
        "underlying_family": family,
        "empirical_semantic_model": empirical,
        "independence_group": independence_group,
        "observed_version_policy": policy_raw.strip(),
    }
