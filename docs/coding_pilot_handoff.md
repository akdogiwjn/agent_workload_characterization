# RUN-01：SWE-bench 单任务 Runner、镜像准备与基础资源观测

初版日期：2026-09-11；最终审批清单更新：2026-09-12。

当前状态：**A 离线实现及返修已验收；B 环境、canary r7、停止链与隔离 gold-patch verifier 验证已验收；C 真实 Agent attempt 未执行、未授权。** 下一步只按第 8 节完成最终命令登记与 G0/C 审批，不重做 A/B。第 4～7 节保留原阶段要求，不代表当前待执行事项。

本次更新仅修改文档，不授予安装、镜像操作、容器启动或模型请求权限。此前“开始”“允许”的 A/B/smoke 授权不延伸到 C。

关联：P0-07/G0 收尾、P1-00 可行性、P1-01/03/04/07/13 的最小子集；不是这些任务的全项验收。

## 1. 一个明确目标

以 **SWE-bench Verified 的 django__django-16485** 为唯一真实任务，建立：

```text
固定本地任务 → 安全输入 → mini Agent → candidate patch
                                     ↓
                              独立 verifier
                                     ↓
                  语义日志 + 明确 scope 的 CPU/内存/I/O
```

服务 RQ2/RQ3：首次得到可核查的本地系统资源观测。不是能力排行，不追求必须修复成功；Agent 未解决任务但运行/评估/采集过程可解释，也是有效交付。不能用模型延迟推算 CPU。

**本批不要求逐 Tool 独占归因，不做 perf/hotspot，不增加 benchmark，不全量 ingest。** 先取得 run/container scope 数据和工具时间关联，下一批再完善 G1 归因与计量核对。

## 2. 固定输入与已验收成果

