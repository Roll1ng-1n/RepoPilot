# 固定真实模型对照结果

Sol 正式原试次 5/45；完成状态 False。所有原始样本、smoke 和 replacement 独立列出，未知数据保留 null。Luna 服务不支持该模型，仅保留失败 smoke，用户随后选择只跑 Sol。

| Model / task / variant / stage / replacement | N | Repository T/F/null | Task T/F/null | Normal end | Steps median | Tokens median | Repeats median | First change median |
|---|---:|---|---|---:|---:|---:|---:|---:|
| gpt-6-luna / real-boltons-slug / loop-on / smoke / False | 1 | 0/1/0 | 0/1/0 | 0 | 1 | None | None | None |
| gpt-6.1-sol / real-boltons-slug / baseline / formal / False | 1 | 1/0/0 | 1/0/0 | 1 | 7 | 63181 | None | None |
| gpt-6.1-sol / real-boltons-slug / loop-off / formal / False | 1 | 1/0/0 | 1/0/0 | 1 | 9 | 69994 | 0 | 4 |
| gpt-6.1-sol / real-boltons-slug / loop-on / formal / False | 1 | 1/0/0 | 1/0/0 | 1 | 7 | 60278 | 0 | 4 |
| gpt-6.1-sol / real-boltons-slug / loop-on / smoke / False | 1 | 1/0/0 | 1/0/0 | 1 | 9 | 60142 | 0 | 6 |
| gpt-6.1-sol / real-more-chunked / baseline / formal / False | 1 | 1/0/0 | 1/0/0 | 1 | 11 | 139061 | None | None |
| gpt-6.1-sol / real-more-chunked / loop-on / formal / False | 1 | 0/1/0 | 0/1/0 | 0 | 26 | 252373 | 1 | 11 |

逐样本状态、成功终止、费用、各耗时及数值分布见 summary.json。费用汇总只累加已知值，unknown 分母同时保留。框架/工具耗时仅在可观测 Trace 中报告，baseline 的未知指标不能当零。

本次结果只能描述这些固定回归与压力任务。baseline 比较不能区分提示、工具和恢复机制的贡献；loop-on/off 是相同代码与预算的机制消融，但每组仅三次，不能宣称普遍因果收益。对收益未改善或合理重读失败的样本仍按原结果保留。冻结源包含当时的上下文边界缺陷，后续修复不回写这批结果。

重新生成此报告不调用模型：python docs/evidence/next-stage/summarize.py。方案见 evaluation-plan.json、plan-amendment.json；离线快照与验证器检查见 offline.py。
