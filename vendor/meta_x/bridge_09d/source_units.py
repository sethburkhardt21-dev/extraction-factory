from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import requests

from bridge_09d.assertions import build_source_unit

SEGMENTER_SCHEMA_VERSION = "frontier-source-unit-segmenter-1.1"
FULLTEXT_ARTIFACT_SCHEMA_VERSION = "frontier-fulltext-artifact-1.0"
RIGHTS_SCHEMA_VERSION = "frontier-rights-decision-1.0"

PMC_OAI_BASE = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
APPROVED_FULLTEXT_HOSTS = {
    "pmc.ncbi.nlm.nih.gov",
    "www.biorxiv.org",
    "www.medrxiv.org",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload); fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _canonical_json_path(parts: Iterable[Any]) -> str:
    out = "$"
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            s = str(part)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s): out += "." + s
            else: out += "[" + json.dumps(s, ensure_ascii=False) + "]"
    return out


def _element_paths(root: ET.Element) -> Dict[int, str]:
    paths: Dict[int, str] = {}

    def walk(elem: ET.Element, path: str) -> None:
        paths[id(elem)] = path
        counts: Dict[str, int] = {}
        for child in list(elem):
            name = _local(child.tag)
            counts[name] = counts.get(name, 0) + 1
            walk(child, f"{path}/{name}[{counts[name]}]")

    walk(root, f"/{_local(root.tag)}[1]")
    return paths


def _append_piece(out: str, piece: str, *, semantic_boundary: bool = False) -> str:
    if not piece:
        return out
    if semantic_boundary and out and not out[-1].isspace() and not piece[0].isspace() and out[-1].isalnum() and piece[0].isalnum():
        return out + " " + piece
    return out + piece


def _render_math(elem: ET.Element) -> str:
    tag=_local(elem.tag)
    children=list(elem)
    if tag == "msup" and len(children)>=2:
        return f"{_render_inline(children[0])}^{_render_inline(children[1])}"
    if tag == "msub" and len(children)>=2:
        return f"{_render_inline(children[0])}_{_render_inline(children[1])}"
    if tag == "mfrac" and len(children)>=2:
        return f"({_render_inline(children[0])})/({_render_inline(children[1])})"
    return _render_inline(elem)


def _render_inline(elem: ET.Element) -> str:
    """Render JATS inline semantics without compatibility-normalizing numerics."""
    out=elem.text or ""
    for child in list(elem):
        tag=_local(child.tag)
        if tag == "sup":
            piece="^" + _render_inline(child)
            boundary=False
        elif tag == "sub":
            piece="_" + _render_inline(child)
            boundary=False
        elif tag in {"msup","msub","mfrac"}:
            piece=_render_math(child); boundary=False
        elif tag == "math":
            piece=_render_math(child); boundary=False
        else:
            piece=_render_inline(child)
            boundary=tag in {"xref","ext-link","uri","inline-graphic","inline-media"}
        out=_append_piece(out,piece,semantic_boundary=boundary)
        if child.tail:
            out=_append_piece(out,child.tail,semantic_boundary=boundary)
    return out


def _text(elem: ET.Element) -> str:
    return _render_inline(elem)


def _parent_map(root: ET.Element) -> Dict[int, ET.Element]:
    return {id(child):parent for parent in root.iter() for child in list(parent)}


def _ancestors(elem: ET.Element, parents: Mapping[int,ET.Element]) -> List[ET.Element]:
    out=[]; cur=parents.get(id(elem))
    while cur is not None:
        out.append(cur); cur=parents.get(id(cur))
    return out


def _section_path(elem: ET.Element, parents: Mapping[int,ET.Element]) -> List[str]:
    labels=[]
    for anc in reversed(_ancestors(elem,parents)):
        if _local(anc.tag)=="sec":
            title=next((c for c in list(anc) if _local(c.tag)=="title"),None)
            if title is not None:
                t=_text(title).strip()
                if t: labels.append(t)
    return labels


def _normalized_xml_fragment_sha256(elem: ET.Element) -> str:
    return _sha256_bytes(ET.tostring(elem,encoding="utf-8"))


