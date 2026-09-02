"""Runtime checks for applied semantic-certification identity authority."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

MODEL_IDENTITY_AUTHORITY_FIELDS = (
    "underlying_family",
    "empirical_semantic_model",
    "independence_group",
    "observed_version_policy",
)
CERTIFICATE_IDENTITY_PROJECTION_FIELDS = (
    "provider",
    "model_alias",
    *MODEL_IDENTITY_AUTHORITY_FIELDS,
    "observed_version",
    "version_binding_certifiable",
)


def canonical_projection_sha256(projection: dict) -> str:
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def certificate_projection_valid(entry: dict, scored_identity: dict) -> bool:
    projection = entry.get("registry_authority_projection")
    expected_hash = str(entry.get("registry_authority_sha256") or "")
    if not isinstance(projection, dict) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash, re.IGNORECASE):
        return False
    if canonical_projection_sha256(projection) != expected_hash.lower():
        return False
    projected_scored = projection.get("scored_identity")
    if not isinstance(projected_scored, dict):
        return False
    return all(projected_scored.get(field) == scored_identity.get(field) for field in CERTIFICATE_IDENTITY_PROJECTION_FIELDS)


def current_registry_identity_matches_certificate(
    registry: dict,
    scored_identity: dict,
    provider: str,
    model_alias: str,
    resolver: Callable[[dict, str, str], dict],
) -> bool:
    try:
        current = resolver(registry, provider, model_alias)
    except (KeyError, ValueError):
        return False
    return all(current.get(field) == scored_identity.get(field) for field in MODEL_IDENTITY_AUTHORITY_FIELDS)
