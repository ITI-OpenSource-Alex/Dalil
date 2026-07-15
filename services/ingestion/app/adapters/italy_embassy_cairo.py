import hashlib
import json
import re

from bs4 import BeautifulSoup

from app.adapters.base_adapter import BaseAdapter

# Regex heuristics for pulling genuinely-present structured facts out of page text.
# Intentionally conservative: fields stay None/empty when nothing matches rather than
# guessing, per GOA-086's "do not fabricate data" requirement.
_PROCESSING_DAYS_RE = re.compile(r"(\d+)\s*(?:-|to|–)\s*(\d+)\s*(?:working\s+)?days", re.IGNORECASE)
_AMOUNT_EUR_RE = re.compile(r"(?:€|EUR)\s?([\d.,]+)", re.IGNORECASE)
_DECLARATION_OF_VALUE_RE = re.compile(r"declaration\s+of\s+value|dichiarazione\s+di\s+valore", re.IGNORECASE)
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# This site authors its document checklist as a run of short standalone <p> tags
# (some manually bulleted with a leading dash, some not) rather than a real <ul><li>
# list. Used as a last-resort fallback when no <li> items are present at all.
_BULLET_PREFIX_RE = re.compile(r"^[–—\-•]\s*")
_HAS_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_CHECKLIST_PARAGRAPH_MAX_LEN = 200


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


def _paragraph_checklist_items(container) -> list:
    """Last-resort fallback for pages whose checklist is authored as plain
    paragraphs instead of a <ul><li> list: treats short, letter-containing <p>
    tags as individual checklist items (stripping any leading bullet dash),
    while skipping long narrative paragraphs and pure-punctuation dividers."""
    items = []
    for p in container.find_all("p"):
        text = p.get_text(strip=True)
        if not text or len(text) > _CHECKLIST_PARAGRAPH_MAX_LEN:
            continue
        if not _HAS_LETTER_RE.search(text):
            continue
        items.append(_BULLET_PREFIX_RE.sub("", text))
    return items


def _split_declaration_of_value(items: list):
    """Pulls any checklist item describing the Declaration of Value (Dichiarazione di
    Valore) procedure out of the general document checklist, so it's reported as its
    own distinct requirement rather than merged in with ordinary checklist items."""
    remaining = []
    declaration_of_value = None
    for item in items:
        if declaration_of_value is None and _DECLARATION_OF_VALUE_RE.search(item):
            declaration_of_value = item
        else:
            remaining.append(item)
    return remaining, declaration_of_value


class ItalyEmbassyCairoAdapter(BaseAdapter):
    """Scrapes Italian student-visa requirements published by the Italian Embassy in Cairo."""

    ISSUING_BODY = "Italian Embassy Cairo"
    VISA_TYPE_BASE = "Student Visa (National Visa - Type D)"

    def __init__(self):
        super().__init__(
            # Verified official page (GOA-086 research): the Italian Cultural Institute
            # in Cairo's study-visa page (iiccairo.esteri.it, an Italian MFA subsite).
            base_url="https://iiccairo.esteri.it",
            target_url="https://iiccairo.esteri.it/it/lingua-e-cultura/studiare-in-italia/visto-per-studio-v-s-u-o-v-n/",
            source_name="italy_embassy_cairo",
            category="visa",
            country="Italy",
            min_delay=2.0,
            max_delay=3.0,
        )

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")

        if _is_arabic_only(soup):
            return []

        # Prefer the real article body over the generic <main>, which also contains
        # the "Naviga nella sezione" sidebar widget -- its nav links would otherwise
        # be mistaken for document-checklist items by the <li> fallback below.
        main_content = (
            soup.find("div", class_="entry-content")
            or soup.find("main")
            or soup.find("div", id="content")
            or soup.find("body")
        )
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
        if not items:
            items = _paragraph_checklist_items(main_content)
        return [self._build_record(None, full_text, items, url)]

    def _build_record(self, heading, text: str, items: list, url: str) -> dict:
        days_min, days_max = _extract_processing_days(text)
        amount_eur = _extract_amount_eur(text)
        items, declaration_of_value = _split_declaration_of_value(items)

        requirements = {"items": items} if items else {"summary": text[:2000]}
        if declaration_of_value:
            requirements["declaration_of_value"] = declaration_of_value
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
