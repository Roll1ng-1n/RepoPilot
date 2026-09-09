"""Summarize raw results without converting unknown measurements into zeroes."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else {}


def rows_for(stage):
    rows = []
    paths = list((HERE / stage).rglob('result.json'))
    if stage == 'ablation':
        paths += list((HERE / 'continuation').rglob('result.json'))
    seen = set()
    for path in sorted(paths):
        data = read_json(path)
        metrics, evaluation = data.get('metrics', {}), data.get('evaluation', {})
        relative = path.relative_to(HERE)
        key = (relative.parts[1], relative.parts[2], data['task_id'], data['engine'])
        if key in seen:
            raise ValueError(f'Duplicate completed trial: {key}')
        seen.add(key)
        trace_path = path.parent / 'trace.jsonl'
        trace = [json.loads(line) for line in trace_path.read_text().splitlines()] if trace_path.exists() else []
        responses = [e for e in trace if e['type'] == 'model_response']
        metadata = read_json(path.parent / 'metadata.json')
        budget = metadata.get('budget', {})
        rows.append({
            'stage': stage, 'model': relative.parts[1], 'variant': relative.parts[2],
            'task': data['task_id'], 'engine': data['engine'],
            'status': data.get('status'), 'task_pass': evaluation.get('task_pass'),
            'repository_pass': evaluation.get('repository_pass'), 'behavior_pass': evaluation.get('behavior_pass'),
            'successful_termination': data.get('status') in ('SUCCEEDED', 'Submitted'),
            'duration_seconds': metrics.get('duration_seconds'),
            'tokens': metrics.get('tokens'),
            'known_trace_tokens': sum((e.get('usage') or {}).get('total_tokens') or 0 for e in responses) if responses else None,
            'trace_usage_complete': all(isinstance((e.get('usage') or {}).get('total_tokens'), int) for e in responses) if responses else None,
            'runtime_reported_cost_usd': metrics.get('cost'),
            'cost_coverage': 'partial' if budget.get('unknown_cost') else 'trace_complete' if responses else 'baseline_internal_retries_not_audited',
            'standard_price_estimate_usd': metrics.get('openai_standard_estimated_cost_usd'),
            'request_count': sum(e['type'] == 'model_request' for e in trace) if trace else metrics.get('llm_calls'),
            'request_errors': [e['error'] for e in responses if e.get('error')],
            'failures': [e for e in trace if e['type'] == 'failure'],
            'recovery_actions': dict(Counter(e.get('action') for e in trace if e['type'] == 'recovery')),
            'budget_exhausted': [e.get('limit') for e in trace if e['type'] == 'budget_exhausted'],
            'effective_budget': metrics.get('run_budget'),
            'verifier': data.get('verifier'), 'result': str(relative),
        })
    return rows


def score(rows, field):
    counts = Counter(r[field] for r in rows)
    return {'true': counts[True], 'false': counts[False], 'null': counts[None], 'samples': len(rows)}


def table(rows):
    result = ['| 模型 | 变体/引擎 | 任务 | 仓库验证 | 任务 | 终态 | 秒 |',
              '| --- | --- | --- | --- | --- | --- | ---: |']
    show = {True: '通过', False: '失败', None: 'null'}
    for r in rows:
        name = r['engine'] if r['stage'] == 'smoke' else r['variant']
        result.append(f"| {r['model'].removeprefix('gpt-5.6-')} | {name} | [{r['task']}]({r['result']}) | {show[r['repository_pass']]} | {show[r['task_pass']]} | {r['status']} | {r['duration_seconds']:.1f} |")
    return '\n'.join(result)


def main():
    smoke, ablation = rows_for('smoke'), rows_for('ablation')
    all_rows = smoke + ablation
    complete = len(smoke) == 8 and len(ablation) == 16
    grouped = defaultdict(list)
    for row in all_rows:
        grouped[(row['stage'], row['model'], row['variant'], row['engine'])].append(row)
    summary = {
        'status': 'COMPLETED' if complete else 'RUNNING',
        'expected': {'smoke': 8, 'new_ablation': 16},
        'completed': {'smoke': len(smoke), 'new_ablation': len(ablation)},
        'initial_configuration_failures': 8,
        'interrupted_attempts': read_json(HERE / 'interruptions.json'),
        'full_control_reused_from_smoke': 4,
        'total_distinct_corrected_trials': len(all_rows),
        'scores': [{'stage': key[0], 'model': key[1], 'variant': key[2], 'engine': key[3],
                    'task_pass': score(group, 'task_pass'), 'repository_pass': score(group, 'repository_pass')}
                   for key, group in grouped.items()],
        'rows': all_rows,
        'billing_total_usd': None,
        'billing_note': 'No relay invoice is available. Reported costs may cover only completed responses; standard prices are separate estimates.',
    }
    (HERE / 'results.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    ablation_pass = sum(r['task_pass'] is True for r in ablation)
    ablation_repo = sum(r['repository_pass'] is True for r in ablation)
    ablation_finished = sum(r['successful_termination'] for r in ablation)
    parts = [
        '# Issue #19–#24：第二轮外部模型验证与固定消融',
        f"状态：{'已完成' if complete else '运行中'}。smoke {len(smoke)}/8，新增消融 {len(ablation)}/16；另保留首批 8 个配置失败样本。",
        '服务地址 `https://jojocode.com/v1`；用户指定 `gpt-5.6-sol`、`gpt-5.6-luna`，授权费用不设上限。凭据从项目 `.env` 读取，不进入证据。',
        f'当前消融结果：task_pass {ablation_pass}/{len(ablation)}，仓库 verifier 通过 {ablation_repo}/{len(ablation)}，成功终态 {ablation_finished}/{len(ablation)}。task_pass 按任务 manifest 的代码及行为要求计算；这两个任务没有要求成功终止，因此它可能与 BUDGET_EXCEEDED 同时出现，不能将它表述为完整运行成功。',
        '## 实现修复与验证',
        '真实 smoke 发现 `_BenchmarkToolCallingModel.complete` 未接收 Runtime 的 `timeout_seconds`，导致进入服务请求前失败。已修复并添加穿过 RequestExecutor 与 LiteLLM 适配器的回归。完整 Runtime Tests：**250 passed，无跳过**，见 [原始输出](runtime-tests.txt)。',
        '首批 `temperature=0` 被 LiteLLM 判为不支持，保留于 [Sol 原始尝试](smoke-sol/) 与 [Luna 原始尝试](smoke-luna/)。修正后的全部对照使用 `temperature=1`、stream、请求 timeout 30 秒、输出上限 2048 tokens，未显式指定 reasoning_effort。',
        '## 固定输入与消融定义',
        '源码：[压缩快照](source.tar.gz)、[逐文件摘要及变体引用](source-manifest.json)。执行器：[run_evaluation.py](run_evaluation.py)、[队列顺序](run_ablation_suite.py)。[评测计划](evaluation-plan.json)记录入口和任务 manifest；[隔离检查](variant-checks.txt)验证各变体确实改变目标机制。',
        '镜像固定为 `sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6`。两个任务均保持原始快照、隐藏 verifier 和 manifest。manifest 覆盖 CLI 默认值后的真实预算为 15 步、1 次 replan、连续失败阈值 2、180 秒、命令超时 30 秒。',
        '- `full`：修复适配器后的完整版本；直接复用 smoke 中 4 个 RepoPilot 样本，避免重复计数。\n- `no-profile`：去掉自动配置概览 facts，保留目录范围的 AGENTS.md 约束。\n- `no-context-selection`：不删除历史、不压缩请求中的工具预览，保留同样的上下文上限，放不下时停止。默认策略原本就是 NONE，本实验不测试模型摘要。\n- `no-planning`：去掉模型可见计划与规划工具 schema；恢复时保留观察及预算计数，去掉计划修订。内部单一任务标识仍用于相同的验证归因。\n- `no-recovery`：首个 Runtime 分类失败立即停止；普通 shell 非零返回不一定被分类为失败，因此不等于禁用模型的一切自主纠错。',
        '每模型、任务、变体仅 1 次。两模型按相反变体顺序执行；队列并行，服务延迟可能影响时间预算。',
        '## 中断与续跑',
        '2026-09-08 中午中断后，两个样本停留在模型请求，晚间检查确认进程和容器均已退出。原始现场见 [中断清单](interruptions.json)。继续时跳过已完成的 3 个消融样本，对中断的 2 个样本从固定任务快照重新运行，并执行未启动的 11 个样本。新结果独立保存在 continuation/；中断试次不伪装成完整失败或成功，且不从原始证据中删除。不同时间段的服务状态是额外混杂因素。',
        '续跑入口：[run_remaining.py](run_remaining.py)，支持跳过已经落盘的完整结果；[单样本执行器](run_replacement.py)继续校验同一源码压缩包及变体摘要。',
        '## Smoke 原始结果', table(smoke),
        '## 消融原始结果', table(ablation),
        '## 结论边界',
        '连接和原生工具调用能够运行；这不等于真实任务验收通过。必须同时查看仓库 verifier、要求的行为、终态与 task_pass。Trace 中可见模型使用 `*** Begin Patch` 格式调用只接受 unified diff 的 apply_patch，恢复中重复相同格式，之后耗尽 replan 或时间预算。服务请求也存在超时。',
        '两个固定任务没有配置概览 facts，因此 no-profile 在这些快照上不改变模型输入；其分数差异不能归因为概览能力。短任务也不足以评估长历史筛选或摘要收益。单次配对且存在服务超时，不支持任何模型或机制的统计优势结论。',
        'baseline 的运行时限在模型轮次之间检查，内部请求及重试可超过 180 秒；原始耗时照录。RepoPilot 的 POSIX 总运行 deadline 保留。SDK timeout 30 秒不是整段流式响应的严格墙钟期限。',
        '已完成样本的唯一性、源码/配置一致性、verifier 与终态交叉核对见 [验收核对](result-audit.json)。',
        '费用和 tokens 见 [逐样本机器可读结果](results.json)。失败或超时请求可能没有 usage/cost；不能把成功响应累计视为完整消耗。`runtime_reported_cost_usd` 和项目自带 `standard_price_estimate_usd` 分开保存，均不能代替该中转服务的实际账单。',
        '所有原始失败样本保留。工作区代码未提交、未推送；本次未关闭任何 issue。',
    ]
    (HERE / 'summary.md').write_text('\n\n'.join(parts) + '\n')
    print(json.dumps(summary['completed']))


if __name__ == '__main__':
    main()
