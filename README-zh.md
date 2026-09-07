# RepoPilot V1 —— 可评测、可恢复的软件工程 Agent

RepoPilot 是一个 CLI 优先的软件工程 Agent，用于在目标仓库中进行有界、可解释、可验证的修改。一次运行会形成计划，通过结构化工具调用检查和修改代码，执行任务验证，并留下检查点、追踪记录、补丁和人类可读的报告。本项目定位为一个小巧、可检查的 V1 工程工作流与学习项目，并不声称具备生产环境级别的自主安全性或模型性能。

RepoPilot 基于固定版本的 mini-SWE-agent v2.4.6 源码快照开发。保留的 `minisweagent` 包、上游许可证和源码归属信息见 [UPSTREAM.md](UPSTREAM.md)。[能力来源矩阵](docs/repopilot-capabilities.md) 区分了上游复用、RepoPilot 扩展和 RepoPilot 新增能力。

## 安装与快速演示

在代码检出目录中，使用隔离环境安装 CLI 和开发依赖：

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

`repopilot run` 需要支持 OpenAI 兼容原生工具调用（Tool Calling）的模型，以及对应服务商的凭据。下面是一个最小化的本地环境调用示例；本地运行会直接在目标仓库中执行命令：

```bash
export REPOPILOT_MODEL=provider/model-name
repopilot run /path/to/target-repository \
  --task "Fix the failing parser tests and verify the change." \
  --environment local
```

CLI 会输出 Agent 运行 ID、当前计划、终态和产物目录。这个示例并不保证运行成功：结果取决于配置的模型、目标仓库和验证证据。

## CLI 工作流

同一个 CLI 提供了 Agent Run 生命周期的主要操作：

```bash
# 查看已持久化的运行记录但不执行（使用 --json 输出一个机器可读的文档）。
repopilot inspect RUN_ID --state-dir /path/to/state --json

# 重新创建执行环境后，恢复一个已停止的运行。
repopilot resume RUN_ID --state-dir /path/to/state --model provider/model-name

# 处理待批准的人工审批，然后让运行从检查点继续。
repopilot approve RUN_ID --state-dir /path/to/state
repopilot reject RUN_ID --state-dir /path/to/state
```

`run` 默认使用本地环境，并明确提示它可能直接修改目标仓库。也可以传入 `--environment docker --image python:3.12-slim` 使用 Docker 后端。Docker 会将目标仓库绑定挂载到 `/workspace`；它是执行后端，而不是完整的安全边界。如果机器上无法使用 Docker，基准测试会记录 `ENVIRONMENT_UNAVAILABLE`，不会静默回退到本地执行。

## 架构概览

`repopilot.cli` 中的组合层负责创建模型、执行环境、工具注册表、计划、上下文策略、运行预算和产物存储。`AgentRuntime` 驱动有界的 Agent Run。工具注册表负责验证原生工具调用，并分发仓库、命令、验证、Git 和 Agent 控制操作。本地与 Docker 后端实现相同的执行环境协议。检查点使 `STOPPED` 和 `WAITING_FOR_APPROVAL` 状态的运行可以恢复；即使提示上下文被压缩，JSONL 追踪事件仍会保留完整的审计历史。

如需查看精简的证据地图，请参阅[能力来源矩阵](docs/repopilot-capabilities.md)。其中将每项声明的能力关联到对应的 CLI 路径、运行时测试、追踪记录/产物或实现源码。[设计验证记录](docs/repopilot-design-validation-record.md)保存了选定的失败案例、根因、修复、验证结果及相关提交。

## 固定 Agent 基准测试

```bash
repopilot benchmark \
  --model provider/model-name \
  --image python:3.12-slim \
  --task seed-cross-file \
  --task workflow-long-chain \
  --engine repopilot
```

重复使用 `--task` 可运行指定的固定任务；省略该参数则运行包含六项任务的套件。重复使用 `--engine` 可选择基线、RepoPilot 或两者。每项任务都有固定的快照版本/哈希、任务描述、仅在主机上运行的隐藏验证器、成功条件、超时限制和运行预算。运行器会创建相互独立的 Git 工作区，并保留原始结果、补丁、提交和验证输出。任务列表和行为覆盖范围见[基准测试详情](docs/repopilot-benchmark.md)。

仓库中提交的[微基准测试摘要](docs/evidence/micro-benchmark-v1/summary.md)是一次保留的历史记录：该次运行包含 12 个样本，但 Docker 不可用。全部 12 个任务/引擎尝试均为 `ENVIRONMENT_UNAVAILABLE`，模型调用次数为 0，且 `success: null`；因此这次运行没有基于模型的结果（应理解为 0/0，而不是 0%）。

