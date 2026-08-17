from __future__ import annotations

from dataclasses import dataclass

import requests

# College Scorecard (api.data.gov) — built directly from IPEDS. Verified live
# 2026-08-16 with the public DEMO_KEY (see tests/fixtures/scorecard_usf.json).
# IMPORTANT: the API's `fields=` narrow-selection parameter returns null for
# every nested "consumer.*" field (cost.avg_net_price.consumer.overall_median,
# earnings.10_yrs_after_entry.consumer.overall_median, etc.) even though the
# SAME fields resolve correctly in the full, unfiltered response — a real,
# confirmed API quirk, not a guess. So this client always fetches the full
# response and parses client-side; do not "optimize" this to a fields= query
# without re-verifying, or every school will silently return None.
SCORECARD_URL = "https://api.data.gov/ed/collegescorecard/v1/schools"
DEMO_API_KEY = "DEMO_KEY"  # rate-limited; register a free key at api.data.gov/signup for production use


class ScorecardError(Exception):
    pass


@dataclass
class SchoolProfile:
    name: str
    city: str
    state: str
    net_price_annual: float | None  # consumer.overall_median — what students actually pay, not sticker price
    earnings_10yr_median: float | None  # consumer.overall_median, 10 years after entry
    completion_rate_4yr: float | None  # 0-1, 150% of normal time


def _api_key() -> str:
    import os

    return os.environ.get("SCORECARD_API_KEY") or DEMO_API_KEY


def find_school(name: str) -> SchoolProfile:
    """Look up a school by name. Raises ScorecardError if no match or the
    request fails.

    Scorecard's relevance ranking does NOT put an exact name match first —
    confirmed live: searching "University of San Francisco" ranks
    "University of California-San Francisco" (a different, grad-only school)
    above the exact match. So this prefers a case-insensitive exact match
    over the API's own result order, falling back to the top-ranked result
    only when nothing matches exactly.
    """
    try:
        resp = requests.get(
            SCORECARD_URL,
            params={"school.name": name, "api_key": _api_key()},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise ScorecardError(f"College Scorecard request failed for {name!r}: {exc}") from exc

    results = payload.get("results", [])
    if not results:
        raise ScorecardError(f"no school found matching {name!r}")

    needle = name.strip().lower()
    top = next((r for r in results if r["school"]["name"].strip().lower() == needle), results[0])
    latest = top.get("latest", {})
    net_price = latest.get("cost", {}).get("avg_net_price", {}).get("consumer", {}).get("overall_median")
    earnings = latest.get("earnings", {}).get("10_yrs_after_entry", {}).get("consumer", {}).get("overall_median")
    completion = latest.get("completion", {}).get("completion_rate_4yr_150nt")

    return SchoolProfile(
        name=top["school"]["name"],
        city=top["school"]["city"],
        state=top["school"]["state"],
        net_price_annual=float(net_price) if net_price is not None else None,
        earnings_10yr_median=float(earnings) if earnings is not None else None,
        completion_rate_4yr=float(completion) if completion is not None else None,
    )
