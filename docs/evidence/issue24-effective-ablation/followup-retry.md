关联 #24；优先级 P1。

## 问题

`RecoveryController.consecutive_failures` 同时累计 NO_PROGRESS、工具/验证失败和瞬时 MODEL_ERROR。瞬时请求错误的重试耗尽判断直接使用这个总计数，导致一次请求超时也可能被直接 STOP，尽管之前从未重试过模型请求。

这与用户要求“一次请求超时可以重试，尽量不要因为中转首字延迟强行结束任务”不符。这里需要调整重试计数语义，不是取消整任务预算或无限重试。

## 真实与离线证据

固定源码 `f707b0b90a0b6632c276f96dbf7d5bcb994d43fb`；初始试次：
`docs/evidence/issue24-effective-ablation/runs/gpt-5.6-sol/no-planning/history-inventory/repopilot/`。

轨迹记录验证失败及多次异常空响应产生 NO_PROGRESS，随后该试次第一次 MODEL_ERROR 为 APITimeoutError。最后恢复决策是 STOP / Model request retries exhausted，而非 RETRY_MODEL；该试次此前 MODEL_ERROR 数量为 0。

离线可使用 `RecoveryController(5)` 先输入 4 次 NO_PROGRESS，再输入 `MODEL_ERROR` 且 `transient_model_error=True`，现实现返回 STOP。源码：`src/repopilot/recovery.py:RecoveryController.recover`。

## 修复验收

- 独立记录连续传输错误重试次数，历史 NO_PROGRESS/验证失败不消耗传输重试预算。
- 第一次瞬时请求超时能够重试；不可达/连续传输失败仍有明确上限，永久认证/配置错误仍直接停止。
- 保持 checkpoint 恢复兼容及计数不重复，成功模型响应合理重置传输连续失败计数。
- no-recovery 实验/运行策略关闭任务恢复时仍保留传输重试。
- 增加混合类别失败与恢复 checkpoint 的有意义回归，不以缩短任务超时解决此问题。

用户已经授权对受上游因素影响的失败样本重跑，原试次保留，替换结果单列。即使替换成功也不删除上述真实缺陷证据。
