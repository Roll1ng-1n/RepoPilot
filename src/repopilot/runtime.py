"""A thin native Tool Calling runtime for one Local Agent Run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repopilot.artifacts import RunArtifacts
from repopilot.model import ToolCallingModel
from repopilot.tools import ToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    status: str
    artifact_directory: Path


class AgentRuntime:
    """Drives a model and Tool Registry without knowing an Environment implementation."""

    def __init__(self, model: ToolCallingModel, registry: ToolRegistry, artifacts: RunArtifacts):
        self._model = model
        self._registry = registry
        self._artifacts = artifacts

    def run(self, task: str, target_repository: Path) -> AgentRunResult:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "Use the provided native tools to inspect the Target Repository. Do not emit text actions.",
            },
            {"role": "user", "content": task},
        ]
        self._artifacts.append_trace(
            "run_started", task=task, target_repository=str(target_repository.resolve()), model=self._model.model_name
        )
        status = "FAILED"
        while True:
            turn = self._model.complete(messages, self._registry.schemas)
            if not turn.tool_calls:
                self._artifacts.append_trace("model_response", content=turn.content or "")
                break
            messages.append(self._assistant_message(turn))
            should_finish = False
            for tool_call in turn.tool_calls:
                self._artifacts.append_trace(
                    "tool_call", tool_call_id=tool_call.id, tool_name=tool_call.name, arguments=tool_call.arguments
                )
                observation = self._registry.dispatch(tool_call)
                self._artifacts.append_trace(
                    "tool_result", tool_call_id=tool_call.id, tool_name=tool_call.name, observation=observation
                )
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(observation, sort_keys=True)}
                )
                if tool_call.name == "finish_task" and observation.get("ok"):
                    status = observation["result"]["status"]
                    should_finish = True
            if should_finish:
                break
        self._artifacts.append_trace("run_finished", status=status)
        self._artifacts.write_metadata(
            {
                "run_id": self._artifacts.run_id,
                "status": status,
                "target_repository": str(target_repository.resolve()),
                "model": self._model.model_name,
            }
        )
        return AgentRunResult(self._artifacts.run_id, status, self._artifacts.path)

    @staticmethod
    def _assistant_message(turn: Any) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": turn.content,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": tool_call.name, "arguments": json.dumps(tool_call.arguments, sort_keys=True)},
                }
                for tool_call in turn.tool_calls
            ],
        }
