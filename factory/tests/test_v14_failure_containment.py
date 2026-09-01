from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hermes_factory.cli import _lease_ttl
from hermes_factory.controller_v14 import _write_json
from run_appliance import _appliance_status, _last_json_object


class LeaseSafetyTests(unittest.TestCase):
    def test_default_lease_exceeds_provider_timeout_with_safety_margin(self):
        args = SimpleNamespace(provider_timeout=900, lease_ttl_seconds=None)
        self.assertGreaterEqual(_lease_ttl(args), 1200)
        self.assertGreater(_lease_ttl(args), args.provider_timeout)

    def test_operator_cannot_make_lease_shorter_than_provider_timeout(self):
        args = SimpleNamespace(provider_timeout=900, lease_ttl_seconds=900)
        with self.assertRaises(SystemExit):
            _lease_ttl(args)


class ApplianceContainmentTests(unittest.TestCase):
    def test_requested_poststage_failure_downgrades_green_core_status(self):
        self.assertEqual(
            _appliance_status("FRONTIER_REVIEW_READY", [{"stage": "09D", "error": "boom"}]),
            "NOT_READY",
        )
        self.assertEqual(_appliance_status("READY_FOR_PROVIDER", []), "READY_FOR_PROVIDER")

    def test_terminal_json_parser_ignores_braces_in_prior_logs(self):
        value = _last_json_object('log {not json}\nmore log\n{"run_id":"R","ok":true}\n')
        self.assertEqual(value["run_id"], "R")
        self.assertTrue(value["ok"])


class AtomicArtifactTests(unittest.TestCase):
    def test_atomic_json_replaces_target_without_visible_temp_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.json"
            _write_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})
            self.assertEqual([p for p in Path(td).iterdir() if p.name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
