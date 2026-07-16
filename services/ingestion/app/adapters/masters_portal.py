import re

import structlog
from bs4 import BeautifulSoup

from app.adapters.base_playwright_adapter import BasePlaywrightAdapter
from app.core.content_hash import compute_content_hash
from app.core.rate_limiter import polite_delay
from app.core.robots import robot_checker

logger = structlog.get_logger(__name__)

_UNIVERSITY_URL_RE = re.compile(r"/universities/\d+/")
_PROGRAMME_URL_RE = re.compile(r"/studies/\d+/")

_IELTS_LABEL_RE = re.compile(r"^ielts$", re.IGNORECASE)
_ECTS_LABEL_RE = re.compile(r"^ects$", re.IGNORECASE)
_GPA_LABEL_RE = re.compile(r"^gpa$", re.IGNORECASE)
_NUMERIC_LINE_RE = re.compile(r"^\d+(\.\d+)?$")
_DEGREE_LEVEL_TITLE_RE = re.compile(
    r"\b(Master|Bachelor|MBA|PhD|LLM|Postgraduate Diploma|Postgraduate Certificate)\b\s+at\b",
    re.IGNORECASE,
)

# A standalone-line label that marks the start of a *different* field's section.
# _find_numeric_after_label() stops scanning as soon as it hits one of these,
# rather than a fixed lookahead window -- otherwise a field with no numeric value
# on the page (e.g. GPA sometimes resolves to a classification like "Upper Second
# Class" rather than a number) could wrongly pick up a neighboring section's number
# (e.g. a TOEFL score) just because it happened to fall within the window.
_SECTION_BOUNDARY_LABELS = {
    "ielts", "toefl", "gpa", "ects", "pte academic",
    "english requirements", "academic requirements", "admission requirements",
    "key information",
}

# Third-tier crawl safeguards. The country -> university hop already capped detail
# pages at 50 (matching BasePlaywrightAdapter.scrape()'s historical `[:50]`); with a
# university -> programme hop added on top, a per-university cap is also needed or a
# single run could attempt hundreds of programme-page fetches.
MAX_UNIVERSITIES_PER_RUN = 50
MAX_PROGRAMMES_PER_UNIVERSITY = 5


