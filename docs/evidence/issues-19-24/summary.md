# Issue #19–#24 第一批修复与验收证据

最新进展见[第二轮实现与验收记录](round2/summary.md)：249 项 Runtime Tests 全部通过，第一轮下方的待办表是当时的历史状态。

日期：2026-09-07。基线：`933195fff117818a793834540def34896bee2738`。
本次工作从干净工作区开始；代码尚未提交或发布，GitHub issue 未关闭。
[原始 issue 快照](issues.json)保存了六项需求及完整验收条件。本记录是阶段性修复证据，**不是六项 issue 全部完成的声明**。

## 已实现与验证

| Issue | 本批改动 | 回归证据 |
| --- | --- | --- |
| [#19](https://github.com/Roll1ng-1n/RepoPilot/issues/19) | 验证增加执行顺序及前后仓库指纹；同一 scope 以后一次结果为准；失败、旧状态、验证期间修改仓库均拒绝完成并继续运行；CLI 可重复指定必要验证命令，恢复保留契约 | `test_latest_failed_check_prevents_completion_and_can_recover`、`test_modified_repository_invalidates_previous_evidence`、`test_mutating_verification_does_not_prove_its_output`、`test_required_checks_are_independent`、CLI 恢复测试 |
| [#20](https://github.com/Roll1ng-1n/RepoPilot/issues/20) | 普通工具批次逐项保存 pending 队列及 in-flight 调用 ID，结果记录后保存剩余队列；中断结果未知的调用返回 `interrupted_result_unknown`，要求重新观察，不自动重复写入 | `test_interrupted_batch_preserves_remaining_calls_without_replaying_write` 实际写入后中断，恢复消息保持原调用 ID，写入只发生一次；原有审批恢复测试仍通过 |
| [#21](https://github.com/Roll1ng-1n/RepoPilot/issues/21) | Checkpoint 保存 `active_seconds_used`；恢复累计活动时间而不累计离线等待；模型前后、每个工具前后和退避检查剩余预算，工具 timeout 取剩余时间与命令配置的较小值；Local 超时/中断清理整个命令进程组 | 假时钟覆盖 9 秒执行 + 长离线等待 + 恢复后 1 秒耗尽；慢模型不能在返回后执行工具；批次耗尽不执行后续写入；真实子进程超时后不产生延迟写入 |
| [#22](https://github.com/Roll1ng-1n/RepoPilot/issues/22) | `applied=false` 映射 `TOOL_ERROR`；搜索无匹配仍是普通观察；补丁收集包含 staged/unstaged/untracked，使用完整命令输出；标准 unified diff 删除含时间戳的形式也需要审批 | 无效 patch 分类、rg 无匹配、标准删除两种形式；暂存新增 4,000 行文件，补丁超过 20,000 字符，末行保留且 `git apply --reverse --check` 通过 |
| [#23](https://github.com/Roll1ng-1n/RepoPilot/issues/23) | 空流和聚合失败抛明确协议错误，聚合数量/大小有上限并关闭迭代器；畸形参数保留 Tool Call ID 与错误，返回结构化纠正观察，不执行；普通 run/resume/approve/reject 暴露连接配置并恢复非秘密选项 | 空流/聚合失败；畸形参数 Checkpoint 快照往返后仍不可执行；CLI > 环境变量 > env-file > Checkpoint 优先级；stream/timeout/max_tokens 恢复；Checkpoint 不含测试密钥 |
| [#24](https://github.com/Roll1ng-1n/RepoPilot/issues/24) | 文件列表遵守 Git ignore、去重和分页；搜索全局行数上限并用 `--` 隔离查询参数；新增免费 doctor；上游启动 banner 改发 stderr；中英文 README 指向 30 任务证据并区分指标 | `.venv` 排除、分页与多文件搜索上限；doctor 不构造模型、不输出测试密钥；真实子进程 `inspect --json` stdout 可直接 `json.loads` |

定向用例位于 [`tests/repopilot/test_issue_regressions.py`](https://github.com/Roll1ng-1n/RepoPilot/blob/main/tests/repopilot/test_issue_regressions.py)。
本批沿用原生 Tool Calling；没有读取隐藏 benchmark verifier 来决定产品运行成功。

## 运行结果与复现

环境：Python 3.12.3、pytest 9.1.1、Git 2.43.0、ripgrep 15.2.0。使用现有 `.venv`，未调用付费模型。

```bash
.venv/bin/pytest tests/repopilot -q -rs
.venv/bin/ruff check src/repopilot/approval.py src/repopilot/budget.py src/repopilot/cli.py src/repopilot/doctor.py src/repopilot/environment.py src/repopilot/model.py src/repopilot/recovery.py src/repopilot/runtime.py src/repopilot/tools.py tests/repopilot/test_budget.py tests/repopilot/test_cli_run.py tests/repopilot/test_issue_regressions.py
.venv/bin/repopilot doctor
```

- [基线原始输出](baseline-runtime-tests.txt)：212 passed、2 skipped。
- [本批完整 Runtime Test 输出](runtime-tests.txt)：232 passed、2 skipped，共新增 20 个用例。
- 两项跳过来自沙箱内不能连接 Docker。沙箱外 `docker info` 已确认 Server 29.7.2 可用；默认测试镜像及历史评测镜像初始均缺失。沙箱外集成测试首次为 36 passed、1 error，唯一错误是首次拉取镜像触发上游 120 秒容器启动超时，见 [Docker/Local 原始输出](docker-runtime-tests.txt)。镜像就绪后仅重跑失败用例，[重试输出](docker-retry.txt)为 1 passed；检查确认未遗留该次失败容器。最终所有被选集成用例均通过，原失败保留。镜像 ID：`sha256:581429e3df12d76e6af4be5ab7d0e7fc2013eb57dc23d2de691411c8efdbb970`。
- [doctor 原始 JSON](doctor.json)是**沙箱内**诊断：Docker server unreachable、模型/凭据未配置。这个结果不能证明 Docker Desktop 未启动；doctor 只给 WSL 集成排查提示，不推断宿主桌面状态。
- 修改过的原有断言：Budget 允许新增活动时间计数；验证失败后的 `finish_task` 不结束，固定两步用例最终为 `BUDGET_EXCEEDED`。

上述数字全部是 Runtime Tests。没有新 Agent Benchmark，因此本批没有新的 `task_pass`、token、费用或模型胜率结论。

## 当前语义与兼容边界

`--required-verification 'command'` 可重复使用。必要命令在运行入口冻结，存于 Checkpoint 的 `environment.required_verifications`，恢复时重建 registry；模型无法更改契约。不同必要命令分别要求最终状态上的成功记录。

未配置契约时，`SUCCEEDED` 只表示模型所选检查在当前仓库状态上通过，`evidence_scope=model_selected_checks`，不证明任务意图全部满足。无契约且无验证记录仍允许明确的 `UNVERIFIED` 终态。已有失败或过期证据返回 `INCOMPLETE / completion_allowed=false`；必要命令缺失也拒绝完成。

旧 Checkpoint 无 `active_seconds_used` 时按 0 读取，无法补算历史活动时间；旧验证记录缺指纹时不能作为当前成功证据，需重新验证。旧 Checkpoint 无 in-flight 字段时不能补救历史已经丢失的调用。

`patch.diff` 当前是工作区相对当前 HEAD 的完整 diff，包含用户原有改动；**还不是精确归因的 Agent Run 增量**。运行内 commit 仍沿用既有 fallback，不承诺混合提交/脏工作区重放正确。

连接配置顺序为显式 CLI > 进程环境 > 指定 env-file > Checkpoint 的非秘密选项。stream/timeout/max_tokens 持久化；API key 不持久化。请求超时参数目前是服务商 timeout，并不等于能够取消任意同步模型适配器。

## 第一轮结束时尚未完成的验收条件（历史）

以下工作仍须继续，六个 issue 保持 open：

| Issue | 后续必须完成 |
| --- | --- |
| #19 | 明确 Plan Step 与验证身份绑定；完成判定原因在报告/inspect 的专用展示；覆盖更完整的恢复后证据失效矩阵。当前 scope 是检查身份，必要命令另按 command 核验。 |
| #20 | 统一审批执行分支的逐调用日志；进程锁/租约；允许核实失活后恢复 RUNNING；真实硬崩溃和并发 resume 测试。当前支持的是普通工具批次的受控中断恢复，不能宣称完整崩溃恢复。 |
| #21 | 可取消的模型请求执行器；摘要/重试/主请求统一用量路径；普通 run/resume 的 token/cost 限额及未知用量策略；审批分支预算；Docker 容器内后代进程取消。当前只有请求前后门禁，慢同步模型仍可能超时返回。 |
| #22 | 初始脏工作区与 Agent Run 增量精确归因；运行内 commit、二进制/重命名混合状态的重放测试；完整产物大小/摘要清单；模型预览和完整产物分离。完整 diff 目前也可能进入模型上下文。 |
| #23 | finish_reason/截断响应和所有响应 shape 的处理；空流/中断流纠正策略；benchmark/campaign 使用同一配置解析入口；主请求与摘要统一预算计量；真实 streaming-only 服务的小预算 smoke。 |
| #24 | 有界 Repository Profile 与嵌套 AGENTS.md；全量搜索/读取产物引用；token 上下文预算与完整协议配对保证；轻量依赖拆分；HITL/长任务终止审计及最终固定消融。当前全局搜索上限不提供截断部分继续读取入口。 |

## 后续固定 smoke 与消融方案

历史证据保持不变：[六种子任务 72 样本](../stage4-seed6-luna-sol-v1/summary.md) + [其余 24 任务 288 样本](../stage4-24tasks-luna-sol-v1/summary.md)，共 360 个开发样本。

先完成 #19–#23 的剩余条件，固定修复提交、任务 manifest 的 snapshot SHA256、镜像 digest、模型、temperature=0、流式选项及每项相同预算。小规模 smoke 使用 `seed-single-file` 和 `recovery-public-failure`，两个引擎各一轮，共四个样本：

```bash
repopilot benchmark --task seed-single-file --task recovery-public-failure \
  --engine baseline --engine repopilot --model "$REPOPILOT_MODEL" --stream
```

仅在显式指定可用模型与预算后执行。当前 doctor 没有模型/凭据配置；本批未运行该命令。大型付费 campaign 单独确认预算。

消融分别固定探索、上下文、计划和恢复为唯一变量；在同一快照/模型/采样/预算下保存完整运行目录，记录替换试次及失败原因。现阶段没有对应全部消融开关，不能将方案标成已实现评测能力。

每个样本报告：`task_pass` true/false/null、仓库 verifier、成功终止、token usage、耗时、provider cost、重试/恢复/重放/审批事件。费用缺失为 null；HITL 和长任务缺完整审计仍为 unsupported/null。比较原始计数和配对结果，不将 Runtime Test 通过数当成 Agent 成功率。
