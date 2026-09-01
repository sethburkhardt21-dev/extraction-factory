from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks_ext.certify_roles import main as certify_main, verify_score_pair
from benchmarks_ext.gold_build import (
    MACHINES_PILOT_SOURCE_SHA256,
    adjudicate_disagreements,
    resolve_gold_identities,
    validate_governed_machines_units,
)
from benchmarks_ext.score_role import (
    build_score_report,
    infer_source_units_path,
    sha256_text,
    validate_scoring_independence,
)
from hermes_factory.models import SourceUnit


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _units() -> tuple[list[SourceUnit], dict[str, str]]:
    rows = []
    expected = {}
    for idx in range(8):
        uid = f"U{idx}"
        content = f"governed-content-{idx}"
        digest = _sha(content)
        expected[uid] = digest
        rows.append(SourceUnit(
            source_unit_id=uid,
            source_id="BOOK-DORSCH-5E",
            source_version_id="BOOK-DORSCH-5E-SHA-379a5d5c7fdf",
            source_sha256=MACHINES_PILOT_SOURCE_SHA256,
            unit_type="PARAGRAPH",
            content_representation="TEXT",
            locator={"pdf_pages": [299]},
            content_sha256=digest,
            content=content,
        ))
    return rows, expected


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in rows), encoding="utf-8")


def _benchmark_fixture(root: Path) -> dict[str, Path]:
    run = root / "RUN"
    source_dir = run / "SOURCE"
    assertion_dir = run / "ASSERTIONS"
    gold = root / "GOLD"
    source_dir.mkdir(parents=True)
    assertion_dir.mkdir(parents=True)
    gold.mkdir(parents=True)

    source_sha = "a" * 64
    units = []
    for idx in (1, 2):
        content = f"Agent {idx} has a measured value of {idx}.0 percent."
        units.append(SourceUnit(
            source_unit_id=f"U{idx}", source_id="S", source_version_id="SV",
            source_sha256=source_sha, unit_type="PARAGRAPH", content_representation="TEXT",
            locator={"pdf_pages": [idx]}, content_sha256=sha256_text(content), content=content,
        ))
    source_path = source_dir / "source_units.jsonl"
    _write_jsonl(source_path, [u.to_dict() for u in units])
    source_raw = source_path.read_text(encoding="utf-8")

    raw_a = []
    raw_b = []
    reference = []
    for unit in units:
        proposition = unit.content
        evidence = unit.content
        raw_a.append({"builder": "A", "backend": "ollama", "model": "gold-a", "source_unit_id": unit.source_unit_id,
                      "proposition": proposition, "evidence": evidence})
        raw_b.append({"builder": "B", "backend": "ollama", "model": "gold-b", "source_unit_id": unit.source_unit_id,
                      "proposition": proposition, "evidence": evidence})
        reference.append({
            "builder": "A", "backend": "ollama", "model": "gold-a", "source_unit_id": unit.source_unit_id,
            "proposition": proposition, "evidence": evidence, "gold_origin": "AGREED_A_B",
            "gold_id": "GOLD-" + sha256_text(unit.source_unit_id + "|" + proposition + "|" + evidence)[:20],
        })
    raw_a_path = gold / "raw_builder_A.jsonl"; _write_jsonl(raw_a_path, raw_a)
    raw_b_path = gold / "raw_builder_B.jsonl"; _write_jsonl(raw_b_path, raw_b)
    adj_path = gold / "adjudication_log.jsonl"; adj_path.write_text("", encoding="utf-8")
    ref_path = gold / "reference_v1.jsonl"; _write_jsonl(ref_path, reference)

    manifest = {
        "benchmark_version": "MACHINES_P0299_P0301_SOURCE_FIRST_v1",
        "gold_label": "MECHANICALLY_CHECKED",
        "source_pdf_sha256": source_sha,
        "source_units_sha256": sha256_text(source_raw),
        "source_unit_count": 2,
        "source_unit_content_sha256": {u.source_unit_id: u.content_sha256 for u in units},
        "builder_a": {"backend": "ollama", "model": "gold-a"},
        "builder_b": {"backend": "ollama", "model": "gold-b"},
        "adjudicator": {"backend": "ollama", "model": "gold-c"},
        "gold_construction_independence_groups": ["GOLD_A", "GOLD_B", "GOLD_C"],
        "gold_construction_models_not_scorable": ["gold-a", "gold-b", "gold-c"],
        "builders_not_scorable": ["gold-a", "gold-b", "gold-c"],
        "raw_builder_a_sha256": sha256_text(raw_a_path.read_text(encoding="utf-8")),
        "raw_builder_b_sha256": sha256_text(raw_b_path.read_text(encoding="utf-8")),
        "adjudication_log_sha256": sha256_text(""),
        "adjudication_complete": True,
        "adjudication_error_count": 0,
        "scoring_reference": "reference_v1.jsonl",
        "reference_v1_sha256": sha256_text(ref_path.read_text(encoding="utf-8")),
        "scoring_reference_sha256": sha256_text(ref_path.read_text(encoding="utf-8")),
    }
    manifest_path = gold / "GOLD_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    registry = {
        "model_identities": {
            "OLLAMA|gold-a": {"underlying_family": "GA", "independence_group": "GOLD_A", "empirical_semantic_model": True},
            "OLLAMA|gold-b": {"underlying_family": "GB", "independence_group": "GOLD_B", "empirical_semantic_model": True},
            "OLLAMA|gold-c": {"underlying_family": "GC", "independence_group": "GOLD_C", "empirical_semantic_model": True},
            "OLLAMA|primary": {"underlying_family": "PRIMARY", "independence_group": "PRIMARY", "empirical_semantic_model": True},
            "OLLAMA|blind": {"underlying_family": "BLIND", "independence_group": "BLIND", "empirical_semantic_model": True},
        },
        "certifications": {}, "role_status": {},
    }
    registry_path = root / "registry.json"
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")

    primary_rows = []
    blind_rows = []
    for idx, unit in enumerate(units, 1):
        base = {
            "source_unit_id": unit.source_unit_id, "source_sha256": source_sha,
            "evidence": unit.content, "evidence_sha256": sha256_text(unit.content), "proposition": unit.content,
        }
        primary_rows.append({**base, "candidate_id": f"P{idx}", "worker_identity": {"provider": "OLLAMA", "model_alias": "primary"}})
        blind_rows.append({**base, "candidate_id": f"B{idx}", "worker_identity": {"provider": "OLLAMA", "model_alias": "blind"}})
    primary_path = assertion_dir / "primary_candidates.jsonl"; _write_jsonl(primary_path, primary_rows)
    blind_path = assertion_dir / "blind_recall_candidates.jsonl"; _write_jsonl(blind_path, blind_rows)

    return {
        "source": source_path, "reference": ref_path, "manifest": manifest_path, "registry": registry_path,
        "primary": primary_path, "blind": blind_path, "raw_a": raw_a_path,
        "primary_score": root / "primary_score.json", "blind_score": root / "blind_score.json",
    }


