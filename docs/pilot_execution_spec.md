# 试点执行规格（P0-07 设计交付，未执行）

任务数据更新：已按用户明确授权获取固定 revision 的目标 instance，并完成必需字段/类型与 parser/enum 静态核对，见 [任务数据交付](pilot_taskdata_delivery.md)。该交付取代下文“任务数据缺失/未授权获取”的历史描述；镜像 digest、环境执行和 harness 配置仍未验证，运行未授权。

状态：**设计文档，未执行任何试点运行**。本文件把首选资源试点从"候选名称"推进到可评审的
task/asset/harness/model/verifier 配置；所有"未执行、待 P1 实现与授权"的标记必须保留。

证据索引：[pilot_evidence.json](../reports/quality/pilot_evidence.json)（每条事实的 locator、SHA-256、结论类型）。

## 最新用户决策（优先于下文历史候选与待决问题）

- 按 benchmark 选择有文档依据的 harness，不统一强制使用 OpenClaw；当前 SWE-bench 优先核实 mini-SWE-agent，版本/配置尚未冻结。历史 OpenHands 轨迹仍是参考输入，不因此改写其来源。
- 模型已选 DeepSeek-V4-Flash，配置入口 `/home/lcq/.config/opencode/opencode.json`；本次仅登记位置，未读取配置或密钥。确切 provider/model ID、endpoint 与 harness 兼容性待核实，不将 OpenCode 可用等同于新 harness 可用。
- 用户暂不设金额上限，但每次运行前必须列明任务、运行方式、资源/时间限制与费用风险，取得明确确认。现有资源预算仍是提案，不能将金额不限解释为时间/资源不限或允许自动重试。
- DEC-MODEL 的模型选择、DEC-HARNESS 的选择方向已解决；余下是配置/兼容性核实。DEC-TASKDATA 的数据获取授权仍待明确，本次同意 harness 策略不视为下载授权。
- P0-07 PARTIAL、G0/M1 未通过；不自动安装、下载、运行或启动 P1 预检。下文 Sonnet/OpenHands 等为历史候选，不再作为当前首选决定。

## 1. 首选：Coding — SWE-bench Verified `django__django-16485`

### 1.1 Task 身份（部分静态确认，数据集记录待补且不保证即取即用）

| 项 | 值 | 证据 | 状态 |
| --- | --- | --- | --- |
| instance_id | `django__django-16485` | EV-SWE-TRAJ-001 文件名；EV-TRACEBENCH-001 manifest 行 | 静态确认 |
| benchmark/subset | SWE-bench / **Verified** | EV-SWE-PACKAGE-001（verified→`SWE-bench/SWE-bench_Verified`）；trajectory 位于 `swebench_experiments/verified/` 目录 | 静态确认 |
| PR 描述 | `floatformat() crashes on "0.00"`（Django template defaultfilters） | EV-SWE-TRAJ-001 user 消息正文 | 静态确认 |
| workspace | `/workspace/django__django__5.0` | EV-SWE-TRAJ-001 user 消息 | 静态确认 |
| base_commit | **null** | — | 缺口 GAP-TASKDATA-001 |
| test_patch / gold patch / FAIL_TO_PASS / PASS_TO_PASS / eval_script / image / log_parser / eval_type / repo / version | **null** | — | 缺口 GAP-TASKDATA-001 + GAP-VERIFIERSPEC-001 |

**数据获取 ≠ 输入齐备（GAP-VERIFIERSPEC-001）**：`make_test_spec`（swebench/harness/utils.py:251，
commit 02e7a74）要求 instance 提供 `image, eval_script, log_parser, eval_type, FAIL_TO_PASS,
PASS_TO_PASS, repo, version` 全部字段。目标 `SWE-bench/SWE-bench_Verified` 的具体数据版本是否
以可直接加载的形式提供上述全部字段**未核实**；若字段缺失或形状不同，需要额外的转换/构建链
（task repo 树检出或适配层），属明确的工作项而非自动成立。因此 DEC-TASKDATA 的授权范围必须
包含"按 make_test_spec 要求做字段级核对"，并允许"需要转换"作为结论。通用 verifier 判定逻辑
（EV-SWE-GRADING-001）已确认，**不等于该 instance 的验证规格已确定**。

