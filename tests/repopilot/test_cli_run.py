import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repopilot.artifacts import RunArtifacts
from repopilot.cli import create_app
from repopilot.environment import (
    Command,
    CommandResult,
    EnvironmentCreationError,
    EnvironmentRequest,
    ExecutionEnvironment,
    LocalExecutionEnvironment,
)
from repopilot.model import AssistantTurn, ToolCall


class ScriptedToolCallingModel:
    """A model-boundary fake for a complete CLI Agent Run."""

    model_name = "scripted-tool-calling-model"

    def __init__(self, turns: list[AssistantTurn]):
        self._turns = iter(turns)
        self.requests: list[tuple[list[dict], list[dict]]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        self.requests.append((messages, tools))
        return next(self._turns)


class TransientThenFinishModel:
    """A model fake that makes one retryable error before returning a Tool Call."""

    model_name = "transient-then-finish-model"

    def __init__(self) -> None:
        self.requests: list[tuple[list[dict], list[dict]]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        self.requests.append((messages, tools))
        if len(self.requests) == 1:
            raise TimeoutError("provider request timed out")
        return AssistantTurn(
            tool_calls=[
                ToolCall(
                    "call-1",
                    "finish_task",
                    {
                        "root_cause": "The provider recovered after a timeout.",
                        "changes": ["No repository changes were needed."],
                    },
                )
            ]
        )


class NonTransientFailingModel:
    """A model fake for an unrecoverable provider failure."""

    model_name = "non-transient-failing-model"

    def __init__(self) -> None:
        self.requests: list[tuple[list[dict], list[dict]]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        self.requests.append((messages, tools))
        raise ValueError("the provider rejected the request")


def _make_target_repository(path: Path) -> None:
    path.mkdir()
    (path / "README.md").write_text("RepoPilot needle\n")
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=RepoPilot Runtime Test",
            "-c",
            "user.email=runtime-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Initial Target Repository state",
        ],
        cwd=path,
        check=True,
    )


def test_cli_stops_at_the_replan_budget_after_consecutive_invalid_tool_calls(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "unknown_tool", {})]),
            AssistantTurn(tool_calls=[ToolCall("call-2", "unknown_tool", {})]),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Make a bounded recovery decision.",
            "--state-dir",
            str(state_directory),
            "--max-consecutive-failures",
            "2",
            "--max-replans",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "BUDGET_EXCEEDED" in result.output
    assert len(model.requests) == 2

    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]

    assert metadata["status"] == "BUDGET_EXCEEDED"
    assert [failure["category"] for failure in metadata["failures"]] == ["TOOL_ERROR", "TOOL_ERROR"]
    assert metadata["recoveries"][-1]["action"] == "REPLAN"
    assert metadata["budget"]["max_replans"] == 0
    assert metadata["budget"]["replans_used"] == 0
    assert any(event["type"] == "failure" and event["category"] == "TOOL_ERROR" for event in events)
    assert any(event["type"] == "recovery" and event["action"] == "REPLAN" for event in events)
    assert any(event["type"] == "budget_exhausted" and event["limit"] == "replans" for event in events)


def test_cli_resets_consecutive_failures_after_a_recovery_replan(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "unknown_tool", {})]),
            AssistantTurn(tool_calls=[ToolCall("call-2", "unknown_tool", {})]),
            AssistantTurn(tool_calls=[ToolCall("call-3", "unknown_tool", {})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-4",
                        "finish_task",
                        {
                            "root_cause": "The new Plan reset the recovery attempt.",
                            "changes": ["No change was needed."],
                        },
                    )
                ]
            ),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Recover once, then handle a separate failure.",
            "--state-dir",
            str(state_directory),
            "--max-consecutive-failures",
            "2",
            "--max-replans",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "UNVERIFIED" in result.output
    assert len(model.requests) == 4
    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())

    assert [recovery["action"] for recovery in metadata["recoveries"]] == [
        "RETURN_OBSERVATION",
        "REPLAN",
        "RETURN_OBSERVATION",
    ]
    assert metadata["budget"]["replans_used"] == 1


