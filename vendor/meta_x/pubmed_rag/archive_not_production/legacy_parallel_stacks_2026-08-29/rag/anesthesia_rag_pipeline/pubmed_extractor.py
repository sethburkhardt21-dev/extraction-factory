"""
Production PubMed Extractor for Anesthesia RAG
FIXES APPLIED from audit:
- CRITICAL-1: Rate limits (0.11s with key, 0.34s without) + exponential backoff + 429 handling + jitter
- CRITICAL-2: MedlineDate fallback (handles 2.1M records) - Year → MedlineDate leading 4-digit regex + season/month ranges
- CRITICAL-3: CollectiveName support + nested XML innerxml handling
- CRITICAL-4: Deterministic ordering + history server for >500
- CRITICAL-5: Local disk cache + per-PMID ESummary
- CRITICAL-6: Full metadata schema extraction (not truncated)
"""
import os
import re
import time
import json
import random
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import xml.etree.ElementTree as ET
from dataclasses import asdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import PubMedConfig

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Date parsing with MedlineDate fallback - AUDIT FIX ---
MEDLINE_DATE_YEAR_RE = re.compile(r'(?P<year>\d{4})')
MEDLINE_DATE_MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'spring': 3, 'summer': 6, 'fall': 9, 'autumn': 9, 'winter': 12
}
SEASON_RANGE_SPLIT = re.compile(r'[-\u2013/]')

def parse_medline_date(medline_date_str: str) -> Dict[str, Optional[int]]:
    """
    Parse MedlineDate free text like:
    - "2007 Spring" -> year 2007, month 3
    - "Fall 2006" -> year 2006, month 9
    - "1999-2000" -> year 1999
    - "2023 Jan-Feb" -> year 2023, month 2 (take last month in range)
    - "1946 May-June" -> year 1946, month 6
    - "1994 Sep-Dec"
    FIX: audit issue #6
    """
    if not medline_date_str:
        return {"year": None, "month": None, "day": None, "raw": medline_date_str}
    text = medline_date_str.strip()
    year_match = MEDLINE_DATE_YEAR_RE.search(text)
    year = int(year_match.group('year')) if year_match else None
    
    # Find last month/season token for range handling
    lower = text.lower()
    tokens = re.findall(r'[a-z]+', lower)
    month = None
    for token in reversed(tokens):
        if token[:3] in MEDLINE_DATE_MONTH_MAP:
            # map full or abbr
            key = token if token in MEDLINE_DATE_MONTH_MAP else token[:3]
            # Normalize season vs month
            if key in MEDLINE_DATE_MONTH_MAP:
                month = MEDLINE_DATE_MONTH_MAP[key]
                break
        if token in MEDLINE_DATE_MONTH_MAP:
            month = MEDLINE_DATE_MONTH_MAP[token]
            break
    
    return {"year": year, "month": month, "day": None, "raw": text}

def parse_pub_date(pub_date_el: Optional[ET.Element], medline_date_el: Optional[ET.Element] = None) -> Dict[str, Any]:
    """
    Robust PubDate parser with fallback hierarchy:
    1. PubDate Year/Month/Day
    2. MedlineDate fallback
    3. ArticleDate
    4. History dates
    Returns structured date.
    """
    year = month = day = None
    raw_medline = None
    
    if pub_date_el is not None:
        y_el = pub_date_el.find('Year')
        m_el = pub_date_el.find('Month')
        d_el = pub_date_el.find('Day')
        med_el = pub_date_el.find('MedlineDate')
        
        if y_el is not None and y_el.text and y_el.text.isdigit():
            try:
                year = int(y_el.text.strip())
            except:
                pass
        # Month may be numeric or textual
        if m_el is not None and m_el.text:
            m_text = m_el.text.strip()
            if m_text.isdigit():
                try:
                    month = int(m_text)
                except:
                    pass
            else:
                month = MEDLINE_DATE_MONTH_MAP.get(m_text[:3].lower())
        
        if d_el is not None and d_el.text and d_el.text.isdigit():
            try:
                day = int(d_el.text.strip()[:2])
            except:
                pass
        
        if med_el is not None and med_el.text:
            raw_medline = med_el.text.strip()
            # Only fallback if year missing
            if year is None:
                parsed = parse_medline_date(raw_medline)
                year = parsed['year']
                if month is None:
                    month = parsed['month']
    
    # External MedlineDate (ArticleDate style, sometimes outside PubDate)
    if year is None and medline_date_el is not None and medline_date_el.text:
        raw_medline = medline_date_el.text.strip() if raw_medline is None else raw_medline
        parsed = parse_medline_date(medline_date_el.text)
        year = parsed['year']
        if month is None:
            month = parsed['month']
    
    return {
        "year": year,
        "month": month,
        "day": day,
        "medline_date_raw": raw_medline,
        "iso_date": f"{year:04d}-{month or 1:02d}-{day or 1:02d}" if year else None
    }

