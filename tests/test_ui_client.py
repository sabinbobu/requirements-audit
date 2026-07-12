"""UI client tests — the ApiClient wired straight to the FastAPI app in-process.

`starlette.testclient.TestClient` subclasses `httpx.Client`, so the exact client
code the Streamlit UI uses is exercised against the real API with no socket and
no keys. The Streamlit layer itself is rendering-only and is not tested here
(streamlit lives in the optional `ui` dependency group, not installed in CI).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient

from requirements_audit.api.app import ModelFactory, create_app
from requirements_audit.ui.client import ApiClient, ApiError, parse_sse
from tests.test_api import _no_model, _qa_model, _settings

_ROOT = Path(__file__).resolve().parents[1]
_CORPUS = _ROOT / "corpus"


def _ui(tmp_path: Path, model_factory: ModelFactory = _no_model) -> ApiClient:
    app = create_app(_settings(tmp_path), model_factory=model_factory)
    # Starlette's TestClient no longer subclasses httpx.Client, but it keeps the
    # same get/post/stream surface ApiClient uses — the cast is the honest,
    # runtime-verified duck-typing bridge for in-process testing.
    return ApiClient(client=cast(httpx.Client, TestClient(app)))


def test_parse_sse_pairs_events_with_data() -> None:
    lines = iter(["event: stage", "data: {}", "", "event: answer", 'data: {"x": 1}'])
    assert list(parse_sse(lines)) == [("stage", "{}"), ("answer", '{"x": 1}')]


def test_health_and_ingest_round_trip(tmp_path: Path) -> None:
    ui = _ui(tmp_path)
    assert ui.health()["chunks"] == 0

    report = ui.ingest(str(_CORPUS))
    assert report["chunks"] > 0
    assert ui.health()["chunks"] == report["chunks"]


def test_audit_deterministic_via_client(tmp_path: Path) -> None:
    ui = _ui(tmp_path)
    ui.ingest(str(_CORPUS))

    report = ui.audit(use_llm=None)  # auto, keyless → deterministic

    assert report["llm_used"] is False
    assert report["findings"]


def test_api_error_carries_server_detail(tmp_path: Path) -> None:
    ui = _ui(tmp_path)
    with pytest.raises(ApiError) as excinfo:
        ui.ingest("/nonexistent/nowhere")
    assert excinfo.value.status_code == 400
    assert "not found" in excinfo.value.detail


def test_query_stream_yields_stages_then_answer(tmp_path: Path) -> None:
    ui = _ui(tmp_path, model_factory=_qa_model)
    ui.ingest(str(_CORPUS))

    events = list(ui.query_stream("What is the watchdog timeout?"))

    names = [name for name, _ in events]
    assert "stage" in names and names[-2:] == ["answer", "trace"]
    answer = dict(events)["answer"]
    assert isinstance(answer, dict)
    assert answer["citations"][0]["requirement_id"] == "SYS-REQ-0101"


def test_query_stream_keyless_raises_api_error(tmp_path: Path) -> None:
    ui = _ui(tmp_path)
    ui.ingest(str(_CORPUS))
    with pytest.raises(ApiError) as excinfo:
        list(ui.query_stream("anything"))
    assert excinfo.value.status_code == 503
