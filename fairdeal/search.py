from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Listing:
    title: str
    price: int  # monthly rent, USD
    url: str
    lat: float | None
    lon: float | None
    posted: str  # ISO-ish date string
    raw_location: str
    bedrooms: int  # 0 = studio
    home_type: str  # e.g. "apartment", "house", "studio"


@dataclass
class SearchCriteria:
    anchors: list[str]  # neighborhoods/cities/universities the user cares about
    budget_monthly: int  # USD
    bedrooms: int | None
    home_type: str | None


class SearchProvider(Protocol):
    PROVIDER_NAME: str  # reported to clients as the response's "data_source"

    def search(self, criteria: SearchCriteria) -> list[Listing]:
        ...


# Imported after Listing/SearchCriteria are defined — fairdeal.craigslist
# imports them back from this module, so importing it any earlier here
# would be a circular import.
from fairdeal.craigslist import SeedProvider  # noqa: E402

_PROVIDERS: dict[str, SearchProvider] = {
    "seed": SeedProvider(),
}


def get_provider(name: str | None = None) -> SearchProvider:
    """Return the search provider registered under `name` (or the
    FAIRDEAL_SEARCH_PROVIDER env var, defaulting to "seed").

    Raises ValueError for an unknown name.
    """
    resolved = name or os.environ.get("FAIRDEAL_SEARCH_PROVIDER", "seed")
    provider = _PROVIDERS.get(resolved)
    if provider is None:
        valid = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Unknown search provider {resolved!r}. Valid names: {valid}")
    return provider
