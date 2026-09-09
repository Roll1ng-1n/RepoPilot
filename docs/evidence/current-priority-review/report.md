# RepoPilot 当前 P0 / P1 审查（2026-09-09）

修复前审查结论：当时未确认 P0，列出 6 项 P1 候选，审查时源码与 round3 一致。审查覆盖完成判定、请求预算、续跑、CLI 状态、仓库快照及 benchmark 产物；不是对所有安全边界的完整证明。

用户后续修正及处理结果：长首字延迟主要来自中转站，撤回“新增短的单请求硬截止”建议。普通运行改为默认无总时间截止，超时请求优先有界重试；显式开发/评测预算继续生效。其余问题已在 #25、#26 完成工作区修复，269 项回归通过。以下保留修复前的触发证据与原建议，当前行为以[修复记录](../issues-25-26/summary.md)为准。旧 reproduce.py 是修复前复现脚本，修复后应运行 test_priority_fixes.py。

分级口径：P0 为应立即停止使用的广泛数据破坏、已确认凭据外泄或核心路径普遍不可用；P1 为正常工作流中的严重可靠性、自动化或证据完整性缺陷，应在下一轮正式评测/交付前处理。P1-4、P1-5 同时属于产品行为缺口，不代表违背已有测试断言。

## P1-1：正常测试生成缓存，使成功验证被拒绝

影响：普通 Python import 产生未被 Git 忽略的 `__pycache__`，测试退出码为 0，finish_task 仍判 `stale_or_mutating_verification`。模型被迫清理缓存、重验和再次收尾，消耗额外请求；这不是代码修复失败。

位置：[tools.py](../../../src/repopilot/tools.py) 的 verify_task（417–437）和 finish_task（439–448）；[checkpoint.py](../../../src/repopilot/checkpoint.py) 的 capture_repository_state（23–44）将未跟踪缓存计入验证指纹。

证据：[离线复现](reproductions.json)的 `P1_cache_invalidates_successful_verification`。round3 8 个 RepoPilot 样本中，6 个出现过 finish_task 拒绝。示例：[sol 常规单文件轨迹](../issues-19-24/round3/smoke/gpt-5.6-sol/seed-single-file/repopilot/trace.jsonl)第 28、41 行。

建议：为验证定义明确的源码/配置输入集合和生成物策略，隔离正常缓存；保持对真实源码修改的失效检查。仅增加时间预算会掩盖问题。

## P1-2：验证记录以自由文本 scope 为身份，修复后重验仍被旧记录阻塞

影响：先以 `module behavior` 验证，修复或消除缓存影响后以 `module final behavior` 重验；即使新验证通过且指纹稳定，旧 scope 的失败/过期记录仍阻止完成。必须再次使用旧 scope 才能解除，接口没有明确的验证替代关系。

位置：[tools.py](../../../src/repopilot/tools.py)第 442–448 行，`latest = {item["scope"]: item for item in verifications}`。

证据：[离线复现](reproductions.json)的 `P1_scope_rename_keeps_obsolete_failure`；[luna 无规划单文件轨迹](../issues-19-24/round3/no-planning/gpt-5.6-luna/seed-single-file/repopilot/trace.jsonl)第 35、42 行，新验证成功后仍被旧 scope 阻塞，最终耗尽时间。

建议：引入稳定 check ID 与显式 supersedes/retry 关系，scope 仅作描述；required checks 仍必须独立满足，不能简单忽略所有旧失败。

## 原 P1-3（已撤回）：缺少每次模型请求的硬时限，一次流式请求可耗尽整次运行

影响：SDK timeout 不等于一次完整流式请求的总墙钟时限。流持续缓慢返回或 SDK 内部重试时，无法及时留出恢复和收尾预算。

位置：[requests.py](../../../src/repopilot/requests.py)第 72、99–101 行只以整次运行剩余时间设置 request_deadline；[model.py](../../../src/repopilot/model.py)第 77–78 行把配置 timeout 传给 SDK，没有单请求硬 deadline。

证据：round3 配置 timeout=30，但 [sol 常规恢复轨迹](../issues-19-24/round3/smoke/gpt-5.6-sol/recovery-public-failure/repopilot/trace.jsonl)第 51 行记录一次请求耗时 **115.436 秒**，最终因整次运行时间耗尽而终止。代码验证已通过。这证明预算分配问题，不表示供应商本身违反了 read timeout 语义。

