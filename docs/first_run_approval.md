# 首次真实运行审批清单（PREP-01 产出，待用户逐项批准）

当前更新：SMOKE-01R 已成功并通过验收，模型认证/工具协议/usage 小样已验证；不再重复申请同一 smoke。批准项 3 的后续具体工作以 [RUN-01 联合任务书](coding_pilot_handoff.md) 为准。其 A 离线开发、B 镜像/容器 canary、C 多轮真实 Agent 单任务严格分开；本次仅生成任务书，B/C 尚未授权。下文旧 smoke 待批及旧候选预算保留作历史，不作为新操作授权。

最新状态：**PREP-01、ENV-01 已验收，安装与离线适配已完成；真实请求仍未批准/执行。** 批准项 2 现以 [SMOKE-01 执行文档](model_smoke_handoff.md) 为准：单次工具协议请求、100 token 输出上限、30 秒查询 watchdog、零重试、工具只解析不执行。需先生成独立路由配置并通过安全启动器在内存读取指定凭据；不使用仍含 UNVERIFIED_PREFIX 的默认 pilot 配置。本更新取代下文历史“安装未批准”与旧的 smoke 消息/手工密钥注入说明；镜像与真实任务仍待后续批准。

本文件仅生成清单，**一项也未执行**。每项批准后单独实施；未批准项不自动开始。
2026-09-11 更新：PREP-01 已验收。批准项 1 现拆出 [ENV-01 独立环境安装与离线适配](environment_adaptation_handoff.md)，其路径、下载/磁盘/时间边界及停止规则以该任务书为准，尚待批准。**ENV-01 不含镜像拉取或模型请求**；下文镜像估算为历史提案，不作为本批范围或已验证大小。批准项 2 的确切 smoke 命令由 ENV-01 交付，不提前执行。

准备包依据：[PREP-01](../reports/preparation/PREP-01/manifest.json)；
静态证据：[mini 2.4.6](mini_2_4_6_static_delivery.md)、
[任务记录](pilot_taskdata_delivery.md)。

## 批准项 1：环境准备（安装与镜像）

| 项 | 内容 |
| --- | --- |
| 安装对象 | mini-swe-agent **2.4.6**（wheel 已本地校验 `a35463c5...cd54`，可直接安装该文件）+ 其依赖（litellm≥1.75.5≠1.82.7/8、openai≠1.100.0/1、pydantic、jinja2、typer、datasets 等 14 项） |
| 安装位置 | 建议独立 venv（如 `data/raw/software/mini_swe_agent/2.4.6/venv/` 或用户指定路径）；**不升级项目现有依赖**（pydantic/yaml 版本不因安装改动） |
| 下载/磁盘预估 | wheel 本体 115 KB 已在本地；依赖包合计约 200–400 MB（litellm+datasets+pydantic 等）；安装后 venv 约 500 MB–1 GB |
| 目标镜像 | `swebench/sweb.eval.x86_64.django_1776_django-16485`（Agent 与 evaluator 同名镜像、独立容器） |
| digest 确认方式 | 拉取前/后 `docker images --digests` 记录 digest；两侧（若 evaluator 另行拉取）必须一致；`:latest` tag 本身不固定——**运行前必须以 digest 记录为准** |
| 镜像存储开销 | 约 1–3 GB（单镜像），**不计入** 5 GiB 新产物上限（另计） |
| 安装后检查 | `mini-extra --help` 可运行；`MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1` 设置路径确认；litellm 版本记录 |

**此项尚不可直接批准执行的具体原因**：安装命令的具体形式（pip/uv、镜像源）与 venv 路径需用户确认；依赖解析可能引入传递依赖变更。

## 批准项 2：模型连通性 smoke（独立审批；ENV-01 已备好入口）

