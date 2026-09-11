# 首次运行准备包：执行任务书

日期：2026-09-11。状态：**任务书已准备，实施未开始**。

执行批次 ID：`PREP-01`。关联 P0-07 收尾、P1-00 只读预检子集、P1-07 准备层；不新建完整 Runner/Collector 平台。

## 1. 目标与交付终点

把已完成的静态核实转为**可测试的本项目准备代码 + 一份具体的运行审批清单**，服务 RQ2/RQ3 的后续真实运行与本地资源观测。

本批做完后，应能从固定任务记录生成安全的 Agent 输入、检查候选配置、报告本机可观测能力，并明确下一次安装/连通性/真实任务分别要做什么。**不是本批跑通 benchmark，也不是重新开展一轮广泛源码审计。**

允许依赖缺失、Docker 不可访问、PMU 未验证等真实限制存在：完整报告这些限制且离线准备功能通过，就可以交付准备包。不得因此无限延长本批，也不得标成运行兼容性已通过。

## 2. 当前事实与固定选择

| 项 | 当前依据 |
| --- | --- |
| 项目 | `/home/lcq/agent_workload_characterization`；自有代码在 `src/agent_workload_characterization/` |
| 已验收底座 | P0-00-r2、P0-01～05、P0-10 小样、P0-08/09 最小集；上次报告基线 175 项测试 |
| 试点 | SWE-bench Verified，唯一任务 `django__django-16485` |
| 模型 | DeepSeek-V4-Flash；配置键 `deepseek-v4-flash`，用户指定配置位置 `/home/lcq/.config/opencode/opencode.json` |
| Harness | mini-SWE-agent 2.4.6，wheel 已下载并静态阅读；不以历史 1.17.3/OpenHands 轨迹代替当前版本证据 |
| 任务记录 | `data/catalog/pilot_task_record.yaml` 定位的固定 revision、本地单条记录；不重新下载数据集 |
| 金额 | 用户不设金额上限；费用未知必须标未知，不等于免费 |
| 运行授权 | 每次真实运行前说明具体操作并等待用户确认；本批不含安装、镜像操作、API 或 benchmark 执行 |

记录 revision：`78f471bf655a3137b2e8a75af1501690ec009ec3`。
记录 SHA-256：`762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`。
mini wheel SHA-256：`a35463c553ac825c7773b03cfa69cd44958e3af20155dcc5711fdf9e4c67cd54`。
以对应 catalog 和实物核对为准；不复制敏感配置全文来计算“证据哈希”。

## 3. 阅读与复用

先完整阅读 `methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`，再读 `docs/data_management.md`、`docs/trace_contract.md`。

本批直接输入：

- `docs/pilot_execution_spec.md`、`workload_catalog/pilot.yaml`；
- `docs/pilot_taskdata_delivery.md`、`data/catalog/pilot_task_record.yaml`；
- `docs/mini_2_4_6_static_delivery.md`、`data/catalog/mini_2_4_6_artifact.yaml`；
- `docs/pilot_harness_model_compatibility.md`、`reports/quality/mini_2_4_6_static_evidence.json`；
- 现有 CLI、catalog/输出保护实现、测试组织方式。

仅针对实施需要核对已下载 wheel 的具体成员，不重读全部第三方项目；不修改 `references/`、旧项目或原始记录。旧文档中“模型未选/下载未授权”等历史描述以最新交付为准，本批只更新当前入口及本批影响的配置，不做全库措辞清理。

## 4. 授权边界及 Gate 调整

本任务书在用户交给执行模型并要求执行后，允许：

- 在新项目中编写准备层自有代码、合成 fixtures 与离线测试；使用已有依赖，不安装新包。
- 只读核对已登记任务记录、wheel、必要的本地源码/包元数据。
- 有界的本机只读预检；实际结果只写本项目新报告目录。
- 用假模型、假凭据验证自有输入/配置/记录边界；不导入或执行 wheel 中 mini 的代码。

**这是 G0 前有限准备例外**：只允许 P1-00 的只读能力发现及 P1-07 的离线准备层。原 P1 采集、真实 Runner 和实验仍需评审及授权。PREP-01 完成不自动通过 G0/M1/P1-00/G1。

