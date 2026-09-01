from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from benchmarks_ext.certify_roles import apply_version_binding_gate
from benchmarks_ext.score_role import validate_scoring_independence
from hermes_factory.model_registry import observed_version_is_certifiable
from providers_ext.ollama_digest_guard import build_parser as build_guard_parser, execute_guarded
from run_appliance import provider_flags, resolve_observed_version, resolve_ollama_digest


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class VersionPolicyTests(unittest.TestCase):
    def test_ollama_digest_is_certifiable(self):
        self.assertTrue(observed_version_is_certifiable("OLLAMA_DIGEST", DIGEST_A))

    def test_ollama_placeholder_is_not_certifiable(self):
        for value in ("CLI_OBSERVED", "UNKNOWN", "UNOBSERVED", ""):
            self.assertFalse(observed_version_is_certifiable("OLLAMA_DIGEST", value))

    def test_generic_cli_observed_policy_is_never_certification_authority(self):
        self.assertFalse(observed_version_is_certifiable("CLI_OBSERVED", "plausible-version-string"))

    def test_unpinned_hosted_alias_is_not_certifiable(self):
        self.assertFalse(observed_version_is_certifiable("UNPINNED_HOSTED_ALIAS", "claude-opus-5-20260901"))


class ScorerVersionIdentityTests(unittest.TestCase):
    REGISTRY = {"model_identities": {
        "OLLAMA|scored": {
            "underlying_family": "DEEPSEEK",
            "independence_group": "DEEPSEEK",
            "empirical_semantic_model": True,
            "observed_version_policy": "OLLAMA_DIGEST",
        }
    }}
    MANIFEST = {
        "gold_construction_independence_groups": ["QWEN", "LLAMA", "MISTRAL"],
        "gold_construction_models_not_scorable": ["a", "b", "c"],
    }

    @staticmethod
    def candidate(version: str) -> dict:
        return {
            "candidate_id": "C",
            "source_unit_id": "U",
            "worker_identity": {
                "provider": "OLLAMA",
                "model_alias": "scored",
                "observed_version": version,
            },
            "proposition": "p",
            "evidence": "e",
        }

    def test_scored_identity_carries_observed_digest(self):
        ident = validate_scoring_independence(
            [self.candidate(DIGEST_A)], self.MANIFEST, self.REGISTRY,
            expected_model="scored", label="scored",
        )
        self.assertEqual(ident["observed_version"], DIGEST_A)
        self.assertTrue(ident["version_binding_certifiable"])

    def test_same_alias_mixed_observed_versions_is_rejected(self):
        rows = [self.candidate(DIGEST_A), {**self.candidate(DIGEST_B), "candidate_id": "C2"}]
        with self.assertRaisesRegex(ValueError, "observed_version_mixed"):
            validate_scoring_independence(rows, self.MANIFEST, self.REGISTRY, label="scored")


class CertificationVersionGateTests(unittest.TestCase):
    def test_metrics_pass_becomes_blocked_external_when_version_unpinned(self):
        score = {"scored_identity": {
            "provider": "CLAUDE",
            "model_alias": "claude-opus-5",
            "observed_version": "UNPINNED_ALIAS:claude-opus-5",
            "observed_version_policy": "UNPINNED_HOSTED_ALIAS",
            "version_binding_certifiable": False,
        }}
        status, failures = apply_version_binding_gate(score, "CERTIFIED_WITH_LIMITS", [])
        self.assertEqual(status, "BLOCKED_EXTERNAL")
        self.assertTrue(any("model_version_binding_not_certifiable" in x for x in failures))

    def test_certifiable_version_preserves_metrics_status(self):
        score = {"scored_identity": {
            "observed_version": DIGEST_A,
            "observed_version_policy": "OLLAMA_DIGEST",
            "version_binding_certifiable": True,
        }}
        self.assertEqual(
            apply_version_binding_gate(score, "CERTIFIED_WITH_LIMITS", []),
            ("CERTIFIED_WITH_LIMITS", []),
        )


