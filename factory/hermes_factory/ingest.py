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

MACHINES_PILOT_SOURCE_SHA256 = "379a5d5c7fdfd1ecdea3db063bef143c94c7db792ec5497bc33b5abe176ae197"
MACHINES_PILOT_PAGE_BREAK = "\n<PDF_PAGE_BREAK 300->301>\n"
# Offset-only reconstruction recipe. No textbook-derived unit bytes are bundled.
# Every reconstructed unit is hash-checked against the original governed pilot.
MACHINES_PILOT_UNIT_SPECS = [
    {"source_unit_id":"SU-DORSCH-P0299-VAPORPRESSURE","pages":[299],"segments":[(299,480,1661)],"unit_type":"PARAGRAPH","content_representation":"TEXT","locator":{"pdf_pages":[299],"heading":"Physics > Vapor Pressure"},"content_sha256":"1e05a3db793673dcc457174da309a192e8c1a2e98e59cad6a14292359423954a"},
    {"source_unit_id":"SU-DORSCH-P0299-BOILING","pages":[299],"segments":[(299,1661,2052)],"unit_type":"PARAGRAPH","content_representation":"TEXT","locator":{"pdf_pages":[299],"heading":"Boiling Point"},"content_sha256":"38f645b80b29d136e2ed2d695d8f5fbd8efd07735bff9b01d90fa66e95ff1d52"},
    {"source_unit_id":"SU-DORSCH-P0300-FIG6_1-CAPTION","pages":[300],"segments":[(300,0,556)],"unit_type":"FIGURE_CAPTION","content_representation":"FIGURE","locator":{"pdf_pages":[300],"figure":"Figure 6.1"},"content_sha256":"9968fd6a723d66d4e6d3840c953cb144f479c876ac4e645a4943b952cda674cf"},
    {"source_unit_id":"SU-DORSCH-P0300-PARTIALPRESSURE","pages":[300],"segments":[(300,556,1271)],"unit_type":"PARAGRAPH","content_representation":"TEXT","locator":{"pdf_pages":[300],"heading":"Gas Concentration > Partial Pressure"},"content_sha256":"71451f23cea84f3656fedaee39a414b79e9c04b6d0111c7b45deaa327ef63657"},
    {"source_unit_id":"SU-DORSCH-P0300_0301-TABLE6_1","pages":[300,301],"segments":[(300,1271,1740),(301,0,207)],"joiner":MACHINES_PILOT_PAGE_BREAK,"unit_type":"TABLE","content_representation":"TABLE","locator":{"pdf_pages":[300,301],"table":"TABLE 6.1 Properties of Common Anesthetic Agents","cross_page":True},"content_sha256":"ae95b47f7c945b00e151dc7184b6f2b15fb806ba5eafc679d772b68b34df6f18"},
    {"source_unit_id":"SU-DORSCH-P0301-VOLUMESPERCENT","pages":[301],"segments":[(301,207,1128)],"unit_type":"PARAGRAPH","content_representation":"TEXT","locator":{"pdf_pages":[301],"heading":"Volumes Percent"},"content_sha256":"f79e7e20ef882e589bf0e164361f8f954ddf24d83a5aaabb8deb247b9930084c"},
    {"source_unit_id":"SU-DORSCH-P0301-EQUATION-PARTIAL","pages":[301],"segments":[(301,708,757)],"unit_type":"EQUATION","content_representation":"EQUATION","locator":{"pdf_pages":[301],"heading":"Volumes Percent"},"content_sha256":"8ba19f5ee9a8ecc5aa8c6483d9e9e97f194d65d0910113835b825c7104f47335"},
    {"source_unit_id":"SU-DORSCH-P0301-HEATVAP","pages":[301],"segments":[(301,1128,2453)],"unit_type":"PARAGRAPH","content_representation":"TEXT","locator":{"pdf_pages":[301],"heading":"Heat of Vaporization"},"content_sha256":"23fb86393c94380963b00e8704f4dc7c9e08cddbec619de781eee2da609e7373"},
]


def reconstruct_machines_pilot(pdf_path: Path, output_jsonl: Path) -> dict:
    """Rebuild the exact governed 8-unit Machines pilot from owner-supplied PDF.

    The repository carries only page/character offsets and expected hashes, not
    textbook-derived source-unit content. If PDF extraction changes under a
    different parser/runtime, hash validation fails closed instead of silently
    creating a different benchmark.
    """
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError(f"pypdf_required_for_machines_pilot_reconstruction:{exc}")
    pdf_path = Path(pdf_path)
    source_sha = sha256_file(pdf_path)
    if source_sha != MACHINES_PILOT_SOURCE_SHA256:
        raise ValueError(f"machines_source_sha256_mismatch:expected={MACHINES_PILOT_SOURCE_SHA256}:actual={source_sha}")
    reader = PdfReader(str(pdf_path))
    page_text = {p: (reader.pages[p-1].extract_text() or "") for p in (299,300,301)}
    units: List[SourceUnit] = []
    for spec in MACHINES_PILOT_UNIT_SPECS:
        parts = []
        for page_no, start, end in spec["segments"]:
            text = page_text[page_no]
            if end > len(text):
                raise ValueError(f"machines_pilot_offset_out_of_range:{spec['source_unit_id']}:{page_no}:{start}:{end}:{len(text)}")
            parts.append(text[start:end])
        content = spec.get("joiner", "").join(parts)
        actual_hash = sha256_text(content)
        if actual_hash != spec["content_sha256"]:
            raise ValueError(
                f"machines_pilot_unit_hash_mismatch:{spec['source_unit_id']}:expected={spec['content_sha256']}:actual={actual_hash}"
            )
        units.append(SourceUnit(
            source_unit_id=spec["source_unit_id"], source_id="BOOK-DORSCH-5E",
            source_version_id="BOOK-DORSCH-5E-SHA-379a5d5c7fdf", source_sha256=source_sha,
            unit_type=spec["unit_type"], content_representation=spec["content_representation"],
            locator=spec["locator"], content_sha256=actual_hash, content=content,
            rights_metadata={
                "local_extraction_allowed":"OWNER_SUPPLIED_LOCAL_SOURCE",
                "redistribution_status":"SOURCE_BYTES_NOT_BUNDLED",
                "rights_basis":"Reconstructed locally from owner-supplied hash-pinned source.",
            },
            process_metadata={
                "ingestion":"hermes_factory.reconstruct_machines_pilot/1.2",
                "semantic_interpretation":False,
                "offset_recipe_hash_checked":True,
            },
        ))
    write_source_units(units, output_jsonl)
    return {
        "source_path":str(pdf_path), "source_sha256":source_sha, "pdf_pages_total":len(reader.pages),
        "pdf_pages_selected":[299,300,301], "source_unit_count":len(units),
        "output_jsonl":str(output_jsonl), "exact_governed_pilot_reconstructed":True,
        "unit_hashes_verified":True, "source_bytes_bundled":False,
    }
