# G1-01 B：无模型容器采集链验证

日期：2026-09-13。状态：**执行任务书已准备；仅可先离线组装，容器执行待用户批准最终清单。**

配套：[给实施模型的提示词](g1_01_b_execution_prompt.md)。遵循“任务书与提示词 → 用户交实施模型 → 原评审核验”。本文件不授予容器操作权限；双旗标也不能代替用户授权记录。

## 1. 本批目标与已验收边界

G1-01 A 已通过功能与离线证据复核：420 项默认测试、5 项 mini 离线集成；单 scope 停止等待在途读取、锚点数量不一致禁用校准、C1 仅不同窗口的诊断对照。

本批只验证新增采集链在真实容器上的行为：真实工具 hook → 容器计数器窗口 → 宿主进程观测 → 停止与末边界。使用 SWE-bench Django 已有镜像作环境载体，**不是执行 SWE-bench 任务**，不运行 mini Agent loop、模型、candidate、gold patch 或 verifier。

A 最新依据：`reports/resource/G1-01-A/G1-01-A-R4-20260913T085846Z/`。历史 C 数据仍为 `data/raw/generated/RUN-01-C/20260912T125202Z-840e49/`；其 26 次工具的真实 duration 与宿主 CPU/RSS 缺口不回填。

历史更正注意：R3 manifest 实际有 `files` map，缺陷是 `summary.md` 登记哈希过期，不是缺少整个 map。首批审批文件已按原哈希恢复。只在新交付追加准确说明，保留 R3/R4 原件及已知缺陷；不得重封存伪装历史完整。

## 2. 阅读与复用

完整阅读 methodology.md、docs/development_tasks.md、references/README.md、references/manifest.yaml；再读 trace_contract.md、data_management.md、g1_01_handoff.md、g1_01_delivery.md、R4 报告与 container_validation_approval.md，以及本任务书。

重点复用 mini_agent_adapter.py、container_runtime.py、resource_sampler.py、host_process.py、semantic_recorder.py、现有 canary 停止链及相关测试。不要重跑旧 canary 入口：它的用例、预算与副作用不等于本批。

当前 ToolEventRecordingEnvironment 嵌在 mini 子进程代码中。允许最小抽取为共享实现，由原 mini 路径和 B 入口共同调用；保留现有事件语义和回归。**不复制第二套 hook，不用手写事件冒充真实 hook，不为了取得工具事件而启动 Agent/model loop。**

## 3. 分两步执行，权限不混用

### B0：离线组装与命令登记

用户转发提示词并要求实施后，可修改自有入口/共享 hook/合成测试/新文档。默认计划模式不调用 Docker，不能读取密钥、联网、安装或运行容器。使用 fake runtime 与现有封网 SDK 集成检查真实复用关系。

入口建议放在现有 runners 包内，名称由实施者确认；本任务书不提供尚不存在的可执行命令。实现后登记真实解释器、模块、argv、工作目录、代码与配置 SHA、固定镜像、用例脚本 SHA、预算、报告目录和授权状态。实跑计划模式与单旗标拒绝路径（均离线）。

B0 一次合并完成，不逐文件申请；只修本批必需接口。最终命令必须同时有执行开关和明确确认开关，缺任何一项拒绝副作用。B0 完成后交付并停止，等待用户针对最终清单批准。

### B1：用户批准后，一批一次即停

批准应明确指向 B0 最终清单及身份。只有此后才允许本地 Docker 只读预检及最多两个顺序容器。审批后如用例/镜像/预算/执行代码改变，停止重新登记，不偷偷修正后续跑。

失败保留原始结果，不自动重试、不新增 r2、不换命令补测；未执行的后续用例标 skipped。安全清理仍须进行。完成后交回原评审，不自动宣布 G1 通过或启动第二次真实任务。

## 4. 固定环境与预算（最终批准清单必须逐项复述）

