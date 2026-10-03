# 下一阶段证据索引

本轮实现计量、跨步探索循环检测、状态重构、Checkpoint 内容对象与独立发行身份。模型方案和输入在调用前固定，原始失败保留。

- [计量与 schema 定义](metrics.md)
- [职责与生命周期](architecture.md)
- [固定计划](evaluation-plan.json)及[仅 Sol 的用户决定](plan-amendment.json)
- [对照结论与限制](interpretation.md)、[全部模型样本与分组结果](model-report.md)与[模型客户端环境](model-client-environment.json)
- [冻结源摘要](source-manifest.json)，离线检查为 5 tasks passed
- [离线完整性审计](audit.py)：核对源码/实验摘要、试次身份、模型与预算、终态结果及替换资格；全部完成后运行 `python docs/evidence/next-stage/audit.py --require-complete` 生成最终审计与原始证据文件摘要。
- [Checkpoint 同机性能与恢复](performance/report.md)
- [本地发行构建](packaging/report.md)
- 当前源码完整回归 [302 passed（含 Docker）](final-current-runtime-tests.txt)，[上游相关回归 46 passed](upstream-tests.txt)；原 301 passed 日志独立保留。

真实 Sol 对照已完成：5 tasks × 3 variants × 3 repeats = 45 formal originals，另有三个 replacement、两个 smoke。Luna 服务不可用，按用户决定没有正式样本。正式原试次的任务 true/false/null 为 baseline 13/0/2、loop-on 11/3/1、loop-off 11/4/0，成功终止分别为 15/9/7。全部真实 RepoPilot 原试次未触发循环诊断，本轮不能证明该机制提高任务收益；合理重读对照未误诊断，more-itertools 两个 RepoPilot 变体均为 0/3。冻结源码保留后来发现的上下文边界缺陷，不能将本批结果当作当前源码的全面验收。

[最终审计](audit.json)确认 45 个原试次身份齐全，308 个源码文件、337 个实验文件与参数/镜像/预算均一致；[原始证据摘要](raw-evidence-manifest.json)覆盖 3440 个文件。全部失败与替换单列。当前代码的完整回归为 302 passed（含 Docker），上游相关回归 46 passed，严格文档构建与干净 wheel 安装验证通过。本地提交未推送，repopilot-runtime 0.1.0 未发布。
