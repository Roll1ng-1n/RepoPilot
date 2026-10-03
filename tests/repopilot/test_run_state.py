from __future__ import annotations

import pytest

from repopilot.artifacts import RunArtifacts
from repopilot.run_state import RunState


def test_lifecycle_rejects_unsupported_transitions_and_resumes_only_explicit_states(tmp_path):
    state = RunState("task", tmp_path, None, None, None, None, None, [], None, None)
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    with pytest.raises(ValueError, match="Invalid Run transition"):
        state.transition("SUCCEEDED", artifacts)
    state.transition("RUNNING", artifacts)
    state.transition("WAITING_FOR_APPROVAL", artifacts)
    with pytest.raises(ValueError, match="Invalid Run transition"):
        state.transition("SUCCEEDED", artifacts)
    state.transition("RUNNING", artifacts)
    state.transition("STOPPED", artifacts)
    state.transition("RUNNING", artifacts)
    state.transition("BUDGET_EXCEEDED", artifacts)
    state.transition("RUNNING", artifacts)
    state.transition("SUCCEEDED", artifacts)
    with pytest.raises(ValueError, match="Invalid Run transition"):
        state.transition("RUNNING", artifacts)