| 项目 | 上限或约束 |
| --- | --- |
| 镜像 | `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2` |
| 来源 | 仅本地已有镜像，禁止 pull/build/install；缺失或架构不符即停 |
| 容器 | 最多 2 个，严格顺序，每个 ≤2 CPU、256 MiB；network none |
| 批 wall | 180 s，从首次本地 Docker 预检前开始，到正常清理结束；内部所有等待取剩余时间 |
| 执行预留 | 停止/清理预留至少 30 s；剩余不足时不开始下一个用例 |
| 单命令 | 常规命令 ≤20 s 且不得越批剩余；后台 busy 被允许存活 ≤5 s |
| 合成文件 | 第一容器仅 `/tmp/g1b.bin` 8 MiB；本批合成文件写入总量 ≤16 MiB，不等于总块 I/O |
| 宿主受测子进程 | 最多 1 个自有确定性短程序，无 busy loop/数据文件，存活 ≤5 s；不运行 Agent |
| 新报告 | `reports/resource/G1-01-B/<batch_id>/` 独占创建；20 MiB 检测阈值，越限停机、保留最小失败证据 |
| 测试 | B0 默认套件单次 timeout≤60 s；显式封网 SDK 套件≤60 s，实验不混入默认测试 |

沿用降级：主机 cgroup v1；正式 block I/O=null + degraded_host_v1_blkio，原始值仅 diagnostic；容器可写层无磁盘配额，不再探测 storage-opt。不宣称写入预算/报告阈值是容器总磁盘硬上限。

禁止远端 DOCKER_HOST/context、host 网络、privileged、Docker socket/宿主数据挂载、宿主 cgroup 改动、提权、perf/eBPF、代理/凭据环境转发。显式使用本地 Docker socket，不能继承远端路由。

## 5. 容器 1：真实 hook 与资源窗口

通过共享 ToolEventRecordingEnvironment → AttachedDockerEnvironment → 本地 Docker 执行四条命令，不直接调用 Docker 绕过 hook。为每次调用提供唯一合成 tool_call_id，不伪装模型 request_id。工具调用次数固定为 4。

```sh
sleep 1
dd if=/dev/urandom of=/tmp/g1b.bin bs=1M count=8 && sync && rm -f /tmp/g1b.bin
false
python3 -c "x=sum(range(2_000_000))"
```

它们是四次独立 execute，不合并成一个 shell；第三条 rc!=0 是预期工具结果，不是批次基础设施失败。其余任何命令错误均失败即停。仅删除本次明确创建的 `/tmp/g1b.bin`，不扩大清理路径。

必须保留与断言：

- 四组 open/closed 配对、ID 唯一、rc 分别为 0/0/非零/0；closed 表示调用返回，不等于成功。
- 睡眠调用仍运行时，由父进程读取已落盘 open，记录读取时刻与调用尚未完成的证据。不能只在结束后检查行顺序来证明 open 事先持久化。
- 同机 monotonic 起止、时钟来源；sleep 窗口不短于请求睡眠时长，若不符保留失败，不调阈值。
- 容器 baseline、样本、末边界与 read_status 全量保留。CPU scope 增量可用、单位正确；短 CPU 命令可能无内部采样点，允许 coverage=0/partial，不插值造独占 Tool CPU。
- 工具窗口仅 shared_scope 关联。setup/collector/其他容器工作可能包含在容器计数中，不要求每个工具都出现正 CPU 增量。
- 工具事件不含完整命令、输出、环境或异常原文；允许本任务书与固定用例脚本保存已审查的合成命令。

## 6. 容器 2：后台工作、宿主采集与停止边界

经同一 hook 启动预登记的后台 busy 脚本。脚本须将 stdin/stdout/stderr 从 exec 管道断开，保存本次后台 PID/身份，并让调用及时返回；B0 登记准确脚本，不能照搬可能继承管道而卡住的裸 `nohup ... &`。

在 ≤5 s 的窗口中取两次容器 CPU 计数，证明工具已经返回但后台仍工作；随后使用已有 terminate_workload。不为得到特定停止分支重试。

