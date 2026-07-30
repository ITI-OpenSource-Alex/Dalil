"""MastersPortal adapter — API-driven discovery, page-based document extraction.

DISCOVERY MECHANISM (verified live, 2026-07-25 — do not "simplify" back to HTML scraping):
The /search/... HTML pages are an SPA. Their server-rendered markup contains a
"featured programmes" module whose 20 cards IGNORE the discipline/region filter in the
URL (observed: fashion, counselling, paramedicine cards on a computer-science search).
Scraping anchors from that HTML is how off-scope programs polluted program_requirements.
The page's real result list comes from the site's own public JSON endpoint:

    GET https://search-api.prtl.co/programmes/search
        ?educationalLevels=master&disciplines=<id>&resultSize=20&resultOffset=<n>

which this adapter now calls directly. Discipline ids come from the site's own
sitemap (sitemaps/disciplines.xml): 7 = Engineering & Technology, 24 = Computer
Science & IT. The API has no working region parameter (probed), so Europe scoping
is applied client-side via each card's getCountryIsoCode against EUROPE_ISO below —
region and disciplines therefore remain configuration, per GOA-111's scope decision.

Program pages themselves are still fetched (politely, robots-checked) for document
text and the application deadline; card fields take precedence for identity and
numeric requirements because they are structured at the source.
"""

import datetime
import re

import httpx
import structlog
from bs4 import BeautifulSoup

from app.adapters.base_playwright_adapter import BasePlaywrightAdapter
from app.core.content_hash import compute_content_hash
from app.core.batch import BatchBudget
from app.core.crawl_state import CrawlStateManager, crawl_state
from app.core.rate_limiter import polite_delay
from app.core.robots import robot_checker
from app.core.url_normalizer import normalize_url

logger = structlog.get_logger(__name__)

_PROGRAMME_URL_RE = re.compile(r"/studies/\d+/")
_DEADLINE_LABEL_RE = re.compile(r"^application deadline$", re.IGNORECASE)
_COUNTRY_RE = re.compile(r"^Study in\s+(.+)$", re.IGNORECASE)
_IELTS_LABEL_RE = re.compile(r"^ielts$", re.IGNORECASE)
_ECTS_LABEL_RE = re.compile(r"^ects$", re.IGNORECASE)
_GPA_LABEL_RE = re.compile(r"^gpa$", re.IGNORECASE)
_NUMERIC_LINE_RE = re.compile(r"^\d+(\.\d+)?$")
_STRICT_NUMBER_RE = re.compile(r"^\d+(\.\d+)?$")

# A standalone-line label marking the start of a *different* field's section;
# _find_numeric_after_label() stops there instead of using a blind window, so a
# field with no numeric value can't pick up a neighboring section's number.
_SECTION_BOUNDARY_LABELS = {
    "ielts", "toefl", "gpa", "ects", "pte academic",
    "english requirements", "academic requirements", "admission requirements",
    "key information",
}

SEARCH_API = "https://search-api.prtl.co/programmes/search"
PAGE_SIZE = 20

# Region/discipline scope is configuration (GOA-111): edit these, not the parser.
DISCIPLINE_IDS = {
    "engineering": 7,        # sitemaps/disciplines.xml -> /disciplines/7/engineering-technology.html
    "computer_science": 24,  # -> /disciplines/24/computer-science-it.html
}

# ISO 3166-1 alpha-2 -> country name, European scope for the GOA catalog.
EUROPE_ISO = {
    "AL": "Albania", "AD": "Andorra", "AT": "Austria", "BA": "Bosnia and Herzegovina",
    "BE": "Belgium", "BG": "Bulgaria", "BY": "Belarus", "CH": "Switzerland",
    "CY": "Cyprus", "CZ": "Czech Republic", "DE": "Germany", "DK": "Denmark",
    "EE": "Estonia", "ES": "Spain", "FI": "Finland", "FR": "France",
    "GB": "United Kingdom", "GE": "Georgia", "GR": "Greece", "HR": "Croatia",
    "HU": "Hungary", "IE": "Ireland", "IS": "Iceland", "IT": "Italy",
    "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro", "MK": "North Macedonia",
    "MT": "Malta", "NL": "Netherlands", "NO": "Norway", "PL": "Poland",
    "PT": "Portugal", "RO": "Romania", "RS": "Serbia", "SE": "Sweden",
    "SI": "Slovenia", "SK": "Slovakia", "SM": "San Marino", "UA": "Ukraine",
}


