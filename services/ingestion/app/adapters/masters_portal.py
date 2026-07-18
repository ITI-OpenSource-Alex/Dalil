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

_DEADLINE_LABEL_RE = re.compile(r"^application deadline$", re.IGNORECASE)
_COUNTRY_RE = re.compile(r"^Study in\s+(.+)$", re.IGNORECASE)

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
        # TODO (GOA-115 discipline filter): point discovery at MastersPortal's Engineering and Computer Science search results.
        # Verify at the live site whether the discipline filter is a URL path segment, a query param, or a facet click.
        # Extract from BOTH disciplines and merge/dedupe into one URL set before the cap.
        
        # TODO (GOA-115 pagination): rework MastersPortalAdapter.extract_urls() to walk result pages 
        # exactly the way DAADAdapter's verified fix does — but FIRST verify against the live site 
        # whether mastersportal.eu uses ?page=N URLs or infinite scroll.
        # Cap at 50 distinct program URLs TOTAL across both disciplines, dedupe, stop early when a page yields no new links.
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
            "university": self._extract_university_name(soup),
            "country": self._extract_country(lines),
            "degree_level": self._extract_degree_level(soup),
            "min_ects": self._find_numeric_after_label(lines, _ECTS_LABEL_RE),
            "min_gpa": self._find_numeric_after_label(lines, _GPA_LABEL_RE),
            "min_ielts": self._find_numeric_after_label(lines, _IELTS_LABEL_RE),
            "required_citizenship": None,
            "min_work_experience": None,
            "program_name": soup.find("h1").get_text(strip=True) if soup.find("h1") else None,
            "deadline": self._find_string_after_label(lines, _DEADLINE_LABEL_RE),
            "source_url": url,
        }
        
        has_real_data = any([
            record["min_ects"], 
            record["min_gpa"], 
            record["min_ielts"],
            record["deadline"]
        ])


        if not record["program_name"] or not has_real_data:
            logger.warning("quality_gate_rejected", url=url, reason="listing_fallback")
            return None

        record["content_hash"] = compute_content_hash(record)
        return record

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


    @staticmethod
    def _extract_country(lines: list[str]) -> str | None:
        for line in lines:
            match = _COUNTRY_RE.search(line.strip())
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _extract_degree_level(soup: BeautifulSoup) -> str | None:
        title_tag = soup.find("title")
        if not title_tag:
            return None
        match = _DEGREE_LEVEL_TITLE_RE.search(title_tag.get_text(strip=True))
        return match.group(1) if match else None

    
    def _extract_university_name(self, soup: BeautifulSoup) -> str | None:
        # E.g. find it in an <h1> or a specific class on the program page
        header = soup.find("a", class_="UniversityLink")
        return header.get_text(strip=True) if header else None

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
        """Discovery phase: Paginate through Europe-wide Engineering and CS programs."""
        search_urls = [
            "https://www.mastersportal.com/search/master/engineering-and-technology/europe",
            "https://www.mastersportal.com/search/master/computer-science-and-it/europe"
        ]


        all_programme_urls = set()


        for page in range(1, 20):
            # For each discipline, construct the paginated URL
            page_links = []
            for base_url in search_urls:
                # Append ?page=N for pages > 1
                url = base_url if page == 1 else f"{base_url}?page={page}"
                
                # Check robots.txt (good citizenship!)
                if not robot_checker.is_allowed(url):
                    continue
                    
                await polite_delay(self.min_delay, self.max_delay)


                try:
                    html = await self.fetch_page(url)

                    discovered = self._extract_matching_urls(html, _PROGRAMME_URL_RE)
                    page_links.extend(discovered)
                except Exception as e:
                    logger.error("crawl_fetch_error", url=url, error=str(e))


            if not page_links:
                break

            for link in page_links:
                all_programme_urls.add(link)
                # Stop immediately if we hit our cap
                if len(all_programme_urls) >= 50:
                    break

            if len(all_programme_urls) >= 50:
                break

        programme_urls = list(all_programme_urls)[:50]
        if not programme_urls:
            return []
            

        documents = []
        for programme_url in programme_urls:
            if not robot_checker.is_allowed(programme_url):
                continue
                
            await polite_delay(self.min_delay, self.max_delay)
            try:
                programme_html = await self.fetch_page(programme_url)
            except Exception as e:
                logger.error("crawl_fetch_error", url=programme_url, error=str(e))
                continue
            # Pass the HTML to extract_documents
            documents.extend(self.extract_documents(programme_html, programme_url))
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
