# G0 评审证据（最小语义 Gate）

状态：**PASSED（2026-09-12T12:39Z 正式决议；C 执行等待用户磁盘风险确认）**。

任务记录、mini 安装与离线适配、SMOKE-01R、arm64 digest、canary r7 和隔离 gold-patch verifier 已完成；C 真实 Agent attempt 尚未执行。最终范围、降级与命令登记以 [RUN-01 任务书第 8 节](../../docs/coding_pilot_handoff.md#8-c-审批清单一次真实-agent-任务) 为准（已冻结，唯一有效版本）。

历史过程见 [宏观交付](../../docs/p0_07_08_09_delivery.md) 与 [RUN-01 交付](../../docs/coding_pilot_delivery.md)。以下第 1～4 项是既有已验收语义证据；第 5 项为本次试点环境与配置证据。

## G0 五条逐项证据

### 1. P0-00 审计与复用边界清楚，旧数据只读策略可检查

- 审计报告：`docs/legacy_asset_audit.md`（P0-00-r2 已验收）
- 复用决策：`data/catalog/code_components.yaml`
- 旧数据只读：三个小样 checker + analyze CLI 均有输入前后 stat 核对与路径 containment；
  输出 guard 拒绝旧源/references/输入重叠（测试覆盖：test_adapters / test_videoweaver）
- 早期 `pilot_evidence.json` 是静态核实；后续分别授权的 smoke/容器/evaluator 验证有各自报告，不沿用其“无执行”标签。原始数据与 references 保持只读。

### 2. 最小 Schema 覆盖三种输入

- AgentX 小样（AX-7/AX-SUB）→ IR 0.2.0 semantic_trace（P0-04 已验收）
- Applied Compute 模板（AC-N2）→ IR 0.2.0 macro_template（P0-05 已验收）
- VideoWeaver 本地 trace（VW-LONG + AUX-INCOMPLETE unassigned）→ IR 0.2.0（P0-10 已验收）
- Schema 0.2.0 + 显式 v0.1 迁移 API；v1～v5 历史报告为 superseded，当前依据 v6

### 3. 手算 fixtures 验证身份、N+1、context、时间/并发、缺失和聚合范围

- 默认合成测试（不依赖旧数据，隔离 cwd 全量 175 项通过）覆盖：P50/min/max/mean、
  interval_totals（union/work/overlap/nested/triple/open/cross-clock/receipt 拒绝）、
  coverage 恒等式、模板/实测不混、分层不混、gold 必需字段缺失 FAIL、sidecar 空/错键/数值差异 FAIL、
  macro/coverage 键对齐断言
- 显式真实回归（三个 check 命令 + 只读 analyze-macro-pilot）分开运行并 PASS：
  AX 7/194368/4097、21/818752/3949；AC-N2 3/32499/1986/13644/2.770s；
  VW-LONG 70/4041546/28631/79937(input)/80378(source ctx)/88 tools/1616.424s
- 两者分开声明，不互相冒充

### 4. 最小宏观与 coverage 同时输出；已知误导性指标被修正或停用

- 当前依据：`reports/macro/macro-pilot-v6/`（analysis_id pilot-b3fd75863e80；
  manifest 含 gold_sha256 + sidecar SHA-256 + 全部输入文件哈希；quality_checks issues=[]）
- macro/coverage 共用 row_key；90/90 macro 行有唯一 coverage 匹配且 n_valid 一致
- run_elapsed/local_cpu_time/tool_cpu_time：真实 run 适用但缺失（显式），模板 not_applicable；
  max_input_context(79937) 与 max_source_context_tokens(80378) 分列；模板与实测分 stratum
- 旧误导指标（representative 混源排序等）未进入新链路
- 不代表正式总体分布（样本=3 run+1 模板+1 unassigned）

### 5. 首个资源试点的任务、配置、可测边界和预算确定

- 固定任务：SWE-bench Verified `django__django-16485`；[任务记录登记](../../data/catalog/pilot_task_record.yaml)，SHA `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`，base commit `39f83765e12b0e5d260b7939fc3fe281d879b279`。原始记录只读，答案不进入 Agent。
- harness：mini-SWE-agent 2.4.6 已安装；真实 mini + fake transport/执行器离线贯通 3 项已验收，默认测试 378 项、evaluator 解析链 5 项已验收。不是实际 Agent attempt。
- 模型/认证：[SMOKE-01R 交付](../../docs/model_smoke_delivery.md) 已验证 `openai/deepseek-v4-flash` 工具协议与 usage；引用凭据内存解析，传递走环境变量。有限已测序列化路径通过，不声称任意第三方日志绝不泄漏。
- 镜像：原生 arm64，`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`；record 的 x86_64 字段保留，配置层显式映射，不自动使用 qemu fallback。
- 资源：[r7](../resource/RUN-01-B-canary-r7/canary.json) 双 workload 成功；[停止链](../resource/RUN-01-B-canary-r7-stopchain/stop_chain.json) 与 r7 覆盖存活容器确认、docker-stop 兜底。cgroup v1 CPU/memory 基础 scope 可测；I/O 降级，不证明完整 G1 或独占 Tool CPU。
- evaluator：[隔离 gold 验证](../resource/RUN-01-B-goldverify/RUN01BGOLD-20260912T104224Z-617538/goldverify.json) 实际执行 apply→eval→parse，10/10 测试、resolved=true；固定版本 `02e7a74`。该证据仅支持所测任务/镜像/gold patch，不作为真实 Agent 样本。
- 预算方案：一次 attempt，30 请求/30 step、每请求 4096 输出 tokens、Agent 25 min + verifier 剩余最多 5 min、总执行 30 min、两个容器各 4 CPU/8 GiB；5 GiB 为 run_dir 超限检测阈值，非磁盘硬配额；费用未知。**尚待 C 明确批准。** 不重新授权已完成的 setup/build。

## 缺口更新、限制与最终审批项

| 原项目/事项 | 2026-09-12 状态与边界 |
| --- | --- |
| GAP-TASKDATA-001 | 已解决：固定本地记录及字段核对完成 |
| GAP-HARNESS-001 / GAP-MINI-SRC-001 | 本试点准备范围已解决：安装版、静态来源与离线真实 mini 编排已验证 |
| GAP-MODEL-ADAPTER-001 / OI-LITELLM-DEEPSEEK-001 | 成功 smoke 已验证该路由/auth/协议；C 使用同配置，变化需重新核对，不默认当前凭据永远有效 |
| GAP-VERIFIERSPEC-001 / 镜像适配 | 该固定实例的 arm64 gold 验证已通过；任意 candidate 的结果由 C 实际评估决定 |
| GAP-DOCKER-001 | 本试点基础容器/计数器/停止链已测；不等于完整 P1-00 或 PMU 可用 |
| GAP-COST-001 / OI-PRICE-001 | 采用成本未知口径，usage 单列，原生零不当免费；价格仍未知，用户未设金额上限，不再申请价格上限作为准备前置 |
| 磁盘降级 | `--storage-opt` 本机不支持；run_dir 检测不覆盖容器可写层，容器删除仅事后回收；用户须看到可用空间与风险后批准 |
| 离网安装失败 | gold 验证中 pip editable 安装失败，但日志确认导入工作树且 10/10 通过；保留限制，不自动开网补依赖 |
| C 最终入口与命令 | **已登记并冻结（2026-09-12 第二轮收紧后）**：入口 `src/agent_workload_characterization/runners/c_entry.py`（SHA-256 前缀 `65f4d62faa02c0db`）；解释器 `.venvs/swebench-eval-02e7a74/bin/python`；计划/执行双命令与配置/代码身份见 [任务书 §8.2](../../docs/coding_pilot_handoff.md)（唯一有效版本，含登记字段表）。默认仅离线计划；执行需用户键入双旗标 `--execute --i-approve-the-c-run` 且凭据环境齐备（缺失在任何容器前拒绝）；**catalog SHA-256 `aee38eaca781df01...902f83` 由入口硬编码绑定——预算篡改/NaN/任意漂移在计划与执行两种模式均拒绝组装**（含评审复现的 30→300 与 NaN 场景，离线回归覆盖）；catalog `execution_authorized: true` 被拒（配置不能授权）；双旗标仅为软件门禁、不证明输入者身份（任务书 §8.2/§8.5 已声明）。入口测试 12 项（全合成 fixtures，不依赖本地真实 record/catalog/venv）+ 全量 390 项通过。**C 未执行**。 |

## 正式决议记录（2026-09-12）

- **决议**：`G0_decision: PASSED`——五条最小语义证据逐项核对如下，均满足 G0 定义（语义 Gate，非资源归因闭环；P1-00 全项/PMU/完整 G1 不在本决议范围）。
- **评审人**：用户（RUN-01 交付评审人，2026-09-12 消息授权记录正式决议："我认可上述单次运行预算及观测限制。请先完成 G0 正式决议，并展示输出盘与 Docker 数据盘的实际可用空间；在我确认磁盘风险后，按已冻结清单执行 C，一次即停。不得自动重试、扩大预算、换任务或修改环境。"）。
- **决议时间**：2026-09-12T12:39Z。
- **所依据身份**：git HEAD `b4437fb8c7563ccfb384a422c23994e43c9ac957` + 未提交 RUN-01 变更；入口 `runners/c_entry.py` SHA-256 前缀 `65f4d62faa02c0db`；catalog `workload_catalog/coding_pilot.yaml` SHA-256 `aee38eaca781df014117c4af14ce6df4fce91e2808dde09b03271b1e94902f83`（入口 pin 同值，冻结）；record SHA-256 `762de270d1ce06ab...ec46a`；镜像 `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c2...7b7d2`；默认测试 390 项 + 集成 8 项（真实 mini 3 + swebench 5）通过。
- **五条结论**：(1) P0-00 审计与只读策略可检查 ✓；(2) 三种输入（AgentX/Applied/VideoWeaver 小样）经 IR 0.2.0 覆盖 ✓；(3) 手算 fixtures（身份/N+1/context/时间并发/缺失/聚合范围）175 项隔离测试 + 三条真实小样回归 ✓；(4) macro/coverage 同时输出且误导指标停用（macro-pilot-v6）✓；(5) 首个资源试点任务/配置/可测边界/预算确定且用户认可 ✓。
- **限制（随决议携带）**：C 的资源观测为 run/container scope 基础集（无 per-tool 独占、无宿主 mini 子进程逐进程采集、I/O 降级、无容器可写层配额）；单任务单 attempt 不构成生产代表性样本；G1/M1 不因本决议自动通过。
- **C 执行授权状态**：预算与观测限制**已认可**（用户原文见上）；磁盘风险**已确认**（输出盘 2.9T / Docker 盘 399G 可用展示后用户确认）；`C_command_frozen=true`。
- **C 执行记录**：`C_executed=true`——2026-09-12T12:52:02Z–12:54:29Z 按冻结清单执行一次（run_id `20260912T125202Z-840e49`，147 s，预算内）：execution/evaluation/archive = ok/ok/ok，**resolved=true**（官方 verifier patch_applied=True、infra_failure=False）；30/30 请求（26 正常 + 4 格式错误，全部计入）、26 steps、10,777 输出 tokens、单请求最大 1,981；agent_container 6.412 core-s / verifier_container 3.423 core-s（native arm64 边界计数）；agent exit=LimitsExceeded 未提交、candidate 经工作树提取路径捕获（26 tool calls/26 tool 消息自轨迹提取）；产物计账经 v2 对账修正（实际 520,090 B = runner 归档 293,859 + 范围外 226,231，见补充完整性清单）；0 残留容器。派生报告三组收尾（tools/退出状态、I/O 正式 null、归档对账）见交付 §5.19，封存数据零改动。**单样本无代表性；G1 不因此自动通过。交付后停止。**
- **catalog 说明**：`workload_catalog/coding_pilot.yaml` 的 `gates` 字段为冻结时快照（哈希绑定不可改）；授权状态以本节为唯一权威记录。

正式决议须记录评审人、UTC 时间、所依据的代码/配置身份及限制；执行授权另记用户原文。只有 Gate 决议、实际命令冻结及用户 C 授权均满足才执行一次。C 无论成功失败均交付后停止。
