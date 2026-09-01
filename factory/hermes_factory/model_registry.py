from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

ALLOWED = {"UNBENCHMARKED", "BENCHMARKING", "CERTIFIED", "CERTIFIED_WITH_LIMITS", "REJECTED", "EXPIRED", "BLOCKED_EXTERNAL", "FIXTURE_NOT_EMPIRICAL"}
CERTIFIED_STATUSES = {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}
VERSION_PLACEHOLDERS = {"", "UNKNOWN", "UNCONFIGURED", "CLI_OBSERVED", "UNOBSERVED"}
OLLAMA_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)


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
    return get_status(registry, key) in CERTIFIED_STATUSES


def certification_entry(registry: Dict[str, Any], key: str) -> Dict[str, Any] | None:
    certs = registry.get("certifications")
    if certs is None:
        return None
    if not isinstance(certs, dict):
        raise ValueError("registry_certifications_not_object")
    entry = certs.get(key)
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise ValueError(f"certification_entry_not_object:{key}")
    return entry


def observed_version_is_certifiable(policy: str, observed_version: str) -> bool:
    """Return True only for a version identifier strong enough to replay certification.

    Ollama roles must bind to the immutable local model digest. Hosted aliases that
    can silently retarget are explicitly non-certifiable until an immutable version
    identifier is supplied by a provider-specific integration. Generic
    `CLI_OBSERVED` is intentionally never certification authority.
    """
    policy = str(policy or "").strip().upper()
    version = str(observed_version or "").strip()
    if version.upper() in VERSION_PLACEHOLDERS or version.upper().startswith("UNPINNED_ALIAS:"):
        return False
    if policy == "OLLAMA_DIGEST":
        return bool(OLLAMA_DIGEST_RE.fullmatch(version))
    if policy in {"UNPINNED_HOSTED_ALIAS", "CLI_OBSERVED"}:
        return False
    if policy == "EXPLICIT_IMMUTABLE_VERSION":
        return bool(version)
    if policy == "DETERMINISTIC_FIXTURE":
        return bool(version)
    return False


def is_certified_for_source(
    registry: Dict[str, Any],
    key: str,
    *,
    source_units_sha256: str,
    source_unit_id: str,
    provider: str,
    model_alias: str,
    observed_version: str,
) -> bool:
    """Require role certification to match exact source scope and model version.

    The historical certification key contains work/source *classes* (e.g. W2/S1),
    not source identity or model bytes. Runtime therefore additionally binds the
    certification to the exact source-units artifact, unit scope, scored provider,
    model alias, and certifiable observed model version recorded by benchmark
    scoring. This prevents either source-scope expansion or changed model weights
    from inheriting a prior certificate.
    """
    entry = certification_entry(registry, key)
    if entry is None:
        return False
    status = entry.get("status", "UNBENCHMARKED")
    if status not in ALLOWED:
        raise ValueError(f"invalid_certification_status:{status}")
    if status not in CERTIFIED_STATUSES:
        return False
    if entry.get("benchmark_inputs_verified") is not True:
        return False

    expected_source_hash = str(entry.get("source_units_sha256") or "")
    if not expected_source_hash or expected_source_hash != str(source_units_sha256):
        return False

    units = entry.get("units_in_scope")
    if not isinstance(units, list) or not units or source_unit_id not in units:
        return False

    scored_identity = entry.get("scored_identity")
    if not isinstance(scored_identity, dict):
        return False
    scored_provider = str(scored_identity.get("provider") or "").upper()
    scored_model = str(scored_identity.get("model_alias") or scored_identity.get("model") or "")
    if scored_provider != str(provider).upper() or scored_model != str(model_alias):
        return False

    certified_version = str(scored_identity.get("observed_version") or "").strip()
    version_policy = str(scored_identity.get("observed_version_policy") or "").strip()
    if not observed_version_is_certifiable(version_policy, certified_version):
        return False
    if certified_version != str(observed_version or "").strip():
        return False

    # Applied benchmark certifications must retain their source/gold evidence chain.
    for required in ("gold_reference_sha256", "gold_manifest_sha256", "candidate_file_sha256"):
        value = entry.get(required)
        if not isinstance(value, str) or len(value) != 64:
            return False
    return True


def identity_key(provider: str, model_alias: str) -> str:
    return "|".join([str(provider).upper(), str(model_alias)])


def resolve_model_identity(registry: Dict[str, Any], provider: str, model_alias: str) -> Dict[str, Any]:
    """Resolve one protected model identity with no permissive identity defaults."""
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
