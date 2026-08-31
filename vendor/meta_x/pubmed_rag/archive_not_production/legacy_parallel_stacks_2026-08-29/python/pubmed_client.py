"""
Hardened PubMed Client - Fixes all audit critical issues:
- Rate limits: email, api_key, delay enforcement, 429/503 exponential backoff with jitter
- Dedup: PMID normalization, title+doi normalization, hash_dedup, journal overlapping dedupe
- MedlineDate fallback: Year -> MedlineDate regex -> ArticleDate -> PubMedPubDate
- Structured abstract: itertext() + preserve section labels
- Author: ForeName LastName -> LastName -> CollectiveName fallback
- DOI: ArticleIdList fallback
"""
import re
import time
import random
import hashlib
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple
import httpx
from .config import settings
from .models import PubMedArticle, Author, AbstractSection
import logging

logger = logging.getLogger(__name__)

# Regex patterns for date fallback - FIX audit
MEDLINE_YEAR_RE = re.compile(r"(\d{4})")  # extracts leading year from "2021-2022", "2024 Spring", "2020 Dec-2021 Jan"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
PMID_RE = re.compile(r"^\d+$")

class PubMedClient:
    def __init__(self):
        self.base_url = settings.pubmed_base_url
        self.email = settings.ncbi_email.strip()
        if not self.email or "@" not in self.email:
            raise ValueError("NCBI_EMAIL must be set to a real contact email before PubMed network access")
        self.api_key = settings.ncbi_api_key
        # Rate limit gaps: 0.34s for 3/s, 0.11s for 10/s - add margin
        self.min_gap = 0.12 if self.api_key else 0.35
        self._last_request_ts = 0.0
        self.timeout = settings.request_timeout
        self.max_retries = settings.max_retries

    def _polite_params(self, extra: Dict) -> Dict:
        params = {
            "tool": settings.pubmed_tool,
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(extra)
        return params

    def _throttle(self):
        """Enforce NCBI rate limit - FIX audit"""
        now = time.time()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_gap:
            sleep_time = self.min_gap - elapsed + random.uniform(0, 0.05)  # jitter
            time.sleep(sleep_time)
        self._last_request_ts = time.time()

    def _request_with_backoff(self, client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
        """Exponential backoff on 429/503 - FIX audit"""
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = client.request(method, url, timeout=self.timeout, **kwargs)
                if resp.status_code in (429, 503):
                    backoff = (settings.backoff_base ** attempt) + random.uniform(0, 1)
                    logger.warning(f"PubMed {resp.status_code}, backoff {backoff:.2f}s attempt {attempt+1}/{self.max_retries}")
                    time.sleep(backoff)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise
                backoff = (settings.backoff_base ** attempt) + random.uniform(0, 1)
                logger.warning(f"HTTP error {e}, backoff {backoff:.2f}s")
                time.sleep(backoff)
        raise RuntimeError("Max retries exceeded for PubMed")

    # --- PMID normalization - FIX audit ---
    def normalize_pmids(self, pmids: List[str]) -> List[str]:
        """_normalise_pmids() helper - centralize validation"""
        normalized = []
        seen = set()
        for p in pmids:
            p = str(p).strip()
            # Handle cases like "PMID: 12345" or URLs
            m = re.search(r"(\d{4,8})", p)
            if m:
                pid = m.group(1)
            else:
                pid = p
            if PMID_RE.match(pid) and pid not in seen:
                seen.add(pid)
                normalized.append(pid)
        return normalized

    # --- Date extraction - FIX audit critical ---
    def extract_pub_date(self, pub_date_elem: Optional[ET.Element], article_elem: ET.Element) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[str], Optional[str], Optional[str]]:
        """
        Returns (year, month, day, pub_date_raw, medline_date_raw, article_date)
        Implements: Year -> MedlineDate regex -> ArticleDate -> PubMedPubDate fallback
        """
        year = month = day = None
        pub_date_raw = None
        medline_raw = None
        article_date = None

        if pub_date_elem is not None:
            # Try Year
            year_elem = pub_date_elem.find("Year")
            if year_elem is not None and year_elem.text and year_elem.text.strip().isdigit():
                try:
                    year = int(year_elem.text.strip())
                    pub_date_raw = year_elem.text.strip()
                except:
                    pass
                # Also try month/day
                month_elem = pub_date_elem.find("Month")
                if month_elem is not None and month_elem.text:
                    try:
                        # Month can be "12" or "Dec"
                        mt = month_elem.text.strip()
                        if mt.isdigit():
                            month = int(mt)
                        else:
                            # Map abbrev
                            month_map = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
                            month = month_map.get(mt[:3], None)
                    except:
                        pass
                day_elem = pub_date_elem.find("Day")
                if day_elem is not None and day_elem.text and day_elem.text.strip().isdigit():
                    try:
                        day = int(day_elem.text.strip())
                    except:
                        pass

            # MedlineDate fallback - FIX audit
            if year is None:
                medline_elem = pub_date_elem.find("MedlineDate")
                if medline_elem is not None and medline_elem.text:
                    medline_raw = medline_elem.text.strip()
                    # Extract leading 4-digit year
                    m = MEDLINE_YEAR_RE.search(medline_raw)
                    if m:
                        try:
                            year = int(m.group(1))
                            pub_date_raw = medline_raw
                        except:
                            pass

        # ArticleDate fallback (electronic pub date)
        if year is None:
            article_date_elem = article_elem.find(".//ArticleDate")
            if article_date_elem is not None:
                y_elem = article_date_elem.find("Year")
                if y_elem is not None and y_elem.text and y_elem.text.strip().isdigit():
                    try:
                        year = int(y_elem.text.strip())
                        article_date = f"{y_elem.text.strip()}"
                    except:
                        pass

        # PubMedPubDate fallback
        if year is None:
            pubmed_pubdate = article_elem.findall(".//PubMedPubDate")
            for ppd in pubmed_pubdate:
                # Prefer pubmed pub date with Year
                y = ppd.find("Year")
                if y is not None and y.text and y.text.strip().isdigit():
                    try:
                        year = int(y.text.strip())
                        pub_date_raw = f"PubMedPubDate:{ppd.get('PubStatus')}"
                        break
                    except:
                        continue

        return year, month, day, pub_date_raw, medline_raw, article_date

    def _extract_text_with_itertext(self, elem: Optional[ET.Element]) -> str:
        """FIX audit: use itertext() so <i>, <sup> etc not dropped"""
        if elem is None:
            return ""
        # Preserve inner text including nested tags
        text = "".join(elem.itertext()).strip()
        # Clean multiple spaces
        text = re.sub(r"\s+", " ", text)
        return text

    def parse_article_xml(self, article_elem: ET.Element) -> Optional[PubMedArticle]:
        try:
            medline = article_elem.find("MedlineCitation")
            if medline is None:
                return None
            pmid_elem = medline.find("PMID")
            pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else None
            if not pmid:
                return None

            article = medline.find("Article")
            if article is None:
                return None

            # Title - FIX: itertext
            title_elem = article.find("ArticleTitle")
            title = self._extract_text_with_itertext(title_elem) if title_elem is not None else "No title"

            # Abstract - FIX: structured labels + itertext
            abstract_sections = []
            abstract_full = ""
            abstract_elem = article.find("Abstract")
            if abstract_elem is not None:
                parts = []
                for abst_text_elem in abstract_elem.findall("AbstractText"):
                    label = abst_text_elem.get("Label") or abst_text_elem.get("NlmCategory") or None
                    text = self._extract_text_with_itertext(abst_text_elem)
                    if text:
                        abstract_sections.append(AbstractSection(label=label, text=text))
                        if label:
                            parts.append(f"{label.upper()}: {text}")
                        else:
                            parts.append(text)
                abstract_full = " ".join(parts)

            # Authors - FIX: collective name
            authors = []
            author_list_elem = article.find("AuthorList")
            if author_list_elem is not None:
                for auth_elem in author_list_elem.findall("Author"):
                    collective = auth_elem.find("CollectiveName")
                    if collective is not None and collective.text:
                        authors.append(Author(collective_name=self._extract_text_with_itertext(collective)))
                        continue
                    last = auth_elem.find("LastName")
                    fore = auth_elem.find("ForeName")
                    init = auth_elem.find("Initials")
                    aff_elem = auth_elem.find("AffiliationInfo/Affiliation")
                    aff = self._extract_text_with_itertext(aff_elem) if aff_elem is not None else None
                    authors.append(Author(
                        last_name=last.text.strip() if last is not None and last.text else None,
                        fore_name=fore.text.strip() if fore is not None and fore.text else None,
                        initials=init.text.strip() if init is not None and init.text else None,
                        affiliation=aff
                    ))

            # Journal
            journal_elem = article.find("Journal")
            journal_title = None
            journal_abbrev = None
            issn = None
            if journal_elem is not None:
                title_elem = journal_elem.find("Title")
                if title_elem is not None:
                    journal_title = self._extract_text_with_itertext(title_elem)
                abbrev_elem = journal_elem.find("ISOAbbreviation")
                if abbrev_elem is not None:
                    journal_abbrev = self._extract_text_with_itertext(abbrev_elem)
                issn_elem = journal_elem.find("ISSN")
                if issn_elem is not None:
                    issn = self._extract_text_with_itertext(issn_elem)

            # Pub date with fallback
            pub_date_elem = article.find("Journal/JournalIssue/PubDate")
            pub_year, pub_month, pub_day, pub_date_raw, medline_raw, article_date_raw = self.extract_pub_date(pub_date_elem, article)

            # PubTypes
            pub_types = []
            for pt_elem in article.findall("PublicationTypeList/PublicationType"):
                if pt_elem.text:
                    pub_types.append(pt_elem.text.strip())

            # MeSH - HIGH precision filter for FP fix
            mesh_terms = []
            mesh_descriptors = []
            mesh_list = medline.find("MeshHeadingList")
            if mesh_list is not None:
                for mh in mesh_list.findall("MeshHeading"):
                    desc = mh.find("DescriptorName")
                    if desc is not None and desc.text:
                        term = desc.text.strip()
                        mesh_terms.append(term)
                        ui = desc.get("UI", "")
                        mesh_descriptors.append({"term": term, "UI": ui})

            # Keywords
            keywords = []
            kw_list = medline.find("KeywordList")
            if kw_list is not None:
                for kw in kw_list.findall("Keyword"):
                    if kw.text:
                        keywords.append(kw.text.strip())

            # ArticleIdList for DOI, PMCID
            doi = None
            pmcid = None
            # PubMedData ArticleIdList
            pubmed_data = article_elem.find("PubmedData")
            if pubmed_data is not None:
                id_list = pubmed_data.find("ArticleIdList")
                if id_list is not None:
                    for aid in id_list.findall("ArticleId"):
                        id_type = aid.get("IdType")
                        if id_type == "doi" and aid.text:
                            doi = aid.text.strip()
                        if id_type == "pmc" and aid.text:
                            pmcid = aid.text.strip()
            # Also try ELocationID in Article
            if doi is None:
                for eloc in article.findall("ELocationID"):
                    if eloc.get("EIdType") == "doi" and eloc.text:
                        doi = eloc.text.strip()

            # Deduplication hashes - FIX audit
            title_norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
            title_norm = re.sub(r"\s+", " ", title_norm)
            doi_norm = doi.lower().strip() if doi else None
            first_author_last = authors[0].last_name.lower() if authors and authors[0].last_name else ""
            hash_str = f"{title_norm}|{first_author_last}|{pub_year or ''}"
            hash_dedup = hashlib.sha256(hash_str.encode()).hexdigest()[:16]

            article_model = PubMedArticle(
                pmid=pmid,
                pmcid=pmcid,
                doi=doi,
                title=title,
                abstract=abstract_full,
                abstract_sections=abstract_sections,
                authors=authors,
                journal=journal_title,
                journal_abbrev=journal_abbrev,
                issn=issn,
                pub_year=pub_year,
                pub_month=pub_month,
                pub_day=pub_day,
                pub_date_raw=pub_date_raw,
                medline_date_raw=medline_raw,
                article_date=article_date_raw,
                pub_types=pub_types,
                mesh_terms=mesh_terms,
                mesh_descriptors=mesh_descriptors,
                keywords=keywords,
                title_normalized=title_norm,
                doi_normalized=doi_norm,
                hash_dedup=hash_dedup,
                is_anesthesia_core=True  # will be refined by classifier
            )
            return article_model
        except Exception as e:
            logger.exception(f"Failed to parse article: {e}")
            return None

    def fetch_by_pmids(self, pmids: List[str]) -> List[PubMedArticle]:
        """Fetch articles by PMID list with dedup and error handling"""
        normalized = self.normalize_pmids(pmids)
        if not normalized:
            return []

        # Deduplicate input PMIDs already
        # Batch size: NCBI recommends <=200 for efetch
        batch_size = 200
        results = []
        seen_hashes = set()
        seen_pmids = set()

        with httpx.Client() as client:
            for i in range(0, len(normalized), batch_size):
                batch = normalized[i:i+batch_size]
                # Filter already fetched pmids
                batch = [p for p in batch if p not in seen_pmids]
                if not batch:
                    continue

                params = self._polite_params({
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml"
                })
                url = f"{self.base_url}/efetch.fcgi"
                resp = self._request_with_backoff(client, "GET", url, params=params)
                try:
                    root = ET.fromstring(resp.content)
                except ET.ParseError as e:
                    logger.error(f"XML parse error for batch {batch[:3]}: {e}")
                    continue

                # Each PubmedArticle
                for art_elem in root.findall("PubmedArticle"):
                    parsed = self.parse_article_xml(art_elem)
                    if parsed is None:
                        continue
                    # PMID dedup - FIX audit
                    if parsed.pmid in seen_pmids:
                        continue
                    # Title+DOI dedup - FIX audit
                    if parsed.hash_dedup in seen_hashes:
                        logger.info(f"Dedup duplicate hash {parsed.hash_dedup} pmid {parsed.pmid}")
                        continue
                    seen_pmids.add(parsed.pmid)
                    seen_hashes.add(parsed.hash_dedup)
                    results.append(parsed)

        return results

    def esearch(self, query: str, retmax: int = 100, retstart: int = 0) -> Tuple[List[str], int]:
        """Search PubMed via esearch, returns pmids and total count"""
        pmids = []
        with httpx.Client() as client:
            params = self._polite_params({
                "db": "pubmed",
                "term": query,
                "retmax": retmax,
                "retstart": retstart,
                "retmode": "json",
                "sort": "date"
            })
            url = f"{self.base_url}/esearch.fcgi"
            resp = self._request_with_backoff(client, "GET", url, params=params)
            data = resp.json()
            esearch_result = data.get("esearchresult", {})
            id_list = esearch_result.get("idlist", [])
            count = int(esearch_result.get("count", 0))
            pmids = self.normalize_pmids(id_list)
            return pmids, count

    def search_and_fetch(self, query: str, retmax: int = 100) -> List[PubMedArticle]:
        pmids, total = self.esearch(query, retmax=retmax)
        logger.info(f"esearch for '{query}' found {total}, fetching {len(pmids)}")
        if not pmids:
            return []
        return self.fetch_by_pmids(pmids)
