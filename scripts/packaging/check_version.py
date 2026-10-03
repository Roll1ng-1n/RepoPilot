"""Validate RepoPilot tags without importing the runtime or upstream config."""

from __future__ import annotations

import ast
import os
from pathlib import Path

tree = ast.parse(Path("src/repopilot/__init__.py").read_text())
version = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
)
ref = os.environ.get("REPOPILOT_RELEASE_REF", "")
if ref.startswith("refs/tags/") and ref != f"refs/tags/repopilot-v{version}":
    raise SystemExit(f"Tag {ref} does not match RepoPilot {version}")
print(f"RepoPilot {version}: build only; no package upload or release creation")
