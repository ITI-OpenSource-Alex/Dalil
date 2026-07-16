import hashlib
import json
import re

from bs4 import BeautifulSoup

from app.adapters.base_adapter import BaseAdapter

# Regex heuristics for pulling genuinely-present structured facts out of page text.
# Intentionally conservative: fields stay None when nothing matches rather than
# guessing, per GOA-086's "do not fabricate data" requirement.
_AMOUNT_EUR_RE = re.compile(r"(?:€|EUR)\s?([\d.,]+)", re.IGNORECASE)
_SETUP_FEE_RE = re.compile(r"setup\s+fee[^.]*?(?:€|EUR)\s?([\d.,]+)", re.IGNORECASE)
_BALANCE_PERIOD_RE = re.compile(
    r"(?:held|blocked|maintained)\s+for\s+(?:at least\s+)?(\d+)\s*(day|month)s?", re.IGNORECASE
)
# Fallback for phrasing like "...amount for Germany is €11,904 for 12 months" -- the
# duration follows a currency amount directly rather than a "held/blocked/maintained" verb.
_BALANCE_PERIOD_AMOUNT_RE = re.compile(
    r"(?:€|EUR)\s?[\d.,]+\s+for\s+(\d+)\s*(day|month)s?", re.IGNORECASE
)
_ACCOUNT_TYPE_RE = re.compile(r"blocked\s+account", re.IGNORECASE)
_SPONSOR_NOT_ACCEPTED_RE = re.compile(r"sponsor\s+letter.{0,30}not\s+accepted", re.IGNORECASE)
_SPONSOR_MENTIONED_RE = re.compile(r"sponsor\s+letter", re.IGNORECASE)
_EGYPTIAN_DEBIT_NOT_ACCEPTED_RE = re.compile(r"egyptian[^.]*?debit[^.]*?not\s+accepted", re.IGNORECASE)
_EGYPTIAN_DEBIT_RE = re.compile(r"egyptian[^.]*?debit", re.IGNORECASE)
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


def _normalize_eur_amount(raw: str):
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


def _extract_amount_eur(text: str):
    match = _AMOUNT_EUR_RE.search(text)
    if not match:
        return None
    return _normalize_eur_amount(match.group(1))


def _extract_setup_fee_eur(text: str):
    match = _SETUP_FEE_RE.search(text)
    if not match:
        return None
    return _normalize_eur_amount(match.group(1))


def _extract_accepts_egyptian_debit(text: str):
    if _EGYPTIAN_DEBIT_NOT_ACCEPTED_RE.search(text):
        return False
    if _EGYPTIAN_DEBIT_RE.search(text):
        return True
    return None


def _extract_minimum_balance_period_days(text: str):
    match = _BALANCE_PERIOD_RE.search(text) or _BALANCE_PERIOD_AMOUNT_RE.search(text)
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


class FintibaSperrkontoAdapter(BaseAdapter):
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
            # Verified official page (GOA-086 research): Fintiba's blocked-account
            # requirements page. Server-rendered, so BaseAdapter is sufficient --
            # no Playwright/JS rendering is required here.
            base_url="https://www.fintiba.com",
            target_url="https://www.fintiba.com/blocked-account-germany",
            source_name="fintiba_sperrkonto",
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
        setup_fee_eur = _extract_setup_fee_eur(text)
        accepts_egyptian_debit = _extract_accepts_egyptian_debit(text)

        proof_of_funds = None
        if any(v is not None for v in (amount_eur, minimum_balance_period_days, accepted_account_types,
                                        sponsor_letter_accepted, notes_egypt, setup_fee_eur,
                                        accepts_egyptian_debit)):
            proof_of_funds = {
                "amount_eur": amount_eur,
                "accepted_account_types": accepted_account_types,
                "blocked_account_providers": ["Fintiba"],
                "minimum_balance_period_days": minimum_balance_period_days,
                "sponsor_letter_accepted": sponsor_letter_accepted,
                "notes_egypt": notes_egypt,
                "setup_fee_eur": setup_fee_eur,
                "accepts_egyptian_debit": accepts_egyptian_debit,
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
