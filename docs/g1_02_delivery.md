# G1-02 A 集中修复交付与 B 准备

2026-09-15。状态：**A_OFFLINE_VERIFIED / B_EXECUTED_ONCE / REVIEW_ACCEPTED**。本记录取代此前 A-PARTIAL 的交付声明；不把此前声称通过的测试当成本轮证据。B 已按用户批准单次执行，实际结果见 §6；后续集中裁定为 G1 登记小闭环范围通过，详见 [评审 §0](g1_consolidated_review.md)。不外推全部平台或 workload。

## 1. 实际修改

- `runners/g1_02_entry.py`：只保留一个生产编排；默认计划、双旗标、完整批准身份、原子 attempt、同进程本地 Docker 环境、共享 deadline、独立清理与归档。删除未被其他模块调用的旧 G1-02 `run_synthetic_batch`/重复校验辅助路径；测试只注入 runtime、预检及短 catalog。
- `scripts/g1_02_controller.py`：同步请求分别经过共享 hook；严格检查 run/service/PID/starttime/请求 ID、事件顺序与终态；服务及 12 个 ON/OFF 区间复用宿主 ResourceSampler/HostProcessMonitor。
- `scripts/g1_02_worker.py`：所有事件带相同身份；同步请求记录工作 CPU；使用独立闭式 checksum 对照迭代结果。
- `workload_catalog/g1_02.yaml`：实际驱动工作量、周期、条件及门槛。修正 YAML ON/OFF 键/值被当成布尔值的问题，JSON 身份 round-trip 已验证；补明确的预注册诊断公式。
- `tests/test_g1_02.py`：26 项短离线回归。生产入口一路走到底，fake 只替换 Docker 与计数输入，不预填 PASS；150,000 次短 fixture 不冒充正式 20,000,000 次计量。
- `workload_catalog/g1_02_identity.json`：机器可读的最终 B 拟批准身份（不是 APPROVAL）。包括全部 48 个包文件及 worker/controller 的 50 个代码 hash、catalog、配置、解释器、镜像。

共享 runtime/hook/collectors、历史 RUN-01/RUN-02、旧 raw/reports/approval/marker、references 未修改。不提交或推送 Git。

## 2. 四组关闭证据

| ID | 实际实现 | 定向回归（`tests.test_g1_02.G102Tests`） |
| --- | --- | --- |
| G102-1 | controller 的 SyncEnvironment 经现有 wrap_environment；两个 sync 各 open/closed；service scope 基线/末界；每条 worker 事件即时 flush | `test_real_entry_complete_chain_once_and_env`、`test_wrong_id_retains_raw_and_error_hook`、`test_missing_cpu_service_cannot_pass` |
| G102-2 | config 直接传 controller；ON 在 selector 循环中周期调用已有 sampler/host，OFF 仅边界；每区间 host 原始快照、process CPU、RSS、cgroup 样本及读耗时；checksum/CPU reset/缺失/充分性检查 | `test_compare_missing_reset_latency_checksum`、`test_short_comparison_can_be_inconclusive_without_mechanism_failure`；完整链路断言实际工作量校验和、ON 有读/OFF 无周期读 |
| G102-3 | 主入口一次 deadline 覆盖预检/执行/正常清理；操作取剩余且≤15s，job/window 共享≤8s；stop 与 verify 分别取剩余；pending 消费；资源证据先落盘再删容器 | `test_preflight_shared_deadline_and_local_env`、`test_stop_then_verify_recompute`、`test_pending_lost_create_consumed`、`test_hang_deadline_and_cleanup`、`test_boundaries_archived_before_remove` |
| G102-4 | local_docker_environment 同一作用域包围预检和 runtime 并恢复；双门/独立一次性身份；逐级 symlink/保护根/独占写入；协议期间检查报告阈值；hash 写后回读 | `test_single_flag_no_probe`、`test_approval_drift_and_old_approval_refused`、`test_preflight_failure_marker_no_runtime`、`test_paths_symlink_existing_and_protected`、`test_threshold_stops_in_protocol`、完整入口测试 |

额外失败回归覆盖：采集异常、空输出 rc=0、未确认清理、过期预算、manifest 写失败、证据落盘失败、已有目录、软链接批准。均在真实编排的相应接口注入，不调用 Docker。

## 3. 实际验证

```bash
PYTHONPATH=src python3 -B -W error::ResourceWarning -m unittest \
  tests.test_g1_02 \
  tests.test_coding_pilot.Round5StopChainTests.test_should_stop_interrupts_execute \
  tests.test_coding_pilot.Round6PipeDrainTests.test_large_output_completes_without_timeout \
  tests.test_coding_pilot.Round6PipeDrainTests.test_output_limit_applies_on_normal_path
```

