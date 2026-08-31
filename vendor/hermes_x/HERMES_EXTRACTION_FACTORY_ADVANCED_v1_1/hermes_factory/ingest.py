from __future__ import annotations
import re
from pathlib import Path
from typing import Iterable, List, Sequence

from .hashing import sha256_file, sha256_text
from .models import SourceUnit
from .source import write_source_units


def parse_page_spec(spec: str | None, total_pages: int) -> List[int]:
    if not spec:
        return list(range(1, total_pages + 1))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            if start > end:
                raise ValueError(f"page_range_reversed:{part}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    bad = [p for p in pages if p < 1 or p > total_pages]
    if bad:
        raise ValueError(f"page_out_of_range:{bad}")
    return sorted(pages)


def _chunk_exact(text: str, target_chars: int = 1800, max_chars: int = 3200) -> List[str]:
    """Deterministically split extracted page text while preserving exact substrings."""
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        target = min(n, start + target_chars)
        hard = min(n, start + max_chars)
        if hard == n:
            end = n
        else:
            candidates = []
            # Prefer paragraph/newline, then sentence boundary, within a safe window.
            for token in ("\n\n", ".\n", ". ", "\n"):
                pos = text.rfind(token, target, hard)
                if pos != -1:
                    candidates.append(pos + len(token))
            end = max(candidates) if candidates else hard
        if end <= start:
            end = min(n, start + max_chars)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end
    return chunks


def _representation(chunk: str) -> tuple[str, str]:
    stripped = chunk.lstrip()
    upper = stripped[:300].upper()
    if upper.startswith("TABLE ") or re.search(r"\bTABLE\s+\d", upper):
        return "TABLE", "TABLE_TEXT_LAYER"
    if upper.startswith("FIGURE ") or re.search(r"\bFIGURE\s+\d", upper):
        return "FIGURE", "FIGURE_CAPTION_OR_MIXED_TEXT"
    if re.search(r"(?:=|/).*\d", chunk) and len(chunk) < 500:
        return "EQUATION", "EQUATION_OR_SHORT_FORMULA"
    return "TEXT", "TEXT_CHUNK"


def ingest_pdf(pdf_path: Path, output_jsonl: Path, *, page_spec: str | None = None,
               source_id: str | None = None, target_chars: int = 1800, max_chars: int = 3200) -> dict:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError(f"pypdf_required_for_pdf_ingestion:{exc}")
    pdf_path = Path(pdf_path)
    source_sha = sha256_file(pdf_path)
    reader = PdfReader(str(pdf_path))
    pages = parse_page_spec(page_spec, len(reader.pages))
    sid = source_id or ("PDF-" + source_sha[:16])
    svid = sid + "-SHA-" + source_sha[:12]
    units: List[SourceUnit] = []
    for pno in pages:
        text = reader.pages[pno - 1].extract_text() or ""
        for idx, chunk in enumerate(_chunk_exact(text, target_chars=target_chars, max_chars=max_chars), 1):
            rep, unit_type = _representation(chunk)
            uid = f"SU-{source_sha[:10]}-P{pno:04d}-C{idx:03d}"
            units.append(SourceUnit(
                source_unit_id=uid,
                source_id=sid,
                source_version_id=svid,
                source_sha256=source_sha,
                unit_type=unit_type,
                content_representation=rep,
                locator={"pdf_pages": [pno], "chunk_index": idx, "derived_from_text_layer": True},
                content_sha256=sha256_text(chunk),
                content=chunk,
                rights_metadata={
                    "local_extraction_allowed": "UNKNOWN",
                    "text_data_mining_status": "UNKNOWN",
                    "redistribution_status": "UNKNOWN",
                    "rights_basis": "Not adjudicated by deterministic ingestion.",
                },
                process_metadata={
                    "ingestion": "hermes_factory.ingest_pdf/1.1",
                    "semantic_interpretation": False,
                },
            ))
    write_source_units(units, output_jsonl)
    return {
        "source_path": str(pdf_path),
        "source_sha256": source_sha,
        "source_id": sid,
        "source_version_id": svid,
        "pdf_pages_total": len(reader.pages),
        "pdf_pages_selected": pages,
        "source_unit_count": len(units),
        "output_jsonl": str(output_jsonl),
        "content_policy": "deterministic text-layer chunks; figures/tables are only flagged from text cues and are not visually interpreted",
    }