class GovernedGoldSourceTests(unittest.TestCase):
    def test_exact_content_is_rehashed_not_trusted_from_declared_hash(self):
        rows, expected = _units()
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            validate_governed_machines_units(rows)
            rows[0].content = "tampered-but-declared-hash-left-unchanged"
            with self.assertRaisesRegex(SystemExit, "wrong_content_hash"):
                validate_governed_machines_units(rows)

    def test_declared_hash_must_equal_recomputed_content_hash(self):
        rows, expected = _units(); rows[0].content_sha256 = "0" * 64
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            with self.assertRaisesRegex(SystemExit, "declared_content_hash_mismatch"):
                validate_governed_machines_units(rows)

    def test_pdf_identity_must_match_pinned_machines_source(self):
        rows, expected = _units(); rows[0].source_sha256 = "f" * 64
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            with self.assertRaisesRegex(SystemExit, "gold_source_pdf_identity_mismatch"):
                validate_governed_machines_units(rows)

    def test_missing_or_extra_units_cannot_receive_machines_benchmark_label(self):
        rows, expected = _units()
        with patch("benchmarks_ext.gold_build.EXPECTED_UNIT_HASHES", expected):
            with self.assertRaisesRegex(SystemExit, "gold_source_not_exact_governed_machines_pilot"):
                validate_governed_machines_units(rows[:-1])


