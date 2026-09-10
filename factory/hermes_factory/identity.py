from __future__ import annotations

import re
from typing import Any, Dict

from .hashing import sha256_json


def normalize_identity_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip().lower()
    return text or None


def stable_candidate_identities(candidate: Dict[str, Any]) -> tuple[str, str]:
    """Return stable witness and claim fingerprints independent of run/model IDs.

    The witness fingerprint is source/locator/evidence identity. The claim
    fingerprint adds source-grounded structured claim fields. When subject or
    predicate is absent, normalized proposition text is used as a conservative
    fallback rather than pretending two unstructured paraphrases are identical.
    """
    witness = {
        "source_sha256": candidate.get("source_sha256"),
        "source_id": candidate.get("source_id"),
        "source_version_id": candidate.get("source_version_id"),
        "source_unit_id": candidate.get("source_unit_id"),
        "locator": candidate.get("locator") or {},
        "evidence_sha256": candidate.get("evidence_sha256"),
    }
    witness_sha = sha256_json(witness)
    structured = {
        "subject": normalize_identity_text(candidate.get("subject")),
        "predicate": normalize_identity_text(candidate.get("predicate")),
        "object_value": normalize_identity_text(candidate.get("object_value")),
        "polarity": normalize_identity_text(candidate.get("polarity")),
        "certainty": normalize_identity_text(candidate.get("certainty")),
        "conditionality": normalize_identity_text(candidate.get("conditionality")),
        "temporality": normalize_identity_text(candidate.get("temporality")),
        "comparison": normalize_identity_text(candidate.get("comparison")),
        "relationship_direction": normalize_identity_text(candidate.get("relationship_direction")),
        "qualifiers": sorted(
            x for x in (normalize_identity_text(v) for v in (candidate.get("qualifiers") or [])) if x
        ),
        "numeric_values": candidate.get("numeric_values") or [],
    }
    if not structured["subject"] or not structured["predicate"]:
        structured["proposition_fallback"] = normalize_identity_text(candidate.get("proposition"))
    claim_sha = sha256_json({"witness_sha256": witness_sha, "claim": structured})
    return witness_sha, claim_sha
