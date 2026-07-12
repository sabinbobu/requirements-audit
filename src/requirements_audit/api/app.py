"""FastAPI ops layer — a thin HTTP surface over the orchestrator.

Routes mirror the CLI verbs one-to-one (`/healthz`, `/ingest`, `/query`,
`/audit`) and re-implement no pipeline logic: the CLI and the Streamlit UI
(Phase G) both sit on the same orchestrator, so there is a single source of
truth for behavior.

Key behaviors:
- `/query` streams Server-Sent Events: one `stage` event per pipeline step as
  it completes (via the injectable tracer), then the final `answer` and a
  `trace` summary with per-stage latencies. No key configured → 503 with the
  same guidance the CLI gives.
- `/audit` falls back to the deterministic classes when no key is configured,
  exactly like `requirements-audit audit` — the response says which mode ran.
- Every response carries the run trace (stage latencies), so cost/latency are
  visible per request without a LangFuse round-trip.

`create_app(settings, model_factory)` exists so tests inject a keyless
`Settings` and a PydanticAI `FunctionModel`; the module-level `app` is what
uvicorn/Docker serve.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_ai.models import Model
from sse_starlette import EventSourceResponse, ServerSentEvent

from requirements_audit import __version__
from requirements_audit.config import Settings
from requirements_audit.ingestion.pipeline import IngestReport, ingest_corpus
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.llm.provider import MissingCredentialsError, build_model
from requirements_audit.models import AuditReport, Chunk, Finding
from requirements_audit.orchestrator import answer_query, run_audit
from requirements_audit.tracing import RunTrace, StepRecord, Tracer

ModelFactory = Callable[[Settings], Model]

# The editor-style web UI: self-contained HTML/CSS/JS, served at "/".
_STATIC_DIR = Path(__file__).parent / "static"


# ─── request / response bodies ────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    version: str
    chunks: int


class IngestRequest(BaseModel):
    corpus_dir: str


class DocumentSummary(BaseModel):
    doc_id: str
    chunk_count: int


class DocumentDetail(BaseModel):
    """A document's requirement chunks in document order — what the editor UI
    renders as a source file."""

    doc_id: str
    chunks: list[Chunk]


class QueryRequest(BaseModel):
    question: str


class AuditRequest(BaseModel):
    # None = auto: use the LLM when a key is configured (mirrors the CLI flag).
    use_llm: bool | None = None


class TraceSummary(BaseModel):
    """The per-request observability payload: stage latencies, token totals,
    and the estimated cost (None on deterministic runs / unpriced models)."""

    steps: list[StepRecord]
    total_latency_ms: float
    usage: dict[str, int] | None = None
    estimated_usd: float | None = None
    pricing_model: str | None = None

    @classmethod
    def from_trace(cls, trace: RunTrace) -> TraceSummary:
        return cls(
            steps=trace.steps,
            total_latency_ms=trace.total_latency_ms,
            usage=trace.metadata.get("usage"),
            estimated_usd=trace.metadata.get("estimated_usd"),
            pricing_model=trace.metadata.get("pricing_model"),
        )


class AuditResponse(BaseModel):
    findings: list[Finding]
    candidates_considered: int
    rejected_by_critic: int
    llm_used: bool
    trace: TraceSummary

    @classmethod
    def from_report(cls, report: AuditReport, llm_used: bool, trace: RunTrace) -> AuditResponse:
        return cls(
            findings=report.findings,
            candidates_considered=report.candidates_considered,
            rejected_by_critic=report.rejected_by_critic,
            llm_used=llm_used,
            trace=TraceSummary.from_trace(trace),
        )


class _StreamingTracer(Tracer):
    """A tracer that also pushes each completed step onto a queue, which the
    SSE generator drains — this is how `/query` streams stages live."""

    def __init__(self, events: queue.Queue[StepRecord | None], settings: Settings, **meta: object):
        super().__init__("query", settings, **meta)
        self._events = events

    def _emit(self, record: StepRecord) -> None:
        self._events.put(record)


def create_app(
    settings: Settings | None = None, model_factory: ModelFactory | None = None
) -> FastAPI:
    settings_ = settings if settings is not None else Settings()
    build = model_factory if model_factory is not None else build_model
    app = FastAPI(
        title="requirements-audit",
        version=__version__,
        description="Multi-agent contradiction detection over engineering requirement documents.",
    )

    def _store() -> SqliteStore:
        # One connection per request: SQLite opens are cheap and this keeps the
        # API process free of cross-request state.
        return SqliteStore(settings_.sqlite_path)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        with _store() as store:
            return HealthResponse(status="ok", version=__version__, chunks=store.chunk_count())

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """The editor-style web UI (self-contained static app)."""
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/documents", response_model=list[DocumentSummary])
    def documents() -> list[DocumentSummary]:
        with _store() as store:
            return [
                DocumentSummary(doc_id=doc_id, chunk_count=count)
                for doc_id, count in store.documents()
            ]

    @app.get("/documents/{doc_id}", response_model=DocumentDetail)
    def document(doc_id: str) -> DocumentDetail:
        with _store() as store:
            chunks = store.chunks_for_doc(doc_id)
        if not chunks:
            raise HTTPException(status_code=404, detail=f"Unknown document: {doc_id}")
        return DocumentDetail(doc_id=doc_id, chunks=chunks)

    @app.post("/ingest", response_model=IngestReport)
    def ingest(body: IngestRequest) -> IngestReport:
        corpus = Path(body.corpus_dir)
        if not corpus.is_dir():
            raise HTTPException(status_code=400, detail=f"Corpus directory not found: {corpus}")
        with _store() as store:
            return ingest_corpus(corpus, store)

    @app.post("/audit", response_model=AuditResponse)
    def audit(body: AuditRequest) -> AuditResponse:
        model: Model | None = None
        if body.use_llm is not False:
            try:
                model = build(settings_)
            except MissingCredentialsError as exc:
                if body.use_llm:  # explicitly requested but unavailable
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
                # Auto mode: fall back to the deterministic classes, like the CLI.
        llm_used = model is not None if body.use_llm is None else body.use_llm
        with _store() as store:
            report, trace = run_audit(store, settings_, model=model, use_llm=llm_used)
        return AuditResponse.from_report(report, llm_used, trace)

    @app.post("/query")
    def query(body: QueryRequest) -> EventSourceResponse:
        """SSE stream: `stage` per completed pipeline step, then `answer` + `trace`."""
        try:
            model = build(settings_)
        except MissingCredentialsError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        def events() -> Iterator[ServerSentEvent]:
            # Starlette runs sync generators in a threadpool, so blocking
            # queue reads here never stall the event loop.
            stage_events: queue.Queue[StepRecord | None] = queue.Queue()
            tracer = _StreamingTracer(stage_events, settings_, question=body.question)
            outcome: dict[str, object] = {}

            def worker() -> None:
                try:
                    with _store() as store:
                        answer, trace = answer_query(
                            store, body.question, settings_, model=model, tracer=tracer
                        )
                    outcome["answer"], outcome["trace"] = answer, trace
                except Exception as exc:  # surfaced to the client as an SSE error event
                    outcome["error"] = str(exc)
                finally:
                    stage_events.put(None)  # sentinel: no more stages

            threading.Thread(target=worker, daemon=True).start()
            while (record := stage_events.get()) is not None:
                yield ServerSentEvent(event="stage", data=record.model_dump_json())

            if "error" in outcome:
                yield ServerSentEvent(event="error", data=str(outcome["error"]))
                return
            answer = outcome["answer"]
            trace = outcome["trace"]
            assert isinstance(trace, RunTrace)  # narrow the untyped dict for mypy
            yield ServerSentEvent(event="answer", data=answer.model_dump_json())  # type: ignore[attr-defined]
            yield ServerSentEvent(
                event="trace", data=TraceSummary.from_trace(trace).model_dump_json()
            )

        return EventSourceResponse(events())

    # CSS/JS assets for the editor UI (index.html itself is served at "/").
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


# What uvicorn / the Docker image serve: real Settings from env/.env, real models.
app = create_app()
