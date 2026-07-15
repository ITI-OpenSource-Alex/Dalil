import io
import re

import httpx
import structlog
from bs4 import BeautifulSoup

from app.adapters.base_adapter import BaseAdapter
from app.core.content_hash import compute_content_hash
from app.core.rate_limiter import polite_delay
from app.core.robots import robot_checker

logger = structlog.get_logger(__name__)

# Regex heuristics for pulling genuinely-present structured facts out of page text.
# Intentionally conservative: fields stay None/empty when nothing matches rather than
# guessing, per GOA-086's "do not fabricate data" requirement.
_PROCESSING_DAYS_RE = re.compile(r"(\d+)\s*(?:-|to|–)\s*(\d+)\s*(?:working\s+)?days", re.IGNORECASE)
_AMOUNT_EUR_RE = re.compile(r"(?:€|EUR)\s?([\d.,]+)", re.IGNORECASE)
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# The embassy publishes its study-visa leaflet under a rotating /resource/blob/...
# path (e.g. ".../250210-studium-englisch-data.pdf") that changes whenever the
# document is reissued -- so the link is discovered by filename convention
# ("studium") rather than ever hardcoding a blob URL, matching StipendiumHungaricumAdapter.
_STUDY_PDF_RE = re.compile(r"studium", re.IGNORECASE)


def _is_arabic_only(soup: BeautifulSoup) -> bool:
    """Detects Arabic-only pages so they can be skipped gracefully (per GOA-086)."""
    html_tag = soup.find("html")
    if html_tag and (html_tag.get("lang") or "").lower().startswith("ar"):
        return True
    text = soup.get_text()
    arabic_count = len(_ARABIC_RE.findall(text))
    latin_count = len(_LATIN_RE.findall(text))
    return arabic_count > 20 and arabic_count > latin_count


