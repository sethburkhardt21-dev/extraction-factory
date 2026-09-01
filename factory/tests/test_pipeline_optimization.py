from __future__ import annotations
import json
import unittest
from unittest.mock import patch

from hermes_factory.controller import _resolved_schedule, _effective_concurrency
from hermes_factory.cold_audit_semantic import _risk_stratified_sample
from hermes_factory.hashing import sha256_text
from hermes_factory.models import AssertionCandidate, SourceUnit, WorkerIdentity
from hermes_factory.providers.base import SemanticProvider
from providers_ext.llm_provider import call_ollama


class Provider(SemanticProvider):
    def __init__(self, name, model, family, local=True):
        self._id = WorkerIdentity(name, model, family, "1", "PRIMARY", "UNBENCHMARKED")
        self.local = local
    def identity(self): return self._id
    def capabilities(self): return {"network_required": not self.local}
    def execute(self, request): return {"assertions": []}


class SchedulerTests(unittest.TestCase):
    def test_auto_phases_distinct_local_models(self):
        p = Provider("OLLAMA", "qwen", "QWEN", True)
        b = Provider("OLLAMA", "nuextract", "NUEXTRACT", True)
        self.assertEqual(_resolved_schedule(p, b, "AUTO"), "PHASED")

    def test_auto_keeps_remote_models_parallel(self):
        p = Provider("CLOUD", "a", "A", False)
        b = Provider("CLOUD", "b", "B", False)
        self.assertEqual(_resolved_schedule(p, b, "AUTO"), "PARALLEL")

    def test_local_default_concurrency_is_one_but_override_is_honored(self):
        p = Provider("OLLAMA", "qwen", "QWEN", True)
        self.assertEqual(_effective_concurrency(p, None, 8), 1)
        self.assertEqual(_effective_concurrency(p, 3, 8), 3)


class ColdAuditSamplingTests(unittest.TestCase):
    def _candidate(self, cid, uid, numeric=False):
        return AssertionCandidate(
            candidate_id=cid, source_unit_id=uid, source_id="S", source_version_id="V", source_sha256="h",
            locator={"pdf_pages":[1]}, evidence="x", evidence_sha256=sha256_text("x"), proposition="x",
            numeric_values=[{"value_literal":"1"}] if numeric else [], originating_capsule_id="C",
            originating_run_id="R", parent_artifact_sha256="P", worker_identity={}, origin_pass="PRIMARY",
        )

    def test_table_numeric_candidate_is_prioritized_without_increasing_sample_volume(self):
        units = {
            "T": SourceUnit("T","S","V","h","TABLE_TEXT_LAYER","TABLE",{"pdf_pages":[1]},sha256_text("x"),"x"),
            "P": SourceUnit("P","S","V","h","PARAGRAPH","TEXT",{"pdf_pages":[1]},sha256_text("x"),"x"),
        }
        candidates = [self._candidate(f"P{i}", "P") for i in range(20)] + [self._candidate("TABLE", "T", True)]
        sample, baseline = _risk_stratified_sample(candidates, units, rate=0.20, max_sample=40)
        self.assertEqual(len(sample), max(baseline, 1))
        self.assertIn("TABLE", {c.candidate_id for c in sample})


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.payload).encode("utf-8")


class OllamaResidencyTests(unittest.TestCase):
    def test_keep_alive_and_deterministic_temperature_are_sent(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured.update(json.loads(req.data.decode("utf-8")))
            return FakeResponse({"message":{"content":"{}"}})
        with patch("providers_ext.llm_provider.urllib.request.urlopen", side_effect=fake_urlopen):
            call_ollama("m", "s", "u", 10, "http://127.0.0.1:11434", keep_alive="45m", temperature=0.0)
        self.assertEqual(captured["keep_alive"], "45m")
        self.assertEqual(captured["options"]["temperature"], 0.0)


if __name__ == "__main__":
    unittest.main()
