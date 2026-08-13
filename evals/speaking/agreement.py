"""Band agreement metrics (SPEAK-EVAL-007, plan section 11.2).

Deterministic arithmetic, deliberately. The plan is explicit: *"Do not use an
LLM judge to decide whether a numeric band matches a human label."* Comparing
6.5 to 7.0 is subtraction. Routing that through a model would add cost, variance
and a second thing to validate, in exchange for nothing.

Every figure carries its sample size, and comparisons carry a bootstrap
confidence interval. On n=12 that interval is wide, and it should be: a point
estimate of "83% agreement" from twelve items invites a confidence the data
cannot support. Reporting the interval is what stops the number being read as
more than it is.

Nothing here knows about lanes or manifests. It takes paired (predicted,
reference) bands and returns statistics.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

# IELTS bands move in half steps, so "within half a band" is the tolerance that
# corresponds to one step of the scale rather than an arbitrary epsilon.
HALF_BAND = 0.5
EPSILON = 1e-9

DEFAULT_BOOTSTRAP_SAMPLES = 10_000
DEFAULT_SEED = 20260808
"""Fixed by default. A confidence interval that moves every run cannot be
compared against the last run, which is the main thing anyone wants to do with
it."""


@dataclass
class Interval:
    low: float
    high: float

    def __str__(self) -> str:
        return f"[{self.low:.3f}, {self.high:.3f}]"


@dataclass
class AgreementMetrics:
    """The section 11.2 battery, over one set of paired bands."""

    n: int

    exact_agreement: float | None = None
    within_half_band: float | None = None
    within_one_band: float | None = None

    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    """Signed mean error. Separate from MAE because direction matters: a system
    that is uniformly half a band generous is recalibrated by subtracting half a
    band, and one that is randomly wrong by the same magnitude is not."""

    overscore_rate: float | None = None
    underscore_rate: float | None = None
    overscore_by_more_than_one: float | None = None
    underscore_by_more_than_one: float | None = None

    quadratic_weighted_kappa: float | None = None
    spearman: float | None = None

    mae_ci95: Interval | None = None
    within_half_band_ci95: Interval | None = None
    bias_ci95: Interval | None = None

    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    caveat: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("mae_ci95", "within_half_band_ci95", "bias_ci95"):
            value = getattr(self, key)
            payload[key] = [value.low, value.high] if value else None
        return payload


def compute_agreement(
    predicted: Sequence[float],
    reference: Sequence[float],
    *,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_SEED,
    min_n_for_stable_stats: int = 10,
) -> AgreementMetrics:
    """Compare predicted bands against human labels.

    Returns a metrics object with `n=0` and everything None when there is
    nothing to compare, rather than raising or returning zeros. Zero MAE on an
    empty set is the most dangerous number this module could produce: it is
    indistinguishable from perfect agreement.
    """
    if len(predicted) != len(reference):
        raise ValueError(
            f"{len(predicted)} predictions against {len(reference)} references; "
            f"the pairing is broken and no statistic over it means anything"
        )

    n = len(predicted)
    metrics = AgreementMetrics(n=n)
    if n == 0:
        metrics.caveat = "no items produced a comparable band; nothing was measured"
        return metrics

    errors = [p - r for p, r in zip(predicted, reference)]
    absolute = [abs(e) for e in errors]

    metrics.exact_agreement = _rate(a <= EPSILON for a in absolute)
    metrics.within_half_band = _rate(a <= HALF_BAND + EPSILON for a in absolute)
    metrics.within_one_band = _rate(a <= 1.0 + EPSILON for a in absolute)

    metrics.mae = _round(sum(absolute) / n)
    metrics.rmse = _round(math.sqrt(sum(e * e for e in errors) / n))
    metrics.bias = _round(sum(errors) / n)

    metrics.overscore_rate = _rate(e > EPSILON for e in errors)
    metrics.underscore_rate = _rate(e < -EPSILON for e in errors)
    metrics.overscore_by_more_than_one = _rate(e > 1.0 + EPSILON for e in errors)
    metrics.underscore_by_more_than_one = _rate(e < -1.0 - EPSILON for e in errors)

    metrics.quadratic_weighted_kappa = _qwk(predicted, reference)
    metrics.spearman = _spearman(predicted, reference)
    metrics.confusion = _confusion(predicted, reference)

    if n >= 2:
        rng = random.Random(seed)
        metrics.mae_ci95 = _bootstrap(
            errors, lambda s: sum(abs(e) for e in s) / len(s), bootstrap_samples, rng
        )
        metrics.bias_ci95 = _bootstrap(
            errors, lambda s: sum(s) / len(s), bootstrap_samples, rng
        )
        metrics.within_half_band_ci95 = _bootstrap(
            absolute,
            lambda s: sum(1 for a in s if a <= HALF_BAND + EPSILON) / len(s),
            bootstrap_samples,
            rng,
        )

    if n < min_n_for_stable_stats:
        metrics.caveat = (
            f"n={n}. Too few items for a stable estimate -- read the confidence "
            f"interval, not the point estimate. This is a measurement of the "
            f"available data, not a validation of the system."
        )

    return metrics


def _rate(flags) -> float:
    values = list(flags)
    return _round(sum(1 for f in values if f) / len(values)) if values else 0.0


def _round(value: float) -> float:
    return round(value, 4)


def _bootstrap(
    sample: Sequence[float],
    statistic,
    iterations: int,
    rng: random.Random,
) -> Interval:
    """Percentile bootstrap over item-level resamples.

    Resampling items rather than assuming a distribution, because band errors on
    a dozen items are not normally distributed and no amount of wishing makes a
    t-interval appropriate here.
    """
    n = len(sample)
    estimates = []
    for _ in range(iterations):
        resample = [sample[rng.randrange(n)] for _ in range(n)]
        estimates.append(statistic(resample))
    estimates.sort()

    low = estimates[int(0.025 * (iterations - 1))]
    high = estimates[int(0.975 * (iterations - 1))]
    return Interval(_round(low), _round(high))


def paired_bootstrap_difference(
    candidate_errors: Sequence[float],
    baseline_errors: Sequence[float],
    *,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Compare two systems on the SAME items.

    Paired, because the items are the same and their difficulty is shared. An
    unpaired comparison throws that away and widens the interval for no reason,
    which is how a real improvement gets reported as inconclusive.

    Returns the MAE difference (candidate minus baseline; negative is better)
    and its interval. An interval spanning zero means the data does not
    distinguish the two, which is a finding and should be reported as one rather
    than resolved by picking the smaller point estimate.
    """
    if len(candidate_errors) != len(baseline_errors):
        raise ValueError("paired comparison needs the same items on both sides")

    n = len(candidate_errors)
    if n == 0:
        return {"n": 0, "mae_difference": None, "ci95": None, "conclusive": False}

    pairs = list(zip(candidate_errors, baseline_errors))
    observed = (
        sum(abs(c) for c, _ in pairs) / n - sum(abs(b) for _, b in pairs) / n
    )

    rng = random.Random(seed)
    differences = []
    for _ in range(bootstrap_samples):
        resample = [pairs[rng.randrange(n)] for _ in range(n)]
        differences.append(
            sum(abs(c) for c, _ in resample) / n - sum(abs(b) for _, b in resample) / n
        )
    differences.sort()

    low = differences[int(0.025 * (bootstrap_samples - 1))]
    high = differences[int(0.975 * (bootstrap_samples - 1))]

    return {
        "n": n,
        "mae_difference": _round(observed),
        "ci95": [_round(low), _round(high)],
        "conclusive": not (low <= 0.0 <= high),
    }


