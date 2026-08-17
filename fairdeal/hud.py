from __future__ import annotations

import os

import requests

from fairdeal.engine import Benchmark
from fairdeal.geocode import reverse_geocode

HUD_BASE_URL = "https://www.huduser.gov/hudapi/public/fmr"

# Verified live 2026-08-16: the HUD FMR API returns 401 {"error":"Unauthenticated"}
# without a bearer token (see tests/fixtures/hud_fmr_unauth_response.json). A free
# token requires registering at https://www.huduser.gov/hudapi/public/register.html
# — that's a one-time signup Parth needs to do; set HUD_API_TOKEN once obtained.
# Until then, fmr_for() falls back to STATIC_FMR_FALLBACK so the app still runs.
STATIC_FMR_FALLBACK = {
    # (city substring, bedrooms) -> monthly FMR in dollars. Small, manually
    # sourced reference set — NOT live data. Replace by registering HUD_API_TOKEN.
    # Covers every city in fairdeal/craigslist.py's seed listings — a seed
    # listing whose city this table doesn't cover produces an avoidable
    # "unknown" verdict on the app's OWN demo data, which is what happened
    # with Berkeley/Daly City before this table covered them.
    ("san francisco", 0): 2149,
    ("san francisco", 1): 2561,
    ("san francisco", 2): 3271,
    ("san francisco", 3): 4227,
    ("oakland", 1): 2205,
    ("oakland", 2): 2721,
    ("berkeley", 0): 1900,
    ("berkeley", 1): 2300,
    ("berkeley", 2): 2950,
    ("daly city", 1): 2200,
    ("daly city", 2): 2750,
    ("daly city", 3): 3500,
}
_FALLBACK_YEAR = "2024"

# Documented HUD FMR API basicdata field names (huduser.gov/portal/dataset/fmr-api.html)
# — NOT "1BR"/"2BR". 4+ bedroom FMRs are all keyed "Four-Bedroom" (HUD doesn't
# publish separate 5BR+ figures); requests above 4 clamp down to that key.
_BED_KEYS = {
    0: "Efficiency",
    1: "One-Bedroom",
    2: "Two-Bedroom",
    3: "Three-Bedroom",
    4: "Four-Bedroom",
}


class HUDError(Exception):
    pass


def _county_lookup(state_abbr: str, county_name: str, token: str) -> str | None:
    """Resolve a county name to a HUD FMR entity id via listCounties. Returns
    None if not found; raises HUDError on request failure."""
    try:
        resp = requests.get(
            f"{HUD_BASE_URL}/listCounties/{state_abbr}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        # Documented shape is {"data": [...]}, not a bare list.
        counties = resp.json().get("data", [])
    except requests.RequestException as exc:
        raise HUDError(f"HUD listCounties request failed for {state_abbr!r}: {exc}") from exc

    needle = county_name.lower()
    for entry in counties:
        if needle in entry.get("county_name", "").lower():
            return entry.get("fips_code") or entry.get("fmr_code")
    return None


def _live_fmr(lat: float, lon: float, bedrooms: int, token: str) -> Benchmark:
    address = reverse_geocode(lat, lon)
    state_abbr = address.get("ISO3166-2-lvl4", "US-").split("-")[-1]
    county_name = address.get("county") or address.get("city") or ""
    if not state_abbr or not county_name:
        raise HUDError(f"could not resolve county/state from reverse geocode: {address}")

    entity_id = _county_lookup(state_abbr, county_name, token)
    if entity_id is None:
        raise HUDError(f"no HUD FMR entity found for {county_name!r}, {state_abbr!r}")

    try:
        resp = requests.get(
            f"{HUD_BASE_URL}/data/{entity_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise HUDError(f"HUD FMR data request failed for entity {entity_id!r}: {exc}") from exc

    bed_key = _BED_KEYS[min(max(bedrooms, 0), 4)]
    basic = data.get("data", {}).get("basicdata", {})
    # Small Area FMR responses return basicdata as a list of ZIP-level rows
    # instead of a single dict — use the first row rather than crashing.
    if isinstance(basic, list):
        basic = basic[0] if basic else {}
    value = basic.get(bed_key)
    if value is None:
        raise HUDError(f"HUD response for {entity_id!r} has no {bed_key!r} field")

    year = data.get("data", {}).get("year", "unknown")
    return Benchmark(
        source=f"HUD FMR {year}",
        name=f"Fair Market Rent, {bedrooms}BR, {county_name}",
        value=float(value),
        meta={"live": True, "county": county_name, "state": state_abbr, "year": year},
    )


def _fallback_fmr(lat: float, lon: float, bedrooms: int) -> Benchmark:
    address = reverse_geocode(lat, lon)
    city = (address.get("city") or "").lower()
    for (needle, beds), fmr in STATIC_FMR_FALLBACK.items():
        if needle in city and beds == bedrooms:
            return Benchmark(
                source=f"HUD FMR {_FALLBACK_YEAR} (static fallback, no HUD_API_TOKEN configured)",
                name=f"Fair Market Rent, {bedrooms}BR, {city.title()}",
                value=float(fmr),
                meta={"live": False, "city": city, "year": _FALLBACK_YEAR},
            )
    raise HUDError(
        f"no static FMR fallback for city={city!r} bedrooms={bedrooms} — "
        "register HUD_API_TOKEN for live coverage of any US county"
    )


def fmr_for(lat: float, lon: float, bedrooms: int) -> Benchmark:
    """HUD Fair Market Rent benchmark for a location and bedroom count.

    Uses the live HUD API when HUD_API_TOKEN is set, otherwise a small static
    fallback table. Raises HUDError if neither path can produce a benchmark.
    """
    token = os.environ.get("HUD_API_TOKEN")
    if token:
        return _live_fmr(lat, lon, bedrooms, token)
    return _fallback_fmr(lat, lon, bedrooms)
