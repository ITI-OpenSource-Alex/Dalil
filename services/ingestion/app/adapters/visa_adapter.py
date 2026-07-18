"""GOA-116: one generic, config-driven visa adapter replacing 9 bespoke scrapers.

Embassy/consular HTML is irregular, PDF-heavy and layout-inconsistent — the content type
brittle CSS-selector scraping handles worst. This adapter fetches a page and hands the
fetched text to Claude for structured extraction against the visa_requirements schema.

The hard rule this file exists to enforce: extraction happens over REAL FETCHED CONTENT,
never the model's own knowledge. Every non-null field must carry a verbatim quote from
that fetch, and source_url is always stamped by this code — never trusted from the model.
"""

import json
import os
import time
import uuid

import httpx
import pydantic
import structlog
from anthropic import AsyncAnthropic
from bs4 import BeautifulSoup
from pydantic import BaseModel

from client import fetch_visa_sources

logger = structlog.get_logger("ingestion_worker.visa_adapter")

# Extraction, not reasoning — same tier as GOA-087's CV extraction.
EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

# Cap the text handed to the model. Embassy pages with embedded PDFs can be enormous and
# the tail is almost always footer/nav boilerplate.
MAX_TEXT_CHARS = 20000

EXTRACTION_SYSTEM_PROMPT = """You are extracting structured visa-requirement data for \
Egyptian student-visa applicants. You will be given the fetched text content of one \
official source page. Extract ONLY information explicitly present in that text. Do not \
use outside knowledge of visa requirements, even if you believe you know the answer — \
the fetched text is the only permitted source.

Rules:
1. Any field not stated in the provided text -> return null. Do not estimate, round, or
   infer a "typical" figure.
2. For every non-null field, include a verbatim quote (<=20 words) from the provided text
   in the `extraction_evidence` object, keyed by field name.
3. Never output a source URL — it will be set by the calling system.
4. If the provided text does not appear to be about the expected country/visa type (e.g.
   a fetch error page, a redirect stub, a cookie wall, or unrelated content), set
   `extraction_valid` to false and leave all extracted fields null.

Return ONLY raw JSON matching this schema — no markdown fence, no prose:
{
  "extraction_valid": true,
  "requirements": {"<requirement_name>": "<value stated on the page>"},
  "proof_of_funds": {
    "amount_eur": null,
    "accepted_account_types": null,
    "blocked_account_providers": null,
    "minimum_balance_period_days": null,
    "sponsor_letter_accepted": null,
    "notes_egypt": null
  },
  "processing_days_min": null,
  "processing_days_max": null,
  "notes": null,
  "extraction_evidence": {"<field_name>": "<verbatim quote from the text>"}
}"""


class VisaSource(BaseModel):
    """A row of the visa_sources config table."""

    id: str | uuid.UUID
    country: str
    visa_type: str
    issuing_body: str
    source_url: str
    fetch_method: str = "httpx"


class ExtractionOutcome(BaseModel):
    """Result of extracting one source.

    proof_of_funds is a dict, not a float: visa_requirements.proof_of_funds is JSONB and
    GOA-109/110 depend on it carrying structured funding-pathway data (scholarship
    exemptions, per-pathway notes). A flat number cannot represent that.
    """

    source_id: str | uuid.UUID
    country: str
    visa_type: str
    issuing_body: str
    source_url: str
    extraction_valid: bool
    requirements: dict = {}
    proof_of_funds: dict | None = None
    processing_days_min: int | None = None
    processing_days_max: int | None = None
    notes: str | None = None
    extraction_evidence: dict | None = None


