from __future__ import annotations
import json
import platform
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable
from .hashing import sha256_file, sha256_json

# This is the certified execution-and-verification surface, not merely runtime
# application code. Tests are intentionally included: a PASS report has no
# authority if the test code that produced it can change without invalidating
# the certificate.
PRODUCTION_GLOBS = [
    ".gitattributes",
    "hermes_factory/**/*.py",
    "providers_ext/**/*.py",
    "stages_ext/**/*.py",
    "benchmarks_ext/**/*.py",
    "validation/**/*.py",
    "tests/**/*.py",
    "run_appliance.py",
    "VERSION",
    "RUN_FACTORY.sh",
    "CURRENT/MODEL_CERTIFICATION_REGISTRY.json",
]


REQUIRED_CHECKOUT_POLICY_LINES = {"* -text"}


def _validate_certified_checkout_policy(root: Path) -> None:
    root = Path(root).resolve()
    # Git checkout policy is part of certification because raw-byte manifests
    # must survive different client autocrlf settings. Extracted/runtime-only
    # roots without repository metadata are validated by their manifest bytes.
    if not (root.parent / ".git").exists():
        return
    policy = root / ".gitattributes"
    if not policy.is_file():
        raise RuntimeError("certified_checkout_policy_missing")
    lines = {
        line.strip()
        for line in policy.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = sorted(REQUIRED_CHECKOUT_POLICY_LINES - lines)
    if missing:
        raise RuntimeError("certified_checkout_policy_incomplete:" + ",".join(missing))



def production_files(root: Path) -> list[Path]:
    root = Path(root)
    found: set[Path] = set()
    for pattern in PRODUCTION_GLOBS:
        for p in root.glob(pattern):
            if p.is_file() and "__pycache__" not in p.parts:
                found.add(p)
    return sorted(found, key=lambda p: str(p.relative_to(root)))


def build_manifest(root: Path) -> Dict[str, Any]:
    root = Path(root)
    _validate_certified_checkout_policy(root)
    files = []
    for p in production_files(root):
        files.append({
            "path": str(p.relative_to(root)).replace("\\", "/"),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    content = {
        "schema_version": "hermes-current-build-manifest-1.3",
        "certified_surface_globs": PRODUCTION_GLOBS,
        # Backward-compatible key retained for readers that display the old name.
        "production_globs": PRODUCTION_GLOBS,
        "files": files,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
    }
    content["production_code_manifest_sha256"] = sha256_json({"files": files})
    return content


def write_current_manifest(root: Path, out: Path) -> Dict[str, Any]:
    manifest = build_manifest(root)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return manifest


def certify_build(root: Path, certificate_path: Path, *, test_report_path: Path, parent_certification_id: str | None = None) -> Dict[str, Any]:
    test_report_path = Path(test_report_path)
    if not test_report_path.exists():
        raise RuntimeError("missing_test_report")
    try:
        report = json.loads(test_report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"test_report_not_json:{exc}")
    if report.get("overall") != "PASS":
        raise RuntimeError("test_report_not_pass")
    current = build_manifest(root)
    cert = {
        "schema_version": "hermes-certified-build-manifest-1.3",
        "certification_id": "CERT-" + uuid.uuid4().hex,
        "parent_certification_id": parent_certification_id,
        "created_at_epoch": time.time(),
        "certification_scope": "OFFLINE_MECHANICAL_BUILD_AND_TEST_SURFACE",
        "semantic_model_certification_included": False,
        "production_code_manifest_sha256": current["production_code_manifest_sha256"],
        "production_files": current["files"],
        "certified_surface_globs": current["certified_surface_globs"],
        "runtime": {
            "python": current["python"],
            "implementation": current["implementation"],
        },
        "test_report_sha256": sha256_file(test_report_path),
        "claim_boundary": (
            "Certifies the exact offline mechanical execution surface, test-suite code, runtime identity, "
            "and PASS report. It does not certify semantic model quality."
        ),
    }
    certificate_path = Path(certificate_path)
    if certificate_path.exists():
        raise FileExistsError("certificate_already_exists; create a new versioned certificate instead of overwriting")
    certificate_path.parent.mkdir(parents=True, exist_ok=True)
    certificate_path.write_text(json.dumps(cert, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return cert


def verify_build(root: Path, certificate_path: Path) -> Dict[str, Any]:
    current = build_manifest(root)
    certificate_path = Path(certificate_path)
    if not certificate_path.exists():
        return {"ok": False, "result": "NOT_RUN", "errors": ["certified_build_manifest_missing"], "current": current}
    cert = json.loads(certificate_path.read_text(encoding="utf-8"))
    errors = []
    if current["production_code_manifest_sha256"] != cert.get("production_code_manifest_sha256"):
        errors.append("production_code_changed_since_certification")
    cert_files = {x["path"]: (x["bytes"], x["sha256"]) for x in cert.get("production_files", [])}
    cur_files = {x["path"]: (x["bytes"], x["sha256"]) for x in current.get("files", [])}
    if cert_files != cur_files:
        missing = sorted(set(cert_files) - set(cur_files))
        added = sorted(set(cur_files) - set(cert_files))
        changed = sorted(k for k in set(cert_files) & set(cur_files) if cert_files[k] != cur_files[k])
        if missing: errors.append("certified_files_missing:" + ",".join(missing))
        if added: errors.append("uncertified_files_added:" + ",".join(added))
        if changed: errors.append("certified_files_changed:" + ",".join(changed))
    return {"ok": not errors, "result": "PASS" if not errors else "FAIL_BLOCKING", "errors": errors,
            "current": current, "certification": cert}