def _apply_cc_license(row: Dict[str,Any], lic: str) -> None:
    if lic in {"cc0","cc_0"}:
        row.update(redistribution_status="UNRESTRICTED",commercial_reuse_allowed=True,derivative_reuse_allowed=True)
    elif lic in {"cc_by","ccby","cc_by_4_0"}:
        row.update(redistribution_status="ALLOWED_WITH_ATTRIBUTION",commercial_reuse_allowed=True,derivative_reuse_allowed=True)
    elif lic in {"cc_by_nc","cc_by_nc_4_0"}:
        row.update(redistribution_status="ALLOWED_NONCOMMERCIAL_WITH_ATTRIBUTION",commercial_reuse_allowed=False,derivative_reuse_allowed=True)
    elif lic in {"cc_by_nd","cc_by_nd_4_0"}:
        row.update(redistribution_status="ALLOWED_UNALTERED_WITH_ATTRIBUTION",commercial_reuse_allowed=True,derivative_reuse_allowed=False)
    elif lic in {"cc_by_nc_nd","cc_by_nc_nd_4_0"}:
        row.update(redistribution_status="ALLOWED_NONCOMMERCIAL_UNALTERED_WITH_ATTRIBUTION",commercial_reuse_allowed=False,derivative_reuse_allowed=False)
    elif lic in {"cc_by_sa","cc_by_sa_4_0"}:
        row.update(redistribution_status="ALLOWED_WITH_ATTRIBUTION_SHAREALIKE",commercial_reuse_allowed=True,derivative_reuse_allowed=True)
    elif lic in {"cc_by_nc_sa","cc_by_nc_sa_4_0"}:
        row.update(redistribution_status="ALLOWED_NONCOMMERCIAL_SHAREALIKE",commercial_reuse_allowed=False,derivative_reuse_allowed=True)


def rights_decision(*, source: str, license_code: Optional[str] = None, basis_url: Optional[str] = None,
                    pmc_oai_fulltext_returned: bool = False) -> Dict[str, Any]:
    """Keep text-mining and redistribution rights independent and fail closed."""
    source_norm = source.lower().strip()
    lic = (license_code or "").strip().lower().replace("-", "_").replace(" ","_")
    row: Dict[str, Any] = {
        "rights_schema_version": RIGHTS_SCHEMA_VERSION,"source":source,"license_code":license_code,"basis_url":basis_url,
        "text_mining_allowed":None,"redistribution_status":"UNKNOWN","commercial_reuse_allowed":None,
        "derivative_reuse_allowed":None,"rights_basis":None,
    }
    if source_norm == "pmc" and pmc_oai_fulltext_returned:
        # PMC documents metadataPrefix=pmc full text as available only where licenses/
        # usage rights permit reuse. Endpoint return establishes reuse eligibility,
        # but detailed commercial/derivative terms still require the article license.
        row["text_mining_allowed"]=True
        row["rights_basis"]="PMC_OAI_REUSE_ELIGIBLE_FULLTEXT_PLUS_ARTICLE_LICENSE"
        if lic:
            _apply_cc_license(row,lic)
        if row["redistribution_status"]=="UNKNOWN":
            row["redistribution_status"]="REUSE_ALLOWED_TERMS_UNCLASSIFIED"
        return row
    if source_norm in {"biorxiv","medrxiv"}:
        row["text_mining_allowed"]=True; row["rights_basis"]="SOURCE_TDM_TERMS_PLUS_ARTICLE_LICENSE"
        _apply_cc_license(row,lic)
        if lic in {"cc_no","no_reuse","none","all_rights_reserved"}:
            row.update(redistribution_status="PERMISSION_REQUIRED",commercial_reuse_allowed=False,derivative_reuse_allowed=False)
        return row
    return row


def _license_code_from_jats(payload: bytes) -> Optional[str]:
    try: article=_find_jats_article(payload)
    except Exception: return None
    candidates=[]
    for elem in article.iter():
        if _local(elem.tag)!="license": continue
        for k,v in elem.attrib.items():
            if k.endswith("href") and v: candidates.append(v)
        txt=" ".join(t.strip() for t in elem.itertext() if t.strip())
        if txt: candidates.append(txt)
    joined=" ".join(candidates).lower()
    patterns=[
        ("cc_by_nc_nd","by-nc-nd"),("cc_by_nc_sa","by-nc-sa"),("cc_by_nc","by-nc"),
        ("cc_by_nd","by-nd"),("cc_by_sa","by-sa"),("cc_by","creativecommons.org/licenses/by/"),("cc0","creativecommons.org/publicdomain/zero"),
    ]
    for code,needle in patterns:
        if needle in joined: return code
    return None


