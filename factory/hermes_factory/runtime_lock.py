from __future__ import annotations
import json
import platform
import importlib.metadata
from pathlib import Path


def current_runtime() -> dict:
    deps = {}
    try:
        deps["pypdf"] = importlib.metadata.version("pypdf")
    except importlib.metadata.PackageNotFoundError:
        deps["pypdf"] = "NOT_INSTALLED"
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "runtime_contract": "hermes-factory-1.1",
        "external_python_dependencies": deps,
    }


def write_runtime_lock(path: Path) -> dict:
    data = current_runtime()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return data


def verify_runtime_lock(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"ok": False, "result": "NOT_RUN", "errors": ["runtime_lock_missing"], "current": current_runtime()}
    expected = json.loads(path.read_text(encoding="utf-8"))
    current = current_runtime()
    errors = []
    for key in ("python_version", "python_implementation", "runtime_contract", "external_python_dependencies"):
        if expected.get(key) != current.get(key):
            errors.append(f"runtime_mismatch:{key}:expected={expected.get(key)}:actual={current.get(key)}")
    return {"ok": not errors, "result": "PASS" if not errors else "FAIL_BLOCKING", "errors": errors,
            "expected": expected, "current": current}
