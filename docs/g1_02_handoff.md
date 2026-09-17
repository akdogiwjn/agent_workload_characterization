# G1-02：服务/异步生命周期与采集开销的有界补证

日期：2026-09-15。状态：A 已完成离线集中验证；B 最终清单见 §7，尚未批准。原 A 要求保留作为实现依据，不再从头实施。
配套：[执行提示词](g1_02_execution_prompt.md)。当前依据：[G1 集中裁定 §0](g1_consolidated_review.md)。

## 1. 用户需要做什么

把配套提示词交给实施模型，A 交付后交回原评审。原评审确认准备完成后，用户决定是否批准 B 的最终清单；B 完成再集中裁定 G1。
本任务不是新增 benchmark、不重跑 Django、不调用 LLM、无 API 费用；用小型本地自有程序补第 2/5 条证据。完成并不自动保证完整 G1 通过。

## 2. 阅读与复用边界

完整阅读 methodology.md、docs/development_tasks.md、references/README.md、references/manifest.yaml；再读 trace_contract.md、data_management.md、本任务书、g1_consolidated_review.md §0。
针对性核对：G1-01 A R4 的 mechanism_checks.json/overhead.json，G1-01 B batch/manifest，RUN-02 review-v2；历史文档旧文字不能覆盖 JSON 的已确认语义。

复用现有 `ToolEventRecordingEnvironment`、`DockerCliRuntime`、`HostProcessMonitor`、`ResourceSampler`、路径保护与清理。旧 b_entry 和 g1_01_mechanism 只作编排参考，不执行、不复制成第二套框架。允许新薄入口、自有合成 worker、定向测试和固定配置；共享模块仅在真实接口缺口时最小增补，交付列明原因及回归，不顺带重构。
保持已有采集字段与降级：cgroup v1、I/O 正式 null、共享 scope、宿主后代不完整、容器磁盘无配额。没有独占 Tool CPU 不是失败理由。

## 3. A：离线实现、预注册、审批材料（本次授权）

允许自有代码/测试/文档修改，现有解释器与依赖的封网合成测试。默认计划零副作用，不读生产配置、真实密钥、无关进程或 environ。
不调用 Docker（含查询）、网络、模型、READY/smoke、既有 canary、真实权限探测；不安装、下载、构建或拉镜像。不创建真实批准/attempt，不执行 B 的计量批次。
允许短暂自有测试子进程验证握手、退出与清理，必须在临时目录、已知 PID 下执行；单个测试子进程存活≤5 s，CPU 工作≤2 s，测试命令≤60 s。这些是回归 fixtures，不是 B 的正式测量，不写进正式证据包。

### A1 固定入口与一次性身份

- 建议新入口 `runners/g1_02_entry.py`；计划模式列完整用例、条件/预算、代码与输入 SHA、解释器/镜像/输出路径。正式命令必须实现并离线验证后登记，任务书不提供猜测命令。
- 新状态固定 `reports/resource/G1-02/APPROVAL.json`、`ATTEMPT_STARTED.json`；新报告固定 `reports/resource/G1-02/<batch_id>/`。不得复用 G1-01 或 R2 批准。
- 批准身份从实际入口生成完整结构，不手写遗漏字段；漂移/缺批准/单旗标/已有 marker 均拒绝。实际 B 还需用户明确批准及必要的工具权限；双旗标不代表身份认证。
- A 只用临时合成批准/marker 走真实入口。生产批准/marker 不创建；一次登记后失败保留，不自动开 R2。
- 预检、工作与正常清理共享绝对截止时间；停止清理保留预留。若为安全清理必须越时，记录 overrun/FAIL，不能伪称严格未越时。
- 复用本地 socket/context、镜像固定检查、pending 容器与 PID 所有权清理；不重写授权和通用 readiness 框架。

### A2 服务与异步用例（B 容器 1）

一个自有常驻 Python 服务进程，使用 stdin/stdout 控制协议或已知私有 IPC，不开网络监听。客户端协议必须有 run/service/request/job ID；自有 worker 源码、协议、固定工作量随批准身份登记。不是通用任务队列或 HTTP 服务框架。

固定一次执行序列：

