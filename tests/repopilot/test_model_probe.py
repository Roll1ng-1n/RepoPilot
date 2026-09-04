from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from repopilot.model_probe import ModelProbe, ProbeReport


def _response(*, content: str | None, model: str, finish_reason: str, usage: Any, tool_calls: list[Any] | None = None, cost: float | None = None) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    response = SimpleNamespace(choices=[choice], model=model, usage=usage)
    if cost is not None:
        response._hidden_params = {"response_cost": cost}
    return response


class _FakeCompletions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.completions = _FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


def _tool_call(name: str = "report_probe", arguments: str = '{"result":"ok"}') -> Any:
    return SimpleNamespace(id="call-1", type="function", function=SimpleNamespace(name=name, arguments=arguments))


def test_probe_runs_text_and_required_native_tool_call_and_records_metrics() -> None:
    usage = SimpleNamespace(
        prompt_tokens=101,
        completion_tokens=23,
        total_tokens=124,
        prompt_tokens_details=SimpleNamespace(cached_tokens=17, cache_write_tokens=3),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=5),
    )
    client = _FakeClient(
        [
            _response(content="OK", model="served-luna", finish_reason="stop", usage=usage, cost=0.012),
            _response(
                content=None,
                model="served-luna",
                finish_reason="tool_calls",
                usage=usage,
                tool_calls=[_tool_call()],
                cost=0.02,
            ),
        ]
    )

    report = ModelProbe(client=client, api_key="secret-key", base_url="https://user:password@example.invalid/v1").run(
        ["gpt-5.6-luna"]
    )

    assert len(report.results) == 1
    result = report.results[0]
    assert result.model == "gpt-5.6-luna"
    assert result.passed is True
    assert result.text.valid is True
    assert result.text.response_model == "served-luna"
    assert result.text.finish_reason == "stop"
    assert result.text.usage == {
        "prompt": 101,
        "completion": 23,
        "total": 124,
        "cached": 17,
        "cache_write": 3,
        "reasoning": 5,
    }
    assert result.text.provider_cost_usd == 0.012
    assert result.text.openai_standard_estimate_usd == pytest.approx(0.00004549)
    assert result.tool_call.valid is True
    assert result.tool_call.tool_call_name == "report_probe"
    assert result.tool_call.finish_reason == "tool_calls"
    assert len(client.completions.calls) == 2
    assert "tools" not in client.completions.calls[0]
    assert client.completions.calls[0]["max_tokens"] == 16
    assert client.completions.calls[1]["tool_choice"] == "required"
    assert client.completions.calls[1]["tools"]
    assert client.completions.calls[1]["max_tokens"] == 64


def test_probe_continues_across_models_and_does_not_retry_errors() -> None:
    api_key = "secret-key"
    base_url = "https://user:password@example.invalid/v1"
    client = _FakeClient(
        [
            RuntimeError(f"request failed for {api_key} at {base_url}"),
            RuntimeError("tool request also failed"),
            _response(content="OK", model="served-terra", finish_reason="stop", usage=None),
            _response(content=None, model="served-terra", finish_reason="tool_calls", usage=None, tool_calls=[_tool_call()]),
        ]
    )

    report = ModelProbe(client=client, api_key=api_key, base_url=base_url).run(["gpt-5.6-sol", "gpt-5.6-terra"])

    assert [result.model for result in report.results] == ["gpt-5.6-sol", "gpt-5.6-terra"]
    assert report.results[0].passed is False
    assert report.results[0].text.error is not None
    assert api_key not in report.results[0].text.error
    assert base_url not in report.results[0].text.error
    assert report.results[1].passed is True
    assert len(client.completions.calls) == 4


def test_probe_report_writes_json_and_markdown_without_credentials(tmp_path) -> None:
    client = _FakeClient(
        [
            _response(content="OK", model="served", finish_reason="stop", usage=None),
            _response(content=None, model="served", finish_reason="tool_calls", usage=None, tool_calls=[_tool_call()]),
        ]
    )
    report: ProbeReport = ModelProbe(client=client, api_key="do-not-write").run(["gpt-5.5"])

    json_path = tmp_path / "probe.json"
    markdown_path = tmp_path / "probe.md"
    report.write_json(json_path)
    report.write_markdown(markdown_path)

    payload = json.loads(json_path.read_text())
    assert payload["results"][0]["passed"] is True
    assert payload["pricing_basis"]["as_of"] == "2026-09-04"
    assert payload["pricing_basis"]["tier"] == "standard"
    assert "do-not-write" not in json_path.read_text()
    assert "gpt-5.5" in markdown_path.read_text()
    assert "OpenAI Standard" in markdown_path.read_text()


def test_default_openai_client_is_configured_without_sdk_retries(monkeypatch) -> None:
    constructed: list[dict[str, Any]] = []

    class _OpenAI:
        def __init__(self, **kwargs: Any) -> None:
            constructed.append(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI))

    ModelProbe(api_key="key", base_url="https://example.invalid/v1")

    assert constructed == [
        {
            "api_key": "key",
            "base_url": "https://example.invalid/v1",
            "timeout": 60.0,
            "max_retries": 0,
        }
    ]
