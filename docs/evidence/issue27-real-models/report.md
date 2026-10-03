# #27 真实模型复测

用户授权后，使用固定源码 `a43d9245e02774167d61a29e439b5da18af601a2` 启动 Sol、Luna 各一次 `history-inventory` 复测。六个试次均已结束，审计结果见 `audit.json`。原始失败和 Luna 预算耗尽均保留；用户后来选择仅 gpt-6.1-sol，新版本 round4 独立验收满足完整标准。

沿用 #24 的任务快照、提示、Docker 镜像、48 步预算及模型参数；只运行 full RepoPilot。源码归档、文件 SHA-256 与预先验收条件保留于 `round1/`。原 #24 样本不覆盖。

```bash
.venv/bin/python docs/evidence/issue27-real-models/status.py
.venv/bin/python docs/evidence/issue27-real-models/audit.py
```

逐模型复现（已有运行目录时拒绝覆盖）：

```bash
.venv/bin/python docs/evidence/issue27-real-models/round1/run.py --model gpt-5.6-sol --env-file .env
.venv/bin/python docs/evidence/issue27-real-models/round1/run.py --model gpt-5.6-luna --env-file .env
```

上游失败处理规则在启动前固定于 `round1/evaluation-plan.json`：失败运行若包含传输错误或异常空响应，最多另行保留一次替换；算法性失败不按成败择优替换。

Docker 已恢复可用；此前涉及 Docker 的检查补跑 **14 passed, 37 deselected**，见 [docker-tests.txt](docker-tests.txt)。

## 完成后的只读审计

| 模型 | 原试次 | 按预先规则保留的替换试次 | 隐藏验证 | task_pass | read_file |
| --- | --- | --- | --- | --- | --- |
| Sol | FAILED，6 次模型服务错误 | SUCCEEDED | true | true | 22（旧版 215） |
| Luna | FAILED，8 次模型服务错误 | BUDGET_EXCEEDED | true | null | 114（旧版 217） |

源码归档、实验文件和两类 patch manifest 的摘要均通过。替换试次均产生仅涉及
`src/inventory/*.py` 的非空补丁，裁剪请求均保留历史回执与目录指令。
Sol 初次失败检查由 `run_command` 执行，不能因没有原生 `verify_task` 就断言未做初检。
Luna 修改后的原生验证未成功，`task_pass=null` 保留复合命令不可观测语义。
两个模型各仅一个替换样本，不足以证明普遍收益；不再次替换算法性失败。
未覆盖 #24 或已有运行的产物。

## 用户选择新模型后的独立验收

round3 使用原 a43d924 源码、同任务/镜像/48 步预算，仅换成用户指定的 gpt-6.1-sol。隐藏验证与 task_pass 为 true，但第 20 步因 context_window 停止。实测请求外层 JSON 漏算字节，裁剪后完整请求为 32,779，超过 32,768 上限 11 字节。原结果保留。

round4 是修复后的新版本验收，沿用 a43d924 加仅一项 envelope 字节计算修正，不含 #32 循环检测，不增加预算，不作为 round3 算法失败的 replacement。调用前固定新源码归档、计划与 SHA。结果为 SUCCEEDED / repository_pass=true / task_pass=true，17 次 read_file、1 次 apply_patch、1 次 verify_task。初检 run_command 失败，修改后的 verify_task 成功；非空补丁只涉及 src/inventory/*.py；源码、实验和 patch 校验通过，4 次裁剪请求保留回执，目录指令始终存在。

新模型不同于历史 5.6，因此 17 次读取只能描述当前样本，不能归因于上下文修复。单次真实验收与完整回归支持关闭本单，不表示每个模型或任务都能成功。复现：round4/run.py（已有目录拒绝覆盖）；新增边界回归为 test_context_envelope.py，最终完整 RepoPilot 301 passed、相关上游 46 passed。
