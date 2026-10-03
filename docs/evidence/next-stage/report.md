# 下一阶段证据索引

本轮实现计量、跨步探索循环检测、状态重构、Checkpoint 内容对象与独立发行身份。模型方案和输入在调用前固定，原始失败保留。

- [计量与 schema 定义](metrics.md)
- [职责与生命周期](architecture.md)
- [固定计划](evaluation-plan.json)及[仅 Sol 的用户决定](plan-amendment.json)
- [全部模型样本与分组结果](model-report.md)
- [冻结源摘要](source-manifest.json)，离线检查为 5 tasks passed
- [Checkpoint 同机性能与恢复](performance/report.md)
- [本地发行构建](packaging/report.md)

真实 Sol 对照正在执行：5 tasks × 3 variants × 3 repeats = 45 formal samples；smoke 和符合预定规则的 replacement 单列。Luna 服务不可用，不运行正式样本。运行代码使用冻结源，不随当前代码变更而更新。全部完成后由 summarize.py 生成分组结果；未完成的样本不能算通过，少量样本不能证明普遍性能收益。
