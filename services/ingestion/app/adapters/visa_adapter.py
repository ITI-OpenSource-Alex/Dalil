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
from app.evidence import validate_evidence
import httpx
import pydantic
import structlog
from anthropic import AsyncAnthropic
from bs4 import BeautifulSoup
from pydantic import BaseModel
from app.schemas.visa_schema import ProofOfFunds, funding_schema_prompt_block
import hashlib
import httpx

from client import fetch_visa_sources, touch_visa_requirement

logger = structlog.get_logger("ingestion_worker.visa_adapter")


def normalize_text_for_hash(text: str) -> str:
    """Strips line-level whitespace and normalizes CRLF line endings prior to SHA-256 hashing."""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())

# Extraction, not reasoning — same tier as GOA-087's CV extraction.
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "claude-opus-4-8")

# Cap the text handed to the model. Embassy pages with embedded PDFs can be enormous and
# the tail is almost always footer/nav boilerplate.
MAX_TEXT_CHARS = 20000

EXTRACTION_SYSTEM_PROMPT = f"""You are extracting structured visa-requirement data for \
Egyptian student-visa applicants. You will be given the fetched text content of one \
official source page. Extract ONLY information explicitly present in that text. Do not \
use outside knowledge of visa requirements, even if you believe you know the answer — \
the fetched text is the only permitted source.

Rules:
1. Any field not stated in the provided text -> return null. Do not estimate, round, or
   infer a "typical" figure.
2. For EVERY non-null leaf field extracted in your JSON response (including enum fields like pathway, period, currency), you MUST include an entry in the
   `extraction_evidence` object. The key MUST be the exact dot-notation JSON path of that
   leaf field (using array bracket indices for lists).
   - Pathway enum example: `"proof_of_funds.pathways[0].pathway": "You must have enough money to pay for your course"`
   - Amount field example: `"proof_of_funds.pathways[0].amounts[0].amount": "£1,334 per month in London"`
   - Currency enum example: `"proof_of_funds.pathways[0].amounts[0].currency": "£1,334 per month"`
   - Period enum example: `"proof_of_funds.pathways[0].amounts[0].period": "for up to 9 months"`
   - Accepted evidence item example: `"proof_of_funds.pathways[0].accepted_evidence[0]": "bank statement showing you have the money"`
   - Flat field example: `"processing_days_min": "Processing time is 15 days"`
   - Requirement dict example: `"requirements.aps_certificate": "An APS certificate is required"`
   CRITICAL REQUIREMENT FOR QUOTES: Each quote in `extraction_evidence` MUST be very concise (strictly 1 to 15 words, NEVER EXCEEDING 20 WORDS) and an exact verbatim match. If a sentence is long, extract only a short verbatim snippet of 5-15 words.
   Every non-null leaf field in your JSON output MUST have a corresponding verbatim quote in `extraction_evidence`,
   and `extraction_evidence` MUST NOT contain any orphan keys.
3. Never output a source URL — it will be set by the calling system.
4. If the provided text does not appear to be about the expected country/visa type (e.g.
   a fetch error page, a redirect stub, a cookie wall, or unrelated content), set
   `extraction_valid` to false and leave all extracted fields null.

Return ONLY raw JSON matching this schema — no markdown fence, no prose:
{{
  "extraction_valid": true,
  "requirements": {{"<requirement_name>": "<value stated on the page>"}},
  "proof_of_funds": {funding_schema_prompt_block()},
  "processing_days_min": null,
  "processing_days_max": null,
  "notes": null,
  "extraction_evidence": {{
    "processing_days_min": "<verbatim quote for processing_days_min>",
    "requirements.<requirement_name>": "<verbatim quote for requirement field>",
    "proof_of_funds.pathways[0].pathway": "<verbatim quote for pathway>",
    "proof_of_funds.pathways[0].amounts[0].amount": "<verbatim quote for amount>",
    "proof_of_funds.pathways[0].amounts[0].currency": "<verbatim quote for currency>",
    "proof_of_funds.pathways[0].amounts[0].period": "<verbatim quote for period>",
    "proof_of_funds.pathways[0].accepted_evidence[0]": "<verbatim quote for accepted evidence>"
  }}
}}"""


class VisaSource(BaseModel):
    """A row of the visa_sources config table."""

    id: str | uuid.UUID
    country: str
    visa_type: str
    issuing_body: str
    source_url: str
    fetch_method: str = "httpx"
    content_hash: str | None = None


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
    proof_of_funds: ProofOfFunds | None = None
    processing_days_min: int | None = None
    processing_days_max: int | None = None
    notes: str | None = None
    extraction_evidence: dict | None = None
    content_hash: str | None = None


