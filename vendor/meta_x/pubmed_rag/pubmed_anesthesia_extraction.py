"""
Canonical PubMed source extraction for the anesthesia research domain.

Source identity and completeness are preserved before any optional classification.
Distinct PMIDs are never deleted by title/DOI heuristics. Extraction is model-agnostic;
embeddings and RAG belong to downstream enrichment.
"""

import time
import random
import re
import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple, Set, Callable, Any
from datetime import datetime, date, timedelta, timezone
import requests
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from dataclasses import dataclass
import uuid

try:
    from .metadata_schema import (
        PubMedRecordFull, PubDateModel, AuthorModel, MeshHeadingModel
    )
except ImportError:  # direct-script/test execution
    from metadata_schema import (
        PubMedRecordFull, PubDateModel, AuthorModel, MeshHeadingModel
    )

logger = logging.getLogger(__name__)

# ==================== AUDIT FIX 1: RATE LIMITS ====================

@dataclass
class RateLimitConfig:
    email: str
    api_key: Optional[str] = None
    tool: str = "frontier-pubmed-source"
    requests_per_second_without_key: float = 3.0
    requests_per_second_with_key: float = 10.0
    max_retries: int = 5
    base_delay: float = 0.34  # 3 req/s = 0.333s; add margin
    with_key_delay: float = 0.11  # 10 req/s = 0.1s

