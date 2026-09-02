"""Compatibility entrypoint for the canonical dimension-aware COLD_AUDIT certifier."""
from __future__ import annotations

import sys

from benchmarks_ext.cold_audit_certifier import (
    BENCHMARK_VERSION,
    COVERAGE_SCHEMA,
    LIMITS,
    REPORT_SCHEMA,
    _build_provider,
    _results_sha256,
    build_challenges,
    build_entries,
    build_request,
    challenge_semantic_projection,
    challenge_semantic_sha256,
    coverage_sha256,
    decide,
    main,
    run_challenges,
    score_results,
    validate_gold_construction_disjointness,
)

__all__ = [
    "BENCHMARK_VERSION",
    "COVERAGE_SCHEMA",
    "LIMITS",
    "REPORT_SCHEMA",
    "_build_provider",
    "_results_sha256",
    "build_challenges",
    "build_entries",
    "build_request",
    "challenge_semantic_projection",
    "challenge_semantic_sha256",
    "coverage_sha256",
    "decide",
    "main",
    "run_challenges",
    "score_results",
    "validate_gold_construction_disjointness",
]

if __name__ == "__main__":
    sys.exit(main())
