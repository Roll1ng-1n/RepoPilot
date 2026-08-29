# RepoPilot V1 — 可评测、可恢复的软件工程 Agent

## Problem Statement

软件工程 Agent 的价值不只是让模型调用 Shell 并生成代码，而是让一次真实仓库任务在有限预算内形成可解释、可恢复、可验证的执行闭环。现有极简 Agent 适合展示基础 Reasoning–Action Loop，但 Planning、语义级 Recovery、Checkpoint/Resume、Context Management、结构化 Trace 和可对照 Evaluation 仍需要被组织成一个完整 Runtime。

项目使用者需要一个以 CLI 为中心的工具：它能理解 Target Repository 中的任务，形成显式 Plan，调用结构化工具修改代码，执行 Task Verification，在失败后 Retry 或 Replan，并输出可审查的 Patch、Trace、验证结果与任务报告。使用者还需要清楚知道哪些能力来自上游 mini-SWE-agent，哪些是 RepoPilot 的新增或扩展，避免把上游已有能力包装成原创。

RepoPilot V1 的首要目标是形成一个适合求职展示和系统学习的真实工程项目。V1 优先覆盖尽可能多的可运行能力，但每个被宣称为 Implemented Capability 的能力都必须能从 CLI 主流程触发、有自动化测试或可重复演示、出现在 Trace 中，并记录已知限制。项目不以虚构成功率或生产级完整性换取表面完成度。

开发资源是单人、低模型预算并具备 Docker 环境。约 40 小时只作为范围规划参考，不是硬性截止线；实际开发遵循功能优先、最小必要验证和避免过度工程化的规则，同时保留足够证据证明功能真实工作。

## Solution

RepoPilot V1 是一个使用 Python 开发的 CLI 软件工程 Agent。项目从 mini-SWE-agent v2.4.6 的固定源码快照开始，保留 minisweagent 包作为可识别的 upstream/base，并在独立 repopilot 包中构建 Agent engineering 层。只有上游接口无法合理扩展时才对 minisweagent 做最小、可追踪的修改。

RepoPilot 通过 LiteLLM 使用支持 OpenAI-compatible 原生 Tool Calling 的模型。Runtime 驱动一个显式、版本化的顺序 Plan，通过 Tool Registry 调用代码浏览、搜索、编辑、命令、验证、Git 和 Agent Control 工具。Environment 是可替换的执行后端：普通 CLI 默认 Local，用户可以显式选择 Docker，自建 Agent Benchmark 和 SWE-bench 默认使用 Docker。

每个 Agent Run 维护持久化 State、Run Budget、错误分类、Recovery 状态和完整 Trace。Runtime 在每个 Agent Step 后保存 Checkpoint，支持等待 Human Approval 或被停止后的 Resume。Context Strategy 可以选择不压缩、滑动窗口或结构化摘要；Prompt 中的上下文可以压缩，但完整 Trace 永久保留。

RepoPilot 对低、中风险 Tool Call 自动执行，对删除、依赖安装和 Git 写操作等高风险行为请求 Human Approval。Task Verification 可以是单元测试、集成测试、类型检查、静态分析或其他可运行检查。只有存在足够验证证据时，Agent Run 才能进入 SUCCEEDED；否则必须报告 UNVERIFIED。

每次 Agent Run 生成机器可读与人类可读产物。Evaluation 同时使用 6–10 个带隐藏测试的微型任务和少量 SWE-bench Lite dev 实例，记录真实成功状态、步数、Token、成本、Tool Call、Retry、Replan、耗时、Patch 和 Commit，不预设或编造结果。

## User Stories

