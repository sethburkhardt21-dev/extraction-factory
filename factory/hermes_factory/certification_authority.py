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
COLD_AUDIT_DIMENSION_SCHEMA = "hermes-cold-audit-dimensions-1.0"
SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)


def canonical_projection_sha256(projection: dict) -> str:
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cold_audit_dimension_authority_valid(entry: dict) -> bool:
    """Legacy/single-dimension cold certificates cannot satisfy runtime authority.

    v1.25 cold certification must prove every declared applicable runtime audit
    dimension was actually challenged and classified perfectly. The coverage
    object is canonically hashed so a registry edit cannot change its dimensions
    or accuracies without invalidating the certificate authority receipt.
    """
    decision_rule = str(entry.get("decision_rule") or "")
    if not decision_rule.startswith("CERT-COLD-AUDIT"):
        return True
    if entry.get("cold_audit_dimension_schema") != COLD_AUDIT_DIMENSION_SCHEMA:
        return False
    coverage = entry.get("cold_audit_dimension_coverage")
    expected_hash = str(entry.get("cold_audit_dimension_coverage_sha256") or "")
    if not isinstance(coverage, dict) or not SHA256_RE.fullmatch(expected_hash):
        return False
    if canonical_projection_sha256(coverage) != expected_hash.lower():
        return False
    if entry.get("cold_audit_all_required_dimensions_covered") is not True:
        return False
    if entry.get("cold_audit_all_required_dimensions_perfect") is not True:
        return False
    if coverage.get("all_required_dimensions_covered") is not True:
        return False
    required = coverage.get("required_dimensions")
    per_dimension = coverage.get("per_dimension")
    if not isinstance(required, list) or not required or not isinstance(per_dimension, dict):
        return False
    for dim in required:
        if not isinstance(dim, str) or not dim:
            return False
        row = per_dimension.get(dim)
        if not isinstance(row, dict):
            return False
        if int(row.get("challenge_count") or 0) < 1:
            return False
        if row.get("accuracy") != 1.0:
            return False
    return True


def certificate_projection_valid(entry: dict, scored_identity: dict) -> bool:
    if not _cold_audit_dimension_authority_valid(entry):
        return False
    projection = entry.get("registry_authority_projection")
    expected_hash = str(entry.get("registry_authority_sha256") or "")
    if not isinstance(projection, dict) or not SHA256_RE.fullmatch(expected_hash):
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
