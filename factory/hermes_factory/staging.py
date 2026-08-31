from __future__ import annotations
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict
from .hashing import canonical_json, sha256_bytes, sha256_file, sha256_json

RESERVED = {"ARTIFACT_MANIFEST.json", "COMPLETION_RECEIPT.json"}


def _write_value(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    elif isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def stage_artifact(staging_root: Path, *, work_id: str, run_id: str, files: Dict[str, Any]) -> Dict[str, Any]:
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    final = staging_root / run_id
    if final.exists():
        raise FileExistsError(f"staging_run_exists:{run_id}")
    tmp = staging_root / (run_id + ".tmp-" + next(tempfile._get_candidate_names()))
    tmp.mkdir(parents=True)
    try:
        entries = []
        for rel, value in sorted(files.items()):
            if Path(rel).name in RESERVED or Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise ValueError(f"illegal_staging_path:{rel}")
            path = tmp / rel
            _write_value(path, value)
            entries.append({"path": str(rel).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        manifest = {
            "schema_version": "hermes-artifact-manifest-1.1",
            "work_id": work_id,
            "run_id": run_id,
            "files": entries,
        }
        manifest_sha = sha256_json(manifest)
        (tmp / "ARTIFACT_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        completion = {
            "schema_version": "hermes-completion-receipt-1.1",
            "work_id": work_id,
            "run_id": run_id,
            "artifact_manifest_sha256": manifest_sha,
            "complete": True,
        }
        (tmp / "COMPLETION_RECEIPT.json").write_text(json.dumps(completion, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, final)
        return {"path": str(final), "manifest": manifest, "manifest_sha256": manifest_sha, "completion": completion}
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def verify_staged_artifact(path: Path) -> Dict[str, Any]:
    path = Path(path)
    errors: list[str] = []
    mp = path / "ARTIFACT_MANIFEST.json"
    cp = path / "COMPLETION_RECEIPT.json"
    if not mp.exists():
        errors.append("missing_artifact_manifest")
    if not cp.exists():
        errors.append("missing_completion_receipt")
    if errors:
        return {"ok": False, "errors": errors}
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        completion = json.loads(cp.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": [f"invalid_control_json:{exc}"]}
    manifest_sha = sha256_json(manifest)
    if completion.get("artifact_manifest_sha256") != manifest_sha:
        errors.append("completion_manifest_hash_mismatch")
    if completion.get("complete") is not True:
        errors.append("completion_not_true")
    declared = {x["path"] for x in manifest.get("files", [])}
    actual = {
        str(p.relative_to(path)).replace("\\", "/") for p in path.rglob("*")
        if p.is_file() and p.name not in RESERVED
    }
    if declared != actual:
        errors.append(f"declared_actual_file_set_mismatch:{sorted(declared ^ actual)}")
    for entry in manifest.get("files", []):
        p = path / entry["path"]
        if not p.exists():
            errors.append(f"missing_declared_file:{entry['path']}")
            continue
        if p.stat().st_size != entry["bytes"]:
            errors.append(f"size_mismatch:{entry['path']}")
        if sha256_file(p) != entry["sha256"]:
            errors.append(f"hash_mismatch:{entry['path']}")
    return {"ok": not errors, "errors": errors, "manifest": manifest, "manifest_sha256": manifest_sha,
            "completion": completion}
