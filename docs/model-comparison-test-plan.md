# Mini-SWE-agent 与 RepoPilot 大模型对照测试计划

本计划对应 Issue #17，用于在同一个 OpenAI-compatible API 中，对 pinned
mini-SWE-agent baseline 与 RepoPilot 进行可复现的模型对照。测试会产生真实的付费
模型调用；先通过低成本 gate，再扩大样本。

## 目标与范围

目标是回答以下问题：在同一个模型、任务和运行预算下，两个 Agent engine 的任务成功率、
工具调用行为、效率、Token 消耗、成本和稳定性有何差异；同时记录中转站兼容性对结果的
影响。结果是开发期证据，不是对模型、仓库或生产性能的普遍声明。

比较的模型 ID 固定为：

- `gpt-5.6-sol`
- `gpt-5.6-terra`
- `gpt-5.6-luna`
- `gpt-5.5`

（四模型清单对应 Stage 1–3 的历史记录。**2026-09-07 起后续 benchmark / campaign
模型集收缩为以下两模型**，`gpt-5.6-terra` 与 `gpt-5.5` 不再进入新的对照测试；官网价格
表和 Stage 1–3 证据仍保留为历史参考。）

后续正式对照模型集：

- `gpt-5.6-sol`
- `gpt-5.6-luna`

API Key 和 Base URL 从本地 `.env` 提供（`REPOPILOT_API_KEY`、
`REPOPILOT_BASE_URL`）。密钥不得写入日志、结果或提交内容。

## 公平性不变量

每个 baseline/RepoPilot 成对运行都必须满足：

- 使用完全相同的模型 ID、API endpoint、模型参数（至少 temperature、reasoning 设置和
  输出上限）以及调用批次配置；
- 使用相同的固定任务描述、Target Repository 快照、隐藏 verifier 和任务顺序策略；
- 使用相同的 Docker image、工作目录、网络/容器代理策略和环境预检结果；
- 使用相同的 Run Budget：最大步骤、最大 Replan、连续失败上限、命令超时和 Agent Run
  墙钟上限；
- 两个 engine 都保留原始轨迹、patch、verifier 输出和可用的 usage 数据，缺失字段使用
  `null`。

Agent system/user prompt、工具集合、工具 schema 和工具处理流程是本次要比较的变量，
不强行改成相同版本。它们必须在配置和结果中完整记录（包括版本或摘要），以便把 engine
差异与模型差异分开解释。随机性尽可能通过 `temperature=0` 和固定 seed（中转站支持时）
降低，但不可把非确定的 API 响应当作完全可复现。

## OpenAI-compatible 中转站假设与探针

用户提供的本地示例展示的是 Chat Completions API。中转站可能只实现其中一部分参数，或者接受
参数但忽略它们；尤其需要验证：

- 普通 `messages` 文本请求和响应内容；
- `tools` + `tool_choice="required"` 的原生 Tool Call，及返回的
  `message.tool_calls`、函数名和 JSON arguments；
- `temperature`、`max_tokens`、`seed`、`response_format` 等可选参数是否接受。探针
  失败时先删减可选参数定位兼容性，不把“参数不支持”误判成 Agent 失败；
- 响应是否包含 `usage.prompt_tokens`、`usage.completion_tokens`、
  `usage.total_tokens`，以及缓存 Token 或 provider cost 字段。

探针只验证传输和响应契约，不验证 Agent 是否能完成仓库任务。每个模型先做一次 text
probe 和一次 Tool Call probe，共 8 次；模型的两个探针都通过后才进入 Agent Run。记录
HTTP 状态、错误类型、请求参数摘要、延迟和经过脱敏的原始响应摘要，不记录 API Key。

## 官方 Standard 价格与估算规则

价格来源为 OpenAI 官方文档的 Standard 同步价格（美元/百万 Token）：

