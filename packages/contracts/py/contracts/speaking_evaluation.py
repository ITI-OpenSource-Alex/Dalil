"""Pydantic representation of the canonical speaking evaluation (SPEAK-EVAL-003).

Source of truth: ``packages/contracts/schemas/speaking-evaluation-v1.schema.json``.
Go representation: ``services/speaking/internal/contract``.
TypeScript representation: ``packages/contracts/ts/speaking-evaluation.ts``.

All three decode the same fixtures in
``packages/contracts/fixtures/speaking-evaluation``, because the drift this
contract replaces was three representations that each looked correct alone.

Two rules run through every model here:

1. **Status is separate from value.** A criterion that did not complete has
   ``status="unavailable"`` and ``band=None``. Band 0.0 is a real IELTS value
   meaning the candidate said nothing usable; it must never stand in for "we did
   not measure this". Validators below make the invalid combination
   unconstructible rather than merely discouraged.

2. **Every claim is addressable.** A rubric match names a descriptor id from the
   frozen rubric; evidence names a transcript offset, an audio interval or a
   measurement id.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "speaking-evaluation/v1"
SCORE_SEMANTICS = "estimated_ielts_practice_band"
ROUNDING_RULE_V1 = "ielts_half_band_v1"


class CriterionID(str, Enum):
    """The four official IELTS speaking criteria.

    Snake_case ids rather than display strings: a display string is a label, and
    labels change. GOA-133 renamed pronunciation in the UI without touching the
    underlying criterion, which is exactly the separation these ids buy.
    """

    FLUENCY_COHERENCE = "fluency_coherence"
    LEXICAL_RESOURCE = "lexical_resource"
    GRAMMATICAL_RANGE = "grammatical_range"
    PRONUNCIATION = "pronunciation"


class Mode(str, Enum):
    PRACTICE = "practice"
    EXAM = "exam"
    #: So an eval run is never mistaken for a user's result.
    BENCHMARK = "benchmark"


class Status(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class CriterionStatus(str, Enum):
    SCORED = "scored"
    UNAVAILABLE = "unavailable"


class UnavailableReason(str, Enum):
    """Why a criterion produced no score.

    Not interchangeable: a deadline may succeed on retry, a provider error will
    not, and ``INSUFFICIENT_EVIDENCE`` never will for this input.
    """

    PROVIDER_ERROR = "provider_error"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    INVALID_OUTPUT = "invalid_output"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Polarity(str, Enum):
    SUPPORTS = "supports"
    #: Why the band is not higher -- what lets an explanation answer "why not a 7".
    CAPS_BELOW = "caps_below"
    REACHES_TOWARD = "reaches_toward"


class EvidenceKind(str, Enum):
    TRANSCRIPT_SPAN = "transcript_span"
    AUDIO_INTERVAL = "audio_interval"
    MEASUREMENT_REF = "measurement_ref"
    PART_OR_TURN = "part_or_turn"
    ABSENCE_OR_DISTRIBUTION = "absence_or_distribution"


class Unit(str, Enum):
    WORDS_PER_MINUTE = "words_per_minute"
    SECONDS = "seconds"
    COUNT = "count"
    RATIO = "ratio"
    PROBABILITY = "probability"


def is_half_band(value: float) -> bool:
    """A legal IELTS band: 0..9 in half steps.

    6.3 is not a band any examiner could award, and accepting one would mean an
    upstream rounding rule was skipped.
    """
    if value < 0 or value > 9:
        return False
    return abs(value * 2 - round(value * 2)) < 1e-9


def round_ielts_band(average: float) -> float:
    """Official half-up rounding. Mirrors ``RoundIELTSBand`` in the Go package;
    a test asserts the two agree across the range."""
    int_part = float(int(average))
    dec = average - int_part
    if dec < 0.25:
        return int_part
    if dec < 0.75:
        return int_part + 0.5
    return int_part + 1.0


class _Base(BaseModel):
    # extra="forbid" so a field the schema has and this model lacks is a loud
    # failure rather than silently dropped data. Silent drops are how three
    # representations diverge while every test stays green.
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class RubricMatch(_Base):
    rubric_id: str
    rubric_version: str
    #: Must exist in the frozen rubric. A model may cite only ids supplied in its
    #: request; anything else is invented and the validator rejects it.
    descriptor_id: str = Field(pattern=r"^(fc|lr|gra|pr)\.[0-9](\.[0-9]+)?$")
    descriptor_band: float
    polarity: Polarity
    application: str | None = None


class Evidence(_Base):
    kind: EvidenceKind
    #: What this is evidence FOR. Evidence attached to nothing is decoration.
    supports_claim: str = Field(min_length=1)

    quote: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    audio_start_s: float | None = Field(default=None, ge=0)
    audio_end_s: float | None = Field(default=None, ge=0)

    measurement_id: str | None = None
    part: int | None = Field(default=None, ge=1, le=3)

    @model_validator(mode="after")
    def _kind_requires_its_fields(self) -> "Evidence":
        if self.kind is EvidenceKind.TRANSCRIPT_SPAN:
            if self.quote is None or self.char_start is None or self.char_end is None:
                raise ValueError(
                    "a transcript span needs a quote and both offsets, or the claim "
                    "cannot be checked against the transcript"
                )
            if self.char_end < self.char_start:
                raise ValueError("transcript offsets are inverted")
        elif self.kind is EvidenceKind.AUDIO_INTERVAL:
            if self.audio_start_s is None or self.audio_end_s is None:
                raise ValueError("an audio interval needs both bounds")
            if self.audio_end_s < self.audio_start_s:
                raise ValueError("audio interval is inverted")
        elif self.kind is EvidenceKind.MEASUREMENT_REF:
            if not self.measurement_id:
                raise ValueError("a measurement reference names no id")
        return self


class ImprovementAction(_Base):
    action: str = Field(min_length=1)
    because: str | None = None


class CriterionResult(_Base):
    criterion_id: CriterionID
    status: CriterionStatus
    band: float | None = None
    unavailable_reason: UnavailableReason | None = None

    summary: str | None = None
    rubric_matches: list[RubricMatch] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    measurements: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    improvement_actions: list[ImprovementAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _status_and_value_agree(self) -> "CriterionResult":
        if self.status is CriterionStatus.SCORED:
            if self.band is None:
                raise ValueError("status is 'scored' but no band is present")
            if not is_half_band(self.band):
                raise ValueError(
                    f"band {self.band} is not a half-band step; no examiner could award it"
                )
            if self.unavailable_reason is not None:
                raise ValueError("a scored criterion carries an unavailable_reason")
        else:
            if self.band is not None:
                raise ValueError(
                    f"an unavailable criterion carries band {self.band}. Band 0.0 is a "
                    f"real IELTS value meaning the candidate said nothing usable; it "
                    f"must never stand in for 'not measured' (BUG-055)"
                )
            if self.unavailable_reason is None:
                raise ValueError("an unavailable criterion gives no reason")
        return self

    @property
    def scored(self) -> bool:
        return self.status is CriterionStatus.SCORED and self.band is not None


class Overall(_Base):
    #: Absent -- not null, not zero -- when fewer than ``min_criteria_required``
    #: criteria scored. A band averaged from one surviving agent describes which
    #: agents survived, not the candidate (BUG-040).
    band: float | None = None
    #: The mean before rounding, so a student can see the arithmetic rather than
    #: be asked to trust it.
    unrounded_mean: float | None = None
    included_criteria: list[CriterionID]
    excluded_criteria: list[CriterionID] = Field(default_factory=list)
    rounding_rule: str
    min_criteria_required: int = Field(ge=1)

    @model_validator(mode="after")
    def _band_is_a_legal_value(self) -> "Overall":
        if self.band is not None and not is_half_band(self.band):
            raise ValueError(f"overall band {self.band} is not a half-band step")
        return self


class Measurement(_Base):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    value: float
    unit: Unit
    extractor_version: str = Field(min_length=1)
    scope: Literal["utterance", "part", "session"] | None = None


class Provenance(_Base):
    """What produced this score: enough to reproduce it, or to explain why not."""

    created_at: datetime
    scorer_version: str = Field(min_length=1)
    rubric_id: str = Field(min_length=1)
    rubric_version: str = Field(min_length=1)
    rubric_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    llm_provider: str | None = None
    #: The EFFECTIVE model, read from configuration at call time. This was
    #: hardcoded to a Haiku id in the Langfuse span while the service ran Opus,
    #: which made every model-to-model telemetry comparison meaningless.
    llm_model: str | None = None
    prompt_template_ids: list[str] = Field(default_factory=list)

    stt_provider: str | None = None
    stt_model: str | None = None
    transcript_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    #: Recorded because SPEAK-EVAL-002 established that a mislabelled audio
    #: format silently produces a score from noise.
    audio_format: str | None = None
    feature_extractor_version: str | None = None

    measurements: list[Measurement] = Field(default_factory=list)


class Telemetry(_Base):
    total_latency_ms: int | None = Field(default=None, ge=0)
    transcription_ms: int | None = Field(default=None, ge=0)
    audio_duration_s: float | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    #: None, never 0.0, when the model is absent from the shared price table
    #: (GOA-135). "We could not price this" and "this was free" are different.
    cost_usd: float | None = None


class SpeakingEvaluation(_Base):
    schema_version: Literal["speaking-evaluation/v1"]
    evaluation_id: str = Field(min_length=1)
    mode: Mode
    status: Status
    #: A const, and deliberately not "ielts_band". This system is not a certified
    #: examiner and the payload must not be able to say it is.
    score_semantics: Literal["estimated_ielts_practice_band"]
    criteria: list[CriterionResult] = Field(min_length=1)
    overall: Overall
    provenance: Provenance
    telemetry: Telemetry | None = None

    @model_validator(mode="after")
    def _overall_follows_from_criteria(self) -> "SpeakingEvaluation":
        """The arithmetic must be reproducible from the parts.

        A band that does not follow from its own criteria is the
        calculation-trace equivalent of an unverifiable quote: it looks like a
        result and cannot be checked.
        """
        scored = [c.band for c in self.criteria if c.scored and c.band is not None]

        if len(self.overall.included_criteria) != len(scored):
            raise ValueError(
                f"overall lists {len(self.overall.included_criteria)} included criteria "
                f"but {len(scored)} actually scored"
            )

        enough = len(scored) >= self.overall.min_criteria_required

        if self.overall.band is None and enough:
            raise ValueError(
                f"{len(scored)} criteria scored (threshold "
                f"{self.overall.min_criteria_required}) but no overall band was computed"
            )
        if self.overall.band is not None and not enough:
            raise ValueError(
                f"an overall band of {self.overall.band} was computed from {len(scored)} "
                f"criteria, below the threshold of {self.overall.min_criteria_required}. "
                f"Such a band describes which agents survived, not the candidate (BUG-040)"
            )
        if self.overall.band is not None and scored:
            mean = sum(scored) / len(scored)
            expected = round_ielts_band(mean)
            if abs(expected - self.overall.band) > 1e-9:
                raise ValueError(
                    f"overall band {self.overall.band} does not follow from the criteria; "
                    f"mean {mean:.4f} rounds to {expected}"
                )
            if (
                self.overall.unrounded_mean is not None
                and abs(self.overall.unrounded_mean - mean) > 1e-9
            ):
                raise ValueError(
                    f"stated unrounded_mean {self.overall.unrounded_mean}, computed {mean:.4f}"
                )
        return self

    def measurement_ids(self) -> set[str]:
        return {m.id for m in self.provenance.measurements}

    def unresolved_references(self) -> list[str]:
        """Measurement ids referenced by a criterion but absent from provenance.

        Schema shape cannot express this -- it is a cross-field reference -- so it
        is checked here and mirrored by ``Validate`` in the Go package.
        """
        known = self.measurement_ids()
        missing: list[str] = []
        for c in self.criteria:
            for mid in c.measurements:
                if mid not in known:
                    missing.append(f"{c.criterion_id.value}.measurements -> {mid}")
            for ev in c.evidence:
                if ev.measurement_id and ev.measurement_id not in known:
                    missing.append(f"{c.criterion_id.value}.evidence -> {ev.measurement_id}")
        return missing