29 项通过（G1-02 26 + 共享 runtime 相关 3），项目内约 2.7s；项目外 `/tmp` 使用绝对 PYTHONPATH 同样核对。后两项用本地假 docker 可执行脚本，不访问 Docker。AST 编译解析、真实 catalog 计划、identity JSON round-trip 与 `git diff --check` 通过。未安装 formatter 或其他依赖。

最终核验：拟批准 identity 与实时 build_plan 完全相等；252 个本地文档路径引用可解析；真实 approval/marker 均不存在。与前轮仓库整理基线相比，325 个既有保护文件中仅本轮授权的 7 个 G1-02 文件（entry/controller/worker/test/catalog/handoff/delivery）改变，其余 318 个哈希不变。新增 identity 文件是拟批准输入，不是运行证据或批准。

测试不证明真实 Docker 支持性、镜像在本地、正式 6 对充分性或性能优劣。没有运行 formal 20M × 12、模型、网络、READY/smoke、真实权限查询。

## 4. 固定测量定义及限制

正式值仍为 20,000,000 次整数循环，2 个同步请求/2 个异步 job 各 1,000 次或取消屏障；6 对交替 ON/OFF，周期 0.2s。checksum 依据 `sha256(str((3*n*(n-1)//2) & 0xFFFFFFFF))`，闭式计算不运行正式工作量。

- 两条件都读开始/结束边界并保持同样握手；ON 额外周期读，OFF 不读周期样本。周期由宿主 selector 循环调度，不再创建后台采样线程；记录实际间隔，不声称精确 0.2s 定时。
- 比较主量为宿主 bracket wall 的配对差（含边界/collector/control 工作，排除 worker 启动与最终归档），保存全部 6 对、median/range。worker process_time 是工作代码段；cgroup 是包围区间，二者不称同纳秒区间。
- 宿主每区间有 `/proc` 原始快照、RSS、tick delta 与 `process_time_ns_delta`；范围为 orchestrator 本进程含线程，不含 Docker CLI 后代，不宣称全 collector 成本。
- 每 ON 区间至少 2 个周期样本；worker CPU 至少 0.05s（用途上避免极短代码段）；边界读最大 0.25s（预注册可接受延迟，不是机器精度）。不满足保留 inconclusive。
- 跨源 CPU 诊断 allowance = `2/CLK_TCK + cpu_limit * max(0, cgroup_bracket_wall - worker_work_wall)`。两 tick 反映观测粒度，额外 bracket 时间按配置核心上限计入允许差；这不是保证覆盖所有系统误差的上界。超过 allowance 为 inconclusive，不为通过改公式。
- mechanism PASS/FAIL 与 comparison sufficient/inconclusive 独立；短 fixture 正常 inconclusive，不伪装为 B 测量通过。B 允许 PASS + inconclusive，一次即停，不追加样本。
- v1 block I/O 正式 null，原始诊断字段可保留；shared scope 不分摊独占工具 CPU；宿主时钟假设为 native Docker 无独立 time namespace。
- 20 MiB 是报告检测阈值，协议循环检查后停止，允许检测间隔超调；最小失败证据不因阈值丢弃。容器无磁盘 quota，不因本批增加。
- 正常清理在总预算内；耗尽后的安全清理每次至多 0.1s，显式 overrun/FAIL，未确认删除保留而非声称无残留。不清理无关容器。

## 5. B 最终身份与准备状态

完整身份见 [g1_02_identity.json](../workload_catalog/g1_02_identity.json)，实时 `build_plan()["identity"]` 必须与其 `identity` 完全相同。任何代码/配置/解释器变化后必须重新登记清单，不自动更新批准。

