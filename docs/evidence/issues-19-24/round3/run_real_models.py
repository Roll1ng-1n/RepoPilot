"""Pinned round3 smoke and corrected no-planning checks on the selected model group."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
IMAGE = 'sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['gpt-5.6-sol', 'gpt-5.6-luna'], required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((HERE / 'source-manifest.json').read_text())
    archive = HERE / 'source.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['archive_sha256']
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == manifest['runner_sha256']
    with tempfile.TemporaryDirectory(prefix='repopilot-round3-source-') as temporary:
        source = Path(temporary)
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter='data')
        for relative, expected in manifest['files'].items():
            assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == expected
        sys.path.insert(0, str(source / 'src'))
        from dotenv import dotenv_values
        import repopilot.benchmark as benchmark
        from repopilot.benchmark import BenchmarkBudget, BenchmarkConfig, BenchmarkModel
        values = dotenv_values(args.env_file)
        key = values.get('REPOPILOT_API_KEY')
        if not key:
            raise SystemExit('Missing REPOPILOT_API_KEY')
        registry_factory = benchmark.create_tool_registry

        def without_planning(request):
            def registry(*a, **kw):
                return registry_factory(*a, **kw, planning_enabled=False)
            with patch.object(benchmark, 'create_tool_registry', registry):
                return benchmark._run_repopilot(request)

        for stage in ('smoke', 'no-planning'):
            output = HERE / stage / args.model
            if (output / 'summary.json').exists():
                print(f'SKIP complete {stage}/{args.model}', flush=True)
                continue
            if output.exists():
                raise SystemExit('Preserve and review the interrupted output before retrying: ' + str(output))
            config = BenchmarkConfig(
                tasks_directory=source / 'src/repopilot/benchmark_tasks', output_directory=output,
                repeats=1,
                model=BenchmarkModel('openai/' + args.model, api_key=key, base_url='https://jojocode.com/v1',
                                     model_kwargs={'temperature': 1, 'stream': True, 'timeout': 30, 'max_tokens': 2048}),
                image=IMAGE,
                budget=BenchmarkBudget(max_steps=24, max_replans=2, max_consecutive_failures=3,
                                       max_run_seconds=120, command_timeout_seconds=30),
                engines=('baseline', 'repopilot') if stage == 'smoke' else ('repopilot',),
                task_ids=('seed-single-file', 'recovery-public-failure'),
            )
            output.mkdir(parents=True)
            (output / 'source-reference.json').write_text(json.dumps({
                'archive_sha256': manifest['archive_sha256'], 'runner_sha256': manifest['runner_sha256'],
                'planning_enabled': stage == 'smoke',
                'provider_group': 'user changed the group in .env; group identity not reported by the API',
            }, indent=2) + '\n')
            print(f'START {stage}/{args.model}', flush=True)
            run = benchmark.run_benchmark(config,
                executors=None if stage == 'smoke' else {'repopilot': without_planning},
                preflight_runner=benchmark.preflight_benchmark_image)
            for result in run.results:
                print(json.dumps({'stage': stage, 'model': args.model, 'task': result.task_id,
                                  'engine': result.engine.value, 'status': result.status,
                                  'repository_pass': result.success, 'task_pass': result.evaluation.get('task_pass')}), flush=True)
            print(f'DONE {stage}/{args.model}', flush=True)


if __name__ == '__main__':
    main()
