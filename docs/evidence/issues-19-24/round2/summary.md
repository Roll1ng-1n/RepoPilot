# Issue #19–#24 第二轮实现与验收记录

后续更新：指定真实模型的 smoke 与固定消融已完成，见 [外部实验汇总](external/summary.md)和 [24 样本核对记录](external/result-audit.json)。smoke 8/8、消融 16/16 均已运行完毕；消融仓库验证通过 3/16、task_pass 1/16、成功终止 0/16。外部 smoke 另发现并修复 benchmark 适配器漏接 timeout_seconds 的问题，修复后完整回归为 250 passed。以下保留外部实验前的第二轮记录。

更新：2026-09-08。基线仍为 `933195fff117818a793834540def34896bee2738`，本轮包含第一轮的未提交修改。代码未提交、未推送，GitHub issue 未关闭。

**完整 RepoPilot Runtime Tests：249 passed，无跳过，25.16 秒。** [原始输出](runtime-tests.txt)与 [Ruff 输出](lint.txt)均保留。本次测试实际使用 Docker；没有调用付费模型。

## 本轮实现

| Issue | 新增实现 | 证据与结论 |
| --- | --- | --- |
| #19 | Task Verification 关联 Plan Step ID，记录顺序和前后指纹；新增 Plan Step 必须取得当前证据；完成判定写入 Checkpoint、Metadata、报告、inspect | 重新规划后旧检查不能覆盖新步骤；重验后可以完成。`COMPLETED` 标签本身不能代替验证。缺省 `step_ids` 表示当前计划的任务级检查，可显式指定子集。 |
| #20 | 内核持有的 `run.lock`；锁内重新核对 Checkpoint 和仓库；允许恢复失活 `RUNNING`；普通调用与审批调用共用逐项 pending/in-flight/result 保存；保存 execution_log | 真实子进程在写入后 `os._exit(91)`，恢复为结果未知观察，后续读取继续，原写入仅一次；另一进程不能取得同一锁；审批执行中断保留调用 ID 和 in-flight 状态。 |
| #21 | 统一 RequestExecutor 包含主请求、摘要、重试；记录用途/耗时/usage/cost；POSIX deadline 中断同步模型；普通 CLI 增加 token/cost 限额并恢复累计；Docker 内 GNU timeout 清理进程组 | 慢模型在延迟动作前被中断；主请求和摘要累计 token/cost，恢复保留计数；未知 usage/cost 在启用相应限额时阻止下一请求；Docker 超时后不存在延迟写入。 |
| #22 | 使用独立 Git index 构建运行起点/终点内容树，按原始字节 hash，不触发 clean filter；生成 Agent Run 内容增量、初始脏工作区补丁、工作区补丁及 SHA256/大小清单；完整工具结果与模型预览分离 | 用户原有未跟踪文件不进入 Agent 增量；运行内 commit、暂存、未暂存、重命名及二进制内容可在干净基线副本重放；真实用户 Git index 不变。 |
| #23 | 保留 finish_reason；拒绝执行截断/过滤响应中的调用；支持映射及 SDK 对象响应；可纠正协议错误走有界恢复；认证错误即使出现在多次重试后也立即停止；benchmark/campaign 共用连接配置解析 | run/resume 经实际 LiteLLM adapter、模拟 streaming-only completion 完成原生 verify/finish；中间中断后保留 stream 与 timeout，并累计三次请求。不是外部真实模型测试。 |
| #24 | 有界 Repository Profile；根目录及访问路径适用的 AGENTS.md；新发现局部约束时先返回观察再允许 patch；上下文保留配置来源/约束；完整产物续读；上下文请求上限；依赖拆分；终止审计与评测计划 | 根/子目录约束生效，兄弟目录约束不混入；模型可通过 read_artifact 按字符续读完整结果；长历史删去完整调用/result 组，必要约束放不下时明确 `BUDGET_EXCEEDED(context_window)`。 |

核心新增模块为 `locking.py`、`requests.py`、`repository_snapshot.py`、`profile.py`。定向故障测试见 [`test_reliability_v2.py`](../../../../tests/repopilot/test_reliability_v2.py)，第一轮回归仍见 [`test_issue_regressions.py`](../../../../tests/repopilot/test_issue_regressions.py)。

## 原始场景产物

这些是确定性 Runtime Test 的真实执行产物，模型为 scripted/fault-injection double，不是 Agent Benchmark：

- [进程崩溃恢复 Trace](scenarios/crash-recovery/trace.jsonl)、[Checkpoint](scenarios/crash-recovery/checkpoint.json)、[补丁清单](scenarios/crash-recovery/patch-manifest.json)。
- [审批执行中断 Checkpoint](scenarios/approval-interruption/checkpoint.json)：状态 STOPPED，`commit` 为 in-flight。
- [流式恢复 Trace](scenarios/streaming-resume/trace.jsonl)、[Checkpoint](scenarios/streaming-resume/checkpoint.json)：模拟服务只接受 stream，最终 SUCCEEDED。
- [摘要统一计量 Trace](scenarios/summary-accounting/trace.jsonl)、[Checkpoint](scenarios/summary-accounting/checkpoint.json)：主请求和摘要分别记录 purpose，并共同累计。

产物中的 `/tmp/pytest-*` 路径是当时的测试仓库身份，不是可直接恢复的生产仓库位置。复制保留的产物用于审查与复现代码逻辑。

## 使用与复现

