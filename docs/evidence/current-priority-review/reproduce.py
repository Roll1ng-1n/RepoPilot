"""Offline reproductions for the 2026-09-09 priority review; no source changes."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from repopilot.cli import create_app
from repopilot.environment import LocalExecutionEnvironment
from repopilot.model import AssistantTurn, ToolCall
from repopilot.plan import PlanHistory
from repopilot.tools import create_tool_registry


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout


def verify(registry, command, scope):
    return registry.dispatch(ToolCall('verify', 'verify_task', {'command': command, 'scope': scope, 'reason': 'review'}))['result']


def finish(registry):
    return registry.dispatch(ToolCall('finish', 'finish_task', {'root_cause': 'review', 'changes': ['review']}))['result']


def main():
    results = {}
    with tempfile.TemporaryDirectory(prefix='repopilot-review-') as temporary:
        root = Path(temporary) / 'target'
        root.mkdir()
        git(root, 'init', '-q')
        (root / 'module.py').write_text('VALUE = 1\n')
        git(root, 'add', '.')
        git(root, '-c', 'user.name=Review', '-c', 'user.email=review@example.invalid', 'commit', '-qm', 'initial')
        registry = create_tool_registry(LocalExecutionEnvironment(root), root, PlanHistory.for_task('Check module'))
        first = verify(registry, 'env -u PYTHONDONTWRITEBYTECODE python -c "import module; assert module.VALUE == 1"', 'module behavior')
        rejected = finish(registry)
        assert first['result']['exit_code'] == 0
        assert first['before_fingerprint'] != first['after_fingerprint']
        assert not rejected['completion_allowed']
        results['P1_cache_invalidates_successful_verification'] = {
            'verification_exit_code': first['result']['exit_code'],
            'generated_files': git(root, 'ls-files', '--others', '--exclude-standard').splitlines(),
            'completion_problems': rejected['problems'],
        }
        second = verify(registry, 'env -u PYTHONDONTWRITEBYTECODE python -c "import module; assert module.VALUE == 1"', 'module final behavior')
        rejected_again = finish(registry)
        assert second['before_fingerprint'] == second['after_fingerprint']
        assert not rejected_again['completion_allowed']
        results['P1_scope_rename_keeps_obsolete_failure'] = {
            'latest_verification_exit_code': second['result']['exit_code'],
            'latest_verification_stable': True,
            'completion_problems': rejected_again['problems'],
        }
        verify(registry, 'env -u PYTHONDONTWRITEBYTECODE python -c "import module; assert module.VALUE == 1"', 'module behavior')
        assert finish(registry)['status'] == 'SUCCEEDED'
        results['P1_scope_rename_keeps_obsolete_failure']['same_scope_retry_succeeds'] = True

        class Model:
            model_name = 'offline-review'

            def complete(self, messages, tools):
                return AssistantTurn(tool_calls=[ToolCall('read', 'read_file', {'path': 'module.py'})])

        state = Path(temporary) / 'state'
        app = create_app(model_factory=lambda _: Model())
        runner = CliRunner()
        run = runner.invoke(app, ['run', str(root), '--task', 'Review', '--state-dir', str(state), '--max-steps', '1'])
        assert run.exit_code == 0, run.output
        directory = next(state.iterdir())
        metadata = json.loads((directory / 'metadata.json').read_text())
        assert metadata['status'] == 'BUDGET_EXCEEDED'
        results['P1_cli_failure_exit_zero'] = {'exit_code': run.exit_code, 'status': metadata['status']}
        resume = runner.invoke(app, ['resume', directory.name, '--state-dir', str(state)])
        assert resume.exit_code == 1
        assert 'cannot resume' in resume.output
        results['P1_budget_exhaustion_cannot_resume'] = {'exit_code': resume.exit_code, 'output': resume.output.strip()}
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