| 项 | 固定选择/依据 |
| --- | --- |
| Benchmark/task | SWE-bench Verified / `django__django-16485`（Django floatformat 问题） |
| 数据 | `data/catalog/pilot_task_record.yaml` 定位的单条本地记录；不重新下载数据集 |
| revision | `78f471bf655a3137b2e8a75af1501690ec009ec3` |
| record SHA | `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a` |
| base commit | `39f83765e12b0e5d260b7939fc3fe281d879b279` |
| Harness | mini-SWE-agent 2.4.6，已安装在 `.venvs/mini-swe-agent-2.4.6-env01` |
| 模型 | 已成功 smoke 的 `openai/deepseek-v4-flash`；API body 为 `deepseek-v4-flash`，大小写以成功批次实际配置为准 |
| 凭据 | 用户指定 OpenCode 配置；launcher 已支持 `{env:VAR}` 内存解析，不再发送引用字面量 |
| 实际目标镜像 | `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`；原生 aarch64，不自动切回 x86_64/qemu |
| Image ID | `sha256:bba60201758effbb3e4795367d470e3d0e00427f0e2e86636801b9f93df0b664` |
| Evaluator 执行副本 | `data/raw/software/swebench-eval-02e7a74`，固定 commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`；venv `.venvs/swebench-eval-02e7a74`；references 仍只读 |
| 已验收测试基线 | 默认 378 项、真实 mini 离线贯通 3 项、SWE-bench 解析链 5 项；不是 C 实测数据 |

前置阅读：完整四份必读文档（methodology、development_tasks、references/README、references/manifest），再读 trace_contract、data_management、pilot_taskdata_delivery、model_smoke_delivery、最新成功 smoke 报告及 PREP/ENV 交付。

仅核对所需 mini Agent/Docker/保存接口和 evaluator 创建容器/应用 patch/运行评估/清理接口，不重读全部参考项目。参考内容不直接当本项目已测事实。

## 3. 三个执行关口：不以“开始”代替全部授权

本次用户要求的是**生成任务书**。实施模型接到明确“执行 RUN-01 离线开发”后可执行 A；B、C 各自列清单并等待明确批准。一个关口内合并工作，不逐文件索要许可。

| 关口 | 范围 | 是否涉及模型/容器 |
| --- | --- | --- |
| A：离线开发 | 自有 Runner/recorder/sampler/analyzer、fake model/fake Docker 测试、只读本机预检、生成 B/C 审批清单 | 不请求模型、不启动容器、不安装/下载 |
| B：环境准备与无 API 验证 | 已完成固定 evaluator/镜像、canary 与停止链；后续独立批准的 gold-patch verifier 验证也已完成 | 无模型 API、无 Agent；gold-patch 验证确实执行了测试，不称纯静态或无执行检查 |
| C：真实单任务 | 用户看到实际命令、镜像/资源能力与预算后批准；只执行一个 task/attempt，含独立 verifier | 多轮模型调用和工具执行；不等同于一次 smoke 请求 |

G0 当前未正式通过。A 为有限准备开发，不等于自动放行真实运行；A/B 完成后集中整理现有 G0 五条证据和实际试点配置，提交一次评审，**C 前确认 Gate 决议与执行授权**。不要求所有 P0 adapter、四场景或全量数据到齐。

如 B 无法提供隔离且可读的 container scope，允许交付精确阻塞/降级方案，不凭空标 ready，也不先花模型调用预算试跑。

## 4. A：实现最小单任务 Runner

### 4.1 输入与执行隔离

- 复用 PREP-01 的 hash/instance 检查、Agent 白名单和输出保护；只向 Agent 传 problem_statement 及公开的工作环境说明。
- 原始记录、gold patch、test_patch、F2P/P2P/eval_script 不进 Agent prompt、工具容器、模板上下文、工作目录或挂载；startup command 保持不设。
- 环境视图只给镜像/repo/base_commit 等必要字段；evaluator 在独立进程/容器中按需读取验证规格。原始 record 的 `agent_input_authorized=false` 不改成全记录放行。
- 从固定本地记录调用已安装 mini 的单任务 API，不使用默认 HF 批量加载、不创建第二个任务、不执行 mini 提供的全量 benchmark CLI。
- 自有 wrapper 保留 mini 原动作协议/Agent loop；不随意将原进程内工具改成子进程来制造“独占 Tool 归因”。
- 不挂宿主 home、项目全根、Docker socket、SSH/key 目录进工具容器；模型凭据留在宿主模型进程，不进入 Tool/Verifier 的环境、argv 或文件。API 使用成功 smoke 的已批准代理方式，容器网络另列审批。

### 4.2 Agent 与 verifier

- Agent 结束或失败时尽可能导出 candidate patch、工具日志与受保护轨迹；candidate 必须来自此次工作树，不拿 gold patch 替代，不重用历史成功 patch。
- 保存明确的工作树/base commit 核对结果；导出阶段不运行候选修改的宿主代码。
- verifier 使用相同已固定镜像 digest 的**独立干净容器**，只应用此次 candidate patch，再按固定 evaluator 规格执行。不要把 Agent 已改动的容器当干净验证环境。
- verifier 允许读取其所需测试规格，测试答案不反馈给尚在运行的 Agent。本批只有一个 Agent attempt，不做“看 verifier 再修一次”。
- 优先复用固定官方 evaluator 与 parser，而非自己重新定义 resolved。核实本地版本的容器资源参数、自动 pull/资产下载、镜像删除与日志清理；禁止其隐藏联网和广泛 cleanup。
- B 如需执行第三方 evaluator，在项目独立执行副本/环境中使用固定版本（核对许可/commit），不在 references 安装或写日志，不原地修改第三方包。已有依赖不必重复安装。
- 工程状态分别为 execution/evaluation/archive；无 candidate、patch apply 失败、基础设施失败、测试未运行、verifier_timeout 都显式记录，不能笼统记成任务未解决。

### 4.3 模型调用与记录

- 复用 ENV/SMOKE 已验证路由、引用凭据解析、环境隔离、usage 白名单和错误摘要；不重新跑单请求 smoke。
- 一次任务包含多轮请求，每个请求有 ID、同机 monotonic 起止/UTC anchor、usage 和安全状态，关联 run_id/attempt_id。
- 明确禁用 mini/litellm/底层 SDK 的请求重试；任务失败不自动再启动。协议纠正提示若产生新调用也计入请求预算，不叫“免费重试”。
- 轨迹保留 Agent/LLM/Tool/result 结构，但密钥或网关回显不能先落原始文件再删除。记录安全过滤规则；秘密不得进入响应全文、traceback、config 或报告。禁止把 `_captured_requests` 调试证据带到真实路径。
- 费用未知：amount=null，usage 保留；原生 cost=0 只列来源值。先确认取消 bundled 3 USD 限额的已安装版本语义，不能自行猜 0/-1；用户未设金额上限不等于无限调用。

## 5. A：基础采集与报告（不要扩成完整平台）

### 5.1 必须可区分的 scope

| Scope | 最小观测与边界 |
| --- | --- |
| Agent sandbox/container | cgroup 累计 CPU、memory current/peak、I/O（平台支持时）；工具运行主要测量边界 |
| 宿主 Agent/model runtime | 独立进程身份及可行 CPU/RSS 观测；无法覆盖其全部子进程须明确缺口，不能忽略后称 Agent 总资源 |
| Verifier container | 与 Agent 分开计时和计量；不混入“Agent 工具消耗” |
| Collector/准备/导出 | 监测器置于被测 scope 外，记录自身范围；初始化/收尾单独声明，不从总量中消失 |

优先读取实际容器对应 cgroup，记录 container ID、host/boot/namespace、scope locator、来源方法。不要把宿主根 cgroup、Docker daemon 或所有容器总计冒充本次数据。

### 5.2 计量最小要求

- CPU：边界累计计数器增量，统一为 core-seconds；CPU/wall 是平均核心数，不是效率。计数器 reset/消失、基线读取晚于工作开始须报告。
- memory：cgroup current/内核 peak 与采样 max 分开；无 memory.peak 时可用采样峰值，但标下界。进程 RSS 不等于 cgroup memory，不把各 scope 峰值相加。
- I/O：有 scope io.stat 才报相应 block I/O；空值/不支持不填 0。可说明缓存影响，不将其等同应用读写量。
- 时间序列初始采用 500 ms，保存实际采样时刻/间隔与缺口；边界累计 CPU 补短突发，不把采到点数当准确性证明。
- 工具开始/结束、命令类别/安全摘要、result/超时在语义日志记录。时间重叠只能形成关联窗口，不能据此标 exclusive_tool_cpu。
- 容器与 scope 自动删除前先导出最后计数器和日志；必要时通过自有环境 adapter 控制清理顺序。计数器读取失败保留 null/原因，不冒充零消耗。
- 本批不用 perf/eBPF，不改全局 cgroup/sysctl。没有 delegation 时保留现有 container scope；禁止迁移无关进程。

产出小型资源摘要与 timeline 数据：scope、wall、CPU、memory、I/O、LLM request/Tool 数、coverage 与局限。不强求 IR 承载所有新字段；最小扩展或 sidecar 映射说明即可，不重设计已验收 IR。synthetic/resource/benchmark_real 的来源必须区分。

## 6. A/B 测试：一次集中完成

默认 unittest 不依赖 mini、Docker、真实 key 或旧数据。实际 SDK/Docker 测试是单独显式入口，按授权范围执行。

最低回归组：

1. 任务 hash/identity/答案隔离、环境凭据不进入工具/日志；fake prompt/response/异常 canary；输出目录/软链接/不覆盖。
2. 假 Agent→工具→candidate→假 verifier 完整路径；成功、Agent 失败、无 candidate、verifier 超时、归档失败；三类状态分开。
3. 请求/step/token/time 预算计数，嵌套重试=0，watchdog 中断后本次 Agent/工具/采集子进程退出；只清理本次身份匹配的资源。
4. 合成 counter/gauge：CPU 单位、reset、missing/zero、memory peak 不相加、父子 CPU 不重复累加、时钟不混。
5. 生命周期：创建→采集基线→执行→最终快照→导出→清理，失败路径也不提前删除计量证据。

B 批准后用**不调用模型**的容器 canary 做一次真实 collector 检查：短时 CPU 工作与固定小内存/文件 I/O，记录 CPU 累计增长、采样/峰值口径、容器身份和最终读取。建议 CPU 工作不超过 5 秒、测试文件不超过 16 MiB、单 canary 不超过 30 秒，合计不超过 3 分钟。不下载测试程序，不执行 Django 任务/verifier。

尽可能通过同 scope 两种独立读取核对 CPU 单位/范围，记录可测开销；严格的短进程漏检/计量容差体系留 G1 完整评审。若资源不可用，交付降级边界供 C 批准，不把 metadata observed 当 workload 已测。

## 7. B 审批清单：准备环境后就停止

A 完成时给用户一份实际清单，不含秘密，至少包含：

- evaluator 固定版本、独立执行路径/依赖差异；若需新增下载，列包/源/大小估计、下载和安装磁盘上限。推荐复用已有 wheel，避免新建全套重复环境。
- 目标镜像完整 registry/repo/tag、平台架构、获取方式、估计压缩/展开空间及**待批准上限**。不能沿用未经实测的“1～3 GB”作为保证。
- 默认只 pull 已有预构建镜像，不 build；镜像不可得/需要 rebuild 时停止并单独说明。批准后解析并记录 RepoDigest/image ID，Agent 与 evaluator 都按同一 digest 引用，禁运行时自动拉 latest。
- 批准代理仅限指定路径/用途；不自动把宿主代理带给 Agent 工具容器。容器预检默认断外网；首次真实容器若确需外网须在 C 明确列出。
- canary 容器数量、命令、资源/时间、输出、清理身份；不执行真实模型或 benchmark。

预算提案：B wall 上限 15 分钟，磁盘/下载上限根据只读空间与镜像信息提出后由用户批准。不能为了符合旧提案隐藏 setup 时间；到限停止，不自动切源/重拉/构建。

## 8. C 审批清单：一次真实 Agent 任务

B 后整理一次 G0 评审与 C 清单，用户明确批准再执行。必须展示真实 argv/config 路径、环境/镜像 digest、task、模型、可测 scope、缺口、网络和以下预算：

### 8.1 预算与边界（建议待批准值）

| 项 | 建议待批准值 |
| --- | --- |
| 任务/attempt | django__django-16485；1 task、1 attempt |
| 模型请求硬上限 | 30 次（多轮 Agent，不是 smoke）；计入协议修复请求，失败不重试 |
| 每请求输出上限 | 4096 tokens，按已验证 SDK 参数传递；不是照搬 smoke 的 100 tokens |
| Agent step 上限 | 30；与模型请求数分别计数并说明 mini step 语义 |
| Agent wall | 最多 25 分钟 |
| Verifier | 最多 5 分钟且受剩余总预算限制；无可验证 candidate 时不强跑 |
| 总执行 wall | 30 分钟，从执行阶段初始化开始计时，初始化/导出计入；不把 setup/pull 混入此计时 |
| CPU/内存 | Agent sandbox 和 verifier 顺序运行，各最多 4 CPU/8 GiB；宿主 runtime/collector 另列开销及限制方式，不声称全主机都被此限制覆盖 |
| 新产物 | 5 GiB，持续检查；镜像/依赖另计，不能用磁盘满作为唯一停止机制 |
| 费用 | 未设金额上限，预计总 token 未知；请求数×单请求输出上限只是输出预算上界，不是总费用上界 |

预算数字不是已授权值；若选用不同值须在批准前解释，不在运行中放宽。mini 不支持某上限时用自有 wrapper/watchdog 实现，不能仅写进 manifest。

Agent 与 verifier 分别有安全停止/容器回收机制，超时也保留轨迹和最终采集结果。取消远端请求不保证停止计费。达到任一硬限即停止，不恢复同一任务继续跑；后续重试另批批准。

执行前确认最终无秘密命令一次；运行中给简短阶段状态，不输出完整 prompt、密钥、环境或原始 traceback。不因为任务失败自动改模型、换实例、增加请求额度。

### 8.2 实际入口与最终命令登记（已登记；唯一有效版本）

2026-09-12 早期只读核对时仅有组件 API 与 `plan-coding-pilot` CLI，无 C 专用入口；经用户授权离线组装后，以下字段已由实际存在的入口填写并验证（组装记录见 [RUN-01 交付 §5.15](coding_pilot_delivery.md)）。本节取代此前所有“待填/待组装”表述。**双旗标只是软件门禁，不能证明输入者身份**：授权以用户在评审中对本清单的明确批准记录为准，旗标仅在批准后由用户本人键入；其他模型/会话不得自行添加旗标视作已获授权。

**计划命令（无秘密，默认只输出离线计划，不执行任何东西；入口在计划模式同样核对配置身份与预算合法性）**：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.c_entry
```

