from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes_factory.cold_audit_semantic import run_semantic_cold_audit
from hermes_factory.controller import run_factory
from hermes_factory.hashing import sha256_file, sha256_text
from hermes_factory.models import AssertionCandidate, SourceUnit, WorkerIdentity
from hermes_factory.providers.base import SemanticProvider
from hermes_factory.runtime_identity import resolve_runtime_topology
from hermes_factory.source import write_source_units


class _Provider(SemanticProvider):
    def __init__(self, provider: str, model: str, family: str, *, empirical: bool = True, role: str = "PRIMARY"):
        self._identity = WorkerIdentity(provider, model, family, "1", role, "UNBENCHMARKED")
        self.empirical = empirical
        self.calls = 0

    def identity(self) -> WorkerIdentity:
        return self._identity

    def capabilities(self):
        return {"network_required": False, "roles": [self._identity.role]}

    def is_empirical_semantic_provider(self) -> bool:
        return self.empirical

    def execute(self, request):
        self.calls += 1
        if request.get("task_role") == "COLD_AUDIT":
            return {"verdict": {"supported": True, "flags": [], "rationale": "fixture"}}
        return {"assertions": []}


def _registry(*rows: tuple[str, str, str, str, bool]) -> dict:
    identities = {}
    for provider, model, family, group, empirical in rows:
        identities[f"{provider.upper()}|{model}"] = {
            "underlying_family": family,
            "independence_group": group,
            "empirical_semantic_model": empirical,
            "observed_version_policy": "CLI_OBSERVED",
        }
    return {
        "schema_version": "test",
        "benchmark_version": "TEST",
        "model_identities": identities,
        "certifications": {},
    }


class RuntimeTopologyTests(unittest.TestCase):
    def test_distinct_family_labels_same_group_are_not_independent(self):
        reg = _registry(
            ("OLLAMA", "qwen-main", "QWEN_MAIN", "QWEN", True),
            ("OLLAMA", "nuextract", "QWEN_NUEXTRACT", "QWEN", True),
        )
        primary = _Provider("OLLAMA", "qwen-main", "QWEN_MAIN")
        blind = _Provider("OLLAMA", "nuextract", "QWEN_NUEXTRACT", role="BLIND_RECALL")
        with self.assertRaisesRegex(ValueError, "primary_blind_independence_group_collision:QWEN"):
            resolve_runtime_topology(reg, primary, blind)

    def test_cold_auditor_cannot_share_primary_group(self):
        reg = _registry(
            ("OLLAMA", "primary", "PRIMARY_FAMILY", "GROUP_A", True),
            ("OLLAMA", "blind", "BLIND_FAMILY", "GROUP_B", True),
            ("OLLAMA", "cold", "COLD_FINE_TUNE", "GROUP_A", True),
        )
        with self.assertRaisesRegex(ValueError, "cold_audit_independence_group_collision:GROUP_A"):
            resolve_runtime_topology(
                reg,
                _Provider("OLLAMA", "primary", "PRIMARY_FAMILY"),
                _Provider("OLLAMA", "blind", "BLIND_FAMILY", role="BLIND_RECALL"),
                _Provider("OLLAMA", "cold", "COLD_FINE_TUNE", role="COLD_AUDIT"),
            )

    def test_provider_family_spoof_is_rejected(self):
        reg = _registry(
            ("OLLAMA", "primary", "REGISTRY_FAMILY", "GROUP_A", True),
            ("OLLAMA", "blind", "BLIND_FAMILY", "GROUP_B", True),
        )
        with self.assertRaisesRegex(ValueError, "PRIMARY_underlying_family_mismatch"):
            resolve_runtime_topology(
                reg,
                _Provider("OLLAMA", "primary", "SPOOFED_FAMILY"),
                _Provider("OLLAMA", "blind", "BLIND_FAMILY", role="BLIND_RECALL"),
            )

    def test_provider_empirical_self_claim_cannot_override_registry(self):
        reg = _registry(
            ("OLLAMA", "primary", "PRIMARY_FAMILY", "GROUP_A", False),
            ("OLLAMA", "blind", "BLIND_FAMILY", "GROUP_B", True),
        )
        with self.assertRaisesRegex(ValueError, "PRIMARY_empirical_status_mismatch"):
            resolve_runtime_topology(
                reg,
                _Provider("OLLAMA", "primary", "PRIMARY_FAMILY", empirical=True),
                _Provider("OLLAMA", "blind", "BLIND_FAMILY", role="BLIND_RECALL"),
            )