class OllamaDigestDiscoveryTests(unittest.TestCase):
    class _Response:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def test_resolves_digest_from_same_ollama_host(self):
        payload = {"models": [{"name": "model:latest", "model": "model:latest", "digest": "a" * 64}]}
        with patch("run_appliance.urllib.request.urlopen", return_value=self._Response(payload)) as mocked:
            self.assertEqual(resolve_ollama_digest("model:latest", "http://127.0.0.1:11434"), DIGEST_A)
            request = mocked.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/tags")

    def test_missing_or_ambiguous_model_fails_closed(self):
        with patch("run_appliance.urllib.request.urlopen", return_value=self._Response({"models": []})):
            with self.assertRaisesRegex(RuntimeError, "digest_resolution_failed"):
                resolve_ollama_digest("missing:latest", "http://127.0.0.1:11434")

    def test_malformed_digest_fails_closed(self):
        payload = {"models": [{"name": "model:latest", "digest": "not-a-digest"}]}
        with patch("run_appliance.urllib.request.urlopen", return_value=self._Response(payload)):
            with self.assertRaisesRegex(RuntimeError, "digest_invalid"):
                resolve_ollama_digest("model:latest", "http://127.0.0.1:11434")

    def test_operator_cannot_spoof_ollama_version(self):
        with patch("run_appliance.resolve_ollama_digest", return_value=DIGEST_A):
            with self.assertRaisesRegex(RuntimeError, "explicit_version_mismatch"):
                resolve_observed_version("ollama", "model:latest", DIGEST_B, "http://127.0.0.1:11434")

    def test_provider_flags_bind_digest_guard_and_same_host(self):
        with patch("run_appliance.resolve_ollama_digest", return_value=DIGEST_A):
            flags = provider_flags(
                "primary", "ollama:model:latest", 60,
                ollama_host="http://10.0.0.2:11434",
            )
        self.assertIn(DIGEST_A, flags)
        command = flags[flags.index("--primary-command") + 1]
        self.assertIn("ollama_digest_guard.py", command)
        self.assertIn(f"--expected-digest {DIGEST_A}", command)
        self.assertIn("--ollama-host http://10.0.0.2:11434", command)


class OllamaSemanticGuardTests(unittest.TestCase):
    def _args(self):
        return build_guard_parser().parse_args([
            "--model", "model:latest",
            "--expected-digest", DIGEST_A,
            "--timeout", "60",
            "--ollama-host", "http://127.0.0.1:11434",
        ])

    def test_pre_call_digest_mismatch_prevents_semantic_process_start(self):
        with patch("providers_ext.ollama_digest_guard.resolve_digest", return_value=DIGEST_B), \
             patch("providers_ext.ollama_digest_guard.subprocess.run") as delegated:
            with self.assertRaisesRegex(RuntimeError, "digest_before_mismatch"):
                execute_guarded(self._args(), '{"request":1}')
            delegated.assert_not_called()

    def test_stable_before_after_digest_releases_provider_json_with_receipt(self):
        inner = subprocess.CompletedProcess(
            args=["provider"], returncode=0,
            stdout=json.dumps({"provider_receipt": {"attempts": 1}, "assertions": []}), stderr="",
        )
        with patch("providers_ext.ollama_digest_guard.resolve_digest", side_effect=[DIGEST_A, DIGEST_A]), \
             patch("providers_ext.ollama_digest_guard.subprocess.run", return_value=inner) as delegated:
            rc, stdout, stderr = execute_guarded(self._args(), '{"request":1}')
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, "")
        delegated.assert_called_once()
        output = json.loads(stdout)
        guard = output["provider_receipt"]["ollama_digest_guard"]
        self.assertTrue(guard["stable"])
        self.assertEqual(guard["expected_digest"], DIGEST_A)
        self.assertEqual(guard["before_digest"], DIGEST_A)
        self.assertEqual(guard["after_digest"], DIGEST_A)

    def test_post_call_digest_mismatch_discards_successful_semantic_output(self):
        inner = subprocess.CompletedProcess(
            args=["provider"], returncode=0,
            stdout=json.dumps({"provider_receipt": {}, "assertions": [{"proposition": "would be discarded"}]}),
            stderr="",
        )
        with patch("providers_ext.ollama_digest_guard.resolve_digest", side_effect=[DIGEST_A, DIGEST_B]), \
             patch("providers_ext.ollama_digest_guard.subprocess.run", return_value=inner) as delegated:
            with self.assertRaisesRegex(RuntimeError, "digest_after_mismatch"):
                execute_guarded(self._args(), '{"request":1}')
            delegated.assert_called_once()


if __name__ == "__main__":
    unittest.main()
