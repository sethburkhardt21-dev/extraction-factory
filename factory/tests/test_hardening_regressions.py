from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes_factory.controller import run_factory
from hermes_factory.hashing import sha256_file, sha256_text
from hermes_factory.models import Gate, SourceUnit, WorkerIdentity
from hermes_factory.providers.base import SemanticProvider
from hermes_factory.readiness import derive_readiness
from hermes_factory.source import write_source_units
from stages_ext.compare_09d import build_index, classify


class CountingProvider(SemanticProvider):
    def __init__(self, role): self.calls=0; self.role=role
    def identity(self): return WorkerIdentity("TEST","m-"+self.role,"F-"+self.role,"1",self.role,"UNBENCHMARKED")
    def capabilities(self): return {"network_required":False}
    def execute(self, request): self.calls += 1; return {"assertions":[]}


class PredispatchTests(unittest.TestCase):
    def test_build_failure_stops_before_any_provider_call(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); source=td/"source.txt"; source.write_text("abc",encoding="utf-8")
            sha=sha256_file(source)
            unit=SourceUnit("U","S","V",sha,"PARAGRAPH","TEXT",{"pdf_pages":[1]},sha256_text("abc"),"abc")
            units=td/"units.jsonl"; write_source_units([unit],units)
            primary=CountingProvider("PRIMARY"); blind=CountingProvider("BLIND_RECALL")
            with patch("hermes_factory.controller.verify_build",return_value={"result":"FAIL_BLOCKING","errors":["changed"]}), \
                 patch("hermes_factory.controller.verify_runtime_lock",return_value={"result":"PASS","errors":[]}):
                with self.assertRaisesRegex(RuntimeError,"predispatch_gate_failure"):
                    run_factory(project_root=Path(__file__).resolve().parents[1],source_units_path=units,
                                primary_provider=primary,blind_provider=blind,output_root=td/"out",
                                source_pdf=source,source_expected_sha256=sha,mode="EXTERNAL_COMMAND",execution_mode="LOCAL_ONLY")
            self.assertEqual(primary.calls,0); self.assertEqual(blind.calls,0)


class ReadinessTests(unittest.TestCase):
    def test_hard_failure_dominates_external_blocker(self):
        r=derive_readiness([Gate("RUNTIME_LOCK","FAIL_BLOCKING"),Gate("SEMANTIC_PROVIDER_CERTIFICATION","BLOCKED_EXTERNAL")])
        self.assertEqual(r["status"],"NOT_READY")


class ComparatorSafetyTests(unittest.TestCase):
    def test_partial_pressure_does_not_contradict_partial_laryngectomy(self):
        carrier=[{"carrier_candidate_id":"R1","subject_entity_id":"E1","predicate_code":"procedure.partial_laryngectomy",
                  "fact_family":"procedure","value_text":"Partial laryngectomy may reduce airway caliber",
                  "subject_tokens":{"partial","laryngectomy"},"predicate_tokens":{"partial","laryngectomy"},
                  "value_tokens":{"partial","laryngectomy","reduce","airway","caliber"},
                  "tokens":{"partial","laryngectomy","reduce","airway","caliber","procedure"},"numbers":set(),"negated":False}]
        c={"candidate_id":"C","source_unit_id":"U","origin_pass":"PRIMARY",
           "proposition":"Partial pressure is not affected by total pressure.","subject":"partial pressure",
           "predicate":"is not affected by","polarity":"NEGATIVE"}
        self.assertNotEqual(classify(c,carrier,build_index(carrier))["state"],"CONTRADICTION")

    def test_mac_value_does_not_contradict_mac_reduction(self):
        carrier=[{"carrier_candidate_id":"R1","subject_entity_id":"DES","predicate_code":"mac_reduction",
                  "fact_family":"drug","value_text":"50% MAC reduction","subject_tokens":{"desflurane"},
                  "predicate_tokens":{"mac","reduction"},"value_tokens":{"mac","reduction"},
                  "tokens":{"desflurane","mac","reduction"},"numbers":{("50","%")},"negated":False}]
        c={"candidate_id":"C","source_unit_id":"U","origin_pass":"PRIMARY",
           "proposition":"Desflurane MAC is 6.4%.","subject":"Desflurane","predicate":"MAC is","polarity":"AFFIRMATIVE"}
        self.assertNotEqual(classify(c,carrier,build_index(carrier))["state"],"CONTRADICTION")


if __name__ == "__main__": unittest.main()
