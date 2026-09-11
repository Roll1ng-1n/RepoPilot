# Issue #24：固定小规模 smoke 与消融

当前保留 24/24 个正式样本。每个模型、任务、变体按预先规则选定一个结果；受影响单元另保留原试次。结果只作描述性比较。

源码固定为 `f707b0b90a0b6632c276f96dbf7d5bcb994d43fb`。两个模型为 `gpt-5.6-sol`、`gpt-5.6-luna`；每个运行使用独立初始工作区。smoke 的 baseline/full 直接复用于总表。用户授权后对预先选定的 9 个受上游错误或异常空响应影响的失败终态各重跑一次；全部 33 个试次保留，表中使用预选替换结果，不按结果优劣挑选。

最终 24 个单元：仓库通过 14/24，task_pass true/false/null 为 12/12/0。

本轮未证明 RepoPilot 的整体收益。两个 full 长历史样本都在反复探索后耗尽 48 步，最终补丁为空；所有消融效果必须结合空响应、传输错误和行为观察器限制解释。

## 结果

| 模型 | 变体 | 仓库通过 | task_pass true/false/null | 成功终止 | 已记录 tokens | 累计运行秒数 |
| --- | --- | --- | --- | --- | --- | --- |
| sol | baseline | 2/2 | 1/1/0 | 2/2 | 92330 | 322.1 |
| sol | full | 1/2 | 1/1/0 | 1/2 | 207915 | 810.9 |
| sol | no-profile | 1/2 | 1/1/0 | 1/2 | 37671 | 580.4 |
| sol | no-context-selection | 1/2 | 1/1/0 | 0/2 | 50714 | 139.6 |
| sol | no-planning | 1/2 | 1/1/0 | 1/2 | 160397 | 2319.0 |
| sol | no-recovery | 1/2 | 1/1/0 | 1/2 | 52998 | 134.0 |
| luna | baseline | 2/2 | 1/1/0 | 2/2 | 62848 | 427.8 |
| luna | full | 1/2 | 1/1/0 | 1/2 | 204943 | 828.8 |
| luna | no-profile | 1/2 | 1/1/0 | 1/2 | 275724 | 4157.0 |
| luna | no-context-selection | 1/2 | 1/1/0 | 1/2 | 37423 | 362.2 |
| luna | no-planning | 1/2 | 1/1/0 | 1/2 | 113857 | 1501.5 |
| luna | no-recovery | 1/2 | 1/1/0 | 1/2 | 47770 | 315.4 |

## 每个样本

ledger = profile-ledger；inventory = history-inventory。恢复次数为 Runtime 恢复决策数，baseline 不提供同等控制器数据，保留 null。

