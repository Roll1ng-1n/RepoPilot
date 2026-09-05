from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import repopilot.benchmark as benchmark_module
from repopilot.benchmark import (
    BenchmarkBudget,
    BenchmarkConfig,
    BenchmarkEngine,
    BenchmarkModel,
    BenchmarkPreflight,
    BenchmarkRunner,
    EngineRun,
    canonical_snapshot_sha256,
    capture_patch,
    copy_snapshot,
    initialize_git_snapshot,
    load_tasks,
    preflight_benchmark_image,
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


def test_baseline_aggregates_cache_write_and_reasoning_tokens() -> None:
    trajectory = {
        "info": {"model_stats": {"api_calls": 2}},
        "messages": [
            {
                "extra": {
                    "response": {
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "total_tokens": 120,
                            "prompt_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 2},
                            "completion_tokens_details": {"reasoning_tokens": 5},
                        }
                    }
                }
            },
            {
                "extra": {
                    "response": {
                        "usage": {
                            "prompt_tokens": 200,
                            "completion_tokens": 30,
                            "total_tokens": 230,
                            "prompt_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 3},
                            "completion_tokens_details": {"reasoning_tokens": 7},
                        }
                    }
                }
            },
        ],
    }

    assert benchmark_module._baseline_model_stats(trajectory)["tokens"] == {
        "prompt": 300,
        "completion": 50,
        "total": 350,
        "cached": 30,
        "cache_write": 5,
        "reasoning": 12,
    }


def test_metrics_keep_provider_cost_and_add_openai_standard_estimate(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)

    def fake_executor(request):
        (request.workspace / "value.txt").write_text("fixed\n")
        return EngineRun(
            status="SUCCEEDED",
            model_stats={
                "tokens": {
                    "prompt": 1_000,
                    "completion": 200,
                    "total": 1_200,
                    "cached": 100,
                    "cache_write": 50,
                    "reasoning": 20,
                },
                "cost": 0.9,
            },
        )

    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("gpt-5.6-luna"),
        image="test-image",
        engines=(BenchmarkEngine.REPOPILOT,),
    )
    result = BenchmarkRunner(config, executors={BenchmarkEngine.REPOPILOT: fake_executor}).run()

    metrics = result.results[0].metrics
    assert metrics["cost"] == 0.9
    assert metrics["openai_standard_estimated_cost_usd"] == pytest.approx(0.0004345)


