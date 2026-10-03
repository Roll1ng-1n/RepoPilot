# 本地发行验证 (#35)

用户选择 repopilot-runtime，独立版本 0.1.0，保留 minisweagent 2.4.6、固定上游来源与 MIT 归属。名称可用性是查询时的 404，未保留名称、未上传包、未创建 release、未推送。

本地 python -m build 生成 wheel 和 sdist，twine check 均 PASSED。最终打包检查确认 RepoPilot 元数据/项目链接/CLI，LICENSE/UPSTREAM、配置和全部 30 个 manifest/快照/验证器；无 Python 缓存或 .env。摘要、字节与文件数见 wheel.json。实际构建日志见 build.txt；发行 workflow 仍用默认隔离构建，本地最终重建使用 --no-isolation（先安装了构建依赖）。

在全新 /tmp venv 安装本地 wheel 及独立下载的运行依赖，未使用 editable 或 system-site-packages。wheel_smoke.py 切到临时目录验证真实 subprocess help/version/doctor/inspect JSON，以及 native CLI 脚本模型修改 sample.py、verify_task、finish_task，最终 SUCCEEDED 且完整七类结果产物存在。见 smoke.json、smoke-stderr.txt、install.txt 与 installed.txt。doctor 无模型/凭据、paid_requests=0；沙箱内 Docker 不可访问如实记录，其含 Docker 契约已在完整回归中单独验证。

严格文档构建通过，见 docs-build.txt。核心回归 301 passed（含 Docker）、相关上游回归 46 passed；后续对象目录引用校验定向 9 passed。Ruff、diff whitespace 检查通过。tag 验证接受 repopilot-v0.1.0、拒绝不匹配版本，不读取上游版本。

默认核心 CI 无服务密钥，Docker/文档独立 job；external-probe workflow 仅显式手动输入模型才执行，配置缺失 skip，连接/鉴权/模型不可用 unavailable，协议验收失败 failure，分别产出 external-probe.json；skip 不算通过服务验证。本地无凭据脚本验证得到 skip，没有发出请求。

release workflow 手动或 repopilot-v* tag 入口，构建+twine+wheel 内容+干净安装 smoke，仅上传 CI artifact。源码 workflow 配置已检查；本轮没有远程 Actions 执行记录，实际 PyPI 发布尚未执行。
