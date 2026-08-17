"""Module 3: college ROI — is this school's price worth what its graduates earn?

Compares the 4-year net cost of attending against what a typical student earns
10 years after entry, both from the federal College Scorecard.
"""

from __future__ import annotations

from fairdeal import scorecard
from fairdeal.engine import DEFAULT_RULES, Benchmark, Claim, evaluate
from fairdeal.scorecard import ScorecardError

DATA_SOURCE = "college-scorecard"

# Local rules — a COPY, so module 3's thresholds can never leak into module 1's
# rent verdicts.
#
# Threshold reasoning: the ratio is (4-year net cost) / (median earnings 10 years
# after entry). Under 1.0x, the whole degree costs less than one typical year of
# a mid-career graduate's salary — recoverable fast, "fair". Up to 2.5x is
# roughly "a couple of years of that salary pays it off", which is defensible but
# worth thinking hard about — "borderline". Above that the debt outruns the
# earnings the degree actually produces — "unfair".
#
# Be clear about what this is: a financial-literacy heuristic we chose, NOT an
# official benchmark — in the same spirit as hud.py documenting that FMR is a
# 40th-percentile figure rather than a market median. Reasonable people would
# pick 0.8x/2.0x. It also ignores aid variance, time-to-degree, and the fact
# that Scorecard earnings cover everyone who ENTERED, graduates or not.
RULES = {**DEFAULT_RULES, "college_cost_ratio": {"fair_max": 1.0, "borderline_max": 2.5}}

# Scorecard publishes major-level (CIP-code) earnings, but they're suppressed for
# most program/school combinations, so a per-major comparison would be mostly
# holes. `major` is carried for display and disclosed in the explanation instead
# of being silently dropped.
_MAJOR_CAVEAT = "ROI is calculated at the school level; major-specific breakdowns aren't available."


def run(school: str, major: str | None = None) -> dict:
    """Rate a school's 4-year net cost against its graduates' 10-year earnings.

    `major` is accepted for context/display only — see _MAJOR_CAVEAT. Degrades to
    an empty result set (never raises) when the school can't be looked up, and to
    rating="unknown" when Scorecard suppressed the numbers the ratio needs.
    """
    try:
        profile = scorecard.find_school(school)
    except ScorecardError as exc:
        return {
            "reply_text": (
                f"I couldn't find {school!r} in the College Scorecard database ({exc}). "
                "Try the school's full official name."
            ),
            "data_source": DATA_SOURCE,
            "results": [],
        }

    major_note = f" You asked about {major}. {_MAJOR_CAVEAT}" if major else f" {_MAJOR_CAVEAT}"

    four_year_cost = profile.net_price_annual * 4 if profile.net_price_annual is not None else None
    claim = Claim(
        kind="college_cost_ratio",
        value=four_year_cost,
        context={"school": profile.name, "major": major, "net_price_annual": profile.net_price_annual},
    )
    benchmark = Benchmark(
        source="College Scorecard",
        name="10-year median earnings",
        value=profile.earnings_10yr_median,
        meta={"city": profile.city, "state": profile.state},
    )
    verdict = evaluate(claim, [benchmark], RULES)

    missing = [
        label
        for label, value in (("net-price", profile.net_price_annual), ("10-year earnings", profile.earnings_10yr_median))
        if value is None
    ]
    if missing:
        # engine.evaluate already returned "unknown"; swap its generic wording for
        # the actual reason so the user knows it's suppressed data, not a bug.
        explanation = (
            f"College Scorecard doesn't publish {' or '.join(missing)} data for {profile.name}, "
            f"so its ROI can't be rated.{major_note}"
        )
        reply_text = f"{profile.name}: not enough College Scorecard data to rate ROI."
    else:
        explanation = (
            f"A 4-year net cost of ${four_year_cost:,.0f} is {verdict.delta:.2f}x the ${profile.earnings_10yr_median:,.0f} "
            f"median earnings of students 10 years after entry (College Scorecard) — {verdict.rating}.{major_note}"
        )
        reply_text = (
            f"{profile.name}: {verdict.rating} ROI — 4-year cost is "
            f"{verdict.delta:.1f}x typical 10-year earnings."
        )

    # Single-item list for frontend consistency with the other three modules.
    return {
        "reply_text": reply_text,
        "data_source": DATA_SOURCE,
        "results": [
            {
                "title": profile.name,
                "rating": verdict.rating,
                "delta": verdict.delta,
                "explanation": explanation,
                "completion_rate_4yr": profile.completion_rate_4yr,
            }
        ],
    }
