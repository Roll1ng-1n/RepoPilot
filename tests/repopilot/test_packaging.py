from __future__ import annotations

from pathlib import Path

import tomllib


def test_swebench_evaluator_is_a_pinned_optional_dependency() -> None:
    repository_root = Path(__file__).parents[2]
    project = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["optional-dependencies"]["swebench"] == ["swebench==5.0.2"]
