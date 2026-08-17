from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fairdeal.geocode import GeoPoint, GeocodeError, _reverse_geocode_cached, geocode, haversine, reverse_geocode

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_throttle_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nominatim throttling would sleep ~1s per test request; the network is mocked anyway.
    monkeypatch.setattr("fairdeal.geocode.time.sleep", lambda _s: None)


@pytest.fixture(autouse=True)
def _clear_reverse_geocode_cache() -> None:
    # reverse_geocode is lru_cache'd process-wide; without clearing, a test
    # could observe another test's mocked response for the same rounded coords.
    _reverse_geocode_cached.cache_clear()


def _mock_response(payload) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_geocode_parses_search_fixture() -> None:
    payload = json.loads((FIXTURES / "nominatim_search_usf.json").read_text())
    with patch("fairdeal.geocode.requests.get", return_value=_mock_response(payload)) as mock_get:
        point = geocode("University of San Francisco")

    assert isinstance(point, GeoPoint)
    assert point.lat == pytest.approx(37.7793627)
    assert point.lon == pytest.approx(-122.4514473)
    assert "University of San Francisco" in point.display_name
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["q"] == "University of San Francisco"
    assert kwargs["params"]["limit"] == 1


def test_geocode_empty_results_raises() -> None:
    with patch("fairdeal.geocode.requests.get", return_value=_mock_response([])):
        with pytest.raises(GeocodeError, match="no geocoding match"):
            geocode("zzzz definitely not a real place 12345")


def test_reverse_geocode_parses_address_from_fixture() -> None:
    payload = json.loads((FIXTURES / "nominatim_reverse_sf.json").read_text())
    with patch("fairdeal.geocode.requests.get", return_value=_mock_response(payload)):
        address = reverse_geocode(37.7748559, -122.4193609)

    assert address["city"] == "San Francisco"
    assert address["state"] == "California"
    assert address["ISO3166-2-lvl4"] == "US-CA"
    # SF is a consolidated city-county, so "county" is legitimately absent.
    assert "county" not in address


def test_reverse_geocode_error_response_raises() -> None:
    with patch("fairdeal.geocode.requests.get", return_value=_mock_response({"error": "Unable to geocode"})):
        with pytest.raises(GeocodeError, match="no reverse geocoding match"):
            reverse_geocode(0.0, 0.0)


def test_haversine_same_point_is_zero() -> None:
    p = GeoPoint(lat=37.7749, lon=-122.4194, display_name="SF")
    assert haversine(p, p) == pytest.approx(0.0, abs=1e-9)


def test_haversine_sf_to_oakland_plausible_range() -> None:
    sf = GeoPoint(lat=37.7749, lon=-122.4194, display_name="San Francisco")
    oakland = GeoPoint(lat=37.8044, lon=-122.2712, display_name="Oakland")
    miles = haversine(sf, oakland)
    # Downtown SF to Lake Merritt is roughly 8-11 miles across the bay.
    assert 5.0 < miles < 15.0