def _extract_processing_days(text: str):
    match = _PROCESSING_DAYS_RE.search(text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _extract_amount_eur(text: str):
    match = _AMOUNT_EUR_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    # Normalize European (1.234,56) vs US (1,234.56) vs plain (1234) number
    # formats before parsing -- German/European sources conventionally use "."
    # as the thousands separator and "," as the decimal separator.
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        _, _, frac_part = raw.rpartition(",")
        raw = raw.replace(",", "") if len(frac_part) == 3 else raw.replace(",", ".")
    elif "." in raw:
        _, _, frac_part = raw.rpartition(".")
        if len(frac_part) == 3:
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _section_elements(heading):
    """Sibling elements belonging to a heading's section, up to the next h2/h3."""
    elements = []
    for sibling in heading.find_next_siblings():
        if sibling.name in ("h2", "h3"):
            break
        elements.append(sibling)
    return elements


def _text_from_elements(elements) -> str:
    parts = [el.get_text(separator="\n", strip=True) for el in elements]
    return "\n".join(part for part in parts if part)


def _list_items_from_elements(elements) -> list:
    items = []
    for el in elements:
        items.extend(li.get_text(strip=True) for li in el.find_all("li") if li.get_text(strip=True))
    return items


class GermanEmbassyCairoAdapter(BaseAdapter):
    """Scrapes German student-visa requirements published by the German Embassy in Cairo."""

    ISSUING_BODY = "German Embassy Cairo"
    VISA_TYPE_BASE = "Student Visa (National Visa - Type D)"

    def __init__(self):
        super().__init__(
            # Verified landing page (GOA-086 research): Service > Visa and Entry > Study
            # on the German Embassy Cairo's official site.
            base_url="https://kairo.diplo.de",
            target_url="https://kairo.diplo.de/eg-de/service/05-visaeinreise/2573252-2573252",
            source_name="german_embassy_cairo",
            category="visa",
            country="Germany",
            min_delay=2.0,
            max_delay=3.0,
        )

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")

        if _is_arabic_only(soup):
            return []

        main_content = soup.find("main") or soup.find("div", id="content") or soup.find("body")
        if not main_content:
            return []

        text_content = main_content.get_text(separator="\n", strip=True)
        if not text_content:
            return []

        page_url = url or self.target_url
        visa_requirements = self._extract_visa_requirements(main_content, text_content, page_url)

        return [{
            "source": self.source_name,
            "category": self.category,
            "country": self.country,
            "url": page_url,
            "content": text_content,
            "visa_requirements": visa_requirements,
        }]

    def _extract_visa_requirements(self, main_content, full_text: str, url: str) -> list[dict]:
        headings = main_content.find_all(["h2", "h3"])

        if len(headings) >= 2:
            records = []
            for heading in headings:
                elements = _section_elements(heading)
                section_text = _text_from_elements(elements)
                if not section_text:
                    continue
                heading_text = heading.get_text(strip=True)
                records.append(
                    self._build_record(heading_text, section_text, _list_items_from_elements(elements), url)
                )
            if records:
                return records

        items = [li.get_text(strip=True) for li in main_content.find_all("li") if li.get_text(strip=True)]
        return [self._build_record(None, full_text, items, url)]

    def _build_record(self, heading, text: str, items: list, url: str) -> dict:
        days_min, days_max = _extract_processing_days(text)
        amount_eur = _extract_amount_eur(text)

        requirements = {"items": items} if items else {"summary": text[:2000]}
        visa_type = f"{self.VISA_TYPE_BASE} - {heading}" if heading else self.VISA_TYPE_BASE

        record = {
            "country": self.country,
            "visa_type": visa_type,
            "issuing_body": self.ISSUING_BODY,
            "requirements": requirements,
            "proof_of_funds": {"amount_eur": amount_eur} if amount_eur is not None else None,
            "source_url": url,
            "processing_days_min": days_min,
            "processing_days_max": days_max,
            "notes": heading,
            "egyptian_specific": True,
        }
        record["content_hash"] = compute_content_hash(record)
        return record

    def _discover_study_pdf_url(self, html: str) -> str:
        """Finds the current English-language study-visa leaflet PDF, preferring the
        "englisch" variant and skipping the Arabic one, without ever hardcoding a URL."""
        soup = BeautifulSoup(html, "lxml")
        fallback_pdf = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf") or not _STUDY_PDF_RE.search(href):
                continue
            if "arab" in href.lower():
                continue
            full_url = href if href.startswith("http") else f"{self.base_url}{href}"
            if "englisch" in href.lower():
                return full_url
            if fallback_pdf is None:
                fallback_pdf = full_url
        return fallback_pdf

    async def scrape(self) -> list[dict]:
        """Overrides the template method to append the dynamically-discovered study-visa
        PDF leaflet as a second document, following StipendiumHungaricumAdapter's pattern."""
        if not robot_checker.is_allowed(self.target_url):
            logger.warning("robots_disallowed", url=self.target_url)
            return []

        async with httpx.AsyncClient() as client:
            await polite_delay(self.min_delay, self.max_delay)
            html = await self.fetch_page(client, self.target_url)
            docs = self.extract_documents(html, self.target_url)

            pdf_url = self._discover_study_pdf_url(html)
            if not pdf_url:
                logger.error("missing_pdf", url=self.target_url, reason="Could not dynamically discover the study visa PDF")
                return docs

            if not robot_checker.is_allowed(pdf_url):
                return docs

            await polite_delay(self.min_delay, self.max_delay)
            try:
                pdf_bytes = await self.fetch_binary(client, pdf_url)

                # Import here to avoid polluting other adapters
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(pdf_bytes))
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

                if text.strip():
                    docs.append({
                        "source": self.source_name,
                        "category": self.category,
                        "country": self.country,
                        "url": pdf_url,
                        "content": text,
                        "visa_requirements": [self._build_record(None, text, [], pdf_url)],
                    })
            except Exception as e:
                logger.error("pdf_fetch_error", url=pdf_url, error=str(e))

        return docs
