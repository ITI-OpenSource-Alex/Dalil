import json
import re
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from goa_pricing import cost_usd as price_call


MODEL = "claude-opus-5"
# 1200 until 2026-08-17, and the same bug app/agents.py:417 already documents:
# claude-opus-5 emits a ThinkingBlock before its TextBlock, and both draw on this
# budget. A long enough thinking block exhausts it, the response returns with
# stop_reason='max_tokens' and no TextBlock at all, and _response_text then has
# nothing to parse. The failure is intermittent by nature -- it depends on how
# much the model happens to think -- which is why the same CV extracted fine by
# hand and failed through the worker. agents.py raised its equivalent to 4000
# for exactly this reason; this call site was missed.
#
# A well-formed extraction measures ~550 output tokens, so 4000 leaves room for
# thinking without inviting a runaway generation.
MAX_TOKENS = 4000
# GOA-135: INPUT_COST_PER_MILLION_USD = 1.0 / OUTPUT_COST_PER_MILLION_USD = 5.0
# lived here and were half the $2/$10 table current during GOA-135, so every CV
# extraction cost was reported at 50%. Current prices come from the shared table
# (packages/pricing), which reads the same LLM_PRICING_JSON the Gateway does.

SYSTEM_PROMPT = """Extract structured facts from the supplied CV.
Return exactly one JSON object and no markdown or commentary. Never infer facts that are
not present. Use null for an unknown scalar and [] for an unknown list. The exact shape is:
{
  "name": null,
  "email": null,
  "phone": null,
  "degree": null,
  "institution": null,
  "graduation_year": null,
  "field_of_study": null,
  "skills": [],
  "work_experience": [{"title": null, "org": null, "years": null}],
  "languages": []
}"""


class WorkExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    org: str | None = None
    years: str | None = None


class StructuredCV(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    degree: str | None = None
    institution: str | None = None
    # Declared str, but a year is a number and the model writes it as one:
    # {"graduation_year": 2025} fails `str | None` under Pydantic v2, which does
    # not coerce int to str. SYSTEM_PROMPT shows the field as bare `null`, so
    # nothing ever told the model to quote it. Every extraction carrying a
    # graduation year therefore failed validation, retried once, failed again,
    # and surfaced as "Claude returned invalid structured CV JSON twice" -- a
    # message that points at the model when the schema was at fault.
    # Accept both and normalise to str so downstream consumers see one type.
    graduation_year: str | int | None = None
    field_of_study: str | None = None

    @field_validator("graduation_year", mode="after")
    @classmethod
    def _year_to_str(cls, value: str | int | None) -> str | None:
        return None if value is None else str(value)

    skills: list[str] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    def fields_extracted(self) -> int:
        values = self.model_dump()
        return sum(value not in (None, "", []) for value in values.values())


@dataclass(frozen=True)
class StructuredExecution:
    data: StructuredCV
    input_tokens: int
    output_tokens: int
    latency_ms: float
    # None when the model is unpriced (GOA-135); never coerced to 0.0.
    cost_usd: float | None


def _response_text(response: Any) -> str:
    text = "".join(
        getattr(block, "text", "") or "" for block in getattr(response, "content", [])
    )
    if not text.strip():
        raise ValueError("Claude returned no structured extraction content")
    return text


def _json_object(text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Claude did not return a JSON object")
    return cleaned[start : end + 1]


class StructuredCVExtractor:
    def __init__(self, client: Any, *, model: str = MODEL) -> None:
        self.client = client
        self.model = model

    def extract(self, cv_text: str) -> StructuredExecution:
        last_parse_error: Exception | None = None
        for attempt in range(2):
            prompt = "CV text:\n" + cv_text
            if attempt:
                prompt = (
                    "Your previous response was not valid for the required schema. "
                    "Return only the corrected JSON object.\n\n" + prompt
                )
            started = time.perf_counter()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                # No `temperature`. The gateway fronts Bedrock, which rejects the
                # parameter outright for Claude Opus through AgentRouter:
                #   ValidationException: `temperature` is deprecated for this model
                # It surfaces here as a flat 400 on every extraction. The same fix
                # was already applied to app/agents.py under GOA-028; this call site
                # was missed because the CV pipeline could not run at all (BUG-018).
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            latency_ms = (time.perf_counter() - started) * 1000
            try:
                data = StructuredCV.model_validate_json(
                    _json_object(_response_text(response))
                )
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_parse_error = exc
                continue

            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            # self.model, not the MODEL constant: the extractor accepts a model
            # override in __init__ and the request above is sent with it, so
            # pricing the constant would bill an override at the default's rate.
            cost_usd = price_call(self.model, input_tokens, output_tokens)
            return StructuredExecution(
                data=data,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
            )

        raise ValueError("Claude returned invalid structured CV JSON twice") from last_parse_error
