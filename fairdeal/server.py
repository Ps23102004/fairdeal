"""Local stdlib-only HTTP server for FairDeal.

Binds 127.0.0.1 only. No web framework — http.server + ThreadingHTTPServer,
matching the sibling llm-ladder / RepoTriage Agent server.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fairdeal.cascade import CascadeParseError
from fairdeal.collegeroi import run as collegeroi_run
from fairdeal.contract import run as contract_run
from fairdeal.lease import run as lease_run
from fairdeal.rentcheck import run as rentcheck_run

DEFAULT_PORT = 8000
PORT = int(os.environ.get("FAIRDEAL_PORT", DEFAULT_PORT))
WEB_DIR = (Path(__file__).resolve().parent.parent / "web").resolve()

_ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
_ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}

_STATIC_ROUTES = {
    "/": "index.html",
    "/index.html": "index.html",
}

# Loopback-only server, so this guards against a misbehaving local client
# tying up a ThreadingHTTPServer thread, not a remote attacker.
_MAX_BODY_BYTES = 1_000_000

# Each module's run() takes different arguments (rentcheck: a chat message;
# lease/contract: pasted document text; collegeroi: school + optional major),
# so each dict value is a small (body: dict) -> dict adapter, not run() itself
# — that keeps _route_post's dispatch uniform regardless of a module's own signature.
def _dispatch_rentcheck(body: dict) -> dict:
    return rentcheck_run(str(body.get("message", "")))


def _dispatch_leasereview(body: dict) -> dict:
    return lease_run(str(body.get("document_text", "")))


def _dispatch_contractreview(body: dict) -> dict:
    return contract_run(str(body.get("document_text", "")))


def _dispatch_collegeroi(body: dict) -> dict:
    major = body.get("major")
    return collegeroi_run(str(body.get("school", "")), major if isinstance(major, str) and major.strip() else None)


MODULES = {
    "rentcheck": _dispatch_rentcheck,
    "leasereview": _dispatch_leasereview,
    "contractreview": _dispatch_contractreview,
    "collegeroi": _dispatch_collegeroi,
}


class _BadRequestError(Exception):
    """Raised for client-side request problems that should map to HTTP 400."""


class Handler(BaseHTTPRequestHandler):
    server_version = "fairdeal/0.1"

    # -- trust-boundary check -------------------------------------------------

    def _origin_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        if host not in _ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in _ALLOWED_ORIGINS:
            return False
        return True

    # -- helpers ----------------------------------------------------------

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise _BadRequestError("missing Content-Length header")
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            raise _BadRequestError("malformed Content-Length header")
        if length < 0:
            raise _BadRequestError("negative Content-Length header")
        if length > _MAX_BODY_BYTES:
            raise _BadRequestError(f"request body exceeds {_MAX_BODY_BYTES} byte limit")
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict):
            raise _BadRequestError(f"request body must be a JSON object, got {type(body).__name__}")
        return body

    def _serve_static(self, url_path: str) -> None:
        rel = _STATIC_ROUTES.get(url_path)
        if rel is None:
            rel = unquote(url_path).lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR not in target.parents and target != WEB_DIR:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not target.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        content_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
        }.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- dispatch -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler naming
        self._handle(self._route_get)

    def do_POST(self) -> None:  # noqa: N802
        self._handle(self._route_post)

    def _handle(self, route_fn) -> None:
        if not self._origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden host/origin"})
            return
        try:
            route_fn()
        except _BadRequestError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "malformed JSON body"})
        except CascadeParseError as exc:
            # A missing/unavailable local model is a business-outcome for the
            # chat UI to explain, not a 500 — but it's still not a client error.
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except Exception:  # noqa: BLE001 - never leak internals to the client
            traceback.print_exc(file=sys.stderr)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal server error"})

    def _route_get(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._serve_static(path)

    def _route_post(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            module_name = path[len("/api/"):]
            module_fn = MODULES.get(module_name)
            if module_fn is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown module {module_name!r}"})
                return
            body = self._read_json_body()
            result = module_fn(body)
            self._send_json(HTTPStatus.OK, result)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:  # quieter default logging
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Serving on http://127.0.0.1:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
