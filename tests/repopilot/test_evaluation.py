import pytest

from repopilot.evaluation import ScenarioObserver, aggregate, evaluate, normalize_trace, scenario_audit


def test_three_way_results_and_termination():
    assert evaluate(True, "SUCCEEDED", {}, [], [])["task_pass"] is True
    assert evaluate(True, "BUDGET_EXCEEDED", {}, [], [])["termination"] == "false_failure"
    assert evaluate(False, "Submitted", {}, [], [])["termination"] == "false_success"
    missing = evaluate(True, "SUCCEEDED", {}, [], ["approval"])
    assert missing["behavior_pass"] is None
    assert missing["task_pass"] is None
    assert evaluate(False, "FAILED", {}, [], ["approval"])["task_pass"] is False
    assert evaluate(None, None, {}, [], [])["termination"] is None
    with pytest.raises(ValueError):
        evaluate(True, "SUCCEEDED", {}, [], ["typo"])


def test_unrelated_success_and_plan_status_changes_never_prove_recovery_or_replan():
    events = [
        {"type": "scenario_triggered", "capability": "recovery", "scenario_id": "a"},
        {"type": "tool_result", "failed": False},
        {"type": "scenario_triggered", "capability": "replan", "scenario_id": "b", "step": 2},
        {"type": "plan_replanned", "plan": {"version": 2}},
    ]
    result = evaluate(True, "SUCCEEDED", {}, events, ["recovery", "replan"])
    assert result["behavior_pass"] is False
    assert result["recovery"]["success_rate"] == 0
    assert result["replan"]["success_rate"] == 0


def test_observer_requires_ordered_public_failure_and_actual_strategy_change(tmp_path):
    class Environment:
        def execute(self, action):
            if action["command"] == "python test.py":
                return {"returncode": 0 if (tmp_path / "fixed").exists() else 1, "output": ""}
            if action["command"] == "python reveal.py":
                return {"returncode": 0, "output": "NEW_EVIDENCE: streaming"}
            (tmp_path / "plan.md").write_text("Implement JSONL", encoding="utf-8")
            return {"returncode": 0, "output": ""}

    spec = dict(
        recovery_command="python test.py",
        evidence_command="python reveal.py",
        evidence_marker="NEW_EVIDENCE",
        plan_path="plan.md",
        before_strategy="ARRAY",
        after_strategy="JSONL",
    )
    observer = ScenarioObserver(Environment(), tmp_path, spec)
    (tmp_path / "plan.md").write_text("Implement ARRAY", encoding="utf-8")
    observer.execute({"command": "python test.py"})
    observer.execute({"command": "python reveal.py"})
    observer.execute({"command": "modify"})
    (tmp_path / "fixed").touch()
    observer.execute({"command": "python test.py"})
    result = evaluate(True, "Submitted", {}, observer.events + [scenario_audit(spec)], ["recovery", "replan"])
    assert result["task_pass"] is True
    assert result["recovery"]["attempt_count"] == 1
    assert result["replan"]["valid_count"] == 1
    assert evaluate(True, "Submitted", {}, [scenario_audit(spec)], ["recovery"])["task_pass"] is False


def test_tool_exit_failure_inside_successful_tool_envelope():
    events = normalize_trace(
        [{"type": "tool_result", "observation": {"ok": True, "result": {"result": {"exit_code": 1}}}}]
    )
    result = evaluate(False, "FAILED", {}, events, [])
    assert result["tool_quality"]["failure_count"] == 1


def test_aggregation_pairs_repeats_models_nulls_and_cost_of_failures():
    def row(engine, repeat, passed, tokens, *, retries=None, replans=None, redundant=None):
        return dict(
            model="model-a",
            engine=engine,
            repeat=repeat,
            task_id="task",
            category="recovery",
            capabilities=["recovery"],
            task_pass=passed,
            metrics={"tokens": {"total": tokens}, "retries": retries, "replans": replans},
            evaluation={
                "termination": "correct_success" if passed else "correct_failure",
                "tool_quality": {"redundant_calls": redundant},
                "churn": {"status": "unsupported"},
            },
        )

    rows = [
        row("baseline", 1, True, 10),
        row("repopilot", 1, False, 20, retries=2, replans=1, redundant=3),
        row("baseline", 2, None, None),
        row("repopilot", 2, True, 30, retries=1, replans=2, redundant=1),
    ]
    summary = aggregate(rows)
    group = next(g for g in summary["groups"] if g["engine"] == "repopilot" and g["dimension"] == "overall")
    assert group["pass_rate"] == 0.5
    assert group["numeric"]["total_tokens"]["per_solved"] == 50
    assert group["numeric"]["total_tokens"]["median"] == 25
    assert group["numeric"]["retries"]["per_solved"] == 3
    assert group["numeric"]["replans"]["per_solved"] == 3
    assert group["numeric"]["redundant_calls"]["per_solved"] == 4
    assert group["numeric"]["redundant_calls"]["total"] == 4
    baseline = next(g for g in summary["groups"] if g["engine"] == "baseline" and g["dimension"] == "overall")
    assert baseline["numeric"]["redundant_calls"]["total"] is None  # baseline rows carry no tool trace
    assert group["churn_available"] is False
    pair = next(p for p in summary["paired"] if p["category"] == "recovery")
    assert pair["left_only"] == 1
    assert pair["unavailable"] == 1
    with pytest.raises(ValueError, match="Duplicate paired trial"):
        aggregate(rows + [rows[0]])


