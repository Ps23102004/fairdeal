from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fairdeal.cascade import CascadeParseError, parse_criteria
from fairdeal.search import SearchCriteria
from llm_ladder.engine import CascadeResult
from llm_ladder.ollama_client import OllamaConnectionError


def _cascade_result(answer: str) -> CascadeResult:
    return CascadeResult(answer=answer, confidence=1.0, tier_index=0, model="test-model")


def test_parse_criteria_happy_path() -> None:
    answer = '{"anchors": ["University of San Francisco", "beach"], "budget_monthly": 2500, "bedrooms": 2, "home_type": null}'
    with patch("fairdeal.cascade.run_cascade", return_value=_cascade_result(answer)):
        criteria = parse_criteria("2BR near USF, budget $2500/month, close to the beach")

    assert criteria == SearchCriteria(
        anchors=["University of San Francisco", "beach"],
        budget_monthly=2500,
        bedrooms=2,
        home_type=None,
    )


def test_parse_criteria_repairs_json_wrapped_in_prose() -> None:
    answer = 'Sure, here you go:\n{"anchors": ["Oakland"], "budget_monthly": 3200, "bedrooms": null, "home_type": "house"}\nHope that helps!'
    with patch("fairdeal.cascade.run_cascade", return_value=_cascade_result(answer)):
        criteria = parse_criteria("looking for a house in Oakland under $3,200")

    assert criteria.anchors == ["Oakland"]
    assert criteria.budget_monthly == 3200
    assert criteria.bedrooms is None
    assert criteria.home_type == "house"


def test_parse_criteria_unparseable_response_raises() -> None:
    with patch("fairdeal.cascade.run_cascade", return_value=_cascade_result("no json here at all")):
        with pytest.raises(CascadeParseError, match="no JSON object"):
            parse_criteria("anything")


def test_parse_criteria_wrong_shape_raises() -> None:
    answer = '{"anchors": "not a list", "budget_monthly": 2500, "bedrooms": null, "home_type": null}'
    with patch("fairdeal.cascade.run_cascade", return_value=_cascade_result(answer)):
        with pytest.raises(CascadeParseError, match="'anchors'"):
            parse_criteria("anything")


def test_parse_criteria_no_budget_stated_stays_none() -> None:
    # Regression: budget_monthly used to be non-nullable in the schema, which
    # forced the model to hallucinate a number when none was mentioned (e.g.
    # misreading "5 guys" as a $5,000 budget). It must stay None when the
    # model correctly reports no budget was stated.
    answer = '{"anchors": ["Miami", "beach"], "budget_monthly": null, "bedrooms": null, "home_type": "house"}'
    with patch("fairdeal.cascade.run_cascade", return_value=_cascade_result(answer)):
        criteria = parse_criteria("house to rent for 5 guys in Miami near the beach")

    assert criteria.budget_monthly is None
    assert criteria.anchors == ["Miami", "beach"]


def test_parse_criteria_no_local_model_raises_cascade_parse_error() -> None:
    with patch("fairdeal.cascade.run_cascade", side_effect=OllamaConnectionError("connection refused")):
        with pytest.raises(CascadeParseError, match="local model inference is unavailable"):
            parse_criteria("anything")
