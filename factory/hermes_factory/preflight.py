from __future__ import annotations
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from .build_integrity import verify_build, write_current_manifest
from .runtime_lock import verify_runtime_lock


def run_preflight(root: Path, *, run_tests: bool = True) -> Dict[str, Any]:
    root = Path(root)
    checks: List[Dict[str, Any]] = []
    write_current_manifest(root, root / "CURRENT" / "CURRENT_BUILD_MANIFEST.json")
    build = verify_build(root, root / "CURRENT" / "CERTIFIED_BUILD_MANIFEST.json")
    checks.append({"name": "MANIFEST_INTEGRITY", "result": build["result"], "detail": build.get("errors", [])})
    runtime = verify_runtime_lock(root / "CURRENT" / "RUNTIME_LOCK.json")
    checks.append({"name": "RUNTIME_LOCK", "result": runtime["result"], "detail": runtime.get("errors", [])})
    registry = root / "CURRENT" / "MODEL_CERTIFICATION_REGISTRY.json"
    checks.append({"name": "MODEL_CERTIFICATION_REGISTRY_PRESENT", "result": "PASS" if registry.exists() else "FAIL_BLOCKING", "detail": str(registry)})
    if run_tests:
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"],
                              cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        combined = (proc.stdout + "\n" + proc.stderr).strip()
        checks.append({"name": "ADVANCED_TEST_SUITE", "result": "PASS" if proc.returncode == 0 else "FAIL_BLOCKING",
                       "detail": combined[-12000:]})
    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL_BLOCKING"
    report = {
        "schema_version": "hermes-preflight-1.1",
        "generated_at_epoch": time.time(),
        "overall": overall,
        "checks": checks,
        "claim_boundary": "Preflight verifies this exact build/runtime/mechanical test state. It does not imply semantic model certification.",
    }
    (root / "CURRENT").mkdir(exist_ok=True)
    (root / "CURRENT" / "PREFLIGHT.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    lines = ["HERMES EXTRACTION FACTORY ADVANCED v1.1 PREFLIGHT", f"OVERALL: {overall}", ""]
    for c in checks:
        lines.append(f"{c['result']}: {c['name']}")
        if c["detail"]:
            detail = c["detail"] if isinstance(c["detail"], str) else json.dumps(c["detail"], ensure_ascii=False)
            lines.append("  " + detail.replace("\n", "\n  "))
    (root / "CURRENT" / "PREFLIGHT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return report