**执行命令（唯一真实入口；批准后由用户键入双旗标）**：

```bash
cd /home/lcq/agent_workload_characterization
# 会话内先注入（值仅存在于内存与环境，不落盘）：PILOT_API_BASE=<网关 base 含 /v1>、PILOT_API_KEY=<密钥>
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.c_entry \
  --execute --i-approve-the-c-run
```

已实现并离线测试的拒绝路径：单 `--execute` → rc=2；双旗标但凭据环境缺失 → 在任何容器/子进程启动前 fail-fast（报变量名不报值）；catalog `execution_authorized: true` → 拒绝；**catalog 内容与登记 SHA-256 漂移（含预算被改）→ 计划与执行两种模式均拒绝组装**；预算字段类型/有限性/正值校验失败 → 拒绝。

组装要求落实情况（此前列出的要求逐项满足）：固定 record SHA/instance/base commit 每次运行前复核，Agent 仅接安全视图；两套 venv 按职责使用（mini 子进程用 mini venv，运行进程用 evaluator venv），无静默安装/混用 site-packages；凭据经 `PILOT_API_BASE`/`PILOT_API_KEY` 执行时读取，映射子进程 `OPENAI_API_BASE`/`OPENAI_API_KEY`，仅内存传递，命令/快照/日志无 key；§8.1 预算真正传入模型配置（step_limit=请求数上限、wall、max_tokens）、runner 与两容器创建参数（4 CPU/8 GiB）；`storage_size` 不启用（本机不支持 `--storage-opt`）；容器网络 `none`，无宿主 home/项目根/Docker socket/凭据挂载，仅宿主模型进程访问网关，无代理变量自动继承；真实模式不携带 fake transport/env/test hook；输出独占创建，仅操作本次 run 身份。

