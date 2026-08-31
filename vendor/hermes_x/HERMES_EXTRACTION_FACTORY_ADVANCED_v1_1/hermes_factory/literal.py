from __future__ import annotations
import re
from typing import Any, Dict, List
from .models import SourceUnit

NUM_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<value>[<>≤≥~≈]?\s*[+-]?\d+(?:\.\d+)?(?:\s*(?:-|–|—|to)\s*[+-]?\d+(?:\.\d+)?)?)"
    r"\s*(?P<unit>%|percent|mm\s*Hg|mmHg|torr|cm\s*H2O|cmH2O|°?C|ยฐC|mL(?:/min(?:ute)?)?|mL|L/min(?:ute)?|L|cal/g|cal/mL|g/mL|seconds?|minutes?|hours?|years?|bpm)?",
    re.I,
)

QUALIFIER_PATTERNS = {
    "NEGATION": re.compile(r"\b(?:not|no|neither|nor|without|never)\b", re.I),
    "EXCEPTION": re.compile(r"\b(?:except|unless|excluding|apart from)\b", re.I),
    "MODAL_MAY": re.compile(r"\b(?:may|might|can|could)\b", re.I),
    "RECOMMENDATION": re.compile(r"\b(?:should|must|recommended|required)\b", re.I),
    "FREQUENCY": re.compile(r"\b(?:usually|often|commonly|rarely|sometimes|always)\b", re.I),
    "CONDITIONAL": re.compile(r"\b(?:if|when|whenever|provided that)\b", re.I),
    "LIMITER_ONLY": re.compile(r"\bonly\b", re.I),
    "COMPARISON": re.compile(r"\b(?:more|less|greater|lower|higher|increase|decrease|rise|fall|compared|than)\b", re.I),
    "TEMPORAL": re.compile(r"\b(?:before|after|during|while|until|then)\b", re.I),
}

REL_PATTERNS = [
    ("INCREASES", re.compile(r"\b(?:increase[sd]?|raise[sd]?|rise[sd]?)\b", re.I)),
    ("DECREASES", re.compile(r"\b(?:decrease[sd]?|lower[sd]?|fall[sd]?|reduce[sd]?)\b", re.I)),
    ("DEPENDS_ON", re.compile(r"\bdepends?\s+(?:only\s+)?on\b", re.I)),
    ("UNAFFECTED_BY", re.compile(r"\b(?:unaffected\s+by|not\s+affected\s+by)\b", re.I)),
    ("EQUALS", re.compile(r"\b(?:equal(?:s| to)?|is the sum of)\b", re.I)),
    ("CAUSES", re.compile(r"\b(?:causes?|results? in|leads? to)\b", re.I)),
    ("RELATED_TO", re.compile(r"\b(?:related to|associated with)\b", re.I)),
]


def numeric_inventory(unit: SourceUnit) -> List[Dict[str, Any]]:
    out = []
    for m in NUM_RE.finditer(unit.content):
        raw = m.group(0).strip()
        value = m.group("value").strip()
        unit_text = (m.group("unit") or "").strip()
        start, end = m.span()
        context = unit.content[max(0, start - 90): min(len(unit.content), end + 90)]
        out.append({
            "source_unit_id": unit.source_unit_id,
            "raw": raw,
            "value_literal": value,
            "unit_literal": unit_text or None,
            "char_start": start,
            "char_end": end,
            "context": context,
            "binding_state": "UNBOUND_LITERAL",
        })
    return out


def qualifier_inventory(unit: SourceUnit) -> List[Dict[str, Any]]:
    out = []
    for kind, pattern in QUALIFIER_PATTERNS.items():
        for m in pattern.finditer(unit.content):
            start, end = m.span()
            out.append({
                "source_unit_id": unit.source_unit_id,
                "qualifier_type": kind,
                "literal": m.group(0),
                "char_start": start,
                "char_end": end,
                "context": unit.content[max(0, start - 100): min(len(unit.content), end + 100)],
                "scope_state": "UNBOUND_LITERAL",
            })
    return sorted(out, key=lambda x: (x["char_start"], x["qualifier_type"]))


def relationship_inventory(unit: SourceUnit) -> List[Dict[str, Any]]:
    out = []
    for kind, pattern in REL_PATTERNS:
        for m in pattern.finditer(unit.content):
            start, end = m.span()
            out.append({
                "source_unit_id": unit.source_unit_id,
                "relationship_type": kind,
                "literal": m.group(0),
                "char_start": start,
                "char_end": end,
                "context": unit.content[max(0, start - 120): min(len(unit.content), end + 120)],
                "direction_state": "UNBOUND_LITERAL",
            })
    return sorted(out, key=lambda x: x["char_start"])
