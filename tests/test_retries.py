"""Retry behaviour of :func:`nl_housing.ingest.build_session` (review finding C1).

The tests use a throwaway HTTP server on 127.0.0.1, so the real ``requests`` /
``urllib3`` retry machinery is exercised without any external network. Sleeps are
recorded instead of performed, which keeps the tests fast and lets us assert the
backoff schedule and the ``Retry-After`` handling exactly.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
import urllib3.util.retry

from nl_housing import ingest


class ScriptedServer:
    """Serves a scripted sequence of ``(status, headers)`` responses, then 200 + JSON."""

    def __init__(self) -> None:
        self.script: list[tuple[int, dict[str, str]]] = []
        self.hits = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (name required by BaseHTTPRequestHandler)
                outer.hits += 1
                status, headers = outer.script.pop(0) if outer.script else (200, {})
                body = json.dumps({"value": [{"ID": 0}]} if status == 200 else {}).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:  # keep pytest output clean
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/TypedDataSet"


@pytest.fixture
def server() -> Iterator[ScriptedServer]:
    srv = ScriptedServer()
    thread = threading.Thread(target=srv.httpd.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.httpd.shutdown()
    srv.httpd.server_close()


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record urllib3's backoff sleeps instead of sleeping."""
    recorded: list[float] = []
    monkeypatch.setattr(urllib3.util.retry.time, "sleep", recorded.append)
    return recorded


def _session(**kwargs: float) -> requests.Session:
    session = ingest.build_session(**kwargs)
    session.trust_env = False  # never route the local test server through an HTTP(S) proxy
    return session


def test_retries_transient_5xx_with_exponential_backoff(server: ScriptedServer, sleeps: list[float]):
    server.script = [(503, {}), (502, {}), (500, {})]
    rows = ingest.fetch_all(server.url, _session(backoff_factor=0.5))
    assert rows == [{"ID": 0}]
    assert server.hits == 4
    # urllib3: no wait after the first failure, then backoff_factor * 2 ** (n - 1)
    assert sleeps == [1.0, 2.0]


def test_respects_retry_after_header(server: ScriptedServer, sleeps: list[float]):
    server.script = [(429, {"Retry-After": "7"})]
    assert ingest.fetch_all(server.url, _session(backoff_factor=0.5)) == [{"ID": 0}]
    assert server.hits == 2
    assert sleeps == [7.0]


def test_gives_up_after_total_retries_with_http_error(server: ScriptedServer, sleeps: list[float]):
    server.script = [(500, {})] * 10
    with pytest.raises(requests.HTTPError, match="500"):
        ingest.fetch_all(server.url, _session(total=2, backoff_factor=0))
    assert server.hits == 3  # first attempt + 2 retries


def test_client_errors_are_not_retried(server: ScriptedServer, sleeps: list[float]):
    server.script = [(404, {})]
    with pytest.raises(requests.HTTPError, match="404"):
        ingest.fetch_all(server.url, _session())
    assert server.hits == 1
    assert sleeps == []


def test_default_session_config():
    adapter = ingest.build_session().get_adapter("https://opendata.cbs.nl/")
    retry = adapter.max_retries
    assert retry.total == ingest.RETRY_TOTAL
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert retry.respect_retry_after_header is True


def test_run_uses_retrying_session(monkeypatch: pytest.MonkeyPatch, repo_root, write_config):
    """`ingest.run` without an explicit session must build the retrying one."""
    write_config("tables: []\n")
    built: list[requests.Session] = []
    original = ingest.build_session

    def spy() -> requests.Session:
        built.append(original())
        return built[-1]

    monkeypatch.setattr(ingest, "build_session", spy)
    ingest.run(root=repo_root)
    assert len(built) == 1
