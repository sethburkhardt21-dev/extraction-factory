"""Verify that the exact active code about to run passed the offline frontier preflight."""
from __future__ import annotations
from pathlib import Path
import json
from .readiness import code_manifest, verification_manifest


def require_frontier_preflight(preflight_path: str | Path, root: str | Path) -> dict:
    p=Path(preflight_path); root=Path(root)
    if not p.is_file(): raise RuntimeError(f"frontier preflight report not found: {p}")
    report=json.loads(p.read_text(encoding="utf-8"))
    if report.get("status")!="PASS": raise RuntimeError("frontier preflight is not PASS")
    if report.get("network_extraction_performed") is not False: raise RuntimeError("invalid preflight: network_extraction_performed must be false")
    expected=(report.get("production_code_manifest") or {}).get("sha256")
    current=code_manifest(root)["sha256"]
    if not expected or expected!=current:
        raise RuntimeError(f"active production code changed since preflight: expected={expected} current={current}")
    expected_verification=(report.get("verification_manifest") or {}).get("sha256")
    if expected_verification:
        current_verification=verification_manifest(root)["sha256"]
        if expected_verification!=current_verification:
            raise RuntimeError(f"verification suite changed since preflight: expected={expected_verification} current={current_verification}")
    return report
