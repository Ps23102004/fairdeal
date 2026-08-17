from __future__ import annotations

from fairdeal.craigslist import SeedProvider
from fairdeal.search import SearchCriteria


def _criteria(budget: int = 2400, bedrooms: int | None = None, home_type: str | None = None) -> SearchCriteria:
    # bedrooms/home_type default to None = "not specified", which filters nothing.
    return SearchCriteria(
        anchors=["San Francisco", "Oakland"],
        budget_monthly=budget,
        bedrooms=bedrooms,
        home_type=home_type,
    )


def test_search_includes_listings_within_budget() -> None:
    results = SeedProvider().search(_criteria(budget=2400))
    prices = {listing.price for listing in results}
    assert 1850 in prices  # studio near Clement St, comfortably under budget
    assert 2400 in prices  # exactly at budget


def test_search_excludes_listings_above_budget_plus_10pct() -> None:
    results = SeedProvider().search(_criteria(budget=2400))
    cap = 2400 * 1.10  # 2640
    assert all(listing.price <= cap for listing in results)
    prices = {listing.price for listing in results}
    assert 3400 not in prices  # 2BR near Dolores Park, well over cap
    assert 2950 not in prices  # 2BR near Lake Merritt
    assert 2800 not in prices  # 2BR in Daly City


def test_search_boundary_listing_at_cap_is_included() -> None:
    # Budget 2682 -> cap 2950.2; the $2950 Lake Merritt listing makes the cut.
    results = SeedProvider().search(_criteria(budget=2682))
    assert any(listing.price == 2950 for listing in results)


def test_search_very_low_budget_excludes_everything() -> None:
    results = SeedProvider().search(_criteria(budget=1000))
    assert results == []


def test_search_unspecified_bedrooms_and_home_type_filter_nothing() -> None:
    # bedrooms=None/home_type=None must stay "no filter", not "match nothing".
    unfiltered = SeedProvider().search(_criteria(budget=5000))
    assert {listing.bedrooms for listing in unfiltered} == {0, 1, 2}
    assert {listing.home_type for listing in unfiltered} == {"studio", "apartment"}


def test_search_filters_on_bedrooms() -> None:
    results = SeedProvider().search(_criteria(budget=5000, bedrooms=1))
    assert results, "expected 1BR seed listings"
    assert all(listing.bedrooms == 1 for listing in results)
    prices = {listing.price for listing in results}
    assert 1850 not in prices  # the studio is within budget but wrong bedroom count
    assert 3400 not in prices  # 2BR, same


def test_search_filters_on_home_type() -> None:
    results = SeedProvider().search(_criteria(budget=5000, home_type="studio"))
    assert [listing.price for listing in results] == [1850]  # only the studio survives
    # ...and the $2400 1BR apartment is in budget, excluded on home_type alone.


def test_search_returns_listing_objects_with_expected_shape() -> None:
    results = SeedProvider().search(_criteria(budget=2400))
    assert results, "expected at least one seed listing under a $2400 budget"
    first = results[0]
    assert first.title
    assert first.url.startswith("https://")
    assert first.lat is not None and first.lon is not None
    assert first.raw_location
    assert isinstance(first.bedrooms, int)
    assert first.home_type


def test_provider_identifies_itself_as_seed_demo() -> None:
    assert SeedProvider.PROVIDER_NAME == "seed-demo"