本批禁止：

- `pip/uv install`、下载新依赖/源码/任务、连通性请求、调用模型；
- 导入/执行 mini、litellm、SWE evaluator 来“试一下”；
- 启动/拉取/构建容器，运行 benchmark/verifier、perf 测量或 CPU 压测；
- 修改 sysctl、cgroup、服务、Docker 权限、用户组、全局配置或用户凭据文件；
- 读取 `/proc/*/environ`、输出环境变量全集、完整 Docker inspect、完整用户配置/历史轨迹；
- 回写旧源、references、历史报告包；提交或推送 Git；自动开始下一批。

权限不足时记录 `permission_denied/unknown`，不提权或绕过限制。缺少依赖时仍完成无依赖部分并列出下一批安装需求，不能自行获取依赖。

## 5. 工作包 A：安全任务投影与配置准备

### A1. 固定单任务，分离三种输入

实现可测试的纯函数/准备 API，验证 catalog 身份、record SHA、instance_id 后生成三个职责分离的视图：

1. **Agent 视图**：白名单仅包含任务标识与 `problem_statement`；不把整个 record 传入模型、配置模板或通用日志。
2. **环境视图**：从已核对字段选择 repo/base_commit/version、镜像引用等必要内容；只供未来运行准备，不作为 Agent prompt。
3. **Evaluator 视图**：本批只输出记录 locator/hash 与必需字段校验结果；不在报告复制 gold patch/test_patch/eval_script/测试内容，未来 evaluator 按需独立读取。

默认新增字段不进入 Agent 视图。`patch/test_patch`、测试答案和 evaluator 专用字段用合成 canary 验证不进入 Agent 输出、日志、模板上下文。真实 record 可以只读核对；生成的真实 Agent 视图若保存，放项目 `data/` 下新派生目录并受输出保护，不发送给模型、不提交题面全文。

本批保持 `run.env_startup_command` 不设；非空配置拒绝。原始 record 的 `agent_input_authorized=false` 不可改成 true 来放行整个 record：只允许准备白名单派生输入，不授权真实 Agent 消费。

### A2. 镜像与任务加载计划

- mini 读 `image_name/docker_image`，evaluator 读 `image`。实现显式适配/一致性检查，不依赖两个默认值“恰好一样”。两个 mini 字段冲突时拒绝。
- 固定本地单条任务输入路线；若 mini CLI 不能直接消费该格式，选择后续小 wrapper 调用路线并写出接口，不重新下载完整 HF 数据集来绕过。
- 不查询远端 registry；本地镜像缺失时 digest=null、状态待拉取/核实，禁止捏造 digest。
- 离线准备可接受未固定 digest 的候选配置，但真实运行就绪检查必须识别该缺口；后续 Agent/evaluator 应绑定同一已核实不可变镜像。
- 不实现实际容器启动或 evaluator 调用，禁止把任务记录中的脚本当准备命令执行。

### A3. 模型、费用和重试策略

实现不含真实凭据的配置模板、检查函数和待核实清单：

- 复用已核实的 provider/model 元信息；本批默认不重读真实 opencode.json，配置解析与注入测试使用合成配置。
- 如精确 litellm 路由在本地已有固定版本材料可核实，则记录依据；没有材料就标 `unverified`，列入下一批受控安装/连通性检查，不扩大静态研究。
- 认证设计为未来运行时环境注入；密钥不放 `model_kwargs`、argv、序列化配置或报告。不能把宿主全部环境传给 Agent 工具容器。
- 环境注入不能被描述为已经证明第三方所有日志安全；本批验证的是自有边界，第三方实际序列化/异常路径另列动态检查。
- 未知价格采用候选策略 `ignore_errors + 独立 cost_status=unknown、amount=null + usage`，不再请用户选择价格机制。真实价格若已有可靠来源可用于核算，但不为此新增下载/搜索任务。
- 原生 `cost=0.0` 只作来源值，不能变成“免费/已核算”；usage 缺失也记未知。费用跟踪失败不应让已获得的响应/usage 在自有记录层消失。
- bundled `cost_limit=3.0` 不是用户预算。列出拟覆盖的 agent/global 费用限制、步数与时间限制；取消金额限制的具体配置若未验证，不猜测数值语义。
- 三层分别列明：任务 attempt=1、请求自动重试=0、SDK/mini 内部重试=0 的实现位置。已知 mini 默认最多 10 次重试，不能只在外层写 `auto_retries: 0` 就声称禁用成功；无法离线确认的列为运行前检查项。

