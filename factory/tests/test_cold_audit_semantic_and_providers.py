from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "providers_ext"))

import llm_provider  # noqa: E402
from hermes_factory.cold_audit_semantic import run_semantic_cold_audit  # noqa: E402
from hermes_factory.models import AssertionCandidate, SourceUnit, WorkerIdentity  # noqa: E402
from hermes_factory.providers.base import SemanticProvider  # noqa: E402
from hermes_factory.providers.command import JSONCommandProvider  # noqa: E402
from hermes_factory.semantic import execute_primary  # noqa: E402


def _unit(content: str = "Vapor pressure increases with temperature. It is not affected by barometric pressure.") -> SourceUnit:
    return SourceUnit(
        source_unit_id="SU-TEST-1", source_id="SRC-TEST", source_version_id="SRC-TEST-V1",
        source_sha256="0" * 64, unit_type="PARAGRAPH", content_representation="TEXT",
        locator={"pdf_pages": [1]}, content_sha256="1" * 64, content=content,
    )


def _candidate(unit: SourceUnit, proposition: str, evidence: str, cid: str) -> AssertionCandidate:
    return AssertionCandidate(
        candidate_id=cid, source_unit_id=unit.source_unit_id, source_id=unit.source_id,
        source_version_id=unit.source_version_id, source_sha256=unit.source_sha256,
        locator=unit.locator, evidence=evidence, evidence_sha256="e" * 64,
        proposition=proposition, originating_capsule_id="CAP-TEST",
        originating_run_id="RUN-TEST", parent_artifact_sha256="GENESIS",
    )


class _FakeAuditor(SemanticProvider):
    def __init__(self, family: str, supported: bool = True, raise_on: set[str] | None = None):
        self.family = family
        self.supported = supported
        self.raise_on = raise_on or set()

    def identity(self) -> WorkerIdentity:
        return WorkerIdentity("FAKE", "fake-auditor", self.family, "1", "COLD_AUDIT", "UNBENCHMARKED")

    def capabilities(self):
        return {"roles": ["COLD_AUDIT"], "network_required": False}

    def execute(self, request):
        cid = request["audit_target"]["candidate_id"]
        if cid in self.raise_on:
            raise RuntimeError("auditor_exploded")
        return {"verdict": {"supported": self.supported, "flags": [], "rationale": "fake"}}


class SemanticColdAuditTests(unittest.TestCase):
    def setUp(self):
        self.unit = _unit()
        self.cands = [
            _candidate(self.unit, "Vapor pressure increases with temperature.",
                       "Vapor pressure increases with temperature.", "CAND-A"),
            _candidate(self.unit, "It is not affected by barometric pressure.",
                       "It is not affected by barometric pressure.", "CAND-B"),
        ]

    def _run(self, auditor):
        return run_semantic_cold_audit(
            auditor, self.cands, [self.unit], rate=1.0, run_id="RUN-TEST",
            primary_family="CLAUDE", blind_family="GPT_OSS",
        )

    def test_independent_supportive_auditor_passes(self):
        report = self._run(_FakeAuditor("DEEPSEEK", supported=True))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["auditor_independent_family"])
        self.assertEqual(report["audited_count"], 2)
        self.assertEqual(report["disagreement_count"], 0)

    def test_same_family_auditor_cannot_pass_even_when_supportive(self):
        report = self._run(_FakeAuditor("CLAUDE", supported=True))
        self.assertEqual(report["status"], "FAIL_INDEPENDENCE")
        self.assertFalse(report["auditor_independent_family"])

    def test_unsupported_verdicts_become_bounded_disagreements(self):
        report = self._run(_FakeAuditor("DEEPSEEK", supported=False))
        self.assertEqual(report["status"], "FAIL_REVIEW_REQUIRED")
        self.assertEqual(report["disagreement_count"], 2)

    def test_auditor_crash_is_a_finding_not_a_crash(self):
        report = self._run(_FakeAuditor("DEEPSEEK", supported=True, raise_on={"CAND-B"}))
        self.assertEqual(report["status"], "FAIL_REVIEW_REQUIRED")
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["audited_count"], 2)

    def test_empty_sample_cannot_pass(self):
        report = run_semantic_cold_audit(
            _FakeAuditor("DEEPSEEK"), [], [self.unit], rate=1.0, run_id="RUN-TEST",
            primary_family="CLAUDE", blind_family="GPT_OSS",
        )
        self.assertNotEqual(report["status"], "PASS")


