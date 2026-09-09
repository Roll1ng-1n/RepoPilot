"""Verify ablation interventions before paid trials, in isolated interpreter processes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK = r'''
import json, sys, tempfile
from pathlib import Path
from repopilot.budget import BudgetExceeded
from repopilot.context import ContextManager
from repopilot.environment import LocalExecutionEnvironment
from repopilot.plan import PlanHistory
from repopilot.profile import repository_profile
from repopilot.recovery import Failure, FailureCategory, RecoveryAction, RecoveryController
from repopilot.tools import create_tool_registry
variant = sys.argv[1]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
    (root / 'AGENTS.md').write_text('Keep the public interface stable.')
    profile = repository_profile(root)
    assert bool(profile['facts']) == (variant != 'no-profile')
    assert profile['instructions'][0]['content'] == 'Keep the public interface stable.'
    plan = PlanHistory.for_task('repair fixture')
    registry = create_tool_registry(LocalExecutionEnvironment(root), root, plan)
    names = {s['function']['name'] for s in registry.schemas}
    assert ('update_plan' in names) == (variant != 'no-planning')
    assert ('replan' in names) == (variant != 'no-planning')
    assert {'verify_task', 'finish_task', 'apply_patch'} <= names
    context = ContextManager()
    messages = [{'role':'system','content':'Original instructions. Current Plan: {}'}, {'role':'user','content':'repair fixture'}]
    selected = context.prepare(messages, plan.current.to_dict()).messages
    assert ('Current Plan:' in selected[0]['content']) == (variant != 'no-planning')
    context.context_window_tokens = 6500
    history = messages + [{'role':'assistant','content':'old history ' * 1000}, {'role':'assistant','content':'recent history'}]
    try:
        bounded = context.bound_request(history, [])
        assert variant != 'no-context-selection'
        assert len(bounded) == 3
    except BudgetExceeded as exc:
        assert variant == 'no-context-selection' and exc.limit == 'context_window'
    decision = RecoveryController(3).recover(Failure(FailureCategory.VERIFICATION_FAILURE, 'failed fixture'))
    assert (decision.action == RecoveryAction.STOP) == (variant == 'no-recovery')
print(json.dumps({'variant':variant, 'intervention_checks':'passed'}))
'''


def main():
    manifest = json.loads((HERE / 'source-manifest.json').read_text())
    for variant, info in manifest['variants'].items():
        with tempfile.TemporaryDirectory(prefix='repopilot-variant-check-') as directory:
            root = Path(directory)
            with tarfile.open(HERE / 'source.tar.gz') as tar:
                tar.extractall(root, filter='data')
            for relative in info['files']:
                (root / relative).write_bytes((HERE / 'variants' / variant / relative).read_bytes())
            subprocess.run([sys.executable, '-c', CHECK, variant], check=True,
                           env={**os.environ, 'PYTHONPATH': str(root / 'src')})


if __name__ == '__main__':
    main()