class RateLimitedPubMedClient:
    """Production NCBI E-utilities client with proper throttling"""
    
    def __init__(self, config: RateLimitConfig, raw_response_hook: Optional[Callable[[str, Dict[str, Any], bytes], None]] = None, session=None):
        if not config.email or "@" not in config.email:
            raise ValueError("A real contact email is required for NCBI E-utilities")
        self.config = config
        self.raw_response_hook = raw_response_hook
        self.last_request_time = 0.0
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": f"{config.tool} (mailto:{config.email})"
        })
        
        delay = config.with_key_delay if config.api_key else config.base_delay
        logger.info(f"Rate limiter: {1/delay:.1f} req/s (API key: {'yes' if config.api_key else 'no'})")
    
    def _throttle(self):
        delay = self.config.with_key_delay if self.config.api_key else self.config.base_delay
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request_time = time.time()
    
    def _request_with_backoff(self, url: str, params: Dict, retries: int = None) -> requests.Response:
        retries = retries or self.config.max_retries
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = None
                    if retry_after:
                        try:
                            wait = max(0.0, float(retry_after))
                        except ValueError:
                            try:
                                retry_dt = parsedate_to_datetime(retry_after)
                                if retry_dt.tzinfo is None:
                                    retry_dt = retry_dt.replace(tzinfo=timezone.utc)
                                wait = max(0.0, (retry_dt - datetime.now(timezone.utc)).total_seconds())
                            except Exception:
                                wait = None
                    if wait is None:
                        wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"429 Rate limit, backoff {wait:.1f}s attempt {attempt+1}/{retries}")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                if attempt == retries-1:
                    raise
                wait = (2 ** attempt) + random.uniform(0,1)
                logger.warning(f"Request failed {e}, retry in {wait:.1f}s")
                time.sleep(wait)
        raise RuntimeError(f"Failed after {retries} retries: {url}")

    def esearch(self, query: str, retmax: int = 10000, retstart: int = 0, 
                sort: str = "relevance", mindate: Optional[str] = None, maxdate: Optional[str] = None) -> Dict:
        """Search PubMed with usehistory for large result sets"""
        if bool(mindate) != bool(maxdate):
            raise ValueError("NCBI ESearch arbitrary date ranges require both mindate and maxdate")
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retstart": retstart,
            "retmode": "json",
            "sort": sort,
            "email": self.config.email,
            "tool": self.config.tool,
            "usehistory": "y"
        }
        if self.config.api_key:
            params["api_key"] = self.config.api_key
        if mindate:
            params["mindate"] = mindate
            params["datetype"] = "pdat"
        if maxdate:
            params["maxdate"] = maxdate
            params["datetype"] = "pdat"
        
        resp = self._request_with_backoff(url, params)
        if self.raw_response_hook is not None:
            safe_params={k:v for k,v in params.items() if k != "api_key"}
            content=resp.content if getattr(resp,"content",None) is not None else resp.text.encode("utf-8")
            self.raw_response_hook("esearch", {"url":url,"params":safe_params,"status_code":resp.status_code,"content_type":resp.headers.get("Content-Type")}, content)
        data = resp.json()
        return data.get("esearchresult", {})

    def esearch_all(self, query: str, *, mindate: Optional[str] = None,
                    maxdate: Optional[str] = None, max_ids: Optional[int] = None,
                    sort: str = "pub_date") -> Tuple[List[str], Dict]:
        """Retrieve a complete PubMed UID set without crossing ESearch's 10,000-UID ceiling.

        NCBI limits PubMed ESearch to the first 10,000 UIDs for any single query.
        Complete runs therefore recursively partition an explicitly bounded publication-date
        range until every leaf contains <=10,000 UIDs. User-capped runs are allowed, but
        are explicitly reported as truncated.
        """
        def _count(start: Optional[str], end: Optional[str]) -> int:
            result = self.esearch(query, retmax=0, retstart=0, sort=sort, mindate=start, maxdate=end)
            try:
                return int(result.get("count", 0))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid PubMed ESearch count for query {query!r}: {result.get('count')!r}") from exc

        def _parse_bound(value: str) -> date:
            for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    pass
            raise ValueError(f"Date bounds for complete PubMed extraction must be YYYY/MM/DD: {value!r}")

        expected = _count(mindate, maxdate)
        if max_ids is not None:
            if max_ids < 0:
                raise ValueError("max_ids must be >= 0")
            take = min(expected, max_ids, 10000)
            if max_ids > 10000 and expected > 10000:
                raise ValueError("A capped PubMed ESearch cannot request >10,000 UIDs from one query; use a <=10,000 cap or a complete date-bounded run")
            result = self.esearch(query, retmax=take, retstart=0, sort=sort, mindate=mindate, maxdate=maxdate)
            ids = [str(x) for x in result.get("idlist", [])]
            if len(ids) != take:
                raise RuntimeError(f"PubMed ESearch returned {len(ids)} IDs but {take} were requested for capped query {query!r}")
            return ids, {
                "query": query, "expected_count": expected, "retrieved_count": len(ids),
                "truncated": expected > len(ids), "max_ids": max_ids,
                "mindate": mindate, "maxdate": maxdate, "segments": 1,
            }

        if expected <= 10000:
            result = self.esearch(query, retmax=expected, retstart=0, sort=sort, mindate=mindate, maxdate=maxdate)
            ids = [str(x) for x in result.get("idlist", [])]
            if len(ids) != expected:
                raise RuntimeError(f"PubMed ESearch count drift/incomplete page for {query!r}: expected {expected}, received {len(ids)}")
            return ids, {
                "query": query, "expected_count": expected, "retrieved_count": len(ids),
                "truncated": False, "max_ids": None, "mindate": mindate,
                "maxdate": maxdate, "segments": 1,
            }

        if not mindate or not maxdate:
            raise RuntimeError(
                f"PubMed query {query!r} matches {expected} records, exceeding the ESearch 10,000-UID limit. "
                "Provide explicit mindate/maxdate bounds so the extractor can partition by publication date, "
                "or use NCBI EDirect/FTP bulk data."
            )

        start_date, end_date = _parse_bound(mindate), _parse_bound(maxdate)
        if end_date < start_date:
            raise ValueError("maxdate must be on or after mindate")

        segments = 0
        collected: List[str] = []

        def _walk(start: date, end: date, parent_count: int) -> None:
            nonlocal segments
            start_s, end_s = start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")
            if parent_count <= 10000:
                result = self.esearch(query, retmax=parent_count, retstart=0, sort=sort, mindate=start_s, maxdate=end_s)
                ids = [str(x) for x in result.get("idlist", [])]
                if len(ids) != parent_count:
                    raise RuntimeError(
                        f"PubMed source changed or ESearch was incomplete for {query!r} {start_s}..{end_s}: "
                        f"count={parent_count}, ids={len(ids)}"
                    )
                collected.extend(ids)
                segments += 1
                return
            if start == end:
                raise RuntimeError(
                    f"PubMed query {query!r} has {parent_count} records on {start_s}; one day still exceeds "
                    "the 10,000-UID ESearch limit. Use NCBI EDirect/FTP bulk data instead of accepting truncation."
                )
            mid = start + (end - start) // 2
            right_start = mid + timedelta(days=1)
            left_count = _count(start_s, mid.strftime("%Y/%m/%d"))
            right_count = _count(right_start.strftime("%Y/%m/%d"), end_s)
            if left_count + right_count != parent_count:
                raise RuntimeError(
                    f"PubMed source count drift while partitioning {query!r} {start_s}..{end_s}: "
                    f"parent={parent_count}, children={left_count + right_count}"
                )
            _walk(start, mid, left_count)
            _walk(right_start, end, right_count)

        _walk(start_date, end_date, expected)
        unique = set(collected)
        if len(collected) != expected or len(unique) != expected:
            raise RuntimeError(
                f"PubMed complete-search reconciliation failed for {query!r}: expected={expected}, "
                f"retrieved={len(collected)}, unique={len(unique)}"
            )
        ids = sorted(unique, key=lambda x: int(x) if x.isdigit() else x)
        return ids, {
            "query": query, "expected_count": expected, "retrieved_count": len(ids),
            "truncated": False, "max_ids": None, "mindate": mindate,
            "maxdate": maxdate, "segments": segments,
        }

    def efetch_xml(self, pmids: List[str], retmax: int = 500) -> str:
        """Batch EFetch and return one valid PubmedArticleSet XML document."""
        if not pmids:
            return "<PubmedArticleSet />"
        if retmax <= 0 or retmax > 500:
            raise ValueError("EFetch batch size must be between 1 and 500")
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        merged_root = ET.Element("PubmedArticleSet")
        for i in range(0, len(pmids), retmax):
            chunk = pmids[i:i+retmax]
            params = {
                "db": "pubmed", "id": ",".join(chunk), "retmode": "xml",
                "email": self.config.email, "tool": self.config.tool
            }
            if self.config.api_key:
                params["api_key"] = self.config.api_key
            resp = self._request_with_backoff(url, params)
            if self.raw_response_hook is not None:
                safe_params={k:v for k,v in params.items() if k != "api_key"}
                content=resp.content if getattr(resp,"content",None) is not None else resp.text.encode("utf-8")
                self.raw_response_hook("efetch", {"url":url,"params":safe_params,"pmids":list(chunk),"status_code":resp.status_code,"content_type":resp.headers.get("Content-Type")}, content)
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError as exc:
                raise RuntimeError(f"NCBI EFetch returned malformed XML for PMID batch beginning {chunk[0]}") from exc
            for child in list(root):
                if child.tag in {"PubmedArticle", "PubmedBookArticle"}:
                    merged_root.append(child)
        return ET.tostring(merged_root, encoding="unicode")


