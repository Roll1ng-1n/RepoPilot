"""Pin the current implementation and explicit, isolated ablation patches."""
from __future__ import annotations

import difflib
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    archive = HERE / 'source.tar.gz'
    if archive.exists():
        raise SystemExit('Source is already pinned; do not overwrite an evaluated implementation.')
    paths = sorted(p for p in (ROOT / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    paths += [ROOT / 'pyproject.toml', ROOT / 'docker/benchmark/Dockerfile']
    with tarfile.open(archive, 'w:gz') as tar:
        for p in paths:
            tar.add(p, arcname=str(p.relative_to(ROOT)), recursive=False)
    manifest = {
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'archive_sha256': digest(archive.read_bytes()),
        'files': {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths},
        'variants': {},
    }
    specs = {
        'full': ({}, 'Unmodified RepoPilot, including default NONE strategy and bounded request selection.'),
        'no-profile': ({'src/repopilot/profile.py': [('"facts": facts,', '"facts": [],')]},
            'Suppress automatic repository configuration facts; retain all scoped AGENTS.md constraints and path discovery.'),
        'no-context-selection': ({'src/repopilot/context.py': [
            ('while size() > available and len(steps) > 1:', 'while False:  # Ablation: retain complete history.'),
            ('if size() > available:\n            for message in selected:', 'if False:  # Ablation: no request preview compression.\n            for message in selected:')
        ]}, 'Retain full history without bounded eviction or preview compression; preserve the identical context ceiling and fail when it does not fit. Default strategy is NONE, so this does not test model summarization.'),
        'no-planning': ({
            'src/repopilot/tools.py': [('self._definitions.values()]', 'self._definitions.values() if definition.name not in {"update_plan", "replan"}]')],
            'src/repopilot/context.py': [('f"{prefix} Current Plan: {json.dumps(current_plan, sort_keys=True)}"', '"Use native tools to inspect and repair the Target Repository. Verify your work with verify_task and request completion with finish_task."')],
            'src/repopilot/runtime.py': [(
                '        step_id = self._next_recovery_step_id(budget)',
                '        messages.append({"role": "user", "content": f"Recovery Observation: {decision.reason}"})\n        return None\n        step_id = self._next_recovery_step_id(budget)'
            )],
        }, 'Remove model-visible plan and planning tool schemas; suppress automatic recovery replans while keeping recovery observations and replan budget charges. Retain one internal task identifier solely for unchanged verification attribution.'),
        'no-recovery': ({'src/repopilot/recovery.py': [(
            '        self.consecutive_failures += 1',
            '        self.consecutive_failures += 1\n        return RecoveryDecision(RecoveryAction.STOP, f"Ablation: stop at first classified failure: {failure.reason}")'
        )]}, 'Fail at the first runtime-classified failure; no controller retry, correction observation, or recovery replan. Model-driven correction after ordinary nonzero shell output can still occur because that output is not always a classified failure.'),
    }
    for name, (changes, description) in specs.items():
        patch = ''
        files = {}
        for relative, replacements in changes.items():
            original = (ROOT / relative).read_text()
            updated = original
            for before, after in replacements:
                if updated.count(before) != 1:
                    raise ValueError(f'{name}: expected exactly one match: {before}')
                updated = updated.replace(before, after)
            compile(updated, relative, 'exec')
            target = HERE / 'variants' / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(updated)
            files[relative] = digest(target.read_bytes())
            patch += ''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile='a/' + relative, tofile='b/' + relative))
        patch_path = HERE / 'variants' / (name + '.patch')
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(patch)
        manifest['variants'][name] = {'description': description, 'files': files, 'patch_sha256': digest(patch.encode())}
    (HERE / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Pinned source and five variant definitions:', manifest['archive_sha256'])


if __name__ == '__main__':
    main()
