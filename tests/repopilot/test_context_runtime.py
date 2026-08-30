import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from repopilot.cli import create_app
from repopilot.model import AssistantTurn, ToolCall


def _context_summary(messages: list[dict]) -> dict:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("context_summary"), dict):
            return value["context_summary"]
    raise AssertionError("No structured Context summary reached the model.")


def _make_target_repository(path: Path) -> None:
    path.mkdir()
    (path / "README.md").write_text("RepoPilot README\n")
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


def test_cli_summary_strategy_uses_the_model_and_keeps_raw_history_in_the_checkpoint(tmp_path: Path) -> None:
    class SummarizingModel:
        model_name = "summarizing-model"

        def __init__(self) -> None:
            self.agent_requests: list[list[dict]] = []
            self.summary_requests: list[list[dict]] = []

        def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
            if not tools:
                self.summary_requests.append(messages)
                return AssistantTurn(
                    content=json.dumps(
                        {
                            "important_facts": [],
                            "completed_work": ["Recorded the requested file."],
                            "decisions": ["Inspect command output before finishing."],
                            "open_questions": [],
                        }
                    )
                )
            self.agent_requests.append(messages)
            if len(self.agent_requests) == 1:
                return AssistantTurn(
                    tool_calls=[ToolCall("fact", "record_fact", {"fact": "Only README.md is in scope."})]
                )
            if len(self.agent_requests) == 2:
                return AssistantTurn(tool_calls=[ToolCall("output", "run_command", {"command": "printf '%0800d' 0"})])
            assert _context_summary(messages)["completed_work"] == ["Recorded the requested file."]
            return AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "finish",
                        "finish_task",
                        {
                            "root_cause": "The context was summarized after the configured threshold.",
                            "changes": ["No repository change was required."],
                        },
                    )
                ]
            )

    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = SummarizingModel()

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the README context.",
            "--state-dir",
            str(state_directory),
            "--context-strategy",
            "summary",
            "--context-max-characters",
            "400",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(model.summary_requests) == 1
    run_directory = next(state_directory.iterdir())
    checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
    assert checkpoint["context"]["strategy"] == "summary"
    assert checkpoint["context"]["summary"]["important_facts"] == ["Only README.md is in scope."]
    assert checkpoint["context"]["summarized_steps"] == 1
    assert any(message.get("tool_call_id") == "fact" for message in checkpoint["messages"])
    assert any(message.get("content") and "000000" in message["content"] for message in checkpoint["messages"])
    assert any(event["type"] == "context_summary_created" for event in events)


def test_cli_summary_failure_falls_back_without_stopping_and_resume_keeps_the_fallback(tmp_path: Path) -> None:
    class FailingSummaryModel:
        model_name = "failing-summary-model"

        def __init__(self) -> None:
            self.agent_calls = 0
            self.summary_calls = 0

        def complete(self, _messages: list[dict], tools: list[dict]) -> AssistantTurn:
            if not tools:
                self.summary_calls += 1
                raise TimeoutError("summary request timed out")
            self.agent_calls += 1
            if self.agent_calls == 1:
                return AssistantTurn(tool_calls=[ToolCall("fact", "record_fact", {"fact": "README only."})])
            if self.agent_calls == 2:
                return AssistantTurn(tool_calls=[ToolCall("output", "run_command", {"command": "printf '%0800d' 0"})])
            raise KeyboardInterrupt()

    class FinishAfterResumeModel:
        model_name = "finish-after-resume-model"

        def __init__(self) -> None:
            self.summary_calls = 0

        def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
            if not tools:
                self.summary_calls += 1
                raise AssertionError("A persisted summary fallback must not retry summarization after resume.")
            assert not any(
                isinstance(message.get("content"), str) and "context_summary" in message["content"]
                for message in messages
            )
            assert any("README only." in str(message["content"]) for message in messages)
            return AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "finish",
                        "finish_task",
                        {"root_cause": "The fallback retained recent context.", "changes": ["No change was needed."]},
                    )
                ]
            )

    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    stopped_model = FailingSummaryModel()
    stopped = CliRunner().invoke(
        create_app(lambda _: stopped_model),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the README context.",
            "--state-dir",
            str(state_directory),
            "--context-strategy",
            "summary",
            "--context-max-characters",
            "400",
        ],
    )

    assert stopped.exit_code == 0, stopped.output
    assert "STOPPED" in stopped.output
    assert stopped_model.summary_calls == 1
    run_directory = next(state_directory.iterdir())
    stopped_checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    assert stopped_checkpoint["context"]["fallback"] == {"active": True, "reason": "summary request timed out"}

    resumed_model = FinishAfterResumeModel()
    resumed = CliRunner().invoke(
        create_app(lambda _: resumed_model),
        ["resume", run_directory.name, "--state-dir", str(state_directory)],
    )

    assert resumed.exit_code == 0, resumed.output
    assert "UNVERIFIED" in resumed.output
    assert resumed_model.summary_calls == 0
    resumed_checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    assert resumed_checkpoint["context"]["fallback"] == {"active": True, "reason": "summary request timed out"}