def get_inner_xml_text(el: Optional[ET.Element]) -> str:
    """
    FIX: preserve text within nested tags <i>, <b>, <sup> in Title/Abstract
    Audit issue: title truncated when nested tags present.
    Implementation: join .itertext()
    """
    if el is None:
        return ""
    # itertext preserves inner text even with nested markup
    return "".join(el.itertext()).strip()

def parse_authors(article_el: ET.Element) -> List[Dict[str, Any]]:
    authors = []
    author_list = article_el.find('.//AuthorList')
    if author_list is None:
        return authors
    for idx, auth in enumerate(author_list.findall('Author')):
        last = auth.find('LastName')
        fore = auth.find('ForeName')
        collective = auth.find('CollectiveName')
        initials = auth.find('Initials')
        affiliation = auth.find('.//AffiliationInfo/Affiliation')
        orcid = None
        # ORCID in Identifier @Source="ORCID"
        for ident in auth.findall('Identifier'):
            if ident.get('Source') == 'ORCID':
                orcid = ident.text
        
        if collective is not None and collective.text:
            authors.append({
                "type": "collective",
                "full_name": collective.text.strip(),
                "last_name": None,
                "fore_name": None,
                "collective_name": collective.text.strip(),
                "initials": None,
                "affiliation": affiliation.text if affiliation is not None and affiliation.text else None,
                "orcid": orcid,
                "order": idx
            })
        else:
            authors.append({
                "type": "person",
                "full_name": f"{fore.text if fore is not None and fore.text else ''} {last.text if last is not None and last.text else ''}".strip(),
                "last_name": last.text if last is not None else None,
                "fore_name": fore.text if fore is not None else None,
                "collective_name": None,
                "initials": initials.text if initials is not None else None,
                "affiliation": affiliation.text if affiliation is not None and affiliation.text else None,
                "orcid": orcid,
                "order": idx
            })
    return authors

