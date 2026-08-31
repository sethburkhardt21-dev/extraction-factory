from __future__ import annotations
import re
from typing import Dict
from .models import SourceUnit


def classify_source_unit(unit: SourceUnit) -> Dict[str, str | list[str]]:
    triggers: list[str] = []
    work_class = "W2"
    source_class = "S1"
    priority = "P2"
    rep = unit.content_representation.upper()
    pages = unit.locator.get("pdf_pages", [])
    if rep in {"TABLE", "FIGURE", "IMAGE_REGION", "MIXED_LAYOUT"}:
        source_class = "S3"
        work_class = "W3"
        priority = "P1"
        triggers.append("COMPLEX_REPRESENTATION")
    if len(pages) > 1 or unit.locator.get("cross_page"):
        source_class = "S3"
        work_class = "W3"
        priority = "P1"
        triggers.append("CROSS_PAGE")
    if re.search(r"\d", unit.content):
        triggers.append("NUMERIC_PRESENT")
    if re.search(r"\b(?:not|no|except|unless|only|may|might|should|if|when)\b", unit.content, re.I):
        triggers.append("QUALIFIER_PRESENT")
    if rep == "EQUATION":
        work_class = "W3"
        priority = "P1"
        triggers.append("EQUATION")
    return {"work_class": work_class, "source_class": source_class, "priority": priority, "triggers": triggers}
