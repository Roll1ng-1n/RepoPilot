# 固定真实模型对照结果

Sol 正式原试次 45/45；完成状态 True。所有原始样本、smoke 和 replacement 独立列出，未知数据保留 null。Luna 服务不支持该模型，仅保留失败 smoke，用户随后选择只跑 Sol。

下表只汇总正式原试次，跨任务总数用于核对完整性；任务难度不同，具体差异以随后逐任务结果为准。

| Variant | N | Repository T/F/null | Task T/F/null | Normal end |
|---|---:|---|---|---:|
| baseline | 15 | 15/0/0 | 13/0/2 | 15 |
| loop-on | 15 | 12/3/0 | 11/3/1 | 9 |
| loop-off | 15 | 11/4/0 | 11/4/0 | 7 |

所有中位数只使用已知数值；首次修改列附已知/null 样本数。该项 null 可能表示未发生实际源码修改，也可能表示缺少观测；逐样本记录保留该范围，不能将 null 当成第 0 步。

| Model / task / variant / stage / replacement | N | Repository T/F/null | Task T/F/null | Normal end | Steps median | Tokens median | Repeated exploration median | First change step median (known/null) |
|---|---:|---|---|---:|---:|---:|---:|---:|
| gpt-6-luna / real-boltons-slug / loop-on / smoke / False | 1 | 0/1/0 | 0/1/0 | 0 | 1 | null | null | null (0/1) |
| gpt-6.1-sol / history-inventory / baseline / formal / False | 3 | 3/0/0 | 3/0/0 | 3 | 9 | 164886 | null | null (0/3) |
| gpt-6.1-sol / history-inventory / loop-off / formal / False | 3 | 3/0/0 | 3/0/0 | 1 | 39 | 361424 | 0 | 10 (3/0) |
| gpt-6.1-sol / history-inventory / loop-on / formal / False | 3 | 3/0/0 | 3/0/0 | 2 | 19 | 177491 | 0 | 9 (3/0) |
| gpt-6.1-sol / real-boltons-reread / baseline / formal / False | 3 | 3/0/0 | 3/0/0 | 3 | 9 | 93166 | null | null (0/3) |
| gpt-6.1-sol / real-boltons-reread / loop-off / formal / False | 3 | 3/0/0 | 3/0/0 | 3 | 9 | 79511 | 2 | 4 (3/0) |
| gpt-6.1-sol / real-boltons-reread / loop-on / formal / False | 3 | 3/0/0 | 3/0/0 | 3 | 9 | 76293 | 2 | 4 (3/0) |
| gpt-6.1-sol / real-boltons-slug / baseline / formal / False | 3 | 3/0/0 | 3/0/0 | 3 | 8 | 74375 | null | null (0/3) |
| gpt-6.1-sol / real-boltons-slug / loop-off / formal / False | 3 | 3/0/0 | 3/0/0 | 2 | 7 | 59181 | 0 | 4 (3/0) |
| gpt-6.1-sol / real-boltons-slug / loop-on / formal / False | 3 | 3/0/0 | 3/0/0 | 3 | 8 | 60707 | 0 | 4 (3/0) |
| gpt-6.1-sol / real-boltons-slug / loop-on / smoke / False | 1 | 1/0/0 | 1/0/0 | 1 | 9 | 60142 | 0 | 6 (1/0) |
| gpt-6.1-sol / real-cachetools-expire / baseline / formal / False | 3 | 3/0/0 | 1/0/2 | 3 | 9 | 113049 | null | null (0/3) |
| gpt-6.1-sol / real-cachetools-expire / loop-off / formal / False | 3 | 2/1/0 | 2/1/0 | 1 | 35 | 338017 | 0 | 19.0 (2/1) |
| gpt-6.1-sol / real-cachetools-expire / loop-off / formal / True | 1 | 0/1/0 | 0/1/0 | 0 | 6 | 36196 | 0 | null (0/1) |
| gpt-6.1-sol / real-cachetools-expire / loop-on / formal / False | 3 | 3/0/0 | 2/0/1 | 1 | 23 | 215113 | 0 | 18 (3/0) |
| gpt-6.1-sol / real-more-chunked / baseline / formal / False | 3 | 3/0/0 | 3/0/0 | 3 | 12 | 145948 | null | null (0/3) |
| gpt-6.1-sol / real-more-chunked / loop-off / formal / False | 3 | 0/3/0 | 0/3/0 | 0 | 46 | 475812 | 2 | 32.0 (2/1) |
| gpt-6.1-sol / real-more-chunked / loop-off / formal / True | 1 | 0/1/0 | 0/1/0 | 0 | 40 | 407849 | 3 | null (0/1) |
| gpt-6.1-sol / real-more-chunked / loop-on / formal / False | 3 | 0/3/0 | 0/3/0 | 0 | 26 | 252373 | 1 | 22.5 (2/1) |
| gpt-6.1-sol / real-more-chunked / loop-on / formal / True | 1 | 0/1/0 | 0/1/0 | 0 | 48 | 484637 | 1 | null (0/1) |

时间单位为秒，均为已知值的中位数；费用为已知归一化美元值之和，同时列出已知/未知样本数，以及可观测请求中费用已知/未知的数量。样本费用非 null 也可能只覆盖部分请求。预算原因来自终态 Trace，baseline 的该项不可观测。

