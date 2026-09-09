# 第三轮固定源码真实模型验证

本轮 12 个样本全部完成：仓库验证 12/12，任务要求 11/12。RepoPilot 的 8 个样本全部满足任务要求，其中 4 个以 SUCCEEDED 结束，另外 4 个达到 180 秒时间上限。无规划接口修复在本轮得到验证，但运行收尾仍受时间预算影响。

## 输入与验证

- 完整 Runtime Tests：259 passed，新增回归：9 passed。见 [完整回归](runtime-tests.txt)、[新增回归](regression-tests.txt)。[原 lint 输出](lint.txt)记录自动修复 1 项、剩余 0 项。
- [固定源码](source.tar.gz) SHA-256：`ad2ffa8c9608d94a460f4de40267066d705900dca5d70af4433ea4050891e61b`；启动前当前源码与[逐文件清单](source-manifest.json)一致。
- [运行脚本](run_real_models.py)校验源码归档、逐文件摘要和自身摘要后执行；两个模型独立并行，每个组合仅运行一次。
- 镜像：`sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6`；两个模型的预检均通过。
- 模型：`gpt-5.6-sol`、`gpt-5.6-luna`；服务：`https://jojocode.com/v1`；凭据从当前 `.env` 读取。分组由服务端控制，API 未报告分组标识，本地不能独立验证分组名称。
- 请求：`temperature=1`、`stream=true`、`timeout=30`、`max_tokens=2048`，未指定 reasoning_effort。
- 任务 manifest 覆盖配置后的实际预算：15 步、1 次 replan、连续失败阈值 2、180 秒、命令超时 30 秒。
- `smoke` 比较 baseline 与完整 RepoPilot；`no-planning` 使用相同固定源码，仅通过 `planning_enabled=False` 禁用规划。两阶段均执行原来的两个任务。

## 逐样本结果

所有样本的仓库 verifier 均通过。下表的“任务”还包含 manifest 要求的行为验证；它与成功终态分别计算。

| 阶段 | 模型 | 引擎 | 任务 | 任务通过 | 终态 | 秒 |
| --- | --- | --- | --- | --- | --- | ---: |
| smoke | sol | baseline | seed-single-file | 是 | Submitted | 82.9 |
| smoke | sol | repopilot | seed-single-file | 是 | SUCCEEDED | 158.0 |
| smoke | sol | baseline | recovery-public-failure | 否 | Submitted | 114.0 |
| smoke | sol | repopilot | recovery-public-failure | 是 | BUDGET_EXCEEDED | 180.4 |
| smoke | luna | baseline | seed-single-file | 是 | Submitted | 107.7 |
| smoke | luna | repopilot | seed-single-file | 是 | SUCCEEDED | 95.9 |
| smoke | luna | baseline | recovery-public-failure | 是 | Submitted | 96.2 |
| smoke | luna | repopilot | recovery-public-failure | 是 | BUDGET_EXCEEDED | 180.4 |
| no-planning | sol | repopilot | seed-single-file | 是 | SUCCEEDED | 37.0 |
| no-planning | sol | repopilot | recovery-public-failure | 是 | SUCCEEDED | 101.7 |
| no-planning | luna | repopilot | seed-single-file | 是 | BUDGET_EXCEEDED | 180.4 |
| no-planning | luna | repopilot | recovery-public-failure | 是 | BUDGET_EXCEEDED | 180.6 |

sol 的 baseline 恢复样本未被完整命令观察器观察到指定的公共测试失败与恢复场景，因此行为验证未通过；代码验证通过不能替代该行为要求。

4 个 BUDGET_EXCEEDED 样本的轨迹均明确记录 `limit=run_time`。这说明修复结果已通过外部验证，但 Agent Run 没有在预算内成功收尾，不能计作完整成功。

无规划模式的 4 个样本均调用了不带 `step_ids` 的 `verify_task`，未调用规划工具；sol 的两个样本成功收尾。因此此前无规划验证依赖计划步骤 ID 的接口问题本轮未再出现。每个组合仅一次，且包含服务延迟，不能据此认定规划或模型的统计优势，也不能把相对上一轮的改善单独归因于代码修复或服务分组。

## 证据核对

2026-09-09 审查勘误：下述原核对只验证了 benchmark 的 `metrics.patch` 摘要，没有交叉验证复制来的 Runtime `patch-manifest.json`。进一步检查发现 8/8 RepoPilot 样本的顶层 `patch.diff` 被 benchmark 覆盖，因而与 Runtime manifest 不匹配；`run-state/<run_id>/` 中原始补丁和 manifest 仍一致。仓库验证 12/12、任务要求 11/12 的统计不变，但不能据原核对宣称两层补丁证据完全一致。见[当前优先级审查](../../current-priority-review/report.md)及[补丁审计](../../current-priority-review/patch-audit.json)。

[核对脚本](audit_results.py)与[核对结果](result-audit.json)确认 12 个唯一 run_id、4 组完成汇总、固定源码引用、补丁 SHA-256、仓库 verifier 与任务布尔值、RepoPilot 最终轨迹状态和重试计数一致。无规划调用验证单独记录。sol 常规单文件样本的一次请求超时对应一次 RETRY_MODEL；luna 常规恢复样本的一次 VERIFICATION_FAILURE 对应一次 DEBUG_OBSERVATION。

[逐样本机器可读结果](results.json)保留原始 metrics、evaluation 和证据路径；[sol 日志](sol.log)、[luna 日志](luna.log)保留运行过程。费用与 tokens 为已报告用量；超时请求可能缺失用量，标准价格估算也不代表中转服务实际账单。

复核命令：`.venv/bin/python docs/evidence/issues-19-24/round3/audit_results.py`。运行时固定源码解压目录由 TemporaryDirectory 自动清理；样本工作区及轨迹保留作为证据。本轮未修改固定源码、提交或推送代码，未发布 issue 消息。