1. 服务 ready 握手，记录 PID+starttime、scope、启动时间；注册后才执行请求。ready 不等于任意 sleep 猜测。
2. 在同一个服务进程内处理两个同步固定请求，保持同一身份；记录执行前后累计 CPU/请求边界，说明进程常驻而请求有独立生命周期。不把整段服务 CPU 重复分给每次请求。
3. 提交一个异步 job：submit 返回后，job 等待父端明确 release，随后执行固定工作量并完成。证明 submit-end < job-start/end、完成前 poll=running、完成后 wait/result=completed；不能把 submit 返回视为 job 已结束。
4. 第二个异步 job 在显式 started 握手后阻塞，发出取消并确认退出/终态；记录 cancelled，不冒充 completed。确定性取消不需要无限 busy loop。
5. 已知任务全部结束后关闭服务，保留最终计数、原始事件与清理证据。进程不回应时使用既有停止链；不得按名字扫描杀无关进程。

同步调用经共享 hook 实际执行；异步 job 事件来自真实 worker 的生命周期，不能用客户端观察时刻冒充 worker 起止。跨边界保留同主机 monotonic/UTC anchor 和接收时刻；共享 CPU、控制协议开销、不可分离部分如实标记。不要求实现生产服务发现或抓全短命后代。

原始证据至少含：调用/任务事件、服务/worker 身份、submit/poll/wait/cancel 对应关系、进程/容器边界和采样、停止结果。事件异常、孤立 ID、未知终态、未确认清理均影响该用例判定；预期 cancelled/非零不能被全局误判为 infra failure。

### A3 固定区间与开销实验设计（B 容器 2）

用持久 worker、确定性 CPU 运算和阻塞握手，替代旧“启动后开始采样、进程退出后取最后快照”的错位对照。

区间协议：worker ready 且阻塞 → 父端读基线 → release 工作 → worker 报 work_done 并阻塞不退出 → 父端读末边界 → ack 后继续/退出。记录每个读操作起止及 worker 工作起止，不以“同步”宣称系统调用发生在完全同一纳秒。

- 父端边界是带握手开销的包围区间；worker process_time 是工作代码段。二者不完全相同，需显式报告 bracket 差异，不再叫精确同区间验证。
- 正式 ON/OFF 比较采用相同定义的区间、相同控制协议/输出校验和/迭代数；测量对象是采样链在该协议下的影响。启动、最终报告序列化另计，不混入某一条件。
- ON 使用现有 ResourceSampler 与 HostProcessMonitor 的指定固定间隔；OFF 仅禁用周期采样，仍保留两端计数与同样握手。不能用空 no-op collector 代替 ON。
- 宿主编排/collector 进程在两条件分别记录 process CPU、wall、RSS；读取耗时单列。process CPU 含同进程线程，但不含 docker CLI 后代；不能把 reader wall 称为全 collector CPU。若要全成本，需要另批，不能本批偷换口径。
- 同时保存 worker self CPU、容器边界 CPU、host 原始记录、样本数、实际采样间隔/缺口、每次条件和顺序、校验和。分开 worker 工作、控制开销、宿主开销，不无条件求和。

固定 6 对 ON/OFF（12 次工作区间），顺序 OFF/ON、ON/OFF 交替，无预热批、无校准后重试。工作量 A 结束前固定（建议 20000000 次整数循环，仅作为待登记选择）；单次太短或超时保留 inconclusive/failed，不在 B 调大循环补跑。

预注册文件 `workload_catalog/g1_02.yaml` 必须在 A 交付前填全：精确 workload/校验和、采样周期、区间语义、ON/OFF 差值定义、最小有效采样/CPU 时间、边界读延迟上限、CPU 跨源诊断容差的公式与依据、比较用途和拒绝条件。
不得猜测机器精度：CLK_TCK/页大小可作为 B 运行时读取的量进入预先冻结公式；不能事后根据结果调公式。0.2 s 采样间隔不等于误差为 0.2 s；1/CLK_TCK 是分辨率，不是全部误差。

正式判定分两层：机制/证据完整性 PASS/FAIL；比较证据 sufficient/inconclusive（独立字段）。6 对数据只报告原始对、median/range 等预登记描述量；不以全部成功或差值小就声称稳定 overhead 百分比。负差值保留为噪声/干扰结果，不能叫“负开销”。不能把本工作量的容差外推为所有 Agent 的通用性能阈值。
实施模型须在 A 中提出可解释的数值门槛与依据，原评审核对后交用户批准；未填写或依据不足时只能交设计缺口，不能进入 B。

## 4. B 最终批准预算提案（目前未授权）