建议：区分连接/读取超时与单请求总时限；硬时限取单请求上限和运行剩余时间的较小值。单请求超时应进入有预算的恢复，而非直接吞掉全部余量。

## P1-4：运行失败或预算耗尽，CLI 仍以退出码 0 结束

影响：shell、CI 和外部调度器只看退出码时，会将未完成任务视为成功。

位置：[cli.py](../../../src/repopilot/cli.py)第 94–99 行 print_result 只输出状态，run 第 266 行及 resume 第 755 行未把失败终态映射到非零退出码。

证据：[离线复现](reproductions.json)的 `P1_cli_failure_exit_zero`：实际状态 BUDGET_EXCEEDED，exit_code=0。现有 test_cli_run.py 第 126–127 行甚至明确断言此行为，因此原回归通过不能证明自动化语义正确。

建议：为成功、未验证、等待审批、暂停、失败/预算耗尽定义稳定退出码；保留机器可读的详细状态。

## P1-5：预算耗尽后没有显式追加预算并续跑的路径

影响：已经改好代码、仅差收尾的运行无法继续；用户必须开启新 Run，原有上下文和验证不能沿同一 Run 接续。round3 的 4 个 BUDGET_EXCEEDED 样本均满足外部任务要求，这个缺口直接影响已有工作的复用。

位置：[cli.py](../../../src/repopilot/cli.py)第 656–663 行只允许 STOPPED/RUNNING 续跑；resume 参数也没有增加 max_steps/max_run_seconds 的入口。

证据：[离线复现](reproductions.json)的 `P1_budget_exhaustion_cannot_resume`：resume 退出码 1，提示 cannot resume from BUDGET_EXCEEDED。

建议：允许用户显式追加预算并记录批准后的新上限，保留已消耗预算、仓库一致性检查和 in-flight 防重放；不要自动无限续跑。

## P1-6：benchmark 覆盖 Runtime 补丁，却留下不匹配的 manifest

影响：同一结果目录中的 patch.diff 与 patch-manifest.json 自相矛盾，消费者按 manifest 校验会失败；不能直接把该目录视为一套可重放的 Runtime 原始产物。

位置：[benchmark.py](../../../src/repopilot/benchmark.py)第 1232–1238 行复制 Runtime 产物，第 805–807 行重新生成并覆盖 patch.diff，未更新/隔离对应 manifest。benchmark 补丁会排除缓存且采用不同 diff 输出，内容或格式可能不同。

证据：[补丁审计](patch-audit.json)：round3 **8/8** RepoPilot 结果目录的 manifest 摘要不匹配。例：sol 常规单文件 manifest 记录 1227 bytes，实际补丁 350 bytes。每个目录 `run-state/<run_id>/` 中的原始补丁与原始 manifest 均仍匹配，故原始证据未丢失。

建议：分别保存 Runtime 原始补丁和 benchmark 规范化补丁，各自拥有匹配的 manifest；验收必须跨两层检查，不能只验证 metrics.patch 的自洽性。

## 已修复和不应夸大的结论

上一轮的流式分片乱序、补丁格式不兼容、恢复重复计数和 no-planning 步骤 ID 接口问题，已有新增回归与 round3 证据，不重复列为当前 P1。259 项回归是此前固定源码的结果，本次未重跑整套回归。

没有把“4/8 RepoPilot 达到时间上限”全部归因于单一缺陷：缓存、scope 和服务延迟分别有证据，但并非每个超时样本都经历相同链路。每组合一次，不能推断总体故障率或模型/规划机制的统计优势。

另观察到字节数代替 token 数的保守上下文预算、POSIX 主线程依赖、best-effort shell 审批限制；本次未发现足以把它们提升到 P0/P1 的新增影响证据。

## 复核与修复顺序

离线复现命令：`.venv/bin/python docs/evidence/current-priority-review/reproduce.py`。4 个本地复现断言全部通过；临时仓库自动清理，未调用付费模型，未修改运行时源码。

建议先修 P1-1/P1-2（正常完成路径）与 P1-4（自动化状态），再修 P1-3/P1-5（预算及续跑）；P1-6 应在下一轮评测前修复。源码固定清单与当前源码一致；本次只新增审查证据并补充 round3 报告的审计勘误，未创建或关闭 GitHub Issues。
