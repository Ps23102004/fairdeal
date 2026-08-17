from __future__ import annotations

import os

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


class ModelListError(Exception):
    pass


def list_ollama_models() -> list[str]:
    """Model tags currently pulled in the local Ollama daemon, for the UI's
    model-selector dropdown. Raises ModelListError if Ollama isn't reachable
    — callers (server.py) should degrade to an empty list, not fail the page."""
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise ModelListError(f"could not reach Ollama at {OLLAMA_HOST}: {exc}") from exc

    return [m["name"] for m in payload.get("models", []) if "name" in m]
