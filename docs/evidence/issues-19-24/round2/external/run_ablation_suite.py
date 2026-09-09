"""Run four isolated variants in a predeclared order; smoke supplies the full control."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDERS = {
    'gpt-5.6-sol': ['no-profile', 'no-context-selection', 'no-planning', 'no-recovery'],
    'gpt-5.6-luna': ['no-recovery', 'no-planning', 'no-context-selection', 'no-profile'],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=list(ORDERS), required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    for variant in ORDERS[args.model]:
        print(f'Starting {args.model}: {variant}', flush=True)
        subprocess.run([sys.executable, str(HERE / 'run_evaluation.py'),
                        '--model', args.model, '--stage', 'ablation', '--variant', variant,
                        '--env-file', str(args.env_file.resolve())], check=True)
        print(f'Finished {args.model}: {variant}', flush=True)


if __name__ == '__main__':
    main()
