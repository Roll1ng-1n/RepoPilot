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
    return {"values": values, "known": len(known), "unknown": len(values) - len(known),
            "median": statistics.median(known) if known else None,
            "min": min(known) if known else None, "max": max(known) if known else None,
            "known_total": sum(known) if known else None}


def states(values):
    return {str(state).lower(): sum(v is state for v in values) for state in (True, False, None)}


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
        for trace in path.parent.glob("*/**/trace.jsonl"):
            if "workspace" in trace.parts or "run-state" in trace.parts:
                continue
            for line in trace.read_text().splitlines():
                event = json.loads(line)
                if event.get("type") == "tool_call":
                    counts[event["tool_name"]] += 1
                if event.get("type") == "exploration_loop_detected":
                    loops += 1
        samples.append({
            "path": str(path.relative_to(HERE)), "model": path.parents[1].name,
            "stage": trial["stage"], "repeat": trial["repeat"],
            "replacement": trial["replacement"], "variant": trial["variant"],
            "task": result["task_id"], "status": result.get("status"),
            "source_matches": trial["source_sha256"] == manifest["archive_sha256"],
            "repository_pass": result.get("repository_pass"), "task_pass": result.get("task_pass"),
            "successful_termination": result.get("status") in {"SUCCEEDED", "Submitted"},
            "provider_failure": trial["provider_failure"], "steps": metrics.get("steps"),
            "tokens": (metrics.get("tokens") or {}).get("total"), "cost": metrics.get("cost"),
            "read_file": counts.get("read_file", 0) if result["engine"] == "repopilot" else None,
            "loop_events": loops if result["engine"] == "repopilot" else None,
            "window_repeated_exploration": quality.get("window_repeated_exploration"),
            "first_effective_source_change_step": progress.get("first_effective_source_change_step"),
            "timing_coverage": duration.get("coverage"),
            **{key: duration.get(key) for key in ("wall_clock_seconds", "llm_seconds", "tool_seconds",
                                                "orchestration_seconds", "active_seconds", "idle_seconds")},
        })
    buckets = defaultdict(list)
    for sample in samples:
        key = (sample["model"], sample["task"], sample["variant"], sample["stage"], sample["replacement"])
        buckets[key].append(sample)
    numeric = ["steps", "tokens", "cost", "read_file", "loop_events", "window_repeated_exploration",
               "first_effective_source_change_step", "wall_clock_seconds", "llm_seconds", "tool_seconds",
               "orchestration_seconds", "active_seconds", "idle_seconds"]
    groups = []
    for key, rows in sorted(buckets.items()):
        groups.append({"model": key[0], "task": key[1], "variant": key[2], "stage": key[3],
                       "replacement": key[4], "n": len(rows),
                       "repository_pass": states([r["repository_pass"] for r in rows]),
                       "task_pass": states([r["task_pass"] for r in rows]),
                       "successful_termination": states([r["successful_termination"] for r in rows]),
                       "status_counts": dict(Counter(r["status"] for r in rows)),
                       "metrics": {name: distribution([r[name] for r in rows]) for name in numeric}})
    formal = [s for s in samples if s["model"] == "gpt-6.1-sol" and s["stage"] == "formal" and not s["replacement"]]
    expected = len(plan["tasks"]) * len(plan["variants"]) * plan["repeats"]
    identities = {(s["task"], s["variant"], s["repeat"]) for s in formal}
    planned = {(t, v, r) for t in plan["tasks"] for v in plan["variants"] for r in range(1, plan["repeats"] + 1)}
    complete = identities == planned and (HERE / "runs/gpt-6.1-sol/completed.json").exists()
    report = {"formal_originals": len(formal), "expected": expected, "complete": complete,
              "archive_integrity": hashlib.sha256((HERE / "source.tar.gz").read_bytes()).hexdigest() == manifest["archive_sha256"],
              "groups": groups, "samples": samples,
              "scope": "Small-sample descriptive results. Originals, smoke and replacements separate. Baseline shell reads and source-change steps are unobservable. Unknown metrics remain null."}
    (HERE / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    text = ["# 固定真实模型对照结果", "", f"Sol 正式原试次 {len(formal)}/{expected}；完成状态 {complete}。所有原始样本、smoke 和 replacement 独立列出，未知数据保留 null。Luna 服务不支持该模型，仅保留失败 smoke，用户随后选择只跑 Sol。", "",
            "| Model / task / variant / stage / replacement | N | Repository T/F/null | Task T/F/null | Normal end | Steps median | Tokens median | Repeats median | First change median |", "|---|---:|---|---|---:|---:|---:|---:|---:|"]
    for g in groups:
        identity = f"{g['model']} / {g['task']} / {g['variant']} / {g['stage']} / {g['replacement']}"
        def tri(field):
            return "/".join(str(g[field][v]) for v in ("true", "false", "none"))
        def med(field):
            return g["metrics"][field]["median"]
        text.append(f"| {identity} | {g['n']} | {tri('repository_pass')} | {tri('task_pass')} | {g['successful_termination']['true']} | {med('steps')} | {med('tokens')} | {med('window_repeated_exploration')} | {med('first_effective_source_change_step')} |")
    text += ["", "逐样本状态、成功终止、费用、各耗时及数值分布见 summary.json。费用汇总只累加已知值，unknown 分母同时保留。框架/工具耗时仅在可观测 Trace 中报告，baseline 的未知指标不能当零。", "",
             "本次结果只能描述这些固定回归与压力任务。baseline 比较不能区分提示、工具和恢复机制的贡献；loop-on/off 是相同代码与预算的机制消融，但每组仅三次，不能宣称普遍因果收益。对收益未改善或合理重读失败的样本仍按原结果保留。冻结源包含当时的上下文边界缺陷，后续修复不回写这批结果。", "",
             "重新生成此报告不调用模型：python docs/evidence/next-stage/summarize.py。方案见 evaluation-plan.json、plan-amendment.json；离线快照与验证器检查见 offline.py。"]
    (HERE / "model-report.md").write_text("\n".join(text) + "\n")
    print(json.dumps({"formal": len(formal), "expected": expected, "complete": complete}))


if __name__ == "__main__":
    main()
