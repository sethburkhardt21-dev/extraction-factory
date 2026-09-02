"""Canonical replay authority for semantic benchmark score reports.

The model registry contains both scoring-relevant identity authority and mutable
operational state such as applied certifications and role-status summaries. A
score report therefore keeps the whole-registry SHA as provenance telemetry but
must not use unrelated mutable registry bytes as its replay equality boundary.

Replay authority is the exact resolved model identity state actually consumed by
the scorer, including the candidate-observed model version. All non-telemetry
score fields remain exact-match requirements.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

AUTHORITY_SCHEMA = "hermes-scoring-authority-projection-1.0"
IDENTITY_AUTHORITY_FIELDS = (
    "provider",
    "model_alias",
    "underlying_family",
    "empirical_semantic_model",
    "independence_group",
    "observed_version_policy",
    "observed_version",
    "version_binding_certifiable",
)
REPLAY_TELEMETRY_FIELDS = {"registry_sha256"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def _project_identity(identity: Any, *, label: str, optional: bool = False) -> dict | None:
    if identity is None and optional:
        return None
    if not isinstance(identity, dict):
        raise ValueError(f"{label}_identity_missing_or_invalid")
    projected = {}
    for field in IDENTITY_AUTHORITY_FIELDS:
        if field not in identity:
            raise ValueError(f"{label}_authority_field_missing:{field}")
        projected[field] = identity[field]
    return projected


def scoring_authority_projection(score: dict) -> dict:
    if not isinstance(score, dict):
        raise ValueError("score_report_not_object")
    return {
        "schema_version": AUTHORITY_SCHEMA,
        "scored_identity": _project_identity(score.get("scored_identity"), label="scored"),
        "primary_baseline_identity": _project_identity(
            score.get("primary_baseline_identity"), label="primary_baseline", optional=True
        ),
    }


def canonical_projection_sha256(projection: dict) -> str:
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def scoring_authority_sha256(score: dict) -> str:
    return canonical_projection_sha256(scoring_authority_projection(score))


def _required_registry_sha(score: dict, *, label: str) -> str:
    value = str(score.get("registry_sha256") or "")
    if not SHA256_RE.fullmatch(value):
        raise ValueError(f"{label}_registry_sha256_missing_or_invalid")
    return value.lower()


def verify_replay_equivalence(stored: dict, recomputed: dict) -> dict:
    """Require exact score replay except for whole-registry SHA telemetry."""
    stored_registry_sha = _required_registry_sha(stored, label="stored")
    current_registry_sha = _required_registry_sha(recomputed, label="recomputed")

    stored_projection = scoring_authority_projection(stored)
    current_projection = scoring_authority_projection(recomputed)
    if stored_projection != current_projection:
        raise ValueError("score_registry_authority_projection_changed")

    left = dict(stored)
    right = dict(recomputed)
    for field in REPLAY_TELEMETRY_FIELDS:
        left.pop(field, None)
        right.pop(field, None)
    if left != right:
        changed = sorted(k for k in set(left) | set(right) if left.get(k) != right.get(k))
        raise ValueError(f"score_report_does_not_match_recomputation:{changed}")

    return {
        "replay_equivalent": True,
        "registry_sha256_at_score": stored_registry_sha,
        "registry_sha256_current": current_registry_sha,
        "registry_sha256_changed": stored_registry_sha != current_registry_sha,
        "registry_authority_projection": current_projection,
        "registry_authority_sha256": canonical_projection_sha256(current_projection),
    }
