from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


@dataclass
class Claim:
    """A single assertion to be judged, e.g. a listed rent or a lease term."""

    kind: str
    value: float | str
    context: dict = field(default_factory=dict)


@dataclass
class Benchmark:
    """A reference figure a claim is judged against, already normalised upstream."""

    source: str
    name: str
    value: float | str
    meta: dict = field(default_factory=dict)


@dataclass
class Verdict:
    rating: str
    delta: float | None
    explanation: str
    claim: Claim
    benchmarks: list[Benchmark]


# Modules 2-4 add their own kinds to a copy of this.
DEFAULT_RULES: dict = {
    "monthly_rent": {"fair_max": 1.05, "borderline_max": 1.20},
}


def _num(value) -> float | None:
    """Coerce to a usable comparison number, or None. Bools and NaN/inf are not numbers."""
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if isfinite(out) else None


def _fmt(value: float) -> str:
    return format(value, ",g")


def evaluate(claim: Claim, benchmarks: list[Benchmark], rules: dict) -> Verdict:
    """Rate a claim against its benchmarks using the multiplier thresholds in `rules`.

    Pure and total: upstream data is partial and untrusted, so anything that cannot be
    compared comes back as rating="unknown" with the reason in `explanation` — this
    never raises. `rules` is keyed by claim.kind, each value
    {"fair_max": float, "borderline_max": float}; benchmark values are used as given
    (any CPI adjustment happens upstream in hud.py/bls.py, not here).
    """
    benchmarks = list(benchmarks or [])

    def unknown(why: str) -> Verdict:
        return Verdict(rating="unknown", delta=None, explanation=why, claim=claim, benchmarks=benchmarks)

    rule = rules.get(claim.kind) if isinstance(rules, dict) else None
    if not isinstance(rule, dict):
        return unknown(f"No fairness rule configured for claim kind '{claim.kind}'.")

    fair_max, borderline_max = _num(rule.get("fair_max")), _num(rule.get("borderline_max"))
    if fair_max is None or borderline_max is None:
        return unknown(f"Rule for '{claim.kind}' is missing a numeric fair_max/borderline_max threshold.")

    claim_value = _num(claim.value)
    if claim_value is None:
        return unknown(f"Claim value {claim.value!r} is not numeric, so it cannot be compared.")

    # Primary benchmark: first one with a value we can actually divide by. A
    # non-positive benchmark is as unusable as a missing one — a negative one
    # would divide to a negative delta and read as "fair".
    primary = next((b for b in benchmarks if (_num(b.value) or 0) > 0), None)
    if primary is None:
        return unknown(f"No numeric benchmark to compare this {claim.kind} against.")

    benchmark_value = _num(primary.value)
    delta = claim_value / benchmark_value
    rating = "fair" if delta <= fair_max else "borderline" if delta <= borderline_max else "unfair"

    explanation = (
        f"{_fmt(claim_value)} is {delta:.2f}x the {primary.name} "
        f"({_fmt(benchmark_value)}, {primary.source}) — {rating}."
    )
    return Verdict(rating=rating, delta=delta, explanation=explanation, claim=claim, benchmarks=benchmarks)
