# 剩余 Issues 验收核对（2026-09-09）

当前源码修复已提交为 `4a48eb0`，源码/测试与[269 项通过的验证摘要](issues-25-26/source-manifest.json)一致。本次核对未重复执行付费模型或原有完整回归。

## 可关闭：#18–#23

| Issue | 验收依据 | 结论 |
| --- | --- | --- |
| #18 Git 镜像 | [历史固定镜像与 Luna 配对 smoke](luna-git-image-smoke-v1/summary.md)记录相同镜像摘要、Python/Git 预检及两个引擎的 verifier；test_benchmark.py 的预检、缺失 Git 阻断及镜像一致性测试；README 中剩余 slim 示例已改为 Git/ripgrep 镜像。 | 环境缺陷已解决。历史任务未完成，不把它写成任务成功。 |
| #19 完成判定 | test_issue_regressions.py：最新失败、修改后失效、验证自身修改、required checks；test_priority_fixes.py：缓存、稳定检查 ID、替代关系、独立检查和旧记录重验。 | 完成；产品不依赖隐藏 verifier。 |
| #20 逐工具恢复 | test_reliability_v2.py：真实进程崩溃、同 Run 互斥锁、审批写入中断；test_issue_regressions.py：批次剩余调用保留；原有 CLI 审批/恢复测试。 | 完成；不承诺任意外部命令 exactly-once。 |
| #21 预算计量 | 假时钟累计恢复时间；主请求/摘要/重试共享计量；未知 usage 限制；明确时间预算的取消与进程后代终止；#26 新增预算续跑、延迟容忍回归。 | 按用户修订完成：默认无墙钟截止，仅显式时间预算有硬限制，不能恢复旧的默认强制截止要求。 |
| #22 工具与补丁 | 失败补丁分类、搜索无匹配、标准删除审批、大于 20KB 补丁；test_snapshot_replays_dirty_baseline_commits_binary_and_rename；#25 原始/规范化补丁与 manifest 分离。 | 完成；本地及 Docker 回归均已包含在无跳过的完整测试中。 |
| #23 模型协议 | 空流/错误参数/ID 保留、按到达序聚合多工具分片；streaming-only run/resume；配置优先级与凭据脱敏；鉴权失败不重试、暂时超时可重试。 | 完成；原生 Tool Calling 约束保留。 |

共同证据：[完整回归](issues-25-26/runtime-tests.txt)、[Ruff](issues-25-26/lint.txt)。历史分析中的缺陷以当前测试/源码为准，不按旧 Issue 未打勾的状态重复修复。

## 保留 #24：能继续解决，但有效消融尚未完成

仓库范围约束、忽略/分页、工具产物续读、上下文有界、doctor、inspect JSON 及历史证据索引均已有实现。当前剩余工作是让评测对照真正改变被测机制，并在当前修复版本上形成可信的结果，而不是再次收集相同的无效对照。

旧 round2 的 no-profile 在选定的两个小任务上没有配置 facts 可移除；no-context-selection 在很短的历史中也难以触发机制差异；旧 no-planning 的验证接口曾不完整。round3 重跑了 smoke 和修正后的 no-planning，但不是当前 #25/#26 修复后的四机制完整消融。不能把这些样本合并成“已经证明探索/上下文/规划/恢复收益”。

可执行的剩余工作：

1. 选用或补充确实含配置/测试入口的任务，以及能触发上下文选择的长历史任务；记录触发证据。短任务不用于声称长历史机制收益。
2. 对每个变体做离线有效性检查：no-profile 的输入确实少了配置 facts 且目录约束保留；no-context-selection 确实保留历史而非仍被通用裁剪；no-planning 不暴露计划接口；no-recovery 在定义的首次失败停止。
3. 固定当前源码、任务、镜像、采样和各任务实际预算；提供一次小规模配对执行入口，记录 true/false/null、成功终态、tokens、耗时、费用及恢复。
4. 执行后只报告观察到的差异。无显著收益也是有效结果，不能为满足“证明收益”而强行作出正向结论。

这项没有代码层面的不可解阻塞。模型/预算仍沿用已授权的小规模评测边界；本次“提交并核对剩余 Issues”没有追加付费运行。#24 保留为 ready-for-agent，不把历史无效消融当作验收通过。

仓库保留历史运行轨迹、源码归档、补丁和清单；可丢弃的 workspace Git 仓库和 run.lock 不进入提交。个人配置、独立项目评审稿与封面不属于本轮提交。
