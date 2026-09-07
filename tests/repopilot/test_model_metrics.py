from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from typing import Any

from repopilot.artifacts import RunArtifacts
from repopilot.environment import LocalExecutionEnvironment
from repopilot.litellm_streaming import StreamingLitellmModel
from repopilot.model import AssistantTurn, LiteLLMToolCallingModel, ToolCall
from repopilot.plan import PlanHistory
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry


def _fake_response(*, usage: Any = None, response_cost: Any = None) -> Any:
    message = SimpleNamespace(content="done", tool_calls=[])
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)
    if response_cost is not None:
        response._hidden_params = {"response_cost": response_cost}
    return response


def test_litellm_model_passes_model_kwargs_and_normalizes_usage_and_cost(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    fake_litellm = SimpleNamespace(
        completion=lambda **kwargs: (
            calls.append(kwargs)
            or _fake_response(
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18), response_cost=0.031
            )
        ),
        cost_calculator=SimpleNamespace(completion_cost=lambda *_args, **_kwargs: 99.0),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    turn = LiteLLMToolCallingModel(model_name="test/model", model_kwargs={"temperature": 0}).complete([], [])

    assert calls[0]["temperature"] == 0
    assert turn.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
        "cached_tokens": None,
        "cache_write_tokens": None,
        "reasoning_tokens": None,
    }
    assert turn.cost == 0.031


def test_litellm_model_supports_input_output_tokens_and_missing_cost(monkeypatch) -> None:
    fake_litellm = SimpleNamespace(
        completion=lambda **_kwargs: _fake_response(
            usage=SimpleNamespace(input_tokens=13, output_tokens=5, total_tokens=18)
        ),
        cost_calculator=SimpleNamespace(completion_cost=lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError())),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    turn = LiteLLMToolCallingModel(model_name="test/model").complete([], [])

    assert turn.usage == {
        "prompt_tokens": 13,
        "completion_tokens": 5,
        "total_tokens": 18,
        "cached_tokens": None,
        "cache_write_tokens": None,
        "reasoning_tokens": None,
    }
    assert turn.cost is None


def test_litellm_model_preserves_nested_cache_and_reasoning_usage(monkeypatch) -> None:
    fake_litellm = SimpleNamespace(
        completion=lambda **_kwargs: _fake_response(
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details=SimpleNamespace(cached_tokens=17, cache_write_tokens=3),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=5),
            )
        ),
        cost_calculator=SimpleNamespace(completion_cost=lambda *_args, **_kwargs: 0.0),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    turn = LiteLLMToolCallingModel(model_name="test/model").complete([], [])

    assert turn.usage == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "cached_tokens": 17,
        "cache_write_tokens": 3,
        "reasoning_tokens": 5,
    }


def test_litellm_model_aggregates_streaming_chunks_when_force_stream(monkeypatch) -> None:
    from repopilot.model import stream_or_plain_completion

    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        # stream=true asks for an iterable of chunks; stream_chunk_builder
        # re-aggregates them into the usual ModelResponse shape.
        chunk = SimpleNamespace(usage=None)
        return iter([chunk])

    fake_litellm = SimpleNamespace(
        completion=fake_completion,
        stream_chunk_builder=lambda _chunks, **_kwargs: _fake_response(
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7), response_cost=0.01
        ),
        cost_calculator=SimpleNamespace(completion_cost=lambda *_args, **_kwargs: 99.0),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    # Explicit opt-in through the request options: stream is consumed from the
    # options and sent exactly once to litellm, with usage requested.
    request_options = {"model": "test/model", "messages": [], "tools": [], "stream": True}
    response = stream_or_plain_completion(fake_litellm, request_options)
    assert calls[0]["stream"] is True
    assert calls[0]["stream_options"] == {"include_usage": True}
    assert response.choices[0].message.content == "done"

    # force_stream drives streaming even when the options do not mention it.
    calls.clear()
    plain = stream_or_plain_completion(fake_litellm, {"model": "test/model", "messages": [], "tools": []}, force_stream=True)
    assert calls[0]["stream"] is True
    assert calls[0]["stream_options"] == {"include_usage": True}
    assert plain.choices[0].message.content == "done"

    # Without either flag, the plain non-streaming path is preserved.
    calls.clear()
    stream_or_plain_completion(fake_litellm, {"model": "test/model", "messages": [], "tools": []})
    assert "stream" not in calls[0]


