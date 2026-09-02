from __future__ import annotations

import unittest

from benchmarks_ext.certify_cold_audit_dimensions import dimension_gate
from benchmarks_ext.cold_audit_challenge_dimensions import (
    DIM_NEGATION,
    DIM_NUMERIC,
    DIM_QUALIFIER,
    DIM_RELATIONSHIP_DIRECTION,
    DIM_SUPPORTED,
    DIM_UNSUPPORTED_ADDITION,
    applicable_dimensions,
    build_dimension_challenges,
    coverage_summary,
)
from hermes_factory.hashing import sha256_text
from hermes_factory.models import SourceUnit


def _unit(content: str) -> SourceUnit:
    return SourceUnit(
        source_unit_id="U1",
        source_id="S",
        source_version_id="V",
        source_sha256="f" * 64,
        unit_type="PARAGRAPH",
        content_representation="TEXT",
        locator={"pdf_pages": [1]},
        content_sha256=sha256_text(content),
        content=content,
    )


class ColdAuditDimensionTests(unittest.TestCase):
    def test_generator_covers_applicable_runtime_dimensions(self):
        content = "Pressure may increase to 20 mmHg under this condition."
        unit = _unit(content)
        gold = [{
            "source_unit_id": "U1",
            "proposition": "Pressure may increase to 20 mmHg.",
            "evidence": "Pressure may increase to 20 mmHg",
        }]
        challenges = build_dimension_challenges(gold, {"U1": unit})
        dimensions = {row["dimension"] for row in challenges}
        required = applicable_dimensions(gold)
        self.assertTrue(required <= dimensions)
        self.assertTrue({
            DIM_SUPPORTED,
            DIM_UNSUPPORTED_ADDITION,
            DIM_NEGATION,
            DIM_NUMERIC,
            DIM_QUALIFIER,
            DIM_RELATIONSHIP_DIRECTION,
        } <= dimensions)

    def test_perfect_results_pass_dimension_gate(self):
        content = "Pressure may increase to 20 mmHg under this condition."
        unit = _unit(content)
        gold = [{
            "source_unit_id": "U1",
            "proposition": "Pressure may increase to 20 mmHg.",
            "evidence": "Pressure may increase to 20 mmHg",
        }]
        challenges = build_dimension_challenges(gold, {"U1": unit})
        results = [{
            "challenge_id": c["challenge_id"],
            "correct": True,
            "actual_supported": c["expected_supported"],
        } for c in challenges]
        coverage = coverage_summary(challenges, results, applicable_dimensions(gold))
        ok, failures = dimension_gate(coverage)
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_one_dimension_failure_blocks_gate_even_when_others_pass(self):
        content = "Pressure may increase to 20 mmHg under this condition."
        unit = _unit(content)
        gold = [{
            "source_unit_id": "U1",
            "proposition": "Pressure may increase to 20 mmHg.",
            "evidence": "Pressure may increase to 20 mmHg",
        }]
        challenges = build_dimension_challenges(gold, {"U1": unit})
        results = []
        failed = False
        for c in challenges:
            correct = True
            actual = c["expected_supported"]
            if c["dimension"] == DIM_NEGATION and not failed:
                correct = False
                actual = True
                failed = True
            results.append({"challenge_id": c["challenge_id"], "correct": correct, "actual_supported": actual})
        coverage = coverage_summary(challenges, results, applicable_dimensions(gold))
        ok, failures = dimension_gate(coverage)
        self.assertFalse(ok)
        self.assertTrue(any("NEGATION" in x for x in failures))


if __name__ == "__main__":
    unittest.main()