# ==================== AUDIT FIX 4: MedlineDate FALLBACK ====================

MONTH_MAP = {
    'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,
    'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,
    'sep':9,'sept':9,'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12,
    'fall':10,'autumn':10,'winter':1,'spring':4,'summer':7
}

def parse_pubmed_date_element(elem) -> Optional[PubDateModel]:
    """Parse a PubDate or ArticleDate XML element with fallback"""
    if elem is None:
        return None
    try:
        year_elem = elem.find("Year")
        month_elem = elem.find("Month")
        day_elem = elem.find("Day")
        medline_date_elem = elem.find("MedlineDate")
        
        if medline_date_elem is not None and medline_date_elem.text:
            medline_str = medline_date_elem.text.strip()
            parsed = PubDateModel.parse_medline_date(medline_str)
            return PubDateModel(
                year=parsed.year if parsed else None,
                month=parsed.month if parsed else None,
                day=parsed.day if parsed else None,
                medline_date_str=medline_str,
                parsed_date=parsed,
                date_source="MedlineDate",
                raw_pubdate={"MedlineDate": medline_str}
            )
        # Structured date
        year = int(year_elem.text) if year_elem is not None and year_elem.text and year_elem.text.isdigit() else None
        month = None
        if month_elem is not None and month_elem.text:
            mt = month_elem.text.strip()
            if mt.isdigit():
                month = int(mt)
            else:
                month = MONTH_MAP.get(mt.lower()[:3], MONTH_MAP.get(mt.lower()))
        day = int(day_elem.text) if day_elem is not None and day_elem.text and day_elem.text.isdigit() else None
        
        parsed_date = None
        if year:
            try:
                parsed_date = date(year, month or 1, day or 1)
            except Exception:
                pass
        
        return PubDateModel(
            year=year, month=month, day=day,
            parsed_date=parsed_date,
            date_source="PubDate_structured",
            raw_pubdate={"Year": year, "Month": month, "Day": day}
        )
    except Exception as e:
        logger.debug(f"Date parse error: {e}")
        return None