唯一实际入口命令与具体批准顺序见 [任务书 §7](g1_02_handoff.md#7-b-最终待批准执行清单)；复制用 [B 提示词](g1_02_execution_prompt.md)。

`user_approval=pending`，`tool_execution_permission=pending`。本次仅完成 A 离线实现并准备 B，真实 G1-02 APPROVAL/ATTEMPT 未创建。完整 G1 不因本交付自动通过。

## 6. B 单次执行记录（2026-09-15）

本节为实际运行证据，仅追加；§1–§5 保留 A 交付时点历史。授权状态更新：`user_approval=granted`（批准人 lcq，`approved_at_utc=2026-09-15T09:32:43Z`，批准原话「批准，执行 B」，完整记录于 `reports/resource/G1-02/APPROVAL.json`，`checklist_identity` 为核对一致后的完整 identity 复制）；`tool_execution_permission` 已对唯一命令行使一次。

### 6.1 执行与预算

- run_id：`G1-02-20260915T093254Z-94bb0ee7`；批目录 `reports/resource/G1-02/G1-02-20260915T093254Z-94bb0ee7/`。
- 实际命令（与任务书 §7.1 逐字相同）：`PYTHONPATH=src /usr/bin/python3.11 -B -m agent_workload_characterization.runners.g1_02_entry --execute --i-approve-the-g1-02-b`。
- 返回码 `0`，`detail=mechanism_PASS_comparison_sufficient`；`ATTEMPT_STARTED.json` 由 started（09:32:54Z）更新为 `completed`。
- 执行前门禁：实时 `build_plan()["identity"]` 与 `workload_catalog/g1_02_identity.json` 的 `identity` 逐字段完全一致后才创建批准；当时 `reports/resource/G1-02/` 不存在，无旧 APPROVAL/ATTEMPT/marker，未覆盖或复用任何旧批准。
- 预检（同一进程 `local_docker_environment`，`unix:///var/run/docker.sock`）：`PREFLIGHT.json` status=READY，context/image 检查通过，固定 arm64 digest 与登记一致。
- wall：summary `wall_s=19.69`（预算 300s，`budget_overrun=false`）；两用例共享同一绝对 deadline。
- 清理：两容器均 `removed`，`cleanup_pending` 无残留，无 overrun，未触碰无关容器。

### 6.2 用例结果

| 用例 | 状态 | 容器（cleanup） | 关键证据 |
| --- | --- | --- | --- |
| service | PASS | `7870b6eb…`（removed） | 同一 worker PID=7：ready → 2 次同步请求（各有独立 open/closed hook，`service.tool_events.jsonl` 4 条）→ job1 submitted→started→poll=started→proceed_ack→finished=completed→wait=completed → job2 submitted→started→finished=cancelled→wait=cancelled → closed；`service.evidence.json` 16 条原始事件、service scope 资源边界 |
| overhead | PASS | `296b6a28…`（removed） | 12 区间按 OFF,ON,ON,OFF,OFF,ON,ON,OFF,OFF,ON,ON,OFF 交替；ON 每区间 7 个周期 tick、OFF 0（无周期读）；12 区间 `work_checksum` 完全一致；worker_cpu 1.487–1.492 s（≥0.05 s 门槛）；边界读延迟最大 0.00033 s（≤0.25 s 上限）；CPU 跨源诊断 12/12 在预注册 allowance 内 |

### 6.3 比较结果（不外推）

`comparison.sufficiency=sufficient`（reasons 为空）。6 对宿主 bracket wall 配对差值（ns）：`[773961, 1898086, -2394031, 1041613, -2069436, 3621388]`；median `907787 ns`，range `[-2394031, 3621388]`。其中 2 对为负差值，按预注册语义保留为噪声/干扰，不称"负开销"。median/range 是本机、本协议、本单次批的描述量，不构成稳定 overhead 百分比，也不能外推为所有 Agent 的通用性能阈值。

### 6.4 归档与哈希

`archive_status=complete`。`manifest.json` 含完整输入 identity（50 个代码 SHA、catalog_sha256 `abee7720…1888a`、config、解释器、镜像 digest）与 6 个输出文件的 bytes+sha256，写后回读校验通过；manifest 不自哈希。输出文件：`service.events.jsonl`、`service.tool_events.jsonl`、`service.evidence.json`、`overhead.events.jsonl`、`overhead.evidence.json`、`summary.json`，合计约 597 KiB（低于 20 MiB 检测阈值）。原始 raw、历史报告、旧 approval/marker、references 未修改；未提交/推送 Git。

### 6.5 缺失与限制

- 正式 block I/O 为 null（cgroup v1 降级不变）。更正说明：12 个区间 resource baseline 均带 `baseline_cpu_unreadable:None` note，此前本节把它解释为"基线 CPU 计数不可读"是错误的——原始边界 CPU 实际有值（`cpu_usage_usec`，read_status `cpuacct.usage=ok_ns_converted_to_usec`）；该 note 是 sampler 对 cgroup v2 键 `cpu.stat` 的 read_status 检查在 v1 环境下键不存在（返回 None）时产生的误导性输出，不是本次 CPU 测量缺失。封存报告按原字节保留，未修改。
- CPU shared，无独占 Tool CPU；宿主 process CPU 为编排进程含线程、不含 Docker CLI 后代，读取耗时单列。
- 单次批、固定 20,000,000 次循环，无预热、无补跑、无自适应调整；本批 sufficient 不改变"inconclusive 亦合法"的预注册政策。
- 时钟假设：同主机 CLOCK_MONOTONIC anchor、native Docker 无独立 time namespace（summary `clock_anchor` 原样保留）。
- 完整 G1 判定仍由原评审针对实际覆盖决定；本交付不宣称完整 G1 通过。
