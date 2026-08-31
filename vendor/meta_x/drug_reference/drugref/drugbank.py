"""Streaming DrugBank XML parser.

The engine never downloads or fabricates DrugBank data. The caller must supply
an XML file they are authorized to use under the applicable DrugBank terms.
"""
from __future__ import annotations
import os
import hashlib
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterator, List, Optional

NS="{http://www.drugbank.ca}"
def local(tag: str) -> str: return tag.rsplit("}",1)[-1]
def child(elem: ET.Element, name: str) -> Optional[ET.Element]:
    x=elem.find(NS+name)
    return x if x is not None else elem.find(name)
def text(elem: ET.Element, name: str) -> Optional[str]:
    x=child(elem,name)
    return x.text.strip() if x is not None and x.text else None

def parse_drug(elem: ET.Element) -> Dict[str, Any]:
    ids=[]; primary=None
    for x in list(elem):
        if local(x.tag)=="drugbank-id" and x.text:
            value=x.text.strip(); ids.append(value)
            if x.attrib.get("primary")=="true": primary=value
    synonyms=[]; se=child(elem,"synonyms")
    if se is not None:
        synonyms=[x.text.strip() for x in list(se) if local(x.tag)=="synonym" and x.text]
    groups=[]; ge=child(elem,"groups")
    if ge is not None:
        groups=[x.text.strip() for x in list(ge) if local(x.tag)=="group" and x.text]
    source_xml_sha256 = hashlib.sha256(ET.tostring(elem, encoding="utf-8")).hexdigest()
    return {
        "drugbank_id": primary or (ids[0] if ids else None),
        "drugbank_ids": ids,
        "name": text(elem,"name"),
        "description": text(elem,"description"),
        "cas_number": text(elem,"cas-number"),
        "groups": groups,
        "synonyms": synonyms,
        "indication": text(elem,"indication"),
        "mechanism_of_action": text(elem,"mechanism-of-action"),
        "toxicity": text(elem,"toxicity"),
        "source_updated": elem.attrib.get("updated"),
        "source_record_sha256": source_xml_sha256,
        "source_payload_type": "drugbank_xml_element",
        "source": "drugbank_local_xml",
    }

def iter_drugs(path: str) -> Iterator[Dict[str, Any]]:
    if not os.path.isfile(path): raise FileNotFoundError(path)
    context=ET.iterparse(path,events=("start","end"))
    _, root=next(context)
    for event, elem in context:
        if event=="end" and local(elem.tag)=="drug":
            yield parse_drug(elem)
            elem.clear(); root.clear()
