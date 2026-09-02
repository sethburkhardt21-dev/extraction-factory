"""Fail-closed runtime authority checks for COLD_AUDIT dimension coverage."""
from __future__ import annotations

import hashlib
import json
import re

COVERAGE_SCHEMA = "hermes-cold-audit-dimension-coverage-1.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.I)


def coverage_sha256(coverage: dict) -> str:
    payload = json.dumps(coverage, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cold_audit_dimension_coverage_valid(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("cold_audit_dimension_coverage_schema") != COVERAGE_SCHEMA:
        return False
    coverage = entry.get("cold_audit_dimension_coverage")
    expected_sha = str(entry.get("cold_audit_dimension_coverage_sha256") or "")
    if not isinstance(coverage, dict) or not SHA256_RE.fullmatch(expected_sha):
        return False
    if coverage_sha256(coverage) != expected_sha.lower():
        return False
    if coverage.get("all_required_dimensions_covered") is not True:
        return False
    if coverage.get("missing_required_dimensions") not in ([], tuple()):
        return False
    required = coverage.get("required_dimensions")
    per_dimension = coverage.get("per_dimension")
    if not isinstance(required, list) or not required or any(not isinstance(x, str) or not x for x in required):
        return False
    if len(set(required)) != len(required) or not isinstance(per_dimension, dict):
        return False
    for dimension in required:
        node = per_dimension.get(dimension)
        if not isinstance(node, dict):
            return False
        if not isinstance(node.get("challenge_count"), int) or node["challenge_count"] < 1:
            return False
        if node.get("correct_count") != node.get("challenge_count"):
            return False
        if node.get("accuracy") != 1.0:
            return False
    semantic_sha = str(entry.get("candidate_semantic_sha256") or "")
    if not SHA256_RE.fullmatch(semantic_sha):
        return False
    return True
