from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks_ext.gold_build import (
    MACHINES_PILOT_SOURCE_SHA256,
    resolve_gold_identities,
    validate_governed_machines_units,
)
from benchmarks_ext.score_role import validate_scoring_independence
from hermes_factory.models import SourceUnit


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _units() -> tuple[list[SourceUnit], dict[str, str]]:
    rows = []
    expected = {}
    for idx in range(8):
        uid = f"U{idx}"
        content = f"governed-content-{idx}"
        digest = _sha(content)
        expected[uid] = digest
        rows.append(SourceUnit(
            source_unit_id=uid,
            source_id="BOOK-DORSCH-5E",
            source_version_id="BOOK-DORSCH-5E-SHA-379a5d5c7fdf",
            source_sha256=MACHINES_PILOT_SOURCE_SHA256,
            unit_type="PARAGRAPH",
            content_representation="TEXT",
            locator={"pdf_pages": [299]},
            content_sha256=digest,
            content=content,
        ))
    return rows, expected


class GovernedGoldSourceTests(unittest.TestCase):
    def test_exact_content_is_rehashed_not_trusted_from_declared_hash(self):
        rows, expected = _units()
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            validate_governed_machines_units(rows)
            rows[0].content = "tampered-but-declared-hash-left-unchanged"
            with self.assertRaisesRegex(SystemExit, "wrong_content_hash"):
                validate_governed_machines_units(rows)

    def test_declared_hash_must_equal_recomputed_content_hash(self):
        rows, expected = _units()
        rows[0].content_sha256 = "0" * 64
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            with self.assertRaisesRegex(SystemExit, "declared_content_hash_mismatch"):
                validate_governed_machines_units(rows)

    def test_pdf_identity_must_match_pinned_machines_source(self):
        rows, expected = _units()
        rows[0].source_sha256 = "f" * 64
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            with self.assertRaisesRegex(SystemExit, "gold_source_pdf_identity_mismatch"):
                validate_governed_machines_units(rows)

    def test_missing_or_extra_units_cannot_receive_machines_benchmark_label(self):
        rows, expected = _units()
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            with self.assertRaisesRegex(SystemExit, "gold_source_not_exact_governed_machines_pilot"):
                validate_governed_machines_units(rows[:-1])


class GoldConstructionIdentityTests(unittest.TestCase):
    def test_gold_builders_require_three_empirical_distinct_groups(self):
        registry = {
            "model_identities": {
                "OLLAMA|a": {"underlying_family": "A1", "independence_group": "A", "empirical_semantic_model": True},
                "OLLAMA|b": {"underlying_family": "B1", "independence_group": "B", "empirical_semantic_model": True},
                "OLLAMA|c": {"underlying_family": "C1", "independence_group": "C", "empirical_semantic_model": True},
            }
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            rows = resolve_gold_identities(path, ["ollama:a", "ollama:b", "ollama:c"])
            self.assertEqual([x["independence_group"] for x in rows], ["A", "B", "C"])
            registry["model_identities"]["OLLAMA|c"]["independence_group"] = "A"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "gold_construction_independence_groups_not_distinct"):
                resolve_gold_identities(path, ["ollama:a", "ollama:b", "ollama:c"])


class ScoringContaminationTests(unittest.TestCase):
    @staticmethod
    def _registry() -> dict:
        return {
            "model_identities": {
                "OLLAMA|gold-a": {"underlying_family": "GOLD_A", "independence_group": "QWEN", "empirical_semantic_model": True},
                "OLLAMA|scored-qwen": {"underlying_family": "QWEN_OTHER", "independence_group": "QWEN", "empirical_semantic_model": True},
                "OLLAMA|scored-deepseek": {"underlying_family": "DEEPSEEK", "independence_group": "DEEPSEEK", "empirical_semantic_model": True},
                "ECHO|echo": {"underlying_family": "FIXTURE", "independence_group": "FIXTURE", "empirical_semantic_model": False},
            }
        }

    @staticmethod
    def _candidate(model: str, provider: str = "OLLAMA") -> list[dict]:
        return [{
            "candidate_id": "C1",
            "source_unit_id": "U1",
            "worker_identity": {"provider": provider, "model_alias": model},
            "proposition": "p",
            "evidence": "e",
        }]

    @staticmethod
    def _manifest() -> dict:
        return {
            "gold_construction_independence_groups": ["QWEN", "LLAMA", "MISTRAL"],
            "gold_construction_models_not_scorable": ["gold-a", "gold-b", "gold-c"],
        }

    def test_same_family_different_model_alias_is_still_contaminated(self):
        with self.assertRaisesRegex(ValueError, "independence_group_authored_gold:QWEN"):
            validate_scoring_independence(
                self._candidate("scored-qwen"), self._manifest(), self._registry(),
                expected_model="scored-qwen", label="scored",
            )

    def test_disjoint_registered_empirical_family_can_be_scored(self):
        identity = validate_scoring_independence(
            self._candidate("scored-deepseek"), self._manifest(), self._registry(),
            expected_model="scored-deepseek", label="scored",
        )
        self.assertEqual(identity["independence_group"], "DEEPSEEK")

    def test_missing_gold_family_lineage_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "gold_manifest_missing_construction_independence_groups"):
            validate_scoring_independence(
                self._candidate("scored-deepseek"), {}, self._registry(),
                expected_model="scored-deepseek", label="scored",
            )

    def test_mixed_candidate_worker_identities_fail_closed(self):
        rows = self._candidate("scored-deepseek") + self._candidate("scored-qwen")
        with self.assertRaisesRegex(ValueError, "worker_identity_mixed"):
            validate_scoring_independence(rows, self._manifest(), self._registry(), label="scored")

    def test_non_empirical_scored_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "model_not_empirical"):
            validate_scoring_independence(
                self._candidate("echo", provider="ECHO"), self._manifest(), self._registry(),
                expected_model="echo", label="scored",
            )


if __name__ == "__main__":
    unittest.main()