def test_cli_persists_every_configured_run_budget_limit(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "finish_task",
                        {"root_cause": "The budget was inspected.", "changes": ["No change was needed."]},
                    )
                ]
            )
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Expose the configured budget.",
            "--state-dir",
            str(state_directory),
            "--max-steps",
            "7",
            "--max-replans",
            "5",
            "--max-consecutive-failures",
            "4",
            "--command-timeout-seconds",
            "123",
            "--max-run-seconds",
            "456",
        ],
    )

    assert result.exit_code == 0, result.output
    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())

    assert metadata["budget"] == {
        "max_steps": 7,
        "steps_used": 1,
        "max_replans": 5,
        "replans_used": 0,
        "max_consecutive_failures": 4,
        "command_timeout_seconds": 123.0,
        "max_run_seconds": 456.0,
    }


def test_cli_returns_a_failed_task_verification_as_a_debug_observation_without_rerunning_it(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "verify_task",
                        {
                            "command": "exit 7",
                            "scope": "focused check",
                            "reason": "Shows the current implementation still fails.",
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-2",
                        "finish_task",
                        {
                            "root_cause": "The focused check failed.",
                            "changes": ["No change was made."],
                        },
                    )
                ]
            ),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        ["run", str(target_repository), "--task", "Debug the failed check.", "--state-dir", str(state_directory)],
    )

    assert result.exit_code == 0, result.output
    assert "UNVERIFIED" in result.output
    assert len(model.requests) == 2
    assert any(message["role"] == "tool" and '"exit_code": 7' in message["content"] for message in model.requests[1][0])
    assert any(
        message["role"] == "user" and "Recovery Observation (VERIFICATION_FAILURE)" in message["content"]
        for message in model.requests[1][0]
    )

    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())
    verification = json.loads((run_directory / "verification.json").read_text())

    assert metadata["failures"] == [
        {
            "category": "VERIFICATION_FAILURE",
            "reason": "Task Verification exited with 7.",
            "tool_name": "verify_task",
        }
    ]
    assert metadata["recoveries"][0]["action"] == "DEBUG_OBSERVATION"
    assert [item["command"] for item in verification["verifications"]] == ["exit 7"]


def test_cli_uses_exponential_retry_recovery_for_a_transient_model_error(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = TransientThenFinishModel()
    retry_delays: list[float] = []

    result = CliRunner().invoke(
        create_app(lambda _: model, sleeper=retry_delays.append),
        [
            "run",
            str(target_repository),
            "--task",
            "Recover from a provider timeout.",
            "--state-dir",
            str(state_directory),
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(model.requests) == 2
    assert retry_delays == [0.25]
    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())

    assert metadata["status"] == "UNVERIFIED"
    assert metadata["failures"][0]["category"] == "MODEL_ERROR"
    assert metadata["recoveries"][0] == {
        "action": "RETRY_MODEL",
        "category": "MODEL_ERROR",
        "reason": "Retrying a transient model error after 0.25 seconds: provider request timed out",
        "retry_delay_seconds": 0.25,
    }


def test_cli_stops_as_failed_after_a_non_transient_model_error(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = NonTransientFailingModel()

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Handle a rejected provider request.",
            "--state-dir",
            str(state_directory),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "FAILED" in result.output
    assert len(model.requests) == 1
    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())

    assert metadata["status"] == "FAILED"
    assert metadata["failures"][0]["category"] == "MODEL_ERROR"
    assert metadata["recoveries"][0]["action"] == "STOP"


def test_cli_keeps_an_ordinary_nonzero_command_as_a_tool_observation(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "run_command", {"command": "exit 4"})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-2",
                        "finish_task",
                        {"root_cause": "The command result was inspected.", "changes": ["No change was needed."]},
                    )
                ]
            ),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        ["run", str(target_repository), "--task", "Inspect a failing command.", "--state-dir", str(state_directory)],
    )

    assert result.exit_code == 0, result.output
    assert len(model.requests) == 2
    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())

    assert metadata["failures"] == []
    assert metadata["recoveries"] == []


