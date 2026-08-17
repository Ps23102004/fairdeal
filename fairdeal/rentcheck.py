"""Vertical slice: a chat message in, ranked fairness verdicts out.

Wires the cascade (message -> criteria), geocoding (anchors -> points), the
search provider (criteria -> listings), HUD/BLS (listing -> benchmark) and the
engine (claim + benchmark -> verdict) into the one dict server.py serialises.
"""

from __future__ import annotations

import datetime
from functools import lru_cache
from math import inf

from fairdeal import bls, hud
from fairdeal.cascade import parse_criteria
from fairdeal.engine import DEFAULT_RULES, Claim, evaluate
from fairdeal.geocode import GeocodeError, GeoPoint, geocode, haversine
from fairdeal.search import Listing, SearchCriteria, get_provider
from fairdeal.websearch import WebSearchError, search_web

DEFAULT_RADIUS_MILES = 5.0
_RATING_ORDER = {"fair": 0, "borderline": 1, "unfair": 2, "unknown": 3}


@lru_cache(maxsize=128)
def _cpi_drift_cached(series_id: str, start_year: str, end_year: str) -> float:
    """Process-local cache over bls.cpi_drift.

    The unauthenticated BLS API allows 25 requests/day, and every listing in
    one run() for the same city asks the identical question — without this,
    one batch can exhaust the quota and end up with some listings CPI-adjusted
    and some not. bls.cpi_drift itself stays uncached (general-purpose client).
    """
    return bls.cpi_drift(series_id, start_year=start_year, end_year=end_year)


def _nearest_anchor_miles(listing: Listing, anchors: list[GeoPoint]) -> float | None:
    """Miles from a listing to its closest anchor, or None if it has no coordinates."""
    if listing.lat is None or listing.lon is None:
        return None
    here = GeoPoint(lat=listing.lat, lon=listing.lon, display_name=listing.raw_location)
    return min(haversine(here, anchor) for anchor in anchors)


def _benchmarked_verdict(listing: Listing):
    """Fairness verdict for one listing as (rating, delta, explanation).

    Benchmarked against the LISTING's own bedroom count, not the query's — a
    studio judged against 2BR FMR because the user asked for 2BR is nonsense.

    Degrades to rating="unknown" rather than raising: a single failed HUD or
    geocode lookup must not drop the listing or kill the batch.
    """
    current_year = str(datetime.date.today().year)
    try:
        # hud.fmr_for reverse-geocodes internally, so GeocodeError is on this path too.
        benchmark = hud.fmr_for(listing.lat, listing.lon, listing.bedrooms)
    except (hud.HUDError, GeocodeError) as exc:
        return "unknown", None, f"No fairness benchmark: HUD FMR lookup failed ({exc})."

    # Adjust whenever the benchmark's published year is behind the current
    # year — this is the static fallback's main use case (hardcoded to a
    # fixed year, so it goes stale every year), but applies equally to live
    # HUD data if its FY lags. Gating on "live" would skip exactly the
    # fallback case that most needs adjusting, so gate on staleness instead.
    if str(benchmark.meta.get("year")) != current_year:
        series_id = bls.cpi_series_for(listing.raw_location)
        if series_id:
            try:
                benchmark.value *= _cpi_drift_cached(
                    series_id,
                    str(benchmark.meta.get("year")),
                    current_year,
                )
            except bls.BLSError:
                pass  # Nice-to-have; the unadjusted FMR is still a usable benchmark.

    claim = Claim(kind="monthly_rent", value=listing.price, context={"bedrooms": listing.bedrooms})
    verdict = evaluate(claim, [benchmark], DEFAULT_RULES)
    return verdict.rating, verdict.delta, verdict.explanation


def _web_references(criteria: SearchCriteria) -> list[dict]:
    """Real (unverified) web search links for the user's criteria — a
    best-effort supplement, never fed into the fairness-verdict engine
    (see fairdeal/websearch.py for why: these are category-search pages,
    not individually priced listings). Degrades to an empty list on any
    search failure rather than affecting the rest of the response."""
    if not criteria.anchors:
        return []
    home_type = criteria.home_type or "apartments"
    query = f"{home_type} for rent near {', '.join(criteria.anchors)}"
    try:
        return search_web(query, max_results=5)
    except WebSearchError:
        return []


def _rank_key(result: dict) -> tuple[int, float]:
    """Best-first: fair before borderline before unfair before unknown, then by
    fairness delta (price / benchmark) ascending — best value first, NOT cheapest
    first. $3000 at 0.9x its benchmark beats $1500 at 1.5x a lower benchmark."""
    return (_RATING_ORDER.get(result["rating"], 3), result["delta"] if result["delta"] is not None else inf)


def run(message: str, model: str | None = None) -> dict:
    """Answer a rental request with ranked, benchmarked listings.

    `model` overrides the configured cascade with a single Ollama model tag
    (see fairdeal.cascade.parse_criteria) — passed through from the UI's
    model selector; omit to use chains.yaml as normal.

    Raises CascadeParseError if the message can't be understood; every other
    failure degrades to fewer results rather than an exception.
    """
    criteria = parse_criteria(message, model=model)
    provider = get_provider()
    # In-band honesty: the default provider serves a seed/demo dataset, which
    # was previously only visible in the README.
    data_source = provider.PROVIDER_NAME

    anchors = []
    for anchor in criteria.anchors:
        try:
            anchors.append(geocode(anchor))
        except GeocodeError:
            continue
    if not anchors:
        return {
            "reply_text": (
                "I couldn't locate any of the places you mentioned "
                f"({', '.join(criteria.anchors) or 'none given'}), so I have nothing to compare. "
                "Try naming a city or neighborhood."
            ),
            "results": [],
            "data_source": data_source,
            "web_references": _web_references(criteria),
        }

    results = []
    for listing in provider.search(criteria):
        miles = _nearest_anchor_miles(listing, anchors)
        if miles is None or miles > DEFAULT_RADIUS_MILES:
            continue
        rating, delta, explanation = _benchmarked_verdict(listing)
        results.append(
            {
                "title": listing.title,
                "price": listing.price,
                "url": listing.url,
                "distance_miles": round(miles, 2),
                "rating": rating,
                "delta": delta,
                "explanation": explanation,
            }
        )

    results.sort(key=_rank_key)
    fair = sum(1 for r in results if r["rating"] == "fair")
    budget_clause = f" under ${criteria.budget_monthly:,}/month" if criteria.budget_monthly is not None else ""
    reply_text = (
        f"Found {len(results)} place{'' if len(results) == 1 else 's'} near your criteria, "
        f"{fair} look{'s' if fair == 1 else ''} fairly priced."
        if results
        else f"Found nothing within {DEFAULT_RADIUS_MILES:g} miles of those places{budget_clause}."
    )
    return {
        "reply_text": reply_text,
        "results": results,
        "data_source": data_source,
        "web_references": _web_references(criteria),
    }


if __name__ == "__main__":
    rows = [
        {"rating": "unfair", "delta": 1.3},
        {"rating": "fair", "delta": 0.9},
        {"rating": "unknown", "delta": None},
        {"rating": "fair", "delta": None},
        {"rating": "fair", "delta": 0.7},
        {"rating": "borderline", "delta": 1.1},
    ]
    rows.sort(key=_rank_key)
    assert [(r["rating"], r["delta"]) for r in rows] == [
        ("fair", 0.7),
        ("fair", 0.9),
        ("fair", None),
        ("borderline", 1.1),
        ("unfair", 1.3),
        ("unknown", None),
    ], rows
    print("rank order ok")