def get_best_pub_date(pub_article_elem, pubmed_pub_dates_elem) -> PubDateModel:
    """
    CRITICAL AUDIT FIX: Full fallback chain
    1. Journal Issue PubDate (may contain MedlineDate)
    2. ArticleDate
    3. PubMedPubDate (pubmed/entrez/medline status)
    """
    # 1. Journal PubDate
    journal_pubdate = pub_article_elem.find(".//Journal/JournalIssue/PubDate")
    best = parse_pubmed_date_element(journal_pubdate) if journal_pubdate is not None else None
    if best and best.parsed_date:
        best.date_source = "Journal_PubDate"
        return best
    if best and best.medline_date_str:  # MedlineDate present even if parsed minimally
        best.date_source = "Journal_MedlineDate"
        return best
    
    # 2. ArticleDate
    article_date_elem = pub_article_elem.find(".//ArticleDate")
    if article_date_elem is not None:
        best = parse_pubmed_date_element(article_date_elem)
        if best:
            best.date_source = "ArticleDate"
            if best.parsed_date:
                return best
    
    # 3. PubMedPubDates - prefer 'pubmed' then 'entrez' then 'medline'
    if pubmed_pub_dates_elem is not None:
        for status in ["pubmed", "entrez", "medline"]:
            for pd in pubmed_pub_dates_elem.findall("PubMedPubDate"):
                if pd.get("PubStatus") == status:
                    pd_best = parse_pubmed_date_element(pd)
                    if pd_best:
                        pd_best.date_source = f"PubMedPubDate_{status}"
                        if pd_best.parsed_date:
                            return pd_best
    
    # ultimate fallback - return whatever we have even partial
    if best:
        return best
    # Return unknown but not None - audit fix prevents missing dates breaking pipeline
    return PubDateModel(date_source="unknown_fallback", year=None)


# Source extraction intentionally contains no classification, embedding, or
# cross-record deduplication logic. Those are downstream enrichment concerns.

# ==================== XML PARSING FULL METADATA ====================

def parse_pubmed_xml(xml_string: str, *, strict: bool = False) -> List[PubMedRecordFull]:
    records = []
    # Handle concatenated XML docs from batched efetch
    # Each doc has <?xml> header, split and parse individually
    docs = re.split(r'<\?xml[^>]+\?>', xml_string)
    docs = [d for d in docs if d.strip()]
    
    for doc_str in docs:
        if not doc_str.strip().startswith("<PubmedArticleSet") and "<PubmedArticle>" not in doc_str:
            continue
        # Wrap if needed
        try:
            root = ET.fromstring(doc_str if doc_str.strip().startswith("<") else f"<root>{doc_str}</root>")
        except ET.ParseError:
            try:
                # Attempt to fix by wrapping in set
                if "<PubmedArticleSet" not in doc_str:
                    doc_str = f"<PubmedArticleSet>{doc_str}</PubmedArticleSet>"
                root = ET.fromstring(doc_str)
            except (ET.ParseError, ValueError, TypeError) as e:
                if strict:
                    raise ValueError(f"PubMed XML document parse failed: {e}") from e
                logger.error(f"XML parse failed: {e}")
                continue
        
        for article_elem in root.findall(".//PubmedArticle"):
            try:
                record = parse_single_article(article_elem)
                if record:
                    records.append(record)
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                if strict:
                    pmid_text = (article_elem.findtext("MedlineCitation/PMID") or "unknown").strip()
                    raise ValueError(f"PubMed article parse failed for PMID {pmid_text}: {e}") from e
                logger.warning(f"Failed to parse article: {e}")
                continue
        for book_elem in root.findall(".//PubmedBookArticle"):
            try:
                record = parse_single_book_article(book_elem)
                if record:
                    records.append(record)
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                if strict:
                    pmid_text = (book_elem.findtext("BookDocument/PMID") or "unknown").strip()
                    raise ValueError(f"PubMed book article parse failed for PMID {pmid_text}: {e}") from e
                logger.warning(f"Failed to parse book article: {e}")
                continue
    return records

def _parse_author_elements(author_elements) -> List[AuthorModel]:
    authors = []
    for author_elem in author_elements:
        last = author_elem.find("LastName")
        fore = author_elem.find("ForeName")
        init = author_elem.find("Initials")
        collective = author_elem.find("CollectiveName")
        affiliations = []
        for aff in author_elem.findall("AffiliationInfo/Affiliation"):
            text = "".join(aff.itertext()).strip()
            if text:
                affiliations.append(text)
        identifiers = {}
        for ident in author_elem.findall("Identifier"):
            if ident.text:
                identifiers[ident.get("Source") or "unknown"] = ident.text.strip()
        authors.append(AuthorModel(
            last_name=last.text.strip() if last is not None and last.text else None,
            fore_name=fore.text.strip() if fore is not None and fore.text else None,
            initials=init.text.strip() if init is not None and init.text else None,
            collective_name=collective.text.strip() if collective is not None and collective.text else None,
            affiliation=affiliations[0] if affiliations else None,
            affiliations=affiliations,
            identifiers=identifiers,
        ))
    return authors