class GoldConstructionIdentityTests(unittest.TestCase):
    def test_gold_builders_require_three_empirical_distinct_groups(self):
        registry = {"model_identities": {
            "OLLAMA|a": {"underlying_family": "A1", "independence_group": "A", "empirical_semantic_model": True},
            "OLLAMA|b": {"underlying_family": "B1", "independence_group": "B", "empirical_semantic_model": True},
            "OLLAMA|c": {"underlying_family": "C1", "independence_group": "C", "empirical_semantic_model": True},
        }}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"; path.write_text(json.dumps(registry), encoding="utf-8")
            rows = resolve_gold_identities(path, ["ollama:a", "ollama:b", "ollama:c"])
            self.assertEqual([x["independence_group"] for x in rows], ["A", "B", "C"])
            registry["model_identities"]["OLLAMA|c"]["independence_group"] = "A"; path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "gold_construction_independence_groups_not_distinct"):
                resolve_gold_identities(path, ["ollama:a", "ollama:b", "ollama:c"])

    def test_adjudicator_failure_invalidates_entire_gold_build(self):
        unit = SourceUnit("U", "S", "SV", "a" * 64, "PARAGRAPH", "TEXT", {"pdf_pages": [1]}, _sha("x"), "x")
        row = {"builder": "A", "source_unit_id": "U", "proposition": "x", "evidence": "x"}
        with patch("benchmarks_ext.gold_build.adjudicate", side_effect=RuntimeError("provider timeout")):
            with self.assertRaisesRegex(RuntimeError, "gold_adjudication_failed:U"):
                adjudicate_disagreements([row], {"U": unit}, "ollama", "audit", 10)


class ScoringContaminationTests(unittest.TestCase):
    @staticmethod
    def _registry() -> dict:
        return {"model_identities": {
            "OLLAMA|gold-a": {"underlying_family": "GOLD_A", "independence_group": "QWEN", "empirical_semantic_model": True},
            "OLLAMA|scored-qwen": {"underlying_family": "QWEN_OTHER", "independence_group": "QWEN", "empirical_semantic_model": True},
            "OLLAMA|scored-deepseek": {"underlying_family": "DEEPSEEK", "independence_group": "DEEPSEEK", "empirical_semantic_model": True},
            "ECHO|echo": {"underlying_family": "FIXTURE", "independence_group": "FIXTURE", "empirical_semantic_model": False},
        }}

    @staticmethod
    def _candidate(model: str, provider: str = "OLLAMA") -> list[dict]:
        return [{"candidate_id": "C1", "source_unit_id": "U1", "worker_identity": {"provider": provider, "model_alias": model}, "proposition": "p", "evidence": "e"}]

    @staticmethod
    def _manifest() -> dict:
        return {"gold_construction_independence_groups": ["QWEN", "LLAMA", "MISTRAL"], "gold_construction_models_not_scorable": ["gold-a", "gold-b", "gold-c"]}

    def test_same_family_different_model_alias_is_still_contaminated(self):
        with self.assertRaisesRegex(ValueError, "independence_group_authored_gold:QWEN"):
            validate_scoring_independence(self._candidate("scored-qwen"), self._manifest(), self._registry(), expected_model="scored-qwen", label="scored")

    def test_disjoint_registered_empirical_family_can_be_scored(self):
        identity = validate_scoring_independence(self._candidate("scored-deepseek"), self._manifest(), self._registry(), expected_model="scored-deepseek", label="scored")
        self.assertEqual(identity["independence_group"], "DEEPSEEK")

    def test_missing_gold_family_lineage_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "gold_manifest_missing_construction_independence_groups"):
            validate_scoring_independence(self._candidate("scored-deepseek"), {}, self._registry(), expected_model="scored-deepseek", label="scored")

    def test_mixed_candidate_worker_identities_fail_closed(self):
        rows = self._candidate("scored-deepseek") + self._candidate("scored-qwen")
        with self.assertRaisesRegex(ValueError, "worker_identity_mixed"):
            validate_scoring_independence(rows, self._manifest(), self._registry(), label="scored")

    def test_non_empirical_scored_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "model_not_empirical"):
            validate_scoring_independence(self._candidate("echo", provider="ECHO"), self._manifest(), self._registry(), expected_model="echo", label="scored")