| Model / task / variant / stage / replacement | Wall | LLM | Tool | Framework | Timing coverage | Cost subtotal (known/unknown samples) | Cost known/unknown requests | Budget stops |
|---|---:|---:|---:|---:|---|---|---|---|
| gpt-6-luna / real-boltons-slug / loop-on / smoke / False | 4.157 | 3.652 | 0.000 | 0.243 | complete:1 | null (0/1) | 0/1 | — |
| gpt-6.1-sol / history-inventory / baseline / formal / False | 165.973 | null | null | null | unavailable:3 | 0.332442 (3/0) | null | null:3 |
| gpt-6.1-sol / history-inventory / loop-off / formal / False | 1095.217 | 1077.593 | 6.031 | 7.587 | complete:3 | 1.193865 (3/0) | 104/2 | context_window:1, steps:1 |
| gpt-6.1-sol / history-inventory / loop-on / formal / False | 495.201 | 486.429 | 5.816 | 5.626 | complete:3 | 0.783890 (3/0) | 70/1 | context_window:1 |
| gpt-6.1-sol / real-boltons-reread / baseline / formal / False | 86.404 | null | null | null | unavailable:3 | 0.187022 (3/0) | null | null:3 |
| gpt-6.1-sol / real-boltons-reread / loop-off / formal / False | 227.781 | 224.088 | 1.503 | 1.470 | complete:3 | 0.186566 (3/0) | 24/0 | — |
| gpt-6.1-sol / real-boltons-reread / loop-on / formal / False | 165.088 | 162.362 | 1.195 | 1.529 | complete:3 | 0.279558 (3/0) | 26/0 | — |
| gpt-6.1-sol / real-boltons-slug / baseline / formal / False | 227.944 | null | null | null | unavailable:3 | 0.236024 (3/0) | null | null:3 |
| gpt-6.1-sol / real-boltons-slug / loop-off / formal / False | 133.399 | 130.833 | 1.080 | 1.292 | complete:3 | 0.160093 (3/0) | 21/1 | context_window:1 |
| gpt-6.1-sol / real-boltons-slug / loop-on / formal / False | 128.697 | 125.896 | 1.116 | 1.381 | complete:3 | 0.179591 (3/0) | 22/2 | — |
| gpt-6.1-sol / real-boltons-slug / loop-on / smoke / False | 397.420 | 394.082 | 1.206 | 1.886 | complete:1 | 0.077556 (1/0) | 7/2 | — |
| gpt-6.1-sol / real-cachetools-expire / baseline / formal / False | 198.650 | null | null | null | unavailable:3 | 0.200814 (3/0) | null | null:3 |
| gpt-6.1-sol / real-cachetools-expire / loop-off / formal / False | 309.521 | 300.209 | 3.552 | 5.510 | complete:3 | 0.968071 (3/0) | 89/4 | steps:1, context_window:1 |
| gpt-6.1-sol / real-cachetools-expire / loop-off / formal / True | 34.596 | 30.758 | 1.954 | 1.571 | complete:1 | 0.022832 (1/0) | 5/0 | context_window:1 |
| gpt-6.1-sol / real-cachetools-expire / loop-on / formal / False | 442.700 | 435.694 | 2.905 | 3.614 | complete:3 | 0.794759 (3/0) | 67/1 | context_window:2 |
| gpt-6.1-sol / real-more-chunked / baseline / formal / False | 539.227 | null | null | null | unavailable:3 | 0.344840 (3/0) | null | null:3 |
| gpt-6.1-sol / real-more-chunked / loop-off / formal / False | 703.414 | 666.408 | 13.814 | 16.413 | complete:3 | 1.762988 (3/0) | 136/1 | steps:1, context_window:2 |
| gpt-6.1-sol / real-more-chunked / loop-off / formal / True | 1410.516 | 1384.470 | 11.851 | 13.933 | complete:1 | 0.490596 (1/0) | 39/0 | context_window:1 |
| gpt-6.1-sol / real-more-chunked / loop-on / formal / False | 413.074 | 397.772 | 7.264 | 7.765 | complete:3 | 1.277918 (3/0) | 95/1 | context_window:2, steps:1 |
| gpt-6.1-sol / real-more-chunked / loop-on / formal / True | 1212.140 | 1184.299 | 11.901 | 15.643 | complete:1 | 0.548460 (1/0) | 46/2 | steps:1 |

逐样本状态、成功终止、费用、各耗时及数值分布见 summary.json。费用使用 provider/LiteLLM 的归一化指标，汇总只累加已知值，unknown 分母同时保留；不是已审计的服务账单总额。tokens 同样只累加已知 usage，失败或无 usage 请求的实际消耗与收费不可观测；请求覆盖数量在 summary.json 中单列。框架/工具耗时仅在可观测 Trace 中报告，baseline 的未知指标不能当零。

本次结果只能描述这些固定回归与压力任务。baseline 比较不能区分提示、工具和恢复机制的贡献；loop-on/off 是相同代码与预算的机制消融，但每组仅三次，不能宣称普遍因果收益。对收益未改善或合理重读失败的样本仍按原结果保留。冻结源包含当时的上下文边界缺陷，后续修复不回写这批结果。

任务结果、未证明的机制收益及观测限制见 [对照结论](interpretation.md)；完整性检查见 [最终审计](audit.json)及[原始证据摘要](raw-evidence-manifest.json)。

重新生成此报告不调用模型：python docs/evidence/next-stage/summarize.py。方案见 evaluation-plan.json、plan-amendment.json；离线快照与验证器检查见 offline.py。
