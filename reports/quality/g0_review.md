# G0 评审证据（最小语义 Gate）

最新数据证据：目标 instance 已按用户授权获取，见 [任务数据交付](../../docs/pilot_taskdata_delivery.md) 与 `data/catalog/pilot_task_record.yaml`。GAP-TASKDATA-001 的本地记录缺失已解决，GAP-VERIFIERSPEC-001 已完成必需字段/类型、parser/enum 的静态核对；镜像 digest/运行级兼容性仍未验证。此更新取代下文相关历史缺失描述，不自动通过 G0。

状态：**READY_FOR_REVIEW（P0-07 设计证据已补齐至静态极限；G0/M1 由用户/评审确认，执行模型不自行宣布通过）**
更新日期：2026-09-10（P0-07 收尾轮）。本文件取代此前 REVISED_FOR_REVIEW 版本中的返修描述；
历史返修过程见 [p0_07_08_09_delivery.md](../../docs/p0_07_08_09_delivery.md)（其早期错误输出已标 superseded）。

## G0 五条逐项证据

### 1. P0-00 审计与复用边界清楚，旧数据只读策略可检查

- 审计报告：`docs/legacy_asset_audit.md`（P0-00-r2 已验收）
- 复用决策：`data/catalog/code_components.yaml`
- 旧数据只读：三个小样 checker + analyze CLI 均有输入前后 stat 核对与路径 containment；
  输出 guard 拒绝旧源/references/输入重叠（测试覆盖：test_adapters / test_videoweaver）
- 文档规则 vs 已有测试区分：本轮 pilot 核实全部为只读（rg/读取/git rev-parse/sha256sum），
  未运行任何 benchmark/容器/API（见 pilot_evidence.json verification_mode）

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

- 首选：SWE-bench Verified `django__django-16485`；官方任务记录已获取并字段级核对
  （[pilot_taskdata_delivery.md](../../docs/pilot_taskdata_delivery.md)，
  [pilot_task_record.yaml](../../data/catalog/pilot_task_record.yaml)）
- harness：用户已选 mini-SWE-agent；**2.4.6 wheel 已授权获取、哈希校验并静态阅读完成**
  （[mini_2_4_6_static_evidence.json](mini_2_4_6_static_evidence.json)，15 成员哈希登记）；
  未安装、未运行。配置 schema/成本/动作协议/轨迹结构已源码确认；剩余 OI-LITELLM-DEEPSEEK-001
  （litellm 路由）、OI-PRICE-001（价格二选一：registry 限额有效 / ignore_errors 静默 0.0 须独立
  标记）、镜像字段适配与 digest 一致性（OI-DATASET-NS-001）、env_startup_command 输入隔离
  （须保持不设）、凭据落盘验证（env-var 路线）
- 模型：用户已选 DeepSeek-V4-Flash（opencode.json 脱敏核实，唯一匹配）；
  精确请求映射未验证（GAP-MODEL-ADAPTER-001）；成本须独立记账（GAP-COST-001）
- verifier 链静态核实（EV-SWE-GRADING-001 等）；镜像 `:latest` 未固定 digest
- 预算：Agent 25 + Verifier 5（总 30 min 硬上限）+ build/setup 独立 15 min，均待批准；
  每次运行前需用户明确确认
- 详见 [pilot_execution_spec.md](../../docs/pilot_execution_spec.md)、
  [pilot_harness_model_compatibility.md](../../docs/pilot_harness_model_compatibility.md)、
  [pilot_harness_model_evidence.json](pilot_harness_model_evidence.json)

## 缺口（不因"待授权"一词掩盖）

- GAP-TASKDATA-001：**已解决**（官方记录获取+字段核对完成，见 pilot_taskdata_delivery）
- GAP-VERIFIERSPEC-001：必需字段/类型/parser/enum 静态兼容已核对；**镜像 digest 与运行级兼容未定**
- GAP-HARNESS-001：**已解决**（2.4.6 获取+静态阅读完成）；新阻塞项为 OI-LITELLM-DEEPSEEK-001 /
  OI-PRICE-001 / 凭据落盘验证（见 mini_2_4_6_static_delivery.md）
- GAP-MODEL-001（缩小）：模型已选 DeepSeek-V4-Flash；mini 侧传递机制已确认，剩余为 litellm
  下游路由未知（GAP-MODEL-ADAPTER-001 → OI-LITELLM-DEEPSEEK-001）
- GAP-COST-001：mini 2.4.6 计费已源码确认（未知价格默认 RuntimeError；ignore_errors 为静默 0.0、无日志、限额失效——须独立"成本未知"标记；OI-PRICE-001 运行前必须二选一）；用户暂不设金额上限，每次运行前确认
- GAP-DOCKER-001：Docker/镜像可执行性未检查——P1-00 范围，不阻塞 G0 设计评审

按任务书规则：配置证据充分且用户选择明确时最多标 READY_FOR_REVIEW。当前模型与 harness 的
**选择**已定，但版本冻结、精确映射与连通性仍未决（需源码获取授权 + 可选连通性测试授权）。
P0-07 状态为 **PARTIAL（设计证据完成，选择已定，版本/映射未冻结）**；G0 是否通过由评审在
DEC-MINISRC / DEC-CONNECT 解决且 GAP-MINI-SRC / GAP-MODEL-ADAPTER / GAP-COST 闭环后裁定。