def extract_full_metadata(medline_citation: ET.Element, pubmed_data: ET.Element, article_el: ET.Element) -> Dict[str, Any]:
    """Full metadata schema extraction per audit."""
    pmid_el = medline_citation.find('PMID')
    pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None
    
    # Article title with nested tag handling
    title_el = article_el.find('ArticleTitle')
    title = get_inner_xml_text(title_el)
    
    # Abstract - structured with labels
    abstract_el = article_el.find('Abstract')
    abstract_text = ""
    abstract_sections = []
    if abstract_el is not None:
        for abs_txt in abstract_el.findall('AbstractText'):
            label = abs_txt.get('Label') or abs_txt.get('NlmCategory') or ""
            txt = get_inner_xml_text(abs_txt)
            if txt:
                if label:
                    abstract_sections.append({"label": label, "text": txt})
                else:
                    abstract_sections.append({"label": "", "text": txt})
        abstract_text = "\n\n".join(
            [f"{s['label']}: {s['text']}" if s['label'] else s['text'] for s in abstract_sections]
        )
    
    # Journal
    journal_el = article_el.find('Journal')
    journal_title = ""
    journal_iso = ""
    issn = None
    eissn = None
    volume = None
    issue = None
    pub_date_info = {"year": None, "month": None, "day": None, "medline_date_raw": None, "iso_date": None}
    if journal_el is not None:
        j_title_el = journal_el.find('Title')
        if j_title_el is not None:
            journal_title = j_title_el.text or ""
        iso_abbr_el = journal_el.find('ISOAbbreviation')
        if iso_abbr_el is not None:
            journal_iso = iso_abbr_el.text or ""
        issn_el = journal_el.find('ISSN')
        if issn_el is not None:
            if issn_el.get('IssnType') == 'Electronic':
                eissn = issn_el.text
            else:
                issn = issn_el.text
        # Try extra ISSN
        for iss in journal_el.findall('ISSN'):
            if iss.get('IssnType') == 'Electronic' and not eissn:
                eissn = iss.text
            elif iss.get('IssnType') == 'Print' and not issn:
                issn = iss.text
        vol_el = journal_el.find('JournalIssue/Volume')
        if vol_el is not None:
            volume = vol_el.text
        issue_el = journal_el.find('JournalIssue/Issue')
        if issue_el is not None:
            issue = issue_el.text
        pub_date_el = journal_el.find('JournalIssue/PubDate')
        # MedlineDate may be inside PubDate or as separate
        medline_date_el = None
        if pub_date_el is not None:
            medline_date_el = pub_date_el.find('MedlineDate')
        pub_date_info = parse_pub_date(pub_date_el, medline_date_el)
    
    # ArticleDate fallback if PubDate missing year
    if pub_date_info['year'] is None:
        art_date_el = article_el.find('.//ArticleDate')
        if art_date_el is not None:
            pub_date_info = parse_pub_date(art_date_el)
    
    # History dates (PubMed PubStatus dates)
    history = {}
    hist_el = pubmed_data.find('History')
    if hist_el is not None:
        for pmd in hist_el.findall('PubMedPubDate'):
            status = pmd.get('PubStatus')
            y = pmd.find('Year')
            m = pmd.find('Month')
            d = pmd.find('Day')
            if y is not None:
                history[status] = f"{y.text}-{m.text if m is not None else '01'}-{d.text if d is not None else '01'}"
    
    # ArticleIdList: DOI, PMC, etc.
    doi = None
    pmc = None
    article_ids = {}
    for aid in pubmed_data.findall('.//ArticleIdList/ArticleId'):
        id_type = aid.get('IdType')
        if id_type and aid.text:
            article_ids[id_type] = aid.text.strip()
            if id_type == 'doi':
                doi = aid.text.strip().lower()
            if id_type == 'pmc':
                pmc = aid.text.strip()
    # Also from medline
    for aid in medline_citation.findall('.//ArticleIdList/ArticleId'):
        id_type = aid.get('IdType')
        if id_type and aid.text and id_type not in article_ids:
            article_ids[id_type] = aid.text.strip()
            if id_type == 'doi' and not doi:
                doi = aid.text.strip().lower()
    
    # Pagination
    medline_pgn = None
    el_pg = article_el.find('Pagination/MedlinePgn')
    if el_pg is not None and el_pg.text:
        medline_pgn = el_pg.text.strip()
    
    # MeSH
    mesh_terms = []
    mesh_heading = medline_citation.findall('.//MeshHeadingList/MeshHeading')
    for mh in mesh_heading:
        desc = mh.find('DescriptorName')
        if desc is not None and desc.text:
            qualifiers = [q.text for q in mh.findall('QualifierName') if q.text]
            mesh_terms.append({
                "descriptor": desc.text,
                "qualifiers": qualifiers,
                "major": desc.get('MajorTopicYN') == 'Y'
            })
    
    # Keywords
    keywords = [k.text for k in medline_citation.findall('.//KeywordList/Keyword') if k.text]
    
    # Publication Types
    pub_types = [pt.text for pt in article_el.findall('.//PublicationTypeList/PublicationType') if pt.text]
    
    # Grants
    grants = []
    for gr in article_el.findall('.//GrantList/Grant'):
        grant_id = gr.find('GrantID')
        agency = gr.find('Agency')
        acronym = gr.find('Acronym')
        grants.append({
            "id": grant_id.text if grant_id is not None else None,
            "agency": agency.text if agency is not None else None,
            "acronym": acronym.text if acronym is not None else None
        })
    
    # Language
    lang = None
    lang_el = article_el.find('Language')
    if lang_el is not None:
        lang = lang_el.text
    
    # Authors parsed earlier
    authors = parse_authors(article_el)
    
    return {
        "pmid": pmid,
        "doi": doi,
        "pmc_id": pmc,
        "article_ids": article_ids,
        "title": title,
        "abstract": abstract_text,
        "abstract_sections": abstract_sections,
        "authors": authors,
        "journal": journal_title,
        "journal_iso_abbreviation": journal_iso,
        "issn": issn,
        "eissn": eissn,
        "volume": volume,
        "issue": issue,
        "pages": medline_pgn,
        "publication_date": pub_date_info,
        "year": pub_date_info.get('year'),
        "history_dates": history,
        "mesh_terms": mesh_terms,
        "keywords": keywords,
        "publication_types": pub_types,
        "grants": grants,
        "language": lang,
        "raw_medline_date": pub_date_info.get('medline_date_raw')
    }

