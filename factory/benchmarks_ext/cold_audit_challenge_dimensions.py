"""Deterministic adversarial challenge generation for COLD_AUDIT certification.

This module reuses the factory's literal cue vocabulary so the benchmark tests the
same semantic dimensions that runtime cold audit is instructed to judge. It does
not create clinical truth; it creates bounded, source-first negative controls from
already verified gold assertions.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from hermes_factory.hashing import sha256_text
from hermes_factory.literal import NUM_RE, QUALIFIER_PATTERNS, REL_PATTERNS

DIM_SUPPORTED = "SUPPORTED"
DIM_UNSUPPORTED_ADDITION = "UNSUPPORTED_ADDITION"
DIM_NUMERIC = "NUMERIC"
DIM_NEGATION = "NEGATION"
DIM_QUALIFIER = "QUALIFIER"
DIM_RELATIONSHIP_DIRECTION = "RELATIONSHIP_DIRECTION"

NEGATIVE_SUFFIXES = (
    "and this establishes an exceptionless rule for every patient",
    "and this proves the statement applies universally without exception",
)

QUALIFIER_STRENGTHEN = (
    (re.compile(r"\b(?:may|might|can|could)\b", re.I), "must"),
    (re.compile(r"\b(?:usually|often|commonly|sometimes|rarely)\b", re.I), "always"),
    (re.compile(r"\bshould\b", re.I), "must"),
)

DIRECTION_SWAPS = (
    (re.compile(r"\bincreases\b", re.I), "decreases"),
    (re.compile(r"\bincrease\b", re.I), "decrease"),
    (re.compile(r"\bincreased\b", re.I), "decreased"),
    (re.compile(r"\braises\b", re.I), "lowers"),
    (re.compile(r"\braise\b", re.I), "lower"),
    (re.compile(r"\braised\b", re.I), "lowered"),
    (re.compile(r"\brises\b", re.I), "falls"),
    (re.compile(r"\brise\b", re.I), "fall"),
    (re.compile(r"\bdecreases\b", re.I), "increases"),
    (re.compile(r"\bdecrease\b", re.I), "increase"),
    (re.compile(r"\bdecreased\b", re.I), "increased"),
    (re.compile(r"\blowers\b", re.I), "raises"),
    (re.compile(r"\blower\b", re.I), "raise"),
    (re.compile(r"\blowered\b", re.I), "raised"),
    (re.compile(r"\bfalls\b", re.I), "rises"),
    (re.compile(r"\bfall\b", re.I), "rise"),
    (re.compile(r"\breduces\b", re.I), "increases"),
    (re.compile(r"\breduce\b", re.I), "increase"),
    (re.compile(r"\breduced\b", re.I), "increased"),
)


def _challenge_id(kind: str, uid: str, proposition: str, evidence: str) -> str:
    return "COLD-" + sha256_text("|".join([kind, uid, proposition, evidence]))[:24]


def _absent(text: str, source: str) -> bool:
    return text.strip().lower() not in (source or "").lower()


def _numeric_negative(proposition: str, evidence: str, unit_content: str) -> tuple[str, str] | None:
    match = NUM_RE.search(proposition or "")
    if not match:
        return None
    raw_value = str(match.group("value") or "").strip()
    scalar = re.search(r"[+-]?\d+(?:\.\d+)?", raw_value)
    if scalar is None:
        return None
    raw = scalar.group(0)
    try:
        value = float(raw)
    except ValueError:
        return None
    value_start = match.start("value") + scalar.start()
    value_end = match.start("value") + scalar.end()
    for delta in (1.0, 2.0, 10.0):
        changed = value + delta
        replacement = str(int(changed)) if changed.is_integer() else f"{changed:.6f}".rstrip("0").rstrip(".")
        if replacement == raw:
            continue
        mutated = proposition[:value_start] + replacement + proposition[value_end:]
        if mutated == proposition or not _absent(mutated, unit_content):
            continue
        return mutated, "NUMERIC_VALUE_CHANGED"
    return None


def _unsupported_addition(proposition: str, unit_content: str) -> tuple[str, str]:
    for suffix in NEGATIVE_SUFFIXES:
        base = (proposition or "").rstrip().rstrip(".")
        mutated = f"{base}; {suffix}."
        if _absent(mutated, unit_content):
            return mutated, "UNSUPPORTED_UNIVERSAL_ADDITION"
    raise ValueError("unable_to_construct_absent_negative_suffix")


def _negation_flip(proposition: str, unit_content: str) -> tuple[str, str] | None:
    if QUALIFIER_PATTERNS["NEGATION"].search(proposition or ""):
        return None
    base = (proposition or "").strip().rstrip(".")
    if not base:
        return None
    mutated = f"It is not true that {base}."
    return (mutated, "NEGATION_FLIPPED") if _absent(mutated, unit_content) else None


def _qualifier_strengthen(proposition: str, unit_content: str) -> tuple[str, str] | None:
    for pattern, replacement in QUALIFIER_STRENGTHEN:
        match = pattern.search(proposition or "")
        if not match:
            continue
        mutated = proposition[:match.start()] + replacement + proposition[match.end():]
        if mutated != proposition and _absent(mutated, unit_content):
            return mutated, "QUALIFIER_STRENGTHENED"
    return None


def _direction_reverse(proposition: str, unit_content: str) -> tuple[str, str] | None:
    if not any(pattern.search(proposition or "") for _, pattern in REL_PATTERNS):
        return None
    for pattern, replacement in DIRECTION_SWAPS:
        match = pattern.search(proposition or "")
        if not match:
            continue
        mutated = proposition[:match.start()] + replacement + proposition[match.end():]
        if mutated != proposition and _absent(mutated, unit_content):
            return mutated, "RELATIONSHIP_DIRECTION_REVERSED"
    return None


def _append_negative(challenges: list[dict], *, uid: str, evidence: str, mutation: tuple[str, str] | None,
                     dimension: str) -> None:
    if mutation is None:
        return
    proposition, kind = mutation
    challenges.append({
        "challenge_id": _challenge_id(kind, uid, proposition, evidence),
        "source_unit_id": uid,
        "proposition": proposition,
        "evidence": evidence,
        "expected_supported": False,
        "mutation": kind,
        "dimension": dimension,
    })


def build_dimension_challenges(gold: list[dict], source_by_id: dict[str, Any]) -> list[dict]:
    if not gold:
        raise ValueError("cold_audit_gold_empty")
    challenges: list[dict] = []
    for row in gold:
        uid = str(row.get("source_unit_id") or "")
        unit = source_by_id.get(uid)
        if unit is None:
            raise ValueError(f"cold_audit_unknown_source_unit:{uid}")
        proposition = str(row.get("proposition") or "").strip()
        evidence = str(row.get("evidence") or "")
        if not proposition or not evidence or evidence not in unit.content:
            raise ValueError(f"cold_audit_gold_row_not_source_bound:{uid}")
        challenges.append({
            "challenge_id": _challenge_id("SUPPORTED", uid, proposition, evidence),
            "source_unit_id": uid,
            "proposition": proposition,
            "evidence": evidence,
            "expected_supported": True,
            "mutation": "NONE_SOURCE_FIRST_POSITIVE",
            "dimension": DIM_SUPPORTED,
        })
        _append_negative(
            challenges, uid=uid, evidence=evidence,
            mutation=_unsupported_addition(proposition, unit.content),
            dimension=DIM_UNSUPPORTED_ADDITION,
        )
        _append_negative(
            challenges, uid=uid, evidence=evidence,
            mutation=_negation_flip(proposition, unit.content),
            dimension=DIM_NEGATION,
        )
        _append_negative(
            challenges, uid=uid, evidence=evidence,
            mutation=_numeric_negative(proposition, evidence, unit.content),
            dimension=DIM_NUMERIC,
        )
        _append_negative(
            challenges, uid=uid, evidence=evidence,
            mutation=_qualifier_strengthen(proposition, unit.content),
            dimension=DIM_QUALIFIER,
        )
        _append_negative(
            challenges, uid=uid, evidence=evidence,
            mutation=_direction_reverse(proposition, unit.content),
            dimension=DIM_RELATIONSHIP_DIRECTION,
        )
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in challenges:
        cid = row["challenge_id"]
        if cid in seen:
            continue
        seen.add(cid)
        deduped.append(row)
    return deduped


def applicable_dimensions(gold: list[dict]) -> set[str]:
    dims = {DIM_SUPPORTED, DIM_UNSUPPORTED_ADDITION, DIM_NEGATION}
    for row in gold:
        proposition = str(row.get("proposition") or "")
        if NUM_RE.search(proposition):
            dims.add(DIM_NUMERIC)
        if any(pattern.search(proposition) for key, pattern in QUALIFIER_PATTERNS.items() if key != "NEGATION"):
            dims.add(DIM_QUALIFIER)
        if any(pattern.search(proposition) for _, pattern in REL_PATTERNS):
            dims.add(DIM_RELATIONSHIP_DIRECTION)
    return dims


def coverage_summary(challenges: list[dict], results: list[dict], required_dimensions: set[str]) -> dict:
    result_by_id = {str(r.get("challenge_id") or ""): r for r in results}
    counts = Counter(str(c.get("dimension") or "UNKNOWN") for c in challenges)
    correct = Counter()
    for challenge in challenges:
        result = result_by_id.get(str(challenge.get("challenge_id") or ""), {})
        if result.get("correct") is True:
            correct[str(challenge.get("dimension") or "UNKNOWN")] += 1
    covered = {d for d, count in counts.items() if count > 0}
    missing = sorted(required_dimensions - covered)
    per_dimension = {
        d: {
            "challenge_count": counts.get(d, 0),
            "correct_count": correct.get(d, 0),
            "accuracy": (correct.get(d, 0) / counts[d]) if counts.get(d, 0) else None,
        }
        for d in sorted(covered | required_dimensions)
    }
    return {
        "required_dimensions": sorted(required_dimensions),
        "covered_dimensions": sorted(covered),
        "missing_required_dimensions": missing,
        "all_required_dimensions_covered": not missing,
        "per_dimension": per_dimension,
    }