### 1.2 历史 trajectory（已有，只读）

- 位置：`agent_benchmark_traces/swebench_experiments/verified/20241029_OpenHands-CodeAct-2.1-sonnet-20241022/trajs/django__django-16485.json`
- SHA-256：`506a50910ba71c178cd5fd473b6821985426cb3cc7b20eb438c84706d80ab11a`
- Agent/harness：OpenHands CodeAct 2.1（历史提交框架，本地无 OpenHands 源码 → GAP-HARNESS-001）
- 模型（历史）：claude-3-5-sonnet-20241022；500 条同批提交（EV-DATASETS-001）
- 行为：30 消息；14 assistant turns；14 tool results；`execute_bash`×7（ls / python reproduce.py / grep）、`str_replace_editor`×7；最终 reproduce.py 通过（历史结果，非本轮验证）
- TraceBench 交叉确认：同 instance 由 OpenHands/GPT-5 solved=true（EV-TRACEBENCH-001，仅身份佐证）

### 1.3 Agent harness（已选 mini-SWE-agent；2.4.6 已获取并静态阅读；未安装）

用户已按 benchmark 选定 **mini-SWE-agent**。2.4.6 wheel 已按授权获取并完成哈希校验与静态阅读
（[mini_2_4_6_static_delivery.md](mini_2_4_6_static_delivery.md)、
[mini_2_4_6_artifact.yaml](../data/catalog/mini_2_4_6_artifact.yaml)）——**未安装、未运行**。

- 入口链与配置层叠已确认（F-CALLCHAIN-001）：`--subset verified` → HF
  `princeton-nlp/SWE-Bench_Verified`（与 evaluator 侧 id 不同，OI-DATASET-NS-001）
- bundled 默认：step_limit=250、cost_limit=3.0 USD、/testbed、docker、60s/command（F-BUNDLED-CONFIG-001）
- 动作协议：**结构化 bash tool call**（与 1.17.3 文本协议不同，F-ACTION-PROTOCOL-001）
- 成本：未知模型默认 **RuntimeError**；`ignore_errors` 为**静默 0.0（无日志、限额失效）**，
  须独立"成本未知"标记；registry 注册真实价格则限额有效（F-COST-001 / OI-PRICE-001）
- **凭据落盘阻塞项**：model_kwargs 含密钥必入轨迹（F-TRAJECTORY-PRIVACY-001）——须走 env-var 认证
- Agent 输入（配置条件性）：默认仅 problem_statement；可选 env_startup_command 会以整个 instance
  渲染（含参考答案字段）——试点必须不设该项。执行环境：mini 读 image_name/docker_image（皆无则
  推导 `:latest` 名），不读 evaluator 的 image 字段——字段级一致性 + digest 固定须首次运行前核实
  （F-ENVIRONMENT-001 / OI-DATASET-NS-001）

### 1.4 模型（已选 DeepSeek-V4-Flash；精确映射未冻结）

用户已选 **DeepSeek-V4-Flash**，配置位于 opencode.json 的 `火山AI网关` provider。
脱敏核实（EV-HM-OPENCODE-001，白名单投影）：

| 项 | 值 |
| --- | --- |
| 配置键 / 显示名 | `deepseek-v4-flash` / `DeepSeek-V4-Flash`（唯一匹配，无歧义） |
| 协议类别 | OpenAI-compatible（npm `@ai-sdk/openai-compatible`；不保证全参数兼容） |
| baseURL | 存在，https，路径含 `/v1`（端点不发布） |
| 认证 | 内联 apiKey 字段（路径 `provider.<key>.options.apiKey`；**密钥值未提取、未输出、未持久化**） |
| 声明限制 | maxInputTokens=256000 / maxOutputTokens=8192 |