## 6. 工作包 B：只读能力预检

实现一个可重复的有限探测入口；默认只读、无网络、无任意命令执行接口。每个外部查询有短超时（建议不超过 5 秒），整体预检建议不超过 30 秒，单项失败不阻断其他安全检查。

最低覆盖：

| 类别 | 本批可做 | 不可据此宣称 |
| --- | --- | --- |
| Python/依赖 | 当前解释器版本、包元数据、可执行文件位置；不导入模型 SDK | 已安装元数据等于调用链可运行 |
| CPU/内存/磁盘 | 必要本机容量、核数、项目输出盘剩余空间 | 已测 workload 或已支持所有 PMU |
| cgroup | 自身 membership、mount/controller、当前可读计数器文件与权限 | 只读权限等于可创建/delegate scope |
| 进程可见性 | 自身 `/proc` 身份/namespace、必要可读性 | 已完整覆盖短进程或其他容器 |
| perf | 二进制存在、可读 paranoid/PMU 元数据 | 未执行 perf 就称 PMU 可用 |
| Docker | 本地客户端存在、本地 Unix socket 状态；必要时有限只读 version/info 字段 | socket 存在等于 daemon/容器可用 |

Docker 查询必须显式限制到本机 Unix socket，不跟随可能指向远端的 DOCKER_HOST/context；若无法安全确定本地端点，跳过并报 unknown。不要输出 info 全文、代理、认证信息或其他用户容器环境；镜像仅可按目标引用做必要的本地元数据白名单查询，不枚举无关容器。

结果逐项区分 `observed/unavailable/permission_denied/not_checked`、原因与方法。cgroup/perf 不可用是降级证据，不是准备代码测试失败。不给能力报告套 `resource_trace` 或填写虚构 CPU 消耗。

## 7. 工作包 C：离线集成测试

使用依赖注入的假 transport、假时钟/响应和 probe backend；测试不得依赖旧数据、真实用户配置、Docker daemon、mini/litellm 安装或网络。合成数据标 `synthetic`，不产出 benchmark_real run。

最低测试矩阵（可合并测试，不规定数量）：

| 测试组 | 必须证明 |
| --- | --- |
| 单任务输入 | 正常白名单投影；错误 hash/instance、缺题面拒绝；新字段默认不传播 |
| 答案隔离 | canary gold/test_patch 不进入 Agent 视图、模板与输出；非空 startup command 拒绝 |
| 凭据保护 | 假密钥不进入 argv/配置/日志/报告；正常、异常和响应回显路径都检查；不用真实密钥做扫描 |
| 模型准备 | 合成端点/模型映射可检查；未知路由保留未验证，不靠 fake 成功宣称真实兼容 |
| 费用与请求记录 | 有 usage/缺 usage、价格未知、价格计算异常；amount=null 不变 0；假失败不自动重试 |
| 镜像适配 | 两套字段显式对应、冲突拒绝、缺 digest 保持运行未就绪 |
| 预检降级 | 缺二进制、permission denied、超时、远端 Docker context 均有界处理 |
| 输出与命令安全 | 旧源/参考/输入重叠及软链接逃逸拒绝；已有报告不静默覆盖；假 tool command 仅记录、不执行 |

要测试准备代码的实际输出路径，不只测试独立脱敏工具。为假 transport 至少记录 request_id、成功/错误、usage、可用时间；不在本批建完整语义采集平台。

自有集成 PASS 与第三方动态未验证必须分列。本批没有执行 mini，不能称“mini 凭据落盘验证已通过”。

## 8. 交付物与实现范围

建议最小布局，允许按现有代码合理合并，禁止为了目录齐全搭空架子：