| 登记字段 | 登记值（2026-09-12 实际） |
| --- | --- |
| C 入口路径与完整 argv | `src/agent_workload_characterization/runners/c_entry.py`；完整命令见上方两段（计划/执行），无内联脚本 |
| 执行解释器及 mini 子进程解释器 | 运行进程 `.venvs/swebench-eval-02e7a74/bin/python`（swebench 02e7a74 + pydantic，verifier lazy import 所需）；mini 子进程 `.venvs/mini-swe-agent-2.4.6-env01/bin/python`（模板经 `load_bundled_config` 从该 venv 加载） |
| 无秘密配置快照与 SHA-256 | `workload_catalog/coding_pilot.yaml`，SHA-256 `aee38eaca781df014117c4af14ce6df4fce91e2808dde09b03271b1e94902f83`（入口硬编码同值，漂移即拒绝组装；预算/镜像/网络与本清单一致；`execution_authorized: false` 强制） |
| 任务与镜像 | record `data/raw/public/swebench_verified/78f471bf.../django__django-16485/record.json`（SHA-256 `762de270d1ce...ec46a`，入口复核）；镜像 `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c2...7b7d2`（Agent 沙箱与 verifier 同 digest，record 的 x86_64 字段经配置层映射、record 只读） |
| 入口及关键自有代码身份 | git HEAD `b4437fb8c7563ccfb384a422c23994e43c9ac957` + 未提交改动 21 项（不假称仅由 HEAD 决定；关键文件 SHA-256 前缀见 [交付 §5.15](coding_pilot_delivery.md)，入口 `65f4d62faa02c0db`） |
| 新 collection/run 输出位置 | `data/raw/generated/RUN-01-C/<run_id>/`（candidate/轨迹/事件/采样/metadata/manifest）+ `reports/resource/` 摘要；不覆盖 A/B、gold、smoke 或旧 attempt |
| 进程/容器资源参数 | 两容器同 digest、各 4 CPU/8 GiB、网络 none、无可写层配额（r7 实测不支持）；宿主 runtime/collector 开销单列 |
| 授权记录 | 用户原文、UTC 时间、批准的配置/命令身份——**当前均为待批准，未代填** |

