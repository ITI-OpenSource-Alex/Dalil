"""Fact identity for GOA-038's long-term memory.

The rules in this module decide two questions that everything else depends on:
what counts as *the same* fact, and how many rows a fact type may hold per user.
Get either wrong and an acceptance criterion breaks silently -- a corrected GPA
becomes a second row instead of an update, or two mentioned programs collapse
into one.
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

FactType = Literal["degree", "gpa", "target_country", "mentioned_program", "concern"]

# One row per (user, type). A new value replaces the old one.
SINGLE_VALUED_TYPES: frozenset[str] = frozenset({"degree", "gpa", "target_country"})

# One row per (user, type, normalised value). Two programs are two facts.
MULTI_VALUED_TYPES: frozenset[str] = frozenset({"mentioned_program", "concern"})

# Below this, a contradicting value is discarded rather than allowed to evict the
# stored one -- so a hedged aside ("maybe Canada, I'm not sure") cannot overwrite
# a target country the user stated plainly. Enforced in SQL as well as here; this
# constant and the WHERE clause in facts_repository.upsert_fact must agree.
CONTRADICTION_MIN_CONFIDENCE = 0.60

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = re.compile(r"[\s.,;:!?\"'()\[\]]+$")


def normalise(value: str) -> str:
    """Reduce a fact value to its identity form.

    Used for two things: the `fact_key` of multi-valued types, and the "is this
    the same fact or a contradicting one?" comparison. That makes it the single
    place where "TU Munich", "tu munich " and "TU Munich." become one fact
    rather than three.

    Deliberately conservative -- no stemming, no synonym folding, no stripping of
    internal punctuation. "MSc Data Science" and "Data Science MSc" stay
    distinct, which produces a duplicate-looking pair occasionally but never
    silently merges two things the user meant separately.
    """
    collapsed = _WHITESPACE.sub(" ", value).strip().lower()
    return _TRAILING_PUNCTUATION.sub("", collapsed)


class FactCandidate(BaseModel):
    """A fact proposed by extraction, before the repository decides its fate."""

    fact_type: FactType
    fact_value: str = Field(..., min_length=1, max_length=512)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_session: Optional[str] = None

    @property
    def fact_key(self) -> str:
        """The discriminator stored alongside fact_type.

        Empty for single-valued types, so the unique index pins them to one row
        per user. The normalised value for multi-valued types, so the same index
        admits one row per distinct value. One index, two cardinality rules.
        """
        if self.fact_type in MULTI_VALUED_TYPES:
            return normalise(self.fact_value)[:255]
        return ""


class StoredFact(BaseModel):
    """A fact as it exists in the database, on its way into a prompt."""

    fact_type: FactType
    fact_key: str
    fact_value: str
    confidence: float
    revision: int
