from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hermes_factory.build_integrity import build_manifest, certify_build, verify_build


class CertifiedTestSurfaceTests(unittest.TestCase):
    def _root(self, td: Path) -> tuple[Path, Path]:
        root = td / "factory"
        (td / ".git").mkdir()
        for rel in ["hermes_factory", "providers_ext", "stages_ext", "benchmarks_ext", "validation", "tests", "CURRENT"]:
            (root / rel).mkdir(parents=True, exist_ok=True)
        (root / ".gitattributes").write_text(
            ".gitattributes text eol=lf\n"
            "*.json text eol=lf\n"
            "*.md text eol=lf\n"
            "*.py text eol=lf\n"
            "*.sh text eol=lf\n"
            "*.txt text eol=lf\n"
            "VERSION text eol=lf\n",
            encoding="utf-8",
            newline="\n",
        )
        (root / "hermes_factory" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "tests" / "test_guard.py").write_text(
            "def test_guard():\n    assert True\n", encoding="utf-8"
        )
        (root / "run_appliance.py").write_text("# appliance\n", encoding="utf-8")
        (root / "RUN_FACTORY.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (root / "VERSION").write_text("x\n", encoding="utf-8")
        (root / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json").write_text(
            json.dumps({"model_identities": {}, "certifications": {}}), encoding="utf-8"
        )
        report = root / "test_report.json"
        report.write_text(json.dumps({"overall": "PASS"}), encoding="utf-8")
        return root, report

    def test_tests_are_part_of_certified_surface(self):
        with tempfile.TemporaryDirectory() as raw:
            root, _ = self._root(Path(raw))
            manifest = build_manifest(root)
            paths = {row["path"] for row in manifest["files"]}
            self.assertIn("tests/test_guard.py", paths)
            self.assertIn("tests/**/*.py", manifest["certified_surface_globs"])

    def test_eol_policy_is_certified_and_required(self):
        with tempfile.TemporaryDirectory() as raw:
            root, _ = self._root(Path(raw))
            manifest = build_manifest(root)
            paths = {row["path"] for row in manifest["files"]}
            self.assertIn(".gitattributes", paths)
            (root / ".gitattributes").unlink()
            with self.assertRaisesRegex(RuntimeError, "certified_eol_policy_missing"):
                build_manifest(root)

    def test_incomplete_eol_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root, _ = self._root(Path(raw))
            (root / ".gitattributes").write_text("*.py text eol=lf\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(RuntimeError, "certified_eol_policy_incomplete"):
                build_manifest(root)

    def test_test_mutation_after_certification_fails_build_integrity(self):
        with tempfile.TemporaryDirectory() as raw:
            root, report = self._root(Path(raw))
            cert = root / "cert.json"
            certify_build(root, cert, test_report_path=report)
            self.assertEqual(verify_build(root, cert)["result"], "PASS")

            (root / "tests" / "test_guard.py").write_text(
                "def test_guard():\n    assert False\n", encoding="utf-8"
            )
            result = verify_build(root, cert)
            self.assertEqual(result["result"], "FAIL_BLOCKING")
            self.assertTrue(any("tests/test_guard.py" in error for error in result["errors"]))

    def test_new_test_added_after_certification_fails_build_integrity(self):
        with tempfile.TemporaryDirectory() as raw:
            root, report = self._root(Path(raw))
            cert = root / "cert.json"
            certify_build(root, cert, test_report_path=report)
            (root / "tests" / "test_new_guard.py").write_text(
                "def test_new_guard():\n    assert True\n", encoding="utf-8"
            )
            result = verify_build(root, cert)
            self.assertEqual(result["result"], "FAIL_BLOCKING")
            self.assertTrue(any("tests/test_new_guard.py" in error for error in result["errors"]))

    def test_certificate_records_test_surface_glob(self):
        with tempfile.TemporaryDirectory() as raw:
            root, report = self._root(Path(raw))
            cert_path = root / "cert.json"
            cert = certify_build(root, cert_path, test_report_path=report)
            self.assertIn("tests/**/*.py", cert["certified_surface_globs"])
            self.assertEqual(cert["certification_scope"], "OFFLINE_MECHANICAL_BUILD_AND_TEST_SURFACE")


if __name__ == "__main__":
    unittest.main()
