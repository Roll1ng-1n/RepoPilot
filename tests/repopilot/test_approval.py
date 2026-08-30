"""Human Approval policy behavior at its public decision seam."""

from __future__ import annotations

from typing import Any

import pytest

from repopilot.approval import ApprovalContext, ApprovalPolicy, RiskDecision, ToolCallSnapshot
from repopilot.model import ToolCall


def _decision(name: str, arguments: dict[str, Any], context: ApprovalContext | None = None) -> RiskDecision:
    policy = ApprovalPolicy(context or ApprovalContext(environment="local"))
    return policy.assess(ToolCallSnapshot.from_tool_call(ToolCall("call-1", name, arguments))).decision


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("run_command", {"command": "git status --short"}),
        ("run_command", {"command": "pytest -q"}),
        ("apply_patch", {"patch": "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n+new\n"}),
    ],
)
def test_policy_allows_routine_repository_work(name: str, arguments: dict[str, Any]) -> None:
    assert _decision(name, arguments) is RiskDecision.ALLOW


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("run_command", {"command": "rm obsolete.txt"}),
        ("run_command", {"command": "python -m pip install requests"}),
        ("run_command", {"command": "git commit -m 'record the change'"}),
        ("run_command", {"command": "git config user.name RepoPilot"}),
        ("apply_patch", {"patch": "diff --git a/obsolete.txt b/obsolete.txt\ndeleted file mode 100644\n"}),
        ("git_commit", {"message": "Record the change", "reason": "Preserve verified work", "paths": ["README.md"]}),
    ],
)
def test_policy_requires_human_approval_for_high_risk_work(name: str, arguments: dict[str, Any]) -> None:
    assert _decision(name, arguments) is RiskDecision.REQUIRE_APPROVAL


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git rebase main",
        "git reset --hard HEAD~1",
        "gh pr create --title change --body reason",
    ],
)
def test_policy_permanently_denies_unsupported_git_and_pull_request_operations(command: str) -> None:
    assert _decision("run_command", {"command": command}) is RiskDecision.DENY


def test_only_an_explicit_disposable_docker_benchmark_can_auto_approve() -> None:
    arguments = {"command": "rm generated-output.txt"}

    assert (
        _decision(
            "run_command",
            arguments,
            ApprovalContext(environment="docker", disposable_benchmark=True, automatic_approval=True),
        )
        is RiskDecision.ALLOW
    )
    assert (
        _decision(
            "run_command",
            arguments,
            ApprovalContext(environment="local", disposable_benchmark=True, automatic_approval=True),
        )
        is RiskDecision.REQUIRE_APPROVAL
    )


@pytest.mark.parametrize(
    ("name", "command", "expected"),
    [
        ("verify_task", "rm generated-output.txt", RiskDecision.REQUIRE_APPROVAL),
        ("verify_task", "git push origin main", RiskDecision.DENY),
        ("run_command", "npm ci", RiskDecision.REQUIRE_APPROVAL),
        ("run_command", "git fetch origin", RiskDecision.REQUIRE_APPROVAL),
        ("run_command", "git pull --ff-only", RiskDecision.REQUIRE_APPROVAL),
    ],
)
def test_policy_covers_high_risk_verification_and_common_write_commands(
    name: str, command: str, expected: RiskDecision
) -> None:
    assert _decision(name, {"command": command}) is expected


def test_snapshot_does_not_change_when_the_original_tool_call_arguments_mutate() -> None:
    tool_call = ToolCall("call-1", "git_commit", {"message": "Initial", "paths": ["README.md"]})

    snapshot = ToolCallSnapshot.from_tool_call(tool_call)
    tool_call.arguments["message"] = "Mutated"
    tool_call.arguments["paths"].append("other.md")

    assert snapshot.to_dict() == {
        "id": "call-1",
        "name": "git_commit",
        "arguments": {"message": "Initial", "paths": ["README.md"]},
    }
