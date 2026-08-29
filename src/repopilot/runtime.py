"""A thin native Tool Calling runtime for one Local Agent Run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repopilot.artifacts import RunArtifacts
from repopilot.model import ToolCallingModel
from repopilot.plan import Plan, PlanHistory
from repopilot.tools import ToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    status: str
    artifact_directory: Path
    plan: Plan


class AgentRuntime:
    """Drives a model and Tool Registry without knowing an Environment implementation."""

    def __init__(
        self, model: ToolCallingModel, registry: ToolRegistry, artifacts: RunArtifacts, plan_history: PlanHistory
    ):
        self._model = model
        self._registry = registry
        self._artifacts = artifacts
        self._plan_history = plan_history

    def run(self, task: str, target_repository: Path) -> AgentRunResult:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "Use the provided native tools to inspect the Target Repository. Do not emit text actions. "
                    "Use the Agent Control Tools to update the explicit Plan, Replan when new facts change the "
                    "unfinished work, and request task completion with finish_task. Current Plan: "
                    f"{json.dumps(self._plan_history.current.to_dict(), sort_keys=True)}"
                ),
            },
            {"role": "user", "content": task},
        ]
        self._artifacts.append_trace(
            "run_started", task=task, target_repository=str(target_repository.resolve()), model=self._model.model_name
        )
        self._artifacts.append_trace("plan_created", plan=self._plan_history.current.to_dict())
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
                if observation.get("ok") and tool_call.name in {"update_plan", "replan"}:
                    event_type = "plan_replanned" if tool_call.name == "replan" else "plan_updated"
                    self._artifacts.append_trace(event_type, **observation["result"])
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(observation, sort_keys=True)}
                )
                if tool_call.name == "finish_task" and observation.get("ok"):
                    status = observation["result"]["status"]
                    self._write_terminal_artifacts(observation["result"])
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
                "plan": self._plan_history.current.to_dict(),
                "plan_history": [plan.to_dict() for plan in self._plan_history.versions],
            }
        )
        return AgentRunResult(self._artifacts.run_id, status, self._artifacts.path, self._plan_history.current)

    def _write_terminal_artifacts(self, completion: dict[str, Any]) -> None:
        self._artifacts.write_text("patch.diff", completion["final_patch"])
        self._artifacts.write_json("verification.json", {"verifications": completion["verifications"]})
        report = completion["report"]
        self._artifacts.write_text(
            "task_report.md",
            self._format_task_report(report, completion["verifications"]),
        )

    @staticmethod
    def _format_task_report(report: dict[str, Any], verifications: list[dict[str, Any]]) -> str:
        verification_lines = [
            f"- `{item['scope']}`: {item['reason']} ({'passed' if item['result']['exit_code'] == 0 else 'failed'})"
            for item in verifications
        ] or ["- No Task Verification was run."]
        risk_lines = [f"- {risk}" for risk in report["risks"]] or ["- No risks reported."]
        return "\n".join(
            [
                "# Task report",
                "",
                "## Root cause",
                "",
                report["root_cause"],
                "",
                "## Changes",
                "",
                *(f"- {change}" for change in report["changes"]),
                "",
                "## Verification",
                "",
                *verification_lines,
                "",
                "## Risks",
                "",
                *risk_lines,
                "",
            ]
        )

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