class MastersPortalAdapter(BasePlaywrightAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://www.mastersportal.com",
            # Country id 30 is the current United Kingdom listing. Id 1 (the
            # previous value here) now resolves and canonicalizes to the
            # Netherlands -- verified by inspecting the live page's <title> and
            # canonical link, not assumed from the URL slug alone.
            target_url="https://www.mastersportal.com/countries/30/united-kingdom.html",
            source_name="masters_portal",
            category="universities",
            country="UK",
            wait_selector="body"
        )

    def extract_urls(self, html: str) -> list[str]:
        """Discovers university profile page links from a country listing page."""
        return self._extract_matching_urls(html, _UNIVERSITY_URL_RE)

    def extract_programme_urls(self, html: str) -> list[str]:
        """Discovers programme (/studies/<id>/...) links from a university profile
        page. Admission-requirements fields (IELTS, GPA, ECTS, ...) live on these
        pages, not on the university profile page itself."""
        return self._extract_matching_urls(html, _PROGRAMME_URL_RE)

    @staticmethod
    def _extract_matching_urls(html: str, pattern: re.Pattern) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if pattern.search(href) and href.startswith("http"):
                if href not in urls:
                    urls.append(href)
        return urls

    def extract_documents(self, html: str, url: str = None, university: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []

        # FIX: Target specific content wrappers to avoid navigation menus
        main_content = soup.find(id="UniversityProfile") or soup.find("main")

        if main_content:
            text_content = main_content.get_text(separator="\n", strip=True)
            effective_url = url or self.target_url
            doc = {
                "source": self.source_name,
                "category": self.category,
                "country": self.country,
                "url": effective_url,
                "content": text_content,
            }

            if _PROGRAMME_URL_RE.search(effective_url):
                record = self._extract_program_requirement(soup, text_content, effective_url, university)
                if record:
                    doc["program_requirements"] = [record]

            documents.append(doc)

        return documents

    def _extract_program_requirement(
        self, soup: BeautifulSoup, text_content: str, url: str, university: str | None
    ) -> dict | None:
        """Extracts a structured program_requirements record from an already-parsed
        programme page. Conservative by design: a field is left None rather than
        guessed when the page doesn't state it unambiguously -- e.g. this adapter
        will not convert a UK degree classification ("Upper Second Class") into a
        fabricated numeric GPA, and will not treat a non-ECTS credit total (e.g.
        "180 alternative credits") as an ECTS figure."""
        lines = text_content.split("\n")

        record = {
            "university": university,
            "country": self.country,
            "degree_level": self._extract_degree_level(soup),
            "min_ects": self._find_numeric_after_label(lines, _ECTS_LABEL_RE),
            "min_gpa": self._find_numeric_after_label(lines, _GPA_LABEL_RE),
            "min_ielts": self._find_numeric_after_label(lines, _IELTS_LABEL_RE),
            "required_citizenship": None,
            "min_work_experience": None,
            "source_url": url,
        }

        if not record["university"] or not record["degree_level"]:
            # (university, degree_level, country) is program_requirements' upsert
            # key -- a record missing either can't be upserted, so don't emit it.
            return None

        record["content_hash"] = compute_content_hash(record)
        return record

    @staticmethod
    def _extract_degree_level(soup: BeautifulSoup) -> str | None:
        title_tag = soup.find("title")
        if not title_tag:
            return None
        match = _DEGREE_LEVEL_TITLE_RE.search(title_tag.get_text(strip=True))
        return match.group(1) if match else None

    @staticmethod
    def _extract_university_name(soup: BeautifulSoup) -> str | None:
        title_tag = soup.find("title")
        if not title_tag:
            return None
        # MastersPortal university-profile <title> tags follow "<Name> | <suffix>".
        name = title_tag.get_text(strip=True).split("|")[0].strip()
        return name or None

    @staticmethod
    def _find_numeric_after_label(lines: list[str], label_pattern: re.Pattern, lookahead: int = 8) -> float | None:
        """Finds a standalone label line (e.g. an "IELTS" line on its own) and scans
        forward for the first purely-numeric line, skipping the descriptive
        paragraph MastersPortal places between a label and its value. Stops early if
        it reaches another recognized section's label first, rather than risk
        attributing a neighboring section's number to the wrong field."""
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

    async def scrape(self) -> list[dict]:
        """Overrides the template method to add a third crawl tier: country ->
        university -> programme. BasePlaywrightAdapter.scrape() only supports a
        single index -> detail hop (extract_urls() is called exactly once, only on
        the initial page); the structured admission-requirements fields live one
        hop deeper than the existing country -> university crawl, on programme
        pages. Follows the same override precedent as
        GermanEmbassyCairoAdapter.scrape() rather than changing the shared
        BasePlaywrightAdapter template method, which would also affect every other
        Playwright-based adapter."""
        if not robot_checker.is_allowed(self.target_url):
            logger.warning("robots_disallowed", url=self.target_url)
            return []

        await polite_delay(self.min_delay, self.max_delay)
        country_html = await self.fetch_page(self.target_url)

        university_urls = self.extract_urls(country_html)[:MAX_UNIVERSITIES_PER_RUN]
        if not university_urls:
            return self.extract_documents(country_html, self.target_url)

        documents = []
        seen_programme_urls: set[str] = set()

        for university_url in university_urls:
            if not robot_checker.is_allowed(university_url):
                continue
            await polite_delay(self.min_delay, self.max_delay)
            try:
                university_html = await self.fetch_page(university_url)
            except Exception as e:
                logger.error("crawl_fetch_error", url=university_url, error=str(e))
                continue

            documents.extend(self.extract_documents(university_html, university_url))

            university_soup = BeautifulSoup(university_html, "lxml")
            university_name = self._extract_university_name(university_soup)

            programme_urls = self.extract_programme_urls(university_html)
            new_programme_urls = [u for u in programme_urls if u not in seen_programme_urls]

            for programme_url in new_programme_urls[:MAX_PROGRAMMES_PER_UNIVERSITY]:
                seen_programme_urls.add(programme_url)
                if not robot_checker.is_allowed(programme_url):
                    continue
                await polite_delay(self.min_delay, self.max_delay)
                try:
                    programme_html = await self.fetch_page(programme_url)
                except Exception as e:
                    logger.error("crawl_fetch_error", url=programme_url, error=str(e))
                    continue

                documents.extend(self.extract_documents(programme_html, programme_url, university_name))

        return documents

    async def scrape_structured(self) -> list[dict]:
        """Returns only the flattened program_requirements records discovered
        during a full scrape() run, for direct testability against fixture HTML
        without needing to inspect full document dicts."""
        documents = await self.scrape()
        records = []
        for doc in documents:
            records.extend(doc.get("program_requirements", []))
        return records
