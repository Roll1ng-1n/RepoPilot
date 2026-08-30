"""Read-only inspection of persisted RepoPilot Agent Runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import StrictUndefined, Template

from repopilot.artifacts import RunArtifacts

_ARTIFACT_NAMES = (
    "metadata.json",
    "checkpoint.json",
    "trace.jsonl",
    "plan.json",
    "patch.diff",
    "verification.json",
    "task_report.md",
)


@dataclass(frozen=True)
class RunInspection:
    """Normalized persisted state and Trace for one Agent Run."""

    run_id: str
    state_source: str
    state_path: Path
    artifact_directory: Path
    status: str | None
    task: str | None
    target_repository: str | None
    model: str | None
    plan: Any
    plan_history: Any
    budget: Any
    recovery: Any
    recoveries: Any
    context: Any
    approval_context: Any
    approval_request: Any
    verifications: Any
    git_commits: Any
    trace: list[dict[str, Any]]
    artifacts: dict[str, dict[str, Any]]
    task_report: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the stable, JSON-serializable inspection document."""

        return {
            "run_id": self.run_id,
            "status": self.status,
            "task": self.task,
            "target_repository": self.target_repository,
            "model": self.model,
            "plan": self.plan,
            "plan_history": self.plan_history,
            "budget": self.budget,
            "recovery": self.recovery,
            "recoveries": self.recoveries,
            "context": self.context,
            "approval_context": self.approval_context,
            "approval_request": self.approval_request,
            "verifications": self.verifications,
            "git_commits": self.git_commits,
            "trace": self.trace,
            "task_report": self.task_report,
            "state_source": self.state_source,
            "state_path": str(self.state_path),
            "artifact_directory": str(self.artifact_directory),
            "artifacts": self.artifacts,
        }


def load_run_inspection(state_directory: Path, run_id: str) -> RunInspection:
    """Load one persisted Agent Run without constructing Runtime dependencies."""

    artifacts = RunArtifacts.reopen(state_directory, run_id, secrets=[])
    metadata_path = artifacts.path / "metadata.json"
    checkpoint_path = artifacts.path / "checkpoint.json"
    if metadata_path.is_file():
        state = artifacts.read_metadata()
        state_source = "metadata"
        state_path = metadata_path
    elif checkpoint_path.is_file():
        state = artifacts.read_checkpoint()
        state_source = "checkpoint"
        state_path = checkpoint_path
    else:
        raise FileNotFoundError(f"Agent Run {run_id} has no Metadata or Checkpoint.")

    trace = artifacts.read_trace()
    return _build_inspection(
        artifacts.path,
        run_id,
        state_source,
        state_path,
        state,
        trace,
    )


def render_human(inspection: RunInspection) -> str:
    """Render an inspection in a compact human-readable format."""

    return _INSPECTION_TEMPLATE.render(
        inspection=inspection.to_dict(),
        json_value=lambda value: json.dumps(value, indent=2, sort_keys=True, default=str),
    ).strip() + "\n"


def _build_inspection(
    artifact_directory: Path,
    run_id: str,
    state_source: str,
    state_path: Path,
    state: dict[str, Any],
    trace: list[dict[str, Any]],
) -> RunInspection:
    task = _string_value(state.get("task")) or _trace_task(trace)
    target_repository = _target_repository(state)
    model = _model_name(state.get("model"))
    task_report_path = artifact_directory / "task_report.md"
    return RunInspection(
        run_id=run_id,
        state_source=state_source,
        state_path=state_path,
        artifact_directory=artifact_directory,
        status=_string_value(state.get("status")),
        task=task,
        target_repository=target_repository,
        model=model,
        plan=state.get("plan"),
        plan_history=state.get("plan_history", []),
        budget=state.get("budget", {}),
        recovery=state.get("recovery", {}),
        recoveries=state.get("recoveries", []),
        context=state.get("context", {}),
        approval_context=state.get("approval_context", {}),
        approval_request=state.get("approval_request"),
        verifications=state.get("verifications", []),
        git_commits=state.get("git_commits", []),
        trace=trace,
        artifacts=_artifact_inventory(artifact_directory),
        task_report=task_report_path.read_text() if task_report_path.is_file() else None,
    )


def _artifact_inventory(artifact_directory: Path) -> dict[str, dict[str, Any]]:
    return {
        name: {"path": str(artifact_directory / name), "available": (artifact_directory / name).is_file()}
        for name in _ARTIFACT_NAMES
    }


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _model_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _string_value(value.get("model_name"))
    return None


def _target_repository(state: dict[str, Any]) -> str | None:
    target_repository = _string_value(state.get("target_repository"))
    if target_repository is not None:
        return target_repository
    repository = state.get("repository")
    if isinstance(repository, dict):
        return _string_value(repository.get("resolved_target_repository"))
    return _string_value(repository)


def _trace_task(trace: list[dict[str, Any]]) -> str | None:
    for event in trace:
        if event.get("type") == "run_started":
            return _string_value(event.get("task"))
    return None


_INSPECTION_TEMPLATE = Template(
    """Agent Run Inspection

Run ID: {{ inspection.run_id }}
Status: {{ inspection.status or "unknown" }}
Task: {{ inspection.task or "unknown" }}
Target Repository: {{ inspection.target_repository or "unknown" }}
Model: {{ inspection.model or "unknown" }}
State Source: {{ inspection.state_source }} ({{ inspection.state_path }})
Artifact Directory: {{ inspection.artifact_directory }}

Plan:
{{ json_value(inspection.plan) }}

Plan History:
{{ json_value(inspection.plan_history) }}

Recovery:
{{ json_value({"state": inspection.recovery, "recoveries": inspection.recoveries}) }}

Context:
{{ json_value(inspection.context) }}

Approval:
{{ json_value({"context": inspection.approval_context, "request": inspection.approval_request}) }}

Task Verification:
{{ json_value(inspection.verifications) }}

Git:
{{ json_value(inspection.git_commits) }}

Budget:
{{ json_value(inspection.budget) }}

Trace ({{ inspection.trace | length }} events):
{% for event in inspection.trace %}- {{ json_value(event) }}
{% else %}- No Trace events.
{% endfor %}
Artifacts:
{% for name, artifact in inspection.artifacts.items() %}- {{ name }}: {{ "available" if artifact.available else "missing" }} ({{ artifact.path }})
{% endfor %}
Task Report ({{ inspection.artifacts["task_report.md"].path }}):
{{ inspection.task_report or "No task report is available." }}
""",
    undefined=StrictUndefined,
)
