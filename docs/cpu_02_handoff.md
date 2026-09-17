# CPU-02：真实 Verifier 执行段的容器内目标映射与热点小试点

2026-09-16。`A_REVIEW_FIXES_APPLIED / B_PENDING_APPROVAL`。A 首轮交付后经评审五组反例（屏障协议、符号链、终态消费、端点固定、日志收尾）一次修复并以 31 项定向回归重验（见 [交付 §8](cpu_02_delivery.md)）；待原评审复核后，B 仍是待批准提案，本任务书未授权 B。

## 1. 为什么做，以及只做什么

CPU-01 已验收：宿主对自有合成进程的 perf 路径可用，不证明容器 PMU 或 Agent 热点。本批选择 **SWE-bench Verified django__django-16485 的 Verifier 段**，使用 RUN-02-R2 已封存的 candidate.patch，在一个新建、隔离容器中准备一次验证与函数采样。

选择 Verifier 是因为任务、补丁、镜像、官方判定链已有证据，执行段短、无需模型。不是重跑整个 Agent，不取轨迹中任意 shell 命令，不使用参考 gold patch，不新增 benchmark，也不验证通用 replay 保真。

本批只做 **一次 perf record + 同期容器资源边界**；不额外运行 stat，不做优化 A/B，不开发 FlameGraph UI。后续若需真实 workload IPC，另批 stat；不得把 CPU-01 的 IPC 移用给本批。

## 2. 必读与固定输入

完整阅读 `methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`。再读本任务书、`docs/data_management.md`、`docs/trace_contract.md`、`docs/g1_consolidated_review.md` §0、`docs/cpu_01_delivery.md` §10/11。

输入仅只读，实施 A 时核对并登记完整 SHA，不修改原件：

- task record：`data/raw/public/swebench_verified/78f471bf655a3137b2e8a75af1501690ec009ec3/django__django-16485/record.json`，登记 SHA `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`。
- candidate：`data/raw/generated/RUN-02/20260915T012427Z-2d75aa/candidate.patch`，核验其原 manifest；禁止替换成 record 的 patch/test_patch。
- 既有 eval 输入与 parser：`runners/coding_pilot.py::SwebenchVerifierRunner`，以及已存在的 `.venvs/swebench-eval-02e7a74` 与登记 evaluator 副本。test_patch 仅按既有 evaluator 语义用于测试准备，不能当 candidate。
- 固定镜像：`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`。A 不查询镜像；B 缺镜像即停，不 pull/build。
- CPU-01 封存批：`reports/cpu/CPU-01/CPU-01-20260916T013510Z-cf30c2dd/`；manifest SHA `5ba8b20ece46edc97d88d32727ee156618149a45f2210581da5c88fa3a420924`。

复用现有 runtime、ResourceSampler、perf_adapter、输出守卫、官方 verifier。只加必要的目标暂停/释放与 profile 接线；共享模块变更必须跑受影响离线回归。禁止复制第二套 verifier、清理框架或通用服务系统。

## 3. A 授权边界

允许自有代码、固定 catalog、定向测试和文档；可运行 fake Docker/perf 程序、短本地合成进程及现有 venv 的封网测试。单测试自有子进程 wall ≤5s、CPU 目标 ≤1s，单测试命令 ≤60s，超时停止并 reap。

禁止真实 Docker（含查询）、perf（含版本/权限探测）、网络、模型、生产凭据、安装/拉镜像、系统配置修改；不运行实际 Django 测试。旧 raw/reports/approval/marker/references 保持原字节；不创建实际 CPU-02 approval/attempt，不提交 Git。

## 4. A 一次完成的实现

### A1 先固定测量边界，再写入口

在交付中列一张边界表：镜像启动/环境准备/补丁应用/测量起点/官方 eval_script/测量终点/官方解析/清理。准备阶段不纳入 eval CPU 窗口；eval_script 内已有步骤则如实包含，不能为了缩短执行而自行删除。

默认选择：**宿主 perf attach 到本批容器内暂停的 eval supervisor 对应的宿主 PID**，随后 supervisor exec 官方脚本，继承范围需核实。不能采集 docker CLI 客户端后声称采到了容器；不能把容器 PID 直接用于宿主 `/proc` 或 perf。

必须形成以下证据链：本批容器 ID/标签 → pid namespace 身份 → 容器内目标 PID/starttime → 宿主目标 PID/starttime → perf 目标 → eval 起止事件。仅检查容器 init PID 不足以确认另一个 exec 进程。映射不唯一、身份变化或 namespace 不匹配即停止，不能猜 PID。

采用等待屏障：目标先就绪并等待，完成 PID 映射与 perf 就绪确认后才释放工作。`Popen` 成功或睡固定时间不能证明采样已就绪。A 依据已有本地文档/源码登记可实现的控制/确认协议；若当前 perf 不支持该方法，明确提出替代方案交回评审，不能悄悄切成全机采样、添加特权或安装 perf 到镜像。

### A2 单次生产调用链