def parse_deadline(date_str: str | None) -> datetime.date | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            pass
    return None


# The canonical degree vocabulary the RAG scoring gate compares against.
_DEGREE_LEVEL_CANON = {
    "master": "Master", "masters": "Master", "pre-master": "Master",
    "bachelor": "Bachelor", "bachelors": "Bachelor",
    "phd": "PhD", "doctorate": "PhD",
}


def _normalize_degree_level(value) -> str | None:
    """Map an API level/degree string onto the canonical vocabulary, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower().rstrip(".")
    if key in _DEGREE_LEVEL_CANON:
        return _DEGREE_LEVEL_CANON[key]
    # Display abbreviations: M.Sc./MSc/M.A./M.Eng. are all master's level.
    compact = key.replace(".", "").replace(" ", "")
    if compact.startswith("m") and len(compact) <= 5:
        return "Master"
    if compact.startswith("b") and len(compact) <= 5:
        return "Bachelor"
    return None


def _as_number(value) -> float | None:
    """Coerce a card value to a number, or None — never a guess.

    The API's numeric-looking fields are not uniformly numeric. getEcts is an int,
    but getGPA is an IGPARequirement object whose score may be a non-numeric grade
    classification, e.g. {"getScale": "uk_honours", "getScore": "2_2"}. Feeding that
    object to the RAG schema produced 422s on every UK program. Per GOA-111's
    null-discipline, an unrepresentable value stays null instead of being converted
    into an invented GPA.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        inner = value.get("func", value)
        return _as_number(inner.get("getScore")) if isinstance(inner, dict) else None
    if isinstance(value, str):
        # Strict pattern, not bare float(): Python treats '_' as a digit separator,
        # so float('2_2') == 22.0 — a UK 2:2 honours grade would silently become a
        # GPA of 22. Only plain decimal numbers are accepted.
        return float(value.strip()) if _STRICT_NUMBER_RE.match(value.strip()) else None
    return None


def _card_field(card: dict, *path, default=None):
    """Walk the API's nested {'func': {...}} card shape: _card_field(c, 'getEnglishRequirements', 'getIELTS')."""
    node = card
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
        if isinstance(node, dict) and "func" in node:
            node = node["func"]
        if node is None:
            return default
    return node


