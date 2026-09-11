# mini-SWE-agent 2.4.6 获取与静态阅读任务书

状态：READY。用户已明确授权“允许下载并阅读代码”。继续采用执行模型实施、评审模型验收的方式。

## 1. 本次授权边界

仅获取锁定的 **一个 2.4.6 wheel**，校验后静态读取源码、包元数据和 bundled config，完成 DeepSeek-V4-Flash 接入设计。

不安装、不 import 包、不执行 --help/CLI/setup/build/测试；不调用模型，不探测 endpoint/API key，不下载依赖或其他版本，不运行容器/benchmark/P1 预检。不修改 references、用户配置、旧源码、原始任务记录或已验收分析代码。不提交/推送 Git。

wheel 是 ZIP 数据，不是要执行的程序；读取它不代表批准安装或首次运行。网络工具所需权限按平台机制申请，不绕过沙箱。

## 2. 开始前阅读

完整阅读 `methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`，再读：

- `docs/pilot_harness_model_handoff.md`（凭据白名单规则继续有效）。
- `docs/pilot_harness_model_compatibility.md`、`reports/quality/pilot_harness_model_evidence.json`。
- `docs/pilot_execution_spec.md`、`workload_catalog/pilot.yaml`、`docs/pilot_taskdata_delivery.md`。
- 本地 SWE-bench `swebench/inference/mini_swe_agent.py` 与 `uv.lock` 的 mini 条目。

模型已选 DeepSeek-V4-Flash，按 benchmark 选 harness；本次核实 mini 2.4.6，不重新询问这些选择。用户没有金额上限，但每次真实运行前必须列明任务和风险并单独确认。

## 3. 唯一允许获取的对象

来源：本地 SWE-bench commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` 的 uv.lock。

```text
filename: mini_swe_agent-2.4.6-py3-none-any.whl
bytes: 115037
sha256: a35463c553ac825c7773b03cfa69cd44958e3af20155dcc5711fdf9e4c67cd54
url: https://files.pythonhosted.org/packages/a2/00/a2f454775f69f540ab529c5f5e35d672f6491f0e6edab7cb196a0d2a0e2e/mini_swe_agent-2.4.6-py3-none-any.whl
```

保存建议：`data/raw/software/mini_swe_agent/2.4.6/`（软件参考包，不是 Agent trace；现有 raw 忽略规则适用）。新目录独占创建，禁止覆盖。若已有相同包，重新校验后复用；内容不符立即停止，不删除/覆盖，不改 expected hash 来通过。

下载使用不带认证的 HTTPS 客户端，设超时和大小上限（例如1 MiB）；不能用 pip install/pip download 触发依赖解析。若源不可访问，只报告失败；授权不扩展到 Git clone、镜像站或另一版本。

校验文件大小和完整 SHA 后再读取 ZIP。优先直接读取指定成员，不必解包；若确需解包，拒绝绝对路径、`..`、软链接、越界路径，限制展开总大小。不执行任何成员。记录包下载时间、URL、实际哈希、成员路径与读取成员 SHA。

## 4. 静态核实清单

先读 METADATA/WHEEL 与目录清单，再定位实际存在的入口、配置和模型源码。不要假定成员路径必然与旧版一致。

1. **版本/依赖**：发行版本、Requires-Python、Requires-Dist、入口点与 bundled config。SWE-bench 自身的 Python 要求不能冒充 mini 的要求。
2. **调用链**：SWE-bench argv builder → mini benchmark 入口 → 配置层叠 → model/environment/agent。指出确切优先级、配置字段和默认值。
3. **模型路由**：OpenAI-compatible/LiteLLM 路由、自定义 base URL、model ID 前缀、认证引用、流式模式和参数传递。区分源码证实、设计建议和待联网验证，不猜补 `/v1` 或 provider 前缀。
4. **动作协议**：2.4.6 实际使用的 action 格式、解析规则、工具执行入口；不得拿1.17.3历史轨迹替代当前证据。
5. **限额/异常**：step/token/timeout/retry/cost 设置、默认重试、未知价格异常及超限行为。只检查 mini 的真实调用链；SWE-bench run_api.py 的价格字典不是 mini 计费证据。
6. **日志/隐私**：trajectory 是否保存完整 config、model kwargs/API key；usage、tokens、cost 的来源；错误日志是否可能打印凭据。发现持久化风险必须列为首次运行前阻塞项，不能仅声称会注意。
7. **环境/产物**：Agent 环境选择、镜像/工作目录、提交 patch 出口、任务字段传递及参考解答隔离。只写白名单设计，不把含 reference patch 的 record.json 整体送入 Agent。

DeepSeek 配置优先使用此前脱敏投影，不重复读取原始配置。确需核对时严格遵守旧任务书：内存解析、输出白名单、密钥不提取/输出/持久化、URL脱敏、不打印配置全文；截断不等于脱敏。

若模型适配器委托给未取得源码的 LiteLLM/openai 依赖，则只能确认传入参数与调用点；下游行为标 unknown，列精确依赖版本与后续需查的内容。不因本授权自动获取依赖，也不能为填表编造兼容结论。

成本字段为0不能断言免费；未知价格单列不可用。无需用户重新设置金额上限，须给出计费/usage记录方案和后续运行确认流程。

## 5. 交付

新增：

- `data/catalog/mini_2_4_6_artifact.yaml`：软件包角色、URL、大小、SHA、locator、版本、许可证元数据来源；不是 sources.yaml 的 trace 数据源。
- `reports/quality/mini_2_4_6_static_evidence.json`：包与成员哈希、源码定位、字段级结论和未验证项；无密钥。
- `docs/mini_2_4_6_static_delivery.md`：实际下载与只读命令、读取成员、检查结果、文件变更与下一依赖。

增量更新 `docs/pilot_harness_model_compatibility.md`、`workload_catalog/pilot.yaml`、`docs/pilot_execution_spec.md`、`reports/quality/g0_review.md`：DEC-MINISRC 已授权且实际获取成功后才标完成；GAP-MINI-SRC 已解决不等于模型连通或环境可运行。

给出不含凭据的 **配置设计表/占位模板**，每个字段对应源码证据。模板标“未执行、非运行授权”，未核实项保留 null/原因，不输出貌似可直接运行的完整命令。

本轮不开发 proxy/wrapper、安装环境、实现 Agent 输入投影或修改分析器。不通过批量重写历史报告抹去此前错误。

## 6. 验收与停止

检查：固定文件大小/SHA、版本元数据、成员来源引用、输出 JSON/YAML 可解析、本地链接、敏感信息保护与 `git diff --check`。没有改代码无需重跑175项测试；不要将历史结果写成本轮执行。

交付清晰区分：

- 已确认：当前版本代码明确表达的行为。
- 可设计但未运行：DeepSeek 参数映射/安全配置提案。
- 仍阻塞：下游依赖未知、凭据落盘风险、版本未固定或其他必要信息。
- 后续动态验证：网络请求、镜像与真实运行，必须单独授权。

完成报告后停止。P0-07/G0/M1 不自动通过；由评审依据证据决定下一步，不自动执行连通性测试。
