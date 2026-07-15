import hashlib
import json
import re

from bs4 import BeautifulSoup

from app.adapters.base_adapter import BaseAdapter

# Regex heuristics for pulling genuinely-present structured facts out of page text.
# Intentionally conservative: fields stay None/empty when nothing matches rather than
# guessing, per GOA-086's "do not fabricate data" requirement.
_PROCESSING_DAYS_RE = re.compile(r"(\d+)\s*(?:-|to|–)\s*(\d+)\s*(?:working\s+)?days", re.IGNORECASE)
# gov.uk states decision times in weeks, not a "N-M days" range (e.g. "3 weeks, if you're
# outside the UK" / "8 weeks, if you're inside the UK") -- fall back to scanning the
# "get a decision" section for week counts and convert to days rather than leaving this
# genuinely-present timing information unextracted.
_PROCESSING_WEEKS_TWO_RE = re.compile(
    r"decision.{0,400}?(\d+)\s*weeks?.{0,200}?(\d+)\s*weeks?", re.IGNORECASE | re.DOTALL
)
_PROCESSING_WEEKS_ONE_RE = re.compile(r"decision.{0,400}?(\d+)\s*weeks?", re.IGNORECASE | re.DOTALL)
_AMOUNT_EUR_RE = re.compile(r"(?:€|EUR)\s?([\d.,]+)", re.IGNORECASE)
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")


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
    if match:
        return int(match.group(1)), int(match.group(2))
    two_weeks_match = _PROCESSING_WEEKS_TWO_RE.search(text)
    if two_weeks_match:
        values = [int(two_weeks_match.group(1)) * 7, int(two_weeks_match.group(2)) * 7]
        return min(values), max(values)
    one_week_match = _PROCESSING_WEEKS_ONE_RE.search(text)
    if one_week_match:
        days = int(one_week_match.group(1)) * 7
        return days, days
    return None, None


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


class UKVISAEgyptAdapter(BaseAdapter):
    """Scrapes UK student-visa requirements as they apply to Egypt-based applicants.

    Sourced from the official UK government visa information, not any outsourced
    application-centre partner's own pages.
    """

    ISSUING_BODY = "UK Visas and Immigration (UKVI)"
    VISA_TYPE_BASE = "Student Visa (Student Route)"

    def __init__(self):
        super().__init__(
            # Verified official landing page (GOA-086 research): gov.uk's Student
            # visa guide, which fans out into several child pages (money, documents,
            # English requirements, etc.) under the same /student-visa/ path.
            base_url="https://www.gov.uk",
            target_url="https://www.gov.uk/student-visa",
            source_name="uk_visa_egypt",
            category="visa",
            country="UK",
            min_delay=2.0,
            max_delay=3.0,
        )

    def extract_urls(self, html: str) -> list[str]:
        """Discovers child guide pages (e.g. /student-visa/money) linked from the
        Student visa landing page, following the same discovery pattern as DAADAdapter."""
        soup = BeautifulSoup(html, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            # Strip tracking query strings (e.g. "?step-by-step-nav=<uuid>") as well as
            # fragments -- gov.uk emits both a plain link and a step-by-step-nav-tagged
            # variant of the same page, which would otherwise crawl as duplicate documents.
            href = a["href"].split("#")[0].split("?")[0]
            if not href.startswith("/student-visa/") and not href.startswith(f"{self.base_url}/student-visa/"):
                continue
            full_url = href if href.startswith("http") else f"{self.base_url}{href}"
            if full_url != self.target_url and full_url not in urls:
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
        record["content_hash"] = _compute_content_hash(record)
        return record