```bash
# 轻量测试依赖；文档与外部数据集评测独立安装
python -m pip install -e '.[test]'
# 文档：python -m pip install -e '.[docs]'
# SWE-bench/数据集：python -m pip install -e '.[evaluation]'

.venv/bin/pytest tests/repopilot -q -rs
repopilot doctor --image python:3.12-bookworm

repopilot run /path/to/target --task '修复任务' \
  --required-verification 'pytest -q' --stream --request-timeout 30 \
  --max-output-tokens 2048 --max-total-tokens 50000 --max-cost-usd 1 \
  --context-window-tokens 32768 --env-file /path/to/provider.env
```

`resume/approve/reject` 保留非秘密模型配置和累计预算；可显式设置 `--max-total-tokens`、`--max-cost-usd`。所有连接入口使用显式 CLI > 进程环境 > 指定 env-file > Checkpoint 的优先级。凭据不写入 Checkpoint。

[环境记录](environment.json)和[依赖约束快照](dependency-constraints.txt)保存本次 Python 3.12 环境的安装版本；约束文件用于复现这个环境，不是跨平台锁文件。原有 `dev` extra 保留兼容性，新增加 `test/docs/evaluation` 入口；`datasets` 不再属于基础运行依赖。

Docker 集成测试使用 `python:3.12-bookworm`。另外已修正固定输入的 [`docker/benchmark/Dockerfile`](../../../../docker/benchmark/Dockerfile)，为真实评测补装 `ripgrep`；构建单独使用标签 `repopilot-benchmark:issues-19-24`，不覆盖历史镜像标签。构建通过，实际版本为 Python 3.12.14、Git 2.47.3、ripgrep 14.1.1；manifest list 为 `sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6`。见[构建原始输出](image-build.txt)。新镜像上另跑 Docker 相关用例为 **14 passed、38 deselected**，见[镜像测试输出](image-tests.txt)；这 14 项与完整回归有重叠，不累加成 263 项。

## 行为边界

- deadline 使用 POSIX 主线程 `setitimer`，锁使用 `flock`；目前验证的平台是 Linux/WSL。其他线程或不支持该机制的平台明确拒绝有界模型请求，不假装能够取消。服务商已经开始的请求仍可能计费，费用限额阻止后续请求，不能保证单个在途请求账单不超额。
- 未知 usage/cost 仍在 Trace 中为 null；Budget 的已知累计量另带 unknown 标记。不能把已知部分当成完整总量。
- 上下文以 UTF-8 字节数作为保守 token 上界，预留输出、schema 和协议空间；默认窗口 32768，可显式配置。它不是服务商精确 tokenizer，也不会为了塞进窗口而丢失必需约束；放不下即停止。
- AGENTS.md 是有目录范围的仓库数据，不提升为系统指令。路径工具及 patch 覆盖局部约束发现；任意 shell 内的动态目录访问不等同于完整命令分析。
- 结果不确定的写入不重放；重新观察后由模型决定下一步。不承诺任意外部命令的 exactly-once，也不保证逃离命令进程组的恶意程序能被取消。
- 新 Checkpoint schema 为 2，保留对 schema 1 的读取。旧记录缺失的历史活动时间或调用结果不能凭空恢复；旧验证无指纹必须重验，旧运行无起点快照的增量补丁归因标为 unsupported。
- 未配置必要命令时，成功只表示模型所选检查在当前状态通过；无任何验证仍为 UNVERIFIED。必要检查命令不由模型修改；运行时不读取隐藏 verifier。
- 补丁覆盖 Git 可见文件，不包含忽略的未跟踪文件。内容树是 Git 对象，运行及恢复期间应保留它们；产物目录必须在 Target Repository 外。submodule 保存其当前 commit，不递归收集未提交内部内容。
- `termination_audit` 保存终态、待执行与结果未知的调用；`budget_audit` 明确限定运行时调度范围，完整外部副作用审计仍为 false。HITL/长任务的联合行为评测据此继续保留 unsupported/null，不把新增测试伪装成完整行为得分。

## 剩余外部验证与评测输入

代码及确定性回归已完成本轮实现验证。**尚未运行外部真实模型 smoke、固定消融或新 campaign，也未产生新的模型收益结论。** [最终 doctor](doctor.json)确认 Docker Server/集成测试镜像可用，但未配置模型名及凭据。

[机器可读评测计划](evaluation-plan.json)固定两个任务 manifest 的摘要、两引擎、相同采样与预算。先显式选定模型与小预算，再运行：

```bash
repopilot benchmark --task seed-single-file --task recovery-public-failure \
  --engine baseline --engine repopilot --repeats 1 \
  --model "$REPOPILOT_MODEL" --env-file /path/to/provider.env --stream \
  --image repopilot-benchmark:issues-19-24 --temperature 0 \
  --max-steps 24 --max-replans 2 --max-consecutive-failures 3 \
  --max-run-seconds 120 --command-timeout-seconds 30 \
  --request-timeout 30 --max-output-tokens 2048
```

这是四个样本；大型付费 campaign 仍需单独指定模型和预算。探索、上下文、计划、恢复的消融必须先固定各实现变体的提交/补丁引用，并保持任务快照、模型、采样、预算、镜像相同。计划中的变体尚未执行，不能当成有消融结果的声明。

每次报告 `task_pass` true/false/null、仓库 verifier、成功终止、tokens、耗时、费用及恢复事件；保留原运行、替换试次和失败原因。已有 [72 种子样本](../../stage4-seed6-luna-sol-v1/summary.md)与 [288 扩展样本](../../stage4-24tasks-luna-sol-v1/summary.md)仍只是历史开发证据。
