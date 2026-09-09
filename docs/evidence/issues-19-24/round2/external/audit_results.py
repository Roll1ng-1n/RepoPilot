"""Check unique trial slots, configuration identity, and raw evidence consistency."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from summarize import rows_for

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / 'evaluation-plan.json').read_text())
    manifest = json.loads((HERE / 'source-manifest.json').read_text())
    assert hashlib.sha256((HERE / 'source.tar.gz').read_bytes()).hexdigest() == manifest['archive_sha256']
    for variant, info in manifest['variants'].items():
        assert hashlib.sha256((HERE / 'variants' / f'{variant}.patch').read_bytes()).hexdigest() == info['patch_sha256']
        for relative, expected in info['files'].items():
            assert hashlib.sha256((HERE / 'variants' / variant / relative).read_bytes()).hexdigest() == expected
    rows = rows_for('smoke') + rows_for('ablation')
    seen = set()
    for row in rows:
        key = (row['stage'], row['model'], row['variant'], row['task'], row['engine'])
        assert key not in seen
        seen.add(key)
        path = HERE / row['result']
        config_dir = path.parent.parent.parent
        config = json.loads((config_dir / 'config.json').read_text())
        reference = json.loads((config_dir / 'source-reference.json').read_text())
        assert reference['archive_sha256'] == manifest['archive_sha256']
        assert reference['patch_sha256'] == manifest['variants'][row['variant']]['patch_sha256']
        assert config['model']['model_kwargs'] == {'temperature': 1, **plan['model_kwargs']}
        assert config['model']['model_name'] == 'openai/' + row['model']
        assert row['effective_budget'] == plan['effective_task_budget']
        assert config['image_id'] == 'sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6'
        assert config['repeats'] == 1
        if row['verifier'] is not None:
            assert row['repository_pass'] == (row['verifier']['exit_code'] == 0)
        assert (path.parent / 'evaluation-events.json').is_file()
        assert (path.parent / 'patch.diff').is_file()
        if row['engine'] == 'repopilot':
            trace = [json.loads(line) for line in (path.parent / 'trace.jsonl').read_text().splitlines()]
            finished = [e for e in trace if e['type'] == 'run_finished']
            assert finished and finished[-1]['status'] == row['status']
            checkpoint = json.loads((path.parent / 'checkpoint.json').read_text())
            assert checkpoint['status'] == row['status']
    expected = {
        ('smoke', model, 'full', task, engine)
        for model in ('gpt-5.6-sol', 'gpt-5.6-luna')
        for task in ('seed-single-file', 'recovery-public-failure')
        for engine in ('baseline', 'repopilot')
    } | {
        ('ablation', model, variant, task, 'repopilot')
        for model in ('gpt-5.6-sol', 'gpt-5.6-luna')
        for variant in ('no-profile', 'no-context-selection', 'no-planning', 'no-recovery')
        for task in ('seed-single-file', 'recovery-public-failure')
    }
    assert seen <= expected
    result = {'verified_samples': len(rows), 'expected_samples': len(expected),
              'missing': sorted(expected - seen), 'duplicate_slots': 0,
              'source_and_configuration_checks': 'passed',
              'terminal_and_verifier_checks': 'passed'}
    (HERE / 'result-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