1. 作为使用 RepoPilot 的开发者，我希望对一个本地 Target Repository 提交自然语言任务，以便让 Agent 自主完成真实软件工程工作。
2. 作为使用 RepoPilot 的开发者，我希望既能通过命令参数提供任务，也能在缺少任务参数时交互输入，以便适应脚本化和临时使用。
3. 作为使用 RepoPilot 的开发者，我希望普通 Agent Run 默认使用 Local Environment，以便不需要先准备项目专用容器镜像。
4. 作为谨慎的开发者，我希望 CLI 明确警告 Local Environment 会直接执行命令并修改 Target Repository，以便理解实际风险。
5. 作为使用 RepoPilot 的开发者，我希望能够显式选择 Docker Environment，以便在需要时隔离任务执行。
6. 作为 benchmark 维护者，我希望 Agent Benchmark 默认使用 Docker，以便获得可重复且相互隔离的任务环境。
7. 作为未来的 RepoPilot 维护者，我希望 Runtime 不依赖 Local 或 Docker 的具体类型，以便新增 Remote、SSH 或其他 Execution Environment。
8. 作为使用 RepoPilot 的开发者，我希望为不同模型提供模型名、Base URL 和凭据配置，以便利用 LiteLLM 支持的模型服务。
9. 作为预算有限的开发者，我希望日常开发优先使用低成本模型，并可选择强模型进行少量对照，以便控制费用。
10. 作为使用 RepoPilot 的开发者，我希望凭据不会写入 Trace、Checkpoint 或 benchmark 结果，以便避免意外泄露。
11. 作为 Runtime 维护者，我希望执行模型使用原生 Tool Calling，以便获得结构化、可验证的工具参数。
12. 作为 Runtime 维护者，我希望不维护 Markdown、XML 或自由文本动作解析器，以便把时间用于 Agent engineering 能力。
13. 作为使用 RepoPilot 的开发者，我希望每个 Agent Run 在修改代码前形成显式 Plan，以便理解 Agent 的预期路径。
14. 作为处理简单任务的开发者，我希望 Plan 可以只有一个 Plan Step，以便 Planning 不给简单任务增加不必要复杂度。
15. 作为使用 RepoPilot 的开发者，我希望每次最多只有一个 Plan Step 处于进行状态，以便当前工作清晰可见。
16. 作为使用 RepoPilot 的开发者，我希望查看每个 Plan Step 的等待、进行、完成、失败或跳过状态，以便理解任务进度。
17. 作为使用 RepoPilot 的开发者，我希望新 Observation 推翻原假设时 Agent 能够 Replan，以便避免盲目执行失效计划。
18. 作为审查 Agent 行为的开发者，我希望 Replan 保留已经完成的 Plan Step，只替换未完成部分，以便保留有效工作。
19. 作为审查 Agent 行为的开发者，我希望每次 Replan 记录原因和计划版本，以便解释计划为何改变。
20. 作为使用 RepoPilot 的开发者，我希望 Agent 能列出文件和目录，以便理解 Target Repository 的结构。
21. 作为使用 RepoPilot 的开发者，我希望 Agent 能执行结构化代码搜索，以便快速定位相关实现和测试。
22. 作为使用 RepoPilot 的开发者，我希望 Agent 能按范围读取文件，以便控制送入模型的代码量。
23. 作为使用 RepoPilot 的开发者，我希望 Agent 能通过结构化 Patch 修改、创建或删除内容，以便留下可审查的编辑记录。
24. 作为使用 RepoPilot 的开发者，我希望 Agent 能查看当前 Diff，以便在验证或完成前审查累计修改。
25. 作为使用 RepoPilot 的开发者，我希望 Agent 能执行通用命令，以便处理专用工具未覆盖的仓库操作。
26. 作为 Runtime 维护者，我希望系统提示优先引导模型使用专用工具，同时保留通用命令作为逃生口，以便兼顾 Trace 质量与任务覆盖。
27. 作为使用 RepoPilot 的开发者，我希望 Agent 能运行与任务成功条件相关的 Task Verification，以便获得可执行证据。
28. 作为使用 RepoPilot 的开发者，我希望 Task Verification 可以运行单元测试、集成测试、类型检查、lint 或其他检查，以便适配不同任务。
29. 作为使用 RepoPilot 的开发者，我希望 Agent 根据任务和修改影响面选择局部或全量验证，以便在成本与可信度之间做判断。
30. 作为使用 RepoPilot 的开发者，我希望没有有效验证证据的结果被标记为 UNVERIFIED，以便不会把未经验证的修改误认为成功。
31. 作为使用 RepoPilot 的开发者，我希望有足够 Task Verification 证据的结果才能进入 SUCCEEDED，以便成功状态具有明确含义。
32. 作为使用 RepoPilot 的开发者，我希望 Agent 可以更新 Plan 并显式结束任务，以便 Agent Control 也是结构化 Tool Call。
33. 作为 Runtime 维护者，我希望 Tool Registry 统一完成 Tool Call 参数校验、分发和结果记录，以便所有工具共享一致行为。
34. 作为 Runtime 维护者，我希望 Runtime 只与 Tool Registry 交互，而不根据 Environment 类型分支，以便保持执行后端可替换。
35. 作为 Tool 开发者，我希望 Execution Environment 提供统一生命周期和命令执行协议，以便同一 Tool 可运行在 Local、Docker 和未来后端。
36. 作为 Tool 开发者，我希望命令结果包含退出码、标准输出、标准错误、耗时和截断状态，以便 Recovery 能基于结构化 Observation 判断失败。
37. 作为使用 RepoPilot 的开发者，我希望模型 API、Tool、Environment、Task Verification 和无进展错误被分类记录，以便理解失败来源。
38. 作为使用 RepoPilot 的开发者，我希望暂时性模型错误能够指数退避重试，以便短暂服务波动不会立即终止任务。
39. 作为使用 RepoPilot 的开发者，我希望无效 Tool Call 可以由模型修正后重试，以便参数错误可以低成本恢复。
40. 作为使用 RepoPilot 的开发者，我希望验证失败成为后续调试 Observation，而不是被简单重复执行，以便 Agent 能分析代码问题。
41. 作为使用 RepoPilot 的开发者，我希望连续失败或没有新进展时触发 Replan，以便 Agent 能切换失效思路。
42. 作为预算有限的开发者，我希望 Recovery 有明确次数限制，以便 Retry 和 Replan 不会无限循环。
43. 作为使用 RepoPilot 的开发者，我希望可以配置最大 Agent Step、Replan、连续失败、命令时间、Run 时间、Token 和费用，以便控制资源消耗。
44. 作为使用 RepoPilot 的开发者，我希望默认 Run Budget 提供合理的步数、Replan、失败、命令和时间限制，以便无需完整配置即可安全运行。
45. 作为使用 RepoPilot 的开发者，我希望达到任何 Run Budget 限制时得到 BUDGET_EXCEEDED，而不是模糊的失败，以便知道任务停止原因。
46. 作为使用 RepoPilot 的开发者，我希望 Ctrl+C 保存 Checkpoint 并让 Agent Run 进入 STOPPED，以便中断不会丢失全部进度。
47. 作为使用 RepoPilot 的开发者，我希望每个 Agent Step 后自动保存 Checkpoint，以便意外中断后可以恢复。
48. 作为使用 RepoPilot 的开发者，我希望通过 Run ID 恢复等待或停止的 Agent Run，以便继续长任务。
49. 作为使用 RepoPilot 的开发者，我希望 Resume 时重新创建 Execution Environment 并核对 Target Repository 和 Git 状态，以便不会在错误仓库中继续。
50. 作为使用 RepoPilot 的开发者，我希望 Checkpoint 不依赖旧进程或旧 Docker 容器仍然存在，以便恢复机制保持轻量。
51. 作为使用 RepoPilot 的开发者，我希望完整历史始终保存在 Trace 中，以便 Context Compression 不会销毁审计证据。
52. 作为实验 RepoPilot 的开发者，我希望选择不压缩上下文，以便获得 Context Management 消融基线。
53. 作为长任务使用者，我希望选择 Sliding Window Context Strategy，以便模型保留任务、Plan、重要事实和近期事件。
54. 作为长任务使用者，我希望选择 Summary Context Strategy，以便较早事件被压缩成结构化摘要。
55. 作为使用 RepoPilot 的开发者，我希望摘要失败时自动退回 Sliding Window，以便 Context Management 故障不会终止整个 Agent Run。
56. 作为使用 RepoPilot 的开发者，我希望低、中风险仓库操作自动执行，以便 Agent 保持足够自主性。
57. 作为使用 RepoPilot 的开发者，我希望删除、安装依赖和 Git 写操作在执行前请求 Human Approval，以便对高风险变化保留控制权。
58. 作为使用 RepoPilot 的开发者，我希望拒绝 Human Approval 后该结果成为 Observation，以便 Agent 能寻找替代方案。
59. 作为 benchmark 维护者，我希望一次性 Docker 任务可以配置自动批准，以便非交互评测不会等待输入。
60. 作为使用 RepoPilot 的开发者，我希望风险判断被明确描述为 best-effort，以便不会把轻量策略误认为完整安全保证。
61. 作为使用 RepoPilot 的开发者，我希望 Agent 可以在批准后创建本地 Git Commit，以便形成可解释的阶段性结果。
62. 作为审查 Agent 行为的开发者，我希望 Trace 记录 Git Commit 的理由和 hash，以便关联修改与计划阶段。
63. 作为使用 RepoPilot 的开发者，我希望 V1 不执行 push、rebase、reset 或创建 Pull Request，以便限制 Git 写能力范围。
64. 作为使用 RepoPilot 的开发者，我希望 Agent Run 可以显示 RUNNING、WAITING_FOR_APPROVAL、SUCCEEDED、UNVERIFIED、FAILED、BUDGET_EXCEEDED 或 STOPPED，以便精确理解状态。
65. 作为等待审批的开发者，我希望 WAITING_FOR_APPROVAL 状态可以通过 Checkpoint 恢复，以便审批不会打断任务连续性。
66. 作为使用 RepoPilot 的开发者，我希望 inspect 命令能查看已有 Agent Run，以便不重新执行任务也能审查状态和 Trace。
67. 作为使用 RepoPilot 的开发者，我希望每次 Agent Run 生成 metadata、Checkpoint、Trace、Plan、Patch、验证结果和任务报告，以便机器和人都能审查。
68. 作为使用 RepoPilot 的开发者，我希望 task report 说明根因、修改内容、修改理由、验证、风险和 Git Commit，以便快速理解交付结果。
69. 作为审查 Agent 行为的开发者，我希望 Trace 使用可追加事件格式，以便长任务不需要反复重写整份历史。
70. 作为评估模型成本的开发者，我希望 Trace 记录实际模型、参数、Token、费用和耗时，以便比较模型与策略。
71. 作为 RepoPilot 维护者，我希望 Runtime Test 关注模块外部行为而不是内部实现细节，以便重构不会导致脆弱测试。
72. 作为 RepoPilot 维护者，我希望 Local 与 Docker 通过同一组 Environment 行为测试，以便验证它们满足相同契约。
73. 作为 RepoPilot 维护者，我希望每项 Implemented Capability 都能通过 CLI 主流程或可重复演示被触发，以便能力声明可证实。
74. 作为 RepoPilot 维护者，我希望真实设计变化和验证失败的现象、定位、根因、修复与验证被记录，以便积累可讲述的工程证据。
75. 作为 benchmark 维护者，我希望有 6–10 个固定快照和隐藏测试的微型任务，以便低成本回归 Planning、Recovery、Resume、HITL、Trace 和 Git。
76. 作为 benchmark 维护者，我希望微型任务覆盖简单 Bug、跨文件修改、验证失败、Replan、长链路探索和 Git 行为，以便避免只验证单一 happy path。
77. 作为 benchmark 维护者，我希望用相同模型、任务和 Run Budget 比较 mini-SWE-agent baseline 与 RepoPilot，以便观察新增能力的真实影响。
78. 作为 benchmark 维护者，我希望记录成功状态、Agent Step、Token、费用、Tool Call、错误、Retry、Replan、耗时、Patch 和 Commit，以便进行失败分析。
79. 作为 benchmark 维护者，我希望运行 1–3 个 SWE-bench Lite dev 实例作为外部 smoke test，以便获得少量可比较证据。
80. 作为预算有限的开发者，我希望不在 V1 运行全量 SWE-bench，以便避免不现实的磁盘、时间和模型费用。
81. 作为查看项目的面试官，我希望 benchmark 报告展示真实结果，包括负面结果，以便判断项目是否诚实完成。
82. 作为查看项目的面试官，我希望文档区分 upstream 已有、RepoPilot 轻量扩展和 RepoPilot 新增能力，以便准确评价贡献。
83. 作为查看项目的面试官，我希望看到 Planning、Recovery、Context 和 Evaluation 过程中真实踩坑与修复记录，以便验证开发者理解实现细节。
84. 作为 RepoPilot 维护者，我希望上游源码通过独立导入 Commit 进入项目，并记录来源版本、commit 和许可证，以便追踪派生关系。
85. 作为 RepoPilot 维护者，我希望 minisweagent 保持可识别的上游基础包，以便比较与同步上游差异。
86. 作为 RepoPilot 维护者，我希望新增能力原则上位于 repopilot 包，以便防止项目逻辑继续堆入上游包。
87. 作为 RepoPilot 维护者，我希望只有合理扩展受阻时才修改 minisweagent，并保持改动最小清晰，以便降低派生维护成本。
88. 作为 Python 项目使用者，我希望 V1 对 Python Target Repository 进行正式验证，以便拥有清晰的已验证兼容范围。
89. 作为其他语言项目使用者，我希望核心执行流程不主动写死 Python，以便未来验证更多语言。
90. 作为其他语言项目使用者，我希望文档把非 Python 仓库标为未验证而不是承诺全面兼容，以便形成准确预期。