class SourceBoundScoringAndCertificationTests(unittest.TestCase):
    def _reports(self, paths: dict[str, Path], scope: set[str] | None = None) -> tuple[dict, dict]:
        scope = scope or {"U1", "U2"}
        primary = build_score_report(
            candidates_path=paths["primary"], reference_path=paths["reference"], gold_manifest_path=paths["manifest"],
            source_units_path=paths["source"], registry_path=paths["registry"], role="PRIMARY", model="primary", units_in_scope=scope)
        blind = build_score_report(
            candidates_path=paths["blind"], reference_path=paths["reference"], gold_manifest_path=paths["manifest"],
            source_units_path=paths["source"], registry_path=paths["registry"], role="BLIND_RECALL", model="blind", units_in_scope=scope,
            primary_candidates_path=paths["primary"])
        paths["primary_score"].write_text(json.dumps(primary, indent=2, sort_keys=True), encoding="utf-8")
        paths["blind_score"].write_text(json.dumps(blind, indent=2, sort_keys=True), encoding="utf-8")
        return primary, blind

    def test_source_units_are_inferred_from_run_candidate_path(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _benchmark_fixture(Path(td))
            self.assertEqual(infer_source_units_path(paths["primary"]), paths["source"].resolve())

    def test_fabricated_candidate_evidence_is_rejected_not_counted_as_fidelity(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _benchmark_fixture(Path(td))
            rows = [json.loads(x) for x in paths["primary"].read_text().splitlines() if x]
            rows[0]["evidence"] = "fabricated evidence"; rows[0]["evidence_sha256"] = sha256_text(rows[0]["evidence"])
            _write_jsonl(paths["primary"], rows)
            with self.assertRaisesRegex(ValueError, "evidence_not_exact_source_substring"):
                self._reports(paths)

    def test_tampered_gold_raw_artifact_breaks_score(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _benchmark_fixture(Path(td)); paths["raw_a"].write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "gold_artifact_hash_mismatch"):
                self._reports(paths)

    def test_hand_edited_score_report_fails_recomputation(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _benchmark_fixture(Path(td)); self._reports(paths)
            stored = json.loads(paths["primary_score"].read_text(encoding="utf-8"))
            stored["metrics"]["semantic_unit_precision"]["value"] = 1.0 if stored["metrics"]["semantic_unit_precision"]["value"] != 1.0 else 0.5
            paths["primary_score"].write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "score_report_does_not_match_recomputation"):
                verify_score_pair(
                    primary_score_path=paths["primary_score"], blind_score_path=paths["blind_score"],
                    primary_candidates_path=paths["primary"], blind_candidates_path=paths["blind"],
                    reference_path=paths["reference"], gold_manifest_path=paths["manifest"],
                    source_units_path=paths["source"], registry_path=paths["registry"])

    def test_cherry_picked_W2_scope_cannot_be_certified(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _benchmark_fixture(Path(td)); self._reports(paths, {"U1"})
            with self.assertRaisesRegex(ValueError, "certification_scope_must_equal_all_W2_S1_units"):
                verify_score_pair(
                    primary_score_path=paths["primary_score"], blind_score_path=paths["blind_score"],
                    primary_candidates_path=paths["primary"], blind_candidates_path=paths["blind"],
                    reference_path=paths["reference"], gold_manifest_path=paths["manifest"],
                    source_units_path=paths["source"], registry_path=paths["registry"])

    def test_self_describing_scores_are_auto_recomputed_by_certifier(self):
        with tempfile.TemporaryDirectory() as td:
            paths = _benchmark_fixture(Path(td)); self._reports(paths)
            rc = certify_main(["--primary-score", str(paths["primary_score"]), "--blind-score", str(paths["blind_score"]), "--registry", str(paths["registry"])])
            self.assertEqual(rc, 0)

    def test_apply_refuses_unverified_legacy_score_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root / "p.json"; b = root / "b.json"; reg = root / "registry.json"
            base = {"benchmark_version": "MACHINES_P0299_P0301_SOURCE_FIRST_v1", "role": "PRIMARY", "model": "x", "metrics": {}, "scored_identity": {"provider": "OLLAMA"}}
            p.write_text(json.dumps(base), encoding="utf-8"); base["role"] = "BLIND_RECALL"; b.write_text(json.dumps(base), encoding="utf-8"); reg.write_text(json.dumps({"certifications": {}}), encoding="utf-8")
            self.assertEqual(certify_main(["--primary-score", str(p), "--blind-score", str(b), "--registry", str(reg), "--apply"]), 3)


if __name__ == "__main__":
    unittest.main()
