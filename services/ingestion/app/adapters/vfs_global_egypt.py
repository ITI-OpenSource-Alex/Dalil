import hashlib
import json
import re

from bs4 import BeautifulSoup

from app.adapters.base_playwright_adapter import BasePlaywrightAdapter

# Regex heuristics for pulling genuinely-present structured facts out of page text.
# Intentionally conservative: fields stay None/empty when nothing matches rather than
# guessing, per GOA-086's "do not fabricate data" requirement.
_PROCESSING_DAYS_RE = re.compile(r"(\d+)\s*(?:-|to|–)\s*(\d+)\s*(?:working\s+)?days", re.IGNORECASE)
_AMOUNT_EUR_RE = re.compile(r"(?:€|EUR)\s?([\d.,]+)", re.IGNORECASE)
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# VFS Global Egypt is a shared visa application centre serving several destination
# countries. We only ever attribute a record to a country genuinely named in the page
# content — never guessed — so this list is a lookup, not an assumption about which
# countries are actually present on any given page.
_KNOWN_DESTINATION_COUNTRIES = [
    "Italy", "Spain", "Czech Republic", "Netherlands", "Switzerland",
    "Belgium", "Portugal", "Poland", "Austria", "Hungary",
]


def _is_arabic_only(soup: BeautifulSoup) -> bool:
    """Detects Arabic-only pages so they can be skipped gracefully (per GOA-086)."""
    html_tag = soup.find("html")
    if html_tag and (html_tag.get("lang") or "").lower().startswith("ar"):
        return True
    text = soup.get_text()
    arabic_count = len(_ARABIC_RE.findall(text))
    latin_count = len(_LATIN_RE.findall(text))
    return arabic_count > 20 and arabic_count > latin_count


def _match_destination_country(text: str):
    """Returns the first known destination country genuinely named in `text`, else None."""
    for country in _KNOWN_DESTINATION_COUNTRIES:
        if country.lower() in text.lower():
            return country
    return None


def _extract_processing_days(text: str):
    match = _PROCESSING_DAYS_RE.search(text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _extract_amount_eur(text: str):
    match = _AMOUNT_EUR_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _compute_content_hash(record: dict) -> str:
    """Deterministic hash of the structured record fields (not raw HTML)."""
    canonical = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


class VFSGlobalEgyptAdapter(BasePlaywrightAdapter):
    """Scrapes VFS Global's Egypt-based visa application centre pages.

    VFS Global Egypt is a shared, outsourced application centre serving several
    destination countries at once, so a single page commonly needs to yield multiple
    visa_requirements records (one per destination country actually named on the page)
    rather than a single record per adapter run.
    """

    ISSUING_BODY = "VFS Global Egypt"
    VISA_TYPE_BASE = "Student Visa (National Visa - Type D)"

    def __init__(self):
        super().__init__(
            # visa.vfsglobal.com is VFS Global's real, well-known domain. The exact
            # Egypt landing/country pages are unconfirmed (see GOA-086 implementation
            # plan Task 11, Prerequisites) and must be set before production scraping.
            base_url="https://visa.vfsglobal.com",
            target_url="https://visa.vfsglobal.com/egy/en",
            source_name="vfs_global_egypt",
            category="visa",
            # This source covers multiple destination countries at the chunk level;
            # each structured visa_requirements record below carries its own, specific
            # country instead (never hardcoded here per GOA-086 Task 11's requirement).
            country="Multiple",
            wait_selector="body",
            min_delay=2.0,
            max_delay=3.0,
        )

    def extract_urls(self, html: str) -> list[str]:
        """Enumerates country-specific sub-pages linked from a VFS Global Egypt index page."""
        soup = BeautifulSoup(html, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            link_text = a.get_text(strip=True)
            href = a["href"]
            if _match_destination_country(link_text) or _match_destination_country(href):
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

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
        if not visa_requirements:
            # No destination country could be genuinely identified on this page —
            # skip rather than fabricate a country attribution.
            return []

        return [{
            "source": self.source_name,
            "category": self.category,
            "country": self.country,
            "url": page_url,
            "content": text_content,
            "visa_requirements": visa_requirements,
        }]

    def _extract_visa_requirements(self, main_content, full_text: str, url: str) -> list[dict]:
        # Primary case: an index-style page listing several countries under their own
        # h2/h3 headings — the norm for a shared application centre like VFS Global.
        headings = main_content.find_all(["h2", "h3"])
        records = []
        for heading in headings:
            heading_text = heading.get_text(strip=True)
            destination_country = _match_destination_country(heading_text)
            if not destination_country:
                continue
            elements = _section_elements(heading)
            section_text = _text_from_elements(elements)
            if not section_text:
                continue
            records.append(
                self._build_record(
                    destination_country, heading_text, section_text,
                    _list_items_from_elements(elements), url,
                )
            )
        if records:
            return records

        # Fallback: a single-country detail page (e.g. reached via extract_urls crawl),
        # where the country is named in the page title/heading rather than a sub-section.
        h1 = main_content.find("h1")
        page_country = _match_destination_country(h1.get_text(strip=True)) if h1 else None
        if not page_country:
            page_country = _match_destination_country(full_text[:500])
        if not page_country:
            return []

        items = [li.get_text(strip=True) for li in main_content.find_all("li") if li.get_text(strip=True)]
        return [self._build_record(page_country, None, full_text, items, url)]

    def _build_record(self, destination_country: str, heading, text: str, items: list, url: str) -> dict:
        days_min, days_max = _extract_processing_days(text)
        amount_eur = _extract_amount_eur(text)

        requirements = {"items": items} if items else {"summary": text[:2000]}
        visa_type = f"{self.VISA_TYPE_BASE} - {heading}" if heading else self.VISA_TYPE_BASE

        record = {
            "country": destination_country,
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
        record["content_hash"] = _compute_content_hash(record)
        return record