## Implementation Decisions

- RepoPilot 从 mini-SWE-agent v2.4.6 固定源码快照派生。导入使用独立 Commit，并记录上游仓库、版本、commit 和 MIT 许可证。项目不承诺自动兼容后续上游版本。
- minisweagent 包保留为 upstream/base。repopilot 包承载 Planner、State、Recovery、Checkpoint、Context Management、HITL、Trace、Evaluation 和 CLI 等新增工程能力。
- 新能力优先通过 repopilot 扩展上游协议。只有现有接口无法支持合理扩展时，才对 minisweagent 做最小、清晰、可追踪修改。
- 项目文档维护能力来源矩阵，区分上游已有、RepoPilot 扩展和 RepoPilot 新增，避免把上游 Budget、基础确认、Docker、trajectory 或 benchmark runner 描述为原创。
- V1 使用 Python 实现。Runtime 核心不主动限制 Target Repository 语言，但正式兼容验证只覆盖 Python 仓库。
- CLI 提供 run、resume、inspect 和 benchmark 四个核心入口。run 接受仓库路径和任务，缺少任务参数时进入交互输入。
- LiteLLM 负责模型接入。模型名、Base URL、Key 和参数通过 CLI、配置或环境变量提供；核心 Runtime 不实现厂商专用业务分支。
- 执行模型必须支持 OpenAI-compatible 原生 Tool Calling。V1 不提供 Markdown、XML 或自由文本动作解析回退。
- 普通 CLI 默认使用 Local Environment，并明确警告其会直接执行命令和修改 Target Repository。Docker 由用户显式选择，Agent Benchmark 默认使用 Docker。
- CLI 或 Factory 创建并注入 Execution Environment。Runtime 只通过 Tool Registry 使用环境，不检查 Local、Docker 或未来 backend 的具体类型。
- Execution Environment 是最小协议，负责生命周期和命令执行。命令请求支持工作目录、timeout 和环境变量；结果提供退出码、标准输出、标准错误、耗时和截断信息。
- Tool Registry 负责 Tool Call schema、参数校验、分发、Observation 标准化、风险元数据和 Trace 记录。
- V1 Repository Tools 包括文件列表、代码搜索、文件读取、Patch 编辑和 Diff 查看；Execution Tools 包括通用命令与 Task Verification；Git Tool 包括受审批的本地 Commit；Agent Control Tools 包括更新 Plan 和完成任务。
- 通用命令保留为专用工具的逃生口。系统提示优先要求模型使用专用工具；V1 不开发复杂 Shell 解析器来强制阻止绕过。
- Plan 是有版本的顺序 Plan Step 列表，不实现 DAG 或多 Agent 调度。状态为 PENDING、IN_PROGRESS、COMPLETED、FAILED 或 SKIPPED，且最多一个 Plan Step 为 IN_PROGRESS。
- 所有 Agent Run 都建立 Plan；简单任务允许单步骤 Plan。Replan 保留已完成步骤、替换未完成部分，并记录原因和版本。
- Agent Run 状态为 RUNNING、WAITING_FOR_APPROVAL、SUCCEEDED、UNVERIFIED、FAILED、BUDGET_EXCEEDED 或 STOPPED。
- WAITING_FOR_APPROVAL 与 STOPPED 可通过 Checkpoint Resume。其余状态默认结束一次 Agent Run。
- Task Verification 是独立结构化工具，可执行测试、类型检查、lint 或其他可运行检查，并记录范围、理由和结果。
- Runtime 根据任务成功条件与验证证据判断 SUCCEEDED。没有有效验证证据时只能得到 UNVERIFIED，而不是伪装成成功。
- 错误分类包括 MODEL_ERROR、TOOL_ERROR、ENVIRONMENT_ERROR、VERIFICATION_FAILURE 和 NO_PROGRESS。分类优先基于可确定的调用来源与结果，不额外调用独立 LLM Error Classifier。
- 暂时性模型错误使用指数退避；参数错误允许模型修正；验证失败进入后续调试 Observation；连续失败或无进展触发 Replan。
- 默认 Run Budget 为最多 30 个 Agent Step、2 次 Replan、3 次连续失败、单命令 300 秒和 Agent Run 30 分钟。Token 与费用限制支持配置，但不设置跨供应商的统一默认值。
- 每个 Agent Step 后原子保存 Checkpoint。等待审批或 Ctrl+C 时再次保存；Ctrl+C 令 Agent Run 进入 STOPPED。
- Checkpoint 保存任务、Plan、State、消息、Context 摘要、Run Budget 计数、工具结果、修改文件和 Commit hash，但不保存 API Key。
- Run 产物默认保存在系统状态目录，不污染 Target Repository。Resume 重新创建 Execution Environment，核对 Target Repository 与 Git 状态，不恢复旧进程或旧容器。
- Context Strategy 支持 none、sliding_window 和 summary。完整历史始终进入 Trace；Prompt 保留任务、当前 Plan、重要事实和近期事件，Summary 策略压缩更早事件。
- Context Compression 在可配置阈值触发。摘要失败时退回 Sliding Window，不因此终止 Agent Run。
- Human Approval 使用轻量、best-effort 风险策略。低、中风险操作自动执行；删除、依赖安装和 Git 写操作等高风险操作等待审批。
- 拒绝 Human Approval 产生 Observation，允许 Agent 调整方案。一次性 Docker benchmark 可以配置自动批准。
- RepoPilot V1 提供经 Human Approval 的本地 Git Commit，但不支持 push、rebase、reset 或 Pull Request。
- Trace 使用可追加的 JSONL 事件流，完整记录 Plan、模型、Tool Call、Observation、错误、Recovery、审批、验证、Context、Budget 和终态。
- 每个 Agent Run 产出 metadata.json、checkpoint.json、trace.jsonl、plan.json、patch.diff、verification.json 和 task_report.md。
- task_report.md 说明根因、修改内容、修改理由、Task Verification、剩余风险和 Git Commit。
- V1 Agent Benchmark 使用 6–10 个带固定仓库快照、任务描述、隐藏测试、成功条件和 timeout 的微型任务。
- 微型任务覆盖简单单文件 Bug、跨文件修改、验证失败与 Recovery、Replan、长链路探索和 Human Approval/Git 行为。
- 外部 smoke test 复用 mini-SWE-agent runner，运行 1–3 个 SWE-bench Lite dev 实例。V1 不运行全量 SWE-bench。
- Evaluation 使用相同模型、任务和 Run Budget 比较 mini-SWE-agent baseline 与 RepoPilot，记录真实结果，不预设成功率。
- RAG Memory 的扩展边界保留在 repopilot，但实现属于 V2。
- Web UI、Multi-Agent 和更广泛 Environment backend 的接口边界在 V1 保留，但不实现这些能力。