def test_benchmark_redacts_api_key_from_baseline_trajectory_and_results(tmp_path: Path, monkeypatch) -> None:
    api_key = "benchmark-api-key"
    proxy_url = "http://proxy-user:proxy-password@127.0.0.1:7897"
    container_proxy_url = "http://proxy-user:proxy-password@host.docker.internal:7897"
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)
    task = load_tasks(tasks_root)[0]
    artifact_directory = tmp_path / "baseline"
    artifact_directory.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("test-model", api_key=api_key),
        image="test-image",
        engines=(BenchmarkEngine.BASELINE,),
        proxy_mode="explicit",
        proxy_url=proxy_url,
    )
    request = benchmark_module.EngineRequest(
        BenchmarkEngine.BASELINE,
        task,
        workspace,
        artifact_directory,
        config,
        initial_head=None,
    )

    class FakeAgent:
        def __init__(self) -> None:
            self.saved_paths: list[Path | None] = []

        def run(self, _task: str) -> dict[str, str]:
            return {"exit_status": "Submitted"}

        def save(self, path: Path | None, *_extra: dict) -> dict:
            self.saved_paths.append(path)
            trajectory = {
                "info": {"exit_status": "Submitted"},
                "messages": [{"content": api_key}],
                "model": {"config": {"model_kwargs": {"api_key": api_key}}},
                "environment": {"run_args": [f"HTTP_PROXY={proxy_url}", f"HTTP_PROXY={container_proxy_url}"]},
            }
            if path is not None:
                path.write_text(json.dumps(trajectory))
            return trajectory

    agent = FakeAgent()
    monkeypatch.setattr(benchmark_module, "get_model", lambda **_kwargs: object())
    monkeypatch.setattr(benchmark_module, "get_config_from_spec", lambda *_args: {"agent": {}})
    monkeypatch.setattr(benchmark_module, "get_environment", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(benchmark_module, "get_agent", lambda *_args, **_kwargs: agent)

    run = benchmark_module._run_baseline(request)

    assert api_key not in json.dumps(run.trajectory)
    assert "proxy-password" not in json.dumps(run.trajectory)
    assert api_key not in (artifact_directory / "trajectory.json").read_text()
    assert all(path is None for path in agent.saved_paths)

    def fake_executor(_request):
        return EngineRun(status="FAILED", error=f"provider error: {api_key}; proxy: {container_proxy_url}")

    result = BenchmarkRunner(
        config,
        executors={BenchmarkEngine.BASELINE: fake_executor},
    ).run()
    output = config.output_directory
    assert api_key not in json.dumps(result.to_dict())
    assert api_key not in (output / "summary.json").read_text()
    assert api_key not in (output / "seed-task" / "baseline" / "result.json").read_text()
    assert "proxy-password" not in json.dumps(result.to_dict())
    assert "proxy-password" not in (output / "summary.json").read_text()


def test_baseline_ignores_unknown_model_costs(tmp_path: Path, monkeypatch) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)
    task = load_tasks(tasks_root)[0]
    artifact_directory = tmp_path / "baseline"
    artifact_directory.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("custom/model"),
        image="test-image",
        engines=(BenchmarkEngine.BASELINE,),
    )
    request = benchmark_module.EngineRequest(
        BenchmarkEngine.BASELINE,
        task,
        workspace,
        artifact_directory,
        config,
        initial_head=None,
    )
    model_configs: list[dict] = []

    class FakeAgent:
        def run(self, _task: str) -> dict[str, str]:
            return {"exit_status": "Submitted"}

        def save(self, _path: Path | None, *_extra: dict) -> dict:
            return {
                "info": {"exit_status": "Submitted", "model_stats": {"api_calls": 1, "instance_cost": 0.0}},
                "messages": [
                    {
                        "extra": {
                            "cost": 0.0,
                            "response": {"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
                        }
                    }
                ],
            }

    monkeypatch.setattr(
        benchmark_module, "get_model", lambda **kwargs: model_configs.append(kwargs["config"]) or object()
    )
    monkeypatch.setattr(benchmark_module, "get_config_from_spec", lambda *_args: {"agent": {}})
    monkeypatch.setattr(benchmark_module, "get_environment", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(benchmark_module, "get_agent", lambda *_args, **_kwargs: FakeAgent())

    run = benchmark_module._run_baseline(request)

    assert model_configs[0]["cost_tracking"] == "ignore_errors"
    assert run.model_stats["cost"] is None


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


def test_runner_records_an_unavailable_environment_without_running_the_verifier(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)

    def unavailable_environment(_request):
        raise subprocess.CalledProcessError(125, ["docker", "run"])

    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("test"),
        image="missing-image",
        engines=(BenchmarkEngine.REPOPILOT,),
    )

    result = BenchmarkRunner(config, executors={BenchmarkEngine.REPOPILOT: unavailable_environment}).run()

    assert result.results[0].status == "ENVIRONMENT_UNAVAILABLE"
    assert result.results[0].success is None
    assert result.results[0].verifier is None


def test_benchmark_image_preflight_resolves_image_id_and_checks_python_and_git(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)
    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("test"),
        image="repopilot-benchmark:py312-git",
    )
    calls: list[list[str]] = []

    def command_runner(argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        "Id": "sha256:local-image-id",
                        "RepoDigests": ["repopilot-benchmark@sha256:registry-digest"],
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(
            argv, 0, stdout="Python 3.12.14\n" if argv[-2] == "python" else "git version 2.47.3\n", stderr=""
        )

    preflight = preflight_benchmark_image(config, command_runner=command_runner)

    assert preflight.ready
    assert preflight.image_id == "sha256:local-image-id"
    assert preflight.image_digest == "repopilot-benchmark@sha256:registry-digest"
    assert preflight.resolved_image == "sha256:local-image-id"
    assert [check["name"] for check in preflight.checks] == ["image_inspect", "python", "git"]
    assert calls[1][-3:] == ["sha256:local-image-id", "python", "--version"]
    assert calls[2][-3:] == ["sha256:local-image-id", "git", "--version"]


def test_runner_preflight_failure_skips_both_engine_executors(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)
    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("test"),
        image="image-without-git",
    )
    calls: list[str] = []
    unavailable = BenchmarkPreflight(
        "ENVIRONMENT_UNAVAILABLE",
        config.image,
        "sha256:local-image-id",
        "sha256:local-image-id",
        None,
        ({"name": "git", "exit_code": 127},),
        "git --version failed",
    )

    def executor(_request):
        calls.append("executor")
        raise AssertionError("an unavailable preflight must not enter an Agent Run")

    result = BenchmarkRunner(
        config,
        executors={BenchmarkEngine.BASELINE: executor, BenchmarkEngine.REPOPILOT: executor},
        preflight_runner=lambda _config: unavailable,
    ).run()

    assert calls == []
    assert [item.status for item in result.results] == ["ENVIRONMENT_UNAVAILABLE", "ENVIRONMENT_UNAVAILABLE"]
    assert all(item.success is None and item.verifier is None for item in result.results)
    assert json.loads((config.output_directory / "preflight.json").read_text())["image_id"] == "sha256:local-image-id"
    assert all((item.artifact_directory / "preflight.json").is_file() for item in result.results)


