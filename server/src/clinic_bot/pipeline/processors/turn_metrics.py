"""Per-session latency spans (SPEC 16.7), summarised as p50/p95 on disconnect."""

from __future__ import annotations

import statistics
import time
from collections import defaultdict

from pipecat.frames.frames import LLMContextFrame, LLMTextFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameProcessor


class TurnMetrics:
    """Collects spans in milliseconds. ``server_overhead`` excludes LLM time."""

    def __init__(self) -> None:
        self._spans: dict[str, list[float]] = defaultdict(list)
        self._turn_started: float | None = None
        self._classifier_done: float | None = None
        self._llm_wait_ms = 0.0
        self.classifier_first: list[bool] = []

    def record(self, span: str, ms: float) -> None:
        self._spans[span].append(ms)

    def user_turn(self) -> None:
        self._turn_started = time.perf_counter()
        self._classifier_done, self._llm_wait_ms = None, 0.0

    def classifier_done(self) -> None:
        self._classifier_done = time.perf_counter()

    def llm_wait(self, ms: float) -> None:
        self._llm_wait_ms += ms

    def first_text(self) -> None:
        if self._turn_started is None:
            return
        now = time.perf_counter()
        total = (now - self._turn_started) * 1000
        self.record("turn.first_text", total)
        self.record("server_overhead", max(total - self._llm_wait_ms, 0.0))
        self.classifier_first.append(
            self._classifier_done is not None and self._classifier_done <= now
        )
        self._turn_started = None

    def summary(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for span, values in self._spans.items():
            ordered = sorted(values)
            p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
            out[span] = {
                "n": len(values),
                "p50": round(statistics.median(ordered), 2),
                "p95": round(p95, 2),
            }
        if self.classifier_first:
            share = sum(self.classifier_first) / len(self.classifier_first)
            out["classifier_before_first_text"] = {
                "n": len(self.classifier_first),
                "share": round(share, 2),
            }
        return out


class TurnMetricsObserver(BaseObserver):
    """Measures time spent inside the main LLM (context in → first token out)."""

    def __init__(self, metrics: TurnMetrics, llm: FrameProcessor) -> None:
        super().__init__()
        self._turn_metrics, self._llm = metrics, llm
        self._context_sent: float | None = None

    async def on_push_frame(self, data: FramePushed) -> None:
        if not data.first_push:
            return
        if isinstance(data.frame, LLMContextFrame) and data.destination is self._llm:
            self._context_sent = time.perf_counter()
        elif (
            isinstance(data.frame, LLMTextFrame) and data.source is self._llm and self._context_sent
        ):
            ms = (time.perf_counter() - self._context_sent) * 1000
            self._turn_metrics.record("llm.first_token", ms)
            self._turn_metrics.llm_wait(ms)
            self._context_sent = None
