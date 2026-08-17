from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

import requests

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "fairdeal/0.1 (portfolio project; contact: parthsingh)"

# ponytail: module-global sleep throttle. Nominatim's usage policy caps
# unauthenticated clients at 1 req/sec. Guarded by _throttle_lock because
# ThreadingHTTPServer means concurrent requesters are real, not hypothetical
# — two unlocked threads could read the same _last_request_at and both
# proceed, exceeding the rate limit.
_MIN_INTERVAL_S = 1.0
_last_request_at = 0.0
_throttle_lock = threading.Lock()


@dataclass
class GeoPoint:
    lat: float
    lon: float
    display_name: str


class GeocodeError(Exception):
    pass


def _throttle() -> None:
    global _last_request_at
    with _throttle_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < _MIN_INTERVAL_S:
            time.sleep(_MIN_INTERVAL_S - elapsed)
        _last_request_at = time.monotonic()


def geocode(query: str) -> GeoPoint:
    """Resolve a free-text place name to coordinates via Nominatim.

    Raises GeocodeError if the query can't be resolved or the request fails.
    """
    _throttle()
    try:
        resp = requests.get(
            NOMINATIM_SEARCH_URL,
            params={"q": query, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        raise GeocodeError(f"geocoding request failed for {query!r}: {exc}") from exc

    if not results:
        raise GeocodeError(f"no geocoding match for {query!r}")

    top = results[0]
    return GeoPoint(lat=float(top["lat"]), lon=float(top["lon"]), display_name=top.get("display_name", query))


def reverse_geocode(lat: float, lon: float) -> dict:
    """Resolve coordinates to an address-component dict (city, county, state, ...).

    Raises GeocodeError on request failure. Missing components (e.g. "county"
    for a consolidated city-county like San Francisco) are simply absent from
    the returned dict — callers should fall back to "city" when "county" is missing.

    Rounded to 2 decimal places (~1.1km) before hitting the cache: callers only
    need city/county/state granularity, and a rank of nearby listings would
    otherwise burn a separate throttled request (and a slice of Nominatim's
    daily goodwill) per listing for an identical answer.
    """
    return _reverse_geocode_cached(round(lat, 2), round(lon, 2))


@lru_cache(maxsize=256)
def _reverse_geocode_cached(lat: float, lon: float) -> dict:
    _throttle()
    try:
        resp = requests.get(
            NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2"},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
    except requests.RequestException as exc:
        raise GeocodeError(f"reverse geocoding request failed for ({lat}, {lon}): {exc}") from exc

    if "error" in result:
        raise GeocodeError(f"no reverse geocoding match for ({lat}, {lon})")

    return result.get("address", {})


def haversine(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points, in miles."""
    earth_radius_mi = 3958.8
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth_radius_mi * math.asin(math.sqrt(h))
