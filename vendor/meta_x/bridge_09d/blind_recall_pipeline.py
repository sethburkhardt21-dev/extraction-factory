"""Hash-bound persistence for the independent blind-recall coverage lane.

The recall lane never sees primary assertions while extracting. Primary assertions are
introduced only after recall extraction, at deterministic reconciliation time.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .assertion_engine import EngineConfig
from .blind_recall import RecallProposalProvider
from .assertions import validate_assertion, validate_source_unit
from .blind_recall import run_blind_recall, reconcile_primary_recall, RECALL_SCHEMA_VERSION
from frontier_core.readiness import code_manifest

RECALL_PIPELINE_MANIFEST_VERSION = "frontier-blind-recall-pipeline-1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{lineno}: row must be object")
        rows.append(obj)
    return rows


def atomic_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_json(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(obj), f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _validate_primary(assertions: Sequence[Mapping[str, Any]], units: Mapping[str, Mapping[str, Any]]) -> None:
    errors = []
    for assertion in assertions:
        unit = units.get(str(assertion.get("source_unit_id") or ""))
        if unit is None:
            errors.append(f"{assertion.get('assertion_id')}: source unit absent")
            continue
        errors.extend(f"{assertion.get('assertion_id')}: {e}" for e in validate_assertion(assertion, source_unit=unit))
        if assertion.get("verification_status") != "NOT_VERIFIED":
            errors.append(f"{assertion.get('assertion_id')}: primary assertion must remain NOT_VERIFIED")
    if errors:
        raise ValueError("invalid primary assertions for recall reconciliation: " + "; ".join(errors[:30]))


def run_blind_recall_pipeline(
    *,
    source_units_path: Path,
    primary_assertions_path: Path,
    output_dir: Path,
    provider: RecallProposalProvider,
    config: EngineConfig,
) -> Dict[str, Any]:
    source_units_path = Path(source_units_path)
    primary_assertions_path = Path(primary_assertions_path)
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"blind recall output must be empty: {output_dir}")
    if not source_units_path.is_file():
        raise FileNotFoundError(source_units_path)
    if not primary_assertions_path.is_file():
        raise FileNotFoundError(primary_assertions_path)

    estate_root = Path(__file__).resolve().parents[1]
    current_code_sha = code_manifest(estate_root)["sha256"]
    if config.code_manifest_sha256 != current_code_sha:
        raise RuntimeError(
            f"blind recall config code hash does not match running estate: config={config.code_manifest_sha256} current={current_code_sha}"
        )

    source_units = read_jsonl(source_units_path)
    unit_map = {str(u.get("source_unit_id") or ""): u for u in source_units}
    unit_errors = []
    for unit in source_units:
        unit_errors.extend(f"{unit.get('source_unit_id')}: {e}" for e in validate_source_unit(unit))
    if unit_errors:
        raise ValueError("invalid source units for blind recall: " + "; ".join(unit_errors[:30]))

    primary_assertions = read_jsonl(primary_assertions_path)
    _validate_primary(primary_assertions, unit_map)

    # Critical independence boundary: primary assertions are not passed to the provider/extractor.
    recall_result = run_blind_recall(source_units, provider=provider, config=config)
    recall_assertions = list(recall_result.get("assertions") or [])
    for assertion in recall_assertions:
        if assertion.get("verification_status") != "NOT_VERIFIED":
            raise RuntimeError("blind recall assertion escaped NOT_VERIFIED state")
        if assertion.get("subject_candidate_id") is not None or assertion.get("object_candidate_id") is not None:
            raise RuntimeError("blind recall assertion attempted candidate resolution")

    reconciliation = reconcile_primary_recall(primary_assertions, recall_assertions)
    if reconciliation.get("automatic_merge_allowed") is not False or reconciliation.get("automatic_repair_allowed") is not False:
        raise RuntimeError("blind recall reconciliation must never auto-merge or auto-repair")

    output_dir.mkdir(parents=True, exist_ok=True)
    recall_path = output_dir / "recall_assertions.jsonl"
    quarantine_path = output_dir / "quarantine.jsonl"
    reconciliation_path = output_dir / "reconciliation.jsonl"
    atomic_jsonl(recall_path, recall_assertions)
    atomic_jsonl(quarantine_path, list(recall_result.get("quarantine") or []))
    atomic_jsonl(reconciliation_path, list(reconciliation.get("rows") or []))

    metrics = {
        **dict(recall_result.get("metrics") or {}),
        "primary_assertions": len(primary_assertions),
        "recall_assertions": len(recall_assertions),
        "reconciliation_counts": dict(reconciliation.get("counts") or {}),
        "recall_only_candidates": int((reconciliation.get("counts") or {}).get("RECALL_ONLY_CANDIDATE", 0)),
        "same_evidence_semantic_disagreements": int((reconciliation.get("counts") or {}).get("SAME_EVIDENCE_SEMANTIC_DISAGREEMENT", 0)),
    }
    manifest = {
        "blind_recall_pipeline_manifest_version": RECALL_PIPELINE_MANIFEST_VERSION,
        "blind_recall_schema_version": RECALL_SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": recall_result.get("status"),
        "source_units_path": str(source_units_path),
        "source_units_sha256": sha256_file(source_units_path),
        "primary_assertions_path": str(primary_assertions_path),
        "primary_assertions_sha256": sha256_file(primary_assertions_path),
        "recall_assertions_path": "recall_assertions.jsonl",
        "recall_assertions_sha256": sha256_file(recall_path),
        "quarantine_path": "quarantine.jsonl",
        "quarantine_sha256": sha256_file(quarantine_path),
        "reconciliation_path": "reconciliation.jsonl",
        "reconciliation_sha256": sha256_file(reconciliation_path),
        "independent_of_primary_extractor": True,
        "primary_assertions_visible_during_recall": False,
        "recall_outputs_are_unverified": True,
        "primary_mutation_performed": False,
        "automatic_merge_allowed": False,
        "automatic_repair_allowed": False,
        "candidate_resolution_performed": False,
        "09d_comparison_performed": False,
        "canonical_authority": False,
        "automatic_selection_allowed": False,
        "generation_eligible": False,
        "public_eligible": False,
        "recall_provenance": recall_result.get("extractor_provenance"),
        "metrics": metrics,
    }
    atomic_json(output_dir / "manifest.json", manifest)
    return {
        **recall_result,
        "reconciliation": reconciliation,
        "pipeline_manifest": manifest,
        "metrics": metrics,
    }