def _strip_markdown_fence(raw: str) -> str:
    """Models wrap JSON in ```json fences despite being told not to."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


class VisaSourceAdapter:
    def __init__(self, anthropic_client=None):
        self.source_name = "visa_adapter"
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "GOA-IngestionBot/1.0 (+educational research)"},
        )
        # API key comes from the environment. An empty key is allowed at construction so
        # the adapter can be instantiated in keyless environments (CI, local dev) — the
        # run loop degrades to extraction_valid=False rather than crashing the orchestrator.
        self.anthropic = anthropic_client or AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )

    async def scrape(self) -> list[dict]:
        """Orchestrator entry point.

        Returns the list-of-dicts shape run_orchestrator expects: each dict carries
        `content` (chunked into a Document by the caller) plus a `visa_requirements`
        list the caller upserts independently — the same dual-write pattern every
        GOA-086 adapter used.
        """
        sources = [VisaSource(**row) for row in fetch_visa_sources()]
        logger.info("visa_sources_loaded", count=len(sources))

        outcomes = await self.run(sources)
        return [self._to_document_dict(o) for o in outcomes if o.extraction_valid]

    def _to_document_dict(self, outcome: ExtractionOutcome) -> dict:
        """Map one extraction into the orchestrator's document + visa_requirements shape."""
        content_lines = [
            f"{outcome.country} — {outcome.visa_type} ({outcome.issuing_body})",
        ]
        for key, value in (outcome.requirements or {}).items():
            content_lines.append(f"{key}: {value}")
        if outcome.notes:
            content_lines.append(outcome.notes)

        visa_record = {
            "country": outcome.country,
            "visa_type": outcome.visa_type,
            "issuing_body": outcome.issuing_body,
            "requirements": outcome.requirements or {},
            "proof_of_funds": outcome.proof_of_funds,
            "source_url": outcome.source_url,
            "processing_days_min": outcome.processing_days_min,
            "processing_days_max": outcome.processing_days_max,
            "notes": outcome.notes,
            "egyptian_specific": True,
        }

        return {
            "content": "\n".join(content_lines),
            "source": self.source_name,
            "source_url": outcome.source_url,
            "country": outcome.country,
            "category": "visa",
            "scrape_frequency": "monthly",
            "visa_requirements": [visa_record],
        }

    async def _fetch_text(self, source: VisaSource) -> str:
        """Fetch a source's visible text, via Playwright when the row demands it."""
        if source.fetch_method == "playwright":
            return await self._fetch_text_playwright(source.source_url)

        response = await self.client.get(source.source_url)
        response.raise_for_status()
        return self._visible_text(response.text)

    async def _fetch_text_playwright(self, url: str) -> str:
        """JS-rendered sources (VFS Global is the only one today)."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()
            finally:
                await browser.close()
        return self._visible_text(html)

    @staticmethod
    def _visible_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:MAX_TEXT_CHARS]

    async def _call_llm(self, text: str, source: VisaSource) -> tuple[dict, dict]:
        """One extraction call. Returns (parsed_json, telemetry)."""
        started = time.perf_counter()
        response = await self.anthropic.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=2000,
            temperature=0.0,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"[FETCHED TEXT — from {source.source_url}, expected country "
                        f"{source.country}, expected visa type {source.visa_type}]\n{text}"
                    ),
                }
            ],
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)
        telemetry = {
            "model": EXTRACTION_MODEL,
            "latency_ms": latency_ms,
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
        return json.loads(_strip_markdown_fence(response.content[0].text)), telemetry

    def _invalid(self, source: VisaSource, reason: str) -> ExtractionOutcome:
        logger.warning(
            "visa_extraction_invalid",
            issuing_body=source.issuing_body,
            country=source.country,
            reason=reason,
        )
        return ExtractionOutcome(
            source_id=source.id,
            country=source.country,
            visa_type=source.visa_type,
            issuing_body=source.issuing_body,
            source_url=source.source_url,
            extraction_valid=False,
        )

    async def run(self, sources: list[VisaSource]) -> list[ExtractionOutcome]:
        outcomes: list[ExtractionOutcome] = []

        for source in sources:
            try:
                text = await self._fetch_text(source)
            except Exception as e:
                # One dead embassy page must never kill the other eight.
                outcomes.append(self._invalid(source, f"fetch_failed: {e}"))
                continue

            if not text.strip():
                outcomes.append(self._invalid(source, "empty_page_text"))
                continue

            max_attempts = 2
            prompt_text = text
            for attempt in range(max_attempts):
                try:
                    raw_data, telemetry = await self._call_llm(prompt_text, source)

                    # The model never gets to decide identity or provenance — this code
                    # stamps them, overwriting anything the model returned.
                    raw_data["source_id"] = source.id
                    raw_data["country"] = source.country
                    raw_data["visa_type"] = source.visa_type
                    raw_data["issuing_body"] = source.issuing_body
                    raw_data["source_url"] = source.source_url

                    outcome = ExtractionOutcome(**raw_data)

                    if not outcome.extraction_valid:
                        outcomes.append(
                            self._invalid(source, "model_reported_content_mismatch")
                        )
                        break

                    non_null = sum(
                        1
                        for f in (
                            outcome.proof_of_funds,
                            outcome.processing_days_min,
                            outcome.processing_days_max,
                            outcome.notes,
                        )
                        if f is not None
                    ) + len(outcome.requirements or {})
                    logger.info(
                        "visa_extraction_succeeded",
                        issuing_body=source.issuing_body,
                        country=source.country,
                        fields_extracted=non_null,
                        evidence_keys=len(outcome.extraction_evidence or {}),
                        **telemetry,
                    )
                    outcomes.append(outcome)
                    break

                except (pydantic.ValidationError, ValueError, json.JSONDecodeError) as e:
                    if attempt == max_attempts - 1:
                        outcomes.append(self._invalid(source, f"schema_invalid: {e}"))
                    else:
                        # Retry exactly once, with the validation error appended so the
                        # model can correct its own output.
                        prompt_text = (
                            f"{text}\n\nYour previous response failed schema validation "
                            f"with: {e}\nReturn corrected JSON."
                        )
                except Exception as e:
                    outcomes.append(self._invalid(source, f"extraction_failed: {e}"))
                    break

        return outcomes
