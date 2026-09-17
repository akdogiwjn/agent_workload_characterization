# CPU-01：CPU/Hotspot 候选与 perf 可测性最小准备

状态：`A_VERIFIED / B_EXECUTED_ONCE`。A 经两轮评审反例修复重验（[交付 §8/§9](cpu_01_delivery.md)），B 已获用户批准单次执行完毕（[交付 §10](cpu_01_delivery.md)）；证据封存于 `reports/cpu/CPU-01/`，不重复执行，后续方向由评审裁定。

## 1. 目标与完成边界

G1 资源小闭环在登记范围内已通过，依据 [集中裁定 §0](g1_consolidated_review.md)。下一步进入 P2，但本批不实现整个 P2：

1. 从已有真实 RUN-02 数据选出后续 CPU/Hotspot 候选 **scope**，说明依据与缺失。
2. 实现一个最小、任务级 perf 可测性入口，A 用 fake perf 进程验证；B 另批后只对自有合成进程验证。
3. 区分硬件事件、软件事件与符号采样各自可用性。不可用是结果，不自动安装、提权或反复试配置。

对应长期 P2-01 的单样本候选选择和 P2-02/P2-04 的最小可测性准备。不是全量 Representative Selector、微架构分类器、FlameGraph 前端或 G2 验收。合成程序的热点不得称为 Agent 热点；后续真实工具 profiling 必须另立清单。

## 2. 阅读与复用

先完整阅读：`methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`。再读 `docs/trace_contract.md`、`docs/data_management.md`、本任务书、`docs/g1_consolidated_review.md` §0 和 `docs/project_status.md`。

只读输入：

- [RUN-02 review-v2](../reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/manifest.json) 与其引用的原报告、raw；不得执行轨迹中的命令。
- [G1-02 B](../reports/resource/G1-02/G1-02-20260915T093254Z-94bb0ee7/manifest.json)：是资源采集机制证据，不是 perf 开销证据。
- 自有 `runners/container_runtime.py`、报告 writer、`collectors/host_process.py` 及相关定向测试：仅选择本批需要的接口，禁止复制启动/清理框架或修改历史入口。

A 可静态阅读现有本地 perf 文档/源码，核实 argv 与输出语义；不运行真实 perf（含版本/权限探测），不联网查安装包。必要文档不存在时列出具体未决项，不编造可执行 B 命令。

## 3. A 的授权边界

允许：自有小模块、固定配置、定向测试、文档；读取上述证据并生成独立候选说明。测试只用临时目录、fake perf 可执行程序、短暂自有子进程。单测试子进程 wall ≤5s、CPU 目标 ≤1s，单条测试命令 wall ≤60s；明确 timeout 并 kill/reap。

禁止：Docker（含查询）、真实 perf/PMU/权限探测、模型/API、网络、安装下载、生产配置或密钥；不读其他进程环境，不改 sysctl/capability/全局配置；不运行 READY/smoke/G1-02/Django。旧 raw、reports、references、批准与 marker 不变；不提交/推送 Git。不创建真实 CPU-01 approval/attempt。

## 4. 一次完成的三个工作单元

### A1 候选选择：先写清楚要测谁

输出 `docs/cpu_01_delivery.md` 的候选表即可，不建设通用选择框架。每行含 source/run/scope、CPU/Wall/memory 的原字段与单位、证据 locator、有效性、选择理由、尚不能回答的问题。

- Agent container 与 Verifier container 分别列出，不合并为全部 E2E CPU。
- mini host 的 CPU 是可读区间，不能和完整容器区间直接排同一榜。
- 工具可按已观测 wall/频次选候选，不能把共享容器 CPU 分配给单工具或据此排 Tool CPU 榜。
- 只有一个 task 的两个 attempt，不声称生产代表性；本批不增加任务样本。

### A2 单一入口与 perf 适配

建议一个薄入口、一个采集/解析模块、一个固定配置；自有已知工作程序尽量简单。不改已有 G1 语义，不引入通用调度器。

生产调用路径必须是：计划/身份核验 → 单次批准与 attempt → 同一执行环境内有限预检 → 启动自有受控程序并采集 → 解析 → 独立归档 → 清理确认。A 测试替换外部 perf 程序及计数输入，必须经过实际入口和同一解析/归档路径，不能直接 mock 一个 PASS。

要求：