## Testing Decisions

- 最高层、首选测试 seam 是 CLI 驱动的完整 Agent Run。测试从受控 Target Repository 和确定性模型响应开始，验证终态、工作区修改、Task Verification、Trace、Checkpoint 和报告等外部行为。
- 测试不依赖私有方法、内部容器结构或具体 Prompt 文本。只要对外状态、Tool Call 协议、产物和仓库结果保持一致，内部重构不应破坏测试。
- 现有 mini-SWE-agent 的 Agent、Model、Environment 和 benchmark runner seam 优先复用。仅当 RepoPilot 行为无法从这些 seam 注入或观察时，才新增更低层测试 seam。
- Runtime Test 覆盖 Plan 状态转换、Replan 历史、错误分类、Recovery 次数、Run Budget、Agent Run 终态、Checkpoint/Resume、Context Strategy fallback 和 Human Approval 状态。
- Tool Registry 测试覆盖 schema 校验、Tool Call 分发、结构化 Observation、风险元数据和 Trace 事件，不重复测试 Shell、Git 或 pytest 本身。
- Local 与 Docker 通过同一组 Execution Environment 契约测试，验证生命周期、工作目录、timeout、环境变量、输出、退出码和截断行为。
- Task Verification 测试覆盖成功、失败、timeout、局部检查、全量检查和无验证证据；重点验证 SUCCEEDED 与 UNVERIFIED 的外部语义。
- Checkpoint 测试覆盖每步保存、原子替换、Ctrl+C、WAITING_FOR_APPROVAL、STOPPED、仓库身份不匹配和 Resume 后 Environment 重建。
- Context Management 测试覆盖 none、sliding_window、summary、阈值触发、重要事实保留、近期事件保留和摘要失败回退。
- HITL 测试覆盖自动执行、请求批准、批准、拒绝、持久化等待状态和 Docker benchmark 自动批准配置。V1 不尝试证明完整安全性。
- Git 测试只覆盖经审批的本地 Commit、Trace 中的原因/hash 以及被禁止的 push、rebase、reset 和 Pull Request 行为。
- 每项 Implemented Capability 至少具有一个自动化测试或可重复演示、对应 Trace 证据和已知限制说明。
- Runtime Test 以核心行为为中心，不设置覆盖率数字门槛，也不为不影响功能的边界组合投入大量测试。
- 微型 Agent Benchmark 使用 6–10 个固定任务和隐藏测试，运行时记录任务成功状态、Agent Step、Token、费用、Tool Call、错误、Retry、Replan、耗时、Patch 和 Commit。
- baseline 与 RepoPilot 对照必须使用相同任务、模型参数、Environment 和 Run Budget；样本量不足时只描述为开发期回归证据，不宣称泛化性能。
- SWE-bench Lite dev 只运行 1–3 个实例作为外部 smoke。运行前固定数据 revision、实例 ID、模型、Budget 和 Docker 环境。
- benchmark 结果无论好坏都保留。README、简历或报告只能引用真实运行结果，不能填充预期数字。
- Runtime Test 或 Task Verification 暴露出具有分析价值的问题时，开发记录说明现象、错误尝试、根因、修复、验证和关联 Commit；普通无分析价值的机械错误不单独记录。