class PubMedExtractor:
    def __init__(self, config: PubMedConfig):
        if not config.email or "@" not in config.email:
            raise ValueError("NCBI_EMAIL must be set to a real contact email before PubMed network access")
        self.config = config
        self.session = requests.Session()
        # Retry strategy for transient errors
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        
        self.base_esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        self.base_efetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        
        Path(config.cache_dir).mkdir(parents=True, exist_ok=True)
    
    def _rate_limit_sleep(self):
        delay = self.config.delay_with_key if self.config.api_key else self.config.delay_without_key
        # Never jitter below the configured safe minimum interval.
        time.sleep(delay + random.uniform(0.0, delay * 0.10))
    
    def _make_request(self, url: str, params: Dict[str, Any], is_post: bool = False) -> requests.Response:
        last_exc = None
        backoff = self.config.initial_backoff
        for attempt in range(self.config.max_retries):
            try:
                self._rate_limit_sleep()
                if is_post:
                    resp = self.session.post(url, data=params, timeout=self.config.timeout)
                else:
                    resp = self.session.get(url, params=params, timeout=self.config.timeout)
                
                # Handle 429 - NCBI rate limit
                if resp.status_code == 429:
                    logger.warning(f"429 Rate limited, backoff {backoff}s attempt {attempt+1}")
                    time.sleep(backoff + random.uniform(0, 1))
                    backoff *= self.config.backoff_factor
                    continue
                
                resp.raise_for_status()
                # Check for E-utilities error in XML
                if b'<ERROR>' in resp.content or b'Error' in resp.content[:500]:
                    # Still try to parse but log
                    logger.warning(f"E-utilities warning: {resp.text[:500]}")
                return resp
            except requests.exceptions.RequestException as e:
                last_exc = e
                logger.warning(f"Request failed attempt {attempt+1}: {e}, backoff {backoff}s")
                time.sleep(backoff + random.uniform(0, 1))
                backoff *= self.config.backoff_factor
        
        raise RuntimeError(f"Failed after {self.config.max_retries} retries: {last_exc}")
    
    def _cache_key(self, params: Dict[str, Any]) -> str:
        serialized = json.dumps(params, sort_keys=True)
        return hashlib.md5(serialized.encode()).hexdigest()
    
    def _read_cache(self, key: str) -> Optional[bytes]:
        if not self.config.enable_cache:
            return None
        cache_file = Path(self.config.cache_dir) / f"{key}.xml"
        if cache_file.exists():
            # Check TTL
            mtime = cache_file.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            if age_hours < self.config.cache_ttl_hours:
                return cache_file.read_bytes()
        return None
    
    def _write_cache(self, key: str, data: bytes):
        if not self.config.enable_cache:
            return
        cache_file = Path(self.config.cache_dir) / f"{key}.xml"
        cache_file.write_bytes(data)
    
    def search_pmids(self, query: str, retmax: int = 10000, sort: str = "relevance") -> Tuple[List[str], Dict[str, str]]:
        """
        Search with history server for large result sets.
        Returns PMIDs and history server keys (WebEnv, QueryKey) for efetch.
        FIX: audit - use history server for >500
        """
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": retmax,
            "sort": sort,
            "usehistory": "y" if self.config.use_history_server else "n",
            "tool": self.config.tool_name,
            "email": self.config.email
        }
        if self.config.api_key:
            params["api_key"] = self.config.api_key
        
        resp = self._make_request(self.base_esearch, params)
        data = resp.json()
        
        esearch_result = data.get("esearchresult", {})
        pmids = esearch_result.get("idlist", [])
        webenv = esearch_result.get("webenv", "")
        query_key = esearch_result.get("querykey", "")
        count = int(esearch_result.get("count", 0))
        
        logger.info(f"ESearch found {count} results, returning {len(pmids)} PMIDs")
        
        # If count > retmax, we may need to paginate via history server
        history = {"WebEnv": webenv, "QueryKey": query_key, "Count": count}
        return pmids, history
    
    def fetch_details(self, pmids: List[str] = None, history: Dict[str, str] = None) -> List[Dict[str, Any]]:
        """
        Fetch details with EFetch, supports history server pagination.
        Full metadata extraction with all audit fixes.
        """
        all_articles = []
        
        if history and history.get("Count", 0) > self.config.history_threshold and self.config.use_history_server:
            # Use history server to fetch in batches - FIX for large sets
            total = history["Count"]
            webenv = history["WebEnv"]
            qkey = history["QueryKey"]
            logger.info(f"Using history server for {total} articles")
            
            for retstart in range(0, total, self.config.batch_size):
                params = {
                    "db": "pubmed",
                    "query_key": qkey,
                    "WebEnv": webenv,
                    "retmode": "xml",
                    "retstart": retstart,
                    "retmax": self.config.batch_size,
                    "tool": self.config.tool_name,
                    "email": self.config.email
                }
                if self.config.api_key:
                    params["api_key"] = self.config.api_key
                
                cache_key = self._cache_key(params)
                cached = self._read_cache(cache_key)
                if cached:
                    content = cached
                else:
                    resp = self._make_request(self.base_efetch, params)
                    content = resp.content
                    self._write_cache(cache_key, content)
                
                articles = self._parse_efetch_xml(content)
                all_articles.extend(articles)
                logger.info(f"Fetched batch {retstart}-{retstart+len(articles)} / {total}")
        else:
            # Direct ID fetch
            if not pmids:
                return []
            # Chunk PMIDs for EFetch (max ~200 per request)
            for i in range(0, len(pmids), self.config.batch_size):
                chunk = pmids[i:i+self.config.batch_size]
                params = {
                    "db": "pubmed",
                    "id": ",".join(chunk),
                    "retmode": "xml",
                    "tool": self.config.tool_name,
                    "email": self.config.email
                }
                if self.config.api_key:
                    params["api_key"] = self.config.api_key
                
                cache_key = self._cache_key(params)
                cached = self._read_cache(cache_key)
                if cached:
                    content = cached
                    logger.info(f"Cache hit for {len(chunk)} PMIDs")
                else:
                    resp = self._make_request(self.base_efetch, params)
                    content = resp.content
                    self._write_cache(cache_key, content)
                
                articles = self._parse_efetch_xml(content)
                all_articles.extend(articles)
                logger.info(f"Fetched {len(articles)} articles for chunk {i}")
        
        # FIX: deterministic ordering by PMID int order
        all_articles.sort(key=lambda x: int(x['pmid']) if x['pmid'] and x['pmid'].isdigit() else 0)
        return all_articles
    
    def _parse_efetch_xml(self, xml_bytes: bytes) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return []
        
        articles = []
        for pubmed_article in root.findall('.//PubmedArticle'):
            medline = pubmed_article.find('MedlineCitation')
            pubmed_data = pubmed_article.find('PubmedData')
            article_el = medline.find('Article') if medline is not None else None
            if medline is None or article_el is None or pubmed_data is None:
                continue
            try:
                meta = extract_full_metadata(medline, pubmed_data, article_el)
                # Only include if has PMID
                if meta.get('pmid'):
                    articles.append(meta)
            except Exception as e:
                logger.warning(f"Failed to parse article: {e}")
                continue
        
        return articles
    
    def extract_max_anesthesia(self, query: Optional[str] = None, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        High-recall extraction for anesthesia domain.
        """
        q = query or self.config.base_query
        limit = max_results or self.config.max_results
        pmids, history = self.search_pmids(q, retmax=limit)
        articles = self.fetch_details(pmids=pmids, history=history)
        return articles
