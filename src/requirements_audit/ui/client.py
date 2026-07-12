"""Typed HTTP client for the requirements-audit API.

All of the UI's server communication lives here, streamlit-free, so it is unit-
testable in-process: `starlette.testclient.TestClient` subclasses `httpx.Client`,
which means tests can wire this client straight to the FastAPI app with no
socket. The Streamlit layer (`ui.app`) contains rendering only — the UI must not
re-implement pipeline logic (Phase G scope rule), and keeping this boundary is
how that stays true.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx


class ApiError(RuntimeError):
    """A non-2xx API response, carrying the server's `detail` message."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"API error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _check(response: httpx.Response) -> dict[str, Any]:
    if response.is_success:
        payload: dict[str, Any] = response.json()
        return payload
    try:
        detail = response.json().get("detail", response.text)
    except json.JSONDecodeError:
        detail = response.text
    raise ApiError(response.status_code, str(detail))


def parse_sse(lines: Iterator[str]) -> Iterator[tuple[str, str]]:
    """Minimal SSE parser: yields (event, data) pairs from a line stream.

    Handles exactly what the API emits (single-line `event:`/`data:` frames);
    comments and multi-line data are out of scope by construction.
    """
    event = ""
    for line in lines:
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            yield event, line.removeprefix("data:").strip()


class ApiClient:
    """One instance per UI session. `client` is injectable for in-process tests."""

    def __init__(self, base_url: str = "http://localhost:8000", client: httpx.Client | None = None):
        # Long timeout: a full audit sweep with the LLM comparator is minutes,
        # not seconds. Streamlit shows a spinner meanwhile.
        self._client = (
            client if client is not None else httpx.Client(base_url=base_url, timeout=300)
        )

    def health(self) -> dict[str, Any]:
        return _check(self._client.get("/healthz"))

    def ingest(self, corpus_dir: str) -> dict[str, Any]:
        return _check(self._client.post("/ingest", json={"corpus_dir": corpus_dir}))

    def audit(self, use_llm: bool | None = None) -> dict[str, Any]:
        return _check(self._client.post("/audit", json={"use_llm": use_llm}))

    def query_stream(self, question: str) -> Iterator[tuple[str, dict[str, Any] | str]]:
        """Stream `/query` events: ('stage'|'answer'|'trace', parsed JSON) or
        ('error', message). Raises ApiError on a non-2xx response (e.g. 503
        when no LLM key is configured server-side)."""
        with self._client.stream("POST", "/query", json={"question": question}) as response:
            if not response.is_success:
                response.read()  # buffer the body so .json() works on a stream
                _check(response)
            for event, data in parse_sse(response.iter_lines()):
                yield (event, data) if event == "error" else (event, json.loads(data))
