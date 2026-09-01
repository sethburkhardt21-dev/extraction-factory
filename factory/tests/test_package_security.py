from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from hermes_factory.package import build_offline_package, verify_offline_package


class PackageSecurityTests(unittest.TestCase):
    def _run_dir(self, parent: Path) -> Path:
        root = parent / "RUN"
        (root / "VALIDATION").mkdir(parents=True)
        (root / "VALIDATION" / "readiness.json").write_text(json.dumps({"status": "NOT_READY"}), encoding="utf-8")
        (root / "payload.txt").write_text("trusted", encoding="utf-8")
        return root

    def test_content_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            root = self._run_dir(parent)
            good = parent / "good.zip"
            build_offline_package(root, good, package_status="NOT_READY")

            unpack = parent / "unpack"
            with zipfile.ZipFile(good) as z:
                z.extractall(unpack)
            bundle = next(unpack.iterdir())
            (bundle / "payload.txt").write_text("tampered", encoding="utf-8")
            bad = parent / "tampered.zip"
            with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for p in bundle.rglob("*"):
                    if p.is_file():
                        z.write(p, Path(bundle.name) / p.relative_to(bundle))
            result = verify_offline_package(bad)
            self.assertFalse(result["ok"])
            self.assertTrue(any("package_" in e for e in result["errors"]))

    def test_path_traversal_member_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "evil.zip"
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("RUN/PACKAGE_MANIFEST.json", json.dumps({
                    "schema_version": "hermes-offline-package-manifest-1.2",
                    "package_status": "NOT_READY",
                    "files": [],
                }))
                z.writestr("../escape.txt", "no")
            result = verify_offline_package(zpath)
            self.assertFalse(result["ok"])
            self.assertTrue(any(e.startswith("unsafe_archive_member:") for e in result["errors"]))

    def test_duplicate_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "dup.zip"
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("RUN/PACKAGE_MANIFEST.json", json.dumps({
                    "schema_version": "hermes-offline-package-manifest-1.2",
                    "package_status": "NOT_READY",
                    "files": [],
                }))
                z.writestr("RUN/x.txt", "a")
                z.writestr("RUN/x.txt", "b")
            result = verify_offline_package(zpath)
            self.assertFalse(result["ok"])
            self.assertTrue(any(e.startswith("duplicate_archive_member:") for e in result["errors"]))

    def test_top_level_extra_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "extra.zip"
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("RUN/PACKAGE_MANIFEST.json", json.dumps({
                    "schema_version": "hermes-offline-package-manifest-1.2",
                    "package_status": "NOT_READY",
                    "files": [],
                }))
                z.writestr("extra.txt", "no")
            result = verify_offline_package(zpath)
            self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
