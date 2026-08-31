from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable, List
from .hashing import sha256_text
from .models import SourceUnit


def load_source_units(path: Path) -> List[SourceUnit]:
    path = Path(path)
    units: List[SourceUnit] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        unit = SourceUnit.from_dict(raw)
        errors = validate_source_unit(unit)
        if errors:
            raise ValueError(f"invalid source unit line {line_no}: {errors}")
        units.append(unit)
    ids = [u.source_unit_id for u in units]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_source_unit_id")
    return units


def validate_source_unit(unit: SourceUnit) -> List[str]:
    errors: List[str] = []
    if not unit.source_unit_id:
        errors.append("missing_source_unit_id")
    if not unit.source_sha256:
        errors.append("missing_source_sha256")
    if not unit.content:
        errors.append("missing_content")
    if sha256_text(unit.content) != unit.content_sha256:
        errors.append("content_sha256_mismatch")
    if not unit.content_representation:
        errors.append("missing_content_representation")
    return errors


def write_source_units(units: Iterable[SourceUnit], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for unit in units:
            f.write(json.dumps(unit.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
