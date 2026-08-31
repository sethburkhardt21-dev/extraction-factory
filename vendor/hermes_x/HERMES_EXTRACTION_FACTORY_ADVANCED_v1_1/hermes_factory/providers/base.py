from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict
from ..models import WorkerIdentity


class SemanticProvider(ABC):
    """Synchronous semantic provider contract used by the deterministic controller.

    Providers may wrap local models, cloud APIs, subagents, or fixtures. They do
    not receive ledger/database authority and return staged semantic output only.
    """

    @abstractmethod
    def identity(self) -> WorkerIdentity:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def is_empirical_semantic_provider(self) -> bool:
        return True