def parse_single_book_article(pub_elem) -> Optional[PubMedRecordFull]:
    """Parse PubmedBookArticle without downgrading it to an unsupported PMID.

    NLM's PubMed DTD allows PubmedArticleSet to contain PubmedBookArticle. The
    complete raw XML is retained so fields not projected today remain reparsable.
    """
    doc = pub_elem.find("BookDocument")
    if doc is None:
        return None
    pmid_el = doc.find("PMID")
    pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None
    if not pmid:
        return None
    version = pmid_el.get("Version") if pmid_el is not None else None
    book = doc.find("Book")
    article_title = doc.find("ArticleTitle")
    book_title_el = book.find("BookTitle") if book is not None else None
    title = "".join(article_title.itertext()).strip() if article_title is not None else ("".join(book_title_el.itertext()).strip() if book_title_el is not None else "")
    abstract_parts=[]; abstract_sections=[]
    abstract_el=doc.find("Abstract")
    if abstract_el is not None:
        for ae in abstract_el.findall("AbstractText"):
            txt="".join(ae.itertext()).strip(); label=ae.get("Label") or ae.get("NlmCategory") or ""
            if txt:
                abstract_parts.append(txt)
                if label: abstract_sections.append({"label":label,"text":txt})
    abstract=" ".join(abstract_parts)
    authors=[]
    for al in doc.findall("AuthorList"):
        authors.extend(_parse_author_elements(al.findall("Author")))
    if book is not None:
        for al in book.findall("AuthorList"):
            authors.extend(_parse_author_elements(al.findall("Author")))
    article_ids={}
    for base in (doc, pub_elem.find("PubmedBookData")):
        if base is None: continue
        for ie in base.findall("ArticleIdList/ArticleId"):
            if ie.text: article_ids[ie.get("IdType") or "unknown"] = ie.text.strip()
    doi=article_ids.get("doi"); pmc_id=article_ids.get("pmc")
    if not doi and book is not None:
        for eid in book.findall("ELocationID"):
            if eid.get("EIdType") == "doi" and eid.text:
                doi=eid.text.strip(); article_ids.setdefault("doi",doi)
    pubdate_el=book.find("PubDate") if book is not None else None
    pub_date=parse_pubmed_date_element(pubdate_el) if pubdate_el is not None else PubDateModel(date_source="Fallback")
    if pub_date: pub_date.date_source = "Book/PubDate"
    history=pub_elem.find("PubmedBookData/History")
    pubmed_dates={}
    if history is not None:
        for ppd in history.findall("PubMedPubDate"):
            status=ppd.get("PubStatus") or "unknown"; parsed=parse_pubmed_date_element(ppd)
            if parsed:
                parsed.date_source=f"History_{status}"; pubmed_dates[status]=parsed
    languages=[x.text.strip() for x in doc.findall("Language") if x.text]
    pub_types=[x.text.strip() for x in doc.findall("PublicationType") if x.text]
    keywords=[x.text.strip() for x in doc.findall("KeywordList/Keyword") if x.text]
    grants=[]
    for grant in doc.findall("GrantList/Grant"):
        grants.append({
            "grant_id": (grant.findtext("GrantID") or "").strip() or None,
            "acronym": (grant.findtext("Acronym") or "").strip() or None,
            "agency": (grant.findtext("Agency") or "").strip() or None,
            "country": (grant.findtext("Country") or "").strip() or None,
        })
    references=[]
    for ref in pub_elem.findall("PubmedBookData/ReferenceList/Reference"):
        ids={}
        for rid in ref.findall("ArticleIdList/ArticleId"):
            if rid.text: ids[rid.get("IdType") or "unknown"] = rid.text.strip()
        references.append({"citation":(ref.findtext("Citation") or "").strip() or None,"article_ids":ids})
    status=(pub_elem.findtext("PubmedBookData/PublicationStatus") or "").strip() or None
    raw_xml=ET.tostring(pub_elem,encoding="unicode")
    source_hash=hashlib.sha256(raw_xml.encode("utf-8")).hexdigest()
    book_metadata={}
    if book is not None:
        publisher=book.find("Publisher")
        book_metadata={
            "book_title": title if article_title is None else ("".join(book_title_el.itertext()).strip() if book_title_el is not None else None),
            "collection_title": (book.findtext("CollectionTitle") or "").strip() or None,
            "publisher_name": (publisher.findtext("PublisherName") or "").strip() or None if publisher is not None else None,
            "publisher_location": (publisher.findtext("PublisherLocation") or "").strip() or None if publisher is not None else None,
            "isbn": [x.text.strip() for x in book.findall("Isbn") if x.text],
            "medium": (book.findtext("Medium") or "").strip() or None,
            "report_number": (book.findtext("ReportNumber") or "").strip() or None,
        }
    return PubMedRecordFull(
        record_type="book_article", pmid=pmid, version=version, doi=doi, pmc_id=pmc_id,
        title=title, abstract=abstract, abstract_sections=abstract_sections, authors=authors,
        journal=book_metadata.get("book_title"), pub_date=pub_date, pubmed_pub_dates=pubmed_dates,
        publication_types=pub_types, languages=languages, keywords=keywords, grants=grants,
        article_ids=article_ids, references=references, publication_status=status, book_metadata=book_metadata,
        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        source_record_sha256=source_hash, retrieved_at=datetime.now(timezone.utc), raw_xml=raw_xml
    )

