from __future__ import annotations
import re
from typing import Any, Dict, List
from .base import SemanticProvider
from ..models import WorkerIdentity

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _sentences(text: str) -> List[str]:
    # Fixture-only segmentation. This is intentionally not a production semantic model.
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = _SENTENCE_END.split(text)
    out = []
    for chunk in chunks:
        chunk = chunk.strip()
        if len(chunk) >= 5:
            out.append(chunk)
    return out


class DeterministicFixtureProvider(SemanticProvider):
    """Exercises the full semantic transport with deterministic sentence fixtures.

    It MUST NOT be used as evidence of semantic model quality. Receipts identify it
    as FIXTURE_NOT_EMPIRICAL and readiness logic blocks empirical semantic claims.
    """

    def __init__(self, role: str = "PRIMARY"):
        self.role = role

    def identity(self) -> WorkerIdentity:
        return WorkerIdentity(
            provider="LOCAL_FIXTURE",
            model_alias="deterministic-sentence-fixture",
            underlying_family="FIXTURE",
            observed_version="1.1",
            role=self.role,
            certification_status="FIXTURE_NOT_EMPIRICAL",
        )

    def capabilities(self) -> Dict[str, Any]:
        return {
            "roles": ["PRIMARY", "BLIND_RECALL", "PRECISION_REVIEW", "COLD_AUDIT"],
            "network_required": False,
            "empirical_semantic_model": False,
        }

    def is_empirical_semantic_provider(self) -> bool:
        return False

    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        unit = request["source_unit"]
        role = request.get("task_role", self.role)
        assertions = []
        for i, sentence in enumerate(_sentences(unit["content"])):
            # Blind fixture takes a slightly different deterministic slice solely to
            # exercise disagreement/union mechanics without seeing primary output.
            if role == "BLIND_RECALL" and i % 3 == 1:
                continue
            assertions.append({
                "proposition": sentence,
                "evidence": sentence if sentence in unit["content"] else unit["content"],
                "subject": None,
                "predicate": None,
                "object_value": None,
                "uncertainty_flags": ["FIXTURE_SEMANTIC_OUTPUT_NOT_EMPIRICAL"],
            })
        return {
            "provider_output_schema": "hermes-semantic-provider-1.1",
            "role": role,
            "assertions": assertions,
            "provider_receipt": {
                "empirical_semantic_model": False,
                "fixture": True,
            },
        }
