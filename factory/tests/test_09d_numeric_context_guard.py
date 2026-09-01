from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stages_ext.guard_09d_numeric_context import evaluate_context, run_guard


def projection_row(proposition: str, value: str = "6.4", unit: str = "%") -> dict:
    return {
        "factory_candidate_id": "C1",
        "proposition": proposition,
        "numeric_values": [{"value_literal": value, "unit_literal": unit}],
        "09d_comparison_state": "SUPPORT",
        "loader_disposition": "READY_FOR_09D_ADJUDICATION",
    }


def comparison(value_text: str) -> dict:
    return {
        "candidate_id": "C1",
        "top_matches": [{
            "subject_compatible": True,
            "predicate_compatible": True,
            "value_text": value_text,
        }],
    }


class NumericContextEvaluationTests(unittest.TestCase):
    def test_temperature_conflict_downgrades_support(self):
        row = projection_row("Desflurane MAC is 6.4% at 25 C.")
        result = evaluate_context(row, comparison("MAC is 6.4% at 20 C"))
        self.assertTrue(result["review_required"])
        self.assertEqual(result["effective_state"], "CONTEXT_DIFFERENCE")
        self.assertEqual(result["context_dimensions"][0]["unit"], "degc")
        self.assertEqual(result["context_dimensions"][0]["relation"], "CONFLICT")

    def test_equal_temperature_preserves_support(self):
        row = projection_row("Desflurane MAC is 6.4% at 25 C.")
        result = evaluate_context(row, comparison("MAC is 6.40% at 25 C"))
        self.assertFalse(result["review_required"])
        self.assertEqual(result["effective_state"], "SUPPORT")
        self.assertEqual(result["context_dimensions"][0]["relation"], "EQUIVALENT")

    def test_missing_temperature_on_one_side_requires_review(self):
        row = projection_row("Desflurane MAC is 6.4% at 25 C.")
        result = evaluate_context(row, comparison("MAC is 6.4%"))
        self.assertTrue(result["review_required"])
        self.assertEqual(result["effective_state"], "CONTEXT_DIFFERENCE")
        self.assertEqual(result["context_dimensions"][0]["relation"], "SCOPE_MISMATCH")

    def test_target_pressure_is_not_misclassified_as_context(self):
        row = projection_row("Partial pressure is 100 mmHg at 25 C.", value="100", unit="mmHg")
        result = evaluate_context(row, comparison("Partial pressure is 100 mmHg at 20 C"))
        self.assertTrue(result["review_required"])
        self.assertEqual([x["unit"] for x in result["context_dimensions"]], ["degc"])

    def test_matching_ambient_pressure_context_can_pass(self):
        row = projection_row("Desflurane MAC is 6.4% at 760 mmHg.")
        result = evaluate_context(row, comparison("MAC is 6.4% at 760 mmHg"))
        self.assertFalse(result["review_required"])
        self.assertEqual(result["context_dimensions"][0]["unit"], "mmhg")
        self.assertEqual(result["context_dimensions"][0]["relation"], "EQUIVALENT")

    def test_no_structured_target_does_not_invent_context_binding(self):
        row = projection_row("Desflurane MAC is 6.4% at 25 C.")
        row["numeric_values"] = []
        result = evaluate_context(row, comparison("MAC is 6.4% at 20 C"))
        self.assertEqual(result["result"], "NOT_EVALUATED_NO_STRUCTURED_TARGET")
        self.assertFalse(result["review_required"])


class NumericContextGuardIntegrationTests(unittest.TestCase):
    def test_guard_downgrades_projection_and_preserves_original_state(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            out = run_dir / "09D"
            out.mkdir(parents=True)
            row = projection_row("Desflurane MAC is 6.4% at 25 C.")
            (out / "motion2_candidate_projection.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            (out / "comparison_09d.jsonl").write_text(
                json.dumps(comparison("MAC is 6.4% at 20 C")) + "\n", encoding="utf-8"
            )
            (out / "motion2_projection_summary.json").write_text(json.dumps({
                "projection_status": "SCHEMA_COMPATIBLE_NEEDS_GOVERNED_09D_LOADER",
                "projection_errors": [],
                "projection_error_count": 0,
            }), encoding="utf-8")

            summary = run_guard(run_dir)
            self.assertEqual(summary["review_required_count"], 1)
            self.assertEqual(summary["projection_status_after_guard"], "PROJECTION_REVIEW_REQUIRED")
            updated = json.loads((out / "motion2_candidate_projection.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(updated["09d_comparison_state"], "SUPPORT")
            self.assertEqual(updated["09d_projection_effective_state"], "CONTEXT_DIFFERENCE")
            self.assertEqual(updated["loader_disposition"], "REVIEW_REQUIRED")
            projection_summary = json.loads((out / "motion2_projection_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(projection_summary["projection_status"], "PROJECTION_REVIEW_REQUIRED")
            codes = {x["code"] for x in projection_summary["projection_errors"]}
            self.assertIn("09D_NUMERIC_CONTEXT_REVIEW_REQUIRED", codes)


if __name__ == "__main__":
    unittest.main()