计划/完整身份 → 新批准与独占 attempt → 固定本地 endpoint/context/digest 预检 → 新容器 → 既有官方准备及 candidate 应用 → 暂停目标/映射/采样就绪 → 资源基线与释放 → 官方 eval → 停采/末边界 → 官方解析 → 保存符号依据及报告 → 归档 → 身份限定清理。

要求：

- 默认计划无副作用。独立 `reports/cpu/CPU-02/` namespace；完整身份包含代码、配置、record、candidate、镜像、解释器、evaluator、目标/采样命令。旧批准不能放行，不能把旧数据的 ID 当本次 run ID。
- 一个正常容器，network=none、pull=never；不挂 Docker socket、不加 privileged、host PID namespace 或新 capability；perf 保持宿主执行。若权限不够，记 unavailable 停止，权限扩大需新批准。
- 宿主 PID 与容器 scope 分开记录。perf 继承到哪些线程/后代、何时 attach、提前退出/遗漏等必须声明。容器 CPU 边界是共享 scope 证据，不是逐函数 CPU 秒数。
- `ResourceSampler` 复用本机 reader，采样周期0.2s；记录原始边界与样本、计数 reset/missing，正式 I/O 保持 null+原因。
- 官方 verifier 复用既有 patch/apply/eval/parser 语义。`resolved=false`、基础设施失败、采样不可用、归档失败、清理失败独立记录；不能为通过而替换补丁或修改测试。
- record 仅 cycles@99Hz，无 callgraph。保持 raw perf.data；派生函数表为 period 加权 Self overhead，不是 sample-count 比例。裸地址、[unknown]、已命名符号分别计行数和显示权重；分母及舍入说明明确。
- **符号解析必须在容器删除前准备好依据**：记录被采样 binary/library 的容器路径、版本/build-ID（能取则取）、与解析使用文件的对应关系。不能用宿主同名 Python 库冒充镜像库。仅允许从本批容器只读取必要文件到受保护批目录，禁止下载 debuginfo；受产物阈值约束。不足则符号 partial，保留原始地址，不硬凑函数名。
- 同一绝对 deadline、工作/清理预留，正常退出也核查自有进程组；杀 perf 客户端不等于停止容器工作负载。容器与宿主收尾独立尝试，不能因报告错误跳过清理。输入/输出哈希、失败阶段与局部证据均归档。

### A3 最低定向回归（不设测试数量指标）

| 类别 | 必须通过的实际路径反例 |
| --- | --- |
| 门禁 | 默认无副作用、缺/旧批准、身份漂移、一次性登记、输出逃逸 |
| 目标映射 | 容器 PID ≠ 宿主 PID；映射歧义、PID复用、错误namespace均拒绝；不采docker客户端 |
| 屏障 | worker已等待→映射→perf真实协议应答→释放；缺应答不得启动eval；不是mock一个ready=True |
| 执行/解析 | fake runtime+fake perf经过实际入口/采样/归档；真实官方parser可用合成日志测试；resolved=false与infra_failure分开 |
| 计量/符号 | cgroup边界缺失/reset；空采样、裸地址、未知符号、宿主同名但身份不匹配的binary，不得虚报完整热点 |
| 收尾 | 启动响应丢失、采样先退出、目标超时、正常退出遗留后代、阈值中断、归档错误，均留证并清理本批资源 |

测试只替换外部环境，不绕过关键映射/屏障/判定函数。A 可以缩小合成负载，不能改 B 的真实 workload。只跑定向及受影响回归，不重新 discover 全历史测试。

## 5. B 预算提案（不是授权）

一次批次、最多一个顺序容器、一次 eval 和一次 record；没有模型、stat、额外基准/对照或自动重试。

| 项 | 提案 |
| --- | --- |
| 批 wall | 300s，含预检、准备、解析、归档及正常清理；保留30s清理 |
| 容器 | ≤4CPU / 8GiB；固定arm64 digest，network none，pull never |
| 准备 | ≤60s；已有离网准备失败不自动联网补装 |
| eval与采样窗口 | ≤120s；采样 cycles@99Hz，仅登记目标及其允许继承范围 |
| 单控制操作 | ≤15s且不越阶段/总剩余预算；长eval使用登记eval限额 |
| 产物 | 本批目录100MiB检测停止阈值（含perf.data、符号副本、日志）；没有绝对磁盘配额 |
| 结束 | 失败即停；不补采、不换事件/任务/补丁、不重跑Agent |

登记预检逐项列表与唯一命令后由用户批准。PMU attach/容器映射/符号可用性是 B 的运行期待测，不因 CPU-01 成功自动通过；但真实环境尚未运行不是 A 缺陷。缺少上述生产接线或可验证协议才是 A 阻塞。

## 6. 交付与停止

实施时创建 `docs/cpu_02_delivery.md`：选段理由、边界表、复用/修改范围、函数→反例→证据字段映射、实际测试、完整机器可读身份、B唯一已实现命令、预算/预检/权限需求、所有运行期未知项。

`user_approval=pending`、`tool_execution_permission=pending`。A完成即停，交回原评审集中验收；不创建批准/attempt。不得用猜测命令填交付。B另批后结果只支持这个Verifier执行段，不声明完整Agent热点、CPU架构建议或G2通过。
