from __future__ import annotations

import html
import re

import requests

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"

# Verified live 2026-08-16: DuckDuckGo's HTML endpoint requires POST (a GET
# just returns the empty search-box shell, no results) and needs a
# browser-like User-Agent. Confirmed it surfaces real Zillow/Apartments.com/
# Rent.com category-search pages for a query like "apartments for rent near
# Miami Beach FL" — real reference links, but NOT individual priced listings
# (Craigslist/Zillow/Apartments.com block direct scraping of those, see
# fairdeal/craigslist.py), so these are shown as unverified "explore more"
# links, never run through the fairness-verdict engine.
_RESULT_RE = re.compile(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


class WebSearchError(Exception):
    pass


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Real web search results for `query`: [{"title": str, "url": str}, ...].

    Filters out DuckDuckGo's ad redirects (always routed through
    duckduckgo.com/y.js) — those aren't organic results and would send the
    user through an ad-tracking URL. Raises WebSearchError on request
    failure; callers should treat this as a soft, best-effort feature and
    degrade to an empty list rather than fail the whole response.
    """
    try:
        resp = requests.post(
            DDG_HTML_URL,
            data={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise WebSearchError(f"web search failed for {query!r}: {exc}") from exc

    results = []
    for href, raw_title in _RESULT_RE.findall(resp.text):
        if "duckduckgo.com" in href:
            continue  # ad redirect, not an organic result
        title = html.unescape(_TAG_RE.sub("", raw_title)).strip()
        if not title:
            continue
        results.append({"title": title, "url": href})
        if len(results) >= max_results:
            break
    return results
