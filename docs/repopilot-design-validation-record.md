# RepoPilot 设计验证记录

本文记录可复核的设计验证与失败，不把未完成的环境或 smoke 运行写成成功结果。

## 案例 1：Benchmark verifier 生成 `__pycache__`

- **现象**：Issue #13 扩展 benchmark 后，host-only verifier 在目标 workspace 中运行并导入目标模块，首次验证在 workspace 留下 `__pycache__`，导致“验证不应污染目标目录”的清洁性断言失败。
- **错误尝试**：直接用继承的 Python 环境启动 verifier，没有禁止字节码写入；只关注 verifier 的返回值，没有检查 workspace 的副作用。
- **根因**：verifier 的工作目录就是目标 workspace；Python 导入模块时默认生成 `.pyc`，于是写入 workspace 下的 `__pycache__`。
- **修复**：运行 host verifier 时传入 `PYTHONDONTWRITEBYTECODE=1`；相关回归辅助函数也使用同一设置。
- **验证**：回归断言检查 `workspace.rglob("__pycache__")` 为空；修复已随 `dc9aa0f` 固化。
- **关联 Commit/Issue**：Commit `dc9aa0f`（`feat: expand agent benchmark task suite (#13)`）；Issue `#13`。

## 案例 2：SWE-bench verifier 的 exit code 不等于 `resolved`

- **现象**：Issue #14 验收时发现，不能把官方 evaluator 进程的 `exit_code == 0` 直接解释为目标实例 `resolved`。进程正常结束只说明 evaluator 调用完成，实例级结果仍需读取报告中的 `resolved` 字段。当前真实 smoke 的 Docker、`/testbed` 和官方 gold patch verifier 前置均通过，preflight status 为 `READY` 且 `gold resolved=true`；随后授权低成本模型真实调用 5 次，Agent 在 `max_steps=5` 下以 `BUDGET_EXCEEDED` 结束、无 patch，最终 verifier 未运行，`success: null`。这是负面 smoke 证据，不是 SWE-bench 分数。
- **错误尝试**：用 verifier 进程的 exit code 设置 smoke 的 `success`，并把 Agent 的 `SUCCEEDED` 当作外部任务已解决；这混淆了进程健康状态、Agent 状态和实例级评测结果。
- **根因**：官方 evaluator 的命令返回状态与其按实例写出的评测报告是两个层次；原验收路径缺少对目标实例是否出现在 `resolved_ids` 中的明确读取与一致性判断。
- **修复**：#14 将成功判定改为读取官方 report 的 `resolved_ids`，同时保留进程 exit code 作为 evaluator 执行状态；报告缺失、格式无效或实例 unresolved 时不伪造成功。固定 revision 的 instance 也先物化为本地 `dataset.json`，再交给 gold preflight 和最终 verifier。
- **验证**：`test_unresolved_official_report_is_failure_even_when_command_exits_zero` 覆盖 `exit_code=0` 但 `resolved_ids=[]`，结果必须为 `FAILED_VERIFICATION` / `success: false`；新发布的真实 smoke 记录 `READY` / `gold resolved=true`，但 Agent 仍为 `BUDGET_EXCEEDED`、无 patch，最终 verifier 未运行且 `success: null`，证明 gold preflight 的 resolved 不能冒充 Agent 任务成功。模型调用 5 次，duration 27.4755s，`cost: null`；模型/endpoint 脱敏且 API key 扫描 clean。
- **关联 Commit/Issue**：Commit `630299f`（`feat: add pinned SWE-bench Lite smoke (#14)`）；Issue `#14`。