def parse_single_article(pub_elem) -> Optional[PubMedRecordFull]:
    medline_citation = pub_elem.find("MedlineCitation")
    if medline_citation is None:
        return None
    
    pmid_elem = medline_citation.find("PMID")
    pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else None
    if not pmid:
        return None
    
    article = medline_citation.find("Article")
    if article is None:
        return None
    
    # Title
    title_elem = article.find("ArticleTitle")
    title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
    
    # Abstract with sections
    abstract_text = ""
    abstract_sections = []
    abstract_elem = article.find("Abstract")
    if abstract_elem is not None:
        texts = []
        for abs_text_elem in abstract_elem.findall("AbstractText"):
            label = abs_text_elem.get("Label") or abs_text_elem.get("NlmCategory") or ""
            txt = "".join(abs_text_elem.itertext()).strip()
            if txt:
                texts.append(txt)
                if label:
                    abstract_sections.append({"label": label, "text": txt})
        abstract_text = " ".join(texts)
    
    # Authors: preserve collective names, all affiliations and identifiers (e.g. ORCID).
    author_list = article.find("AuthorList")
    authors = _parse_author_elements(author_list.findall("Author")) if author_list is not None else []

    # Journal
    journal_elem = article.find("Journal")
    journal_title = None
    journal_abbrev = None
    issn = None
    volume = None
    issue = None
    if journal_elem is not None:
        jt = journal_elem.find("Title")
        if jt is not None:
            journal_title = jt.text
        ja = journal_elem.find("ISOAbbreviation")
        if ja is not None:
            journal_abbrev = ja.text
        issn_el = journal_elem.find("ISSN")
        if issn_el is not None:
            issn = issn_el.text
        ji = journal_elem.find("JournalIssue")
        if ji is not None:
            v = ji.find("Volume")
            if v is not None:
                volume = v.text
            iss = ji.find("Issue")
            if iss is not None:
                issue = iss.text
    
    # Pages
    pages = None
    pagination = article.find("Pagination")
    if pagination is not None:
        mn = pagination.find("MedlinePgn")
        if mn is not None:
            pages = mn.text
    
    # DOI / IDs
    doi = None
    pmc_id = None
    article_ids = {}
    for id_elem in pub_elem.findall("PubmedData/ArticleIdList/ArticleId"):
        id_type = id_elem.get("IdType") or "unknown"
        if id_elem.text:
            value = id_elem.text.strip()
            article_ids[id_type] = value
            if id_type == "doi":
                doi = value
            elif id_type == "pmc":
                pmc_id = value
    # Some records expose DOI as ELocationID even when ArticleIdList is sparse.
    if not doi:
        for eid in article.findall("ELocationID"):
            if eid.get("EIdType") == "doi" and eid.text:
                doi = eid.text.strip(); article_ids.setdefault("doi", doi)
    
    # MeSH: one descriptor may carry multiple qualifiers; preserve them all.
    mesh_headings = []
    for mh in medline_citation.findall("MeshHeadingList/MeshHeading"):
        d = mh.find("DescriptorName")
        if d is None:
            continue
        qs = mh.findall("QualifierName")
        qualifiers = [{
            "name": (q.text or "").strip(),
            "ui": q.get("UI"),
            "major_topic": q.get("MajorTopicYN") == "Y",
        } for q in qs]
        q = qs[0] if qs else None
        mesh_headings.append(MeshHeadingModel(
            descriptor_name=(d.text or "").strip(),
            descriptor_ui=d.get("UI"),
            qualifier_name=(q.text or "").strip() if q is not None else None,
            qualifier_ui=q.get("UI") if q is not None else None,
            qualifiers=qualifiers,
            major_topic=(d.get("MajorTopicYN") == "Y") or any(x["major_topic"] for x in qualifiers)
        ))
    
    # Keywords
    keywords = []
    for kw_list in medline_citation.findall(".//KeywordList"):
        for kw in kw_list.findall("Keyword"):
            if kw.text:
                keywords.append(kw.text.strip())
    
    # Publication Types
    pub_types = []
    for pt in article.findall("PublicationTypeList/PublicationType"):
        if pt.text:
            pub_types.append(pt.text.strip())

    languages = [x.text.strip() for x in article.findall("Language") if x.text]
    chemicals = []
    for chem in medline_citation.findall("ChemicalList/Chemical"):
        name = chem.find("NameOfSubstance")
        reg = chem.find("RegistryNumber")
        chemicals.append({
            "registry_number": reg.text.strip() if reg is not None and reg.text else None,
            "name": (name.text or "").strip() if name is not None else None,
            "ui": name.get("UI") if name is not None else None,
        })
    grants = []
    for grant in article.findall("GrantList/Grant"):
        grants.append({
            "grant_id": (grant.findtext("GrantID") or "").strip() or None,
            "acronym": (grant.findtext("Acronym") or "").strip() or None,
            "agency": (grant.findtext("Agency") or "").strip() or None,
            "country": (grant.findtext("Country") or "").strip() or None,
        })
    references = []
    for ref in pub_elem.findall("PubmedData/ReferenceList/Reference"):
        ids = {}
        for rid in ref.findall("ArticleIdList/ArticleId"):
            if rid.text:
                ids[rid.get("IdType") or "unknown"] = rid.text.strip()
        references.append({"citation": (ref.findtext("Citation") or "").strip() or None, "article_ids": ids})
    publication_status = (pub_elem.findtext("PubmedData/PublicationStatus") or "").strip() or None
    
    # Dates - CRITICAL FIX with fallback
    best_date = get_best_pub_date(article, pub_elem.find("PubmedData/History"))
    # ArticleDate separate
    article_date_elem = article.find("ArticleDate")
    article_date_model = parse_pubmed_date_element(article_date_elem) if article_date_elem is not None else None
    
    # PubMed PubDates
    pubmed_pub_dates_dict = {}
    history = pub_elem.find("PubmedData/History")
    if history is not None:
        for ppd in history.findall("PubMedPubDate"):
            status = ppd.get("PubStatus") or "unknown"
            model = parse_pubmed_date_element(ppd)
            if model:
                model.date_source = f"History_{status}"
                pubmed_pub_dates_dict[status] = model
    
    # Date created/completed/revised
    def parse_medline_date_str(elem_name):
        el = medline_citation.find(elem_name)
        if el is None:
            return None
        try:
            y = int(el.find("Year").text) if el.find("Year") is not None else 1
            m = int(el.find("Month").text) if el.find("Month") is not None and el.find("Month").text.isdigit() else 1
            d = int(el.find("Day").text) if el.find("Day") is not None and el.find("Day").text.isdigit() else 1
            return datetime(y,m,d)
        except (AttributeError, TypeError, ValueError):
            return None
    
    date_created = parse_medline_date_str("DateCreated")
    date_completed = parse_medline_date_str("DateCompleted")
    date_revised = parse_medline_date_str("DateRevised")
    
    raw_xml = ET.tostring(pub_elem, encoding="unicode")
    source_record_sha256 = hashlib.sha256(raw_xml.encode("utf-8")).hexdigest()

    return PubMedRecordFull(
        record_type="journal_article",
        pmid=pmid,
        doi=doi,
        pmc_id=pmc_id,
        title=title,
        abstract=abstract_text,
        abstract_sections=abstract_sections,
        authors=authors,
        journal=journal_title,
        journal_abbrev=journal_abbrev,
        journal_issn=issn,
        volume=volume,
        issue=issue,
        pages=pages,
        pub_date=best_date,
        article_date=article_date_model,
        pubmed_pub_dates=pubmed_pub_dates_dict,
        date_created=date_created,
        date_completed=date_completed,
        date_revised=date_revised,
        mesh_headings=mesh_headings,
        keywords=keywords,
        publication_types=pub_types,
        languages=languages,
        chemicals=chemicals,
        grants=grants,
        article_ids=article_ids,
        references=references,
        publication_status=publication_status,
        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        source_record_sha256=source_record_sha256,
        retrieved_at=datetime.now(timezone.utc),
        raw_xml=raw_xml
    )