宿主观测并行覆盖 host_runner_process（含 collector）及本批自建的一个短子进程，记录 PID+starttime、实际 CLK_TCK/页大小、原始快照、首末可读窗口、CPU/RSS 与采集读耗时。短子进程仅作宿主采集载体，不是 mini；不得声称已测真实 Agent host runtime 或容器进程 CPU。无需扫描无关进程/environ。

停止链按实际三分类：

- stopped_confirmed：容器仍存活；采样 stop 等待在途读取，取末边界，然后才拆除。
- stopped_via_docker_stop：容器 EXITED；若 cgroup 已消失，末值 null+原因，最后可读值只作诊断。
- stop_not_confirmed：批次失败，报告仍可能有工作负载，不宣称清理成功。

stop(scope) 返回后保持后台采样循环至少两个预登记采样周期，核对该 scope 的 reader 次数/样本数/末边界冻结，再停整个采样线程。不能把“全局线程停了”当单 scope 冻结证据。

不要求本批两个停止分支都发生；另一分支可引用已验收 RUN-01-B canary 证据并注明旧代码身份，不冒充本批新增采集链实测。

## 7. 控制、清理和失败交付

复用 Popen 排空/输出帽、剩余 wall、容器停止确认与 finally 清理。父进程 watchdog 必须能打断阻塞执行；不能仅事后检查用时。到限终止本批工作并进入清理，若清理超过预算或 Docker 不响应，如实记录实际 wall/残留，不藏超时、不继续测量。

仅清理本次实际创建且 container ID 与 run_id/name/label 对得上的容器；宿主子进程同样按本次 PID+starttime。禁止全局 prune、宽泛 pkill 或前缀批量删除历史容器。第一次拆除前归档最后可读证据；最终清理状态再纳入 manifest。

输出守卫在容器创建前检查：可信项目根、catalog 旧源根与 references 保护、路径段 symlink 拒绝、批次独占创建。不得读取用户密钥来做扫描；以离线 canary 与安全字段投影检查新产物。不输出完整 docker inspect/env/第三方 traceback。

## 8. B0 最低离线回归与最终审批登记

最低覆盖六组，可扩已有测试而不造新框架：

1. 默认计划零 Docker/网络副作用；单旗标拒绝；固定镜像与预算漂移拒绝。
2. 原 mini 与 B 复用同一 hook；调用尚未完成时 open 已可读；非零 rc 保留 closed/error 真实语义。
3. 超时/后台管道断开/停止确认/末边界/先归档后清理，注入失败仍交付。
4. 单 scope 在途读取与停止交错，停止后冻结，不能只关闭全局线程。
5. 输出保护、秘密 canary、未知不补零、I/O 正式降级。
6. manifest 写最后，全树列举；回读对账覆盖 mismatch/missing/unlisted，摘要写完后不得再偷偷修改。

审批登记至少包含：实际可运行命令与解释器、双旗标、代码/配置/脚本 SHA、两容器准确 argv/命令序列、实际监控周期、每步 deadline 与清理预留、host 子进程规模、磁盘降级、批准记录位置。记录“B_user_approval=pending”，不代签。

## 9. B1 交付与验收边界

新包至少包含 plan/approval 引用、工具事件、容器原始计数/样本、host_process 结构化证据、逐用例 checks、停止与清理结果、summary、manifest。文件可合并，不以文件数量作为成果。包含实际执行时间、代码/配置/镜像身份、每项 PASS/FAIL/PARTIAL/SKIPPED 及理由，输入输出 SHA/字节。

历史封存/v2/首批/R2/R3/R4 保持原件，R3 已知哈希缺陷单列，不把它算成本批新漂移。追加 R4 更正说明：R3 有 files map，仅 summary 哈希过期；不改写 R4 manifest。

更新 docs/g1_01_b_delivery.md、G1 六条证据与项目最新状态。默认及封网集成测试按实际执行报告，不复制旧通过数量。

验收只覆盖无模型真实容器采集链。不能证明真实任务宿主开销、独占 Tool CPU、稳定开销比例、生产代表性或 G1 全项通过。**B 完成后停止；任何新的模型/任务/容器批次另行批准。**
