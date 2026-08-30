from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from repopilot.benchmark import (
    BenchmarkBudget,
    BenchmarkConfig,
    BenchmarkEngine,
    BenchmarkModel,
    BenchmarkRunner,
    EngineRun,
    canonical_snapshot_sha256,
    load_tasks,
    run_hidden_verifier,
)


def _write_task(root: Path, *, task_id: str = "seed-task") -> Path:
    task_root = root / task_id
    snapshot = task_root / "snapshot"
    snapshot.mkdir(parents=True)
    (snapshot / "value.txt").write_text("before\n")
    digest = canonical_snapshot_sha256(snapshot)
    (task_root / "manifest.json").write_text(
        json.dumps(
            {
                "id": task_id,
                "task": "Change value.txt and verify it.",
                "snapshot": "snapshot",
                "snapshot_sha256": digest,
                "hidden_verifier": {
                    "command": "python -c \"from pathlib import Path; assert Path('value.txt').read_text() == 'fixed\\n'\"",
                    "success_condition": "value.txt contains fixed.",
                },
                "timeout_seconds": 5,
                "run_budget": {"max_steps": 99, "max_run_seconds": 99},
            }
        )
    )
    return task_root / "manifest.json"


def test_load_tasks_validates_the_manifest_shape_and_canonical_snapshot(tmp_path: Path) -> None:
    manifest = _write_task(tmp_path / "tasks")

    tasks = load_tasks(tmp_path / "tasks")

    assert len(tasks) == 1
    assert tasks[0].task_id == "seed-task"
    assert tasks[0].snapshot == manifest.parent.joinpath("snapshot").resolve()
    assert tasks[0].timeout_seconds == 5


def test_runner_runs_both_engines_in_order_on_independent_workspaces(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)
    output = tmp_path / "results"
    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=output,
        model=BenchmarkModel("test-model", {"temperature": 0.0}),
        image="python:3.12-bookworm",
        budget=BenchmarkBudget(max_steps=4, max_replans=1, command_timeout_seconds=12, max_run_seconds=30),
    )
    requests = []

    def fake_baseline(request):
        requests.append(request)
        (request.workspace / "value.txt").write_text("fixed\n")
        trajectory = {
            "info": {"exit_status": "Submitted", "model_stats": {"api_calls": 2, "instance_cost": 1.5}},
            "messages": [],
        }
        (request.artifact_directory / "trajectory.json").write_text(json.dumps(trajectory))
        return EngineRun(
            status="Submitted",
            trajectory=trajectory,
            model_stats={
                "steps": 2,
                "tokens": {"prompt": None, "completion": None, "total": None},
                "cost": 1.5,
                "tool_calls": 2,
                "errors": [],
            },
        )

    def fake_repopilot(request):
        requests.append(request)
        (request.workspace / "value.txt").write_text("fixed\n")
        (request.artifact_directory / "metadata.json").write_text(
            json.dumps({"budget": {"steps_used": 3, "replans_used": 1}, "failures": [], "recoveries": []})
        )
        (request.artifact_directory / "trace.jsonl").write_text(
            json.dumps({"type": "tool_call", "tool_name": "apply_patch"}) + "\n"
        )
        return EngineRun(
            status="SUCCEEDED",
            model_stats={
                "tokens": {"prompt": None, "completion": None, "total": None},
                "cost": None,
            },
        )

    result = BenchmarkRunner(
        config,
        executors={BenchmarkEngine.BASELINE: fake_baseline, BenchmarkEngine.REPOPILOT: fake_repopilot},
    ).run()

    assert [item.engine for item in result.results] == [BenchmarkEngine.BASELINE, BenchmarkEngine.REPOPILOT]
    assert [item.success for item in result.results] == [True, True]
    assert requests[0].workspace != requests[1].workspace
    assert requests[0].initial_head == requests[1].initial_head
    assert requests[0].config.model.public_dict() == requests[1].config.model.public_dict()
    assert requests[0].config.image == requests[1].config.image == "python:3.12-bookworm"
    assert requests[0].config.budget == requests[1].config.budget
    assert requests[0].effective_budget.max_steps == requests[1].effective_budget.max_steps == 4
    assert requests[0].effective_budget.max_run_seconds == requests[1].effective_budget.max_run_seconds == 5
    assert (output / "config.json").is_file()
    assert (output / "summary.json").is_file()
    assert (output / "summary.md").is_file()
    assert json.loads((output / "summary.json").read_text())["tasks"][0]["snapshot_revision"] is None
    assert "Snapshot Revision" in (output / "summary.md").read_text()
    assert all((item.artifact_directory / "result.json").is_file() for item in result.results)
    assert all((item.artifact_directory / "patch.diff").is_file() for item in result.results)
    assert result.results[0].metrics["retries"] is None
    assert result.results[0].metrics["replans"] is None
    assert result.results[1].metrics["retries"] == 0
    assert result.results[1].metrics["replans"] == 1
    assert result.results[0].metrics["run_budget"] == result.results[1].metrics["run_budget"]


def test_runner_rejects_a_changed_snapshot_before_starting_an_engine(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    manifest = _write_task(tasks_root)
    payload = json.loads(manifest.read_text())
    payload["snapshot_sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload))
    called = False

    def fake_executor(_request):
        nonlocal called
        called = True
        return EngineRun()

    config = BenchmarkConfig(tasks_root, tmp_path / "results", BenchmarkModel("test"), "test-image")
    with pytest.raises(ValueError, match="Snapshot SHA256 mismatch"):
        BenchmarkRunner(config, executors={BenchmarkEngine.BASELINE: fake_executor}).run()
    assert called is False


def test_bundled_manifests_load_with_revisions_and_host_verifiers() -> None:
    tasks_root = Path(__file__).resolve().parents[2] / "src" / "repopilot" / "benchmark_tasks"

    tasks = load_tasks(tasks_root)

    assert {task.task_id for task in tasks} == {"seed-single-file", "seed-cross-file"}
    for task in tasks:
        assert task.snapshot_revision == "seed-v1"
        assert task.verifier_path is not None and task.verifier_path.is_absolute()
        assert task.manifest_path is not None
        assert task.verifier_path.name == f"verify_{task.task_id.replace('-', '_')}.py"
        assert task.verifier_timeout_seconds == 20
        assert task.run_budget is not None
        assert canonical_snapshot_sha256(task.snapshot) == task.snapshot_sha256


def test_path_verifier_runs_outside_the_workspace(tmp_path: Path) -> None:
    tasks_root = Path(__file__).resolve().parents[2] / "src" / "repopilot" / "benchmark_tasks"
    task = load_tasks(tasks_root)[0]
    workspace = tmp_path / "workspace"
    shutil.copytree(task.snapshot, workspace)

    result = run_hidden_verifier(task, workspace)

    assert result is not None
    assert result["exit_code"] != 0
    assert not (workspace / "verifier.py").exists()
