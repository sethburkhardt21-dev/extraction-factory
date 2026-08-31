from __future__ import annotations
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict
from .hashing import sha256_file


def _manifest_for_dir(root: Path) -> Dict[str, Any]:
    files = []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or p.name == "PACKAGE_MANIFEST.json":
            continue
        files.append({
            "path": str(p.relative_to(root)).replace("\\", "/"),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    return {"schema_version": "hermes-offline-package-manifest-1.1", "files": files}


def build_offline_package(run_dir: Path, zip_path: Path, *, package_status: str) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        bundle = Path(td) / run_dir.name
        shutil.copytree(run_dir, bundle)
        manifest = _manifest_for_dir(bundle)
        manifest["package_status"] = package_status
        (bundle / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        tmpzip = zip_path.with_suffix(zip_path.suffix + ".tmp")
        if tmpzip.exists(): tmpzip.unlink()
        with zipfile.ZipFile(tmpzip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(bundle.rglob("*")):
                if p.is_file():
                    z.write(p, Path(bundle.name) / p.relative_to(bundle))
        with zipfile.ZipFile(tmpzip) as z:
            bad = z.testzip()
            if bad:
                tmpzip.unlink(missing_ok=True)
                raise RuntimeError(f"zip_crc_failure:{bad}")
        tmpzip.replace(zip_path)
    verification = verify_offline_package(zip_path)
    if not verification["ok"]:
        raise RuntimeError(f"package_verification_failed:{verification['errors']}")
    return {"path": str(zip_path), "sha256": sha256_file(zip_path), "verification": verification}


def verify_offline_package(zip_path: Path) -> Dict[str, Any]:
    zip_path = Path(zip_path)
    errors = []
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                errors.append(f"zip_crc_failure:{bad}")
            z.extractall(td)
        roots = [p for p in Path(td).iterdir() if p.is_dir()]
        if len(roots) != 1:
            return {"ok": False, "errors": errors + ["package_root_count_invalid"]}
        root = roots[0]
        mp = root / "PACKAGE_MANIFEST.json"
        if not mp.exists():
            return {"ok": False, "errors": errors + ["package_manifest_missing"]}
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        declared = {x["path"]: x for x in manifest.get("files", [])}
        actual = {str(p.relative_to(root)).replace("\\", "/"): p for p in root.rglob("*") if p.is_file() and p.name != "PACKAGE_MANIFEST.json"}
        if set(declared) != set(actual):
            errors.append(f"package_file_set_mismatch:{sorted(set(declared)^set(actual))}")
        for rel, entry in declared.items():
            p = actual.get(rel)
            if not p: continue
            if p.stat().st_size != entry["bytes"]:
                errors.append(f"package_size_mismatch:{rel}")
            if sha256_file(p) != entry["sha256"]:
                errors.append(f"package_hash_mismatch:{rel}")
    return {"ok": not errors, "errors": errors, "zip_sha256": sha256_file(zip_path)}
