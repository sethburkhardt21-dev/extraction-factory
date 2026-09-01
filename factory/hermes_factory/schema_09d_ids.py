from __future__ import annotations

import hashlib
from typing import Any


def source_identity_sha256(source_table: str, source_key: Any) -> str:
    """Reproduce Project 09D's candidate source-identity algorithm exactly.

    09D uses UTF-8(source_table) + 0x1f + UTF-8(str(source_key)). The extraction
    factory keeps this separate from its source-grounded stable claim hash: the
    latter describes the extracted claim instance; this hash describes the 09D
    candidate-registry source-table/source-key identity.
    """
    if not isinstance(source_table, str) or not source_table:
        raise ValueError("source_table_must_be_nonempty_text")
    if source_key is None:
        raise ValueError("source_key_must_not_be_null")
    payload = source_table.encode("utf-8") + b"\x1f" + str(source_key).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def candidate_id(source_table: str, source_key: Any) -> str:
    """Return the stable noncanonical 09D candidate ID."""
    return "CAND:" + source_identity_sha256(source_table, source_key)[:32]
