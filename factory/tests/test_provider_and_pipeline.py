import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes_factory.providers.command import JSONCommandProvider
from hermes_factory.providers.fixture import DeterministicFixtureProvider
from hermes_factory.hashing import sha256_text, sha256_file
from hermes_factory.models import SourceUnit
from hermes_factory.source import write_source_units
from hermes_factory.controller import run_factory


class CommandProviderTests(unittest.TestCase):
    def test_json_stdin_stdout_provider(self):
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/"provider.py"
            script.write_text(textwrap.dedent('''
                import sys,json
                req=json.load(sys.stdin)
                content=req['source_unit']['content']
                print(json.dumps({'assertions':[{'proposition':content,'evidence':content}]}))
            '''))
            p=JSONCommandProvider([os.sys.executable,str(script)],provider="LOCAL",model_alias="test",underlying_family="TEST",role="PRIMARY",network_required=False)
            out=p.execute({"source_unit":{"content":"abc"}})
            self.assertEqual(out["assertions"][0]["evidence"],"abc")


class PipelineTests(unittest.TestCase):
    def test_one_unit_fixture_pipeline_outputs_package_and_blocks_semantic_certification(self):
        # This test isolates fixture pipeline/readiness semantics from the repository's
        # intentionally immutable build certificate. Production-code changes are
        # supposed to invalidate that certificate until an explicit post-test
        # certification step, so coupling this test to the current repo certificate
        # creates a circular "tests cannot pass until certification" dependency.
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            content="Pressure may increase to 20 mmHg when heat is applied."
            source=td/"source.txt"; source.write_text(content)
            source_sha=sha256_file(source)
            u=SourceUnit(source_unit_id="U",source_id="S",source_version_id="V",source_sha256=source_sha,unit_type="PARAGRAPH",content_representation="TEXT",locator={"pdf_pages":[1]},content_sha256=sha256_text(content),content=content)
            sup=td/"units.jsonl";write_source_units([u],sup)
            project=Path(__file__).resolve().parents[1]
            with patch("hermes_factory.controller_v14.verify_build", return_value={"result":"PASS","errors":[]}), \
                 patch("hermes_factory.controller_v14.verify_runtime_lock", return_value={"result":"PASS","errors":[]}):
                result=run_factory(project_root=project,source_units_path=sup,primary_provider=DeterministicFixtureProvider("PRIMARY"),blind_provider=DeterministicFixtureProvider("BLIND_RECALL"),output_root=td/"out",mode="OFFLINE_FIXTURE",source_pdf=source,source_expected_sha256=source_sha)
            self.assertTrue(Path(result["package"]["path"]).exists())
            self.assertEqual(result["readiness"]["status"],"READY_FOR_PROVIDER")
            blockers={x["gate"] for x in result["readiness"]["blockers"]}
            self.assertIn("SEMANTIC_PROVIDER_CERTIFICATION",blockers)
            self.assertIn("COLD_AUDIT_POLICY",blockers)


if __name__ == "__main__": unittest.main()

class NetworkPolicyTests(unittest.TestCase):
    def test_local_only_rejects_network_provider(self):
        from hermes_factory.network_policy import enforce_provider_network_policy
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/"provider.py";script.write_text("import sys,json; print(json.dumps({'assertions':[]}))")
            p=JSONCommandProvider([os.sys.executable,str(script)],provider="REMOTE",model_alias="x",underlying_family="X",network_required=True)
            with self.assertRaises(RuntimeError):
                enforce_provider_network_policy("LOCAL_ONLY",p)

    def test_cloud_mode_allows_network_provider(self):
        from hermes_factory.network_policy import enforce_provider_network_policy
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/"provider.py";script.write_text("import sys,json; print(json.dumps({'assertions':[]}))")
            p=JSONCommandProvider([os.sys.executable,str(script)],provider="REMOTE",model_alias="x",underlying_family="X",network_required=True)
            enforce_provider_network_policy("CLOUD_MODEL",p)
