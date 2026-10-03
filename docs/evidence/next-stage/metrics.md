# #31 指标与兼容语义

`operation_started`/`operation_finished` 用 monotonic 计时，以 run_id、span_id、step、request、tool_call_id 追溯来源。`active_run` 明确包围 Runtime 生命周期；嵌套区间暂停父区间的 exclusive time。模型请求包含摘要与重试，复用 RequestExecutor 的 `model_response.duration_seconds` 作 LLM 指标，操作 span 仅作覆盖审计，不再累加到 LLM 指标。工具只统计实际 execute，参数准备与审批属于框架时间。Checkpoint serialization/write_sync、repository_scan、source_scan、context_prepare 为细分，不能再加到框架总时间。

跨 Resume 按所有结束的 active_run 区间累计；两次区间之间的 UTC 差值单列 idle_seconds，不计入 active time。硬中断缺少结束事件时保留已测量的 tool/measured_orchestration，并把 active/orchestration 标为 null，coverage=partial。旧 Trace 全部为 unavailable；从旧运行恢复而来的混合记录也不冒充完整覆盖。CPU 调度、文件系统缓存和 Trace 写入成本都包含在所在观察区间内。

`source_changed` 记录 Git 可见源码的前后 SHA-256、路径、调用 ID 和步骤；不是 apply_patch 次数。无效/空修改不算，shell 编辑、删除、新建均可观察，生成缓存排除。当前限定 Python、JS/TS、Go、Rust、C/C++、Java、shell 常见扩展名；其他语言未支持。首次有效修改取首个有路径变化的事件，旧数据缺失为 null。此指标不声明支持完整 post-solution churn。

重复探索窗口为最近 12 个已完成的 read_file/search_code/list_files，按原始完整 Observation 摘要比较，只去掉 duration_seconds。路径规范化保留搜索词、offset、start_line/max_lines、max_results。文件变化和新验证证据分段，控制调用、等待、传输重试不产生探索结果。预览相同不能替代完整输出相同；历史记录无法观察 shell 中的读操作时保持未知。原有相邻冗余字段保留，新字段 window_repeated_exploration 独立增加。

Evaluation schema 从 5 增到 6，旧产物不改写。inspect --json 增加 evaluation；repository_pass/task_pass 保留三态，成功终止与 repository_pass 分开。汇总按模型、任务、引擎/变体报告数值分布和 true/false/null 分母。成本缺失保持 null。