执行前须向用户重申的已知缺口：宿主 mini 子进程（host_agent_runtime scope）本 run 无逐进程 CPU/RSS 采集（仅 status 协议 wall/请求边界）；I/O 降级（v1 blkio）；容器可写层无配额，5 GiB 仅为 run_dir 检测阈值（§8.3-1）。

### 8.3 已完成证据：不重复执行

| 项 | 已验收证据与范围 |
| --- | --- |
| 模型连通性 | [SMOKE 交付](model_smoke_delivery.md)：成功批次工具协议通过，usage 308/69/377；认证引用在内存解析，费用未知；不是任务成功证明 |
| 实际 mini 编排 | `tests/integration_run01.py`：安装版 mini + 离线 fake transport/工具执行器，3 项通过；不是实际模型任务 |
| 原生资源采集 | [r7 报告](../reports/resource/RUN-01-B-canary-r7/canary.json)：23.68 s，CPU 5.122157/12.27605 core-s，两个 workload 均成功，`mem_alloc_ok 134217728` |
| 两类停止路径 | r7 的 docker-stop 路径；[独立停止链报告](../reports/resource/RUN-01-B-canary-r7-stopchain/stop_chain.json) 的存活容器确认路径，停止后计数器可读 |
| 评估链兼容性 | [gold verifier 报告](../reports/resource/RUN-01-B-goldverify/RUN01BGOLD-20260912T104224Z-617538/goldverify.json)：12.28 s，10/10 测试通过，官方 parser `resolved=true`、`infra_failure=False` |
| 入口与审批材料 | `runners/c_entry.py` 离线组装并登记（本节）；离线计划/拒绝路径在登记解释器实测通过；默认 390 项测试通过。**C 未执行** |
| 证据完整性 | 上述报告目录各自 manifest 的登记文件 SHA 已于容器交付评审核对匹配；不修改这些封存报告 |