def validate_rights_decision(row: Mapping[str, Any]) -> List[str]:
    e: List[str] = []
    if row.get("rights_schema_version") != RIGHTS_SCHEMA_VERSION: e.append("rights schema mismatch")
    if not isinstance(row.get("source"), str) or not row.get("source"): e.append("source required")
    if row.get("text_mining_allowed") not in (True, False, None): e.append("text_mining_allowed must be boolean/null")
    if row.get("redistribution_status") not in {
        "UNKNOWN", "SOURCE_ENDPOINT_PERMITS_FULLTEXT_OUTPUT", "UNRESTRICTED", "ALLOWED_WITH_ATTRIBUTION",
        "ALLOWED_NONCOMMERCIAL_WITH_ATTRIBUTION", "ALLOWED_UNALTERED_WITH_ATTRIBUTION",
        "ALLOWED_NONCOMMERCIAL_UNALTERED_WITH_ATTRIBUTION", "ALLOWED_WITH_ATTRIBUTION_SHAREALIKE",
        "ALLOWED_NONCOMMERCIAL_SHAREALIKE", "REUSE_ALLOWED_TERMS_UNCLASSIFIED", "PERMISSION_REQUIRED"
    }: e.append("invalid redistribution_status")
    return e


def persist_fulltext_artifact(*, payload: bytes, output_path: Path, source: str, source_resource_id: str,
                              source_version_id: str, source_url: str, content_type: str,
                              rights: Mapping[str, Any], retrieval_transport: str = "HTTP") -> Dict[str, Any]:
    errs = validate_rights_decision(rights)
    if errs: raise ValueError("invalid rights decision: " + "; ".join(errs))
    _atomic_bytes(Path(output_path), payload)
    return {
        "fulltext_artifact_schema_version": FULLTEXT_ARTIFACT_SCHEMA_VERSION,
        "source": source,
        "source_resource_id": source_resource_id,
        "source_version_id": source_version_id,
        "source_url": source_url,
        "content_type": content_type,
        "retrieval_transport": retrieval_transport,
        "artifact_path": str(output_path),
        "artifact_locator": Path(output_path).name,
        "artifact_sha256": _sha256_bytes(payload),
        "artifact_bytes": len(payload),
        "rights": dict(rights),
        "text_mining_allowed": rights.get("text_mining_allowed"),
        "redistribution_status": rights.get("redistribution_status"),
    }


def validate_fulltext_artifact(row: Mapping[str, Any], *, require_local_file: bool = False) -> List[str]:
    e: List[str] = []
    if row.get("fulltext_artifact_schema_version") != FULLTEXT_ARTIFACT_SCHEMA_VERSION: e.append("artifact schema mismatch")
    for k in ("source", "source_resource_id", "source_version_id", "source_url", "content_type", "artifact_sha256"):
        if not isinstance(row.get(k), str) or not row.get(k): e.append(f"{k} required")
    if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("artifact_sha256") or "")): e.append("artifact_sha256 invalid")
    e.extend(validate_rights_decision(row.get("rights") or {}))
    if row.get("text_mining_allowed") is not True: e.append("full-text artifact cannot be segmented unless text_mining_allowed=true")
    if require_local_file:
        p = Path(str(row.get("artifact_path") or ""))
        if not p.is_file(): e.append("artifact file missing")
        elif _sha256_bytes(p.read_bytes()) != row.get("artifact_sha256"): e.append("artifact file hash mismatch")
    return e