| 模型 | 变体 | 任务 | 仓库/task | 终态 | tokens | 秒数 | 记录 cost USD | 标准估算 USD | 恢复 | 裁剪 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| luna | baseline | inventory | true/false | Submitted | 44400 | 250.0 | 0.008746 | 0.008746 | null | 0 |
| luna | full | inventory | false/false | BUDGET_EXCEEDED | 163172 | 772.9 | 0.035264 | 0.035264 | 18 | 45 |
| luna | baseline | ledger | true/true | Submitted | 18448 | 177.7 | 0.004523 | 0.004523 | null | 0 |
| luna | full | ledger | true/true | SUCCEEDED | 41771 | 55.9 | 0.008431 | 0.008431 | 0 | 3 |
| luna | no-context-selection | inventory | false/false | BUDGET_EXCEEDED | 9402 | 198.9 | 0.002070 | 0.002070 | 1 | 0 |
| luna | no-context-selection | ledger | true/true | SUCCEEDED | 28021 | 163.3 | 0.005441 | 0.005441 | 0 | 0 |
| luna | no-planning | inventory | false/false | BUDGET_EXCEEDED | 98826 | 1420.3 | 0.022858 | 0.025899 | 30 | 29 |
| luna | no-planning | ledger | true/true | SUCCEEDED | 15031 | 81.2 | 0.003053 | 0.003053 | 0 | 0 |
| luna | no-profile | inventory | false/false | BUDGET_EXCEEDED | 162453 | 532.2 | 0.040393 | 0.040393 | 18 | 46 |
| luna | no-profile | ledger | true/true | SUCCEEDED | 113271 | 3624.8 | 0.022574 | 0.022574 | 21 | 17 |
| luna | no-recovery | inventory | false/false | FAILED | 5281 | 136.9 | 0.000928 | 0.000928 | 1 | 0 |
| luna | no-recovery | ledger | true/true | SUCCEEDED | 42489 | 178.5 | 0.006997 | 0.006997 | 0 | 3 |
| sol | baseline | inventory | true/false | Submitted | 74861 | 113.1 | 0.242836 | 0.242836 | null | 0 |
| sol | full | inventory | false/false | BUDGET_EXCEEDED | 158363 | 542.1 | 0.750057 | 0.750057 | 18 | 44 |
| sol | baseline | ledger | true/true | Submitted | 17469 | 209.0 | 0.088513 | 0.088513 | null | 0 |
| sol | full | ledger | true/true | SUCCEEDED | 49552 | 268.8 | 0.165152 | 0.165152 | 0 | 3 |
| sol | no-context-selection | inventory | false/false | BUDGET_EXCEEDED | 26813 | 50.2 | 0.098631 | 0.098631 | 1 | 0 |
| sol | no-context-selection | ledger | true/true | BUDGET_EXCEEDED | 23901 | 89.4 | 0.112996 | 0.112996 | 0 | 0 |
| sol | no-planning | inventory | false/false | BUDGET_EXCEEDED | 118911 | 1417.7 | 0.579535 | 0.596124 | 26 | 38 |
| sol | no-planning | ledger | true/true | SUCCEEDED | 41486 | 901.3 | 0.141180 | 0.141180 | 4 | 0 |
| sol | no-profile | inventory | false/false | BUDGET_EXCEEDED | 11212 | 373.3 | 0.057392 | 0.057392 | 5 | 0 |
| sol | no-profile | ledger | true/true | SUCCEEDED | 26459 | 207.1 | 0.099804 | 0.099804 | 0 | 0 |
| sol | no-recovery | inventory | false/false | FAILED | 6043 | 13.3 | 0.006473 | 0.006473 | 1 | 0 |
| sol | no-recovery | ledger | true/true | SUCCEEDED | 46955 | 120.7 | 0.195814 | 0.195814 | 0 | 3 |

## 固定条件与消融定义

- 固定 48 步、4 次 replan、5 次连续失败、命令超时 60 秒、整任务紧急上限 7200 秒。请求 timeout=120 秒、stream=true、temperature=1、max_tokens=4096；瞬时模型错误重试保留于所有变体。
- 镜像固定为 `sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6`。源码、脚本、任务配置和快照的 SHA256 见 [source-manifest.json](source-manifest.json)。运行顺序和 smoke 门槛见 [evaluation-plan.json](evaluation-plan.json)、[smoke-gate.json](smoke-gate.json)。
- no-profile 只移除自动配置 facts，保留目录指令；模型仍可自行读取配置。no-context-selection 禁用通用历史裁剪，超过相同的保守上下文预算时明确停止。no-planning 移除计划工具和 step_ids。no-recovery 停止任务/协议错误恢复，保留 MODEL_ERROR 的传输重试。
- full 使用生产默认 ContextStrategy.NONE 及请求前通用裁剪。baseline 使用上游原有上下文路径，未施加 RepoPilot 的 32768 UTF-8 字节估算限制；因此 baseline/full 的差异包含架构和工具开销，不能归因于单一机制。RepoPilot 消融组才用于比较对应开关。

## 指标解释与限制

- repository_pass 由隐藏验证器决定；task_pass 还包含行为要求；成功终止单列。inventory baseline 的观察器只匹配完整独立命令；首次失败测试还被复合 shell 命令后续成功操作掩盖退出码，自动 recovery/task_pass 为 false。轨迹中仍能看到初始失败及修复后的成功测试，因此不能把自动 false 解读为模型没有执行测试；未事后改写自动指标。
- ledger 用有来源的配置约束验证 profile 开关；inventory 是人为构造的长文档压力任务，六份合同带样例记录，用来触发上下文路径，不代表一般项目难度或分布。
- 单次样本不能支持统计显著性、模型排名或泛化胜率。恢复任务要求先运行失败测试，no-recovery 停止是该开关的预期后果，并不能独立证明恢复策略质量。
- cost 是框架记录的 provider/LiteLLM 数值；标准价格估算独立列示。中转站实际账单未获取，实际支付费用为 null。失败或中断请求可能缺少 usage，已记录的 tokens/cost 不能当作完整账单。
- 耗时包含中转站延迟，不用于推断模型本身速度。完整过程中的 churn、逐步仓库状态及部分恢复归因不受支持，原始结果保留 unsupported/null。

