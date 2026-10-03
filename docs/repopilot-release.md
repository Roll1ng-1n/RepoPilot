# RepoPilot 发行与本地安装验证

用户确认发行名称为 `repopilot-runtime`。注册表查询见 [名称记录](evidence/next-stage/pypi-names.json)：原三个名称被占用，候选查询为 404；404 表示当时未找到项目，不表示名称已保留。CLI 与导入仍为 `repopilot`。

RepoPilot 独立版本来自 `src/repopilot/__init__.py`，当前 0.1.0；保留上游 `minisweagent.__version__=2.4.6`，固定来源见 [UPSTREAM](https://github.com/Roll1ng-1n/RepoPilot/blob/main/UPSTREAM.md)。wheel 保留 LICENSE、UPSTREAM、上游配置、入口以及全部 30 个任务的 manifest、快照、行为与隐藏验证器。

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m venv /tmp/repopilot-wheel
/tmp/repopilot-wheel/bin/python -m pip install dist/*.whl
/tmp/repopilot-wheel/bin/python scripts/packaging/wheel_smoke.py
```

smoke 在临时工作目录运行已安装包，检查 help/version、无凭据 doctor、脚本模型驱动的 native CLI Run 与真实 subprocess inspect JSON；不调用模型服务，不依赖 editable checkout。构建日志见 [packaging](evidence/next-stage/packaging/report.md)。

发行 workflow 支持手动和 `repopilot-v<version>` tag，校验 tag/RepoPilot version 后构建、twine check 和干净安装 smoke，仅上传 CI artifact。当前无 PyPI 上传步骤、无 release 创建步骤。本次未推送源码、未上传包、未创建 release。

默认核心 CI 无模型密钥，Docker 契约与文档检查单独执行。外部模型检查是显式手动命令：未提供配置时 skip，服务/模型不可用时记录 unavailable，运行验收失败时保留 failure；不会用空集成样本宣称外部成功。
