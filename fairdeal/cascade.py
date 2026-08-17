"""Natural-language rental request -> SearchCriteria, via the llm-ladder cascade.

The cheap local tiers in chains.yaml handle most requests; the cascade only
escalates when the small models disagree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from llm_ladder.config import load_chains
from llm_ladder.engine import run_cascade
from llm_ladder.ollama_client import OllamaConnectionError, OllamaModelNotFoundError

from fairdeal.search import SearchCriteria

CHAINS_PATH = Path(__file__).parent.parent / "chains.yaml"
CHAIN_NAME = "extract_json"

_PROMPT = """You extract structured search criteria from a renter's request.
Respond with STRICT JSON ONLY — no prose, no markdown fences, no explanation.

Schema (exactly these four keys):
{{"anchors": ["..."], "budget_monthly": <int>, "bedrooms": <int or null>, "home_type": "<string or null>"}}

anchors: place names mentioned — universities, neighborhoods, landmarks, cities.
  Expand well-known abbreviations to their full name.
budget_monthly: the dollar figure mentioned, digits only (no $ or commas).
bedrooms: number of bedrooms, or null if unstated.
home_type: e.g. "apartment", "house", "studio", or null if unstated.

Example input: 2BR near USF, budget $2500/month, close to the beach
Example output: {{"anchors": ["University of San Francisco", "beach"], "budget_monthly": 2500, "bedrooms": 2, "home_type": null}}

Example input: looking for a house in Oakland under $3,200
Example output: {{"anchors": ["Oakland"], "budget_monthly": 3200, "bedrooms": null, "home_type": "house"}}

Input: {message}
Output:"""


class CascadeParseError(Exception):
    pass


def _loads(text: str) -> dict:
    """Parse JSON from a model response, with one repair pass for stray prose."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise CascadeParseError(f"model response contained no JSON object: {text!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise CascadeParseError(f"model response was not valid JSON: {text!r}") from exc


def _validate(data: dict) -> SearchCriteria:
    """Coerce a parsed model response to SearchCriteria, or raise CascadeParseError."""
    if not isinstance(data, dict):
        raise CascadeParseError(f"expected a JSON object, got {type(data).__name__}")

    anchors = data.get("anchors")
    if not isinstance(anchors, list) or not all(isinstance(a, str) for a in anchors):
        raise CascadeParseError(f"'anchors' must be a list of strings, got {anchors!r}")

    budget = data.get("budget_monthly")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)):
        raise CascadeParseError(f"'budget_monthly' must be a number, got {budget!r}")

    bedrooms = data.get("bedrooms")
    if bedrooms is not None and (isinstance(bedrooms, bool) or not isinstance(bedrooms, int)):
        raise CascadeParseError(f"'bedrooms' must be an integer or null, got {bedrooms!r}")

    home_type = data.get("home_type")
    if home_type is not None and not isinstance(home_type, str):
        raise CascadeParseError(f"'home_type' must be a string or null, got {home_type!r}")

    return SearchCriteria(
        anchors=anchors,
        budget_monthly=int(budget),
        bedrooms=bedrooms,
        home_type=home_type,
    )


def parse_criteria(message: str) -> SearchCriteria:
    """Turn a free-text rental request into SearchCriteria using the local model cascade.

    Raises CascadeParseError if no local model is reachable or the response
    can't be parsed into the expected shape.
    """
    chain_config = load_chains(str(CHAINS_PATH))[CHAIN_NAME]
    try:
        result = run_cascade(_PROMPT.format(message=message), CHAIN_NAME, chain_config, ledger=None)
    except (OllamaConnectionError, OllamaModelNotFoundError) as exc:
        raise CascadeParseError(
            f"local model inference is unavailable (is Ollama running with the "
            f"{CHAIN_NAME} chain's models pulled?): {exc}"
        ) from exc

    return _validate(_loads(result.answer))