## 证据与复现

[audit.json](audit.json) 保留初始 24 个样本；[replacement-audit.json](replacement-audit.json) 记录 9 个替换试次；[effective-audit.json](effective-audit.json) 为最终 24 个单元，[replacement-comparison.json](replacement-comparison.json) 并列保留替换前后结果。这些文件提供每个样本的终态、usage、恢复决策、目录约束来源、计划调用、上下文触发和两层补丁校验。[diagnostics.json](diagnostics.json) 记录重复探索与 baseline 测试输出。每个 result_path 指向完整运行目录，包括 trace、流分片、checkpoint、verifier 和 patch。

离线验证：`.venv/bin/python docs/evidence/issue24-effective-ablation/offline_checks.py`。正式运行：`run.py --model gpt-5.6-sol --stage smoke --env-file .env`，审查后使用 `--stage ablation`；Luna 同理。已存在的完成组会跳过，不完整组拒绝覆盖。例如完整命令为 `.venv/bin/python docs/evidence/issue24-effective-ablation/run.py --model gpt-5.6-sol --stage smoke --env-file .env`。替换选择及脚本哈希见 `replacement-plan.json`；`rerun.py` 使用同一源码归档和任务预算。

结果审计：依次执行同目录的 `audit.py`、`audit.py replacements/attempt-1`、`diagnose.py`、`finalize.py`、`build_report.py`。源码归档独立保留于 `source.tar.gz`；环境版本记录在 manifest。

## 替换前后

异常列为传输错误响应数/空白且无工具响应数；空白响应只表示疑似上游影响。原始结果不删除，不将替换成功事后当作选择条件。

| 模型 | 变体 | 任务 | 原终态 → 替换终态 | 原仓库通过 → 替换仓库通过 | 原异常 → 替换异常 |
| --- | --- | --- | --- | --- | --- |
| gpt-5.6-luna | no-context-selection | profile-ledger | BUDGET_EXCEEDED → SUCCEEDED | true → true | 0/6 → 0/0 |
| gpt-5.6-luna | no-planning | history-inventory | BUDGET_EXCEEDED → BUDGET_EXCEEDED | false → false | 1/1 → 0/20 |
| gpt-5.6-luna | no-profile | history-inventory | BUDGET_EXCEEDED → BUDGET_EXCEEDED | false → false | 0/6 → 1/0 |
| gpt-5.6-sol | no-context-selection | history-inventory | BUDGET_EXCEEDED → BUDGET_EXCEEDED | false → false | 0/10 → 0/0 |
| gpt-5.6-sol | no-context-selection | profile-ledger | BUDGET_EXCEEDED → BUDGET_EXCEEDED | true → true | 0/5 → 0/0 |
| gpt-5.6-sol | no-planning | history-inventory | FAILED → BUDGET_EXCEEDED | false → false | 1/13 → 0/13 |
| gpt-5.6-sol | no-profile | history-inventory | BUDGET_EXCEEDED → BUDGET_EXCEEDED | false → false | 2/1 → 0/4 |
| gpt-5.6-sol | no-recovery | history-inventory | FAILED → FAILED | false → false | 3/1 → 0/0 |
| gpt-5.6-sol | no-recovery | profile-ledger | FAILED → SUCCEEDED | false → true | 2/1 → 0/0 |

## 后续问题

- [#27](https://github.com/Roll1ng-1n/RepoPilot/issues/27) P1：默认裁剪丢失已执行动作与阶段上下文，出现反复探索；见 [问题证据](followup-context.md)。
- [#28](https://github.com/Roll1ng-1n/RepoPilot/issues/28) P1：非传输失败挤占模型请求重试预算，第一次瞬时超时可能直接 STOP；见 [问题证据](followup-retry.md)。
- [#29](https://github.com/Roll1ng-1n/RepoPilot/issues/29) P2：复合 shell 测试无法识别时仍宣称完整观测并判 false；见 [问题证据](followup-observer.md)。

本轮生产源码保持固定；上述问题单列跟踪，不把完成评测报告等同于已经修复这些新发现。

## 全部试次的已记录资源用量

33 个试次累计记录 1,921,346 tokens，provider/LiteLLM cost 合计 $4.165239。包含原试次与替换试次；缺失请求 usage 未补算，不能视为完整账单。实际中转账单费用为 null。

校验摘要见 [final-checks.json](final-checks.json)：33 个唯一 Run ID，初始与替换审计均无不一致。