**未冻结原因（缩小至 litellm 侧，OI-LITELLM-DEEPSEEK-001）**：mini 2.4.6 传递机制已确认
（model_name + model_kwargs 逐字直通 litellm，不加前缀，F-MODEL-ROUTING-001）。剩余未知全部
在 litellm 下游：网关的 provider 前缀写法、base_url 键名与 `/v1` 追加行为、auth 环境变量名。
**"OpenCode 能用"不构成 harness 能用的证据。**
成本：价格未核实。swebench `run_api.py` 的 `calc_cost` 对价格字典**直接索引**——未知模型触发
**KeyError（fail loudly）**，源码注释明确为避免静默低估（EV-HM-RUNAPI-COST-001）；该文件不证明
mini 2.4.6 的实际计费路径（litellm 侧待源码核实）。历史轨迹 instance_cost=0.0 仅示记录值为零，
原因不能据此断定。待核实：该模型费用如何记录、未知价格如何处理（GAP-COST-001）。
用户已明确**暂不设金额上限**；已定要求是**每次运行前说明具体任务并取得明确确认**。

### 1.5 Verifier（静态链条已核实）

链条：dataset instance（含 FAIL_TO_PASS/PASS_TO_PASS/eval_script/log_parser/image）
→ `make_test_spec`（EV-SWE-DATASET-001）
→ `run_evaluation.run_instance`：起容器 → `git apply` candidate patch → 跑 eval_script（EV-SWE-RUNEVAL-001）
→ `get_eval_report`（EV-SWE-GRADING-001）：解析日志 → F2P=1 且 P2P=1 → `resolved=true`。

- candidate patch（模型输出）与 gold/reference patch 区分：evaluator 只应用 candidate patch；
  gold patch 仅在数据集记录中作对照，**不进入 Agent 输入**（trajectory 的 user 消息只含 PR 描述，
  EV-SWE-TRAJ-001 已确认无测试逻辑泄露之外的解答）。
- 基础设施失败与任务失败区分：`infra_failure` 字段 + `classify_logs` 按 tier 分类（EV-SWE-GRADING-001）；
  `SUITE_RAN` 正则防止"未运行的套件判为通过"。
- "静态判定逻辑已核实" ≠ "在本机复现验证器通过"；后者属后续 Runner/评估验证。
- **缺口**：本 instance 的 F2P/P2P 具体测试名与 eval_script 内容在数据集记录中（GAP-TASKDATA-001）。

### 1.6 资源边界（已见机制 vs 待验证假设）

已见机制（静态）：execute_bash 命令为 shell 命令（ls/python/grep）；str_replace_editor 为
OpenHands runtime 内置工具。容器内执行（run_evaluation 起独立容器）。

待 P1 验证假设（**不可现在断言**）：
- OpenHands 的 execute_bash 是否每次调用派生独立短命子进程，还是经常驻 action-executor server
  转发（影响 per-tool 独占归因可行性）；
- str_replace_editor 是否进程内编辑（无独立子进程）；
- 容器 cgroup 边界与宿主观测关系。

底线方案：run/service/scope 级测量兜底；per-tool 独占归因仅作待验证目标，不作为 G1 前提。

## 2. 备选：Office — DocOps `word_001`

### 2.1 Task 身份（本地静态确认）

- 任务：`agent_benchmark_traces/docops/tasks/atomic__word_001_engineering_report_toc_hierarchy_seed/`
  （task.toml SHA `541e0d24...`，EV-DOCOPS-TASK-001）
- doc_type=word；verifier_mode=semantic-strict；artifact 级确定性验证
- 任务树 commit：`ccf7a751bc5c8a69c1cdd0400125d53455b33be3`（EV-DOCOPS-REPO-001；211 任务目录）
- 资源限制（task.toml）：cpus=1、memory_mb=4096、storage_mb=10240、gpus=0、allow_internet=true；
  verifier 600s / agent 1200s / build 900s

