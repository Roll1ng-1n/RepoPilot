"""Continue only missing trial slots; preserve all interrupted attempts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_ablation_suite import ORDERS

HERE = Path(__file__).resolve().parent
TASKS = ('seed-single-file', 'recovery-public-failure')


def completed_result(model, variant, task):
    original = HERE / 'ablation' / model / variant / task / 'repopilot/result.json'
    candidates = [original, *sorted((HERE / 'continuation' / model / variant / task).glob('attempt-*/*/repopilot/result.json'))]
    completed = [p for p in candidates if p.is_file()]
    if len(completed) > 1:
        raise ValueError(f'Multiple completed results for {model}/{variant}/{task}')
    return completed[0] if completed else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=list(ORDERS), required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    for variant in ORDERS[args.model]:
        for task in TASKS:
            previous = completed_result(args.model, variant, task)
            if previous:
                print(f'SKIP completed {args.model}/{variant}/{task}', flush=True)
                continue
            print(f'RUN missing {args.model}/{variant}/{task}', flush=True)
            if args.dry_run:
                continue
            parent = HERE / 'continuation' / args.model / variant / task
            number = 1
            while (parent / f'attempt-{number:03d}').exists():
                number += 1
            output = parent / f'attempt-{number:03d}'
            parent.mkdir(parents=True, exist_ok=True)
            audit = {
                'started_at': datetime.now(timezone.utc).isoformat(),
                'original_slot': str(Path('ablation') / args.model / variant / task),
                'new_attempt': str(output.relative_to(HERE)),
                'policy': 'Fresh pinned task snapshot and unchanged full run budget; prior interrupted artifacts retained.',
                'runner_sha256': hashlib.sha256((HERE / 'run_replacement.py').read_bytes()).hexdigest(),
            }
            (parent / f'attempt-{number:03d}-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
            subprocess.run([sys.executable, str(HERE / 'run_replacement.py'),
                            '--model', args.model, '--stage', 'ablation', '--variant', variant,
                            '--task', task, '--output-directory', str(output),
                            '--env-file', str(args.env_file.resolve())], check=True)
            result = completed_result(args.model, variant, task)
            if result is None:
                raise RuntimeError('Runner exited without a durable result')
            print(f'DONE {args.model}/{variant}/{task}', flush=True)


if __name__ == '__main__':
    main()