class ProviderValidationTests(unittest.TestCase):
    CONTENT = "At sea level the pressure is 760 mm Hg.  Water boils at\n100°C at that pressure."

    def test_exact_substring_passes(self):
        valid, rejected = llm_provider.validate_assertions(
            [{"proposition": "p", "evidence": "the pressure is 760 mm Hg"}], self.CONTENT)
        self.assertEqual(len(valid), 1)
        self.assertEqual(rejected, [])

    def test_trimmed_evidence_recovered(self):
        valid, rejected = llm_provider.validate_assertions(
            [{"proposition": "p", "evidence": "  the pressure is 760 mm Hg  "}], self.CONTENT)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["evidence"], "the pressure is 760 mm Hg")

    def test_whitespace_normalized_recovery_uses_source_bytes(self):
        valid, rejected = llm_provider.validate_assertions(
            [{"proposition": "p", "evidence": "Water boils at 100°C at that pressure."}], self.CONTENT)
        self.assertEqual(len(valid), 1)
        self.assertIn("boils at\n100°C", valid[0]["evidence"])
        self.assertIn(valid[0]["evidence"], self.CONTENT)

    def test_fabricated_evidence_rejected(self):
        valid, rejected = llm_provider.validate_assertions(
            [{"proposition": "p", "evidence": "pressure is 761 mm Hg"}], self.CONTENT)
        self.assertEqual(valid, [])
        self.assertEqual(rejected[0]["reason"], "evidence_not_exact_source_substring")

    def test_ambiguous_normalized_match_rejected(self):
        # No exact occurrence (double-space vs newline), two normalized ones:
        # recovery must refuse rather than guess which span was meant.
        content = "alpha  beta gamma. alpha\nbeta gamma."
        valid, rejected = llm_provider.validate_assertions(
            [{"proposition": "p", "evidence": "alpha beta gamma"}], content)
        self.assertEqual(valid, [])
        self.assertEqual(len(rejected), 1)

    def test_json_extraction_handles_fences_and_think_blocks(self):
        fenced = "```json\n{\"assertions\": []}\n```"
        self.assertEqual(llm_provider._extract_json_object(fenced), {"assertions": []})
        thinky = "<think>reasoning here {not json}</think>\n{\"verdict\": {\"supported\": true}}"
        self.assertEqual(llm_provider._extract_json_object(thinky)["verdict"]["supported"], True)
        trailing = "Here you go: {\"assertions\": [{\"a\": \"b {c}\"}]} hope that helps"
        self.assertEqual(llm_provider._extract_json_object(trailing)["assertions"][0]["a"], "b {c}")


class EchoBackendBridgeTests(unittest.TestCase):
    def test_wrapper_bridges_through_json_command_provider(self):
        script = ROOT / "providers_ext" / "llm_provider.py"
        provider = JSONCommandProvider(
            [sys.executable, "-B", str(script), "--backend", "echo"],
            provider="LOCAL_ECHO", model_alias="echo", underlying_family="ECHO",
            observed_version="1", role="PRIMARY", network_required=False,
        )
        unit = _unit()
        candidates, receipt = execute_primary(provider, unit, "CAP-TEST", "RUN-TEST")
        self.assertGreaterEqual(len(candidates), 2)
        for c in candidates:
            self.assertIn(c.evidence, unit.content)
        self.assertEqual(receipt["role"], "PRIMARY")

    def test_wrapper_cold_audit_role_roundtrip(self):
        script = ROOT / "providers_ext" / "llm_provider.py"
        request = {
            "task_role": "COLD_AUDIT",
            "source_unit": _unit().to_dict(),
            "audit_target": {"candidate_id": "CAND-A", "proposition": "p", "evidence": "e"},
            "task_instructions": "audit",
        }
        proc = subprocess.run(
            [sys.executable, "-B", str(script), "--backend", "echo"],
            input=json.dumps(request), capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertIn("verdict", out)
        self.assertIsInstance(out["verdict"]["supported"], bool)


if __name__ == "__main__":
    unittest.main()