gold 验证仅证明固定任务/镜像与 gold patch 的链路可运行。它是独立 verifier 验证，不计为真实 Agent attempt，也不作为 C 的 candidate。`pip install -e .` 在离网容器失败；本次日志确认测试导入 `/testbed/django` 且通过。保留该限制，不推论任意 Agent 修改或依赖变化均兼容。

### 8.4 本次须明确接受的降级与风险

1. **磁盘**：r7 证实 daemon 不支持 `--storage-opt size=6g`。5 GiB 只检测 `run_dir`，不限制容器可写层，删除容器是事后回收而非磁盘防满保证。最终清单须列出项目输出盘与 Docker 数据盘实际可用空间，并请用户明确接受该单次运行风险；空间不足或需新增保护机制时停止，不自行修改文件系统/daemon，不宣称已有未实现的全盘监控。
2. **计量**：主机 cgroup v1；CPU 边界增量、memory current/kernel peak/sampled max 分开。scope block I/O 本机不可靠，正式结果 null + 原因，原始计数仅作诊断；不声称 per-tool 独占 CPU、完整宿主 CPU 或 PMU/hotspot。
3. **停止**：`stopped_confirmed`、`stopped_via_docker_stop`、`stop_not_confirmed` 分开。docker stop 后 cgroup 可能消失，最终值不可读即 null/原因。30 分钟为工作负载执行预算；紧急终止、证据保存与清理耗时单列，不为满足数字伪称已全部停止。
4. **模型与费用**：未知价格 `amount=null/cost_status=unknown`，来源原生 0 不当免费。任务最多一次，不自动重试；取消本地请求不保证远端停止计费。协议纠错的新调用计入 30 次。
5. **验证限制**：离网安装步骤已知失败，不允许为候选 patch 临时开网、安装依赖或换镜像。candidate 导致评估失败时照实归档，不将失败改成未执行或自动使用 gold 补救。

### 8.5 G0 决议与用户执行授权分开记录