| 项目 | 固定上限/范围 |
| --- | --- |
| 批次 | 1 次；用例 1 服务/异步，随后用例 2 开销；不重试 |
| 镜像 | 仅已有 `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`，作合成程序载体，不运行 Django |
| 容器 | 最多 2 个、严格顺序，各≤2 CPU/256 MiB，network none、pull never，无特权或宿主数据/socket 挂载 |
| wall | 从首次本地预检前开始至正常清理≤300 s；预留30 s清理；单操作≤15 s且取剩余时间 |
| 工作量 | 服务固定2同步请求＋2异步job；开销固定6对/12区间；单工作区间≤8 s，服务单job≤8 s |
| 进程 | 同时最多4个自有受测进程（不含已登记编排/必要 docker 客户端）；不扫描无关进程 |
| 采样 | 容器0.2 s、宿主0.2 s；A 登记后不得 B 自适应变更 |
| 数据 | 只写私有临时程序/控制文件，合成文件≤8 MiB；报告20 MiB检测阈值，超限停机并保留最小失败证据，不称绝对磁盘配额 |
| 网络/费用 | 无网络请求，无模型/凭据/API；不安装、不拉镜像、不探测 perf/eBPF |

固定本地 Docker socket，清除远端 context 影响；若权限不足，仅为登记单次命令申请所需工具权限，不 chmod/sudo/全局关闭限制。旧批准不能放行。默认 B 两用例任一非预期失败停止后续、归档并清理；比較证据 inconclusive 也不补跑。

## 5. 最低回归（A 一次集中交付）

1. 实际新入口的计划/单旗标/无批准/身份漂移/旧批准/重复 marker 门禁；完整身份生成后再写合成批准，禁止手抄缺字段。
2. 服务同 PID 跨请求、job 在 submit 返回后才 release、poll/wait/cancel 终态；丢 started/错 ID/无终态 → 非 PASS。回归用 fake runtime 加短本地协议程序，不操作 Docker。
3. 握手确保 worker 末读之前仍存活阻塞；拒绝把启动/退出区间偷换为工作区间。ON 实际调用 collectors、OFF 无周期读；缺样本/边界reset/区间不满足门槛 → 比较 inconclusive，不能伪充分。
4. 真实生产编排经 fake runtime 到归档/manifest/清理；超时、报告超限、服务挂住、启动异常都保留身份和失败证据，清理单独执行；不要只测 helper 或注入假 PASS。
5. 固定输出根/逐段symlink/独占文件/旧源保护；输入和输出哈希闭环、缺失/不一致非 PASS；受测进程开始的握手证据避免只测试解释器导入期耗时。

只跑新增定向套件与实际受影响共享模块回归；不以新增测试数量为目标，不重跑全部历史数百项或无关 SDK 集成。保留假凭据完全不需要；本批没有认证路径。

## 6. 交付与范围控制

A 交付仅一份 `docs/g1_02_delivery.md`：改动/复用关系、实际测试、预注册条件、唯一可执行命令、完整代码/config/worker/镜像身份、输出位置、两容器具体操作、预算和停止链。标 `user_approval=pending`、`tool_execution_permission=pending`。
允许新增新入口/worker/定向测试及固定配置；必要共享修正逐项解释。不改 RUN-01/RUN-02 代码身份记录、旧 catalog、历史报告、references、旧 raw、批准/marker。README 与 docs 索引只替换当前任务入口，不再堆叠“下一步”。

B 获批后的包包含原始生命周期事件、进程/资源证据、12 条条件结果、开销/容差判定、cleanup、summary、manifest（所有输入与输出SHA，manifest不自哈希）。执行/计量充分性/归档/清理分列，不把“报告生成”当实验成功。
执行后仅追加同一交付文档，交回原评审；G1 判定由评审针对实际覆盖决定。不再生成连续返修任务书；阻塞只限授权、安全、停止、假成功、核心证据不成立，其他作为范围限制。

## 7. B 最终待批准执行清单

状态：`user_approval=pending`、`tool_execution_permission=pending`。用户要求“修复并准备下一阶段”不是 B 运行授权。本清单已完成代码接线及短离线验证；不重复 READY/smoke/B1，也不要求再跑 Django。

### 7.1 唯一身份与命令