def test_runner_uses_one_resolved_image_for_both_engine_requests(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root)
    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("test"),
        image="mutable-tag",
    )
    resolved = BenchmarkPreflight("READY", config.image, "sha256:stable-id", "sha256:stable-id", None, ())
    seen: list[str] = []

    def executor(request):
        seen.append(request.config.resolved_image)
        (request.workspace / "value.txt").write_text("fixed\n")
        return EngineRun(status="SUCCEEDED")

    result = BenchmarkRunner(
        config,
        executors={BenchmarkEngine.BASELINE: executor, BenchmarkEngine.REPOPILOT: executor},
        preflight_runner=lambda _config: resolved,
    ).run()

    assert seen == ["sha256:stable-id", "sha256:stable-id"]
    assert result.config.image == "mutable-tag"
    assert result.config.resolved_image == "sha256:stable-id"
    assert all(item.metrics["image"] == "sha256:stable-id" for item in result.results)


def test_snapshot_hash_and_copy_ignore_python_bytecode(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    (snapshot / "src").mkdir(parents=True)
    (snapshot / "src" / "module.py").write_text("value = 1\n")
    expected = canonical_snapshot_sha256(snapshot)

    (snapshot / "src" / "__pycache__").mkdir()
    (snapshot / "src" / "__pycache__" / "module.cpython-312.pyc").write_bytes(b"cache")
    (snapshot / "module.pyc").write_bytes(b"cache")
    (snapshot / "module.pyo").write_bytes(b"cache")

    assert canonical_snapshot_sha256(snapshot) == expected
    workspace = tmp_path / "workspace"
    copy_snapshot(snapshot, workspace)
    assert (workspace / "src" / "module.py").is_file()
    assert not (workspace / "src" / "__pycache__").exists()
    assert not (workspace / "module.pyc").exists()
    assert not (workspace / "module.pyo").exists()

    (snapshot / "src" / "module.py").write_text("value = 2\n")
    assert canonical_snapshot_sha256(snapshot) != expected


def test_capture_patch_ignores_untracked_python_bytecode(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "module.py").write_text("value = 1\n")
    initial_head = initialize_git_snapshot(workspace)

    (workspace / "module.py").write_text("value = 2\n")
    (workspace / "module.pyc").write_bytes(b"cache")
    cache_directory = workspace / "__pycache__"
    cache_directory.mkdir()
    (cache_directory / "module.cpython-312.pyc").write_bytes(b"cache")

    patch = capture_patch(workspace, initial_head)

    assert patch is not None and "value = 2" in patch
    assert "module.pyc" not in patch
    assert "__pycache__" not in patch

    subprocess.run(["git", "add", "--all"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "--quiet", "--message", "agent change"], cwd=workspace, check=True)
    committed_patch = capture_patch(workspace, initial_head)
    assert committed_patch is not None and "value = 2" in committed_patch
    assert "module.pyc" not in committed_patch
    assert "__pycache__" not in committed_patch


def test_runner_can_select_one_task_for_an_independent_repeat(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_task(tasks_root, task_id="first-task")
    _write_task(tasks_root, task_id="second-task")
    seen: list[str] = []

    def fake_executor(request):
        seen.append(request.task.task_id)
        (request.workspace / "value.txt").write_text("fixed\n")
        return EngineRun(status="SUCCEEDED")

    config = BenchmarkConfig(
        tasks_directory=tasks_root,
        output_directory=tmp_path / "results",
        model=BenchmarkModel("test"),
        image="test-image",
        engines=(BenchmarkEngine.REPOPILOT,),
        task_ids=("second-task",),
    )

    result = BenchmarkRunner(config, executors={BenchmarkEngine.REPOPILOT: fake_executor}).run()

    assert seen == ["second-task"]
    assert [task.task_id for task in result.tasks] == ["second-task"]


def test_bundled_manifests_load_with_revisions_and_host_verifiers() -> None:
    tasks_root = Path(__file__).resolve().parents[2] / "src" / "repopilot" / "benchmark_tasks"
    revisions = {
        "seed-single-file": "seed-v1",
        "seed-cross-file": "seed-v1",
        "recovery-public-failure": "recovery-v1",
        "replan-new-evidence": "replan-v1",
        "workflow-long-chain": "workflow-v1",
        "workflow-human-approval-git": "approval-git-v1",
    }

    tasks = load_tasks(tasks_root)

    assert {task.task_id for task in tasks} == set(revisions)
    for task in tasks:
        assert task.snapshot_revision == revisions[task.task_id]
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
    copy_snapshot(task.snapshot, workspace)

    result = run_hidden_verifier(task, workspace)

    assert result is not None
    assert result["exit_code"] != 0
    assert not (workspace / "verifier.py").exists()
    assert not list(workspace.rglob("__pycache__"))
