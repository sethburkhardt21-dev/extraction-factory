"""Canonical semantic digest for benchmark candidate evidence.

The candidate JSONL file contains ephemeral/controller fields such as candidate_id,
run lineage, row order, and metadata. Those bytes are useful provenance but are not
semantic freshness because the benchmark scorer does not use them to decide its
metrics. This module projects only score-relevant source/proposition/evidence and
authoritative worker identity, then hashes the sorted multiset.

Observed-version normalization intentionally mirrors score_role: a missing version
becomes UNOBSERVED. That value can be descriptively scored/digested but cannot earn
semantic certification because the separate model-version authority gate rejects it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

SEMANTIC_PROJECTION_SCHEMA = "hermes-candidate-semantic-projection-1.0"


def _worker_projection(row: dict) -> dict[str, str]:
    worker = row.get("worker_identity")
    if not isinstance(worker, dict):
        raise ValueError("candidate_semantic_worker_identity_missing")
    provider = str(worker.get("provider") or "").upper().strip()
    model = str(worker.get("model_alias") or "").strip()
    observed_version = str(worker.get("observed_version") or "UNOBSERVED").strip() or "UNOBSERVED"
    if not provider or not model:
        raise ValueError("candidate_semantic_worker_identity_incomplete")
    return {
        "provider": provider,
        "model_alias": model,
        "observed_version": observed_version,
    }


def candidate_semantic_projection(rows: Iterable[dict], *, units_in_scope: Iterable[str]) -> dict[str, Any]:
    scope = {str(x) for x in units_in_scope if str(x)}
    if not scope:
        raise ValueError("candidate_semantic_scope_empty")
    projected = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("candidate_semantic_row_not_object")
        unit_id = str(row.get("source_unit_id") or "")
        if unit_id not in scope:
            continue
        source_sha = str(row.get("source_sha256") or "").strip()
        evidence = row.get("evidence")
        proposition = row.get("proposition")
        if not source_sha or not isinstance(evidence, str) or not evidence or not isinstance(proposition, str) or not proposition.strip():
            raise ValueError("candidate_semantic_required_field_missing")
        projected.append({
            "source_unit_id": unit_id,
            "source_sha256": source_sha,
            "evidence": evidence,
            "proposition": proposition,
            "worker_identity": _worker_projection(row),
        })
    if not projected:
        raise ValueError("candidate_semantic_scope_has_no_candidates")
    projected.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return {
        "schema_version": SEMANTIC_PROJECTION_SCHEMA,
        "units_in_scope": sorted(scope),
        "candidate_count": len(projected),
        "candidates": projected,
    }


def candidate_semantic_sha256(rows: Iterable[dict], *, units_in_scope: Iterable[str]) -> str:
    projection = candidate_semantic_projection(rows, units_in_scope=units_in_scope)
    canonical = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def candidate_semantic_sha256_from_path(path: Path, *, units_in_scope: Iterable[str]) -> str:
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return candidate_semantic_sha256(rows, units_in_scope=units_in_scope)
