from __future__ import annotations
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple
from .hashing import sha256_text
from .models import AssertionCandidate, EvidenceFamily


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def deterministic_union(*populations: Iterable[AssertionCandidate]) -> List[AssertionCandidate]:
    """Union candidate populations without semantic voting or destructive merging."""
    seen: set[str] = set()
    out: List[AssertionCandidate] = []
    for population in populations:
        for cand in population:
            if cand.candidate_id in seen:
                continue
            seen.add(cand.candidate_id)
            out.append(cand)
    return sorted(out, key=lambda c: (c.source_unit_id, c.origin_pass, c.candidate_id))


def _family_risk_metadata(members: List[AssertionCandidate]) -> dict:
    work = {str(m.metadata.get("source_risk_work_class")) for m in members if m.metadata.get("source_risk_work_class")}
    source = {str(m.metadata.get("source_risk_source_class")) for m in members if m.metadata.get("source_risk_source_class")}
    unit_types = {str(m.metadata.get("source_unit_type")) for m in members if m.metadata.get("source_unit_type")}
    representations = {
        str(m.metadata.get("source_content_representation"))
        for m in members if m.metadata.get("source_content_representation")
    }
    return {
        "family_rule": "EXACT_NORMALIZED_EVIDENCE_WITHIN_SOURCE_UNIT",
        "source_risk_work_class": next(iter(work)) if len(work) == 1 else ("CONFLICT" if len(work) > 1 else None),
        "source_risk_source_class": next(iter(source)) if len(source) == 1 else ("CONFLICT" if len(source) > 1 else None),
        "source_unit_type": next(iter(unit_types)) if len(unit_types) == 1 else ("CONFLICT" if len(unit_types) > 1 else None),
        "source_content_representation": next(iter(representations)) if len(representations) == 1 else ("CONFLICT" if len(representations) > 1 else None),
        "source_risk_metadata_complete": len(work) == 1 and len(source) == 1,
    }


def build_evidence_families(candidates: Iterable[AssertionCandidate]) -> List[EvidenceFamily]:
    """Build conservative evidence families.

    Candidates are grouped only when they share the exact normalized evidence span
    in the same source unit. This intentionally avoids semantic fuzzy merging.
    Governed source-risk metadata is carried forward when present so W3 families
    cannot later appear locally safe merely because narrower specialist flags are absent.
    """
    buckets: Dict[Tuple[str, str], List[AssertionCandidate]] = defaultdict(list)
    for c in candidates:
        buckets[(c.source_unit_id, _norm(c.evidence))].append(c)
    families: List[EvidenceFamily] = []
    for (unit_id, normalized_evidence), members in sorted(buckets.items()):
        origins = sorted({m.origin_pass for m in members})
        props = sorted({_norm(m.proposition) for m in members})
        disagreements: List[str] = []
        if len(props) > 1:
            disagreements.append("PROPOSITION_VARIANT_ON_SAME_EVIDENCE")
        if "PRIMARY" in origins and "BLIND_RECALL" not in origins:
            disagreements.append("PRIMARY_ONLY")
        if "BLIND_RECALL" in origins and "PRIMARY" not in origins:
            disagreements.append("BLIND_RECALL_ONLY")
        requirements: List[str] = []
        for m in members:
            if m.numeric_values:
                requirements.append("NUMERIC_BINDING")
            if m.qualifiers or m.polarity != "AFFIRMATIVE" or m.certainty != "ASSERTED":
                requirements.append("QUALIFIER_SCOPE")
            if m.relationship_direction:
                requirements.append("RELATIONSHIP_DIRECTION")
            if m.table_binding_state not in ("NOT_APPLICABLE", "SUPPORTED"):
                requirements.append("TABLE_BINDING")
            if m.visual_binding_state not in ("NOT_APPLICABLE", "SUPPORTED"):
                requirements.append("VISUAL_BINDING")
            if m.cross_page_state == "CROSS_PAGE":
                requirements.append("CROSS_PAGE_CONTEXT")
            requirements.extend(m.uncertainty_flags)
        family_id = "FAM-" + sha256_text(unit_id + "|" + normalized_evidence)[:24]
        families.append(EvidenceFamily(
            family_id=family_id,
            source_unit_id=unit_id,
            member_candidate_ids=[m.candidate_id for m in members],
            propositions=[m.proposition for m in members],
            origins=origins,
            evidence_hashes=sorted({m.evidence_sha256 for m in members}),
            disagreement_types=sorted(set(disagreements)),
            specialist_requirements=sorted(set(requirements)),
            metadata=_family_risk_metadata(members),
        ))
    return families
