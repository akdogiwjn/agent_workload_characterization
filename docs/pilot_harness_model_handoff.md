# 试点 Harness / 模型配置核实任务书

状态：READY_FOR_IMPLEMENTATION（仅任务书，尚未执行本任务）。属于 P0-07 配置收尾，不是 P1 Runner 开发。

## 1. 目标与用户决定

按 benchmark 选择 harness；本轮仅为 SWE-bench `django__django-16485` 优先核实 **mini-SWE-agent**。不强制所有场景统一 harness，不切回 OpenClaw/OpenHands，不比较能力排行榜。

模型已选 **DeepSeek-V4-Flash**，配置位置 `/home/lcq/.config/opencode/opencode.json`。本轮核实精确模型标识、provider/协议和 mini-SWE-agent 配置路径，不能因为 OpenCode 能用就宣称该 harness 能用。

用户未设置金额上限，但要求 **每次运行前说明具体任务并取得明确确认**。本任务不授权任何真实或测试 API 请求。资源/时间预算仍是提案，没有金额上限不意味着不限资源、自动重试或自动运行。

## 2. 已有基线，不重复实施

- P0-08/09 最小分析及测试隔离已验收：175 项测试，v6 报告；P0-07 PARTIAL，G0/M1 未通过。
- 官方任务数据已获取：`data/catalog/pilot_task_record.yaml`，交付见 `docs/pilot_taskdata_delivery.md`。
- 数据 revision：`78f471bf655a3137b2e8a75af1501690ec009ec3`；Django base commit：`39f83765e12b0e5d260b7939fc3fe281d879b279`。
- 目标记录所需 evaluator 字段/类型及 parser/enum 已静态核对；镜像 `:latest` 未固定 digest，未验证可运行性。
- 原始 record 包含 reference patch/test_patch；尚未生成安全 Agent 输入投影，不能将整个 record 提供给 Agent。“不展示补丁”不等于技术上已完成输入隔离。
- 本地 SWE-bench commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` 有 mini-SWE-agent argv builder，**不证明 mini-SWE-agent 已安装、有源码或配置可用**。

## 3. 必读与范围

先完整阅读 `methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`；再读：

- `docs/data_management.md`、`docs/trace_contract.md`。
- `docs/p0_07_g0_handoff.md`、`docs/pilot_execution_spec.md`、`workload_catalog/pilot.yaml`。
- `docs/pilot_taskdata_delivery.md`、`data/catalog/pilot_task_record.yaml`。
- `reports/quality/pilot_evidence.json`、`reports/quality/g0_review.md`。
- 本地 `references/repos/SWE-bench/swebench/inference/mini_swe_agent.py`、其调用入口和相关配置说明。

允许：本地文件/版本元数据静态读取、固定少量文件哈希、相关自有文档与无密钥设计清单编辑。保留工作树已有改动。

禁止：安装/升级依赖、pip/uv sync、导入第三方包以探测、执行第三方 --help、网络探测/API 请求、下载/clone、镜像查询/拉取/构建、容器或 Agent 运行、P1-00 系统能力预检、修改 references/旧工程/用户配置、读取整个凭据库、Git commit/push。

若本地没有 mini-SWE-agent 源码或发行包元数据，记录缺口并提出**固定来源、版本、下载大小与用途**的获取请求；本任务不擅自下载，不把先前任务数据授权推广为软件获取授权。网络资料若确需查阅也应先说明范围并取得授权。

## 4. 凭据安全：先设计过滤，再读取

不得直接 `cat`、`sed`、`rg` 整个 opencode.json，不将原文件内容、完整 provider/options 对象或环境变量值输出到终端/报告/对话。

用受控解析器在内存中读取配置，仅读取匹配 DeepSeek-V4-Flash 的条目和必要关联；输出严格白名单：配置内 provider 键、模型显示名、模型映射键、协议/SDK 包名、是否使用环境变量引用、能力声明。能力声明不是实测结果。

- apiKey/token/password/Authorization/header 值一律不输出、不复制、不哈希；不要用匹配 secret 字段的黑名单替代输出白名单。
- URL 必须移除 userinfo、query、fragment；路径也可能含密钥/租户标识，不原样输出。必要时只报告协议类别、是否存在 base URL、需本地使用的配置字段路径。地址详细适配可在内存分析，不必发布具体端点。
- 只登记凭据引用方式和字段路径，不展开环境变量、不检查凭据有效性、不复制凭据到临时文件。
- 原配置不计算/发布全文哈希；记录经过白名单脱敏的配置投影及其摘要，明确不是原文件快照哈希。
- 配置不可解析（如 JSONC）时不能通过打印原文排错；使用已有安全解析能力或说明阻塞，不安装解析库、不草率用正则删除注释而损坏 URL。
- 检查模型名是否有多个匹配、显示名与请求 model ID 是否不同；有歧义先列脱敏候选，不自行猜测。绝不能将 API key 当 model ID 展示。

## 5. Harness 版本核实

在已知项目、catalog 和本地 Python 环境位置做定向查找，不递归扫描整个 home 或敏感配置目录。

优先读取发行包 `.dist-info/METADATA`、`direct_url.json`、锁文件、现有源码和 Git commit；不 import mini-SWE-agent/litellm，不执行其 CLI。元数据中的 URL 同样先脱敏。

记录：包版本/完整 commit、安装或源码 locator、实际入口模块、SWE-bench 配置文件、模型适配实现、依赖约束/锁定状态、Python 要求。区分“本地存在”“静态配置适配可行”“运行验证通过”。当前只允许前两种结论。

若发现多个版本，按证据提出一个推荐固定版本及理由；不因 latest 字样直接冻结版本。不修改现有环境。没有足够源码时，不用 argv builder 猜第三方配置字段。

## 6. 静态兼容性矩阵

每项记录 evidence_id、文件 SHA/源码行号、状态（confirmed_static / proposed / unknown / incompatible）、理由和后续验证方法：

| 项 | 核对要求 |
| --- | --- |
| 请求协议 | OpenCode 实际 SDK/协议，与该版本 mini 模型适配器是否一致；OpenAI-compatible 不是所有参数都兼容的保证 |
| model ID | 显示名、配置键、provider 路由前缀、线上请求字段明确区分，不自动加减前缀 |
| base URL / auth | 依据源码的字段名/环境引用，避免重复 `/v1`、认证方式不匹配；不发请求 |
| 工具动作格式 | 该版本用文本 bash action 还是结构化 tool call；不能仅凭“bash-only”推断协议 |
| 输出与错误 | response/usage/finish reason、流式行为、拒绝响应和解析失败的处理路径 |
| 参数与限制 | timeout、max steps/tokens、采样参数、重试、速率限制和费用跟踪；未知不是支持 |
| 成本处理 | 自定义模型是否被费用库识别，未知价格会否导致异常或零成本；不能将未知成本当免费 |
| 轨迹产物 | 原生消息、工具调用/结果、时序、patch 出口；不伪造 CPU 或单工具独占进程关系 |
| 执行环境 | Agent 执行镜像与 evaluator 镜像是否不同；当前 evaluator 的 latest tag 风险继续保留 |

不强行复用 telemetry proxy：先判断当前模型路径能否获得必要原生数据。若需要 proxy/适配补丁，列 P1 实现项，不在此任务启动或开发。

明确未来 Agent 输入白名单（例如 problem_statement、repo/base_commit、必要工作目录），以及需排除的 patch/test_patch/测试答案字段；本轮只写设计，不运行 Agent，不将原始任务记录作为命令输入。

## 7. 交付物

新增：

1. `docs/pilot_harness_model_compatibility.md`：版本证据、脱敏映射、兼容性矩阵、未验证项、最小后续工作。
2. `reports/quality/pilot_harness_model_evidence.json`：静态证据索引与脱敏配置摘要，禁止密钥/认证 header/原始配置全文。
3. `docs/pilot_harness_model_delivery.md`：实际读取范围、命令、改动、结果、缺口和下一步需要的授权。

增量更新 `workload_catalog/pilot.yaml`、`docs/pilot_execution_spec.md`、`reports/quality/g0_review.md` 及必要的任务状态说明：不要继续询问已定的 DeepSeek 模型选择/按 benchmark 选择策略；只询问确实缺失的版本获取、映射歧义等信息。

可提供**未执行的配置模板**，凭据仅用占位符/环境引用；所有参数有源码依据。不得让模板默认可运行、自动触发下载或调用模型。未知参数保持待定，不制造貌似完整的 runnable 配置。

不改分析代码、IR、测试、历史报告包、官方原始任务记录；不重新跑 macro 来掩盖配置缺口。

## 8. 验收与停止

- 文档/JSON/YAML 可解析、证据路径/版本真实、普通源码哈希可复核、无敏感字段泄露。
- 所有兼容性结论有实际读取证据；不能把配置字段存在等同运行成功。
- 模型名称选择已确认，但精确 provider/协议映射未核实时 `frozen=false`；harness 版本未确定亦同。
- G0/M1 不自动通过；缺源码可交付 PARTIAL，列一个精确、有限的获取请求，不无限遍历或自动安装。
- 只做文档/静态检查时无需重跑175测试。实际执行 `git diff --check`、文档链接及脱敏交付物检查，报告真实结果，不贴历史命令当本轮结果。

完成后停止。若下一步需要联网获取源码、安装依赖、模型连通性测试或真实 task，必须分别说明行动清单、范围、资源/费用风险，等待用户明确确认；本任务书不包含这些授权。