def acquire_http_fulltext(*, url: str, output_path: Path, source: str, source_resource_id: str,
                          source_version_id: str, rights: Mapping[str, Any], allow_network: bool,
                          session: Optional[requests.Session] = None, timeout: int = 30,
                          expected_content_markers: Tuple[str, ...] = ("xml",),
                          require_jats: bool = True, allow_local_test_host: bool = False) -> Dict[str, Any]:
    if not allow_network: raise RuntimeError("full-text HTTP acquisition is locked; explicit allow_network=True required")
    if rights.get("text_mining_allowed") is not True: raise RuntimeError("full-text acquisition blocked: text-mining permission is not established")
    from urllib.parse import urlparse
    host=(urlparse(url).hostname or "").lower()
    local=host in {"127.0.0.1","localhost"}
    if local and not allow_local_test_host: raise RuntimeError("local test host requires explicit allow_local_test_host=True")
    if host not in APPROVED_FULLTEXT_HOSTS and not (local and allow_local_test_host): raise RuntimeError(f"unapproved full-text host: {host}")
    sess=session or requests.Session(); response=sess.get(url,timeout=timeout,headers={"Accept-Encoding":"gzip, deflate"}); response.raise_for_status()
    payload=bytes(response.content); ctype=str(response.headers.get("Content-Type") or "application/octet-stream")
    if expected_content_markers and not any(x in ctype.lower() for x in expected_content_markers): raise RuntimeError(f"unexpected full-text content type: {ctype}")
    if require_jats:
        try: _find_jats_article(payload)
        except Exception as exc: raise RuntimeError(f"full-text payload is not parseable JATS XML: {exc}") from exc
    return persist_fulltext_artifact(payload=payload,output_path=Path(output_path),source=source,source_resource_id=source_resource_id,
                                     source_version_id=source_version_id,source_url=url,content_type=ctype,rights=rights)


def pmc_oai_getrecord_url(pmcid: str) -> str:
    numeric = str(pmcid).upper().removeprefix("PMC")
    if not numeric.isdigit(): raise ValueError("PMCID must be PMC followed by digits")
    from urllib.parse import urlencode
    q = urlencode({"verb": "GetRecord", "identifier": f"oai:pubmedcentral.nih.gov:{numeric}", "metadataPrefix": "pmc"})
    return PMC_OAI_BASE + "?" + q



def acquire_pmc_oai_fulltext(*, pmcid: str, output_path: Path, source_version_id: str, allow_network: bool,
                             session: Optional[requests.Session] = None, timeout: int = 30) -> Dict[str, Any]:
    if not allow_network: raise RuntimeError("PMC full-text acquisition is locked; explicit allow_network=True required")
    url = pmc_oai_getrecord_url(pmcid)
    sess = session or requests.Session()
    response = sess.get(url, timeout=timeout, headers={"Accept-Encoding":"gzip, deflate"})
    response.raise_for_status()
    payload = bytes(response.content)
    # Full-text output must actually contain a JATS article; OAI errors fail closed.
    _find_jats_article(payload)
    license_code=_license_code_from_jats(payload)
    rights = rights_decision(source="pmc", license_code=license_code, basis_url=url, pmc_oai_fulltext_returned=True)
    return persist_fulltext_artifact(payload=payload, output_path=Path(output_path), source="pmc",
        source_resource_id=f"PMCID:{str(pmcid).upper().removeprefix('PMC')}", source_version_id=source_version_id, source_url=url,
        content_type=str(response.headers.get("Content-Type") or "application/xml"), rights=rights)


def acquire_preprint_jats(*, jats_url: str, server: str, doi: str, version: str, license_code: Optional[str],
                          output_path: Path, allow_network: bool, session: Optional[requests.Session] = None,
                          timeout: int = 30) -> Dict[str, Any]:
    if server.lower() not in {"biorxiv","medrxiv"}: raise ValueError("server must be biorxiv or medrxiv")
    rights = rights_decision(source=server, license_code=license_code, basis_url=jats_url)
    return acquire_http_fulltext(url=jats_url, output_path=Path(output_path), source=server,
        source_resource_id=f"DOI:{doi}", source_version_id=str(version), rights=rights, allow_network=allow_network,
        session=session, timeout=timeout, expected_content_markers=("xml",), require_jats=True)

def _find_jats_article(xml_payload: bytes) -> ET.Element:
    root = ET.fromstring(xml_payload)
    if _local(root.tag) == "article": return root
    for elem in root.iter():
        if _local(elem.tag) == "article": return elem
    # OAI errors must not become empty/full-text success.
    for elem in root.iter():
        if _local(elem.tag) == "error":
            raise ValueError(f"full-text source returned OAI error: {''.join(elem.itertext()).strip()}")
    raise ValueError("no JATS article element found in full-text XML")