def test_streaming_litellm_baseline_model_forces_stream(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        chunk = SimpleNamespace(usage=None)
        return iter([chunk])

    fake_litellm = SimpleNamespace(
        completion=fake_completion,
        stream_chunk_builder=lambda _chunks, **_kwargs: _fake_response(
            usage=SimpleNamespace(prompt_tokens=6, completion_tokens=1, total_tokens=7), response_cost=0.0
        ),
        exceptions=SimpleNamespace(AuthenticationError=RuntimeError),
        cost_calculator=SimpleNamespace(completion_cost=lambda *_args, **_kwargs: 0.0),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    model = StreamingLitellmModel(model_name="test/model", model_kwargs={"stream": True})
    response = model._query([])
    assert response.choices[0].message.content == "done"
    assert calls[0]["stream"] is True


def test_litellm_model_force_stream_from_model_kwargs(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        chunk = SimpleNamespace(usage=None)
        return iter([chunk])

    fake_litellm = SimpleNamespace(
        completion=fake_completion,
        stream_chunk_builder=lambda _chunks, **_kwargs: _fake_response(
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=3, total_tokens=11), response_cost=0.02
        ),
        cost_calculator=SimpleNamespace(completion_cost=lambda *_args, **_kwargs: 99.0),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    turn = LiteLLMToolCallingModel(model_name="test/model", model_kwargs={"stream": True}).complete([], [])
    assert calls[0]["stream"] is True
    assert turn.usage == {
        "prompt_tokens": 8,
        "completion_tokens": 3,
        "total_tokens": 11,
        "cached_tokens": None,
        "cache_write_tokens": None,
        "reasoning_tokens": None,
    }
    assert turn.cost == 0.02


def _make_repository(path) -> None:
    path.mkdir()
    (path / "README.md").write_text("metrics\n")
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=RepoPilot Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
        ],
        cwd=path,
        check=True,
    )


class _ScriptedModel:
    model_name = "metrics-model"

    def complete(self, _messages, _tools) -> AssistantTurn:
        return AssistantTurn(
            tool_calls=[ToolCall("finish", "finish_task", {"root_cause": "done", "changes": ["none"]})],
            usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            cost=0.004,
        )


class _FailingThenFinishingModel(_ScriptedModel):
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, tools) -> AssistantTurn:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("temporary model failure")
        return super().complete(messages, tools)


def test_runtime_persists_model_metrics_on_success(tmp_path) -> None:
    repository = tmp_path / "target"
    _make_repository(repository)
    environment = LocalExecutionEnvironment(repository)
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    plan_history = PlanHistory.for_task("Collect metrics")
    runtime = AgentRuntime(
        _ScriptedModel(),
        create_tool_registry(environment, repository, plan_history),
        artifacts,
        plan_history,
        sleeper=lambda _delay: None,
    )

    try:
        runtime.run("Collect metrics", repository)
    finally:
        environment.close()

    response = next(event for event in artifacts.read_trace() if event["type"] == "model_response")
    assert response["usage"] == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    assert response["cost_usd"] == 0.004
    assert isinstance(response["duration_seconds"], float)
    assert response["duration_seconds"] >= 0


def test_runtime_persists_duration_for_a_model_exception(tmp_path) -> None:
    repository = tmp_path / "target"
    _make_repository(repository)
    environment = LocalExecutionEnvironment(repository)
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    plan_history = PlanHistory.for_task("Collect metrics")
    runtime = AgentRuntime(
        _FailingThenFinishingModel(),
        create_tool_registry(environment, repository, plan_history),
        artifacts,
        plan_history,
        sleeper=lambda _delay: None,
    )

    try:
        runtime.run("Collect metrics", repository)
    finally:
        environment.close()

    error_response = next(
        event for event in artifacts.read_trace() if event["type"] == "model_response" and "error" in event
    )
    assert error_response["error"] == "temporary model failure"
    assert error_response["usage"] is None
    assert error_response["cost_usd"] is None
    assert isinstance(error_response["duration_seconds"], float)
    assert error_response["duration_seconds"] >= 0
