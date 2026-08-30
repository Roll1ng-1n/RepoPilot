from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repopilot.swebench_smoke import (
    DATASET_NAME,
    DATASET_REVISION,
    INSTANCE_ID,
    SPLIT,
    AgentExecution,
    SWEbenchSmokeConfig,
    load_pinned_instance,
    run_swebench_smoke,
)


def test_load_pinned_instance_uses_the_canonical_dataset_revision() -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    rows = [{"instance_id": INSTANCE_ID, "problem_statement": "Fix sqlfluff."}]

    def loader(name: str, **kwargs: object) -> list[dict[str, object]]:
        calls.append((name, kwargs))
        return rows

    assert load_pinned_instance(loader=loader) == rows[0]
    assert calls == [(DATASET_NAME, {"revision": DATASET_REVISION, "split": SPLIT})]


def test_missing_image_is_persisted_without_building_a_model(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    model_calls: list[object] = []
    dataset_calls: list[object] = []

    def command_runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="No such image")

    def model_factory(_instance: dict[str, object]) -> object:
        model_calls.append(_instance)
        return object()

    def dataset_loader(_name: str, **_kwargs: object) -> list[dict[str, object]]:
        dataset_calls.append(object())
        raise AssertionError("dataset loading must happen after the environment preflight")

    result = run_swebench_smoke(
        SWEbenchSmokeConfig(output_directory=tmp_path / "results", image="local/missing:latest"),
        model_factory=model_factory,
        command_runner=command_runner,
        loader=dataset_loader,
    )

    assert result.status == "ENVIRONMENT_UNAVAILABLE"
    assert model_calls == []
    assert dataset_calls == []
    assert len(calls) == 1
    assert calls[0][:3] == ["docker", "image", "inspect"]
    artifact_directory = tmp_path / "results" / INSTANCE_ID
    assert json.loads((artifact_directory / "result.json").read_text())["status"] == "ENVIRONMENT_UNAVAILABLE"
    assert (artifact_directory / "patch.diff").read_text() == ""
    assert (artifact_directory / "trace.jsonl").is_file()


def test_ready_preflight_runs_model_and_persists_patch_cost_and_verifier(tmp_path: Path) -> None:
    model_calls: list[dict[str, object]] = []
    agent_calls: list[tuple[dict[str, object], object]] = []
    commands: list[list[str]] = []
    rows = [{"instance_id": INSTANCE_ID, "problem_statement": "Fix sqlfluff."}]

    def command_runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        commands.append(argv)
        if "--report_dir" in argv:
            report_directory = Path(argv[argv.index("--report_dir") + 1])
            report_directory.mkdir(parents=True, exist_ok=True)
            (report_directory / "report.json").write_text(
                json.dumps({"resolved_ids": [INSTANCE_ID]}), encoding="utf-8"
            )
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    def model_factory(instance: dict[str, object]) -> object:
        model_calls.append(instance)
        return object()

    def agent_runner(
        instance: dict[str, object], model: object, artifact_directory: Path, _config: SWEbenchSmokeConfig
    ) -> AgentExecution:
        agent_calls.append((instance, model))
        return AgentExecution(
            status="SUCCEEDED",
            patch="diff --git a/foo.py b/foo.py\n",
            trajectory={"messages": []},
            model_calls=2,
            cost_usd=0.12,
        )

    result = run_swebench_smoke(
        SWEbenchSmokeConfig(output_directory=tmp_path / "results", image="local/ready:latest"),
        model_factory=model_factory,
        agent_runner=agent_runner,
        command_runner=command_runner,
        loader=lambda _name, **_kwargs: rows,
    )

    assert result.status == "SUCCEEDED"
    assert result.success is True
    assert len(model_calls) == 1
    assert len(agent_calls) == 1
    artifact_directory = tmp_path / "results" / INSTANCE_ID
    assert (artifact_directory / "patch.diff").read_text().startswith("diff --git")
    assert json.loads((artifact_directory / "trajectory.json").read_text()) == {"messages": []}
    saved = json.loads((artifact_directory / "result.json").read_text())
    assert saved["metrics"]["model_calls"] == 2
    assert saved["metrics"]["cost_usd"] == 0.12
    assert saved["verifier"]["exit_code"] == 0
    predictions = json.loads((artifact_directory / "preds.json").read_text())
    assert predictions[INSTANCE_ID]["model_patch"].startswith("diff --git")
    dataset_path = artifact_directory / "dataset.json"
    assert json.loads(dataset_path.read_text()) == rows
    verifier_commands = [command for command in commands if any("run_evaluation" in arg for arg in command)]
    assert len(verifier_commands) == 2
    assert all(
        verifier_command[verifier_command.index("--dataset_name") + 1] == str(dataset_path)
        for verifier_command in verifier_commands
    )


def test_unresolved_official_report_is_failure_even_when_command_exits_zero(tmp_path: Path) -> None:
    model_calls: list[dict[str, object]] = []
    rows = [{"instance_id": INSTANCE_ID, "problem_statement": "Fix sqlfluff."}]

    def command_runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        if "--report_dir" in argv:
            report_directory = Path(argv[argv.index("--report_dir") + 1])
            report_directory.mkdir(parents=True, exist_ok=True)
            is_preflight = "preflight" in argv[argv.index("--run_id") + 1]
            report = {"resolved_ids": [INSTANCE_ID]} if is_preflight else {"resolved_ids": []}
            (report_directory / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    def model_factory(instance: dict[str, object]) -> object:
        model_calls.append(instance)
        return object()

    result = run_swebench_smoke(
        SWEbenchSmokeConfig(output_directory=tmp_path / "results", image="local/ready:latest"),
        model_factory=model_factory,
        agent_runner=lambda _instance, _model, _directory, _config: AgentExecution(
            status="SUCCEEDED", patch="diff --git a/foo.py b/foo.py\n"
        ),
        command_runner=command_runner,
        loader=lambda _name, **_kwargs: rows,
    )

    assert result.status == "FAILED_VERIFICATION"
    assert result.success is False
    assert len(model_calls) == 1
    assert result.verifier is not None
    assert result.verifier["exit_code"] == 0
    assert result.verifier["resolved_ids"] == []
