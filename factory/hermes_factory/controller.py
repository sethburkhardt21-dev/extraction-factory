"""Compatibility surface for the governed extraction controller.

The active implementation lives in :mod:`hermes_factory.controller_v14` so the
v1.4 schema/failure hardening can be audited as a coherent unit while existing
imports of ``hermes_factory.controller`` remain stable.
"""
from .controller_v14 import (  # noqa: F401
    _effective_concurrency,
    _execute_semantic_work,
    _provider_is_local,
    _provider_telemetry,
    _resolved_schedule,
    _work_id,
    run_factory,
)

__all__ = [
    "run_factory",
    "_work_id",
    "_provider_is_local",
    "_resolved_schedule",
    "_effective_concurrency",
    "_provider_telemetry",
    "_execute_semantic_work",
]
