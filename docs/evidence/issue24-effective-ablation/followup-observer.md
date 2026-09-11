关联 #24；优先级 P2。固定小规模评测发现行为指标观测范围不足，可能把无法识别的行为记成失败。

## 证据

固定源码 `f707b0b90a0b6632c276f96dbf7d5bcb994d43fb`；新任务 history-inventory 的两个 baseline 都通过隐藏验证，但自动 recovery/task_pass=false。

原始 trajectory.json 显示初始 `python -m unittest discover -s checks` 确实失败，修复后也运行并通过。首次测试在复合 shell 命令中，后续操作掩盖了退出码。

`ScenarioObserver.execute` 只识别整条命令与 recovery_command 完全相等的情况，类说明也明确不推断复合 shell。但 `scenario_audit` 只检查 spec 有无 recovery_command，评估器随后把没有识别到场景解释成 complete observer 下的失败。

## 预期修复

无法可信识别复合命令内部测试结果时，应明确观测不完整，保留 null/unsupported，而非把未观测到当成模型未执行。可采用受信任测试包装器/独立行为验证器记录测试执行，不要用任意 stdout 文本猜测通过。

需要保留可确认缺失必需行为时的 false、可确认执行时的 true，以及无法判断时的 null。验证独立命令、复合命令、测试被篡改与未运行测试几类有实际差异的场景。

本轮自动指标不事后重写，人工轨迹核对与自动值分别列出，见 docs/evidence/issue24-effective-ablation/report.md、diagnostics.json。
