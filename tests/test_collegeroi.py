from __future__ import annotations

from unittest.mock import patch

import pytest

from fairdeal.collegeroi import RULES, run
from fairdeal.engine import DEFAULT_RULES
from fairdeal.scorecard import ScorecardError, SchoolProfile


def _profile(net_price=17140.5, earnings=48560.0, completion=0.7006) -> SchoolProfile:
    return SchoolProfile(
        name="University of San Francisco",
        city="San Francisco",
        state="CA",
        net_price_annual=net_price,
        earnings_10yr_median=earnings,
        completion_rate_4yr=completion,
    )


def _run(profile, school="University of San Francisco", major=None) -> dict:
    with patch("fairdeal.collegeroi.scorecard.find_school", return_value=profile):
        return run(school, major)


def test_full_data_produces_a_single_rated_result() -> None:
    result = _run(_profile())
    assert len(result["results"]) == 1
    row = result["results"][0]

    assert set(row) == {"title", "rating", "delta", "explanation", "completion_rate_4yr"}
    assert row["title"] == "University of San Francisco"
    assert row["rating"] == "borderline"  # 4 x 17,140.5 = 68,562 -> 1.41x of 48,560
    assert row["delta"] == pytest.approx(68_562.0 / 48_560.0)
    assert result["data_source"] == "college-scorecard"
    assert result["reply_text"] == "University of San Francisco: borderline ROI — 4-year cost is 1.4x typical 10-year earnings."


def test_cost_ratio_is_four_years_of_net_price_over_ten_year_earnings() -> None:
    row = _run(_profile(net_price=10_000.0, earnings=40_000.0))["results"][0]

    assert row["delta"] == pytest.approx(1.0)
    assert row["completion_rate_4yr"] == pytest.approx(0.7006)


@pytest.mark.parametrize(
    ("net_price", "earnings", "expected"),
    [
        (10_000.0, 40_000.0, "fair"),        # exactly 1.00x -> fair_max is inclusive
        (5_000.0, 40_000.0, "fair"),         # 0.50x
        (10_100.0, 40_000.0, "borderline"),  # 1.01x, just over fair_max
        (25_000.0, 40_000.0, "borderline"),  # exactly 2.50x -> borderline_max is inclusive
        (25_100.0, 40_000.0, "unfair"),      # 2.51x, just over borderline_max
    ],
)
def test_threshold_boundaries(net_price, earnings, expected) -> None:
    assert _run(_profile(net_price=net_price, earnings=earnings))["results"][0]["rating"] == expected


def test_missing_net_price_degrades_to_unknown() -> None:
    result = _run(_profile(net_price=None))
    row = result["results"][0]

    assert row["rating"] == "unknown"
    assert row["delta"] is None
    assert "net-price" in row["explanation"]
    assert "not enough College Scorecard data" in result["reply_text"]


def test_missing_earnings_degrades_to_unknown() -> None:
    row = _run(_profile(earnings=None))["results"][0]

    assert row["rating"] == "unknown"
    assert row["delta"] is None
    assert "10-year earnings" in row["explanation"]


def test_all_fields_suppressed_names_both_gaps_and_still_returns_a_row() -> None:
    row = _run(_profile(net_price=None, earnings=None, completion=None))["results"][0]

    assert row["rating"] == "unknown"
    assert "net-price" in row["explanation"] and "10-year earnings" in row["explanation"]
    assert row["completion_rate_4yr"] is None


def test_scorecard_error_degrades_to_empty_results() -> None:
    with patch("fairdeal.collegeroi.scorecard.find_school", side_effect=ScorecardError("no school found")):
        result = run("Hogwarts", "Potions")

    assert result["results"] == []
    assert "couldn't find" in result["reply_text"]
    assert result["data_source"] == "college-scorecard"


def test_major_is_acknowledged_not_silently_ignored() -> None:
    row = _run(_profile(), major="Computer Science")["results"][0]

    assert "Computer Science" in row["explanation"]
    assert "school level" in row["explanation"]


def test_no_major_still_discloses_the_school_level_limitation() -> None:
    row = _run(_profile())["results"][0]

    assert "school level" in row["explanation"]


def test_local_rules_do_not_mutate_engine_defaults() -> None:
    assert "college_cost_ratio" in RULES
    assert "college_cost_ratio" not in DEFAULT_RULES
    assert RULES["college_cost_ratio"] == {"fair_max": 1.0, "borderline_max": 2.5}