# ==================== MAX EXTRACTION ORCHESTRATOR ====================

class PubMedSourceExtractor:
    """Lossless PubMed source extractor for a configured research-domain query set."""
    
    # Retrieval scope only. No interpretive or destructive post-filter is applied.
    DEFAULT_DOMAIN_QUERIES = [
        # Primary MeSH - high precision
        'Anesthesia[mh]',
        'Anesthetics[mh]',
        'Anesthesiology[mh]',
        'Anesthesia and Analgesia[mh]',
        'Anesthesia, General[mh] OR Anesthesia, Inhalation[mh] OR Anesthesia, Intravenous[mh]',
        # Secondary MeSH with keyword for recall
        '(Anesthesia, Conduction[mh] OR Anesthesia, Epidural[mh] OR Anesthesia, Spinal[mh])',
        # High-precision keyword + MeSH filter
        '("general anesthesia" OR "regional anesthesia" OR "spinal anesthesia" OR "epidural anesthesia")[tiab] AND (Anesthesia[mh] OR Anesthetics[mh])',
    ]
    
    def __init__(self, client: RateLimitedPubMedClient):
        self.client = client
    
    def extract_max(self, query_overrides: Optional[List[str]] = None,
                    mindate: Optional[str] = None, maxdate: Optional[str] = None,
                    max_ids_per_query: Optional[int] = None) -> List[PubMedRecordFull]:
        """Extract all query candidates, failing closed on source incompleteness.

        ``max_ids_per_query`` is an explicit user cap. Any cap that excludes source
        records is recorded as TRUNCATED in ``last_extraction_meta``.
        """
        queries = query_overrides or self.DEFAULT_DOMAIN_QUERIES
        all_pmids: Set[str] = set()
        pmid_queries: Dict[str, Set[str]] = {}
        query_meta: List[Dict] = []
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        for q in queries:
            logger.info(f"ESearch complete: {q} (mindate={mindate}, maxdate={maxdate}, cap={max_ids_per_query})")
            pmids, meta = self.client.esearch_all(
                q, mindate=mindate, maxdate=maxdate, max_ids=max_ids_per_query
            )
            query_meta.append(meta)
            all_pmids.update(pmids)
            for pmid in pmids:
                pmid_queries.setdefault(str(pmid), set()).add(q)
            logger.info(f"  -> {len(pmids)}/{meta['expected_count']} PMIDs" + (" [TRUNCATED]" if meta['truncated'] else ""))

        pmid_list = sorted(all_pmids, key=lambda x: int(x) if x.isdigit() else x)
        logger.info(f"Total unique PMIDs across queries: {len(pmid_list)}")

        records: List[PubMedRecordFull] = []
        parsed_pmids: Set[str] = set()
        for i in range(0, len(pmid_list), 500):
            chunk = pmid_list[i:i+500]
            logger.info(f"EFetch batch {i//500+1}/{max(1, (len(pmid_list)-1)//500+1)} - {len(chunk)} PMIDs")
            xml_str = self.client.efetch_xml(chunk, retmax=500)
            batch_records = parse_pubmed_xml(xml_str, strict=True)
            returned = {str(rec.pmid) for rec in batch_records if rec.pmid}
            requested = set(chunk)
            missing = requested - returned
            unexpected = returned - requested
            if missing or unexpected:
                raise RuntimeError(
                    f"PubMed EFetch reconciliation failed: missing={sorted(missing)[:10]} "
                    f"unexpected={sorted(unexpected)[:10]} requested={len(requested)} returned={len(returned)}"
                )
            parsed_pmids.update(returned)

            for rec in batch_records:
                rec.run_id = run_id
                rec.retrieval_queries = sorted(pmid_queries.get(str(rec.pmid), set()))
                rec.retrieval_query = rec.retrieval_queries[0] if len(rec.retrieval_queries) == 1 else None
                records.append(rec)

        if parsed_pmids != set(pmid_list):
            raise RuntimeError(
                f"PubMed extraction completeness mismatch: union_ids={len(pmid_list)}, parsed={len(parsed_pmids)}"
            )
        any_truncated = any(m.get("truncated") for m in query_meta)
        self.last_extraction_meta = {
            "manifest_schema_version": "frontier-run-manifest-1.0",
            "run_id": run_id,
            "source": "pubmed",
            "mode": "esearch_efetch_domain_candidates",
            "status": "completed",
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "parser_version": "pubmed-canonical-3.0",
            "canonical_schema_version": "pubmed-record-3.0",
            "query_diagnostics": query_meta,
            "queries": list(queries),
            "query_count": len(queries),
            "mindate": mindate,
            "maxdate": maxdate,
            "union_pmid_count": len(pmid_list),
            "observed_records": len(pmid_list),
            "valid_records": len(parsed_pmids),
            "unique_records": len(parsed_pmids),
            "parsed_pmid_count": len(parsed_pmids),
            "returned_record_count": len(records),
            "max_ids_per_query": max_ids_per_query,
            "truncated": any_truncated,
            "complete_against_source": not any_truncated and len(parsed_pmids) == len(pmid_list),
            "certification_status": "TRUNCATED" if any_truncated else "PASS",
            "warnings": [],
            "errors": [],
        }
        logger.info(
            f"Final source candidate set: {len(records)} records (from {len(pmid_list)} source PMIDs); "
            f"status={self.last_extraction_meta['certification_status']}"
        )
        return records
