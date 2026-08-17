from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from fairdeal.bls import BLSError, cpi_drift, cpi_series_for

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_response(payload, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _fixture_payload() -> dict:
    return json.loads((FIXTURES / "bls_cpi_sf.json").read_text())


def test_cpi_drift_computes_latest_over_earliest_from_fixture() -> None:
    payload = _fixture_payload()
    points = payload["Results"]["series"][0]["data"]
    expected = float(points[0]["value"]) / float(points[-1]["value"])  # BLS returns newest-first

    with patch("fairdeal.bls.requests.post", return_value=_mock_response(payload)) as mock_post:
        drift = cpi_drift("CUURS49BSA0", "2023", "2024")

    assert drift == pytest.approx(expected)
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["seriesid"] == ["CUURS49BSA0"]
    assert kwargs["json"]["startyear"] == "2023"
    assert kwargs["json"]["endyear"] == "2024"


def test_cpi_drift_raises_on_non_200() -> None:
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    with patch("fairdeal.bls.requests.post", return_value=resp):
        with pytest.raises(BLSError, match="BLS request failed"):
            cpi_drift("CUURS49BSA0", "2023", "2024")


def test_cpi_drift_raises_on_unsuccessful_status() -> None:
    payload = {"status": "REQUEST_NOT_PROCESSED", "message": ["invalid series"]}
    with patch("fairdeal.bls.requests.post", return_value=_mock_response(payload)):
        with pytest.raises(BLSError, match="BLS request unsuccessful"):
            cpi_drift("CUURS49BSA0", "2023", "2024")


def test_cpi_drift_raises_on_malformed_no_data() -> None:
    payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": []}]}}
    with patch("fairdeal.bls.requests.post", return_value=_mock_response(payload)):
        with pytest.raises(BLSError, match="no CPI data"):
            cpi_drift("CUURS49BSA0", "2023", "2024")


def test_cpi_series_for_matches_case_insensitive_substring() -> None:
    assert cpi_series_for("San Francisco") == "CUURS49BSA0"
    assert cpi_series_for("OAKLAND, CA") == "CUURS49BSA0"
    assert cpi_series_for("Daly City, san francisco bay area") == "CUURS49BSA0"


def test_cpi_series_for_unmapped_city_returns_none() -> None:
    assert cpi_series_for("Fresno") is None
    assert cpi_series_for("") is None
