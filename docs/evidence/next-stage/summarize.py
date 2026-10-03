"""Offline descriptive reporting; include originals and replacements separately."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def distribution(values):
    known = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return {
        "values": values,
        "known": len(known),
        "unknown": len(values) - len(known),
        "median": statistics.median(known) if known else None,
        "min": min(known) if known else None,
        "max": max(known) if known else None,
        "known_total": sum(known) if known else None,
    }


def states(values):
    return {name: sum(v is state for v in values) for name, state in (("true", True), ("false", False), ("null", None))}


def main():
    plan = json.loads((HERE / "evaluation-plan.json").read_text())
    manifest = json.loads((HERE / "source-manifest.json").read_text())
    samples = []
    for path in sorted((HERE / "runs").glob("*/*/trial.json")):
        trial = json.loads(path.read_text())
        result = trial["result"]
        evaluation = result.get("evaluation") or {}
        metrics = result.get("metrics") or {}
        duration = evaluation.get("duration") or {}
        quality = evaluation.get("tool_quality") or {}
        progress = evaluation.get("progress") or {}
        counts = Counter()
        loops = 0
        observed_trace = False
        budget_limits = []
        model_errors = 0
        model_requests = 0
        cost_requests_known = 0
        token_requests_known = 0
        for trace in path.parent.glob("*/**/trace.jsonl"):
            if "workspace" in trace.parts or "run-state" in trace.parts:
                continue
            observed_trace = True
            for line in trace.read_text().splitlines():
                event = json.loads(line)
                if event.get("type") == "tool_call":
                    counts[event["tool_name"]] += 1
                if event.get("type") == "budget_exhausted":
                    budget_limits.append(event.get("limit"))
                if event.get("type") == "model_response" and event.get("error"):
                    model_errors += 1
                if event.get("type") == "model_request":
                    model_requests += 1
                if event.get("type") == "model_response":
                    cost = event.get("cost_usd")
                    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                        cost_requests_known += 1
                    total_tokens = (event.get("usage") or {}).get("total_tokens")
                    if isinstance(total_tokens, (int, float)) and not isinstance(total_tokens, bool):
                        token_requests_known += 1
                if event.get("type") == "exploration_loop_detected":
                    loops += 1
        samples.append(
            {
                "path": str(path.relative_to(HERE)),
                "model": path.parents[1].name,
                "stage": trial["stage"],
                "repeat": trial["repeat"],
                "replacement": trial["replacement"],
                "variant": trial["variant"],
                "task": result["task_id"],
                "status": result.get("status"),
                "source_matches": trial["source_sha256"] == manifest["archive_sha256"],
                "repository_pass": result.get("repository_pass"),
                "task_pass": result.get("task_pass"),
                "successful_termination": result.get("status") in {"SUCCEEDED", "Submitted"},
                "provider_failure": trial["provider_failure"],
                "terminal_budget_limits": budget_limits if observed_trace else None,
                "model_errors": model_errors if observed_trace else None,
                "model_requests_observed": model_requests if observed_trace else None,
                "cost_requests_known": cost_requests_known if observed_trace else None,
                "cost_requests_unknown": model_requests - cost_requests_known if observed_trace else None,
                "token_requests_known": token_requests_known if observed_trace else None,
                "token_requests_unknown": model_requests - token_requests_known if observed_trace else None,
                "steps": metrics.get("steps"),
                "tokens": (metrics.get("tokens") or {}).get("total"),
                "cost": metrics.get("cost"),
                "read_file": counts.get("read_file", 0) if result["engine"] == "repopilot" and observed_trace else None,
                "loop_events": loops if result["engine"] == "repopilot" and observed_trace else None,
                "window_repeated_exploration": quality.get("window_repeated_exploration"),
                "first_effective_source_change_step": progress.get("first_effective_source_change_step"),
                "timing_coverage": duration.get("coverage"),
                **{
                    key: duration.get(key)
                    for key in (
                        "wall_clock_seconds",
                        "llm_seconds",
                        "tool_seconds",
                        "orchestration_seconds",
                        "active_seconds",
                        "idle_seconds",
                    )
                },
            }
        )
    buckets = defaultdict(list)
    for sample in samples:
        key = (sample["model"], sample["task"], sample["variant"], sample["stage"], sample["replacement"])
        buckets[key].append(sample)
    numeric = [
        "steps",
        "tokens",
        "cost",
        "read_file",
        "loop_events",
        "window_repeated_exploration",
        "first_effective_source_change_step",
        "wall_clock_seconds",
        "llm_seconds",
        "tool_seconds",
        "orchestration_seconds",
        "active_seconds",
        "idle_seconds",
        "model_errors",
        "model_requests_observed",
        "cost_requests_known",
        "cost_requests_unknown",
        "token_requests_known",
        "token_requests_unknown",
    ]
    groups = []
    for key, rows in sorted(buckets.items()):
        groups.append(
            {
                "model": key[0],
                "task": key[1],
                "variant": key[2],
                "stage": key[3],
                "replacement": key[4],
                "n": len(rows),
                "repository_pass": states([r["repository_pass"] for r in rows]),
                "task_pass": states([r["task_pass"] for r in rows]),
                "successful_termination": states([r["successful_termination"] for r in rows]),
                "status_counts": dict(Counter(r["status"] for r in rows)),
                "timing_coverage_counts": dict(Counter(r["timing_coverage"] for r in rows)),
                "terminal_budget_limit_counts": dict(
                    Counter(limit for r in rows for limit in (r["terminal_budget_limits"] or []))
                ),
                "terminal_budget_limit_unknown_samples": sum(r["terminal_budget_limits"] is None for r in rows),
                "metrics": {name: distribution([r[name] for r in rows]) for name in numeric},
            }
        )
    formal = [s for s in samples if s["model"] == "gpt-6.1-sol" and s["stage"] == "formal" and not s["replacement"]]
    expected = len(plan["tasks"]) * len(plan["variants"]) * plan["repeats"]
    identities = {(s["task"], s["variant"], s["repeat"]) for s in formal}
    planned = {(t, v, r) for t in plan["tasks"] for v in plan["variants"] for r in range(1, plan["repeats"] + 1)}
    complete = (
        len(formal) == expected
        and identities == planned
        and (HERE / "runs/gpt-6.1-sol/completed.json").exists()
    )
    report = {
        "formal_originals": len(formal),
        "expected": expected,
        "complete": complete,
        "archive_integrity": hashlib.sha256((HERE / "source.tar.gz").read_bytes()).hexdigest()
        == manifest["archive_sha256"],
        "experiment_integrity": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest
            for name, digest in manifest["experiment_files"].items()
        },
        "all_sample_source_matches": all(s["source_matches"] for s in samples),
        "groups": groups,
        "samples": samples,
        "scope": "Small-sample descriptive results. Originals, smoke and replacements separate. Baseline shell reads and source-change steps are unobservable. Unknown metrics remain null.",
    }
    (HERE / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    text = [
        "# 固定真实模型对照结果",
        "",
        f"Sol 正式原试次 {len(formal)}/{expected}；完成状态 {complete}。所有原始样本、smoke 和 replacement 独立列出，未知数据保留 null。Luna 服务不支持该模型，仅保留失败 smoke，用户随后选择只跑 Sol。",
        "",
        "下表只汇总正式原试次，跨任务总数用于核对完整性；任务难度不同，具体差异以随后逐任务结果为准。",
        "",
        "| Variant | N | Repository T/F/null | Task T/F/null | Normal end |",
        "|---|---:|---|---|---:|",
    ]
    for variant in plan["variants"]:
        rows = [s for s in formal if s["variant"] == variant]
        repository = states([s["repository_pass"] for s in rows])
        task = states([s["task_pass"] for s in rows])
        repository_text = "/".join(str(repository[key]) for key in ("true", "false", "null"))
        task_text = "/".join(str(task[key]) for key in ("true", "false", "null"))
        normal = sum(s["successful_termination"] for s in rows)
        text.append(f"| {variant} | {len(rows)} | {repository_text} | {task_text} | {normal} |")
    text += [
        "",
        "所有中位数只使用已知数值；首次修改列附已知/null 样本数。该项 null 可能表示未发生实际源码修改，也可能表示缺少观测；逐样本记录保留该范围，不能将 null 当成第 0 步。",
        "",
        "| Model / task / variant / stage / replacement | N | Repository T/F/null | Task T/F/null | Normal end | Steps median | Tokens median | Repeated exploration median | First change step median (known/null) |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for g in groups:
        identity = f"{g['model']} / {g['task']} / {g['variant']} / {g['stage']} / {g['replacement']}"

        def tri(field):
            return "/".join(str(g[field][v]) for v in ("true", "false", "null"))

        def med(field):
            value = g["metrics"][field]["median"]
            return "null" if value is None else value

        change = g["metrics"]["first_effective_source_change_step"]
        first_change = f"{med('first_effective_source_change_step')} ({change['known']}/{change['unknown']})"
        text.append(
            f"| {identity} | {g['n']} | {tri('repository_pass')} | {tri('task_pass')} | {g['successful_termination']['true']} | {med('steps')} | {med('tokens')} | {med('window_repeated_exploration')} | {first_change} |"
        )
    text += [
        "",
        "时间单位为秒，均为已知值的中位数；费用为已知归一化美元值之和，同时列出已知/未知样本数，以及可观测请求中费用已知/未知的数量。样本费用非 null 也可能只覆盖部分请求。预算原因来自终态 Trace，baseline 的该项不可观测。",
        "",
        "| Model / task / variant / stage / replacement | Wall | LLM | Tool | Framework | Timing coverage | Cost subtotal (known/unknown samples) | Cost known/unknown requests | Budget stops |",
        "|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for g in groups:
        identity = f"{g['model']} / {g['task']} / {g['variant']} / {g['stage']} / {g['replacement']}"

        def number(field):
            value = g["metrics"][field]["median"]
            return "null" if value is None else f"{value:.3f}"

        cost = g["metrics"]["cost"]
        subtotal = "null" if cost["known_total"] is None else f"{cost['known_total']:.6f}"
        coverage = ", ".join(f"{key or 'null'}:{count}" for key, count in g["timing_coverage_counts"].items())
        limits = ", ".join(f"{key}:{count}" for key, count in g["terminal_budget_limit_counts"].items()) or "—"
        unknown_limits = g["terminal_budget_limit_unknown_samples"]
        if unknown_limits:
            limits = ("" if limits == "—" else limits + ", ") + f"null:{unknown_limits}"
        known = g["metrics"]["cost_requests_known"]["known_total"]
        unknown = g["metrics"]["cost_requests_unknown"]["known_total"]
        request_coverage = "null" if known is None or unknown is None else f"{known}/{unknown}"
        text.append(
            f"| {identity} | {number('wall_clock_seconds')} | {number('llm_seconds')} | {number('tool_seconds')} | {number('orchestration_seconds')} | {coverage} | {subtotal} ({cost['known']}/{cost['unknown']}) | {request_coverage} | {limits} |"
        )
    text += [
        "",
        "逐样本状态、成功终止、费用、各耗时及数值分布见 summary.json。费用使用 provider/LiteLLM 的归一化指标，汇总只累加已知值，unknown 分母同时保留；不是已审计的服务账单总额。tokens 同样只累加已知 usage，失败或无 usage 请求的实际消耗与收费不可观测；请求覆盖数量在 summary.json 中单列。框架/工具耗时仅在可观测 Trace 中报告，baseline 的未知指标不能当零。",
        "",
        "本次结果只能描述这些固定回归与压力任务。baseline 比较不能区分提示、工具和恢复机制的贡献；loop-on/off 是相同代码与预算的机制消融，但每组仅三次，不能宣称普遍因果收益。对收益未改善或合理重读失败的样本仍按原结果保留。冻结源包含当时的上下文边界缺陷，后续修复不回写这批结果。",
        "",
        "任务结果、未证明的机制收益及观测限制见 [对照结论](interpretation.md)；完整性检查见 [最终审计](audit.json)及[原始证据摘要](raw-evidence-manifest.json)。",
        "",
        "重新生成此报告不调用模型：python docs/evidence/next-stage/summarize.py。方案见 evaluation-plan.json、plan-amendment.json；离线快照与验证器检查见 offline.py。",
    ]
    (HERE / "model-report.md").write_text("\n".join(text) + "\n")
    print(json.dumps({"formal": len(formal), "expected": expected, "complete": complete}))


if __name__ == "__main__":
    main()
