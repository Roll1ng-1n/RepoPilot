"""One deadline, trace and accounting boundary for all model requests."""

from __future__ import annotations

import json
import math
import signal
import threading
import time
from contextlib import contextmanager

from repopilot.budget import BudgetExceeded
from repopilot.model import LiteLLMToolCallingModel, stream_chunk_record


class _DeadlineExpired(BaseException):
    """Bypass provider retry handlers so a deadline cannot restart a request."""


@contextmanager
def request_deadline(seconds):
    if not math.isfinite(seconds):
        yield
        return
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        raise ValueError("Bounded model requests require a POSIX main-thread runtime.")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def expired(signum, frame):
        raise _DeadlineExpired()

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(seconds, previous_timer[0]) if previous_timer[0] else seconds)
    try:
        yield
    except _DeadlineExpired as error:
        raise BudgetExceeded("run_time") from error
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(
                signal.ITIMER_REAL, max(0.000001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1]
            )


class RequestExecutor:
    def __init__(self, model, budget, artifacts, *, purpose="main"):
        self.model = model
        self.model_name = model.model_name
        self.budget = budget
        self.artifacts = artifacts
        self.purpose = purpose
        self.context_window_tokens = 32768
        self.output_reserve_tokens = 4096

    def for_summary(self):
        child = RequestExecutor(self.model, self.budget, self.artifacts, purpose="summary")
        child.context_window_tokens = self.context_window_tokens
        child.output_reserve_tokens = self.output_reserve_tokens
        return child

    def complete(self, messages, tools):
        size = len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False).encode())
        if size + self.output_reserve_tokens + 1024 > self.context_window_tokens:
            raise BudgetExceeded("context_window")
        self.budget.before_request()
        remaining = self.budget.remaining_seconds()
        started = time.monotonic()
        self.artifacts.append_trace(
            "model_request",
            model=self.model_name,
            purpose=self.purpose,
            step=self.budget.steps_used,
            message_count=len(messages),
        )
        turn = None
        error_name = None
        stream_artifact = None
        previous_observer = None
        if isinstance(self.model, LiteLLMToolCallingModel):
            previous_observer = self.model.stream_observer

            def observe(sequence, chunk):
                nonlocal stream_artifact
                stream_artifact = f"model-stream-{self.budget.requests_used + 1:04d}.jsonl"
                self.artifacts.append_jsonl(stream_artifact, stream_chunk_record(sequence, chunk))

            self.model.stream_observer = observe
        try:
            with request_deadline(remaining):
                if isinstance(self.model, LiteLLMToolCallingModel):
                    turn = self.model.complete(
                        messages, tools, timeout_seconds=remaining if math.isfinite(remaining) else None
                    )
                else:
                    turn = self.model.complete(messages, tools)
            return turn
        except BaseException as error:
            error_name = str(error) or type(error).__name__
            raise
        finally:
            if isinstance(self.model, LiteLLMToolCallingModel):
                self.model.stream_observer = previous_observer
            usage = getattr(turn, "usage", None)
            cost = getattr(turn, "cost", None)
            self.budget.record_request(usage, cost)
            self.artifacts.append_trace(
                "model_response",
                model=self.model_name,
                purpose=self.purpose,
                content=getattr(turn, "content", None),
                error=error_name,
                usage=usage,
                cost_usd=cost,
                finish_reason=getattr(turn, "finish_reason", None),
                stream_artifact=stream_artifact,
                duration_seconds=time.monotonic() - started,
                tool_calls=[
                    {
                        "id": c.id,
                        "name": c.name,
                        "arguments": c.arguments,
                        "protocol_error": c.protocol_error,
                        "raw_arguments": c.raw_arguments,
                    }
                    for c in getattr(turn, "tool_calls", [])
                ],
            )