def segment_jats_xml(*, xml_payload: bytes, source_record_key: str, source_resource_id: str,
                     source_version_id: str, source_sha256: Optional[str] = None,
                     publication_year: Optional[int] = None, edition_or_version: Optional[str] = None,
                     source_era: Optional[str] = None, source_scope: str = "FULL_TEXT",
                     metadata: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    article=_find_jats_article(xml_payload); actual_sha=_sha256_bytes(xml_payload)
    if source_sha256 is not None and source_sha256!=actual_sha: raise ValueError("provided source_sha256 does not match JATS/full-text bytes")
    paths=_element_paths(article); parents=_parent_map(article); units=[]; ordinal=0
    base_meta={**dict(metadata or {}),"segmenter_version":SEGMENTER_SCHEMA_VERSION,"source_artifact_sha256":actual_sha}

    def scope_for(elem: ET.Element, path: str) -> str:
        if "/back[" in path: return "METADATA"
        if "/abstract[" in path: return "ABSTRACT_WITHIN_FULLTEXT" if source_scope=="FULL_TEXT" else "ABSTRACT_ONLY"
        return source_scope

    def meta_for(elem: ET.Element) -> Dict[str,Any]:
        return {**base_meta,"section_path":_section_path(elem,parents),"normalized_xml_fragment_sha256":_normalized_xml_fragment_sha256(elem),"jats_xpath":paths[id(elem)]}

    for elem in article.iter():
        tag=_local(elem.tag); path=paths[id(elem)]; ancestors=_ancestors(elem,parents)
        if tag=="p":
            if any(_local(a.tag) in {"caption","td","th","p"} for a in ancestors): continue
            text=_text(elem)
            if not text.strip(): continue
            scope=scope_for(elem,path)
            locator={"locator_type":"JATS_XPATH","jats_xpath":path,"element":"p","section_path":_section_path(elem,parents)}
            units.append(build_source_unit(source_record_key=source_record_key,source_resource_id=source_resource_id,source_version_id=source_version_id,
                source_sha256=actual_sha,source_scope=scope,unit_kind="TEXT",locator=locator,content_text=text,ordinal=ordinal,
                publication_year=publication_year,edition_or_version=edition_or_version,source_era=source_era,metadata=meta_for(elem))); ordinal+=1
        elif tag=="title" and any(_local(a.tag)=="sec" for a in ancestors):
            text=_text(elem).strip()
            if not text: continue
            scope=scope_for(elem,path)
            locator={"locator_type":"JATS_XPATH","jats_xpath":path,"element":"title","section_path":_section_path(elem,parents)}
            units.append(build_source_unit(source_record_key=source_record_key,source_resource_id=source_resource_id,source_version_id=source_version_id,
                source_sha256=actual_sha,source_scope=scope,unit_kind="TEXT",locator=locator,content_text=text,ordinal=ordinal,
                publication_year=publication_year,edition_or_version=edition_or_version,source_era=source_era,metadata=meta_for(elem))); ordinal+=1
        elif tag in {"td","th"}:
            text=_text(elem)
            if not text.strip(): continue
            parent=parents.get(id(elem)); siblings=[c for c in (list(parent) if parent is not None else []) if _local(c.tag) in {"th","td"}]
            col_index=siblings.index(elem) if elem in siblings else None
            row=parent if parent is not None and _local(parent.tag)=="tr" else None
            row_parent=parents.get(id(row)) if row is not None else None
            rows=[c for c in list(row_parent) if _local(c.tag)=="tr"] if row_parent is not None else []
            row_index=rows.index(row) if row in rows else None
            headers=[]
            if row is not None:
                headers=[_text(c).strip() for c in list(row) if _local(c.tag)=="th" and _text(c).strip()]
            # Column header from preceding header rows and the table's THEAD.
            if row_parent is not None and col_index is not None:
                for prior in rows[:row_index or 0]:
                    cells=[c for c in list(prior) if _local(c.tag) in {"th","td"}]
                    if col_index < len(cells) and _local(cells[col_index].tag)=="th":
                        h=_text(cells[col_index]).strip()
                        if h and h not in headers: headers.append(h)
                table_ancestor=next((a for a in ancestors if _local(a.tag)=="table"),None)
                if table_ancestor is not None:
                    for tr in table_ancestor.iter():
                        if _local(tr.tag)!="tr": continue
                        cells=[c for c in list(tr) if _local(c.tag) in {"th","td"}]
                        if col_index < len(cells) and _local(cells[col_index].tag)=="th":
                            h=_text(cells[col_index]).strip()
                            if h and h not in headers: headers.append(h)
            locator={"locator_type":"TABLE_CELL","jats_xpath":path,"cell_tag":tag,"row_index":row_index,"col_index":col_index,
                     "colspan":int(elem.attrib.get("colspan","1") or 1),"rowspan":int(elem.attrib.get("rowspan","1") or 1),"header_refs":headers,
                     "section_path":_section_path(elem,parents)}
            units.append(build_source_unit(source_record_key=source_record_key,source_resource_id=source_resource_id,source_version_id=source_version_id,
                source_sha256=actual_sha,source_scope="TABLE",unit_kind="TABLE_CELL",locator=locator,content_text=text,ordinal=ordinal,
                publication_year=publication_year,edition_or_version=edition_or_version,source_era=source_era,metadata=meta_for(elem))); ordinal+=1
        elif tag=="caption":
            parent_path=path.rsplit("/",1)[0]
            if "/fig[" not in parent_path and "/table-wrap[" not in parent_path: continue
            text=_text(elem)
            if not text.strip(): continue
            kind="FIGURE_CAPTION" if "/fig[" in parent_path else "TEXT"; scope="FIGURE" if kind=="FIGURE_CAPTION" else "TABLE"
            locator={"locator_type":"FIGURE" if kind=="FIGURE_CAPTION" else "TEXT_SECTION","jats_xpath":path,"element":"caption","section_path":_section_path(elem,parents)}
            units.append(build_source_unit(source_record_key=source_record_key,source_resource_id=source_resource_id,source_version_id=source_version_id,
                source_sha256=actual_sha,source_scope=scope,unit_kind=kind,locator=locator,content_text=text,ordinal=ordinal,
                publication_year=publication_year,edition_or_version=edition_or_version,source_era=source_era,metadata=meta_for(elem))); ordinal+=1
    return units


def segment_pubmed_abstract(*, record: Mapping[str, Any], source_record_key: str,
                            source_resource_id: Optional[str] = None) -> List[Dict[str, Any]]:
    source_sha = str(record.get("source_record_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha): raise ValueError("PubMed record lacks valid source_record_sha256")
    pmid = str(record.get("pmid") or "")
    rid = source_resource_id or f"PMID:{pmid}"
    version = str(record.get("version") or record.get("date_revised") or record.get("retrieved_at") or "unknown")
    year = None
    pd = record.get("pub_date") or {}
    if isinstance(pd, dict):
        parsed = str(pd.get("parsed_date") or pd.get("year") or "")
        m = re.search(r"\b(18|19|20)\d{2}\b", parsed)
        if m: year = int(m.group(0))
    sections = record.get("abstract_sections") or []
    units: List[Dict[str, Any]] = []
    if sections:
        for i, sec in enumerate(sections):
            text = str(sec.get("text") or "") if isinstance(sec, dict) else str(sec)
            if not text.strip(): continue
            label = sec.get("label") if isinstance(sec, dict) else None
            units.append(build_source_unit(source_record_key=source_record_key, source_resource_id=rid, source_version_id=version,
                source_sha256=source_sha, source_scope="ABSTRACT_ONLY", unit_kind="ABSTRACT_SECTION",
                locator={"locator_type":"TEXT_SECTION","section":"Abstract","label":label,"ordinal":i}, content_text=text,
                ordinal=i, publication_year=year, edition_or_version=version, metadata={"segmenter_version":SEGMENTER_SCHEMA_VERSION,"fallback_reason":"FULL_TEXT_NOT_PROVIDED"}))
    else:
        abstract = str(record.get("abstract") or "")
        if abstract.strip():
            units.append(build_source_unit(source_record_key=source_record_key, source_resource_id=rid, source_version_id=version,
                source_sha256=source_sha, source_scope="ABSTRACT_ONLY", unit_kind="ABSTRACT_SECTION",
                locator={"locator_type":"TEXT_SECTION","section":"Abstract","ordinal":0}, content_text=abstract,
                ordinal=0, publication_year=year, edition_or_version=version, metadata={"segmenter_version":SEGMENTER_SCHEMA_VERSION,"fallback_reason":"FULL_TEXT_NOT_PROVIDED"}))
    return units


def segment_structured_json(*, value: Any, source_record_key: str, source_resource_id: str,
                            source_version_id: str, source_sha256: str, source_scope: str = "REGISTRY_STRUCTURED",
                            root_path: Tuple[Any, ...] = (), publication_year: Optional[int] = None,
                            edition_or_version: Optional[str] = None, source_era: Optional[str] = None,
                            metadata: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    ordinal = 0

    def walk(obj: Any, parts: Tuple[Any, ...]) -> None:
        nonlocal ordinal
        if isinstance(obj, dict) and obj:
            for k in sorted(obj): walk(obj[k], parts + (k,))
            return
        if isinstance(obj, list) and obj:
            for i, item in enumerate(obj): walk(item, parts + (i,))
            return
        locator_path = _canonical_json_path(parts)
        units.append(build_source_unit(source_record_key=source_record_key, source_resource_id=source_resource_id,
            source_version_id=source_version_id, source_sha256=source_sha256, source_scope=source_scope, unit_kind="JSON_FIELD",
            locator={"locator_type":"JSON_PATH","json_path":locator_path}, content_json=obj, ordinal=ordinal,
            publication_year=publication_year, edition_or_version=edition_or_version, source_era=source_era,
            metadata={**dict(metadata or {}),"segmenter_version":SEGMENTER_SCHEMA_VERSION}))
        ordinal += 1

    walk(value, root_path)
    return units


def segment_monograph_text(*, text: str, source_record_key: str, source_resource_id: str,
                           source_version_id: str, source_sha256: str, publication_year: Optional[int] = None,
                           edition_or_version: Optional[str] = None, source_era: Optional[str] = None,
                           metadata: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    units=[]; separators=list(re.finditer(r"(?:\r?\n[ \t]*\r?\n)+",text)); boundaries=[]; start=0
    for sep in separators: boundaries.append((start,sep.start())); start=sep.end()
    boundaries.append((start,len(text)))
    ordinal=0
    for start,end in boundaries:
        raw=text[start:end]
        if not raw.strip(): continue
        # Paragraph identity should not depend on file-format boundary whitespace
        # (for example a terminal newline). Preserve exact offsets for the retained text.
        left=len(raw)-len(raw.lstrip(" \t\r\n"))
        right=len(raw)-len(raw.rstrip(" \t\r\n"))
        pstart=start+left; pend=end-right if right else end
        paragraph=text[pstart:pend]
        if not paragraph: continue
        byte_start=len(text[:pstart].encode("utf-8")); byte_end=len(text[:pend].encode("utf-8"))
        units.append(build_source_unit(source_record_key=source_record_key,source_resource_id=source_resource_id,source_version_id=source_version_id,
            source_sha256=source_sha256,source_scope="MONOGRAPH",unit_kind="TEXT",
            locator={"locator_type":"MONOGRAPH_SECTION","paragraph":ordinal,"char_start":pstart,"char_end":pend,"utf8_byte_start":byte_start,"utf8_byte_end":byte_end},
            content_text=paragraph,ordinal=ordinal,publication_year=publication_year,edition_or_version=edition_or_version,source_era=source_era,
            metadata={**dict(metadata or {}),"segmenter_version":SEGMENTER_SCHEMA_VERSION})); ordinal+=1
    return units



def _publication_year_from_record(record: Mapping[str, Any]) -> Optional[int]:
    for candidate in (record.get("publication_year"), record.get("date"), record.get("published"), record.get("pub_date"), record.get("date_created")):
        if isinstance(candidate, dict):
            candidate = candidate.get("parsed_date") or candidate.get("year") or candidate.get("date")
        m = re.search(r"\b(18|19|20)\d{2}\b", str(candidate or ""))
        if m: return int(m.group(0))
    return None


def segment_pubmed_evidence(*, record: Mapping[str, Any], source_record_key: str,
                            fulltext_artifact: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    if fulltext_artifact is None:
        return segment_pubmed_abstract(record=record, source_record_key=source_record_key)
    pmc=str(record.get("pmc_id") or "").upper()
    if not pmc: raise ValueError("PubMed full-text artifact requires a verified pmc_id on the source record")
    expected="PMCID:"+pmc.removeprefix("PMC")
    if str(fulltext_artifact.get("source_resource_id") or "") != expected:
        raise ValueError("PubMed full-text artifact identifier does not match source record pmc_id")
    return segment_artifact_jats(artifact=fulltext_artifact, source_record_key=source_record_key,
        publication_year=_publication_year_from_record(record), edition_or_version=str(record.get("version") or fulltext_artifact.get("source_version_id") or "unknown"),
        source_era=record.get("source_era"))


def segment_preprint_evidence(*, record: Mapping[str, Any], source_record_key: str,
                              fulltext_artifact: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    if fulltext_artifact is not None:
        doi=str(record.get("doi") or "")
        if not doi or str(fulltext_artifact.get("source_resource_id") or "") != f"DOI:{doi}":
            raise ValueError("preprint full-text artifact identifier does not match source DOI")
        return segment_artifact_jats(artifact=fulltext_artifact, source_record_key=source_record_key,
            publication_year=_publication_year_from_record(record), edition_or_version=str(record.get("version") or fulltext_artifact.get("source_version_id") or "unknown"),
            source_era=record.get("source_era"))
    sha = str(record.get("source_record_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", sha): raise ValueError("preprint record lacks valid source_record_sha256")
    abstract = str(record.get("abstract") or "")
    if not abstract.strip(): return []
    doi = str(record.get("doi") or "")
    version = str(record.get("version") or "unknown")
    return [build_source_unit(source_record_key=source_record_key, source_resource_id=f"DOI:{doi}", source_version_id=version,
        source_sha256=sha, source_scope="ABSTRACT_ONLY", unit_kind="ABSTRACT_SECTION",
        locator={"locator_type":"TEXT_SECTION","section":"Abstract","ordinal":0}, content_text=abstract, ordinal=0,
        publication_year=_publication_year_from_record(record), edition_or_version=version, source_era=record.get("source_era"),
        metadata={"segmenter_version":SEGMENTER_SCHEMA_VERSION,"fallback_reason":"FULL_TEXT_NOT_PROVIDED","server":record.get("server")})]


def segment_clinicaltrials_evidence(*, raw_record: Mapping[str, Any], source_record_key: str, source_resource_id: str,
                                    source_version_id: str, source_sha256: str, retrieved_year: Optional[int] = None) -> List[Dict[str, Any]]:
    return segment_structured_json(value=dict(raw_record), source_record_key=source_record_key, source_resource_id=source_resource_id,
        source_version_id=source_version_id, source_sha256=source_sha256, source_scope="REGISTRY_STRUCTURED",
        publication_year=None, edition_or_version=source_version_id, source_era=str(retrieved_year) if retrieved_year else None,
        metadata={"source_family":"clinicaltrials.gov"})

def segment_artifact_jats(*, artifact: Mapping[str, Any], source_record_key: str,
                          publication_year: Optional[int] = None, edition_or_version: Optional[str] = None,
                          source_era: Optional[str] = None) -> List[Dict[str, Any]]:
    errs = validate_fulltext_artifact(artifact, require_local_file=True)
    if errs: raise ValueError("invalid full-text artifact: " + "; ".join(errs))
    payload = Path(str(artifact["artifact_path"])).read_bytes()
    return segment_jats_xml(xml_payload=payload, source_record_key=source_record_key,
        source_resource_id=str(artifact["source_resource_id"]), source_version_id=str(artifact["source_version_id"]),
        source_sha256=str(artifact["artifact_sha256"]), publication_year=publication_year,
        edition_or_version=edition_or_version or str(artifact["source_version_id"]), source_era=source_era,
        metadata={"fulltext_artifact_sha256":artifact["artifact_sha256"],"source_url":artifact["source_url"],
                  "redistribution_status":artifact.get("redistribution_status")})