class MastersPortalAdapter(BasePlaywrightAdapter):
    def __init__(
        self,
        crawl_state_manager: CrawlStateManager | None = None,
        budget: BatchBudget | None = None,
    ):
        super().__init__(
            base_url="https://www.mastersportal.com",
            target_url="https://www.mastersportal.com/search/master/engineering-and-technology/europe",
            source_name="masters_portal",
            category="universities",
            country="Europe",
            wait_selector="body",
        )
        self._crawl_state_manager = crawl_state_manager
        self.budget = budget

    @property
    def crawl_state(self) -> CrawlStateManager:
        # Resolve the legacy singleton lazily so existing direct-adapter tests can
        # replace it, while the canonical runner injects an invocation-scoped manager.
        return self._crawl_state_manager or crawl_state

    # ------------------------------------------------------------------ discovery

    async def discover_page(self, discipline_id: int, offset: int) -> tuple[list[dict], int]:
        """One API result page. Returns (cards, hits_total). Cards are raw 'func' dicts."""
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Origin": "https://www.mastersportal.com",
                "Referer": "https://www.mastersportal.com/",
            },
        ) as client:
            resp = await client.get(SEARCH_API, params={
                "educationalLevels": "master",
                "disciplines": str(discipline_id),
                "resultSize": PAGE_SIZE,
                "resultOffset": offset,
                "sortBy": "default",
            })
            resp.raise_for_status()
            data = resp.json()
        cards = [p["card"]["func"] for p in data.get("programmes", []) if p.get("card")]
        return cards, int(data.get("hitsTotal", 0))

    @staticmethod
    def card_in_scope(card: dict) -> bool:
        return _card_field(card, "getCountryIsoCode") in EUROPE_ISO

    def card_to_url(self, card: dict) -> str | None:
        rel = _card_field(card, "getProgrammeLink", "getUrl")
        if not rel:
            return None
        return normalize_url(self.base_url + rel if rel.startswith("/") else rel)

    # ------------------------------------------------------------------ extraction

    def extract_documents(self, html: str, url: str = None, university: str = None,
                          card: dict | None = None, discipline: str | None = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []

        main_content = soup.find(id="UniversityProfile") or soup.find("main") or soup.find("body")
        if not main_content:
            return documents

        text_content = main_content.get_text(separator="\n", strip=True)
        effective_url = normalize_url(url or self.target_url)
        doc = {
            "source": self.source_name,
            "category": self.category,
            "country": (EUROPE_ISO.get(_card_field(card, "getCountryIsoCode")) if card else None) or self.country,
            "url": effective_url,
            "source_url": effective_url,
            "content": text_content,
        }

        if _PROGRAMME_URL_RE.search(effective_url):
            record = self._build_record(soup, text_content, effective_url, university, card, discipline)
            if record:
                doc["program_requirements"] = [record]

        documents.append(doc)
        return documents

    def _build_record(self, soup: BeautifulSoup, text_content: str, url: str,
                      university: str | None, card: dict | None,
                      discipline: str | None = None) -> dict | None:
        """Card fields win (structured at source); page parsing is the fallback."""
        lines = text_content.split("\n")

        iso = _card_field(card, "getCountryIsoCode") if card else None
        record = {
            "university": (_card_field(card, "getUniversityLink", "getDescription") if card else None)
                          or university or self._extract_university_name(soup),
            "country": (EUROPE_ISO.get(iso) if iso else None) or self._extract_country(lines),
            # getLevel is the API's canonical enum ('master'); getDegree is a display
            # name ('M.Sc.', 'M.A.', 'Pre-Master'). The scoring gate compares
            # degree_level by exact string, so display names blocked 33 of 46 programs
            # with "Requires M.Sc. degree" — normalize to the canonical vocabulary.
            "degree_level": _normalize_degree_level(
                (_card_field(card, "getLevel") if card else None)
                or (_card_field(card, "getDegree") if card else None)
            ) or "Master",
            "program_name": (_card_field(card, "getTitle") if card else None)
                            or self._extract_title(soup),
            "deadline": parse_deadline(self._find_string_after_label(lines, _DEADLINE_LABEL_RE)),
            "min_ects": _as_number(_card_field(card, "getEcts") if card else None)
                        or self._find_numeric_after_label(lines, _ECTS_LABEL_RE),
            "min_gpa": _as_number(_card_field(card, "getGPA") if card else None)
                       or self._find_numeric_after_label(lines, _GPA_LABEL_RE),
            "min_ielts": _as_number(_card_field(card, "getEnglishRequirements", "getIELTS") if card else None)
                         or self._find_numeric_after_label(lines, _IELTS_LABEL_RE),
            "required_citizenship": None,
            "min_work_experience": _as_number(_card_field(card, "getWorkExperienceYears") if card else None),
            "source_url": normalize_url(url),
            # Which configured search bucket found this program. /match pre-filters on
            # it (migration 022); NULL stays eligible rather than being hidden.
            "discipline": discipline,
        }

        # Null-tolerant quality gate: identity is required, numerics/deadline are not.
        # country IS identity here — 'Europe' placeholder rows broke the Profile
        # Matcher's visa-finance join, so a record needs a real country, never the
        # region literal.
        if not record["program_name"] or not record["university"] or not record["source_url"] \
                or not record["country"] or record["country"].strip().lower() == "europe":
            logger.warning("quality_gate_rejected", url=url, reason="missing_identity")
            return None

        if isinstance(record["deadline"], datetime.date):
            record["deadline"] = record["deadline"].isoformat()

        record["content_hash"] = compute_content_hash(record)
        return record

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str | None:
        """Page-fallback title. StudyTitle spans nest the name twice on some pages
        (observed: 'Generative AIGenerative AI') — take the deepest single text node."""
        study_title = soup.find("span", class_="StudyTitle")
        if study_title:
            texts = [t.strip() for t in study_title.stripped_strings]
            if texts:
                title = texts[0]
                # collapse exact doubling, e.g. 'Data ScienceData Science'
                half = len(title) // 2
                if len(title) % 2 == 0 and title[:half] == title[half:]:
                    title = title[:half]
                return title
        h1 = soup.find("h1")
        return h1.get_text(strip=True) if h1 else None

    @staticmethod
    def _extract_country(lines: list[str]) -> str | None:
        for line in lines:
            match = _COUNTRY_RE.search(line.strip())
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _find_numeric_after_label(lines: list[str], label_pattern: re.Pattern, lookahead: int = 8) -> float | None:
        for i, line in enumerate(lines):
            if not label_pattern.match(line.strip()):
                continue
            for candidate in lines[i + 1: i + 1 + lookahead]:
                candidate_stripped = candidate.strip()
                if _NUMERIC_LINE_RE.match(candidate_stripped):
                    return float(candidate_stripped)
                if candidate_stripped.lower() in _SECTION_BOUNDARY_LABELS:
                    break
        return None

    @staticmethod
    def _find_string_after_label(lines: list[str], label_pattern: re.Pattern, lookahead: int = 4) -> str | None:
        for i, line in enumerate(lines):
            if not label_pattern.match(line.strip()):
                continue
            for candidate in lines[i + 1: i + 1 + lookahead]:
                candidate_stripped = candidate.strip()
                if candidate_stripped:
                    return candidate_stripped
        return None

    def _extract_university_name(self, soup: BeautifulSoup) -> str | None:
        header = (
            soup.find("a", class_="js-essential-info-organisation-link")
            or soup.find("span", class_="OrganisationName")
            or soup.find("a", class_="UniversityLink")
        )
        if header:
            return header.get_text(strip=True)
        title = soup.find("title")
        if title:
            match = re.search(r"\bat\s+(.*?)\s*\|", title.get_text(strip=True))
            if match:
                return match.group(1).strip()
        return None

    # ------------------------------------------------------------ tier 1: card sweep

    def _card_to_document(self, card: dict, url: str, discipline: str) -> dict | None:
        """Build a structured record and a small document from the API card alone.

        Tier 1 of the two-tier crawl. A page fetch costs ~10 seconds, so covering the
        ~20,000 in-scope catalog that way is ~55 hours — impossible inside any bounded
        worker. The card already carries everything program_requirements needs except
        the application deadline (null on every program observed so far), and its
        getSummary field is real prose, so one searchable chunk per program comes free.

        Tier 2 later fetches the page for richer document text; the deadline and the
        full requirements sections are the only things sacrificed here.
        """
        iso = _card_field(card, "getCountryIsoCode")
        country = EUROPE_ISO.get(iso)
        title = _card_field(card, "getTitle")
        university = _card_field(card, "getUniversityLink", "getDescription")
        if not (country and title and university):
            return None

        record = {
            "university": university,
            "country": country,
            "degree_level": _normalize_degree_level(
                _card_field(card, "getLevel") or _card_field(card, "getDegree")
            ) or "Master",
            "program_name": title,
            "deadline": None,  # not published on the card; Tier 2's page carries it
            "min_ects": _as_number(_card_field(card, "getEcts")),
            "min_gpa": _as_number(_card_field(card, "getGPA")),
            "min_ielts": _as_number(_card_field(card, "getEnglishRequirements", "getIELTS")),
            "required_citizenship": None,
            "min_work_experience": _as_number(_card_field(card, "getWorkExperienceYears")),
            "source_url": url,
            "discipline": discipline,
        }
        record["content_hash"] = compute_content_hash(record)

        summary = _card_field(card, "getSummary") or ""
        location = _card_field(card, "getLocationText") or country
        content = "\n".join(
            part for part in (
                f"{title} — {university} ({location})",
                f"Degree: {record['degree_level']}",
                f"IELTS requirement: {record['min_ielts']}" if record["min_ielts"] else "",
                f"ECTS: {record['min_ects']}" if record["min_ects"] else "",
                summary,
                f"Official source: {url}",
            ) if part
        )

        return {
            "source": self.source_name,
            "category": self.category,
            "country": country,
            "url": url,
            "source_url": url,
            "content": content,
            "program_requirements": [record],
        }

    async def scrape_cards(self, per_run_cap_per_discipline: int = 500) -> list[dict]:
        """Tier 1 sweep: whole catalog from the search API, no browser, no page fetch."""
        documents: list[dict] = []
        telemetry: dict[str, dict] = {}

        for discipline, discipline_id in DISCIPLINE_IDS.items():
            counts = {"discovered": 0, "skipped": 0, "extracted": 0, "failed": 0, "remaining": 0}
            if self.budget and self.budget.exhausted:
                counts["remaining"] = self.crawl_state.count_remaining(
                    self.source_name, tier=1, discipline=discipline
                ) or 1
                telemetry[discipline] = counts
                continue
            cursor = self.crawl_state.get_cursor(self.source_name, discipline)
            if cursor["exhausted"]:
                telemetry[discipline] = counts
                continue

            offset = cursor["scroll_offset"]
            hits_total = None
            produced = 0

            while produced < per_run_cap_per_discipline:
                if self.budget and self.budget.exhausted:
                    break
                await polite_delay(self.min_delay, self.max_delay)
                try:
                    cards, hits_total = await self.discover_page(discipline_id, offset)
                except Exception as e:
                    logger.error("tier1_discovery_failed", discipline=discipline,
                                 offset=offset, error=str(e))
                    counts["failed"] += 1
                    self.crawl_state.mark_cursor_failure(
                        self.source_name, discipline, str(e)
                    )
                    break
                if not cards:
                    self.crawl_state.update_cursor(
                        self.source_name,
                        discipline,
                        offset // PAGE_SIZE + 1,
                        scroll_offset=offset,
                        exhausted=True,
                        total_items=hits_total,
                    )
                    break

                page_produced = 0
                page_failed = False
                for card in cards:
                    if self.budget and self.budget.exhausted:
                        break
                    url = self.card_to_url(card)
                    if not url:
                        continue
                    if not self.card_in_scope(card):
                        counts["skipped"] += 1
                        continue
                    counts["discovered"] += 1
                    if self.crawl_state.is_url_scraped(url):
                        counts["skipped"] += 1
                        continue
                    if self.budget and not self.budget.consume():
                        break
                    doc = self._card_to_document(card, url, discipline)
                    if doc is None:
                        counts["failed"] += 1
                        page_failed = True
                        self.crawl_state.mark_url_status(
                            self.source_name,
                            discipline,
                            url,
                            "failed",
                            "card_missing_identity",
                        )
                        continue
                    documents.append(doc)
                    produced += 1
                    page_produced += 1
                    counts["extracted"] += 1
                    self.crawl_state.mark_url_status(
                        self.source_name, discipline, url, "extracted"
                    )
                    if produced >= per_run_cap_per_discipline:
                        break

                # Do not advance past work that has only been extracted. The handler
                # promotes those URLs to scraped after the RAG HTTP write succeeds.
                # A killed task therefore revisits this page, skips acknowledged rows,
                # and retries the unacknowledged ones instead of losing them.
                if page_produced or page_failed:
                    self.crawl_state.update_cursor(
                        self.source_name,
                        discipline,
                        offset // PAGE_SIZE + 1,
                        scroll_offset=offset,
                        exhausted=False,
                        total_items=hits_total,
                    )
                    break

                offset += len(cards)
                exhausted = hits_total is not None and offset >= hits_total
                self.crawl_state.update_cursor(
                    self.source_name,
                    discipline,
                    offset // PAGE_SIZE + 1,
                    scroll_offset=offset,
                    exhausted=exhausted,
                    total_items=hits_total,
                )
                if exhausted:
                    break

            counts["remaining"] = self.crawl_state.count_remaining(
                self.source_name, tier=1, discipline=discipline
            )
            telemetry[discipline] = counts
            logger.info("masters_portal_tier1_batch", discipline=discipline, **counts)

        logger.info("masters_portal_tier1_telemetry", telemetry=telemetry)
        # Publish, don't just log. Already-ingested cards are skipped HERE, before
        # chunking, so a run that correctly skipped 986 of 1000 still reported
        # skipped_chunks: 0 — the exact metric ING-03 tells an operator to check.
        # The number existed all along and died in a log line.
        self.last_run_telemetry = telemetry
        return documents

    # ------------------------------------------------------- tier 2: page enrichment

    async def scrape(self, per_run_cap_per_discipline: int = 10) -> list[dict]:
        """Resumable catalog crawl: API discovery per discipline, page fetch per program.

        Status contract (GOA-111): this adapter marks a URL 'extracted' when a
        structured record was produced, or 'failed' otherwise. Only the handler,
        after a successful RAG upsert, promotes it to 'scraped' — so an upsert
        failure is retried on the next run instead of being silently lost.
        """
        documents = []
        telemetry = {}

        for discipline, discipline_id in DISCIPLINE_IDS.items():
            counts = {"discovered": 0, "skipped": 0, "extracted": 0, "failed": 0, "remaining": 0}
            if self.budget and self.budget.exhausted:
                counts["remaining"] = self.crawl_state.count_remaining(
                    self.source_name, tier=2, discipline=discipline
                ) or 1
                telemetry[discipline] = counts
                continue
            cursor = self.crawl_state.get_cursor(self.source_name, discipline)
            if cursor["exhausted"]:
                telemetry[discipline] = counts
                continue

            offset = cursor["scroll_offset"]
            hits_total = None
            produced = 0

            while produced < per_run_cap_per_discipline:
                if self.budget and self.budget.exhausted:
                    break
                await polite_delay(self.min_delay, self.max_delay)
                try:
                    cards, hits_total = await self.discover_page(discipline_id, offset)
                except Exception as e:
                    logger.error("discovery_page_failed", discipline=discipline, offset=offset, error=str(e))
                    counts["failed"] += 1
                    self.crawl_state.mark_cursor_failure(
                        self.source_name, discipline, str(e)
                    )
                    break
                if not cards:
                    self.crawl_state.update_cursor(
                        self.source_name,
                        discipline,
                        offset // PAGE_SIZE + 1,
                        scroll_offset=offset,
                        exhausted=True,
                        total_items=hits_total,
                    )
                    break

                page_produced = 0
                page_failed = False
                for card in cards:
                    if self.budget and self.budget.exhausted:
                        break
                    p_url = self.card_to_url(card)
                    if not p_url:
                        continue
                    if not self.card_in_scope(card):
                        counts["skipped"] += 1
                        continue
                    counts["discovered"] += 1
                    # Tier 2 checks the PAGE axis: Tier 1 already marked these URLs
                    # scraped for the structured row, so reusing that flag here would
                    # skip every program and the document corpus would never grow.
                    if self.crawl_state.is_page_fetched(p_url):
                        counts["skipped"] += 1
                        continue
                    if self.budget and not self.budget.consume():
                        break
                    if not robot_checker.is_allowed(p_url):
                        counts["skipped"] += 1
                        continue
                    await polite_delay(self.min_delay, self.max_delay)
                    try:
                        programme_html = await self.fetch_page(p_url)
                        extracted = self.extract_documents(
                            programme_html, p_url, card=card, discipline=discipline
                        )
                        has_record = any(
                            d.get("program_requirements") for d in extracted
                        )
                        if has_record:
                            documents.extend(extracted)
                            produced += 1
                            page_produced += 1
                            counts["extracted"] += 1
                            self.crawl_state.mark_url_status(
                                self.source_name, discipline, p_url, "extracted"
                            )
                            self.crawl_state.mark_page_status(p_url, "extracted")
                        else:
                            counts["failed"] += 1
                            page_failed = True
                            self.crawl_state.mark_url_status(
                                self.source_name,
                                discipline,
                                p_url,
                                "failed",
                                "no_record_extracted",
                            )
                    except Exception as e:
                        counts["failed"] += 1
                        page_failed = True
                        logger.error(
                            "programme_fetch_failed", url=p_url, error=str(e)
                        )
                        self.crawl_state.mark_url_status(
                            self.source_name, discipline, p_url, "failed", str(e)
                        )

                if page_produced or page_failed:
                    self.crawl_state.update_cursor(
                        self.source_name,
                        discipline,
                        offset // PAGE_SIZE + 1,
                        scroll_offset=offset,
                        exhausted=False,
                        total_items=hits_total,
                    )
                    break

                offset += len(cards)
                exhausted = hits_total is not None and offset >= hits_total
                self.crawl_state.update_cursor(
                    self.source_name,
                    discipline,
                    offset // PAGE_SIZE + 1,
                    scroll_offset=offset,
                    exhausted=exhausted,
                    total_items=hits_total,
                )
                if exhausted:
                    break

            counts["remaining"] = self.crawl_state.count_remaining(
                self.source_name, tier=2, discipline=discipline
            )
            telemetry[discipline] = counts
            logger.info("masters_portal_batch_complete", discipline=discipline, **counts)

        logger.info("masters_portal_run_telemetry", telemetry=telemetry)
        self.last_run_telemetry = telemetry
        return documents

    async def scrape_structured(self) -> list[dict]:
        """Flattened program_requirements from a scrape() run, for tests."""
        documents = await self.scrape()
        records = []
        for doc in documents:
            records.extend(doc.get("program_requirements", []))
        return records