单独的[基于模型的冒烟测试证据](docs/evidence/model-backed-smoke-v1/summary.md)记录了在同一个经过脱敏的低成本授权模型、温度、运行预算和 Docker 镜像下，两个引擎各执行一次 `seed-single-file` 任务。基线结果为 `Submitted`，隐藏验证器为 `true`，7 个步骤、总计 19,660 个 token、7 次工具调用、耗时 20.475 秒，`cost: null`；RepoPilot 结果为 `SUCCEEDED`，验证器为 `true`，7 个步骤、总计 28,212 个 token、9 次工具调用、0 次重试、0 次重新规划、耗时 19.723 秒，`cost: null`。模型名称和端点均已脱敏，API 密钥扫描通过。这是两个引擎对同一项任务的尝试，属于冒烟测试证据，不是统计意义上的胜率，也不是一般性能声明。

当前的 [SWE-bench Lite 冒烟测试结果](docs/evidence/swebench-lite-smoke-v1/sqlfluff__sqlfluff-1625/result.json)是实际的负向冒烟测试证据，不是 SWE-bench 得分。固定版本的 SQLFluff 镜像已预加载到本地，已安装 `swebench` 5.0.2，Docker 启动、`/testbed` 和官方 gold patch 验证器预检均已通过（`status: READY`，`gold resolved: true`）。经授权的低成本模型在 27.4755 秒内被调用 5 次；`cost: null`。在 `max_steps=5` 的限制下，Agent 以 `BUDGET_EXCEEDED` 结束，没有生成补丁，最终验证器未运行，且 `success: null`。模型名称和端点已脱敏，API 密钥扫描通过。

要复现基于模型的 SWE-bench 冒烟测试，需要官方 `swebench` Python 包和固定版本的镜像已在本地可用。在构造模型之前，缺失的验证器或镜像前置条件就会被记录下来。

```bash
uv pip install swebench
```

缺失的服务商用量、费用或耗时数据会以 JSON `null` 记录；RepoPilot 不会估算这些数据。六项任务的基准测试是开发阶段的回归证据，样本规模较小，并非具有统计效力的比较，也不代表具备泛化能力。

## 已知限制与范围之外

- 本地执行会直接影响目标仓库，应将其视为由开发者控制的环境。
- Docker 隔离能力取决于主机和配置的镜像；本项目不将 Docker 描述为完整的安全边界。
- 模型/服务商可用性、凭据、原生工具调用支持以及返回的用量数据都属于外部依赖。环境失败或不可用只能说明执行可用性，不能说明任务正确性。
- 基准测试包含六项很小的固定任务，无法据此确定成功率、费用排名或一般性能。
- V1 只对 Python 目标仓库进行正式验证；现有证据不宣称支持其他语言。
- 人工审批是轻量级、尽力而为的风险策略。Git 仅支持本地提交；不支持 push、pull、rebase、reset 和创建 Pull Request。
- RAG 记忆、多 Agent 编排、Web UI、远程执行后端和完整 SWE-bench 运行均在范围之外。
- SWE-bench Lite 冒烟测试是一次固定版本的负向运行（`BUDGET_EXCEEDED`，没有补丁或最终验证器结果），不是 SWE-bench 得分，也不是一般性能声明。

---

## 上游 mini-SWE-agent 基础

以下内容是为保留归属信息而收录的上游项目简介。关于 Docker、模型和 SWE-bench 的说明描述的是上游 mini-SWE-agent，而不是 RepoPilot V1 的运行或结果。

<div align="center">
<a href="https://mini-swe-agent.com/latest/"><img src="https://github.com/SWE-agent/mini-swe-agent/raw/main/docs/assets/mini-swe-agent-banner.svg" alt="mini-swe-agent banner" style="height: 7em"/></a>
</div>

### 极简 AI 软件工程 Agent