## Out of Scope

- V1 不实现 RAG Memory 或项目知识库检索；只保留未来位于 repopilot 的扩展边界。
- V1 不实现 Multi-Agent、Manager/Coder/Reviewer 团队或 Agent 间辩论。
- V1 不实现 Web UI、TUI、浏览器控制、GUI 操作、语音或桌面自动化。
- V1 不自动 push、不创建 Pull Request、不 rebase、不 reset，也不自动部署。
- V1 不承诺生产级 Security Analyzer、完整命令语义分析、强隔离或恶意仓库防护。
- V1 不要求所有模型供应商兼容；不支持原生 Tool Calling 的模型不能作为执行模型。
- V1 不为 Markdown、XML 或自由文本动作实现兼容解析。
- V1 不正式保证 JavaScript、Go、Java 或其他非 Python Target Repository；核心流程避免主动写死语言。
- V1 不实现复杂 Plan DAG、并行 Plan Step、分布式调度或多 Agent 调度。
- V1 不恢复旧操作系统进程、旧 Shell 或旧 Docker 容器；Checkpoint 只恢复 Agent Run 状态。
- V1 不自动同步未来 mini-SWE-agent 版本，也不为上游升级建立复杂同步工具。
- V1 不运行 SWE-bench Full、完整 SWE-bench Lite、完整 SWE-bench Verified、SWT-Bench 或 ProgramBench。
- V1 不设定必须达到的 benchmark 成功率、覆盖率或商业 SLA。
- V1 不加入 Redis、向量数据库、消息队列或其他尚无当前需求的基础设施。

