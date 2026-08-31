from __future__ import annotations
from .providers.base import SemanticProvider

ALLOWED_EXECUTION_MODES = {"LOCAL_ONLY", "CLOUD_MODEL", "HYBRID"}


def enforce_provider_network_policy(execution_mode: str, provider: SemanticProvider) -> None:
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        raise ValueError(f"unknown_execution_mode:{execution_mode}")
    network_required = bool(provider.capabilities().get("network_required", False))
    if execution_mode == "LOCAL_ONLY" and network_required:
        raise RuntimeError("network_provider_forbidden_in_local_only_mode")
