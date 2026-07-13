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
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_ai.models import Model
from sse_starlette import EventSourceResponse, ServerSentEvent

from requirements_audit import __version__
from requirements_audit.config import Settings
from requirements_audit.corpus.generator import render_markdown
from requirements_audit.ingestion.parser import parse_file
from requirements_audit.ingestion.pipeline import IngestReport, ingest_corpus, reconstruct_document
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.llm.provider import MissingCredentialsError, build_model
from requirements_audit.models import AuditReport, Chunk, Finding
from requirements_audit.orchestrator import answer_query, run_audit
from requirements_audit.tracing import RunTrace, StepRecord, Tracer

ModelFactory = Callable[[Settings], Model]

# The editor-style web UI: self-contained HTML/CSS/JS, served at "/".
_STATIC_DIR = Path(__file__).parent / "static"

# Ingestible upload formats and a size cap (generous for a spec, bounds abuse).
_UPLOAD_SUFFIXES = {".md", ".pdf"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


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
    source: str  # source filename (e.g. "SYS.md", "BRAKE.pdf") for the explorer


class DocumentDetail(BaseModel):
    """A document's requirement chunks in document order — what the editor UI
    renders as a source file."""

    doc_id: str
    chunks: list[Chunk]


class UpdateRequirementRequest(BaseModel):
    """A resolve edit: `None` leaves a field unchanged; `parameters`, when
    given, replaces the whole dict (the client already holds the full chunk
    and sends it back merged with its edit)."""

    text: str | None = None
    parameters: dict[str, str] | None = None


class QueryRequest(BaseModel):
    question: str


class AuditRequest(BaseModel):
    # None = auto: use the LLM when a key is configured (mirrors the CLI flag).
    use_llm: bool | None = None
    # None = full-corpus sweep; a doc_id scopes candidate generation to that
    # document (compared against the rest of the corpus) — faster, focused.
    doc_id: str | None = None


class AuditProgress(BaseModel):
    """Fine-grained progress through the comparator loop, the audit's most
    expensive (LLM-bound) stage — what a determinate progress bar reads."""

    done: int
    total: int


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
    doc_id: str | None = None  # set when the audit was scoped to one document

    @classmethod
    def from_report(
        cls, report: AuditReport, llm_used: bool, trace: RunTrace, *, doc_id: str | None = None
    ) -> AuditResponse:
        return cls(
            findings=report.findings,
            candidates_considered=report.candidates_considered,
            rejected_by_critic=report.rejected_by_critic,
            llm_used=llm_used,
            trace=TraceSummary.from_trace(trace),
            doc_id=doc_id,
        )


# Union of everything a streaming endpoint can push through its queue.
_StreamEvent = StepRecord | AuditProgress


class _StreamingTracer(Tracer):
    """A tracer that also pushes each completed step onto a queue, which the
    SSE generator drains — this is how `/query` and `/audit/stream` show
    live progress."""

    def __init__(
        self,
        name: str,
        events: queue.Queue[_StreamEvent | None],
        settings: Settings,
        **meta: object,
    ) -> None:
        super().__init__(name, settings, **meta)
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

    def _require_known_doc(store: SqliteStore, doc_id: str) -> None:
        # Without this, an unknown focus_doc silently scopes an audit to
        # nothing (zero candidates touch a document that isn't in the store),
        # which reads as "no contradictions" instead of "bad request".
        known_ids = {d for d, _, _ in store.documents()}
        if doc_id not in known_ids:
            raise HTTPException(status_code=404, detail=f"Unknown document: {doc_id}")

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
                DocumentSummary(doc_id=doc_id, chunk_count=count, source=Path(source).name)
                for doc_id, count, source in store.documents()
            ]

    @app.get("/documents/{doc_id}", response_model=DocumentDetail)
    def document(doc_id: str) -> DocumentDetail:
        with _store() as store:
            chunks = store.chunks_for_doc(doc_id)
        if not chunks:
            raise HTTPException(status_code=404, detail=f"Unknown document: {doc_id}")
        return DocumentDetail(doc_id=doc_id, chunks=chunks)

    @app.patch("/requirements/{requirement_id}", response_model=Chunk)
    def update_requirement(requirement_id: str, body: UpdateRequirementRequest) -> Chunk:
        """The write path behind the compare/resolve view: edit a requirement's
        text and/or parameters, then re-audit to see the conflict clear. This
        endpoint only updates the store and a convenience corrected-copy file —
        the caller triggers the re-audit (`/audit` or `/audit/stream`) itself.
        """
        with _store() as store:
            updated = store.update_requirement(
                requirement_id, text=body.text, parameters=body.parameters
            )
            if updated is None:
                raise HTTPException(
                    status_code=404, detail=f"Unknown requirement: {requirement_id}"
                )
            doc = reconstruct_document(store, updated.doc_id)

        # Best-effort convenience artifact: never the original PDF/Markdown,
        # and never consulted by re-audit (which reads the store directly).
        if doc is not None:
            settings_.corrected_dir.mkdir(parents=True, exist_ok=True)
            (settings_.corrected_dir / f"{updated.doc_id}.md").write_text(
                render_markdown(doc), encoding="utf-8"
            )
        return updated

    @app.post("/ingest", response_model=IngestReport)
    def ingest(body: IngestRequest) -> IngestReport:
        corpus = Path(body.corpus_dir)
        if not corpus.is_dir():
            raise HTTPException(status_code=400, detail=f"Corpus directory not found: {corpus}")
        with _store() as store:
            return ingest_corpus(corpus, store)

    @app.post("/upload", response_model=IngestReport)
    async def upload(file: Annotated[UploadFile, File()]) -> IngestReport:
        """Accept a .md/.pdf spec, save it to the uploads dir, and ingest it.

        Reuses the idempotent `ingest_corpus` over the uploads dir. A file that
        cannot be parsed (scanned PDF, no requirement IDs) is deleted and the
        parser's reason is returned, so a bad upload never wedges future ingests.
        """
        name = Path(file.filename or "").name  # strip any path components
        if not name or Path(name).suffix.lower() not in _UPLOAD_SUFFIXES:
            raise HTTPException(status_code=400, detail="Only .md and .pdf files are supported.")
        data = await file.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit.")

        settings_.uploads_dir.mkdir(parents=True, exist_ok=True)
        target = settings_.uploads_dir / name
        target.write_bytes(data)
        try:
            # Validate the new file up front: PDFs raise on failure, and a
            # Markdown file with no requirement IDs parses to zero requirements
            # (would otherwise ingest a phantom empty document).
            doc = parse_file(target)
            if not doc.requirements:
                raise ValueError(
                    f"{name}: no requirements found — expected `XXX-REQ-0000` style identifiers."
                )
            with _store() as store:
                return ingest_corpus(settings_.uploads_dir, store)
        except ValueError as exc:  # PdfParseError and the empty-doc guard above
            target.unlink(missing_ok=True)  # don't let a bad file wedge re-ingest
            raise HTTPException(status_code=422, detail=str(exc)) from exc

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
            if body.doc_id is not None:
                _require_known_doc(store, body.doc_id)
            report, trace = run_audit(
                store, settings_, model=model, use_llm=llm_used, focus_doc=body.doc_id
            )
        return AuditResponse.from_report(report, llm_used, trace, doc_id=body.doc_id)

    @app.post("/audit/stream")
    def audit_stream(body: AuditRequest) -> EventSourceResponse:
        """SSE stream: `stage` per completed pipeline step, `progress` through
        the comparator loop (the LLM-bound stage — what a progress bar tracks),
        then a final `report` (an `AuditResponse`)."""
        model: Model | None = None
        if body.use_llm is not False:
            try:
                model = build(settings_)
            except MissingCredentialsError as exc:
                if body.use_llm:
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
        llm_used = model is not None if body.use_llm is None else body.use_llm

        if body.doc_id is not None:
            with _store() as store:
                _require_known_doc(store, body.doc_id)

        def events() -> Iterator[ServerSentEvent]:
            # Starlette runs sync generators in a threadpool, so blocking
            # queue reads here never stall the event loop.
            stage_events: queue.Queue[_StreamEvent | None] = queue.Queue()
            tracer = _StreamingTracer(
                "audit", stage_events, settings_, use_llm=llm_used, doc_id=body.doc_id
            )
            outcome: dict[str, object] = {}

            def progress_cb(done: int, total: int) -> None:
                stage_events.put(AuditProgress(done=done, total=total))

            def worker() -> None:
                try:
                    with _store() as store:
                        report, trace = run_audit(
                            store,
                            settings_,
                            model=model,
                            use_llm=llm_used,
                            focus_doc=body.doc_id,
                            tracer=tracer,
                            progress_cb=progress_cb,
                        )
                    outcome["report"], outcome["trace"] = report, trace
                except Exception as exc:  # surfaced to the client as an SSE error event
                    outcome["error"] = str(exc)
                finally:
                    stage_events.put(None)  # sentinel: no more events

            threading.Thread(target=worker, daemon=True).start()
            while (item := stage_events.get()) is not None:
                if isinstance(item, AuditProgress):
                    yield ServerSentEvent(event="progress", data=item.model_dump_json())
                else:
                    yield ServerSentEvent(event="stage", data=item.model_dump_json())

            if "error" in outcome:
                yield ServerSentEvent(event="error", data=str(outcome["error"]))
                return
            report = outcome["report"]
            trace = outcome["trace"]
            assert isinstance(report, AuditReport)  # narrow the untyped dict for mypy
            assert isinstance(trace, RunTrace)
            yield ServerSentEvent(
                event="report",
                data=AuditResponse.from_report(
                    report, llm_used, trace, doc_id=body.doc_id
                ).model_dump_json(),
            )

        return EventSourceResponse(events())

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
            stage_events: queue.Queue[_StreamEvent | None] = queue.Queue()
            tracer = _StreamingTracer("query", stage_events, settings_, question=body.question)
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
                assert isinstance(record, StepRecord)  # /query never emits progress
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