## Further Notes

- mini-SWE-agent v2.4.6 是 MIT 许可的 Python 项目，官方定位强调 hackable 和可扩展，但包元数据仍标记为 Alpha。v2 已使用原生 Tool Calling，默认能力仍主要围绕 Bash Tool。
- mini-SWE-agent 已有 Step/Cost/Wall-time 限制、模型 API 重试、基础确认、Local/Docker 等 Environment、trajectory、inspector 和 SWE-bench runner。RepoPilot 对这些能力应描述为复用或扩展，而不是原创。
- mini-SWE-agent 的 trajectory 保存不等于真正的 Checkpoint/Resume。RepoPilot 的增量是持久化 Agent Run State、恢复 Plan/Context/Budget，并在新 Environment 中继续。
- OpenHands 继续作为架构参考，但应引用当前 software-agent-sdk 与 V1 Workspace 文档。旧版“默认所有执行都在 Docker Runtime”描述已经过时；当前架构把 sandboxing 视为可选择的 Workspace backend。
- SWE-agent ACI 应引用官方仓库或论文，不再引用个人 Fork。
- 主要上游来源：
  - https://github.com/SWE-agent/mini-swe-agent/releases/tag/v2.4.6
  - https://github.com/SWE-agent/mini-swe-agent
  - https://github.com/SWE-agent/SWE-agent
  - https://arxiv.org/abs/2405.15793
  - https://github.com/OpenHands/software-agent-sdk
  - https://github.com/OpenHands/docs/tree/main/sdk/arch
  - https://github.com/SWE-bench/SWE-bench
- V1 的约 40 小时是规划参考线，不是硬性完成条件。功能数量可以增加，但不能把 stub、TODO 或未接入主流程的代码称为 Implemented Capability。
- Codex 开发 RepoPilot 时的“功能优先、最小必要验证、主代理控制 Commit/PR/部署”等规则只约束开发过程，不自动成为 RepoPilot 产品 Runtime 的行为。
- RepoPilot 产品的 Human Approval、Task Verification 和 Git 行为以本 Spec 与 ADR 为准。
