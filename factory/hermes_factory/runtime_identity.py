from __future__ import annotations

from typing import Any, Dict

from .model_registry import resolve_model_identity
from .providers.base import SemanticProvider


def resolve_registered_provider_identity(
    registry: Dict[str, Any],
    provider: SemanticProvider,
    label: str,
    *,
    require_empirical: bool = False,
) -> Dict[str, Any]:
    """Resolve one runtime provider through the protected model registry.

    Runtime provider self-claims are not authority. Provider/model identity,
    underlying family, empirical status, and independence group must agree with
    the protected registry before dispatch. Non-empirical fixtures may be
    resolved for mechanical validation, but cannot satisfy semantic readiness.
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
    """Resolve and validate runtime model topology before inference.

    `require_empirical=True` protects real semantic execution, but deliberately
    preserves one mechanical-validation exception: PRIMARY and BLIND_RECALL may
    both be registered non-empirical fixtures. Such runs remain unable to satisfy
    semantic readiness elsewhere in the factory.

    Rules:
    - every configured provider must match protected registry identity metadata;
    - PRIMARY and BLIND_RECALL must either both be non-empirical fixtures or both
      be empirical semantic providers; mixed producer pairs fail closed;
    - empirical PRIMARY and BLIND_RECALL must use distinct protected
      `independence_group` values;
    - an empirical COLD_AUDIT provider must be group-distinct from empirical
      PRIMARY and BLIND_RECALL;
    - a non-empirical cold fixture may accompany an all-fixture mechanical run but
      never upgrades semantic readiness.

    This intentionally uses `independence_group`, not `underlying_family`: related
    fine-tunes may use different family labels while sharing one independence group.
    """
    # Resolve identity truth first without prematurely rejecting fixture transports.
    resolved = {
        "PRIMARY": resolve_registered_provider_identity(
            registry, primary_provider, "PRIMARY", require_empirical=False
        ),
        "BLIND_RECALL": resolve_registered_provider_identity(
            registry, blind_provider, "BLIND_RECALL", require_empirical=False
        ),
    }
    if cold_audit_provider is not None:
        resolved["COLD_AUDIT"] = resolve_registered_provider_identity(
            registry, cold_audit_provider, "COLD_AUDIT", require_empirical=False
        )

    primary_empirical = bool(resolved["PRIMARY"]["empirical_semantic_model"])
    blind_empirical = bool(resolved["BLIND_RECALL"]["empirical_semantic_model"])
    if primary_empirical != blind_empirical:
        raise ValueError(
            "primary_blind_empirical_status_mixed:"
            f"PRIMARY={primary_empirical}:BLIND_RECALL={blind_empirical}"
        )

    # `require_empirical` means a semantic pair cannot degrade to one fixture.
    # An all-fixture pair is retained solely for deterministic bridge/E2E testing.
    all_fixture_producers = not primary_empirical and not blind_empirical
    if require_empirical and not all_fixture_producers and not (primary_empirical and blind_empirical):
        raise ValueError("primary_blind_empirical_pair_required")

    primary_group = str(resolved["PRIMARY"]["independence_group"])
    blind_group = str(resolved["BLIND_RECALL"]["independence_group"])
    if primary_empirical and primary_group == blind_group:
        raise ValueError(
            f"primary_blind_independence_group_collision:{primary_group}"
        )

    if "COLD_AUDIT" in resolved:
        cold_empirical = bool(resolved["COLD_AUDIT"]["empirical_semantic_model"])
        cold_group = str(resolved["COLD_AUDIT"]["independence_group"])
        if cold_empirical and all_fixture_producers:
            raise ValueError("empirical_cold_audit_with_nonempirical_producers")
        if primary_empirical and cold_empirical and cold_group in {primary_group, blind_group}:
            raise ValueError(
                f"cold_audit_independence_group_collision:{cold_group}"
            )
    return resolved