def test_cli_resume_reuses_a_persisted_summary_and_important_fact_without_resummarizing(tmp_path: Path) -> None:
    class SummaryThenStopModel:
        model_name = "summary-then-stop-model"

        def __init__(self) -> None:
            self.agent_calls = 0
            self.summary_calls = 0

        def complete(self, _messages: list[dict], tools: list[dict]) -> AssistantTurn:
            if not tools:
                self.summary_calls += 1
                return AssistantTurn(
                    content=json.dumps(
                        {
                            "important_facts": [],
                            "completed_work": ["Recorded the scope."],
                            "decisions": [],
                            "open_questions": [],
                        }
                    )
                )
            self.agent_calls += 1
            if self.agent_calls == 1:
                return AssistantTurn(tool_calls=[ToolCall("fact", "record_fact", {"fact": "README only."})])
            if self.agent_calls == 2:
                return AssistantTurn(tool_calls=[ToolCall("output", "run_command", {"command": "printf '%0800d' 0"})])
            raise KeyboardInterrupt()

    class FinishAfterSummaryResumeModel:
        model_name = "finish-after-summary-resume-model"

        def __init__(self) -> None:
            self.summary_calls = 0

        def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
            if not tools:
                self.summary_calls += 1
                raise AssertionError("Resume must use the persisted Context Summary before requesting another one.")
            assert _context_summary(messages)["completed_work"] == ["Recorded the scope."]
            assert any("README only." in str(message["content"]) for message in messages)
            return AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "finish",
                        "finish_task",
                        {"root_cause": "Resume kept the compressed context.", "changes": ["No change was needed."]},
                    )
                ]
            )

    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    stopped_model = SummaryThenStopModel()
    stopped = CliRunner().invoke(
        create_app(lambda _: stopped_model),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the README context.",
            "--state-dir",
            str(state_directory),
            "--context-strategy",
            "summary",
            "--context-max-characters",
            "400",
        ],
    )

    assert stopped.exit_code == 0, stopped.output
    assert stopped_model.summary_calls == 1
    run_directory = next(state_directory.iterdir())
    stopped_checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    assert stopped_checkpoint["context"]["summary"]["important_facts"] == ["README only."]

    resumed_model = FinishAfterSummaryResumeModel()
    resumed = CliRunner().invoke(
        create_app(lambda _: resumed_model),
        ["resume", run_directory.name, "--state-dir", str(state_directory)],
    )

    assert resumed.exit_code == 0, resumed.output
    assert resumed_model.summary_calls == 0


def test_cli_trace_keeps_text_from_a_model_response_that_also_calls_tools(tmp_path: Path) -> None:
    class TextAndToolModel:
        model_name = "text-and-tool-model"

        def complete(self, _messages: list[dict], _tools: list[dict]) -> AssistantTurn:
            return AssistantTurn(
                content="The repository already satisfies the task.",
                tool_calls=[
                    ToolCall(
                        "finish",
                        "finish_task",
                        {"root_cause": "No change was required.", "changes": ["Kept the repository unchanged."]},
                    )
                ],
            )

    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"

    result = CliRunner().invoke(
        create_app(lambda _: TextAndToolModel()),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the repository.",
            "--state-dir",
            str(state_directory),
        ],
    )

    assert result.exit_code == 0, result.output
    run_directory = next(state_directory.iterdir())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
    assert any(
        event["type"] == "model_response" and event["content"] == "The repository already satisfies the task."
        for event in events
    )
