from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fairdeal.hud import HUDError, STATIC_FMR_FALLBACK, fmr_for

SF_ADDRESS = {
    "road": "South Van Ness Avenue",
    "suburb": "Mission",
    "city": "San Francisco",
    "state": "California",
    "ISO3166-2-lvl4": "US-CA",
    "postcode": "94102",
    "country": "United States",
    "country_code": "us",
}


@pytest.fixture(autouse=True)
def _no_hud_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUD_API_TOKEN", raising=False)


def test_fmr_for_falls_back_to_static_without_token() -> None:
    with patch("fairdeal.hud.reverse_geocode", return_value=dict(SF_ADDRESS)):
        bench = fmr_for(37.7748559, -122.4193609, bedrooms=2)

    assert bench.meta["live"] is False
    assert bench.value == pytest.approx(float(STATIC_FMR_FALLBACK[("san francisco", 2)]))
    assert "static fallback" in bench.source
    assert "San Francisco" in bench.name


def test_fallback_handles_city_substring_and_bedrooms() -> None:
    # "san francisco" must match as a substring of the lowercased city name.
    with patch("fairdeal.hud.reverse_geocode", return_value={"city": "SAN FRANCISCO"}):
        bench = fmr_for(0.0, 0.0, bedrooms=0)

    assert bench.value == pytest.approx(float(STATIC_FMR_FALLBACK[("san francisco", 0)]))
    assert bench.meta["live"] is False


def test_fallback_unmatched_city_raises_hud_error() -> None:
    with patch("fairdeal.hud.reverse_geocode", return_value={"city": "Fresno"}):
        with pytest.raises(HUDError, match="no static FMR fallback"):
            fmr_for(36.7378, -119.7871, bedrooms=1)


def test_fallback_matched_city_unmatched_bedrooms_raises_hud_error() -> None:
    with patch("fairdeal.hud.reverse_geocode", return_value=dict(SF_ADDRESS)):
        with pytest.raises(HUDError, match="no static FMR fallback"):
            fmr_for(37.7748559, -122.4193609, bedrooms=5)


def test_fallback_empty_city_raises_hud_error() -> None:
    with patch("fairdeal.hud.reverse_geocode", return_value={}):
        with pytest.raises(HUDError, match="no static FMR fallback"):
            fmr_for(0.0, 0.0, bedrooms=1)


def test_fallback_covers_berkeley_and_daly_city() -> None:
    # Every city in fairdeal/craigslist.py's seed listings must resolve here,
    # or the app's own demo data produces avoidable "unknown" verdicts.
    with patch("fairdeal.hud.reverse_geocode", return_value={"city": "Berkeley"}):
        assert fmr_for(0.0, 0.0, bedrooms=1).value == pytest.approx(float(STATIC_FMR_FALLBACK[("berkeley", 1)]))
    with patch("fairdeal.hud.reverse_geocode", return_value={"city": "Daly City"}):
        assert fmr_for(0.0, 0.0, bedrooms=2).value == pytest.approx(float(STATIC_FMR_FALLBACK[("daly city", 2)]))


# -- live HUD path (HUD_API_TOKEN set) --------------------------------------

LIVE_ADDRESS = {"city": "San Francisco", "county": "San Francisco", "ISO3166-2-lvl4": "US-CA"}


def _json_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_live_fmr_parses_documented_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    # listCounties is documented as {"data": [...]}, not a bare list — and
    # basicdata keys are "One-Bedroom"/"Two-Bedroom"/etc, not "1BR"/"2BR".
    monkeypatch.setenv("HUD_API_TOKEN", "test-token")
    counties_response = _json_response({"data": [{"county_name": "San Francisco County", "fips_code": "0607599999"}]})
    data_response = _json_response(
        {"data": {"basicdata": {"Efficiency": 2149, "One-Bedroom": 2561, "Two-Bedroom": 3271}, "year": 2026}}
    )
    with (
        patch("fairdeal.hud.reverse_geocode", return_value=dict(LIVE_ADDRESS)),
        patch("fairdeal.hud.requests.get", side_effect=[counties_response, data_response]),
    ):
        bench = fmr_for(37.7749, -122.4194, bedrooms=2)

    assert bench.value == pytest.approx(3271.0)
    assert bench.meta["live"] is True
    assert bench.meta["year"] == 2026


def test_live_fmr_handles_small_area_fmr_list_shaped_basicdata(monkeypatch: pytest.MonkeyPatch) -> None:
    # Small Area FMR responses can return basicdata as a list of ZIP-level
    # rows instead of a single dict.
    monkeypatch.setenv("HUD_API_TOKEN", "test-token")
    counties_response = _json_response({"data": [{"county_name": "San Francisco County", "fips_code": "0607599999"}]})
    data_response = _json_response(
        {"data": {"basicdata": [{"Efficiency": 2000, "One-Bedroom": 2400, "zip_code": "94102"}], "year": 2026}}
    )
    with (
        patch("fairdeal.hud.reverse_geocode", return_value=dict(LIVE_ADDRESS)),
        patch("fairdeal.hud.requests.get", side_effect=[counties_response, data_response]),
    ):
        bench = fmr_for(37.7749, -122.4194, bedrooms=1)

    assert bench.value == pytest.approx(2400.0)


def test_live_fmr_clamps_bedrooms_above_four(monkeypatch: pytest.MonkeyPatch) -> None:
    # HUD only publishes up to "Four-Bedroom" — a 5BR+ request should reuse it.
    monkeypatch.setenv("HUD_API_TOKEN", "test-token")
    counties_response = _json_response({"data": [{"county_name": "San Francisco County", "fips_code": "0607599999"}]})
    data_response = _json_response({"data": {"basicdata": {"Four-Bedroom": 5200}, "year": 2026}})
    with (
        patch("fairdeal.hud.reverse_geocode", return_value=dict(LIVE_ADDRESS)),
        patch("fairdeal.hud.requests.get", side_effect=[counties_response, data_response]),
    ):
        bench = fmr_for(37.7749, -122.4194, bedrooms=6)

    assert bench.value == pytest.approx(5200.0)


def test_live_fmr_no_county_match_raises_hud_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUD_API_TOKEN", "test-token")
    counties_response = _json_response({"data": [{"county_name": "Some Other County", "fips_code": "0699999999"}]})
    with (
        patch("fairdeal.hud.reverse_geocode", return_value=dict(LIVE_ADDRESS)),
        patch("fairdeal.hud.requests.get", return_value=counties_response),
    ):
        with pytest.raises(HUDError, match="no HUD FMR entity found"):
            fmr_for(37.7749, -122.4194, bedrooms=1)
