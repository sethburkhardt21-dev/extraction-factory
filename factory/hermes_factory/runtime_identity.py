from __future__ import annotations

from typing import Any, Dict

from .model_registry import resolve_model_identity
from .providers.base import SemanticProvider


def resolve_registered_provider_identity(
    registry: Dict[str, Any],
    provider: SemanticProvider,
    label: str,
    *,
    require_empirical: bool = True,
) -> Dict[str, Any]:
    """Resolve one runtime provider through the protected model registry.

    Runtime provider self-claims are not authority. Provider/model identity,
    underlying family, empirical status, and independence group must agree with
    the protected registry before a real semantic call is allowed.
    """
    observed = provider.identity()
    try:
        resolved = resolve_model_identity(registry, observed.provider, observed.model_alias)
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"{label}_registry_identity_invalid:{observed.provider}|{observed.model_alias}:{exc}"
        ) from exc

    declared_family = str(observed.underlying_family or "").strip()
    registry_family = str(resolved.get("underlying_family") or "").strip()
    if declared_family not in ("", "UNCONFIGURED", registry_family):
        raise ValueError(
            f"{label}_underlying_family_mismatch:{declared_family}!={registry_family}"
        )

    provider_empirical = bool(provider.is_empirical_semantic_provider())
    registry_empirical = bool(resolved.get("empirical_semantic_model"))
    if provider_empirical != registry_empirical:
        raise ValueError(
            f"{label}_empirical_status_mismatch:provider={provider_empirical}:registry={registry_empirical}"
        )
    if require_empirical and not registry_empirical:
        raise ValueError(f"{label}_model_not_empirical:{observed.provider}|{observed.model_alias}")

    group = str(resolved.get("independence_group") or "").strip()
    if not group or group == "UNCONFIGURED":
        raise ValueError(f"{label}_independence_group_missing")
    return resolved


def resolve_runtime_topology(
    registry: Dict[str, Any],
    primary_provider: SemanticProvider,
    blind_provider: SemanticProvider,
    cold_audit_provider: SemanticProvider | None = None,
    *,
    require_empirical: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Resolve and validate runtime model independence before inference.

    PRIMARY and BLIND_RECALL must be from distinct protected independence groups.
    A configured COLD_AUDIT model must be distinct from both. This intentionally
    uses `independence_group`, not `underlying_family`: related fine-tunes may use
    different family labels while still sharing the same benchmark-independence
    group.
    """
    resolved = {
        "PRIMARY": resolve_registered_provider_identity(
            registry, primary_provider, "PRIMARY", require_empirical=require_empirical
        ),
        "BLIND_RECALL": resolve_registered_provider_identity(
            registry, blind_provider, "BLIND_RECALL", require_empirical=require_empirical
        ),
    }
    if cold_audit_provider is not None:
        resolved["COLD_AUDIT"] = resolve_registered_provider_identity(
            registry, cold_audit_provider, "COLD_AUDIT", require_empirical=require_empirical
        )

    primary_group = str(resolved["PRIMARY"]["independence_group"])
    blind_group = str(resolved["BLIND_RECALL"]["independence_group"])
    if primary_group == blind_group:
        raise ValueError(
            f"primary_blind_independence_group_collision:{primary_group}"
        )

    if "COLD_AUDIT" in resolved:
        cold_group = str(resolved["COLD_AUDIT"]["independence_group"])
        if cold_group in {primary_group, blind_group}:
            raise ValueError(
                f"cold_audit_independence_group_collision:{cold_group}"
            )
    return resolved