- [API Pricing](https://developers.openai.com/api/docs/pricing)
- [GPT-5.5 model](https://developers.openai.com/api/docs/models/gpt-5.5)

下表使用降价后的价格。短上下文为 `<=272K`，长上下文为 `>272K`；普通 benchmark
默认使用 Standard，不使用 Batch、Flex 或 Fast。`Cache write` 为官网提供的缓存写入
单价；`—` 表示该模型官网没有该项单价。官网同时注明 GPT-5.6 Sol 的促销价至少持续到
2026-11-21；超过该日期再次运行 campaign 前必须重新核价。

### 短上下文（`<=272K`）

| 模型 | Input | Cached input | Cache write | Output |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.6-sol` | $4.00 | $0.40 | $5.00 | $20.00 |
| `gpt-5.6-terra` | $2.00 | $0.20 | $2.50 | $12.00 |
| `gpt-5.6-luna` | $0.20 | $0.02 | $0.25 | $1.20 |
| `gpt-5.5` | $5.00 | $0.50 | — | $30.00 |

### 长上下文（`>272K`）

| 模型 | Input | Cached input | Cache write | Output |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.6-sol` | $8.00 | $0.80 | $10.00 | $30.00 |
| `gpt-5.6-terra` | $4.00 | $0.40 | $5.00 | $18.00 |
| `gpt-5.6-luna` | $0.40 | $0.04 | $0.50 | $1.80 |
| `gpt-5.5` | $10.00 | $1.00 | — | $45.00 |

离线官网估算使用实际 usage（Token 数，不从字符数推算）：

```text
uncached_input = prompt_tokens - cached_tokens
cost_usd = uncached_input * input_rate / 1_000_000
          + cached_tokens * cached_rate / 1_000_000
          + cache_write_tokens * cache_write_rate / 1_000_000
          + completion_tokens * output_rate / 1_000_000
```

中转站不返回 cached/cache-write 明细时，把完整的 `prompt_tokens` 作为普通 Input，
并在结果中标记为“官网 Standard 估算”，不能声称是中转站实际账单。没有任何 usage
Token 时，`tokens` 和 `cost` 均记录为 `null`；不能用总 Token、响应长度或其他模型的
价格补造数字。若 provider 返回真实 cost，另存为 `provider_cost_usd`，与官网估算
分开报告。

## 测试阶段与 Gate

### Stage 0：固定配置和环境预检

冻结四个模型 ID、temperature、预算、六个任务清单、Docker image、代理模式和输出目录
规则。确认 `.env` 中两个变量存在但不打印值；确认 Docker daemon、镜像和隐藏 verifier
可用。使用下方固定 Python digest 和 Debian snapshot 构建的 Git 镜像；Stage 0 在容器内验证
`python --version` 和 `git --version`，缺失时在付费 Agent Run 前记录 `ENVIRONMENT_UNAVAILABLE`。
成对运行使用同一解析后的不可变镜像标识，并保留预检结果。代理可以是无代理、继承宿主代理或显式 URL，
但一轮成对运行必须采用同一策略。

### Stage 1：API 能力探针（8 次）

对四个模型各做 text + native Tool Call 两次请求。四个模型的 8 个探针全部通过，才
进入下一阶段。单个模型探针失败只阻止该模型的 Agent Run，并归类为认证、配额、HTTP
错误、超时或请求/Tool Call 不兼容；不要继续烧该模型额度。

### Stage 2：Luna 低成本 smoke（4 次 Agent Run）

只使用 `gpt-5.6-luna`，在 `seed-single-file` 和一个跨文件任务上各运行 baseline 与
RepoPilot，共 `2 tasks × 2 engines = 4` 次。两 engine 都应至少完成一对任务并通过隐藏
verifier，且能解析主要 metrics，才扩大测试。失败仍保留完整 artifacts，不能用重试覆盖
第一次结果。

### Stage 3：四模型单轮对照（48 次 Agent Run）

对四个模型运行六个固定 benchmark task，并为每个 task 运行两个 engine：
`4 models × 6 tasks × 2 engines = 48` 次。baseline 与 RepoPilot 必须使用成对的快照和
预算，建议交错模型/engine 顺序以减少中转站瞬时负载的偏差。

### Stage 4：稳定性三轮（144 次 Agent Run）

重复 Stage 3 三轮，即 `48 × 3 = 144` 次（不是额外再加 144 次）。报告每个模型、
engine、task 的逐轮结果和三轮汇总；成功率使用 verifier 结果，`ENVIRONMENT_UNAVAILABLE`
或 API 不可用不计入模型分母。

六个固定任务为 `seed-single-file`、`seed-cross-file`、`recovery-public-failure`、
`replan-new-evidence`、`workflow-long-chain` 和 `workflow-human-approval-git`。

## 记录指标

每个 task/engine/model 样本至少记录：

- 主要结果：hidden verifier success、Agent status、patch 是否产生、失败类别；
- 过程：steps、Tool Calls、Retry、Replan、Recovery、commit 数（engine 不支持的字段为
  `null`）；
- 资源：prompt/completion/total Token、cached/cache-write Token（有则记录）、provider
  cost、官网 Standard 估算 cost；
- 时间：模型请求延迟、Agent Run duration、verifier duration，以及 Docker/镜像预检耗时；
- 可复现性：model ID、参数、task/snapshot SHA-256、image digest（可得时）、预算、代理
  mode、engine/prompt/tools 版本和结果 artifacts 路径。

首要比较是 verifier success rate、成对成功/失败差异和 pass@1；次要比较为中位 steps、
Tool Calls、Token、成本和 duration。三轮数据可报告 median 与范围，样本太小则只报告原始
值，不做显著性或泛化结论。

## 失败分类

使用单一、互斥的首要分类，并保留原始错误：

| 分类 | 含义 | 是否计入模型失败率 |
| --- | --- | --- |
| `ENVIRONMENT_UNAVAILABLE` | Docker daemon、镜像、网络或 verifier 环境不可用 | 否 |
| `API_AUTH_OR_QUOTA` | Key、权限、额度或模型不可用 | 否（单独报告） |
| `API_HTTP_ERROR` | 中转站 4xx/5xx、限流或请求超时 | 否（单独报告） |
| `REQUEST_UNSUPPORTED` | 参数、Responses/Chat 格式或 Tool Call 契约不支持 | 否（兼容性报告） |
| `MODEL_OUTPUT_INVALID` | 空响应、无法解析的 Tool Call 或非法 arguments | 是 |
| `AGENT_RUNTIME_ERROR` | Agent 解析、命令、预算、Recovery 或运行时错误 | 是 |
| `VERIFIER_FAILED` | Agent 结束但隐藏 verifier 非零退出 | 是 |
| `ARTIFACT_ERROR` | 结果无法持久化或关键证据丢失 | 是（并标记数据不完整） |

同一运行同时出现多个问题时，按“环境/API → 请求契约 → Agent runtime → verifier →
artifact”的顺序确定首要分类，其余写入 `errors`。环境/API 问题不能记为代码任务失败。

## 停止条件

- Stage 1 未通过的模型不进入 Agent Run；Stage 2 未通过则暂停全量测试并先修复或记录
  兼容性问题。
- Docker、镜像或 hidden verifier 不可用时停止受影响批次，记录
  `ENVIRONMENT_UNAVAILABLE`，不重试到伪造成功为止。
- 出现认证、额度、全局 endpoint 错误或连续限流/超时，停止该模型后续调用；先保留
  artifacts 和原始错误。
- 单次运行达到 max steps、wall-clock、连续失败或预设 cost guard 时结束该运行并记录
  触发原因；不为了追求通过率提高预算。
- 发现模型参数、任务快照、镜像或代理策略不一致时停止当前轮并作废该轮成对比较，修正
  配置后重新开始；不混合不同配置的结果。
- 任何时候都不打印或提交 API Key；usage/cost 缺失时停止成本推断，而不是停止功能测试。

## 命令示例

`probe` 和 `campaign` 默认从当前目录的 `.env` 补齐缺失的 `REPOPILOT_API_KEY` 和
`REPOPILOT_BASE_URL`；也可显式传 `--env-file`。它们不会把 Key 或 endpoint 写入汇总。

```bash
# Stage 0：构建默认 Git-enabled benchmark image
docker build -t repopilot-benchmark:py312-git docker/benchmark

# Stage 1：四模型 text + required Tool Call，共 8 个请求
.venv/bin/repopilot probe \
  --model gpt-5.6-sol \
  --model gpt-5.6-terra \
  --model gpt-5.6-luna \
  --model gpt-5.5

# Stage 2：Luna 两个 seed task 的 4 次 Agent Run
.venv/bin/repopilot campaign \
  --image repopilot-benchmark:py312-git \
  --model gpt-5.6-luna \
  --task seed-single-file \
  --task seed-cross-file

# Stage 3：四模型、全部六任务、两个 engine，共 48 次 Agent Run
.venv/bin/repopilot campaign \
  --image repopilot-benchmark:py312-git \
  --model gpt-5.6-sol \
  --model gpt-5.6-terra \
  --model gpt-5.6-luna \
  --model gpt-5.5 \
  --rounds 1

# Stage 4：相同矩阵三轮，共 144 次 Agent Run
.venv/bin/repopilot campaign \
  --image repopilot-benchmark:py312-git \
  --model gpt-5.6-sol \
  --model gpt-5.6-terra \
  --model gpt-5.6-luna \
  --model gpt-5.5 \
  --rounds 3

# Issue #18：Stage 4 前仅复测 Luna Git task 一对（2 次 Agent Run）
.venv/bin/repopilot campaign \
  --image repopilot-benchmark:py312-git \
  --model gpt-5.6-luna \
  --task workflow-human-approval-git \
  --engine baseline --engine repopilot --rounds 1
```

若开发机需要代理，将同一个策略传给成对 engine；没有代理时显式保持默认 `none`：

```bash
.venv/bin/repopilot campaign \
  --model gpt-5.6-luna \
  --docker-proxy-mode inherit \
  --engine baseline --engine repopilot

# 显式代理 URL 仅放在本地环境变量，不写入结果或文档
export REPOPILOT_DOCKER_PROXY_MODE=explicit
export REPOPILOT_DOCKER_PROXY_URL="$LOCAL_DOCKER_PROXY_URL"
.venv/bin/repopilot campaign --model gpt-5.6-luna --engine baseline --engine repopilot
```

campaign 会在 LiteLLM 内部自动补 `openai/` provider 路由前缀；发给中转站的底层模型 ID
仍是官网一致的 `gpt-5.6-luna`。`probe` 直接使用 Chat Completions，每个模型只做一次
text 和一次 `tool_choice="required"` 请求，失败不自动重试。

## 已观测结果

以下是本计划建立前已完成的低成本实测；费用是按上面的官网 Standard 价格和返回 usage
做的估算，不是中转站账单。脱敏结果分别保存在 [四模型 API probe](evidence/four-model-api-probe-v1/summary.md)
和 [Luna paired smoke](evidence/luna-paired-smoke-v1/summary.md)：

- 四个模型的 text probe 和 Tool Call probe 全部通过（`8/8`）。观测到 Terra 请求偏慢，
  延迟约 `33–40 s`；该现象需要在三轮中继续记录，不直接解释为 Agent 性能差异。
- 8 次 probe 的官网价格估算合计约 `$0.0587`。
- `gpt-5.6-luna` 的 `seed-single-file` smoke 中，baseline 和 RepoPilot 均通过隐藏
  verifier。随后通过新 `campaign` 命令完成 `seed-cross-file` 配对运行；两份 patch 的
  SHA-256 相同且都通过隐藏 verifier，但 RepoPilot 的最终 Agent status 为
  `BUDGET_EXCEEDED`（最后一次在途模型调用越过 180 秒墙钟预算）：

  | Task | Engine | Status | Steps | Total tokens | Cost | Agent duration |
  | --- | --- | --- | ---: | ---: | ---: | ---: |
  | seed-single-file | baseline | Submitted | 5 | 9,052 | $0.00276892 | 37.54 s |
  | seed-single-file | RepoPilot | SUCCEEDED | 7 | 12,819 | $0.00280760 | 47.42 s |
  | seed-cross-file | baseline | Submitted | 9 | 24,326 | $0.00663492 | 113.43 s |
  | seed-cross-file | RepoPilot | BUDGET_EXCEEDED | 6 | 10,218 | $0.00274480 | 196.11 s |

Stage 2 的四个 Target Repository 均通过 verifier，说明 endpoint、Agent、Docker 与 verifier
链路已经贯通；`BUDGET_EXCEEDED` 同时说明全量运行必须把“代码最终正确”和“Agent 在预算内
干净结束”分开报告。这些仍只有两对任务样本，不能作为四模型或长期胜率结论。

### Stage 3 单轮结果

2026-09-05 已完成四模型、六任务、双 engine 的 48 个样本，完整的脱敏汇总见
[Stage 3 evidence](evidence/four-model-stage3-v1/summary.md)。campaign 无 batch error，隐藏 verifier
总计通过 32/48；baseline 与 RepoPilot 都是 16/24。总使用量为 949,636 tokens，官网 Standard
估算为 `$3.25369592`，不是中转站账单。

本轮暴露出两个进入 Stage 4 前必须处理的限制：中转站存在显著长尾延迟，在途模型请求可越过
180 秒 Agent 预算后才返回；同时 `python:3.12-slim` 容器没有 Git，使
`workflow-human-approval-git` 被环境因素混淆。后者的 8 个样本保留在原始结果中，但不能用于
engine 排名；修复并固定包含 Git 的 benchmark image 后再执行 Stage 4。

Issue #18 的 [Git 镜像复测证据](evidence/luna-git-image-smoke-v1/summary.md) 已记录：同一固定
digest 的 Python/Git 预检通过，但 Luna 的 baseline 和 RepoPilot 分别用时约 413 秒和 290 秒，
均超预算且未通过 verifier。容器缺 Git 已修复；Stage 4 仍应等待后续官方 API 测试确认运行链路。

### Stage 4 六种子任务首轮干净结果

2026-09-06 使用固定 Git 镜像（`repopilot-benchmark:py312-git`，
digest `sha256:29c73ce6d8fc...`）对六个种子任务（每类一个）、`gpt-5.6-luna` 与
`gpt-5.6-sol`、三轮完成 72 个样本，无 batch error、无连接错误。脱敏汇总见
[Stage 4 六种子任务证据](evidence/stage4-seed6-luna-sol-v1/summary.md)。仓库 verifier 共通过
67/72；`task_pass` 明确判定中 Luna RepoPilot 11/13、Sol RepoPilot 8/13，优于各自 baseline
（8/12 与 7/12）；两引擎对 `seed-single-file`、`seed-cross-file` 全部通过。HITL 与
long-horizon 任务因完整 approval/budget 审计尚不支持而保持 `task null`。

本轮暴露两点：中转站长尾延迟仍可使在途模型请求越过 180 秒预算（RepoPilot 多次
`BUDGET_EXCEEDED` 但仓库仍正确），以及 manifest `run_budget`（24 步/240 秒等）尚未覆盖
CLI 默认预算。

### Stage 4 剩余 24 任务三轮结果

2026-09-07 用同镜像完成剩余 24 个 Stage 4 任务的 `gpt-5.6-luna` 与 `gpt-5.6-sol` 三轮
对比，共 288 样本、零 batch error。脱敏汇总见
[Stage 4 24 任务证据](evidence/stage4-24tasks-luna-sol-v1/summary.md)。执行前的两处修复：
① manifest `run_budget` 现在按字段覆盖共享 CLI 预算并以任务 timeout 封顶（原先仅记录不生效）；
② 中转站账户限制仅流式请求，故给两引擎增加 `--stream`（`stream=true` + chunk 聚合，
RepoPilot 走 `repopilot.model`、baseline 走 `StreamingLitellmModel`）。

总体：仓库 verifier 通过 199/288；`task_pass` 明确判定中 Sol RepoPilot 40/60、Sol baseline
33/60，显著优于 Luna（RepoPilot 21/66、baseline 27/63）。Sol 的 RepoPilot 在 recovery 与
replan 两类上优势最明显（recovery 12 轮中 9 轮 RepoPilot-only/both-pass；`recovery-argument-contract`
三轮全 RepoPilot-only），Luna 在多数 recovery/replan 轮次为 `neither_pass`。HITL/long-horizon
仍多为 `task null`/unsupported（完整 approval/budget 审计不支持）。6 例 MODEL_ERROR 按决策保留不
重跑；3 例环境错误（断网 InternalServerError ×2、上游 BadRequestError ×1）已在新输出根补跑替换并在
`summary.json` 标记 `rerun_replacement`。运行日志显示一次 21.4 万字符的截断响应使单个 run 拖至约
17.5 分钟（超出 240 秒预算），RepoPilot 的模型调用尚无运行期墙钟强制中断，属后续健壮性改进项。

连同六种子任务证据，两份 evidence 已覆盖 30 个 Stage 4 任务、两模型、三轮
（360 samples）。这批数据可以离线产出初始要求中的以下指标：repository/task
pass、category/capability 分项成功率、termination 混淆矩阵与成功率、Recovery /
Replan 触发与成功率、per-solved 效率指标（LLM calls / steps / tool calls /
tokens / tool failures）、redundant calls、paired 与按 category 的 paired、
三重复稳定性行。尚未覆盖且当前实现标记 unsupported 的指标包括：HITL 完整
approval 审计、完整 execution-budget 审计、post-solution churn（first solved
step）、逐阶段 latency / orchestration overhead、任意错误恢复与无意义 replan
判定；这些缺的不是“少跑一轮能补上的数据”，而是缺对应的 instrumentation（详见
repopilot-benchmark.md “Supported and deferred instrumentation”），因此
**不能在补功能前靠这些样本生成近似指标**。

**2026-09-07 决策**：benchmark 采用“两引擎可公平对比才实现”的原则。上述
unsupported 项在基线侧缺少对等的机制或记录（baseline 无结构化 approval
协议、无 failure/replan 预算执行、无 per-step 仓库快照，且无法提供逐阶段非重叠
时间 span），因此**不会为这些指标新增 instrumentation**；post-solution churn
与逐阶段 latency / orchestration overhead 明确放弃，approval / budget /
任意错误恢复 / 无意义 replan 维持 unsupported 或 experimental（仅作
RepoPilot 单侧观测，不进入引擎对比结论）。已有 360 样本的可对比指标即本阶段
完整证据，**不再安排“补 instrumentation 后整轮重跑填满全指标”的运行**。

后续若重跑，仅服务于更换数据源（官方 API 而非中转站）或提高 repeat 数
（正式终测 `--repeats 5`），模型集固定为 `gpt-5.6-sol` 与 `gpt-5.6-luna`
（不含 `gpt-5.6-terra` 与 `gpt-5.5`），不以填充上述 unsupported 指标为目标。

### 360 样本的存放与复算

Stage 4 全部 360 samples 分两层存放：

- 仓库内脱敏归档：`docs/evidence/stage4-24tasks-luna-sol-v1/`（24 任务、
  288 samples）与 `docs/evidence/stage4-seed6-luna-sol-v1/`（seed 6 任务、
  72 samples），各含可读 `summary.md` 与精简行级 `summary.json`。
- 仓库外原始运行（含完整 metrics/evaluation/trace/patch/workspace 与根级
  `evaluation_summary`）：`~/.local/state/repopilot/campaigns/<run-id>/`。
  24-task 主运行 + 两个 rerun 根（替换 3 个 baseline 环境错误 trial）对应
  24-task 证据；`seed-cross-file` 等五个任务与 `seed-single-file` 各自一个
  clean campaign 对应 seed 6 证据。

用 `src/repopilot/recompute.py` 可从原始 summary 完整复算
category/capability/numeric/paired 指标并落盘（后者覆盖前者，用于重跑替换
环境错误 trial）。每个 evidence 目录下已提交 `recomputed.json`（完整
`evaluation_summary` + 紧凑行清单；需要完整行级对象时加 `--include-rows`）
与 `recomputed.md`。该合并已用 `--include-rows` 核对：与 `summary.json`
的行级 key/status 零差异。用法详见 `repopilot-benchmark.md` “Reproduce
evidence from raw state”。