- G0 证据汇总见 [当前评审记录](../reports/quality/g0_review.md)。本轮只补齐材料，状态维持 `READY_FOR_REVIEW`，不代替正式 Gate 决议。
- 用户先看到 8.2 的**实际**命令/配置和 8.4 风险，再明确批准 C；“补齐文档”不是批准运行。
- C 一次性批准范围：一个 `django__django-16485` attempt，DeepSeek-V4-Flash + mini 2.4.6，固定 arm64 digest，候选 patch 的独立 verifier，及本次采集/归档/身份限定清理。**不含**重跑 smoke/canary/gold、pull/build/install、换任务/模型、放宽预算、perf 或下一次 attempt。
- 双旗标 `--execute --i-approve-the-c-run` 是软件门禁，不证明输入者身份；授权仅由用户对本清单的明确批准记录构成。
- 当前记录：`G0_decision=pending`；`C_user_approval=pending`；`C_command_frozen=true`（入口/命令/配置哈希已按 8.2 登记冻结，变更须重新登记并重新审批）；`C_executed=false`。这些是事实状态，不是可以通过改 YAML 自行获得的权限。

### 8.6 批准后的顺序与一次性交付

1. 对照批准的代码/配置身份、record、镜像及路径做只读核验；变化或缺失则停止，不自动修环境。
2. 创建本次 Agent 容器、确认工作树与资源基线后运行一次 Agent；模型密钥留宿主，任务答案不进入 Agent。
3. Agent 停止，保留停止原因、状态/轨迹与本次 candidate；在预算与执行状态允许时，用独立干净容器运行 verifier。无 candidate 不强跑，不以历史/gold 替代。
4. 保留可读最终计数器与采样；归档后清理本次身份匹配容器，失败/未确认停止与残留如实记录，不清理其他资源。
5. 交付原始安全轨迹、candidate、verifier 日志、events、samples、metadata/manifest，以及 `reports/resource/` 摘要和 `docs/coding_pilot_delivery.md` 的 C 记录；大文件被截断/跳过时声明。报告保留 execution/evaluation/archive 三状态、实际请求/usage、成本未知、scope/coverage、磁盘降级与清理结果。

无论 `resolved` 真/假、超时或失败，交付后停止。C 完成仍不自动通过 G1，不据单条样本给 CPU 架构或生产代表性结论。

## 9. 新产物与验收口径

建议布局（允许合理合并，禁止搭空目录）：

- `src/agent_workload_characterization/runners/coding_pilot.py` 及必要 adapter；
- `collectors/` 最小 container/resource sampler、语义 recorder；`analyzers/` 小型资源摘要；
- 默认合成测试 + 显式已批准 Docker/SDK 测试；
- `workload_catalog/coding_pilot.yaml`：本次有效配置/预算/授权阶段，无秘密；
- `data/raw/generated/RUN-01-<collection>/<run_id>/`：新采安全原生日志、candidate、验证结果、边界与资源采样、metadata；
- `reports/resource/RUN-01-<batch>/`：scope 摘要、timeline 数据、coverage、限制与 manifest；
- `docs/coding_pilot_delivery.md`：A/B/C 分阶段实际操作与结果、Gate 决议、剩余问题。

报告必须包含 task/record/code/harness/model/config/image/host 版本证据、独立状态、scope/单位、missing reason、实际调用数及停止原因。日志封存后不覆盖；所有新 attempts 保留，不能只保留成功运行。

阶段验收：

- A：离线代码与接口测试完成、B/C 审批清单具体，可以提交开发交付；不冒充真实 Runner 已跑通。
- B：固定环境与容器计量 canary 通过，或明确不可测降级；不冒充 benchmark 已可验证通过。
- C：一次真实 attempt 的证据完整且资源范围诚实；任务 resolved=false 不自动导致工程验收失败。无资源数据时仅可验收运行子集，不能称资源闭环完成。

阻塞项限于越权/泄漏/数据损坏、实际功能错误、计量 scope/单位误导及关键控制未落实。未来精确 Tool 归因、四场景、历史措辞统一不阻塞本批。不为了表格齐全填假数据，不要求一次 RUN-01 就通过全部 G1。

完成当前已授权关口即停：A 等 B 批准；B 等 Gate/C 批准；C 无论任务结果如何均交付后停止。下一步基于真实采集缺口完善 G1，满足目标 scope 后再进入 CPU/Hotspot 试点。