项目根：`/home/lcq/agent_workload_characterization`。
完整拟批准身份：[workload_catalog/g1_02_identity.json](../workload_catalog/g1_02_identity.json)。它不是批准记录。包含 50 个自有代码完整 SHA、catalog SHA/config、worker/controller、解释器 `/usr/bin/python3.11` 及版本、固定 arm64 image digest。批准必须绑定这份身份；禁止手写遗漏字段。

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src /usr/bin/python3.11 -B -m agent_workload_characterization.runners.g1_02_entry --execute --i-approve-the-g1-02-b
```

去掉两个旗标是离线计划；单旗标返回 2。双旗标仍须真实批准文件、身份完全一致和 marker 不存在。计划/配置解析需要项目现有 PyYAML，不安装依赖。此次无 API，无凭据，也无需代理；不要读取 opencode.json 或 VOLCANO_API_KEY。

### 7.2 用户批准的范围

| 内容 | 本次固定范围 |
| --- | --- |
| 任务 | 自有合成服务与开销补证，不是 Django task，不调用模型 |
| 容器 | 已有固定 arm64 digest，最多 2 个顺序；各 2 CPU/256MiB，none/never，不挂载宿主数据/socket、不特权 |
| 服务 | 同一 worker 的两个同步请求，各 1,000 次运算；两个异步 job 分别 completed/cancelled；同步 hook 各自记录 |
| 比较 | 第二容器同一 worker；固定 20,000,000 次循环 × 12 区间、6 对；ON/OFF 交替，不预热、不补跑 |
| 采集 | 宿主 controller；两条件各有边界，ON 0.2s 周期采 cgroup 与本进程 CPU/RSS；真实采样间隔保存 |
| 时间 | 总 300s，自预检前至正常清理；预留 30s；单 Docker 操作≤15s、job/window≤8s，均取共享剩余 |
| 磁盘 | 小型 owned source 通过 argv 进入容器，worker 不写数据文件；报告20MiB检测阈值，允许检测超调与最小失败证据；容器可写层无配额 |
| 清理 | 仅本批名称/handle/pending 身份；正常清理截止后每操作最多0.1s尽力清理，标 overrun/FAIL，不承诺一定删除成功 |
| 结论 | 正式 I/O null；shared CPU；宿主不含 Docker CLI 后代；不宣称稳定 overhead 百分比或独占 Tool CPU |

比较定义、门槛和诊断公式见 [交付 §4](g1_02_delivery.md#4-固定测量定义及限制)。同一批 mechanism PASS 但 comparison inconclusive 是允许结果，不自动转成充分，也不重试。

### 7.3 获批后的严格顺序

1. 读取本清单和交付；离线核对实时 build_plan identity 与拟批准身份完全相同。检查真实 APPROVAL/ATTEMPT 是否已有；不删除、不覆盖、不创建第二个 attempt。
2. 没有用户对本清单的明确批准时停止。获得批准后，把实际批准人/批准 UTC 时间和用户原话记录到新 `reports/resource/G1-02/APPROVAL.json`。结构为 `approved: true`、`approved_by`、`approved_at_utc`、`checklist_identity`（后者完整复制已核对 identity）。独占创建；任何旧批准不能授权本批。
3. 针对上面的唯一命令申请单次工具执行权限（宿主本地 Docker socket 需沙箱外时）；不要先偷偷查询 Docker，也不申请宽泛 python/shell 永久权限。用户批准与工具许可是两层门禁。
4. 一次启动同一进程：原子 ATTEMPT → 临时清除代理/远端 Docker 路由 → 固定本地 context/image 预检 → 两顺序容器 → 证据 → 清理 → 报告 → marker 终态。退出恢复原进程环境，不依赖之前 shell 的残留设置。
5. 预检失败返回4；执行/清理/归档/marker 失败非零；身份拒绝返回3；成功机制与完整归档返回0，但仍要读 comparison。任何失败或 inconclusive 均停止，不补跑、不调门槛、不拉镜像、不自动修代码后再试。
6. 同一交付文档追加本次 run_id、退出码、wall、两用例状态、比较结果、归档与清理证据、局限，交回评审。不自行宣布完整 G1 通过。

### 7.4 输出位置

- 批准：`reports/resource/G1-02/APPROVAL.json`。
- 一次性记录：同目录 `ATTEMPT_STARTED.json`，只由入口登记与更新。
- 预检：同目录 `PREFLIGHT.json`，独占创建，失败也保留。
- 批报告：`reports/resource/G1-02/G1-02-<UTC>-<unique>/`。
- 每用例即时 `*.events.jsonl`；同步 `service.tool_events.jsonl`；拆容器前 `*.evidence.json`；`summary.json`；manifest 全输入身份/输出哈希且不自哈希。异常可能只有部分证据，归档错误另记 `archive_failure.json`，不伪造完整文件。

本次准备阶段以上真实文件均未创建。旧 G1-01/RUN-01/RUN-02/READY 产物不修改。
