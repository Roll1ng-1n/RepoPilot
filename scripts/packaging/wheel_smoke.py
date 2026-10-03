"""Exercise an installed wheel offline, from outside the source checkout."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="repopilot-wheel-smoke-") as temporary:
        root = Path(temporary)
        os.chdir(root)
        for name in list(os.environ):
            if any(word in name.upper() for word in ("API_KEY", "TOKEN", "SECRET", "REPOPILOT_")):
                os.environ.pop(name)
        os.environ.update(MSWEA_SILENT_STARTUP="1", MSWEA_GLOBAL_CONFIG_DIR=str(root / "config"))
        from typer.testing import CliRunner

        import minisweagent
        import repopilot
        from repopilot.benchmark import load_tasks
        from repopilot.cli import create_app
        from repopilot.model import AssistantTurn, ToolCall

        distribution = importlib.metadata.distribution("repopilot-runtime")
        assert distribution.version == repopilot.__version__
        assert minisweagent.__version__ == "2.4.6"
        assert "site-packages" in str(Path(repopilot.__file__).resolve())
        files = [str(p) for p in distribution.files]
        assert any(p.endswith("share/repopilot/UPSTREAM.md") for p in files)
        assert any(p.endswith("share/repopilot/LICENSE.md") for p in files)
        assert list((minisweagent.package_dir / "config").rglob("*.yaml"))
        tasks = load_tasks(Path(repopilot.__file__).parent / "benchmark_tasks")
        assert len(tasks) == 30
        assert all(t.snapshot.is_dir() and t.verifier_path.is_file() for t in tasks)
        executable = str(Path(sys.executable).with_name("repopilot"))

        def cli(*args):
            result = subprocess.run([executable, *args], text=True, capture_output=True, check=True)
            return result.stdout

        assert "run" in cli("--help")
        assert cli("--version").strip() == f"RepoPilot {repopilot.__version__}"
        doctor = json.loads(cli("doctor"))
        assert "SECRET" not in json.dumps(doctor)
        repository = root / "target"
        repository.mkdir()
        (repository / "sample.py").write_text("value = 1\n")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "add", "sample.py"], cwd=repository, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Wheel Smoke", "-c", "user.email=smoke@example.invalid", "commit", "-qm", "seed"],
            cwd=repository,
            check=True,
        )
        patch = "--- a/sample.py\n+++ b/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
        turns = iter(
            [
                AssistantTurn(tool_calls=[ToolCall("edit", "apply_patch", {"patch": patch})]),
                AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            "verify",
                            "verify_task",
                            {
                                "command": f'{sys.executable} -c "import sample; assert sample.value == 2"',
                                "scope": "sample value",
                                "reason": "Check the requested change",
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
                                "root_cause": "Incorrect value",
                                "changes": ["Set value to 2"],
                            },
                        )
                    ]
                ),
            ]
        )

        class ScriptedModel:
            model_name = "offline-wheel-smoke"

            def complete(self, messages, tools):
                return next(turns)

        states = root / "runs"
        result = CliRunner().invoke(
            create_app(lambda _: ScriptedModel()),
            [
                "run",
                str(repository),
                "--task",
                "Set sample.value to 2 and verify it.",
                "--state-dir",
                str(states),
            ],
        )
        assert result.exit_code == 0, result.output
        run = next(states.iterdir())
        inspection = json.loads(cli("inspect", run.name, "--state-dir", str(states), "--json"))
        assert inspection["status"] == "SUCCEEDED"
        for name in (
            "metadata.json",
            "checkpoint.json",
            "trace.jsonl",
            "plan.json",
            "patch.diff",
            "verification.json",
            "task_report.md",
        ):
            assert (run / name).is_file(), name
        assert (repository / "sample.py").read_text() == "value = 2\n"
        print(
            json.dumps(
                {
                    "distribution": distribution.metadata["Name"],
                    "version": distribution.version,
                    "tasks": len(tasks),
                    "doctor": doctor,
                    "offline_run": "SUCCEEDED",
                    "inspect_stdout": "parseable JSON",
                    "model_calls": "scripted only",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
