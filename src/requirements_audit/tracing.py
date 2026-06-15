"""Run tracing — every agent stage is recorded, with LangFuse as an optional sink.

"Trace everything" (Project_plan principle #5) shouldn't depend on a running
LangFuse or the heavy eval extras being installed. So a `Tracer` always records
each stage (name, detail, latency) into an in-memory `RunTrace` you can inspect or
print — and *additionally* ships it to LangFuse when keys are configured and the
client is importable. Tracing failures never break a run.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel, Field

from requirements_audit.config import Settings


class StepRecord(BaseModel):
    name: str
    detail: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0


class RunTrace(BaseModel):
    name: str
    steps: list[StepRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.steps)


class Tracer:
    """Records stages for one run. Use `with tracer.step("retrieve", ...) as detail`."""

    def __init__(self, name: str, settings: Settings | None = None, **metadata: Any) -> None:
        self.trace = RunTrace(name=name, metadata=metadata)
        self._settings = settings

    @contextmanager
    def step(self, name: str, **detail: Any) -> Iterator[dict[str, Any]]:
        record = StepRecord(name=name, detail=dict(detail))
        start = time.perf_counter()
        try:
            yield record.detail
        finally:
            record.latency_ms = (time.perf_counter() - start) * 1000.0
            self.trace.steps.append(record)

    def finish(self, **outputs: Any) -> RunTrace:
        self.trace.metadata.update(outputs)
        if self._settings is not None and self._settings.tracing_enabled:
            _ship_to_langfuse(self.trace, self._settings)
        return self.trace


def _ship_to_langfuse(trace: RunTrace, settings: Settings) -> None:
    """Best-effort export. Any failure (missing client, network) is swallowed."""
    try:
        from langfuse import Langfuse

        client = Langfuse(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
        lf_trace = client.trace(name=trace.name, metadata=trace.metadata)
        for step in trace.steps:
            lf_trace.span(name=step.name, metadata=step.detail)
        client.flush()
    except Exception:  # pragma: no cover - tracing must never break a run
        pass