📣 [mini-swe-agent 现在为 Ramp SWE-Bench 提供支持](https://labs.ramp.com/swebench)<br/>
📣 [mini-swe-agent 在 DeepSWE 上击败 Claude Code 和 Codex](https://deepswe.datacurve.ai/blog#evaluation-harness)<br/>
📣 [在全新且极具挑战性的 ProgramBench 基准测试上运行 mini-swe-agent](https://mini-swe-agent.com/latest/usage/programbench/)<br/>
📣 [关于构建极简 AI Agent 的新教程](https://minimal-agent.com/)

[![文档](https://img.shields.io/badge/Docs-green?style=for-the-badge&logo=materialformkdocs&logoColor=white)](https://mini-swe-agent.com/latest/)
[![Slack](https://img.shields.io/badge/Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://join.slack.com/t/swe-bench/shared_invite/zt-36pj9bu5s-o3_yXPZbaH2wVnxnss1EkQ)
[![PyPI - 版本](https://img.shields.io/pypi/v/mini-swe-agent?style=for-the-badge&logo=python&logoColor=white&labelColor=black&color=deeppink)](https://pypi.org/project/mini-swe-agent/)

> [!WARNING]
> 这是 **mini-swe-agent v2**。请阅读[迁移指南](https://mini-swe-agent.com/latest/advanced/v2_migration/)。如需使用之前的版本，请查看 [v1 分支](https://github.com/SWE-agent/mini-swe-agent/tree/v1)。

2024 年，我们构建了 [SWE-bench](https://github.com/swe-bench/SWE-bench) 和 [SWE-agent](https://github.com/swe-agent/swe-agent)，并帮助开启了编程 Agent 的浪潮。

现在我们想问：**如果我们的 Agent 简化 100 倍，却仍然几乎一样好用，会怎样？**

`mini` 具备以下特点：

- **广泛采用**：被 Meta、NVIDIA、Essential AI、IBM、Nebius、Anyscale、普林斯顿大学、斯坦福大学等众多机构使用。
- **极简**：Agent 类只有约 100 行 Python 代码（[环境](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py)、[模型](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/models/litellm_model.py)和[运行脚本](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/run/hello_world.py)会再多一些），没有复杂的依赖！
- **高性能**：在 [SWE-bench verified 基准测试](https://www.swebench.com/)中得分超过 74%，启动速度远快于 Claude Code。
- **易部署**：支持**本地环境**、**docker/podman**、**singularity/apptainer**、**bublewrap**、**contree** 等。
- **兼容性强**：通过 **litellm**、**openrouter**、**portkey** 等支持所有模型；支持 `/completion` 和 `/response` 端点、交错思考等功能。
- 由普林斯顿大学和斯坦福大学团队构建，该团队也是 [SWE-bench](https://swebench.com)、[SWE-agent](https://swe-agent.com) 等项目的幕后团队。
- **经过测试**：[![Codecov](https://img.shields.io/codecov/c/github/swe-agent/mini-swe-agent?style=flat-square)](https://codecov.io/gh/SWE-agent/mini-swe-agent)

<details>

<summary>更多动机（研究方向）</summary>

[SWE-agent](https://swe-agent.com/latest/) 在 2024 年推动了 AI Agent 的发展。当时，我们非常重视工具和专用的 Agent-计算机接口。然而一年之后，随着语言模型能力增强，构建有用的 Agent 根本不再需要这么多东西！

事实上，`mini` Agent：

- **除了 bash 没有其他工具**——它甚至不需要使用语言模型的工具调用接口。这意味着你几乎可以使用任何模型运行它。在沙箱环境中运行时，也不需要费心安装任何包——它只需要 bash。
- **拥有完全线性的历史记录**——Agent 的每一步都只是向消息中追加内容，仅此而已。因此，Agent 轨迹和传给语言模型的消息之间没有区别，非常适合调试和微调。
- **使用 `subprocess.run` 执行动作**——每个动作都是完全独立的（不同于保持一个有状态的 shell 会话）。这使它可以轻松地在沙箱中执行（实际上只需用 `docker exec` 替换 `subprocess.run`），也可以轻松扩展。说真的，这一点非常重要（参见[为什么没有 shell 会话](https://mini-swe-agent.com/latest/faq/#why-no-shell-session)）。

这使它非常适合作为基线系统，也适合作为一种将注意力放在语言模型（而非 Agent 脚手架）上的系统。
你可以在 [SWE-bench（仅 bash）](https://www.swebench.com/)排行榜上看到它的成果；该排行榜评估不同语言模型使用 `mini` 时的表现。

</details>

<details>
<summary>更多动机（工具方向）</summary>

有些 Agent 是为研究过度定制的产物，另一些则是 UI 臃肿的前端巨兽。

`mini` Agent 希望成为一个可改造的工具，而不是黑盒：

- 足够**简单**，一眼就能理解
- 足够**方便**，可以用于日常工作流
- 足够**灵活**，便于扩展

与其他 Agent（包括我们自己的 [swe-agent](https://swe-agent.com/latest/)）不同，它极其简单，原因在于：

- **除了 bash 没有其他工具**——它甚至不需要使用语言模型的工具调用接口。我们没有为 Agent 可能需要的每件事都实现自定义工具，而是让语言模型充分利用 shell。如果你希望它完成某件具体的事情，例如创建 PR，只要告诉语言模型，让它自己想办法即可，无需花时间在 Agent 中实现这项功能。
- **使用 `subprocess.run` 执行动作**——每个动作都是完全独立的（不同于保持一个有状态的 shell 会话）。这对 Agent 的稳定性非常重要，参见[为什么没有 shell 会话](https://mini-swe-agent.com/latest/faq/#why-no-shell-session)。
- **拥有完全线性的历史记录**——Agent 的每一步都只是将内容追加到下一步传给语言模型的消息中，仅此而已。这非常有利于调试，也便于理解传给语言模型的提示内容。

</details>

<details>
<summary>我应该使用 SWE-agent 还是 mini-SWE-agent？</summary>

你可以将 `mini-swe-agent` 作为默认选择。
特别是当你满足以下条件时，应使用 `mini-swe-agent`：

- 想要一个可以在本地运行的快速命令行工具
- 想要一个控制流非常简单的 Agent
- 想要更快、更简单、更稳定的沙箱和基准测试评估
- 正在进行微调（FT）或强化学习（RL），不希望对某个特定 Agent 脚手架过拟合

当你满足以下条件时，可以使用 `swe-agent`：

- 想要试验不同的工具集合，并让每个工具拥有自己的接口
- 想要试验不同的历史记录处理器

两者都能提供：

- 在 SWE-Bench 上的出色性能
- 轨迹浏览器

</details>

<table>
<tr>
<td width="50%">
<a href="https://mini-swe-agent.com/latest/usage/mini/"><strong>CLI</strong></a> (<code>mini</code>)
</td>
<td>
<a href="https://mini-swe-agent.com/latest/usage/swebench/"><strong>批量推理</strong></a>
</td>
</tr>
<tr>
<td width="50%">

![mini](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/mini.gif?raw=true)

</td>
<td>

![swebench](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/swebench.gif?raw=true)

</td>
</tr>
<tr>
<td>
<a href="https://mini-swe-agent.com/latest/usage/inspector/"><strong>轨迹浏览器</strong></a>
</td>
<td>
<a href="https://mini-swe-agent.com/latest/advanced/cookbook/"><strong>Python 绑定</strong></a>
</td>
</tr>
<tr>
<td>

![inspector](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/inspector.gif?raw=true)

</td>
<td>

```python
agent = DefaultAgent(
    LitellmModel(model_name=...),
    LocalEnvironment(),
)
agent.run("Write a sudoku game")
```

</td>
</tr>
</table>

## 开始使用

**选项 1：** 如果你只想试用 CLI（软件包会安装在匿名虚拟环境中）：

```bash
pip install uv && uvx mini-swe-agent
# 或
pip install pipx && pipx ensurepath && pipx run mini-swe-agent
```

**选项 2：** 在当前环境中安装 CLI 和 Python 绑定：

```bash
pip install mini-swe-agent
mini  # 运行 CLI
```

**选项 3：** 从源码安装（开发者设置）：

```bash
git clone https://github.com/SWE-agent/mini-swe-agent.git
cd mini-swe-agent && pip install -e .
mini  # 运行 CLI
```

更多信息请参阅我们的[文档](https://mini-swe-agent.com/latest/)：

* [快速开始指南](https://mini-swe-agent.com/latest/quickstart/)
* [使用 `mini` CLI](https://mini-swe-agent.com/latest/usage/mini/)
* [全局配置](https://mini-swe-agent.com/latest/advanced/global_configuration/)
* [Yaml 配置文件](https://mini-swe-agent.com/latest/advanced/yaml_configuration/)
* [通过 cookbook 扩展能力](https://mini-swe-agent.com/latest/advanced/cookbook/)
* [常见问题](https://mini-swe-agent.com/latest/faq/)
* [参与贡献！](https://mini-swe-agent.com/latest/contributing/)

## 归属与引用

如果这项工作对你有所帮助，欢迎在研究中引用 [SWE-agent 论文](https://arxiv.org/abs/2405.15793)：

```bibtex
@inproceedings{yang2024sweagent,
  title={{SWE}-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author={John Yang and Carlos E Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik R Narasimhan and Ofir Press},
  booktitle={The Thirty-eighth Annual Conference on Neural Information Processing Systems},
  year={2024},
  url={https://arxiv.org/abs/2405.15793}
}
```

我们的其他项目：

<div align="center">
  <a href="https://github.com/SWE-agent/SWE-agent"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/sweagent_logo_text_below.svg" alt="SWE-agent" height="120px"></a>
   &nbsp;&nbsp;
  <a href="https://github.com/SWE-agent/SWE-ReX"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swerex_logo_text_below.svg" alt="SWE-ReX" height="120px"></a>
   &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/SWE-bench"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swebench_logo_text_below.svg" alt="SWE-bench" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/SWE-smith"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swesmith_logo_text_below.svg" alt="SWE-smith" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/codeclash-ai/codeclash"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/codeclash_logo_text_below.svg" alt="CodeClash" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/sb-cli"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/sbcli_logo_text_below.svg" alt="sb-cli" height="120px"></a>
</div>
