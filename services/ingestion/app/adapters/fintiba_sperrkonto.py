import hashlib
import json
import re

from bs4 import BeautifulSoup

from app.adapters.base_playwright_adapter import BasePlaywrightAdapter

# Regex heuristics for pulling genuinely-present structured facts out of page text.
# Intentionally conservative: fields stay None when nothing matches rather than
# guessing, per GOA-086's "do not fabricate data" requirement.
_AMOUNT_EUR_RE = re.compile(r"(?:€|EUR)\s?([\d.,]+)", re.IGNORECASE)
_BALANCE_PERIOD_RE = re.compile(
    r"(?:held|blocked|maintained)\s+for\s+(?:at least\s+)?(\d+)\s*(day|month)s?", re.IGNORECASE
)
_ACCOUNT_TYPE_RE = re.compile(r"blocked\s+account", re.IGNORECASE)
_SPONSOR_NOT_ACCEPTED_RE = re.compile(r"sponsor\s+letter.{0,30}not\s+accepted", re.IGNORECASE)
_SPONSOR_MENTIONED_RE = re.compile(r"sponsor\s+letter", re.IGNORECASE)
_EGYPT_LINE_RE = re.compile(r"egypt|egp", re.IGNORECASE)
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


def _extract_amount_eur(text: str):
    match = _AMOUNT_EUR_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_minimum_balance_period_days(text: str):
    match = _BALANCE_PERIOD_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    return value * 30 if unit == "month" else value


def _extract_accepted_account_types(text: str):
    return ["blocked_account"] if _ACCOUNT_TYPE_RE.search(text) else None


def _extract_sponsor_letter_accepted(text: str):
    if _SPONSOR_NOT_ACCEPTED_RE.search(text):
        return False
    if _SPONSOR_MENTIONED_RE.search(text):
        return True
    return None


def _extract_notes_egypt(text: str):
    for line in text.split("\n"):
        if _EGYPT_LINE_RE.search(line):
            return line.strip()
    return None


def _compute_content_hash(record: dict) -> str:
    """Deterministic hash of the structured record fields (not raw HTML)."""
    canonical = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FintibaSperrkontoAdapter(BasePlaywrightAdapter):
    """Scrapes blocked-account (Sperrkonto) requirements from Fintiba.

    Fintiba is a blocked-account provider, not a visa-issuing body — its content feeds
    the proof_of_funds side of the German student-visa requirement. blocked_account_providers
    is fixed to ["Fintiba"] since that identifies the source itself (not a scraped fact);
    every other proof_of_funds field is extracted from the page content.
    """

    ISSUING_BODY = "Fintiba GmbH"
    VISA_TYPE = "Student Visa (Blocked Account Requirement)"

    def __init__(self):
        super().__init__(
            # fintiba.com is Fintiba's real, well-known domain. The exact Sperrkonto
            # requirements page path is unconfirmed (see GOA-086 implementation plan
            # Task 12, Prerequisites) and must be set before production scraping.
            base_url="https://fintiba.com",
            target_url="https://fintiba.com",
            source_name="fintiba_sperrkonto",
            category="visa",
            country="Germany",
            wait_selector="body",
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
        items = [li.get_text(strip=True) for li in main_content.find_all("li") if li.get_text(strip=True)]
        visa_requirements = [self._build_record(text_content, items, page_url)]

        return [{
            "source": self.source_name,
            "category": self.category,
            "country": self.country,
            "url": page_url,
            "content": text_content,
            "visa_requirements": visa_requirements,
        }]

    def _build_record(self, text: str, items: list, url: str) -> dict:
        amount_eur = _extract_amount_eur(text)
        minimum_balance_period_days = _extract_minimum_balance_period_days(text)
        accepted_account_types = _extract_accepted_account_types(text)
        sponsor_letter_accepted = _extract_sponsor_letter_accepted(text)
        notes_egypt = _extract_notes_egypt(text)

        proof_of_funds = None
        if any(v is not None for v in (amount_eur, minimum_balance_period_days, accepted_account_types,
                                        sponsor_letter_accepted, notes_egypt)):
            proof_of_funds = {
                "amount_eur": amount_eur,
                "accepted_account_types": accepted_account_types,
                "blocked_account_providers": ["Fintiba"],
                "minimum_balance_period_days": minimum_balance_period_days,
                "sponsor_letter_accepted": sponsor_letter_accepted,
                "notes_egypt": notes_egypt,
            }

        requirements = {"items": items} if items else {"summary": text[:2000]}

        record = {
            "country": self.country,
            "visa_type": self.VISA_TYPE,
            "issuing_body": self.ISSUING_BODY,
            "requirements": requirements,
            "proof_of_funds": proof_of_funds,
            "source_url": url,
            "processing_days_min": None,
            "processing_days_max": None,
            "notes": None,
            "egyptian_specific": True,
        }
        record["content_hash"] = _compute_content_hash(record)
        return record
