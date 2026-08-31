from __future__ import annotations
import json
import subprocess
import sys
import time
from pathlib import Path


def run_tests(root: Path) -> dict:
    root = Path(root)
    start = time.time()
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"],
                          cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=240)
    text = (proc.stdout + "\n" + proc.stderr).strip()
    report = {
        "schema_version": "hermes-test-report-1.1",
        "overall": "PASS" if proc.returncode == 0 else "FAIL",
        "returncode": proc.returncode,
        "duration_seconds": round(time.time() - start, 3),
        "command": [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"],
        "output": text,
    }
    (root / "CURRENT").mkdir(exist_ok=True)
    (root / "CURRENT" / "TEST_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md = ["# Hermes Advanced v1.1 Test Report", "", f"- Overall: **{report['overall']}**", f"- Return code: `{proc.returncode}`", f"- Duration: `{report['duration_seconds']}` seconds", "", "```text", text, "```", ""]
    (root / "CURRENT" / "TEST_REPORT.md").write_text("\n".join(md), encoding="utf-8")
    return report