def test_cli_replans_after_a_repeated_tool_call_and_observation(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "list_files", {"path": "."})]),
            AssistantTurn(tool_calls=[ToolCall("call-2", "list_files", {"path": "."})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-3",
                        "finish_task",
                        {"root_cause": "A revised plan was made.", "changes": ["No change was needed."]},
                    )
                ]
            ),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Avoid repeating inspection without progress.",
            "--state-dir",
            str(state_directory),
            "--max-consecutive-failures",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(model.requests) == 3
    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())

    assert metadata["failures"][0]["category"] == "NO_PROGRESS"
    assert metadata["recoveries"][0]["action"] == "REPLAN"
    assert metadata["budget"]["replans_used"] == 1
    assert metadata["plan"]["version"] == 2


def _docker_available() -> bool:
    executable = shutil.which("docker")
    if executable is None:
        return False
    try:
        subprocess.run([executable, "version"], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


@pytest.mark.parametrize(
    ("environment", "environment_arguments"),
    [
        ("local", []),
        pytest.param(
            "docker",
            ["--image", os.environ.get("REPOPILOT_DOCKER_TEST_IMAGE", "python:3.12-bookworm")],
            marks=pytest.mark.skipif(not _docker_available(), reason="Docker is unavailable"),
        ),
    ],
)
def test_cli_completes_a_verified_patch_run_and_persists_its_evidence(
    tmp_path: Path, environment: str, environment_arguments: list[str]
) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    patch = """\\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-RepoPilot needle
+RepoPilot verified change
"""
    verification_command = (
        "python -c \"from pathlib import Path; assert Path('README.md').read_text() == 'RepoPilot verified change\\n'\""
    )
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "apply_patch", {"patch": patch})]),
            AssistantTurn(tool_calls=[ToolCall("call-2", "view_diff", {})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-3",
                        "verify_task",
                        {
                            "command": verification_command,
                            "scope": "README.md patch",
                            "reason": "Proves the requested repository change is present.",
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-4",
                        "finish_task",
                        {
                            "root_cause": "The README still contained the obsolete text.",
                            "changes": ["Replaced the obsolete README text."],
                            "risks": ["No runtime behavior changed."],
                        },
                    )
                ]
            ),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Replace the obsolete README text and verify it.",
            "--state-dir",
            str(state_directory),
            "--environment",
            environment,
            *environment_arguments,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "SUCCEEDED" in result.output
    if environment == "local":
        assert "Local Environment executes commands directly in the Target Repository." in result.output
    else:
        assert "not a security boundary" in result.output
    assert (target_repository / "README.md").read_text() == "RepoPilot verified change\n"

    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
    verification = json.loads((run_directory / "verification.json").read_text())
    report = (run_directory / "task_report.md").read_text()

    assert metadata["status"] == "SUCCEEDED"
    assert "-RepoPilot needle" in (run_directory / "patch.diff").read_text()
    assert verification["verifications"][0]["command"] == verification_command
    assert verification["verifications"][0]["scope"] == "README.md patch"
    assert verification["verifications"][0]["reason"] == "Proves the requested repository change is present."
    assert verification["verifications"][0]["result"]["exit_code"] == 0
    assert "## Root cause\n\nThe README still contained the obsolete text." in report
    assert "## Changes\n\n- Replaced the obsolete README text." in report
    assert (
        "## Verification\n\n- `README.md patch`: Proves the requested repository change is present. (passed)" in report
    )
    assert "## Risks\n\n- No runtime behavior changed." in report
    assert [event["type"] for event in events] == [
        "run_started",
        "plan_created",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "run_finished",
    ]
    assert [event["tool_name"] for event in events if event["type"] == "tool_call"] == [
        "apply_patch",
        "view_diff",
        "verify_task",
        "finish_task",
    ]
    assert events[2]["arguments"]["patch"] == patch
    assert events[3]["observation"]["result"]["applied"] is True
    assert "-RepoPilot needle" in events[5]["observation"]["result"]["patch"]
    assert {schema["function"]["name"] for schema in model.requests[0][1]} >= {
        "apply_patch",
        "view_diff",
        "verify_task",
        "finish_task",
    }