def _bucket(band: float) -> str:
    return f"{band:.1f}"


def _confusion(predicted: Sequence[float], reference: Sequence[float]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for p, r in zip(predicted, reference):
        row = matrix.setdefault(_bucket(r), {})
        row[_bucket(p)] = row.get(_bucket(p), 0) + 1
    return matrix


def _qwk(predicted: Sequence[float], reference: Sequence[float]) -> float | None:
    """Quadratic weighted kappa over half-band buckets.

    The right statistic for an ordinal scale: it penalises being three bands out
    far more than being one out, which plain accuracy does not, and it corrects
    for the agreement you would get by chance -- which matters when the reference
    bands cluster, as IELTS bands do.
    """
    n = len(predicted)
    if n < 2:
        return None

    levels = sorted({round(v * 2) for v in list(predicted) + list(reference)})
    index = {level: i for i, level in enumerate(levels)}
    size = len(levels)
    if size < 2:
        # Everything landed on one band. Kappa is undefined rather than perfect:
        # there is no variation for it to explain.
        return None

    observed = [[0.0] * size for _ in range(size)]
    for p, r in zip(predicted, reference):
        observed[index[round(r * 2)]][index[round(p * 2)]] += 1

    reference_totals = [sum(row) for row in observed]
    predicted_totals = [sum(observed[i][j] for i in range(size)) for j in range(size)]

    numerator = 0.0
    denominator = 0.0
    for i in range(size):
        for j in range(size):
            weight = ((i - j) ** 2) / ((size - 1) ** 2)
            expected = reference_totals[i] * predicted_totals[j] / n
            numerator += weight * observed[i][j]
            denominator += weight * expected

    if denominator == 0:
        return None
    return _round(1.0 - numerator / denominator)


def _spearman(predicted: Sequence[float], reference: Sequence[float]) -> float | None:
    """Rank correlation, as a secondary ranking measure.

    Secondary on purpose: a system that ranks candidates perfectly but is a full
    band generous throughout has a Spearman of 1.0 and is still unusable for
    telling someone their band. It answers a different question from MAE.
    """
    n = len(predicted)
    if n < 3:
        return None

    p_ranks = _ranks(predicted)
    r_ranks = _ranks(reference)

    mean_p = sum(p_ranks) / n
    mean_r = sum(r_ranks) / n
    covariance = sum((a - mean_p) * (b - mean_r) for a, b in zip(p_ranks, r_ranks))
    variance_p = sum((a - mean_p) ** 2 for a in p_ranks)
    variance_r = sum((b - mean_r) ** 2 for b in r_ranks)

    if variance_p == 0 or variance_r == 0:
        return None
    return _round(covariance / math.sqrt(variance_p * variance_r))


def _ranks(values: Sequence[float]) -> list[float]:
    """Average ranks, so ties do not distort the correlation. Band data ties
    constantly -- twelve items across five distinct bands guarantees it."""
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)

    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and values[ordered[end + 1]] == values[ordered[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for k in range(position, end + 1):
            ranks[ordered[k]] = average
        position = end + 1

    return ranks
