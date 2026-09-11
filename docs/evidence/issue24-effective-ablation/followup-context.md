关联 #24；固定源码 `f707b0b90a0b6632c276f96dbf7d5bcb994d43fb` 的新评测发现。

优先级：P1。长历史下核心任务持续无进展；修复应单列，避免改变正在运行的固定消融输入。

## 可复现证据

`docs/evidence/issue24-effective-ablation/` 的两个模型 full/history-inventory 均耗尽 48 步，隐藏验证失败，最终 patch 为 0 字节。

- Sol：44 次上下文裁剪、215 次 read_file、18 次 verify_task；没有 apply_patch。
- Luna：45 次上下文裁剪、217 次 read_file、18 次 verify_task；没有 apply_patch。
- checkpoint 的 ContextStrategy 为 none、summary=null、important_facts=[]。
- baseline 同任务两个模型都完成源码修复并通过隐藏验证。此对比包含上下文上限和工具开销差异，仅用于说明任务可完成，不能单独归因。
- `context-replay.json` 离线回放保留历史前缀，显示已执行的初始验证与合同读取会被删除。回放采用最终 checkpoint 的 profile/plan，是机制诊断，不冒充逐次原始请求快照。

## 机制与影响

`src/repopilot/context.py:bound_request` 在请求超限时删除旧 Tool Call/result 组；默认 none 不生成摘要，也没有把已验证的进度独立保存进请求。一次批量读取六份合同后，再读取源码就可能丢掉此前合同或初始测试记录。模型随后反复探索和重跑初始测试。

运行预算能最终停止，但无法恢复有效进展。单纯扩大步数或缩短超时不能解决信息丢失。

## 建议修复与验收

1. 为裁剪保留有界、可追溯的已完成动作/验证结果/当前阶段信息，并保留当前阶段必要合同内容或可继续读取的引用。
2. 处理单个批量工具组超大时的选择，避免整组反复读取与删除；不破坏 Tool Call/result 配对与目录约束。
3. 以本次 checkpoint 的离线回放建立有意义回归：已执行的初始测试在后续请求可辨识，摘要/事实预算有界，受保护约束保留。
4. 再验证长历史任务不出现相同重复探索循环。新增付费 campaign 不属于本次固定 24 样本；不得覆盖本轮失败样本。

原始轨迹、补丁和 verifier 保留在 runs/<model>/full/history-inventory/repopilot/，总表与限制见 report.md。
