from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.owner_real_validation import (
    EXPECTED_MACHINES_SHA256,
    EXPECTED_UNIT_HASHES,
    _contradiction_queue,
    parse_spec,
    validate_gold,
    validate_gold_scoring_disjointness,
    validate_independence,
)


class OwnerValidationHelperTests(unittest.TestCase):
    def test_parse_spec_preserves_ollama_tag(self):
        self.assertEqual(parse_spec("ollama:nuextract3-q8:latest"), ("ollama", "nuextract3-q8:latest"))

    def test_independence_requires_distinct_empirical_groups(self):
        registry = {
            "model_identities": {
                "OLLAMA|a": {"underlying_family": "A", "independence_group": "A", "empirical_semantic_model": True},
                "OLLAMA|b": {"underlying_family": "B", "independence_group": "B", "empirical_semantic_model": True},
                "OLLAMA|c": {"underlying_family": "C", "independence_group": "C", "empirical_semantic_model": True},
            }
        }
        rows = validate_independence(registry, ["ollama:a", "ollama:b", "ollama:c"], "test")
        self.assertEqual([x["independence_group"] for x in rows], ["A", "B", "C"])
        registry["model_identities"]["OLLAMA|c"]["independence_group"] = "A"
        with self.assertRaisesRegex(RuntimeError, "independence_groups_not_distinct"):
            validate_independence(registry, ["ollama:a", "ollama:b", "ollama:c"], "test")

    def test_non_empirical_provider_is_rejected(self):
        registry = {
            "model_identities": {
                "ECHO|echo": {"underlying_family": "FIXTURE", "independence_group": "FIXTURE", "empirical_semantic_model": False},
            }
        }
        with self.assertRaisesRegex(RuntimeError, "non_empirical_provider_not_allowed"):
            validate_independence(registry, ["echo:echo"], "test")

    def test_gold_reference_must_match_source_and_reference_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "reference_v1.jsonl"
            row = {"source_unit_id": "U", "proposition": "p", "evidence": "e"}
            ref.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
            import hashlib
            ref_sha = hashlib.sha256(ref.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            manifest = {
                "benchmark_version": "MACHINES_P0299_P0301_SOURCE_FIRST_v1",
                "gold_label": "MECHANICALLY_CHECKED",
                "source_pdf_sha256": EXPECTED_MACHINES_SHA256,
                "source_units_sha256": "sourcehash",
                "source_unit_count": 8,
                "source_unit_content_sha256": EXPECTED_UNIT_HASHES,
                "gold_construction_independence_groups": ["A", "B", "C"],
                "gold_construction_models_not_scorable": ["gold-a", "gold-b", "gold-c"],
                "scoring_reference": "reference_v1.jsonl",
                "scoring_reference_sha256": ref_sha,
            }
            (root / "GOLD_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
            reference, _, _ = validate_gold(root, "sourcehash")
            self.assertEqual(reference, ref)
            with self.assertRaisesRegex(RuntimeError, "gold_source_units_hash_mismatch"):
                validate_gold(root, "other")

    def test_gold_scoring_family_overlap_is_rejected_even_with_different_model_alias(self):
        manifest = {
            "gold_construction_independence_groups": ["QWEN", "LLAMA", "MISTRAL"],
            "gold_construction_models_not_scorable": ["gold-qwen", "gold-llama", "gold-mistral"],
        }
        scored = [
            {"model_alias": "different-qwen-model", "independence_group": "QWEN"},
            {"model_alias": "deepseek", "independence_group": "DEEPSEEK"},
        ]
        with self.assertRaisesRegex(RuntimeError, "gold_scoring_independence_group_overlap"):
            validate_gold_scoring_disjointness(manifest, scored)

    def test_gold_scoring_disjointness_passes_for_separate_families(self):
        manifest = {
            "gold_construction_independence_groups": ["GOLD_A", "GOLD_B", "GOLD_C"],
            "gold_construction_models_not_scorable": ["ga", "gb", "gc"],
        }
        scored = [
            {"model_alias": "primary", "independence_group": "PRIMARY_FAMILY"},
            {"model_alias": "blind", "independence_group": "BLIND_FAMILY"},
        ]
        result = validate_gold_scoring_disjointness(manifest, scored)
        self.assertEqual(result["overlap"], [])

    def test_contradiction_queue_rejects_unstructured_contradiction(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            (run / "09D").mkdir()
            (run / "ASSERTIONS").mkdir()
            (run / "ASSERTIONS" / "union_candidates.jsonl").write_text(
                json.dumps({"candidate_id": "C1", "evidence": "e"}) + "\n", encoding="utf-8"
            )
            bad = {
                "candidate_id": "C1", "source_unit_id": "U1", "state": "CONTRADICTION",
                "comparison_confidence": "HIGH", "proposition": "x",
                "top_matches": [{"subject_compatible": False, "predicate_compatible": True, "fact_family_compatible": True}],
            }
            (run / "09D" / "comparison_09d.jsonl").write_text(json.dumps(bad) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unstructured_contradiction_emitted"):
                _contradiction_queue(run)


if __name__ == "__main__":
    unittest.main()
