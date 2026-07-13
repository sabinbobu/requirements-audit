"""API tests — keyless throughout: explicit empty-key Settings, FunctionModel
for the SSE query path, TestClient for transport. No network, no services."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from requirements_audit.api.app import create_app
from requirements_audit.config import Settings
from requirements_audit.llm.provider import MissingCredentialsError


def _settings(tmp_path: Path) -> Settings:
    # Explicit ctor args outrank env/.env in pydantic-settings, so these tests
    # stay keyless and hermetic even on a machine with real keys configured.
    return Settings(
        anthropic_api_key=None,
        openai_api_key=None,
        sqlite_path=tmp_path / "api-test.sqlite",
        uploads_dir=tmp_path / "uploads",
        corrected_dir=tmp_path / "corrected",
    )


def _no_model(_: Settings) -> Model:
    raise MissingCredentialsError("No LLM API key configured.")


def _qa_model(_: Settings) -> Model:
    """A canned Planner+Analyst: route to Q&A, search once, answer with a citation."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        props = set(info.output_tools[0].parameters_json_schema.get("properties", {}))
        if "route" in props:  # planner step
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=info.output_tools[0].name,
                        args={"route": "qa", "subqueries": [], "rationale": "info request"},
                    )
                ]
            )
        tool_returned = any(
            isinstance(part, ToolReturnPart) for message in messages for part in message.parts
        )
        if not tool_returned:  # analyst step: retrieve before answering
            return ModelResponse(
                parts=[ToolCallPart(tool_name="hybrid_search", args={"query": "watchdog", "k": 3})]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={
                        "question": "What is the watchdog timeout?",
                        "text": "The watchdog supervision timeout is 100 ms.",
                        "citations": [
                            {"doc_id": "SYS", "requirement_id": "SYS-REQ-0101", "quote": "100 ms"}
                        ],
                    },
                )
            ]
        )

    return FunctionModel(fn)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Keyless app over an empty store; /query raises 503 by construction."""
    return TestClient(create_app(_settings(tmp_path), model_factory=_no_model))


@pytest.fixture
def ingested_client(tmp_path: Path, generated_corpus: Path) -> TestClient:
    """Keyless app with the generated corpus ingested through the API itself
    (hermetic: user documents in the repo's corpus/ never affect these tests)."""
    c = TestClient(create_app(_settings(tmp_path), model_factory=_no_model))
    assert c.post("/ingest", json={"corpus_dir": str(generated_corpus)}).status_code == 200
    return c


def test_index_serves_the_editor_ui(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Requirements Audit" in response.text
    # The self-contained assets resolve through the /static mount.
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_documents_lists_ingested_docs_in_order(ingested_client: TestClient) -> None:
    docs = ingested_client.get("/documents").json()
    ids = [d["doc_id"] for d in docs]
    assert ids == sorted(ids) and len(ids) == 8
    assert all(d["chunk_count"] > 0 for d in docs)


def test_document_detail_returns_chunks_in_document_order(ingested_client: TestClient) -> None:
    detail = ingested_client.get("/documents/SYS").json()
    assert detail["doc_id"] == "SYS"
    req_ids = [c["requirement_id"] for c in detail["chunks"]]
    assert req_ids == sorted(req_ids) and req_ids  # zero-padded ids = doc order
    assert all(c["doc_id"] == "SYS" for c in detail["chunks"])


def test_document_detail_unknown_doc_is_404(ingested_client: TestClient) -> None:
    assert ingested_client.get("/documents/NOPE").status_code == 404


# ─── PATCH /requirements/{id} (the resolve write path) ─────────────────────────
def test_patch_requirement_updates_text_and_writes_corrected_copy(
    ingested_client: TestClient, tmp_path: Path
) -> None:
    resp = ingested_client.patch(
        "/requirements/SYS-REQ-0101", json={"text": "Rewritten watchdog behavior."}
    )
    assert resp.status_code == 200, resp.text
    chunk = resp.json()
    assert chunk["requirement_id"] == "SYS-REQ-0101"
    assert chunk["text"] == "Rewritten watchdog behavior."

    # A convenience artifact only — never the original source, and not
    # consulted by re-audit (which reads the store directly).
    corrected = tmp_path / "corrected" / "SYS.md"
    assert corrected.exists()
    assert "Rewritten watchdog behavior." in corrected.read_text(encoding="utf-8")


def test_patch_requirement_replaces_parameters(ingested_client: TestClient) -> None:
    resp = ingested_client.patch(
        "/requirements/SYS-REQ-0101", json={"parameters": {"watchdog_timeout_ms": "250"}}
    )
    assert resp.status_code == 200
    assert resp.json()["parameters"] == {"watchdog_timeout_ms": "250"}


def test_patch_requirement_unknown_is_404(ingested_client: TestClient) -> None:
    resp = ingested_client.patch("/requirements/NOPE-REQ-0001", json={"text": "x"})
    assert resp.status_code == 404


def test_patch_requirement_resolves_scoped_numeric_mismatch(
    ingested_client: TestClient,
) -> None:
    """The exact "Beyond Compare" loop: a scoped audit shows a numeric
    conflict, the losing side is edited to match, and re-running the same
    scoped audit no longer reports it."""
    target = frozenset(("SWC-REQ-0101", "SYS-REQ-0101"))

    before = ingested_client.post("/audit", json={"doc_id": "SYS"}).json()
    before_pairs = {
        frozenset((f["candidate"]["req_a"], f["candidate"]["req_b"])) for f in before["findings"]
    }
    assert target in before_pairs

    resp = ingested_client.patch(
        "/requirements/SYS-REQ-0101", json={"parameters": {"watchdog_timeout_ms": "250"}}
    )
    assert resp.status_code == 200

    after = ingested_client.post("/audit", json={"doc_id": "SYS"}).json()
    after_pairs = {
        frozenset((f["candidate"]["req_a"], f["candidate"]["req_b"])) for f in after["findings"]
    }
    assert target not in after_pairs


# ─── /upload ──────────────────────────────────────────────────────────────────
_UPLOAD_MD = (
    "# Brake Control\n\nDocument ID: BRAKE\nType: component\n\n## Timing\n\n"
    "### BRAKE-REQ-0101 — Actuation latency\n\n"
    "The brake actuator shall engage within 50 ms.\n\n"
    "- Status: active\n- Parameters: brake_latency_ms = 50\n"
)


def test_upload_markdown_ingests_and_appears_in_documents(client: TestClient) -> None:
    resp = client.post("/upload", files={"file": ("BRAKE.md", _UPLOAD_MD, "text/markdown")})
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert "BRAKE" in report["new_docs"] and report["chunks"] > 0

    ids = [d["doc_id"] for d in client.get("/documents").json()]
    assert "BRAKE" in ids


def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    resp = client.post("/upload", files={"file": ("notes.txt", "hello", "text/plain")})
    assert resp.status_code == 400


def test_upload_unparseable_is_422_and_not_persisted(client: TestClient) -> None:
    # Valid extension, but no requirement IDs → parser raises → 422, file removed.
    resp = client.post("/upload", files={"file": ("junk.md", "just some prose", "text/markdown")})
    assert resp.status_code == 422
    # A subsequent listing must not show a phantom doc, and re-uploading a good
    # file must still work (the bad file did not wedge the uploads dir).
    assert client.get("/documents").json() == []
    good = client.post("/upload", files={"file": ("BRAKE.md", _UPLOAD_MD, "text/markdown")})
    assert good.status_code == 200


def test_healthz_reports_version_and_chunk_count(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chunks"] == 0  # nothing ingested yet


def test_ingest_returns_report_and_is_idempotent(
    client: TestClient, generated_corpus: Path
) -> None:
    first = client.post("/ingest", json={"corpus_dir": str(generated_corpus)}).json()
    assert first["chunks"] > 0
    assert first["new_docs"] and not first["unchanged_docs"]

    again = client.post("/ingest", json={"corpus_dir": str(generated_corpus)}).json()
    assert not again["new_docs"] and again["unchanged_docs"]  # ledger hit: no re-work


def test_ingest_missing_directory_is_400(client: TestClient) -> None:
    response = client.post("/ingest", json={"corpus_dir": "/nonexistent/nowhere"})
    assert response.status_code == 400


def test_audit_keyless_falls_back_to_deterministic(ingested_client: TestClient) -> None:
    response = ingested_client.post("/audit", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["llm_used"] is False  # auto mode, no keys → deterministic classes
    assert body["findings"]  # numeric/superseded conflicts exist in the corpus
    assert body["trace"]["total_latency_ms"] > 0


def test_audit_explicit_llm_without_keys_is_503(ingested_client: TestClient) -> None:
    response = ingested_client.post("/audit", json={"use_llm": True})
    assert response.status_code == 503


def test_audit_scoped_to_doc_only_returns_touching_findings(
    ingested_client: TestClient,
) -> None:
    response = ingested_client.post("/audit", json={"doc_id": "SYS"})
    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == "SYS"
    assert body["findings"]  # SYS participates in a known deterministic conflict
    for f in body["findings"]:
        c = f["candidate"]
        assert c["req_a"].startswith("SYS-") or c["req_b"].startswith("SYS-")


def test_audit_unknown_doc_is_404(ingested_client: TestClient) -> None:
    response = ingested_client.post("/audit", json={"doc_id": "NOPE"})
    assert response.status_code == 404


# ─── /audit/stream ──────────────────────────────────────────────────────────
def _parse_sse(raw: str) -> list[tuple[str, str]]:
    """Parse a raw SSE response body into (event, data) pairs."""
    events: list[tuple[str, str]] = []
    current_event = ""
    for line in raw.splitlines():
        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            events.append((current_event, line.removeprefix("data:").strip()))
    return events


def test_audit_stream_keyless_emits_stages_and_report(ingested_client: TestClient) -> None:
    with ingested_client.stream("POST", "/audit/stream", json={}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())

    events = _parse_sse(raw)
    names = [name for name, _ in events]
    assert names[-1] == "report"
    assert "stage" in names
    # Keyless (deterministic-only): no comparator loop, so no progress events.
    assert "progress" not in names

    report = json.loads(dict(events)["report"])
    assert report["llm_used"] is False
    assert report["findings"]
    assert report["doc_id"] is None


def test_audit_stream_scoped_to_doc_only_returns_touching_findings(
    ingested_client: TestClient,
) -> None:
    with ingested_client.stream("POST", "/audit/stream", json={"doc_id": "SYS"}) as response:
        assert response.status_code == 200
        raw = "".join(response.iter_text())

    report = json.loads(dict(_parse_sse(raw))["report"])
    assert report["doc_id"] == "SYS"
    assert report["findings"]
    for f in report["findings"]:
        c = f["candidate"]
        assert c["req_a"].startswith("SYS-") or c["req_b"].startswith("SYS-")


def test_audit_stream_unknown_doc_is_404(ingested_client: TestClient) -> None:
    # Validated synchronously before the SSE response starts, so this is a
    # normal blocking request/response, not a stream.
    response = ingested_client.post("/audit/stream", json={"doc_id": "NOPE"})
    assert response.status_code == 404


def test_query_without_keys_is_503(ingested_client: TestClient) -> None:
    response = ingested_client.post("/query", json={"question": "What is the watchdog timeout?"})
    assert response.status_code == 503


def test_query_streams_stages_then_answer_and_trace(tmp_path: Path, generated_corpus: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path), model_factory=_qa_model))
    assert client.post("/ingest", json={"corpus_dir": str(generated_corpus)}).status_code == 200

    with client.stream(
        "POST", "/query", json={"question": "What is the watchdog timeout?"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())

    # Parse the SSE frames into (event, data) pairs.
    events: list[tuple[str, str]] = []
    current_event = ""
    for line in raw.splitlines():
        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            events.append((current_event, line.removeprefix("data:").strip()))

    names = [name for name, _ in events]
    assert names[-2:] == ["answer", "trace"]  # stages stream first, answer last
    assert "stage" in names

    answer = json.loads(dict(events)["answer"])
    assert answer["citations"][0]["requirement_id"] == "SYS-REQ-0101"
    trace = json.loads(dict(events)["trace"])
    assert [s["name"] for s in trace["steps"]] == ["plan", "analyst"]
