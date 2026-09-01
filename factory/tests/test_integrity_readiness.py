import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes_factory.build_integrity import certify_build, verify_build, build_manifest
from hermes_factory.runtime_lock import write_runtime_lock, verify_runtime_lock
from hermes_factory.readiness import derive_readiness
from hermes_factory.models import Gate
from hermes_factory.bridge_09d import assert_write_blocked, inventory_schema_readonly
from hermes_factory.package import build_offline_package, verify_offline_package


class BuildIntegrityTests(unittest.TestCase):
    def test_certified_build_detects_mutation_and_verify_does_not_recertify(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"hermes_factory").mkdir();(root/"hermes_factory/x.py").write_text("A=1\n");(root/"VERSION").write_text("x\n")
            report=root/"test.json";report.write_text(json.dumps({"overall":"PASS"}))
            cert=root/"cert.json"
            c=certify_build(root,cert,test_report_path=report)
            before=cert.read_bytes()
            self.assertTrue(verify_build(root,cert)["ok"])
            (root/"hermes_factory/x.py").write_text("A=2\n")
            v=verify_build(root,cert)
            self.assertFalse(v["ok"])
            self.assertIn("production_code_changed_since_certification",v["errors"])
            self.assertEqual(before,cert.read_bytes())

    def test_added_production_file_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"hermes_factory").mkdir();(root/"hermes_factory/x.py").write_text("A=1\n");(root/"VERSION").write_text("x\n")
            report=root/"test.json";report.write_text(json.dumps({"overall":"PASS"}));cert=root/"cert.json";certify_build(root,cert,test_report_path=report)
            (root/"hermes_factory/backdoor.py").write_text("def promote(): return 'CERTIFIED'\n")
            v=verify_build(root,cert)
            self.assertFalse(v["ok"]);self.assertTrue(any("uncertified_files_added" in x for x in v["errors"]))

    def test_validation_harness_mutation_invalidates_certification(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"hermes_factory").mkdir();(root/"hermes_factory/x.py").write_text("A=1\n");(root/"VERSION").write_text("x\n")
            (root/"validation").mkdir();harness=root/"validation/owner_real_validation.py";harness.write_text("SAFE=True\n")
            report=root/"test.json";report.write_text(json.dumps({"overall":"PASS"}));cert=root/"cert.json";certify_build(root,cert,test_report_path=report)
            self.assertTrue(verify_build(root,cert)["ok"])
            harness.write_text("SAFE=False\n")
            v=verify_build(root,cert)
            self.assertFalse(v["ok"])
            self.assertTrue(any("certified_files_changed:validation/owner_real_validation.py" in x for x in v["errors"]))


class RuntimeLockTests(unittest.TestCase):
    def test_runtime_lock_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"lock.json";write_runtime_lock(p);self.assertTrue(verify_runtime_lock(p)["ok"])

    def test_runtime_lock_mutation_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"lock.json";d=write_runtime_lock(p);d["python_version"]="0.0.0";p.write_text(json.dumps(d));self.assertFalse(verify_runtime_lock(p)["ok"])


class ReadinessTests(unittest.TestCase):
    def test_not_run_cannot_be_ready(self):
        r=derive_readiness([Gate("SOURCE","PASS"),Gate("VISUAL","NOT_RUN")])
        self.assertFalse(r["frontier_review_ready"]);self.assertEqual(r["status"],"NOT_READY")

    def test_external_provider_block_yields_ready_for_provider(self):
        r=derive_readiness([Gate("SOURCE","PASS"),Gate("SEMANTIC_PROVIDER_CERTIFICATION","BLOCKED_EXTERNAL")])
        self.assertEqual(r["status"],"READY_FOR_PROVIDER")

    def test_bounded_review_queue_can_be_frontier_review_ready(self):
        r=derive_readiness([Gate("SOURCE","PASS"),Gate("VISUAL","FAIL_REVIEW_REQUIRED",bounded_queue="review/visual.jsonl")])
        self.assertTrue(r["frontier_review_ready"])
        self.assertEqual(r["status"],"FRONTIER_REVIEW_READY")

    def test_unbounded_review_failure_blocks(self):
        r=derive_readiness([Gate("SOURCE","PASS"),Gate("INDEPENDENCE","FAIL_REVIEW_REQUIRED")])
        self.assertFalse(r["frontier_review_ready"])


class ReadOnly09DTests(unittest.TestCase):
    def test_read_only_bridge_blocks_write(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"d.sqlite";c=sqlite3.connect(p);c.execute("create table x(id integer)");c.commit();c.close()
            inv=inventory_schema_readonly(p)
            self.assertIn("x",inv["tables"])
            self.assertTrue(assert_write_blocked(p))


class PackageTests(unittest.TestCase):
    def _run_dir(self, parent: Path, status: str = "NOT_READY") -> Path:
        root=parent/"RUN";root.mkdir();(root/"a.txt").write_text("abc")
        (root/"VALIDATION").mkdir();(root/"VALIDATION/readiness.json").write_text(json.dumps({"status": status}))
        return root

    def test_package_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root=self._run_dir(Path(td));z=Path(td)/"x.zip";r=build_offline_package(root,z,package_status="NOT_READY")
            self.assertTrue(r["verification"]["ok"])
            self.assertTrue(verify_offline_package(z)["ok"])

    def test_package_status_cannot_override_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            root=self._run_dir(Path(td), "NOT_READY")
            with self.assertRaisesRegex(RuntimeError, "package_status_must_match_readiness"):
                build_offline_package(root, Path(td)/"x.zip", package_status="FRONTIER_REVIEW_READY")


if __name__ == "__main__": unittest.main()
