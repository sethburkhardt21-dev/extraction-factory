from __future__ import annotations
import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict
from .hashing import sha256_file

MANIFEST_SCHEMA = "hermes-offline-package-manifest-1.2"


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
    return {"schema_version": MANIFEST_SCHEMA, "files": files}


def _validate_archive_members(z: zipfile.ZipFile) -> tuple[list[str], str | None]:
    """Reject ambiguous or unsafe archive topology before extraction."""
    errors: list[str] = []
    seen: set[str] = set()
    roots: set[str] = set()
    for info in z.infolist():
        raw = info.filename.replace("\\", "/")
        p = PurePosixPath(raw)
        if not raw or raw.startswith("/") or p.is_absolute() or ".." in p.parts:
            errors.append(f"unsafe_archive_member:{raw}")
            continue
        if raw in seen:
            errors.append(f"duplicate_archive_member:{raw}")
        seen.add(raw)
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            errors.append(f"symlink_archive_member:{raw}")
        if p.parts:
            roots.add(p.parts[0])
            if len(p.parts) == 1 and not info.is_dir():
                errors.append(f"top_level_file_outside_package_root:{raw}")
    if len(roots) != 1:
        errors.append(f"package_root_count_invalid:{sorted(roots)}")
        return errors, None
    return errors, next(iter(roots))


def _validate_manifest_shape(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        errors.append(f"package_manifest_schema_invalid:{manifest.get('schema_version')}")
    if not isinstance(manifest.get("package_status"), str) or not manifest.get("package_status"):
        errors.append("package_status_missing")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        return errors + ["package_manifest_files_not_list"]
    paths: list[str] = []
    for idx, entry in enumerate(rows):
        if not isinstance(entry, dict):
            errors.append(f"package_manifest_entry_not_object:{idx}")
            continue
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel:
            errors.append(f"package_manifest_path_invalid:{idx}")
            continue
        pp = PurePosixPath(rel.replace("\\", "/"))
        if rel.startswith("/") or pp.is_absolute() or ".." in pp.parts:
            errors.append(f"package_manifest_path_unsafe:{rel}")
        paths.append(rel)
        if not isinstance(entry.get("bytes"), int) or entry.get("bytes", -1) < 0:
            errors.append(f"package_manifest_size_invalid:{rel}")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            errors.append(f"package_manifest_hash_invalid:{rel}")
    if len(paths) != len(set(paths)):
        errors.append("package_manifest_duplicate_paths")
    return errors


def build_offline_package(run_dir: Path, zip_path: Path, *, package_status: str) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    zip_path = Path(zip_path)
    readiness_path = run_dir / "VALIDATION" / "readiness.json"
    if not readiness_path.exists():
        raise RuntimeError("package_requires_readiness_json")
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    derived_status = readiness.get("status")
    if package_status != derived_status:
        raise RuntimeError(f"package_status_must_match_readiness:{package_status}!={derived_status}")

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        bundle = Path(td) / run_dir.name
        shutil.copytree(run_dir, bundle)
        manifest = _manifest_for_dir(bundle)
        manifest["package_status"] = package_status
        (bundle / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        tmpzip = zip_path.with_suffix(zip_path.suffix + ".tmp")
        if tmpzip.exists():
            tmpzip.unlink()
        with zipfile.ZipFile(tmpzip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(bundle.rglob("*")):
                if p.is_file():
                    z.write(p, Path(bundle.name) / p.relative_to(bundle))
        with zipfile.ZipFile(tmpzip) as z:
            member_errors, _ = _validate_archive_members(z)
            bad = z.testzip()
            if bad:
                member_errors.append(f"zip_crc_failure:{bad}")
            if member_errors:
                tmpzip.unlink(missing_ok=True)
                raise RuntimeError(f"package_archive_validation_failed:{member_errors}")
        tmpzip.replace(zip_path)

    verification = verify_offline_package(zip_path)
    if not verification["ok"]:
        raise RuntimeError(f"package_verification_failed:{verification['errors']}")
    return {"path": str(zip_path), "sha256": sha256_file(zip_path), "verification": verification}


def verify_offline_package(zip_path: Path) -> Dict[str, Any]:
    zip_path = Path(zip_path)
    errors: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(zip_path) as z:
                member_errors, root_name = _validate_archive_members(z)
                errors.extend(member_errors)
                bad = z.testzip()
                if bad:
                    errors.append(f"zip_crc_failure:{bad}")
                if errors or root_name is None:
                    return {"ok": False, "errors": errors, "zip_sha256": sha256_file(zip_path)}
                z.extractall(td)

            top = list(Path(td).iterdir())
            if len(top) != 1 or not top[0].is_dir() or top[0].name != root_name:
                return {"ok": False, "errors": errors + ["package_root_topology_invalid"], "zip_sha256": sha256_file(zip_path)}
            root = top[0]
            mp = root / "PACKAGE_MANIFEST.json"
            if not mp.exists():
                return {"ok": False, "errors": errors + ["package_manifest_missing"], "zip_sha256": sha256_file(zip_path)}
            try:
                manifest = json.loads(mp.read_text(encoding="utf-8"))
            except Exception as exc:
                return {"ok": False, "errors": errors + [f"package_manifest_invalid_json:{type(exc).__name__}"], "zip_sha256": sha256_file(zip_path)}
            if not isinstance(manifest, dict):
                return {"ok": False, "errors": errors + ["package_manifest_not_object"], "zip_sha256": sha256_file(zip_path)}
            errors.extend(_validate_manifest_shape(manifest))

            entries = manifest.get("files") if isinstance(manifest.get("files"), list) else []
            declared = {x["path"]: x for x in entries if isinstance(x, dict) and isinstance(x.get("path"), str)}
            actual = {
                str(p.relative_to(root)).replace("\\", "/"): p
                for p in root.rglob("*") if p.is_file() and p.name != "PACKAGE_MANIFEST.json"
            }
            if set(declared) != set(actual):
                errors.append(f"package_file_set_mismatch:{sorted(set(declared) ^ set(actual))}")
            for rel, entry in declared.items():
                p = actual.get(rel)
                if not p:
                    continue
                if p.stat().st_size != entry.get("bytes"):
                    errors.append(f"package_size_mismatch:{rel}")
                if sha256_file(p) != entry.get("sha256"):
                    errors.append(f"package_hash_mismatch:{rel}")

            readiness_path = root / "VALIDATION" / "readiness.json"
            if not readiness_path.exists():
                errors.append("packaged_readiness_missing")
            else:
                try:
                    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
                    if manifest.get("package_status") != readiness.get("status"):
                        errors.append(
                            f"package_status_readiness_mismatch:{manifest.get('package_status')}!={readiness.get('status')}"
                        )
                except Exception as exc:
                    errors.append(f"packaged_readiness_invalid:{type(exc).__name__}")
    except (zipfile.BadZipFile, OSError) as exc:
        errors.append(f"package_unreadable:{type(exc).__name__}:{exc}")

    return {"ok": not errors, "errors": errors, "zip_sha256": sha256_file(zip_path)}
