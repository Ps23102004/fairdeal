from __future__ import annotations

from unittest.mock import patch

import pytest

from fairdeal.engine import Benchmark
from fairdeal.geocode import GeoPoint, GeocodeError
from fairdeal.hud import HUDError
from fairdeal.rentcheck import DEFAULT_RADIUS_MILES, run
from fairdeal.search import Listing, SearchCriteria


def _criteria(anchors=("University of San Francisco",), budget=2500, bedrooms=2):
    return SearchCriteria(anchors=list(anchors), budget_monthly=budget, bedrooms=bedrooms, home_type=None)


def _usf_point():
    return GeoPoint(lat=37.7794, lon=-122.4514, display_name="University of San Francisco")


@pytest.fixture(autouse=True)
def _no_live_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    # web_references hits real DuckDuckGo network calls otherwise — every
    # test in this file would slow down and depend on network availability.
    monkeypatch.setattr("fairdeal.rentcheck.search_web", lambda query, max_results=5: [])


def _listing(price=2400, lat=37.7800, lon=-122.4520, title="Test listing", bedrooms=2, home_type="apartment"):
    return Listing(
        title=title,
        price=price,
        url="https://example.com/seed-listing/x",
        lat=lat,
        lon=lon,
        posted="2026-08-15",
        raw_location="San Francisco, CA",
        bedrooms=bedrooms,
        home_type=home_type,
    )


def _fmr_benchmark(value=2300.0, year="2026"):
    return Benchmark(source=f"HUD FMR {year}", name="FMR 2BR SF", value=value, meta={"live": True, "year": year})


def test_run_ranks_and_shapes_results() -> None:
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", return_value=_fmr_benchmark()),
    ):
        mock_get_provider.return_value.search.return_value = [_listing(price=2400)]
        result = run("2BR near USF, budget $2500/month")

    assert "results" in result and "reply_text" in result
    assert len(result["results"]) == 1
    row = result["results"][0]
    assert set(row) == {"title", "price", "url", "distance_miles", "rating", "delta", "explanation"}
    assert row["rating"] in ("fair", "borderline", "unfair", "unknown")
    assert row["distance_miles"] >= 0


def test_run_no_anchors_geocode_returns_empty_without_crashing() -> None:
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", side_effect=GeocodeError("no match")),
    ):
        result = run("somewhere unresolvable")

    assert result["results"] == []
    assert "couldn't locate" in result["reply_text"]


def test_run_no_results_reply_text_omits_budget_when_none() -> None:
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria(budget=None)),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
    ):
        mock_get_provider.return_value.search.return_value = []
        result = run("something near USF")

    assert "under $" not in result["reply_text"]
    assert "those places." in result["reply_text"]


def test_run_no_results_reply_text_includes_budget_when_stated() -> None:
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria(budget=2500)),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
    ):
        mock_get_provider.return_value.search.return_value = []
        result = run("something near USF under $2500")

    assert "under $2,500/month." in result["reply_text"]


def test_run_excludes_listings_beyond_radius() -> None:
    far_listing = _listing(price=2400, lat=38.5, lon=-121.5)  # well outside DEFAULT_RADIUS_MILES
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
    ):
        mock_get_provider.return_value.search.return_value = [far_listing]
        result = run("2BR near USF")

    assert result["results"] == []


def test_run_hud_failure_yields_unknown_rating_not_a_crash() -> None:
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", side_effect=HUDError("no coverage")),
    ):
        mock_get_provider.return_value.search.return_value = [_listing()]
        result = run("2BR near USF")

    assert len(result["results"]) == 1
    assert result["results"][0]["rating"] == "unknown"
    assert result["results"][0]["delta"] is None


def test_run_results_sorted_best_first() -> None:
    cheap = _listing(price=1000, title="cheap")   # far below FMR -> fair, low delta
    pricey = _listing(price=5000, title="pricey")  # far above FMR -> unfair
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", return_value=_fmr_benchmark(value=2300.0)),
    ):
        mock_get_provider.return_value.search.return_value = [pricey, cheap]
        result = run("2BR near USF")

    titles = [r["title"] for r in result["results"]]
    assert titles.index("cheap") < titles.index("pricey")


def test_default_radius_is_five_miles() -> None:
    assert DEFAULT_RADIUS_MILES == 5.0


