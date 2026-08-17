from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fairdeal.scorecard import ScorecardError, SchoolProfile, find_school

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_response(payload) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _fixture_payload() -> dict:
    return json.loads((FIXTURES / "scorecard_usf.json").read_text())


def test_find_school_prefers_exact_match_over_api_result_order() -> None:
    # The fixture's first result is UC-San Francisco (a different, grad-only
    # school); "University of San Francisco" is a later entry.
    payload = _fixture_payload()
    assert payload["results"][0]["school"]["name"] != "University of San Francisco"

    with patch("fairdeal.scorecard.requests.get", return_value=_mock_response(payload)):
        profile = find_school("University of San Francisco")

    assert profile.name == "University of San Francisco"
    assert profile.net_price_annual == pytest.approx(17140.5)
    assert profile.earnings_10yr_median == pytest.approx(48560.0)
    assert profile.completion_rate_4yr == pytest.approx(0.7006)


def test_find_school_falls_back_to_first_result_when_no_exact_match() -> None:
    payload = _fixture_payload()
    with patch("fairdeal.scorecard.requests.get", return_value=_mock_response(payload)):
        profile = find_school("some school name not in the fixture at all")

    assert profile.name == payload["results"][0]["school"]["name"]


def test_find_school_no_results_raises() -> None:
    with patch("fairdeal.scorecard.requests.get", return_value=_mock_response({"results": []})):
        with pytest.raises(ScorecardError, match="no school found"):
            find_school("zzzz not a real school")


def test_find_school_missing_nested_fields_return_none_not_crash() -> None:
    payload = {
        "results": [
            {
                "school": {"name": "Sparse College", "city": "Nowhere", "state": "XX"},
                "latest": {"cost": {}, "earnings": {}, "completion": {}},
            }
        ]
    }
    with patch("fairdeal.scorecard.requests.get", return_value=_mock_response(payload)):
        profile = find_school("Sparse College")

    assert profile == SchoolProfile(
        name="Sparse College",
        city="Nowhere",
        state="XX",
        net_price_annual=None,
        earnings_10yr_median=None,
        completion_rate_4yr=None,
    )
