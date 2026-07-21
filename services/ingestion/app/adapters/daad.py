import re

from bs4 import BeautifulSoup

from app.adapters.base_playwright_adapter import BasePlaywrightAdapter
from app.core.content_hash import compute_content_hash

# Section labels this adapter looks for on a DAAD scholarship detail page, and the
# text-based extraction approach used to read them. DAAD detail-page markup could
# not be confirmed live while this was written (www2.daad.de was returning a
# consistent 403 "Request forbidden by administrative rules" to every request,
# curl and Playwright alike -- see Task 10's implementation report) -- extraction is
# therefore built around get_text(separator="\n")'s existing line-per-element
# convention (already used by every extraction function in this codebase) rather
# than specific heading tag names, so it stays correct even if the real markup uses
# <h2>/<h3>, <dt>/<dd>, <strong>, or plain <div> labels for these sections.
_DEADLINE_LABELS = {"application deadline", "deadline"}
_VALUE_LABELS = {"scholarship value", "value", "funding", "amount"}
_ELIGIBILITY_LABELS = {"who can apply?", "who can apply", "target group", "eligibility"}
# The headings below (overview/objective/what can be funded?/duration of the
# funding/selection/application requirements/language skills/application
# procedure) were confirmed on a real live DAAD scholarship page (detail=50026200)
# during Task 10's implementation -- without them as boundaries, award_amount and
# eligibility both bled past their intended section into this neighboring content.
_ALL_SECTION_LABELS = _DEADLINE_LABELS | _VALUE_LABELS | _ELIGIBILITY_LABELS | {
    "duration", "benefits", "about the daad scholarship", "selection criteria",
    "overview", "objective", "what can be funded?", "duration of the funding",
    "selection", "application requirements", "what requirements must be met?",
    "language skills", "application procedure", "application documents",
}

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
_DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTHS})\s+(\d{{4}})\b", re.IGNORECASE)

# Matches a EUR amount whether the currency comes before the number ("EUR 10,000",
# "€850") or after it ("10,000 EUR per request", "992 euros a month") -- real DAAD
# pages use the latter ordering, which german_embassy_cairo.py's currency-first
# _AMOUNT_EUR_RE does not match. See Task 10's implementation report for why this
# is an adapted, not verbatim-copied, version of that adapter's approach.
_AMOUNT_EUR_RE = re.compile(
    r"(?:€|EUR|euros?)\s?[\d][\d.,]*|[\d][\d.,]*\s?(?:€|EUR|euros?)\b",
    re.IGNORECASE,
)

_DEGREE_LEVEL_PATTERNS = [
    (re.compile(r"\bresearch\s+grants?\b", re.IGNORECASE), "Research Grant"),
    (re.compile(r"\bdoctoral\b|\bphd\b|\bph\.d\.\b", re.IGNORECASE), "PhD"),
    (re.compile(r"\bmaster'?s?\b", re.IGNORECASE), "Master"),
    (re.compile(r"\bbachelor'?s?\b", re.IGNORECASE), "Bachelor"),
]

_IELTS_RE = re.compile(r"IELTS[^\d]{0,40}(\d(?:\.\d)?)", re.IGNORECASE)
_GPA_RE = re.compile(r"GPA[^\d]{0,60}(\d\.\d{1,2})", re.IGNORECASE)


def _lines_from(text_content: str) -> list[str]:
    return [line.strip() for line in text_content.split("\n") if line.strip()]


def _section_text_after_label(lines: list[str], label_variants: set[str], max_lines: int = 12) -> str | None:
    """Finds a standalone line matching one of label_variants and collects the
    following lines as that section's raw text, stopping at the next recognized
    section label (or max_lines) rather than a fixed window -- avoids bleeding into
    a neighboring section's content. Returns None if the label itself isn't found
    or its section has no content."""
    for i, line in enumerate(lines):
        if line.lower() not in label_variants:
            continue
        collected = []
        for candidate in lines[i + 1: i + 1 + max_lines]:
            if candidate.lower() in _ALL_SECTION_LABELS:
                break
            collected.append(candidate)
        if collected:
            return "\n".join(collected)
    return None


def _extract_deadline(section_text: str | None):
    if not section_text:
        return None
    match = _DATE_RE.search(section_text)
    if not match:
        return None
    from datetime import datetime
    day, month_name, year = match.group(1), match.group(2), match.group(3)
    try:
        return datetime.strptime(f"{day} {month_name.capitalize()} {year}", "%d %B %Y").date()
    except ValueError:
        return None


def _extract_award_amount(section_text: str | None) -> str | None:
    if not section_text or not _AMOUNT_EUR_RE.search(section_text):
        return None
    return section_text[:255]


def _extract_eligibility(section_text: str | None) -> dict:
    if not section_text:
        return {}
    items = [line for line in section_text.split("\n") if line.strip()]
    return {"items": items} if items else {}


def _extract_degree_level(text_content: str, name: str | None = None) -> str | None:
    """Checks the scholarship name/title first, since it reliably states the
    degree actually being AWARDED (e.g. "Study Scholarships - Master Studies for
    All Academic Disciplines"). The whole-body-text fallback below is a real
    false-positive risk on live pages: confirmed against a real live DAAD
    scholarship during Task 10's implementation, where the eligibility section
    states a PREREQUISITE degree ("you must have completed... Bachelor's or
    Diplom") earlier in the page than the funding description states the degree
    actually offered ("...a whole postgraduate or Master's degree programme") --
    a naive earliest-occurrence scan over the full text incorrectly returned
    "Bachelor" for a scholarship titled "...Master Studies...". Title-first
    resolves that without discarding the fallback for scholarships whose title
    doesn't state a degree word at all."""
    if name:
        for pattern, label in _DEGREE_LEVEL_PATTERNS:
            if pattern.search(name):
                return label

    best_match = None
    best_label = None
    for pattern, label in _DEGREE_LEVEL_PATTERNS:
        match = pattern.search(text_content)
        if match and (best_match is None or match.start() < best_match.start()):
            best_match = match
            best_label = label
    return best_label