def test_run_includes_web_references_alongside_verdicts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_refs = [{"title": "Apartments in SF - Zillow", "url": "https://www.zillow.com/san-francisco-ca/"}]
    monkeypatch.setattr("fairdeal.rentcheck.search_web", lambda query, max_results=5: fake_refs)
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", return_value=_fmr_benchmark()),
    ):
        mock_get_provider.return_value.search.return_value = [_listing()]
        result = run("2BR near USF")

    assert result["web_references"] == fake_refs


def test_run_web_search_failure_degrades_to_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from fairdeal.websearch import WebSearchError

    def _boom(query, max_results=5):
        raise WebSearchError("network down")

    monkeypatch.setattr("fairdeal.rentcheck.search_web", _boom)
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", return_value=_fmr_benchmark()),
    ):
        mock_get_provider.return_value.search.return_value = [_listing()]
        result = run("2BR near USF")  # must not raise

    assert result["web_references"] == []


def test_run_no_anchors_still_includes_web_references(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_refs = [{"title": "x", "url": "https://example.com"}]
    monkeypatch.setattr("fairdeal.rentcheck.search_web", lambda query, max_results=5: fake_refs)
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", side_effect=GeocodeError("no match")),
    ):
        result = run("somewhere unresolvable")

    assert result["web_references"] == fake_refs


def test_run_studio_bedrooms_zero_is_not_coerced_to_one() -> None:
    # bedrooms=0 (studio) is falsy in Python — a `bedrooms or 1` bug would
    # silently look up 1BR pricing instead. Assert fmr_for sees 0, not 1.
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria(bedrooms=0)),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", return_value=_fmr_benchmark()) as mock_fmr,
    ):
        mock_get_provider.return_value.search.return_value = [_listing(bedrooms=0, home_type="studio")]
        run("studio near USF")

    assert mock_fmr.call_args.args[2] == 0


def test_run_benchmarks_listing_bedrooms_not_query_bedrooms() -> None:
    # The user asked for 2BR; the provider returned a studio. It must be judged
    # against studio FMR, not 2BR FMR.
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria(bedrooms=2)),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", return_value=_fmr_benchmark()) as mock_fmr,
    ):
        mock_get_provider.return_value.search.return_value = [_listing(bedrooms=0, home_type="studio")]
        run("2BR near USF")

    assert mock_fmr.call_args.args[2] == 0


def test_run_geocode_failure_inside_hud_yields_unknown_rating() -> None:
    # hud.fmr_for reverse-geocodes internally; that GeocodeError used to escape
    # rentcheck entirely and become an HTTP 500.
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", side_effect=GeocodeError("nominatim down")),
    ):
        mock_get_provider.return_value.search.return_value = [_listing()]
        result = run("2BR near USF")

    assert len(result["results"]) == 1
    assert result["results"][0]["rating"] == "unknown"
    assert result["results"][0]["delta"] is None


def test_run_reports_data_source_and_singular_reply_text() -> None:
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", return_value=_fmr_benchmark()),
    ):
        mock_get_provider.return_value.PROVIDER_NAME = "seed-demo"
        mock_get_provider.return_value.search.return_value = [_listing(price=2000)]
        result = run("2BR near USF")

    assert result["data_source"] == "seed-demo"
    assert result["reply_text"] == "Found 1 place near your criteria, 1 looks fairly priced."


def test_cpi_drift_is_fetched_once_per_batch() -> None:
    from fairdeal.rentcheck import _cpi_drift_cached

    _cpi_drift_cached.cache_clear()
    with (
        patch("fairdeal.rentcheck.parse_criteria", return_value=_criteria()),
        patch("fairdeal.rentcheck.geocode", return_value=_usf_point()),
        patch("fairdeal.rentcheck.get_provider") as mock_get_provider,
        patch("fairdeal.rentcheck.hud.fmr_for", side_effect=lambda *a: _fmr_benchmark(year="2024")),
        patch("fairdeal.rentcheck.bls.cpi_drift", return_value=1.1) as mock_drift,
    ):
        mock_get_provider.return_value.search.return_value = [
            _listing(price=2000, title="a"),
            _listing(price=2100, title="b"),
            _listing(price=2200, title="c"),
        ]
        result = run("2BR near USF")

    assert len(result["results"]) == 3
    assert mock_drift.call_count == 1
    _cpi_drift_cached.cache_clear()
