import re

from bs4 import BeautifulSoup

from app.adapters.base_playwright_adapter import BasePlaywrightAdapter
from app.core.content_hash import compute_content_hash

# Generic extraction (section scanning, deadline/amount/degree parsing) now lives in
# app/adapters/scholarship_extraction.py so Chevening and Stipendium Hungaricum can
# reuse the regexes that were tuned against real live pages here (BUG-010b). The
# behaviour is unchanged -- this module's tests, including the two transcribed from
# the real detail=50026200 page, are what prove that.
from app.adapters.scholarship_extraction import (
    DEADLINE_LABELS,
    ELIGIBILITY_LABELS,
    GPA_RE,
    IELTS_RE,
    VALUE_LABELS,
    extract_award_amount,
    extract_deadline,
    extract_degree_level,
    extract_eligibility,
    extract_numeric_field,
    lines_from,
    section_text_after_label,
)


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

        lines = lines_from(text_content)

        record = {
            "name": name,
            "provider": "DAAD",
            "source_url": url,
            "country": self.country,
            "degree_level": extract_degree_level(text_content, name),
            "award_amount": extract_award_amount(section_text_after_label(lines, VALUE_LABELS)),
            "deadline": extract_deadline(section_text_after_label(lines, DEADLINE_LABELS)),
            "eligibility": extract_eligibility(section_text_after_label(lines, ELIGIBILITY_LABELS)),
            "citizenship_eligible": True,
            "min_gpa": extract_numeric_field(text_content, GPA_RE),
            "min_ielts": extract_numeric_field(text_content, IELTS_RE),
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
