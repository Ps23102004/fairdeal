from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from unittest.mock import patch

import pytest

from fairdeal import server as server_module
from fairdeal.server import Handler


@pytest.fixture()
def live_server():
    """Boot a real Handler on an ephemeral port for socket-level tests.

    server.py reads _ALLOWED_HOSTS/_ALLOWED_ORIGINS from the module-level
    PORT at import time, so the fixture patches those to match whatever
    port the OS hands out instead of trying to force a fixed port.
    """
    httpd = server_module.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    with (
        patch.object(server_module, "_ALLOWED_HOSTS", allowed_hosts),
        patch.object(server_module, "_ALLOWED_ORIGINS", allowed_origins),
    ):
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)
            httpd.server_close()


def _post(port: int, path: str, body: bytes | None, headers: dict | None = None) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, body=body, headers=headers or {})
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else {})
    finally:
        conn.close()


def test_forbidden_host_rejected(live_server) -> None:
    status, payload = _post(live_server, "/api/rentcheck", b'{"message":"hi"}', {"Host": "evil.test"})
    assert status == 403
    assert payload == {"error": "forbidden host/origin"}


def test_forbidden_origin_rejected(live_server) -> None:
    status, payload = _post(
        live_server,
        "/api/rentcheck",
        b'{"message":"hi"}',
        {"Content-Type": "application/json", "Origin": "http://evil.test"},
    )
    assert status == 403


def test_unknown_module_404(live_server) -> None:
    status, payload = _post(live_server, "/api/notarealmodule", b'{"message":"hi"}', {"Content-Type": "application/json"})
    assert status == 404
    assert "notarealmodule" in payload["error"]


def test_malformed_json_400(live_server) -> None:
    status, payload = _post(live_server, "/api/rentcheck", b"{", {"Content-Type": "application/json"})
    assert status == 400
    assert payload == {"error": "malformed JSON body"}


def test_non_object_json_body_400(live_server) -> None:
    # A bare JSON array is valid JSON but not a valid request body — must not
    # reach `body.get(...)` and crash with a 500.
    status, payload = _post(live_server, "/api/rentcheck", b"[]", {"Content-Type": "application/json"})
    assert status == 400
    assert "JSON object" in payload["error"]


def test_oversized_body_rejected(live_server) -> None:
    conn = HTTPConnection("127.0.0.1", live_server, timeout=5)
    try:
        conn.putrequest("POST", "/api/rentcheck")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(server_module._MAX_BODY_BYTES + 1))
        conn.endheaders()
        resp = conn.getresponse()
        payload = json.loads(resp.read())
    finally:
        conn.close()
    assert resp.status == 400
    assert "exceeds" in payload["error"]


def test_successful_rentcheck_roundtrip(live_server) -> None:
    fake_result = {"reply_text": "Found 1 place.", "results": []}
    with patch.object(server_module, "MODULES", {"rentcheck": lambda message: fake_result}):
        status, payload = _post(
            live_server, "/api/rentcheck", b'{"message":"2BR near USF"}', {"Content-Type": "application/json"}
        )
    assert status == 200
    assert payload == fake_result


def test_leasereview_dispatch_passes_document_text(live_server) -> None:
    captured = {}

    def fake_run(document_text):
        captured["document_text"] = document_text
        return {"reply_text": "ok", "data_source": "clause-library-v1", "results": []}

    with patch("fairdeal.server.lease_run", fake_run):
        status, payload = _post(
            live_server,
            "/api/leasereview",
            json.dumps({"document_text": "the rent may increase at landlord's sole discretion"}).encode(),
            {"Content-Type": "application/json"},
        )
    assert status == 200
    assert payload["data_source"] == "clause-library-v1"
    assert captured["document_text"] == "the rent may increase at landlord's sole discretion"


def test_contractreview_dispatch_passes_document_text(live_server) -> None:
    captured = {}

    def fake_run(document_text):
        captured["document_text"] = document_text
        return {"reply_text": "ok", "data_source": "clause-library-v1", "results": []}

    with patch("fairdeal.server.contract_run", fake_run):
        status, payload = _post(
            live_server,
            "/api/contractreview",
            json.dumps({"document_text": "unlimited liability"}).encode(),
            {"Content-Type": "application/json"},
        )
    assert status == 200
    assert captured["document_text"] == "unlimited liability"


def test_collegeroi_dispatch_passes_school_and_major(live_server) -> None:
    captured = {}

    def fake_run(school, major=None):
        captured["school"] = school
        captured["major"] = major
        return {"reply_text": "ok", "data_source": "college-scorecard", "results": []}

    with patch("fairdeal.server.collegeroi_run", fake_run):
        status, payload = _post(
            live_server,
            "/api/collegeroi",
            json.dumps({"school": "University of San Francisco", "major": "Computer Science"}).encode(),
            {"Content-Type": "application/json"},
        )
    assert status == 200
    assert captured == {"school": "University of San Francisco", "major": "Computer Science"}


def test_collegeroi_dispatch_blank_major_becomes_none(live_server) -> None:
    captured = {}

    def fake_run(school, major=None):
        captured["major"] = major
        return {"reply_text": "ok", "data_source": "college-scorecard", "results": []}

    with patch("fairdeal.server.collegeroi_run", fake_run):
        _post(
            live_server,
            "/api/collegeroi",
            json.dumps({"school": "X", "major": "   "}).encode(),
            {"Content-Type": "application/json"},
        )
    assert captured["major"] is None


def test_unexpected_exception_returns_generic_500_no_leak(live_server) -> None:
    def _boom(message: str) -> dict:
        raise RuntimeError("some internal detail that must not reach the client")

    with patch.object(server_module, "MODULES", {"rentcheck": _boom}):
        status, payload = _post(
            live_server, "/api/rentcheck", b'{"message":"hi"}', {"Content-Type": "application/json"}
        )
    assert status == 500
    assert payload == {"error": "internal server error"}
    assert "internal detail" not in json.dumps(payload)


def test_static_index_served(live_server) -> None:
    conn = HTTPConnection("127.0.0.1", live_server, timeout=5)
    try:
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read()
    finally:
        conn.close()
    assert resp.status == 200
    assert b"FairDeal" in body


def test_path_traversal_blocked(live_server) -> None:
    conn = HTTPConnection("127.0.0.1", live_server, timeout=5)
    try:
        conn.request("GET", "/../pyproject.toml")
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
    assert resp.status == 404