class ColdAuditGroupTests(unittest.TestCase):
    def test_cold_audit_uses_independence_group_not_family_label(self):
        content = "Vapor pressure increases with temperature."
        unit = SourceUnit(
            source_unit_id="SU", source_id="SRC", source_version_id="V1", source_sha256="0" * 64,
            unit_type="PARAGRAPH", content_representation="TEXT", locator={"pdf_pages": [1]},
            content_sha256=sha256_text(content), content=content,
        )
        candidate = AssertionCandidate(
            candidate_id="CAND", source_unit_id="SU", source_id="SRC", source_version_id="V1",
            source_sha256="0" * 64, locator=unit.locator, evidence=content,
            evidence_sha256=sha256_text(content), proposition=content,
            originating_capsule_id="CAP", originating_run_id="RUN", parent_artifact_sha256="PARENT",
        )
        auditor = _Provider("OLLAMA", "cold", "DISTINCT_FAMILY", role="COLD_AUDIT")
        report = run_semantic_cold_audit(
            auditor, [candidate], [unit], rate=1.0, run_id="RUN",
            primary_family="PRIMARY_FAMILY", blind_family="BLIND_FAMILY",
            primary_independence_group="SHARED_GROUP",
            blind_independence_group="OTHER_GROUP",
            auditor_independence_group="SHARED_GROUP",
        )
        self.assertEqual(report["status"], "FAIL_INDEPENDENCE")
        self.assertFalse(report["auditor_independent_group"])
        self.assertEqual(report["auditor_independence_group"], "SHARED_GROUP")


class PredispatchTopologyTests(unittest.TestCase):
    def test_same_group_is_rejected_before_any_real_provider_call(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            project = td / "project"
            current = project / "CURRENT"
            current.mkdir(parents=True)
            reg = _registry(
                ("OLLAMA", "qwen-main", "QWEN_MAIN", "QWEN", True),
                ("OLLAMA", "nuextract", "QWEN_NUEXTRACT", "QWEN", True),
            )
            (current / "MODEL_CERTIFICATION_REGISTRY.json").write_text(json.dumps(reg), encoding="utf-8")

            source = td / "source.bin"
            source.write_bytes(b"governed source")
            source_sha = sha256_file(source)
            content = "Vapor pressure increases with temperature."
            unit = SourceUnit(
                source_unit_id="SU", source_id="SRC", source_version_id="V1", source_sha256=source_sha,
                unit_type="PARAGRAPH", content_representation="TEXT", locator={"pdf_pages": [1]},
                content_sha256=sha256_text(content), content=content,
            )
            units_path = td / "source_units.jsonl"
            write_source_units([unit], units_path)

            primary = _Provider("OLLAMA", "qwen-main", "QWEN_MAIN")
            blind = _Provider("OLLAMA", "nuextract", "QWEN_NUEXTRACT", role="BLIND_RECALL")
            with patch("hermes_factory.controller.write_current_manifest", return_value={}), \
                 patch("hermes_factory.controller.verify_build", return_value={"result": "PASS", "errors": []}), \
                 patch("hermes_factory.controller.verify_runtime_lock", return_value={"result": "PASS", "errors": []}):
                with self.assertRaisesRegex(RuntimeError, "MODEL_IDENTITY_INDEPENDENCE"):
                    run_factory(
                        project_root=project, source_units_path=units_path,
                        primary_provider=primary, blind_provider=blind,
                        output_root=td / "out", source_pdf=source,
                        source_expected_sha256=source_sha, mode="EXTERNAL_COMMAND",
                        execution_mode="LOCAL_ONLY",
                    )
            self.assertEqual(primary.calls, 0)
            self.assertEqual(blind.calls, 0)


if __name__ == "__main__":
    unittest.main()
