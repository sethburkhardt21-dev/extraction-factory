from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks_ext.certify_roles import build_entry, recompute_and_verify_score
from benchmarks_ext.replay_authority import (
    canonical_projection_sha256,
    scoring_authority_projection,
    verify_replay_equivalence,
)


IDENTITY = {
    "provider": "OLLAMA",
    "model_alias": "primary",
    "underlying_family": "DEEPSEEK",
    "empirical_semantic_model": True,
    "independence_group": "DEEPSEEK",
    "observed_version_policy": "OLLAMA_DIGEST",
    "observed_version": "sha256:" + "1" * 64,
    "version_binding_certifiable": True,
}
BASELINE = {
    "provider": "OLLAMA",
    "model_alias": "baseline",
    "underlying_family": "QWEN_NUEXTRACT",
    "empirical_semantic_model": True,
    "independence_group": "QWEN",
    "observed_version_policy": "OLLAMA_DIGEST",
    "observed_version": "sha256:" + "2" * 64,
    "version_binding_certifiable": True,
}


def _score(registry_sha: str = "a" * 64, *, baseline=False) -> dict:
    return {
        "score_schema_version": "hermes-role-score-1.2",
        "role": "BLIND_RECALL" if baseline else "PRIMARY",
        "model": "primary",
        "scored_identity": copy.deepcopy(IDENTITY),
        "primary_baseline_identity": copy.deepcopy(BASELINE) if baseline else None,
        "gold_construction_independence_groups": ["A", "B", "C"],
        "benchmark_version": "MACHINES_P0299_P0301_SOURCE_FIRST_v1",
        "gold_label": "MECHANICALLY_CHECKED",
        "reference_sha256": "b" * 64,
        "source_units_sha256": "c" * 64,
        "candidate_file_sha256": "d" * 64,
        "primary_candidate_file_sha256": "e" * 64 if baseline else None,
        "gold_manifest_sha256": "f" * 64,
        "registry_sha256": registry_sha,
        "units_in_scope": ["U1", "U2"],
        "benchmark_inputs_verified": True,
        "input_paths": {
            "candidates": "/tmp/candidates.jsonl",
            "primary_candidates": "/tmp/primary.jsonl" if baseline else None,
            "reference": "/tmp/reference.jsonl",
            "gold_manifest": "/tmp/manifest.json",
            "source_units": "/tmp/source.jsonl",
            "registry": "/tmp/registry.json",
        },
        "metrics": {
            "semantic_unit_recall": {"numerator": 2, "denominator": 2, "value": 1.0},
            "semantic_unit_precision": {"numerator": 2, "denominator": 2, "value": 1.0},
        },
    }


class ReplayAuthorityTests(unittest.TestCase):
    def test_whole_registry_sha_only_change_is_replay_equivalent(self):
        stored = _score("a" * 64)
        recomputed = _score("9" * 64)
        receipt = verify_replay_equivalence(stored, recomputed)
        self.assertTrue(receipt["replay_equivalent"])
        self.assertTrue(receipt["registry_sha256_changed"])
        self.assertEqual(
            receipt["registry_authority_sha256"],
            canonical_projection_sha256(scoring_authority_projection(stored)),
        )

    def test_scored_identity_authority_drift_fails(self):
        stored = _score()
        recomputed = _score("9" * 64)
        recomputed["scored_identity"]["independence_group"] = "CHANGED"
        with self.assertRaisesRegex(ValueError, "score_registry_authority_projection_changed"):
            verify_replay_equivalence(stored, recomputed)

    def test_primary_baseline_authority_drift_fails(self):
        stored = _score(baseline=True)
        recomputed = _score("9" * 64, baseline=True)
        recomputed["primary_baseline_identity"]["observed_version_policy"] = "EXPLICIT_IMMUTABLE_VERSION"
        with self.assertRaisesRegex(ValueError, "score_registry_authority_projection_changed"):
            verify_replay_equivalence(stored, recomputed)

    def test_non_registry_score_change_still_fails_exact_replay(self):
        stored = _score()
        recomputed = _score("9" * 64)
        recomputed["metrics"]["semantic_unit_precision"]["value"] = 0.5
        with self.assertRaisesRegex(ValueError, "score_report_does_not_match_recomputation"):
            verify_replay_equivalence(stored, recomputed)

    def test_missing_authority_field_fails_closed(self):
        stored = _score(); stored["scored_identity"].pop("empirical_semantic_model")
        with self.assertRaisesRegex(ValueError, "authority_field_missing"):
            verify_replay_equivalence(stored, _score())


class CertifierReplayIntegrationTests(unittest.TestCase):
    def test_recompute_accepts_registry_mutation_when_authority_is_unchanged(self):
        stored = _score("a" * 64)
        recomputed = _score("9" * 64)
        with tempfile.TemporaryDirectory() as td:
            score_path = Path(td) / "score.json"
            score_path.write_text(json.dumps(stored), encoding="utf-8")
            with patch("benchmarks_ext.certify_roles.build_score_report", return_value=recomputed):
                result, receipt = recompute_and_verify_score(
                    score_path=score_path,
                    candidates_path=Path(td) / "candidates.jsonl",
                    reference_path=Path(td) / "reference.jsonl",
                    gold_manifest_path=Path(td) / "manifest.json",
                    source_units_path=Path(td) / "source.jsonl",
                    registry_path=Path(td) / "registry.json",
                    role="PRIMARY",
                )
        self.assertEqual(result["registry_sha256"], "9" * 64)
        self.assertTrue(receipt["replay_equivalent"])
        self.assertTrue(receipt["registry_sha256_changed"])

    def test_recompute_rejects_current_identity_drift_even_if_registry_sha_changed(self):
        stored = _score("a" * 64)
        recomputed = _score("9" * 64)
        recomputed["scored_identity"]["underlying_family"] = "OTHER"
        with tempfile.TemporaryDirectory() as td:
            score_path = Path(td) / "score.json"
            score_path.write_text(json.dumps(stored), encoding="utf-8")
            with patch("benchmarks_ext.certify_roles.build_score_report", return_value=recomputed):
                with self.assertRaisesRegex(ValueError, "score_registry_authority_projection_changed"):
                    recompute_and_verify_score(
                        score_path=score_path,
                        candidates_path=Path(td) / "candidates.jsonl",
                        reference_path=Path(td) / "reference.jsonl",
                        gold_manifest_path=Path(td) / "manifest.json",
                        source_units_path=Path(td) / "source.jsonl",
                        registry_path=Path(td) / "registry.json",
                        role="PRIMARY",
                    )

    def test_certificate_entry_carries_hashed_authority_projection(self):
        score = _score()
        entry = build_entry(score, "PRIMARY", "CERTIFIED_WITH_LIMITS", [], {"recomputation_verified": True})
        projection = entry["registry_authority_projection"]
        self.assertEqual(entry["registry_authority_sha256"], canonical_projection_sha256(projection))
        self.assertEqual(projection["scored_identity"]["observed_version"], IDENTITY["observed_version"])
        self.assertTrue(entry["benchmark_inputs_verified"])


if __name__ == "__main__":
    unittest.main()