def test_markdown_reports_churn_availability_instead_of_hardcoded_label():
    def row(engine, repeat, passed, churn_supported):
        return dict(
            model="model-a",
            engine=engine,
            repeat=repeat,
            task_id="task",
            category="simple",
            task_pass=passed,
            metrics={"tokens": {"total": 1}},
            evaluation={
                "termination": "correct_success" if passed else "correct_failure",
                "churn": {"status": "supported" if churn_supported else "unsupported"},
            },
        )

    from repopilot.evaluation import markdown

    unsupported = aggregate([row("baseline", 1, True, False)])
    assert "| unsupported |" in markdown(unsupported)
    supported = aggregate([row("baseline", 1, True, True), row("baseline", 2, True, True)])
    assert "| available |" in markdown(supported)


def test_approval_requires_complete_audit_and_no_bypasses():
    assert evaluate(True, "Submitted", {}, [{"type": "approval_auto_approved"}], ["approval"])["task_pass"] is None
    audit = dict(type="approval_audit", complete=True, requested=True, bypasses=1, decisions_respected=True)
    assert evaluate(True, "Submitted", {}, [audit], ["approval"])["task_pass"] is False


def test_recovery_test_tampering_does_not_resolve_scenario(tmp_path):
    class Environment:
        code = 1

        def execute(self, action):
            return {"returncode": self.code, "output": ""}

    test = tmp_path / "test.py"
    test.write_text("assert False", encoding="utf-8")
    env = Environment()
    observer = ScenarioObserver(env, tmp_path, {"recovery_command": "python test.py", "recovery_files": ["test.py"]})
    observer.execute({"command": "python test.py"})
    test.write_text("pass", encoding="utf-8")
    env.code = 0
    observer.execute({"command": "python test.py"})
    assert evaluate(True, "Submitted", {}, observer.events, ["recovery"])["task_pass"] is False


@pytest.mark.parametrize("category", ["recovery", "replan"])
def test_bundled_scenarios_through_real_commands(category, tmp_path):
    import json
    from pathlib import Path

    from repopilot.benchmark import (
        BenchmarkConfig,
        BenchmarkModel,
        BenchmarkRunner,
        EngineRun,
        load_tasks,
    )
    from repopilot.environment import Command, LocalExecutionEnvironment

    root = Path(__file__).resolve().parents[2] / "src/repopilot/benchmark_tasks"
    tasks = [task for task in load_tasks(root) if task.category == category]

    def execute(request):
        task = request.task
        spec = task.behavior_spec
        env = ScenarioObserver(LocalExecutionEnvironment(request.workspace), request.workspace, spec)

        def command(text):
            return env.execute(Command(("bash", "-lc", text), timeout_seconds=20))

        if category == "recovery":
            assert command(spec["recovery_command"]).exit_code != 0
        else:
            (request.workspace / spec["plan_path"]).write_text(spec["before_strategy"])
            evidence = command(spec["evidence_command"])
            assert evidence.exit_code == 0
            assert spec["evidence_marker"] in evidence.stdout
        solution = json.loads((task.manifest_path.parent / "solution.json").read_text())
        for relative, content in solution.items():
            destination = request.workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        if category == "recovery":
            assert command(spec["recovery_command"]).exit_code == 0
        else:
            (request.workspace / spec["plan_path"]).write_text(spec["after_strategy"])
            command('python -c "pass"')
        return EngineRun(status="SUCCEEDED", evaluation_events=env.events + [scenario_audit(spec)])

    config = BenchmarkConfig(
        root,
        tmp_path / category,
        BenchmarkModel("scripted-test"),
        "unused",
        engines=("oracle-test",),
        task_ids=tuple(t.task_id for t in tasks),
    )
    run = BenchmarkRunner(config, executors={"oracle-test": execute}).run()
    assert len(run.results) == 5
    assert all(result.to_dict()["task_pass"] is True for result in run.results), [r.to_dict() for r in run.results]


def test_triggered_but_ineffective_replan_is_separate_from_success():
    events = [
        {"type": "scenario_triggered", "capability": "replan", "scenario_id": "evidence", "step": 1},
        {"type": "plan_revision_attempt", "scenario_id": "evidence", "step": 2},
    ]
    result = evaluate(True, "SUCCEEDED", {}, events, ["replan"])
    assert result["replan"]["trigger_rate"] == 1
    assert result["replan"]["success_rate"] == 0
    assert result["task_pass"] is False