- 默认计划零副作用；执行旗标不等于用户批准。复用已存在的批准/独占登记思路，独立 `CPU-01` namespace。身份覆盖实际代码、配置、解释器、目标程序及登记事件；已有批准不能授权本批。
- perf 只包围本批自建目标及明确登记的线程/后代范围，不使用 system-wide 模式，不 attach 任意 PID，不复用历史容器。PID/starttime、目标 argv 身份与测量 scope 分开记录。
- A 固定一次 stat 请求和一次 record 请求的 argv/事件/频率/目标程序。命令依据需定位到已读文档或源码。硬件事件不可用时记录原因，不能循环换事件直到成功；软件结果可单独有效，不自动提升为硬件支持。
- stat 原始值、单位、支持状态、运行比例/缩放语义分别保留；缺失、不支持、权限拒绝、零值不得混同。实际格式有 enabled/running 则保留；没有则 null，不从一个百分比捏造二者。IPC 仅在同 scope/同区间且 cycles/instructions 有效、分母正值时输出。
- record 保留原始采样文件、解析输出和目标 binary 身份；区分无样本、符号未知、丢样信息不可得。样本比例注明分母；本批只输出小型函数表，不开发 FlameGraph UI。没有可靠符号时允许 partial，不添加未经批准的 unwind/安装步骤。
- collector wall/CPU 覆盖范围明确；G1-02 的约 0.9ms 配对中位数不可用作 perf 误差界或开销扣除。CPU 计数/采样成功不证明微架构瓶颈。
- 单一绝对 deadline 贯穿预检、采集、解析与清理；连续排空有界 stdout/stderr，超时终止且 reap 自有进程，不能只杀客户端后留目标继续跑。报告阈值为检测停机而非绝对磁盘配额。
- 原始错误仅在安全投影后进入报告；不捕获全机命令/环境。失败仍留下状态、已获得计数、缺失原因和清理证据；不伪造空的成功报告。

### A3 交付与一次集中验收

必须具备以下实际反例，允许一个测试覆盖多项，不设测试数量指标：

| 组 | 必须证明 |
| --- | --- |
| 门禁 | 默认无进程/写入；旧/缺批准拒绝；身份漂移拒绝；一次性 marker 生效 |
| stat | 有效值/真实零、not-supported、权限错误、缺值、部分计数、零 cycles；无有效依据不生成 IPC |
| record | 有符号/unknown/零样本；rc=0 但输出缺失不能声称 profile 成功 |
| 进程 | 有输出阻塞、超时、启动失败；目标确实开始后才触发超时测试，停止及 reap 可核验 |
| 证据 | 成功和失败均归档；输出守卫、输入/输出 SHA；清理失败不能 PASS |

先完成调用链与测试再登记 B 命令。没有真实 perf 运行并非 A 缺陷；实际生产接线缺失才是。若只剩权限/PMU/符号等运行期未知，可完成 A 并列为 B 的待测项，不以“真实环境未测”为由继续离线返修。

## 5. B 最小提案（不是授权）

本提案只验证当前宿主 native arm64 的 **自有合成进程**，不操作容器、模型或真实任务；不得据此宣布容器 PMU 归因成立。

| 项 | 固定提案上限 |
| --- | --- |
| 批 wall | 120s，含正常清理，预留20s |
| 采集 | 最多一次 stat + 一次 record；目标进程顺序，不同时运行 |
| 单目标 | wall ≤10s；固定工作量，预期 CPU ≤5s，超 wall 停止 |
| 预检/解析 | 各阶段均受共享 deadline；能力查询只限本批必需项，最终清单逐项列出 |
| record | 频率不高于99Hz；具体事件/模式须 A 核实并冻结 |
| 新产物 | 20MiB 检测阈值，阈值触发停止并留最小失败证据；无绝对磁盘配额声明 |
| 副作用 | 不安装、不提权改配置、不网络、不全机采样、不追踪无关进程 |

perf 不存在/被拒绝：归档 `unavailable` 并停止，不安装、不重试。部分事件不支持：如实记录 partial；仅在预登记流程已允许且安全条件仍满足时继续唯一 record，不临场补测。任何启动/清理/身份错误终止批次。结果不足也不新增重复对照。

## 6. A 的交付清单

更新本任务的 `docs/cpu_01_delivery.md`（实施时创建）：候选表、实际修改、生产函数→测试→产物字段映射、实际测试、完整身份、B 唯一命令与逐项预算、预检列表、支持/不支持时的终止规则。B 命令必须离线验证，不能照抄历史入口。标记 `user_approval=pending`、`tool_execution_permission=pending`。

不修改本提案预算以适应测试；设计变更明确列出交回评审。A 完成即停；原评审集中验收后，用户对最终清单及工具权限另行批准 B。此任务不授权 B，不宣布 P2/G2 完成。