| 项 | 内容 |
| --- | --- |
| 目的 | 验证 DeepSeek-V4-Flash 经 litellm→火山网关的真实路由（前缀、auth、usage、mini bash tool 协议） |
| 规模 | **最多 1 次请求**；单条非任务消息（"Reply with the single word: ready"）；无工具执行；≤100 token；总 30s wall deadline |
| 重试 | 0（三层全禁：任务 attempt=1 外无自动重试；`MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1`；`num_retries=0`） |
| 凭据 | 运行时环境变量注入（`PILOT_API_BASE` 含 `/v1`；`PILOT_API_KEY`）；不打印/hash/保存；模型 config 无密钥（ENV-01 已验证） |
| 费用 | 价格未知即 unknown；记录实际 usage；不承诺极小额或免费 |
| 确切命令（ENV-01 交付，含 PYTHONPATH=src） | 见 [environment_adaptation_delivery.md](environment_adaptation_delivery.md) 末节：独立 venv 解释器 + `PYTHONPATH=src` + `-m agent_workload_characterization.runners.smoke --execute --i-approve-the-smoke`；结果脱敏写入 `reports/smoke/<run-id>.json` |
| 运行时开关 | `LITELLM_LOCAL_MODEL_COST_MAP=True` 建议保留（防止 litellm 拉远端价格表外连）；是否保留由本批准一并确认 |
| 失败处理 | 停止；不换端点/模型自动重试；成功仅记录路由事实，不进入 benchmark |

**已完成（2026-09-11）**：首次失败（{env:} 引用未解析）→ 修复后重试成功——
tool-call 回复 + usage(308/69/377) + 路由/auth/工具协议全链路验证。详见
[model_smoke_delivery.md](model_smoke_delivery.md)。批准项 3（真实任务）待新任务书。

## 批准项 3：真实任务运行（django__django-16485，单次）

| 项 | 内容 |
| --- | --- |
| 任务 | 仅 `django__django-16485`（SWE-bench Verified，revision `78f471bf...`，record SHA `762de270...`） |
| Harness / 模型 | mini-SWE-agent 2.4.6 / DeepSeek-V4-Flash；**1 attempt**，0 外层自动重试 |
| 输入 | 经白名单投影的 `problem_statement`（PREP-01 `plan.json` 的 agent_view）；`env_startup_command` 保持不设；record 本体不进 Agent |
| 命令形态 | 调用本地 wrapper（**待批准项 1 后实现**）加载校验后的 record 并进入 mini 入口；具体 argv 待安装后以 `--help` 核实填入——**当前不填貌似可运行的猜测命令** |
| 输入/输出路径 | 输入：`data/raw/public/swebench_verified/.../record.json`（只读）；输出：`reports/` 外新目录（项目 `data/raw/generated/` 下按 run 独立目录） |
| 镜像 | 同批准项 1 的镜像 + 已核实 digest；Agent 与 evaluator 使用同一 digest |
| 时间预算 | Agent 25 min + verifier 5 min = **总 30 min 硬上限**（任何分段不得越总限）；setup/build 独立 15 min |
| 资源预算 | 4 CPU / 8 GiB 内存 / 5 GiB 新产物（**不含镜像存储**）；镜像另计 1–3 GB |
| 金额 | 用户不设上限；未知价格标未知；逐调用 usage 从轨迹 response dump 独立核算（cost_status=unknown 不当免费） |
| 超时/失败处理 | Agent 停止后 verifier 仅在剩余预算内运行；超出记 `verifier_timeout`（评估未完成≠任务失败）；candidate patch 与验证结果归档；失败样本保留 |
| 残留资源 | 只清理本次创建的容器/目录（身份可确认）；不做递归清理；残留记录在案 |
| 基础采集 | 底线为 run/container scope（docker stats 或宿主侧采样——**属下一批与 Runner 一起实现，本批无 Tool CPU 归因**）；Agent runtime 与 evaluator 边界分开列 |

**此项尚不可直接批准执行的具体原因**：依赖批准项 1（安装）+ 批准项 2（路由确认）；wrapper 未实现；digest 未固定。

## 运行前检查项（不阻塞准备包，但阻塞真实运行）

- [ ] mini 2.4.6 安装且入口可用（批准项 1）
- [ ] litellm 路由前缀/base_url/auth 确认（批准项 2 或源码核实）
- [ ] 镜像 digest 拉取时记录并双侧一致
- [ ] `MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1` 实际生效验证
- [ ] 凭据仅经环境变量注入；`model_kwargs` 无 api_key/api_base（轨迹落盘防护）
- [ ] OI-PRICE-001 落地：ignore_errors + 独立 usage 核算（已选策略）或 registry 注册
- [ ] wrapper 实现 + 白名单投影接入（P1-07 下一批）
- [ ] run/container scope 采集方案确定（下一批）

## 明确不在本清单内

- P1 完整采集器/Runner 平台；CPU hotspot/perf 实验；并发/Scale；四场景扩展
- 任何对 references/旧工程/历史报告的修改