def _strip_markdown_fence(raw: str) -> str:
    """Models wrap JSON in ```json fences or include prose despite being told not to."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx : end_idx + 1]
    return text


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
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY") or "dummy-key"
        client_kwargs = {
            "api_key": api_key,
            # `or` not a get() default: compose injects an empty string when the var is
            # unset, and an empty UA makes AgentRouter reject the client outright.
            "default_headers": {"User-Agent": os.environ.get("ANTHROPIC_USER_AGENT")
                                or "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"},
        }
        if os.environ.get("ANTHROPIC_BASE_URL"):
            client_kwargs["base_url"] = os.environ.get("ANTHROPIC_BASE_URL")
            
        self.anthropic = anthropic_client or AsyncAnthropic(**client_kwargs)

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

        if outcome.proof_of_funds and outcome.proof_of_funds.pathways:
            for p in outcome.proof_of_funds.pathways:
                content_lines.append(f"Pathway: {p.pathway}")
                for amt in p.amounts:
                    qual = f" ({amt.qualifier})" if amt.qualifier else ""
                    content_lines.append(f"  Amount: {amt.amount} {amt.currency} {amt.period}{qual}")
                if p.accepted_evidence:
                    content_lines.append(f"  Accepted evidence: {', '.join(p.accepted_evidence)}")
                if p.notes:
                    content_lines.append(f"  Pathway notes: {p.notes}")
        if outcome.proof_of_funds and outcome.proof_of_funds.notes:
            content_lines.append(f"Proof of funds notes: {outcome.proof_of_funds.notes}")

        if outcome.processing_days_min is not None or outcome.processing_days_max is not None:
            min_d = outcome.processing_days_min if outcome.processing_days_min is not None else "?"
            max_d = outcome.processing_days_max if outcome.processing_days_max is not None else "?"
            content_lines.append(f"Processing time: {min_d}–{max_d} days")

        if outcome.notes:
            content_lines.append(outcome.notes)

        content_lines.append(f"Official source: {outcome.source_url}")

        visa_record = {
            "country": outcome.country,
            "visa_type": outcome.visa_type,
            "issuing_body": outcome.issuing_body,
            "requirements": outcome.requirements or {},
            "proof_of_funds": outcome.proof_of_funds.model_dump() if outcome.proof_of_funds else None,
            "source_url": outcome.source_url,
            "processing_days_min": outcome.processing_days_min,
            "processing_days_max": outcome.processing_days_max,
            "notes": outcome.notes,
            "content_hash": getattr(outcome, "content_hash", None),
            "extraction_evidence": outcome.extraction_evidence,
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
            max_tokens=4000,
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
        
        try:
            from app.telemetry import record_llm_cost
            in_tok = getattr(usage, "input_tokens", 0)
            out_tok = getattr(usage, "output_tokens", 0)
            record_llm_cost("anonymous", EXTRACTION_MODEL, in_tok, out_tok)
        except ImportError:
            pass
            
        text_content = ""
        for block in response.content:
            b_text = getattr(block, "text", "")
            if b_text and "{" in b_text:
                text_content = b_text
                break
        if not text_content and response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text_content = block.text
                    break

        stripped = _strip_markdown_fence(text_content)
        if not stripped or "{" not in stripped:
            raise ValueError(f"LLM response did not contain a valid JSON object: {text_content[:200]}")

        return json.loads(stripped), telemetry

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



            normalized_text = normalize_text_for_hash(text)
            fetched_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()

            if source.content_hash and source.content_hash == fetched_hash:
                logger.info("visa_source_unchanged", source=source.id)
                try:
                    touch_visa_requirement([{
                        "country": source.country, 
                        "visa_type": source.visa_type, 
                        "issuing_body": source.issuing_body
                    }])
                except Exception as e:
                    logger.warning("failed_to_touch_visa_source", source=source.id, error=str(e))
                # Skip the LLM and go to the next source!
                continue
            max_attempts = 2
            prompt_text = text
            for attempt in range(max_attempts):
                try:
                    raw_data, telemetry = await self._call_llm(prompt_text, source)

                    raw_data.setdefault("extraction_valid", True)
                    raw_data["source_id"] = source.id
                    raw_data["country"] = source.country
                    raw_data["visa_type"] = source.visa_type
                    raw_data["issuing_body"] = source.issuing_body
                    raw_data["source_url"] = source.source_url

                    outcome = ExtractionOutcome(**raw_data)

                    outcome.content_hash = fetched_hash

                    validate_evidence(outcome, text)

                    
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
                    # Proof-of-funds amounts are the highest-value field for Egyptian
                    # applicants. A source can extract requirements cleanly and still
                    # publish no figure (observed: gov.uk/student-visa says only "the
                    # amount will vary"), which used to count as an unqualified success.
                    # Surface it so the source URL can be pointed at the page that
                    # actually publishes the money.
                    pathways = (
                        outcome.proof_of_funds.pathways if outcome.proof_of_funds else []
                    )
                    amount_count = sum(len(p.amounts or []) for p in pathways)
                    if amount_count == 0:
                        logger.warning(
                            "visa_extraction_without_financial_amounts",
                            issuing_body=source.issuing_body,
                            country=source.country,
                            source_url=source.source_url,
                            hint="point this source at the page that publishes the figures",
                        )

                    logger.info(
                        "visa_extraction_succeeded",
                        financial_amounts=amount_count,
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
