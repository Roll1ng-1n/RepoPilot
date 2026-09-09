"""Run a pinned real-provider benchmark; credentials are read only from the supplied env file."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['gpt-5.6-sol', 'gpt-5.6-luna'], required=True)
    parser.add_argument('--stage', choices=['smoke', 'ablation'], required=True)
    parser.add_argument('--variant', choices=['full', 'no-profile', 'no-context-selection', 'no-planning', 'no-recovery'], default='full')
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--task', choices=['seed-single-file', 'recovery-public-failure'], required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((HERE / 'source-manifest.json').read_text())
    archive = HERE / 'source.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['archive_sha256']
    variant = manifest['variants'][args.variant]
    output = args.output_directory.resolve()
    if output.exists():
        raise SystemExit(f'Refusing to overwrite {output}')
    with tempfile.TemporaryDirectory(prefix='repopilot-evaluation-source-') as temporary:
        root = Path(temporary)
        with tarfile.open(archive) as tar:
            tar.extractall(root, filter='data')
        for relative, expected in manifest['files'].items():
            assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
        for relative, expected in variant['files'].items():
            data = (HERE / 'variants' / args.variant / relative).read_bytes()
            assert hashlib.sha256(data).hexdigest() == expected
            (root / relative).write_bytes(data)
        sys.path.insert(0, str(root / 'src'))
        from dotenv import dotenv_values
        from repopilot.benchmark import (
            BenchmarkBudget, BenchmarkConfig, BenchmarkModel,
            preflight_benchmark_image, run_benchmark,
        )
        values = dotenv_values(args.env_file)
        key = values.get('REPOPILOT_API_KEY')
        if not key:
            raise SystemExit('Missing REPOPILOT_API_KEY in env file')
        engines = ('baseline', 'repopilot') if args.stage == 'smoke' else ('repopilot',)
        config = BenchmarkConfig(
            tasks_directory=root / 'src/repopilot/benchmark_tasks',
            output_directory=output,
            repeats=1,
            model=BenchmarkModel(
                model_name='openai/' + args.model,
                api_key=key,
                base_url='https://jojocode.com/v1',
                model_kwargs={'temperature': 1, 'stream': True, 'timeout': 30, 'max_tokens': 2048},
            ),
            image='sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6',
            budget=BenchmarkBudget(max_steps=24, max_replans=2, max_consecutive_failures=3,
                                   max_run_seconds=120, command_timeout_seconds=30),
            engines=engines,
            task_ids=(args.task,),
        )
        output.mkdir(parents=True)
        (output / 'source-reference.json').write_text(json.dumps({
            'archive_sha256': manifest['archive_sha256'],
            'variant': args.variant,
            'patch_sha256': variant['patch_sha256'],
            'definition': variant['description'],
            'provider_base_url': 'https://jojocode.com/v1',
            'financial_limit_usd': None,
            'repeats': 1,
        }, indent=2) + '\n')
        result = run_benchmark(config, preflight_runner=preflight_benchmark_image)
        for item in result.results:
            print(json.dumps({'model': args.model, 'variant': args.variant, 'task': item.task_id,
                              'engine': item.engine.value, 'status': item.status,
                              'task_pass': item.evaluation.get('task_pass')}), flush=True)


if __name__ == '__main__':
    main()
