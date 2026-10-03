# Issues #25 / #26 修复记录

工作区修复完成。完整 RepoPilot 回归 **269 passed，无跳过**；Ruff 与 git diff --check 通过。本轮新增 11 个确定性用例，并更新旧 CLI 测试的退出码约定；未调用付费模型或重跑真实模型评测。

## #25：验证完成、退出码和补丁证据

- 验证指纹忽略已知未跟踪测试缓存，真实源码/已跟踪文件仍受检查；Checkpoint 仓库一致性校验仍使用完整工作区指纹。
- verify_task 支持稳定 check_id 和按验证序号指定 supersedes。同命令可换 scope 重验，旧的同 scope 重验兼容保留。独立显式 ID 不会因 scope 相同而覆盖；required commands 不能被替代关系取消。finish_task 返回待重验的 ID、序号和纠正提示。
- CLI 返回 0=SUCCEEDED，1=FAILED/BUDGET_EXCEEDED，3=UNVERIFIED，4=WAITING_FOR_APPROVAL，5=STOPPED；参数错误仍为 2。
- benchmark 规范化补丁和 Runtime 原始补丁分开保存，各自的 manifest、大小、摘要和重放文件名匹配。新捕获的 benchmark 补丁也经过脱敏。历史 round3 目录保持原始证据和勘误，不追改已固定产物。

## #26：延迟容忍与显式续跑

按用户修正，撤回“短的单请求硬截止”建议。RunBudget / 普通 CLI run 默认无总时间截止，耗时照常计量。SDK 超时和暂时连接错误仍有界退避重试；已有成功工具结果不会随请求重试重放。步骤、replan、命令、token/cost 和显式时间预算保留，benchmark 仍使用固定有界预算。

BUDGET_EXCEEDED 支持显式修改预算后 resume：--max-steps、--max-replans、--max-run-seconds、--max-total-tokens、--max-cost-usd；--no-time-limit 可取消已保存的时间上限。上限是包含旧消耗的总量，已消耗计数、活动时间、Run ID、仓库一致性和防重放机制保留；变更记录为 budget_limits_changed。旧版数字时间预算与新版 null 时间预算均可读取。

## 证据

- [完整回归](runtime-tests.txt)：`.venv/bin/pytest tests/repopilot -q -rs`。
- [静态检查](lint.txt)：`.venv/bin/ruff check src/repopilot tests/repopilot`。
- [本轮源码摘要](source-manifest.json)：关联 round3 基线归档并记录当前源码/测试摘要。
- [新增回归](https://github.com/Roll1ng-1n/RepoPilot/blob/main/tests/repopilot/test_priority_fixes.py)：缓存与源码变动、scope 改名、独立检查、required command、默认无时间截止、一次超时重试、步骤耗尽续跑、补丁保真、旧版时间预算增加/取消及旧验证记录重验。
- [先前审查](../current-priority-review/report.md)保留问题触发证据并标注用户修正。

修复在现有工作区完成，未提交或推送代码。GitHub #25、#26 回填本轮实现和验证结果；#19–#24 的历史范围未一并关闭。本轮确定性回归证明接口和控制流修复，不代表已经获得新的真实模型成功率。