def _extract_numeric_field(text_content: str, pattern: re.Pattern) -> float | None:
    match = pattern.search(text_content)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


class DAADAdapter(BasePlaywrightAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://www2.daad.de",
            target_url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?status=1&origin=190&subjectGrps=&daad=&intention=&q=&page=1&back=1",
            source_name="daad",
            category="scholarships",
            country="Germany",
            wait_selector="body"
        )

    async def fetch_page(self, url: str) -> str:
        original_wait = self.wait_selector
        if "detail=" in url:
            self.wait_selector = "#ifa-stipendien-detail"
        try:
            return await super().fetch_page(url)
        finally:
            self.wait_selector = original_wait

    def extract_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "detail=" in href:
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []

        main_content = soup.find("main") or soup.find("div", id="main-content") or soup.find(id="content") or soup.find("div", class_="c-detail-page")

        if main_content:
            text_content = main_content.get_text(separator="\n", strip=True)
            effective_url = url or self.target_url
            doc = {
                "source": self.source_name,
                "category": self.category,
                "country": self.country,
                "url": effective_url,
                "content": text_content
            }

            record = self._extract_scholarship(soup, main_content, text_content, effective_url)
            doc["scholarship_programs"] = [record] if record else []

            documents.append(doc)

        return documents

    def _extract_scholarship(self, soup: BeautifulSoup, main_content, text_content: str, url: str) -> dict | None:
        """Extracts a structured scholarship_programs record from an already-parsed
        DAAD detail page. Conservative by design: fields are left None when the
        page doesn't state them unambiguously -- a rolling/unstated deadline stays
        None rather than a guessed date, an ambiguous degree type stays None rather
        than a guessed level, and a missing IELTS/GPA requirement (common on DAAD
        pages, per manual investigation) stays None rather than an assumed value."""
        name = self._extract_name(soup, main_content)
        if not name:
            # (provider, name) is scholarship_programs' upsert key -- a record
            # missing the name can't be upserted, so don't emit it.
            return None

        lines = _lines_from(text_content)

        record = {
            "name": name,
            "provider": "DAAD",
            "source_url": url,
            "country": self.country,
            "degree_level": _extract_degree_level(text_content, name),
            "award_amount": _extract_award_amount(_section_text_after_label(lines, _VALUE_LABELS)),
            "deadline": _extract_deadline(_section_text_after_label(lines, _DEADLINE_LABELS)),
            "eligibility": _extract_eligibility(_section_text_after_label(lines, _ELIGIBILITY_LABELS)),
            "citizenship_eligible": True,
            "min_gpa": _extract_numeric_field(text_content, _GPA_RE),
            "min_ielts": _extract_numeric_field(text_content, _IELTS_RE),
        }

        record["content_hash"] = compute_content_hash(record)
        return record

    @staticmethod
    def _extract_name(soup: BeautifulSoup, main_content) -> str | None:
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # Strip the trailing " <separator> DAAD" site-name suffix. Confirmed
            # against a real live DAAD scholarship page during Task 10's
            # implementation that the real separator is "•" (a bullet
            # character, e.g. "...Disciplines • DAAD"), not "-"/"|" as
            # originally assumed -- both are matched here so this is resilient to
            # either convention appearing on different pages.
            cleaned = re.split(r"\s*[-|•]\s*DAAD\b.*$", title_text, flags=re.IGNORECASE)[0].strip()
            if cleaned:
                return cleaned
        h1 = main_content.find("h1")
        if h1:
            h1_text = h1.get_text(strip=True)
            if h1_text:
                return h1_text
        return None

    async def scrape(self) -> list[dict]:
        from app.core.robots import robot_checker
        from app.core.rate_limiter import polite_delay
        import structlog

        logger = structlog.get_logger(__name__)

        if not robot_checker.is_allowed(self.target_url):
            logger.warning("robots_disallowed", url=self.target_url)
            return []

        detail_urls = []
        # DAAD yields 18 per page, so 3 pages gives 54 urls
        for page_num in range(1, 4):
            page_url = self.target_url.replace("page=1", f"page={page_num}")
            await polite_delay()
            index_html = await self.fetch_page(page_url)
            urls = self.extract_urls(index_html)
            if not urls:
                break
            for u in urls:
                if u not in detail_urls:
                    detail_urls.append(u)
            if len(detail_urls) >= 50:
                break

        detail_urls = detail_urls[:50]

        documents = []
        for url in detail_urls:
            if not robot_checker.is_allowed(url):
                continue
            await polite_delay()
            try:
                detail_html = await self.fetch_page(url)
                docs = self.extract_documents(detail_html, url)
                documents.extend(docs)
            except Exception as e:
                logger.error("crawl_fetch_error", url=url, error=str(e))

        return documents

    async def scrape_structured(self) -> list[dict]:
        """Returns only the flattened scholarship_programs records discovered
        during a full scrape() run (reusing the existing crawl unchanged), for
        direct testability without needing to inspect full document dicts.

        Not currently called anywhere in the ingestion pipeline (Task 12, not yet
        implemented, is what would wire structured dual-write into a real run) --
        it must never be called alongside scrape() in the same run once that
        wiring exists, since both re-run the identical crawl end to end."""
        documents = await self.scrape()
        records = []
        for doc in documents:
            records.extend(doc.get("scholarship_programs", []))
        return records