### 2.2 Verifier（静态确认）

- `tests/test.sh` → `pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py`（EV-DOCOPS-VERIFIER-001/002）
- 输入 docx + 提交 docx 对比；Dockerfile 存在（EV-DOCOPS-ENV-001），digest 未构建（GAP-DOCKER-001）

### 2.3 历史（参考，非冻结配置）

- 本地无 word_001 历史运行（trace_word 批次为 003~012；word_002 在清理归档，EV-DOCOPS-HISTORY-001）
- 历史批用 codex agent + Harbor + 代理（surrogate 模型），**不作为本试点冻结 harness**

## 3. 预算（待批准，非测量结果）

| 项 | 值 |
| --- | --- |
| 任务数 | 1 task、1 attempt |
| Agent 执行时长 | 25 分钟硬上限（wall） |
| Verifier 时长 | 预留 5 分钟，计入总预算（见下） |
| 总预算 | **30 分钟硬上限（Agent 25 + Verifier 5，不重叠计）** |
| CPU | 4 |
| 内存 | 8 GiB |
| 新产物 | 5 GiB |
| 自动重试 | 0 |

**停止规则（消除冲突）**：
- 30 分钟为**总硬上限**：Agent 段到 25 分钟即停（kill/终止），进入 verifier 段；
  verifier 段最多再用 5 分钟。**任何一段都不得越过总上限继续运行**——verifier 超出自己的
  5 分钟配额即中止并记为 `verifier_timeout`（样本仍保留为失败样本，判定字段为
  evaluation 未完成而非任务失败）。
- Agent timeout/失败后**仍运行 verifier** 的前提是总预算尚有余量；若 Agent 段已耗尽
  25 分钟，verifier 只使用剩余的 5 分钟。
- 时长分段：build/setup（镜像构建）**不计入** 30 分钟执行预算，单独记录并设独立上限
  （建议 15 分钟，待批准）；Agent 与 verifier 分别计时。
- 残留产物处理方案属 P1（本轮不创建、不清理资源）。
- DocOps 任务自身限制（1 CPU/4 GiB/verifier 600s/agent 1200s）低于本预算上限；
  该任务声明同时含 build 900s——若选 DocOps，以其任务声明为更紧约束。

## 4. 用户待决事项（已定项不再询问；余下为有限授权请求）

已定（不再询问）：模型=DeepSeek-V4-Flash；harness=mini-SWE-agent；按 benchmark 选择策略。

仍需授权（明确、有限）：
1. **mini-SWE-agent 2.4.6 wheel 获取**（DEC-MINISRC，**待授权、未授予**；用户已确认的是
   版本锁定决定——2.4.6、115,037 bytes——不是下载授权）：从 PyPI 获取锁内 wheel，校验哈希
   （uv.lock: `a35463c5...cd54`）后**仅静态阅读**——核对 bundled `benchmarks/swebench.yaml`
   配置 schema 与模型适配器字段；**不安装、不运行**。不获取 1.17.3，不做连通性测试。
2. 沿袭：evaluator 镜像 digest 核实（P1-00 范围）；Agent 输入投影生成器（P1 实现项）。

**授权获取不等于缺口已解决，也不等于允许运行 benchmark。**

## 5. 非目标

- 本任务不运行 benchmark/容器/API/验证器；不安装依赖；不做 P1-00 预检。
- 不把本文件当作执行授权；`execution_authorized=false`。
- 不扩展四场景候选为正式代表性集合。

## 6. 未来实施依赖（P1 序列，供评审参考）

P1-00 只读能力预检（Docker daemon、cgroup v2、PMU 权限）→ P1-01~05 采集器 → P1-07 Coding Runner
（含 harness 适配）→ 首次真实运行（本规格 §1/§3 预算）→ G1 评审。