- `src/agent_workload_characterization/runners/preparation.py`：投影/配置/准备结果；
- `src/agent_workload_characterization/collectors/preflight.py`：有限只读探测；
- 对应 tests（可 1～2 个文件）及合成 fixtures；
- CLI 新增准备入口（建议 `prepare-pilot`，实际命名交付时列明）；默认不写文件，显式 `--output-dir` 才写新报告包，不提供 `--execute`；
- `reports/preparation/<独立批次>/`：`preflight.json`、脱敏 `plan.json`、`offline_checks.json`、`summary.md`、`manifest.json`；
- `docs/first_run_approval.md`：面向用户的一份运行审批清单；
- `docs/first_run_preparation_delivery.md`：本批完成项、命令、证据、限制、关键未决项；
- 少量同步 README、development_tasks、pilot.yaml/spec 当前状态；不批量重写历史交付文档。

不要求新增数据库、数据框架、完整 Runner、资源采集器、SWE 轨迹 adapter 或全新 IR 版本。API/模块布局可调整，但上述行为和授权边界不变。

报告身份绑定本批非敏感配置、代码版本/工作树变更情况、任务 record/wheel hash 与实际输入；manifest 覆盖报告文件（不自哈希），不哈希用户含密钥配置。复用现有路径保护，新增报告不可覆盖历史包。

`plan.json` 至少分开：`preparation_status`、`runtime_compatibility`、`execution_authorized=false`、未验证项、下一步所需授权。可用 `READY_FOR_REVIEW` 表示准备包可审，不用单一 PASS 冒充可以运行。

## 9. 下一次运行审批清单必须具体到什么

只生成清单，**本批一项也不执行**。至少分成：

1. **环境准备**：需要安装的包/版本、独立环境位置、预计下载/磁盘范围、目标镜像及 digest 确认方式；已有项目依赖不无故升级。
2. **模型连通性 smoke**：独立审批，建议最多 1 请求、无私有任务内容、无执行工具、有限输出和超时、0 自动重试；成功也不自动进入 benchmark。
3. **真实任务**：仅 django__django-16485、mini 2.4.6、DeepSeek-V4-Flash、1 attempt；确切命令与输入/输出路径，Agent/evaluator 镜像、输入隔离、基础资源记录方案。

沿用待审批提案：Agent 25 分钟 + verifier 5 分钟，总执行硬上限 30 分钟；setup 独立 15 分钟；4 CPU/8 GiB/5 GiB 新产物；用户无金额上限。说明安装/拉取的下载与磁盘开销是否另计，不把 5 GiB 产物上限误当已经覆盖镜像存储。

列明超时/取消、残留资源处理、只清理本次资源、失败保留、candidate patch 与验证结果归档。未知的命令参数可以明确留待安装后核实，但此时必须标“尚不可直接批准执行”，不得填一个貌似可运行的猜测命令。

基础采集以可行的 run/container scope 为底线，单独列 Agent runtime 与 evaluator 边界；尚无采集实现就安排下一批与 Runner 一起补齐，不伪称本批已有 Tool CPU 归因。

## 10. 验证、验收与停止规则

实施后实际运行现有完整 unittest + 新增离线测试；至少一次在项目外 cwd 用绝对 PYTHONPATH/tests 路径验证测试不依赖 cwd。真实任务记录检查和主机预检独立于默认 unittest，并清楚标示依赖。

```bash
# 已有入口；新命令只在实现并核实 --help 后使用
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
git diff --check
```

未改 adapter/macro 时不必重复生成全部真实小样报告；若改共享输出保护/公共模型/CLI 分发导致旧路径可能受影响，运行相关既有回归，保留历史报告包。

一次集中验收，问题按以下等级处理：

- **本批阻塞**：越权执行、泄漏凭据/参考答案、写坏输入/历史数据、自有输出直接错误、合成结果冒充真实验证、关键测试未覆盖实际路径。
- **下一次运行前解决**：缺依赖、网关兼容性、镜像 digest、第三方日志/重试行为。明确列入审批前置条件即可，不阻塞离线准备包交付。
- **非阻塞待办**：历史文档措辞、将来场景/并发/完整归因、非当前路径增强。不为这些另开返修轮。

交付必须回答：完成了什么、哪些测试实际执行、哪些接口仅 fake 验证、主机有什么限制、还需哪些授权。完成后停止。不得自行把 P0-07/G0/M1 或全部 P1-00 标 DONE，也不得自动安装、联网或运行任务。
