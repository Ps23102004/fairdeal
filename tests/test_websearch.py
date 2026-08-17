from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fairdeal.websearch import WebSearchError, search_web

_SAMPLE_HTML = """
<a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=apartments.com&amp;u3=abc">See Studio, 1, 2, &amp; 3 Bedrooms</a>
<a class="result__a" href="https://www.zillow.com/miami-beach-fl/apartments/">Apartments For Rent in Miami Beach FL - 2178 Rentals - Zillow</a>
<a class="result__a" href="https://www.apartments.com/miami-beach-fl/">Apartments <b>for</b> Rent in Miami Beach FL</a>
<a class="result__a" href="https://www.trulia.com/for_rent/Miami_Beach,FL/">Apartments For Rent in Miami Beach, FL</a>
"""


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


def test_search_web_filters_ad_redirects_and_strips_tags() -> None:
    with patch("fairdeal.websearch.requests.post", return_value=_mock_response(_SAMPLE_HTML)):
        results = search_web("apartments for rent near Miami Beach FL")

    assert len(results) == 3
    assert all("duckduckgo.com" not in r["url"] for r in results)
    assert results[0] == {
        "title": "Apartments For Rent in Miami Beach FL - 2178 Rentals - Zillow",
        "url": "https://www.zillow.com/miami-beach-fl/apartments/",
    }
    # Nested <b> tags and HTML entities in the title are cleaned up.
    assert results[1]["title"] == "Apartments for Rent in Miami Beach FL"


def test_search_web_respects_max_results() -> None:
    with patch("fairdeal.websearch.requests.post", return_value=_mock_response(_SAMPLE_HTML)):
        results = search_web("anything", max_results=1)

    assert len(results) == 1


def test_search_web_no_results_returns_empty_list() -> None:
    with patch("fairdeal.websearch.requests.post", return_value=_mock_response("<html><body>no results</body></html>")):
        results = search_web("zzzz-nonsense-query")

    assert results == []


def test_search_web_request_failure_raises_websearcherror() -> None:
    import requests

    with patch("fairdeal.websearch.requests.post", side_effect=requests.RequestException("timeout")):
        with pytest.raises(WebSearchError, match="web search failed"):
            search_web("anything")