def test_cli_resumes_a_stopped_run_in_a_new_environment_without_reapplying_the_patch(tmp_path: Path) -> None:
    """A stopped Agent Run resumes its full context but never restores its old Environment."""

    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    patch = """\\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-RepoPilot needle
+RepoPilot checkpointed change
"""
    verification_command = (
        "python -c \"from pathlib import Path; assert Path('README.md').read_text() == "
        "'RepoPilot checkpointed change\\n'\""
    )

    class InterruptAfterPatchModel:
        model_name = "interrupt-after-patch"

        def __init__(self) -> None:
            self.requests: list[tuple[list[dict], list[dict]]] = []

        def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
            self.requests.append((messages, tools))
            if len(self.requests) == 1:
                return AssistantTurn(tool_calls=[ToolCall("apply", "apply_patch", {"patch": patch})])
            raise KeyboardInterrupt()

    class ResumeModel:
        model_name = "resume-model"

        def __init__(self) -> None:
            self.requests: list[tuple[list[dict], list[dict]]] = []

        def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
            self.requests.append((messages, tools))
            turns = [
                AssistantTurn(tool_calls=[ToolCall("diff", "view_diff", {})]),
                AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            "verify",
                            "verify_task",
                            {
                                "command": verification_command,
                                "scope": "README checkpointed patch",
                                "reason": "Proves the side effect from before Ctrl+C is still present.",
                            },
                        )
                    ]
                ),
                AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            "finish",
                            "finish_task",
                            {
                                "root_cause": "The task was interrupted after applying its patch.",
                                "changes": ["Kept the one already-applied README change."],
                            },
                        )
                    ]
                ),
            ]
            return turns[len(self.requests) - 1]

    class RecordingEnvironment:
        def __init__(self) -> None:
            self.closed = False

        def execute(self, command: Command) -> CommandResult:
            return LocalExecutionEnvironment(target_repository).execute(command)

        def close(self) -> None:
            self.closed = True

    first_model = InterruptAfterPatchModel()
    first_environments: list[RecordingEnvironment] = []

    def first_environment_factory(_request: EnvironmentRequest) -> RecordingEnvironment:
        environment = RecordingEnvironment()
        first_environments.append(environment)
        return environment

    stopped = CliRunner().invoke(
        create_app(lambda _: first_model, first_environment_factory),
        [
            "run",
            str(target_repository),
            "--task",
            "Change the README once, then verify it.",
            "--state-dir",
            str(state_directory),
            "--api-key",
            "test-api-key",
        ],
    )

    assert stopped.exit_code == 0, stopped.output
    assert "STOPPED" in stopped.output
    assert first_environments[0].closed is True
    run_directory = next(state_directory.iterdir())
    checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    assert checkpoint["status"] == "STOPPED"
    assert checkpoint["task"] == "Change the README once, then verify it."
    assert checkpoint["budget"]["steps_used"] == 2
    assert checkpoint["tool_results"][0]["tool_name"] == "apply_patch"
    assert checkpoint["repository"]["resolved_target_repository"] == str(target_repository.resolve())
    assert checkpoint["environment"] == {"backend": "local", "image": None}
    assert "test-api-key" not in json.dumps(checkpoint)
    assert (target_repository / "README.md").read_text() == "RepoPilot checkpointed change\n"

    resumed_model = ResumeModel()
    resumed_environments: list[RecordingEnvironment] = []

    def resumed_environment_factory(_request: EnvironmentRequest) -> RecordingEnvironment:
        environment = RecordingEnvironment()
        resumed_environments.append(environment)
        return environment

    resumed = CliRunner().invoke(
        create_app(lambda _: resumed_model, resumed_environment_factory),
        ["resume", run_directory.name, "--state-dir", str(state_directory)],
    )

    assert resumed.exit_code == 0, resumed.output
    assert "SUCCEEDED" in resumed.output
    assert resumed_environments[0].closed is True
    assert len(resumed_model.requests) == 3
    assert any(
        message["role"] == "tool" and message["tool_call_id"] == "apply" for message in resumed_model.requests[0][0]
    )
    assert (target_repository / "README.md").read_text() == "RepoPilot checkpointed change\n"

    metadata = json.loads((run_directory / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
    checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    assert metadata["status"] == "SUCCEEDED"
    assert [
        item["scope"] for item in json.loads((run_directory / "verification.json").read_text())["verifications"]
    ] == ["README checkpointed patch"]
    assert checkpoint["status"] == "SUCCEEDED"
    assert checkpoint["verifications"][0]["command"] == verification_command
    assert [event["type"] for event in events if event["type"] in {"run_stopped", "run_resumed"}] == [
        "run_stopped",
        "run_resumed",
    ]


def test_cli_resume_rejects_a_target_repository_changed_after_its_checkpoint(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"

    class InterruptModel:
        model_name = "interrupt-model"

        def complete(self, _messages: list[dict], _tools: list[dict]) -> AssistantTurn:
            raise KeyboardInterrupt()

    class NoCallsModel:
        model_name = "must-not-run"

        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _messages: list[dict], _tools: list[dict]) -> AssistantTurn:
            self.calls += 1
            raise AssertionError("The model must not run after repository validation fails.")

    class RecordingEnvironment:
        def __init__(self) -> None:
            self.closed = False

        def execute(self, _command: Command) -> CommandResult:
            raise AssertionError("No Tool Call should occur before repository validation.")

        def close(self) -> None:
            self.closed = True

    stopped = CliRunner().invoke(
        create_app(lambda _: InterruptModel(), lambda _: RecordingEnvironment()),
        [
            "run",
            str(target_repository),
            "--task",
            "Do not run after the repository changes.",
            "--state-dir",
            str(state_directory),
        ],
    )
    assert stopped.exit_code == 0, stopped.output
    run_directory = next(state_directory.iterdir())
    (target_repository / "README.md").write_text("Changed after checkpoint\n")

    model = NoCallsModel()
    environments: list[RecordingEnvironment] = []

    def environment_factory(_request: EnvironmentRequest) -> RecordingEnvironment:
        environment = RecordingEnvironment()
        environments.append(environment)
        return environment

    resumed = CliRunner().invoke(
        create_app(lambda _: model, environment_factory),
        ["resume", run_directory.name, "--state-dir", str(state_directory)],
    )

    assert resumed.exit_code == 1
    assert "Target Repository changed since the Checkpoint" in resumed.output
    assert model.calls == 0
    assert environments[0].closed is True


@pytest.mark.parametrize("status", ["RUNNING", "SUCCEEDED", "UNVERIFIED", "FAILED", "BUDGET_EXCEEDED"])
def test_cli_resume_rejects_runs_that_are_not_stopped_or_waiting_for_approval(tmp_path: Path, status: str) -> None:
    artifacts = RunArtifacts(tmp_path / "agent-runs", secrets=[])
    artifacts.write_checkpoint({"run_id": artifacts.run_id, "status": status})

    result = CliRunner().invoke(
        create_app(lambda _: (_ for _ in ()).throw(AssertionError("Model factory must not run."))),
        ["resume", artifacts.run_id, "--state-dir", str(tmp_path / "agent-runs")],
    )

    assert result.exit_code == 1
    assert f"cannot resume from '{status}'" in result.output


def test_cli_resume_keeps_a_waiting_run_waiting_for_human_approval(tmp_path: Path) -> None:
    artifacts = RunArtifacts(tmp_path / "agent-runs", secrets=[])
    artifacts.write_checkpoint({"run_id": artifacts.run_id, "status": "WAITING_FOR_APPROVAL"})

    result = CliRunner().invoke(
        create_app(lambda _: (_ for _ in ()).throw(AssertionError("Model factory must not run."))),
        ["resume", artifacts.run_id, "--state-dir", str(tmp_path / "agent-runs")],
    )

    assert result.exit_code == 0, result.output
    assert "still waiting for Human Approval" in result.output


def test_cli_selects_an_environment_through_the_factory(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    requests: list[EnvironmentRequest] = []

    class RecordingEnvironment:
        closed = False

        def execute(self, _command: Command) -> CommandResult:
            return CommandResult(0, "", "", 0.0, False)

        def close(self) -> None:
            self.closed = True

    environment = RecordingEnvironment()
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "finish_task",
                        {
                            "root_cause": "No changes were needed.",
                            "changes": ["No repository changes were made."],
                            "risks": ["No verification evidence was collected."],
                        },
                    )
                ]
            )
        ]
    )

    def environment_factory(request: EnvironmentRequest) -> RecordingEnvironment:
        requests.append(request)
        return environment

    result = CliRunner().invoke(
        create_app(lambda _: model, environment_factory),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the repository.",
            "--state-dir",
            str(tmp_path / "agent-runs"),
            "--environment",
            "docker",
            "--image",
            "repo-image",
        ],
    )

    assert result.exit_code == 0, result.output
    assert requests == [
        EnvironmentRequest(target_repository=target_repository.resolve(), environment="docker", image="repo-image")
    ]
    assert environment.closed is True


