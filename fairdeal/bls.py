from __future__ import annotations

import requests

BLS_TIMESERIES_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Regional CPI-U (All Urban Consumers) series for a handful of large metros,
# used to adjust a benchmark published in a prior period up to "now". BLS's
# public v2 API works without a key at low request volume (verified live
# 2026-08-16, see tests/fixtures/bls_cpi_sf.json).
METRO_CPI_SERIES = {
    "san francisco": "CUURS49BSA0",
    "oakland": "CUURS49BSA0",
    "los angeles": "CUURS49ASA0",
    "new york": "CUURS12ASA0",
    "chicago": "CUURS23ASA0",
}


class BLSError(Exception):
    pass


def cpi_series_for(city_or_region: str) -> str | None:
    """Best-effort match of a city/region name to a BLS regional CPI series id."""
    needle = city_or_region.lower()
    for key, series_id in METRO_CPI_SERIES.items():
        if key in needle:
            return series_id
    return None


def cpi_drift(series_id: str, start_year: str, end_year: str) -> float:
    """Ratio of the most recent CPI value to the earliest value in range.

    Multiply a benchmark published in `start_year` by this to approximate
    today's dollars. Raises BLSError if the API call fails or returns no data.
    """
    try:
        resp = requests.post(
            BLS_TIMESERIES_URL,
            json={"seriesid": [series_id], "startyear": start_year, "endyear": end_year},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise BLSError(f"BLS request failed for series {series_id!r}: {exc}") from exc

    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise BLSError(f"BLS request unsuccessful: {payload.get('message')}")

    series = payload.get("Results", {}).get("series", [])
    if not series or not series[0].get("data"):
        raise BLSError(f"no CPI data returned for series {series_id!r}")

    # BLS returns newest-first.
    points = series[0]["data"]
    latest = float(points[0]["value"])
    earliest = float(points[-1]["value"])
    if earliest == 0:
        raise BLSError("earliest CPI value is zero, cannot compute drift")
    return latest / earliest
