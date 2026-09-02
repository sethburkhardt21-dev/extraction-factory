from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmarks_ext.certify_roles import _bound_semantic_digest
from benchmarks_ext.score_role import sha256_file


class SemanticDigestByteBindingTests(unittest.TestCase):
    def _row(self, proposition: str = "Agent is 1%.") -> dict:
        return {
            "candidate_id": "C1",
            "source_unit_id": "U1",
            "source_sha256": "a" * 64,
            "evidence": "Agent is 1%.",
            "proposition": proposition,
            "worker_identity": {
                "provider": "OLLAMA",
                "model_alias": "model",
                "observed_version": "sha256:" + "1" * 64,
            },
        }

    def test_bound_digest_accepts_exact_scored_candidate_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "candidates.jsonl"
            path.write_text(json.dumps(self._row(), sort_keys=True) + "\n", encoding="utf-8")
            score = {
                "input_paths": {"candidates": str(path)},
                "candidate_file_sha256": sha256_file(path),
                "units_in_scope": ["U1"],
            }
            digest = _bound_semantic_digest(
                score, path_key="candidates", file_sha_key="candidate_file_sha256"
            )
            self.assertIsInstance(digest, str)
            self.assertEqual(len(digest), 64)

    def test_post_score_candidate_mutation_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "candidates.jsonl"
            path.write_text(json.dumps(self._row(), sort_keys=True) + "\n", encoding="utf-8")
            score = {
                "input_paths": {"candidates": str(path)},
                "candidate_file_sha256": sha256_file(path),
                "units_in_scope": ["U1"],
            }
            path.write_text(json.dumps(self._row("Agent is approximately 1%."), sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidate_file_changed_after_score"):
                _bound_semantic_digest(
                    score, path_key="candidates", file_sha_key="candidate_file_sha256"
                )


if __name__ == "__main__":
    unittest.main()