def test_cli_rejects_docker_without_an_image(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    model = ScriptedToolCallingModel([])

    result = CliRunner().invoke(
        create_app(lambda _: model),
        ["run", str(target_repository), "--task", "Inspect the repository.", "--environment", "docker"],
    )

    assert result.exit_code == 2
    assert "requires an image" in result.output


def test_cli_reports_an_unavailable_docker_environment_without_falling_back_to_local(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    model = ScriptedToolCallingModel([])

    def unavailable_environment(_request: EnvironmentRequest) -> ExecutionEnvironment:
        raise EnvironmentCreationError("Unable to start Docker Environment: docker is unavailable")

    result = CliRunner().invoke(
        create_app(lambda _: model, unavailable_environment),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the repository.",
            "--environment",
            "docker",
            "--image",
            "repo-image",
        ],
    )

    assert result.exit_code == 1
    assert "docker is unavailable" in result.output
    assert "Local Environment executes commands" not in result.output


def test_cli_runs_a_read_only_native_tool_calling_agent_and_writes_safe_artifacts(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    before_status = subprocess.run(
        ["git", "status", "--short"], cwd=target_repository, capture_output=True, check=True, text=True
    ).stdout
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "list_files", {"path": "."})]),
            AssistantTurn(tool_calls=[ToolCall("call-2", "search_code", {"query": "needle", "path": "."})]),
            AssistantTurn(tool_calls=[ToolCall("call-3", "read_file", {"path": "README.md"})]),
            AssistantTurn(tool_calls=[ToolCall("call-4", "run_command", {"command": "git status --short"})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-5",
                        "finish_task",
                        {
                            "root_cause": "The task was exploration only.",
                            "changes": ["No repository changes were needed."],
                            "risks": ["No verification evidence was collected."],
                        },
                    )
                ]
            ),
        ]
    )
    app = create_app(lambda _: model)

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(target_repository),
            "--task",
            "Explore this repository without modifying it.",
            "--state-dir",
            str(state_directory),
            "--api-key",
            "test-api-key",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Local Environment executes commands directly in the Target Repository." in result.output
    assert "UNVERIFIED" in result.output
    assert (
        subprocess.run(
            ["git", "status", "--short"], cwd=target_repository, capture_output=True, check=True, text=True
        ).stdout
        == before_status
    )
    assert not (target_repository / ".repopilot").exists()

    run_directories = list(state_directory.iterdir())
    assert len(run_directories) == 1
    metadata = json.loads((run_directories[0] / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directories[0] / "trace.jsonl").read_text().splitlines()]
    persisted_artifacts = json.dumps({"metadata": metadata, "events": events})

    assert metadata["status"] == "UNVERIFIED"
    assert (run_directories[0] / "patch.diff").read_text() == ""
    assert json.loads((run_directories[0] / "verification.json").read_text()) == {"verifications": []}
    assert "No verification evidence was collected." in (run_directories[0] / "task_report.md").read_text()
    assert [event["type"] for event in events] == [
        "run_started",
        "plan_created",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "run_finished",
    ]
    assert "test-api-key" not in persisted_artifacts
    assert {schema["function"]["name"] for schema in model.requests[0][1]} == {
        "list_files",
        "search_code",
        "read_file",
        "run_command",
        "apply_patch",
        "view_diff",
        "verify_task",
        "finish_task",
        "update_plan",
        "replan",
        "record_fact",
    }


