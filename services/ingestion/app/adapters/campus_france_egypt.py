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
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# This site (Drupal) renders sidebar/footer widgets -- related articles, generic footer
# CTA -- as their own h2-headed sections alongside the real procedural content. They're
# not visa information, so headings inside these known widget containers are skipped
# rather than surfaced as bogus "requirements" records.
_NON_CONTENT_SECTION_CLASSES = {"sur-le-meme-sujet", "contenus-recommandes", "push-container"}


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
    if elements:
        return elements
    # This site (Drupal "paragraph" blocks) wraps each heading in its own single-child
    # title container, with the section's real body as a sibling of that wrapper --
    # not of the heading itself, so the walk above finds nothing. Retry one level up.
    parent = heading.parent
    if parent is None or parent.name in ("html", "body"):
        return elements
    for sibling in parent.find_next_siblings():
        if sibling.name in ("h2", "h3") or sibling.find(["h2", "h3"]):
            break
        elements.append(sibling)
    return elements


def _is_non_content_section(heading) -> bool:
    """True if `heading` lives inside a known sidebar/footer widget container rather
    than the page's real procedural content."""
    for ancestor in heading.parents:
        classes = ancestor.get("class") or []
        if _NON_CONTENT_SECTION_CLASSES.intersection(classes):
            return True
    return False


def _text_from_elements(elements) -> str:
    parts = [el.get_text(separator="\n", strip=True) for el in elements]
    return "\n".join(part for part in parts if part)


def _list_items_from_elements(elements) -> list:
    items = []
    for el in elements:
        items.extend(li.get_text(strip=True) for li in el.find_all("li") if li.get_text(strip=True))
    return items


def _count_pre_registration_steps(elements) -> int:
    """Counts <li> items within <ol> (ordered list) elements among `elements` -- the
    Études en France pre-registration procedure is a numbered sequence, distinct from
    an unordered document checklist. Returns 0 if no <ol> is present, rather than
    fabricating a step count from an unrelated list."""
    count = 0
    for el in elements:
        if el.name == "ol":
            count += len(el.find_all("li"))
        else:
            count += sum(len(ol.find_all("li")) for ol in el.find_all("ol"))
    return count


class CampusFranceEgyptAdapter(BaseAdapter):
    """Scrapes French student-visa procedural requirements (Études en France) published
    by Campus France Egypt."""

    ISSUING_BODY = "Campus France Egypt"
    VISA_TYPE_BASE = "Student Visa (Long Stay - VLS-TS)"

    def __init__(self):
        super().__init__(
            # Verified official page (GOA-086 research): Campus France Egypt's
            # application-procedure page.
            base_url="https://www.egypte.campusfrance.org",
            target_url="https://www.egypte.campusfrance.org/en/campus-france-egypt-application-procedure",
            source_name="campus_france_egypt",
            category="visa",
            country="France",
            min_delay=2.0,
            max_delay=3.0,
        )

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")

        if _is_arabic_only(soup):
            return []

        # Prefer the real article body (excludes the breadcrumb nav region, which sits
        # outside it) over the generic <main>/<body> fallback used when this site's
        # specific Drupal markup isn't present.
        main_content = (
            soup.find("div", class_="node__content")
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
                if _is_non_content_section(heading):
                    continue
                elements = _section_elements(heading)
                section_text = _text_from_elements(elements)
                if not section_text:
                    continue
                heading_text = heading.get_text(strip=True)
                records.append(
                    self._build_record(
                        heading_text, section_text, _list_items_from_elements(elements),
                        _count_pre_registration_steps(elements), url,
                    )
                )
            if records:
                return records

        items = [li.get_text(strip=True) for li in main_content.find_all("li") if li.get_text(strip=True)]
        step_count = _count_pre_registration_steps([main_content])
        return [self._build_record(None, full_text, items, step_count, url)]

    def _build_record(self, heading, text: str, items: list, step_count: int, url: str) -> dict:
        days_min, days_max = _extract_processing_days(text)
        amount_eur = _extract_amount_eur(text)

        requirements = {"items": items} if items else {"summary": text[:2000]}
        if step_count:
            requirements["pre_registration_steps"] = step_count
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
