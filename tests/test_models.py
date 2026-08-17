from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fairdeal.models import ModelListError, list_ollama_models


def _mock_response(payload) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_list_ollama_models_returns_names() -> None:
    payload = {"models": [{"name": "qwen2.5:3b", "size": 123}, {"name": "llama3.2:3b", "size": 456}]}
    with patch("fairdeal.models.requests.get", return_value=_mock_response(payload)):
        assert list_ollama_models() == ["qwen2.5:3b", "llama3.2:3b"]


def test_list_ollama_models_empty_when_none_pulled() -> None:
    with patch("fairdeal.models.requests.get", return_value=_mock_response({"models": []})):
        assert list_ollama_models() == []


def test_list_ollama_models_raises_on_unreachable() -> None:
    import requests

    with patch("fairdeal.models.requests.get", side_effect=requests.RequestException("connection refused")):
        with pytest.raises(ModelListError, match="could not reach Ollama"):
            list_ollama_models()