def test_cli_prompts_for_a_task_when_the_task_option_is_omitted(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "finish_task",
                        {
                            "root_cause": "No changes were needed.",
                            "changes": ["No repository changes were made."],
                            "risks": ["No verification evidence was collected."],
                        },
                    )
                ]
            )
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        ["run", str(target_repository), "--state-dir", str(tmp_path / "agent-runs")],
        input="Inspect the repository.\n",
    )

    assert result.exit_code == 0, result.output
    assert model.requests[0][0][1]["content"] == "Inspect the repository."


def test_cli_records_a_versioned_plan_and_replan_from_agent_control_tools(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "replan",
                        {
                            "reason": "The repository needs inspection before implementation.",
                            "steps": [
                                {
                                    "id": "inspect",
                                    "description": "Inspect the repository structure.",
                                    "completion_condition": "Relevant files are identified.",
                                },
                                {
                                    "id": "implement",
                                    "description": "Implement the requested change.",
                                    "completion_condition": "The change is verified.",
                                },
                            ],
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[ToolCall("call-2", "update_plan", {"step_id": "inspect", "status": "IN_PROGRESS"})]
            ),
            AssistantTurn(
                tool_calls=[ToolCall("call-3", "update_plan", {"step_id": "inspect", "status": "COMPLETED"})]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-4",
                        "replan",
                        {
                            "reason": "Inspection found a more direct implementation path.",
                            "steps": [
                                {
                                    "id": "implement-directly",
                                    "description": "Implement the direct change.",
                                    "completion_condition": "The focused Runtime Test passes.",
                                }
                            ],
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[ToolCall("call-5", "update_plan", {"step_id": "implement-directly", "status": "COMPLETED"})]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-6",
                        "finish_task",
                        {
                            "root_cause": "The test exercises Plan and Replan behavior.",
                            "changes": ["Completed the explicit Plan without repository changes."],
                            "risks": ["No Task Verification evidence was collected."],
                        },
                    )
                ]
            ),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Implement a verified change.",
            "--state-dir",
            str(state_directory),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Plan v3" in result.output
    assert "[COMPLETED] Inspect the repository structure." in result.output
    assert "[COMPLETED] Implement the direct change." in result.output
    assert "Current Plan:" in model.requests[0][0][0]["content"]

    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]

    assert [plan["version"] for plan in metadata["plan_history"]] == [1, 2, 3]
    assert metadata["plan_history"][2]["steps"] == [
        {
            "id": "inspect",
            "description": "Inspect the repository structure.",
            "completion_condition": "Relevant files are identified.",
            "status": "COMPLETED",
        },
        {
            "id": "implement-directly",
            "description": "Implement the direct change.",
            "completion_condition": "The focused Runtime Test passes.",
            "status": "COMPLETED",
        },
    ]
    assert [event["type"] for event in events if event["type"].startswith("plan_")] == [
        "plan_created",
        "plan_replanned",
        "plan_updated",
        "plan_updated",
        "plan_replanned",
        "plan_updated",
    ]
    assert events[-1] == {"type": "run_finished", "status": "UNVERIFIED"}
