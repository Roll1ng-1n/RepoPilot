# RepoPilot

RepoPilot 是面向代码仓库的 CLI Agent。它通过原生 Tool Calling 读取与修改代码，维护 Plan，执行验证，并保存可检查、可恢复的运行产物。正常完成需要验证证据；隐藏测试通过和 Agent 正常结束是分别报告的结果。

RepoPilot 版本为 `repopilot.__version__`；发行名称为 **repopilot-runtime**，CLI 和 Python 导入为 `repopilot`。发行包通过 [GitHub Releases](https://github.com/Roll1ng-1n/RepoPilot/releases) 提供；PyPI 发布状态见 [发行记录](docs/repopilot-release.md)。项目基于固定的 mini-SWE-agent v2.4.6，保留 `minisweagent` 包及上游入口。来源、原始 commit 和 MIT 许可见 [UPSTREAM.md](UPSTREAM.md) 与 [LICENSE.md](LICENSE.md)。

## 安装

需要 Python 3.10+、Git 和 ripgrep（`rg`）；Docker 运行另需可用的 daemon 和镜像。Ubuntu/WSL 可通过 `sudo apt-get install git ripgrep` 安装命令行依赖。从 [PyPI](https://pypi.org/project/repopilot-runtime/) 安装：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install repopilot-runtime==0.1.0
repopilot --version
repopilot --help
```

从 checkout 可安装 `python -m pip install .`，开发环境可安装 `python -m pip install -e '.[test]'`。本地发行验证使用 `python -m build`，再将 `dist/repopilot_runtime-*.whl` 安装到干净 venv；[发行决策与验证](docs/repopilot-release.md) 记录具体命令。

## 配置与首次运行

模型服务需支持 OpenAI-compatible native Tool Calling。在未提交的 `.env` 中配置：

```dotenv
REPOPILOT_MODEL=openai/your-model
REPOPILOT_API_KEY=your-key
REPOPILOT_BASE_URL=https://your-provider.example/v1
```

`doctor` 只检查本地配置与依赖，不请求模型。Local 环境直接在目标仓库运行命令：

```bash
repopilot doctor --env-file .env
repopilot run /path/to/repository \
  --task "Fix the parser failure and rerun its tests." \
  --env-file .env --environment local --state-dir ./agent-runs
```

Docker 环境先准备镜像：

```bash
docker build -t repopilot-benchmark:local -f docker/benchmark/Dockerfile .
repopilot run /path/to/repository --task "Fix the failing tests." \
  --env-file .env --environment docker --image repopilot-benchmark:local \
  --state-dir ./agent-runs
```

运行参数包括步骤、时间、tokens、费用和 Recovery 限额；见 `repopilot run --help`。容器代理配置见 [benchmark 操作说明](docs/repopilot-benchmark.md)。CLI 输出 Run ID、状态和产物目录。

## 检查、审批与恢复

```bash
repopilot inspect RUN_ID --state-dir ./agent-runs
repopilot inspect RUN_ID --state-dir ./agent-runs --json
repopilot resume RUN_ID --state-dir ./agent-runs --env-file .env
```

只有可恢复状态支持 resume，目标仓库必须匹配保存的状态。审批等待使用 `approve` / `reject`；具体参数见 [审批说明](docs/repopilot-approval.md)。恢复未知执行结果时不会重放可能修改文件的调用。

每次运行保存 metadata、Checkpoint、Trace、Plan、patch、验证和报告。schema 3 的大文本保存在同目录 `objects/`，备份与移动时保留完整目录。详见 [产物检查](docs/repopilot-inspect.md) 与 [保存格式和性能](docs/evidence/next-stage/performance/report.md)。

## 能力与证据

内置 benchmark 有 30 个固定任务，使用隔离的 host verifier；baseline 与 RepoPilot 可对照运行。`repository_pass`、`task_pass` 和正常终止分别记录，未知 usage/cost 保留 null。

- [能力来源矩阵](docs/repopilot-capabilities.md)：上游复用、RepoPilot 扩展和新增职责。
- [评测操作](docs/repopilot-benchmark.md)与[指标定义](docs/evidence/next-stage/metrics.md)：耗时、循环、首次实际源码修改与兼容语义。
- [下一阶段证据索引](docs/evidence/next-stage/report.md)：45 个正式真实对照已完成，原始失败、替换和未知结果均保留；本轮未证明循环检测的任务收益。
- [上下文进度复测](docs/evidence/issue27-real-models/report.md)：保留成功、预算耗尽和服务错误，历史模型不同的结果只作描述比较。
- [历史 SWE-bench smoke](docs/repopilot-swebench-smoke.md)：预算耗尽、无最终验证的负面记录，不能视为 SWE-bench 分数。

默认 CI 运行无凭据核心回归，Docker 和文档检查独立运行。真实模型调用需要显式选择模型并执行付费命令；离线检查不会自动调用服务。
