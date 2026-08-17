"""Seed/demo listing provider.

On 2026-08-16 we live-tested Craigslist (RSS via ?format=rss and the plain
HTML search page), Zillow, and Apartments.com with direct fetches. All of
them returned HTTP 403 (Cloudflare/bot-detection). This is not a bug in
our code and there is currently no zero-key path to real individual rental
listings, so the default provider ships this clearly-labeled SEED dataset
grounded in realistic Bay Area numbers instead of hammering a blocked
site.

To swap in a real provider later (e.g. a paid listings API like RentCast):
implement the SearchProvider protocol in fairdeal.search, register the
instance in _PROVIDERS there, and set FAIRDEAL_SEARCH_PROVIDER to its key.
"""

from __future__ import annotations

from fairdeal.search import Listing, SearchCriteria

# Placeholder URLs (example.com) — these are demo rows, not live listings.
_SEED_LISTINGS: list[Listing] = [
    Listing(
        title="Sunny 1BR in the Inner Sunset",
        price=2400,
        url="https://example.com/seed-listing/1",
        lat=37.7601,
        lon=-122.4750,
        posted="2026-08-10",
        raw_location="Inner Sunset, San Francisco, CA",
        bedrooms=1,
        home_type="apartment",
    ),
    Listing(
        title="Cozy studio near Clement St",
        price=1850,
        url="https://example.com/seed-listing/2",
        lat=37.7826,
        lon=-122.4640,
        posted="2026-08-12",
        raw_location="Inner Richmond, San Francisco, CA",
        bedrooms=0,
        home_type="studio",
    ),
    Listing(
        title="Bright 2BR near Dolores Park",
        price=3400,
        url="https://example.com/seed-listing/3",
        lat=37.7596,
        lon=-122.4269,
        posted="2026-08-08",
        raw_location="Mission Dolores, San Francisco, CA",
        bedrooms=2,
        home_type="apartment",
    ),
    Listing(
        title="Spacious 1BR in Adams Point",
        price=2250,
        url="https://example.com/seed-listing/4",
        lat=37.8103,
        lon=-122.2580,
        posted="2026-08-11",
        raw_location="Adams Point, Oakland, CA",
        bedrooms=1,
        home_type="apartment",
    ),
    Listing(
        title="Quiet 2BR near Lake Merritt",
        price=2950,
        url="https://example.com/seed-listing/5",
        lat=37.8044,
        lon=-122.2494,
        posted="2026-08-13",
        raw_location="Lakeside, Oakland, CA",
        bedrooms=2,
        home_type="apartment",
    ),
    Listing(
        title="Student-friendly 1BR near UC Berkeley",
        price=2100,
        url="https://example.com/seed-listing/6",
        lat=37.8697,
        lon=-122.2680,
        posted="2026-08-14",
        raw_location="Southside, Berkeley, CA",
        bedrooms=1,
        home_type="apartment",
    ),
    Listing(
        title="Renovated 2BR in Daly City",
        price=2800,
        url="https://example.com/seed-listing/7",
        lat=37.6879,
        lon=-122.4702,
        posted="2026-08-09",
        raw_location="Westlake, Daly City, CA",
        bedrooms=2,
        home_type="apartment",
    ),
    Listing(
        title="Sunny 1BR in the Outer Richmond",
        price=2350,
        url="https://example.com/seed-listing/8",
        lat=37.7800,
        lon=-122.4870,
        posted="2026-08-15",
        raw_location="Outer Richmond, San Francisco, CA",
        bedrooms=1,
        home_type="apartment",
    ),
]


class SeedProvider:
    """Returns budget/bedroom/home-type-filtered rows from the hardcoded seed set."""

    PROVIDER_NAME = "seed-demo"  # surfaced as the API's "data_source" field

    def search(self, criteria: SearchCriteria) -> list[Listing]:
        cap = criteria.budget_monthly * 1.10
        results: list[Listing] = []
        for listing in _SEED_LISTINGS:
            if listing.price > cap:
                continue
            if criteria.bedrooms is not None and listing.bedrooms != criteria.bedrooms:
                continue
            if (
                criteria.home_type is not None
                and criteria.home_type.lower() not in listing.home_type.lower()
            ):
                continue
            results.append(listing)
        return results
