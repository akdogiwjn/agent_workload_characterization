# CPU-01 A 交付：候选 scope 与 perf 可测性最小准备

2026-09-15 创建，2026-09-16 更新。状态：**A_REVIEW_FIXES_APPLIED_R2 / B_EXECUTED_ONCE**。A 经原评审两轮注入反例复核（四组 + 三处，见 §8/§9）修复重验后，用户批准并按 §5–6 清单执行了一次真实 B（见 §10）；授权状态现为 `user_approval=granted`（一次性）、`tool_execution_permission=used_once`。本交付不宣布 P2/G2 完成。

## 1. A1 候选 scope 表（只读 RUN-02 封存证据）

单一来源：RUN-02-R2（同一 `django__django-16485` task 的真实 attempt，`benchmark_real`）。单位照抄原字段；一个 task 的两个 attempt（RUN-01/RUN-02）不构成生产代表性，本批不增加任务样本。没有单工具 CPU 证据，**不做 Tool CPU 排名**。

| # | scope（run/scope id） | CPU 原字段（单位） | Wall | Memory | 证据 locator（run_id `20260915T012427Z-2d75aa`） | 有效性 | 选择理由 | 尚不能回答 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Agent 容器 `…-agent-sandbox`（`agent_container`） | `cpu_core_seconds=51.007123`（core·s，`cpuacct.usage` 边界差，`cpu_evidence=counter_boundary`） | `wall_s=143.651636264` | `memory_kernel_peak_bytes=1434140672`（cgroup kernel peak） | `reports/resource/RUN-02/20260915T012427Z-2d75aa/summary.json` → `resource_summary.scopes[0]`；raw `data/raw/generated/RUN-02/…/samples.json` | 有效（G1 评审已核 CPU 边界重算吻合） | CPU/Wall/Memory 三项全量最大的 scope，P2-01 单样本首要候选；后续真实工具 profiling 须另立清单 | 内部哪些工具/库占 CPU；共享容器 CPU 无法分摊给单工具；I/O 正式 null |
| 2 | Verifier 容器 `…-verifier`（`verifier_container`） | `cpu_core_seconds=3.64963` | `wall_s=12.264456124` | `memory_kernel_peak_bytes=72548352` | 同上 `resource_summary.scopes[1]` | 有效 | 短而集中的测试执行段；与 Agent 段分开列出，不合并为"全部 E2E CPU" | 同上；单次 verifier 运行的代表性 |
| 3 | mini 宿主进程 `host_mini_child`（PID 4062146+starttime 224132801） | `cpu_seconds=4.19`（s，`utime+stime` tick 差，**首末可读区间，非 lifetime**） | 观测跨度含 717 快照（716 可读） | `rss_current_last_readable=218214400`、`rss_sampled_max=226713600`（B，两者口径不同）；无进程级 kernel peak | 同上 `host_process.summary`；raw `…/host_process.jsonl` | 有效（区间语义，`final_read_status=process_exited`） | Agent 本体 host 侧可读区间候选；**不能与完整容器区间排同一榜** | 生命周期完整 CPU；短命后代覆盖不完整（已声明缺口） |
| 4 | 工具调用集合（28 个 native hook，`shared_scope` 关联） | 无 per-tool CPU（共享容器，不分摊） | wall min/median/max = 0.174/0.277/**14.611** s，合计 23.765 s | 无 per-tool memory | `…/mini_tool_events.jsonl`（28 open/28 closed/0 error）；派生 `summary.json` → `tool_timeline.records`、`trajectory_timeline.records` | wall 有效（`duration_evidence=native_hook_boundaries`） | 按 wall/频次选候选：最长的 14.611 s 调用与 0.4 s 量级常规调用是两类后续采样对象 | **不能据此排 Tool CPU 榜**；命令内容仅 sha256/length 安全投影（最长调用 heuristic_category=Read/Search，非语义分类）；P1-06 分类器未接线 |

候选口径与 G1 集中裁定 §0 一致：Agent 51.007123 core-s / Verifier 3.64963 core-s 为容器级满足项；独占 Tool CPU、函数热点、PMU、多任务排名明确不在本表。

## 2. A2 实际修改与复用

| 文件 | 性质 | 说明 |
| --- | --- | --- |
| `runners/cpu_01_entry.py`（新；修复轮修订） | 薄入口 | 计划/身份核验→单次批准与 attempt→同进程预检→stat→record→report 解析→独立归档→清理确认；默认零副作用；`--execute --i-approve-the-cpu-01-b` 双旗标，单旗标 rc=2；阶段状态分层（流程结束/计数有效/采样有效分判），先存证再抛错 |
| `collectors/perf_adapter.py`（新；修复轮修订） | 采集/解析 | stat/record/report argv 构造与输出解析；单一 run-time 列＋optional metric 尾字段、period 口径 report 分母、闭式 `expected_checksum`；不执行任何 perf |
| `scripts/cpu_01_target.py`（新） | 自有目标 | 固定整数循环（同 G1-02 闭式 checksum 家族），stdout JSONL 自报 PID+starttime；合成热点不冒充 Agent 热点 |
| `workload_catalog/cpu_01.yaml`（新） | 固定配置 | 事件、频率、argv 语义、预算、授权状态；`execution_authorized: false` |
| `tests/test_cpu_01.py`（新） | 定向回归 | 26 项，fake perf 可执行程序 + 短自有目标进程走实际入口/解析/归档/清理 |
| `runners/report_writer.py`（最小增补） | 共享修正 | 新增 `_guard_collection_root` 泛化与 `guard_cpu_root`/`guard_cpu_report`（`reports/cpu/<collection>` namespace 之前无 guard）；既有 `guard_resource_*` 行为逐字节不变，受影响回归通过 |

复用：`guard_resource_*` 同构的保护/独占写入思路、G1-02 的 deadline/cleanup_timeout/finish_marker 模式、`host_process.read_starttime` 身份语义。不复制 Docker 启动/清理框架，不创建服务框架，不改 G1 语义。历史入口、旧 raw/reports/references/批准/marker 未动；不提交 Git。

**perf 命令依据**（本地静态文档，未运行 perf）：perf-stat(1) CSV FORMAT 节与 `-o file`、`-x`；perf core shell 测试 `stat+csv_output.sh`/`stat+csv_summary.sh`/`perf_json_output_lint.py`（`<not counted>`/`<not supported>` 为合法计数值、CSV 字段序）；perf-record(1) `-F`/`-o`/workload 模式 `-- <cmd>`；perf-report(1) `--stdio`/`--no-children`/`-i` 及 arm64 测试 `test_arm_coresight.sh`/`test_arm_spe.sh` 的行格式样例。

**格式未决项（不猜测）**：本地 perf 6.x CSV 行的可选尾字段数与"一个还是两个时间列"无法仅凭文档确定——解析器按 man 字段序探测，两列时间（enabled/running/pct）与单列（run_time/pct）都保留原值并标注 `time_fields_interpretation`，绝不从百分比捏造 enabled/running；`perf report --stdio` 头部 `# Samples:` 行缺位时分母记 null。B 运行后按实际输出如实记录。

## 3. 生产函数 → 测试 → 产物字段映射

| 生产函数 | 离线反例测试（`tests.test_cpu_01.CPU01Tests`） | 产物字段 |
| --- | --- | --- |
| `main`/`build_plan` | `test_default_plan_no_subprocess_no_write`、`test_single_flag_returns_2`、`test_no_approval_returns_3`、`test_identity_drift_and_old_collection_refused`、`test_marker_exists_refuses_second_attempt` | `PREFLIGHT.json`、`ATTEMPT_STARTED.json` 状态、批目录 |
| `run_phase`（进程组/排空/预算/阈值/reap） | `test_phase_timeout_kills_group_and_reaps`（目标 started 后才触发超时，killpg+`/proc` 核验）、`test_phase_budget_is_not_summed`（阶段预算不与操作上限相加）、`test_no_popen_after_deadline`（预算耗尽不启动）、`test_threshold_aborts_growing_output`（增长期间中断）、`test_launch_failure_fails`、`test_big_output_bounded_no_deadlock`（>1 MiB 截断不死锁）、`test_drain_group_release_no_lingering_descendant`（管道持有者经组清理后才能完成） | `phases.*.{perf_pid,returncode,timed_out,threshold_aborted,drain_incomplete,stop_events,stdout_truncated}` |
| `parse_stat_csv`/`compute_ipc` | `test_stat_mixed_support_states`（not_supported/not_counted/missing/partial 四态并存）、`test_stat_zero_cycles_no_ipc`（真实零 ≠ 缺失，IPC 零分母另记原因）、`test_stat_metric_tail_not_second_time_column`（metric 尾字段不冒充第二时间列）、`test_parse_short_line_error`、`test_stat_parse_error_lines_not_complete` | `phases.stat.parsed.events[].{value_raw,value,unit,status,percent_running,run_time_ns,extra_fields}`、`phases.stat.ipc` |
| record 归档判定 | `test_record_no_output_rc0_not_success`（rc=0 无输出不得称成功）、`test_record_unavailable_archives_unavailable`（拒绝→`unavailable`，不重试） | `phases.record.{status,perf_data_present,perf_data_sha256,returncode,target_check}` |
| `parse_report` | `test_report_unknown_symbols`、`test_report_zero_samples`（header 明确 0 → 诚实零样本，complete）、`test_report_unknown_output_not_complete`（无 header 无行 → fail）、`test_report_no_header_denominator_null`（period 口径分母说明） | `phases.report.parsed.{evidence_status,total_samples,event_count_approx,rows,unknown_symbol_rows,zero_samples,denominator_note}` |
| 目标身份核对 `check_target` | `test_target_identity_mismatch_fails`（checksum/iterations 不符 → FAIL）、`test_stat_complete_chain_via_main`（ok 断言） | `phases.*.target_check.{status,problems,expected_checksum}` |
| 清理确认 `stat_survivor`/`stop_process_group` | `test_cleanup_survivor_cannot_pass`（同 PID+starttime 幸存→FAIL）、`test_stop_escalates_while_group_alive`（组空才停升级）、`test_survivor_permission_denied_is_check_failed`、`test_cleanup_check_failed_cannot_pass` | `cleanup.after_stat/after_record.{target_pid,status}`、`stop_events` |
| 守卫/归档/manifest | `test_paths_symlink_and_protected_rejected`、`test_symlink_approval_refused`、`test_success_and_failure_both_archive`、`test_archive_failure_writes_marker_file`、`test_threshold_stops_batch`、`test_budget_exhausted_fails`、`test_stat_complete_chain_via_main`（manifest 输入/输出 SHA 闭环，manifest 不自哈希） | `manifest.json`、`archive_failure.json`、`summary.json` |

## 4. 实际验证

```bash
PYTHONPATH=src python3 -B -W error::ResourceWarning -m unittest \
  tests.test_cpu_01 tests.test_g1_02 tests.test_run_02
PYTHONPATH=src:tests python3 -B -m unittest tests.test_preparation
```

- CPU-01 定向 **45 项**通过（首轮 26 项 + 评审修复两轮共 19 项，约 27 s，fake perf + 真实短目标进程，单子进程 CPU ≤1 s、wall 秒级；连续 3 轮无失败）。
- 受 `report_writer.py` 增补影响回归：`test_g1_02`（26）+`test_run_02`（10）通过；`test_preparation`（56）按其自身 `import test_skeleton` 假设需 tests 在 path（既有状况，与本轮无关）。
- AST 解析改动文件通过；真实计划模式 `main([])` rc=0 且零副作用（`reports/cpu/` 不存在，无 APPROVAL/ATTEMPT/marker）。
- 未运行：真实 perf（含 `--version`/权限/事件探测）、Docker、网络、READY/smoke/G1-02/Django、生产配置/密钥。测试不证明真实 PMU 可用性、符号可用性或正式比较充分性。

## 5. 完整身份与 B 唯一命令

完整拟批准身份由 `build_plan()["identity"]` 生成（51 个代码 SHA：`src/agent_workload_characterization/**` 50 文件 + `scripts/cpu_01_target.py`；catalog SHA `6c779676…`；interpreter `/usr/bin/python3.11` 3.11.6；target argv 与 20,000,000 次迭代；perf 二进制/10 个 stat 事件/record=cycles@99Hz）。批准必须绑定该 identity；`workload_catalog/cpu_01.yaml` 是配置真值来源。B 命令已离线验证（计划模式 rc=0；双旗标在无批准时 rc=3 有测试）：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src /usr/bin/python3.11 -B -m agent_workload_characterization.runners.cpu_01_entry --execute --i-approve-the-cpu-01-b
```

固定三次 perf 子命令调用（目标顺序、不同时运行）：`perf stat -x ';' -o stat.csv -e task-clock,context-switches,cpu-migrations,page-faults,cycles,instructions,branches,branch-misses,cache-references,cache-misses -- <target>`；`perf record -F 99 -o perf.data -e cycles -- <target>`（无 call-graph，仅符号级函数表）；`perf report --stdio --no-children -i perf.data`（离线解析，不运行目标）。无回退事件、无重试。

## 6. B 逐项预算、预检与终止规则

| 项 | 固定值 |
| --- | --- |
| 批 wall | 120 s（预检前→清理），预留 20 s；单操作 ≤15 s，超时 killpg 整组并 reap |
| 采集 | 1× stat + 1× record + 1× report 解析；目标进程顺序不同时 |
| 目标 | wall ≤10 s，20,000,000 次迭代（预期 CPU ≈1.5 s），自报 PID+starttime |
| record | cycles @ 99 Hz（≤99 Hz 上限内） |
| 产物 | 20 MiB 检测阈值，触发停止留最小失败证据；无绝对磁盘配额声明 |
| 副作用 | 不安装、不提权、不改 sysctl、不网络、不 system-wide、不 attach 无关 PID、不追踪无关进程 |

预检（同进程、不运行 perf）：① perf 二进制存在且 X_OK；② target 脚本存在；③ `/proc/sys/kernel/perf_event_paranoid` 仅读取记录（不据此判定成败——真实权限是运行期结果）；④ namespace/批准/marker 门禁。

终止规则：预检失败 → rc=4 停止；perf 运行期拒绝（stat/record 未跑 workload 即失败）→ 归档 `status=unavailable`、rc=0、`detail` 说明，不安装不重试；事件 `not supported`/`not counted` → 如实逐事件记录，stat 其余事件继续有效（软件事件不提升为硬件支持）；rc=0 但 perf.data 缺失 → `fail`（不得声称 profile 成功）；stat/record 非零 rc（含文件存在）、空输出、解析错误行、report 空输出/未知输出、目标身份（PID/迭代/checksum）不符 → 均 `fail`；任何启动/超时/阈值中断/清理未确认（`check_failed` 含）/drain 未完成 → rc=5，失败阶段证据先落盘再抛错；成功（rc=0 且 archive complete）仍须读 `summary.status`（complete/unavailable）与逐事件支持状态，不据此宣称 PMU 归因、Agent 热点或 G2 通过。

## 7. 缺失与限制

- stat CSV 可选尾字段与时间列数的本地文档歧义按 §2 未决项处理；B 真实输出为准，不预先假设。
- `perf report` 函数表的 Overhead 列是 perf 按 sample period 累加的 Self overhead（§8 组 2 修正口径），不是精确 CPU 时间，也不用 `# Samples:` 作分母换算；无 FlameGraph UI（不在本批）。
- collector 覆盖范围：宿主编排进程管理 perf+目标进程组；`perf` 后代（如 record 的内核侧）不单独计量；G1-02 的 0.9 ms 配对中位数不可用作 perf 误差界或开销扣除。
- 合成目标的热点与开销是机制证据，不是 Agent workload 证据；容器内 PMU 归因（候选表 #1/#2）须另立清单与授权。
- PMU 权限、硬件事件可用性、符号/unwind 可用性均为 B 运行期未知项，本 A 不阻塞、不伪造。

## 8. 评审修复轮（2026-09-15，四组一次修完）

原评审对首轮 A 注入离线反例复核，判定"失败仍判 complete、perf 字段解释错误、预算与阈值未落实、停止确认不足"四组实质问题；A 暂不能验收、B 不放行。本轮一次修完，全部经实际入口反例验证：

| 组 | 评审注入复现 | 修复 | 反例测试 |
| --- | --- | --- | --- |
| 1 失败不能 complete | stat 空文件 / report 空输出 / report rc=7 / stat rc=7 且文件存在均判 complete | 状态分层：`empty_output`、`nonzero_rc_with_output`、`nonzero_rc_no_output`、`parsed_with_errors`（含 parse_error 行）、`rc0_output_missing` 均不得 complete；complete 仅限 stat=`parsed`＋record=`data_present`（rc≠0 不再算）＋report=`parsed`；`data_with_nonzero_rc` 降为 fail。目标完成改为 `check_target`：started/done 同 PID、迭代数等于登记值、checksum 等于闭式 `expected_checksum`，任一不符 → `target_identity_mismatch`。零样本（header 明确 0）与未知输出（无 header 无行）由 `evidence_status` 区分：前者是诚实的零样本 profile，后者 fail | `test_stat_empty_output_not_complete`、`test_stat_nonzero_rc_with_output_not_complete`、`test_report_empty_output_not_complete`、`test_report_nonzero_rc_not_complete`、`test_report_unknown_output_not_complete`、`test_target_identity_mismatch_fails`、`test_stat_parse_error_lines_not_complete` |
| 2 perf 字段解释 | `4000000;;instructions;150123000;100.00;2.00;insn per cycle` 被误读为双时间列（running=100ns、2%） | 删除凭数值推断第二时间列的逻辑：按 perf-stat(1) 只有一个 run-time 列＋percent，其后视为 optional variance/metric value/unit 原样保留（`extra_fields`），`time_enabled_ns`/`time_running_ns` 仅在真实存在时记录否则 null；metric-only 行独立状态。report 分母口径修正：Self overhead 是按 period 累加（`denominator_note` 明示），`# Samples:` 不再被当作百分比分母，另存 `event_count_approx`（header 提供时）；不明确字段保留 null/unknown | `test_stat_metric_tail_not_second_time_column`、`test_report_no_header_denominator_null`、`test_stat_complete_chain_via_main`（event_count_approx 断言） |
| 3 预算与阈值 | 超时上限为 target_wall+operation 之和（登记 10 s 实际可到 25 s；限额 0.05 s 跑 0.316 s 未判超时）；deadline 已过仍 Popen；20 MiB 只在阶段末检查 | `run_phase`：启动前 `remaining()` 检查（预算耗尽不再启动）；轮询循环分别执行共享 deadline、本阶段独立预算（stat/record 用 `target_wall_s`、report 解析用 `operation_s`，取 min 语义不叠加）、mid-phase 阈值回调（产物增长期间即中断并标记 `threshold_aborted`） | `test_phase_budget_is_not_summed`（0.05 s 限额 ~0.05 s 中止）、`test_no_popen_after_deadline`（Popen mock 断言未调用）、`test_threshold_aborts_growing_output`（文件增长期间中断） |
| 4 停止确认与失败证据 | perf 主进程退出即停升级信号；/proc 读取被拒绝误报 exited；report 超时丢失阶段证据 | `stop_process_group` 每级信号等待 perf 退出**且进程组空**（`killpg(pgid,0)` 探测）才停，否则升级 SIGKILL 并留 `group_alive_after_wait` 证据；`_survivor_check` 区分 `exited`（FileNotFound）/`exited_zombie_pending_reap`/`check_failed`（PermissionError 等读取失败，不冒充 exited），任何非确认状态不能 PASS；drain 线程 join 后检查存活，持有管道的后代通过组级 SIGKILL 清出，`drain_incomplete` 不得 complete；report 等阶段先写 `report_raw.txt` 并存 `payload['phases']` 再 raise，失败阶段证据保留 | `test_stop_escalates_while_group_alive`（TERM 无效→KILL→组空）、`test_survivor_permission_denied_is_check_failed`、`test_cleanup_check_failed_cannot_pass`、`test_report_timeout_preserves_phase_evidence`、`test_drain_group_release_no_lingering_descendant` |

修复涉及 `cpu_01_entry.py`/`perf_adapter.py`/`test_cpu_01.py`；`cpu_01.yaml`、target 脚本与共享模块未再改动。代码 SHA 变化使 `build_plan()["identity"]` 与首轮不同——批准仍 pending，无既有批准需要迁移；§5 的 B 命令字符串不变，身份以执行时实时 `build_plan()` 为准。本轮未新增框架或实验，未运行真实 perf/Docker，未创建真实批准/marker。

## 9. 评审修复轮二（2026-09-15，三处闭合）

首轮修复复核确认 41 项通过、CSV 时间列与 period 分母两项不再返修；另注入三处离线反例复现未闭合，本轮集中修复（`run_phase`/`run_batch`/`parse_stat_csv`）：

| 复现 | 修复 | 反例测试 |
| --- | --- | --- |
| 正常退出路径漏清理后代：fake perf 启动关闭 stdout/stderr 的后台进程后正常退出，批次 complete 但进程组仍存活 | `run_phase` 在正常返回路径也核验本批进程组（`_group_alive`）：组仍活即走 `stop_process_group` 清理并标记 `group_leftover`；`_confirm_group_cleanup` 在 stat/record/report 每阶段收尾强制执行——发生过停止动作但没有 `group_stopped` 确认 → `group_cleanup_unconfirmed`，禁止 complete | `test_normal_exit_group_leftover_is_cleaned`（complete 且组空确认 + `group_leftover` 证据）、`test_drain_group_release_no_lingering_descendant`（管道持有者经组清理后才能 complete） |
| 有限时长进程绕过超时判定：登记 0.01 s、实际 ~0.066 s 自然退出仍 `timed_out=false` | `run_phase` 的 `wait()` 超时改取剩余量（`min(poll, 剩余阶段预算, 剩余 deadline)`，下限 1 ms）；进程成功返回后同样检查阶段预算/deadline（自然退出但超预算 → `timed_out=true` 走停止链）；每次清理、join 的等待量经 `cleanup_timeout` 重算剩余预算 | `test_short_process_cannot_evade_budget`（0.01 s 预算对 0.066 s 自然退出判超时）、`test_phase_budget_is_not_summed` |
| 不完整解析仍判 complete：stat 只有 metric-only 行、report 含 `25.00% broken` 未解析行均 complete | `parse_stat_csv` 区分 `n_counters` 与 `n_metric_only`（metric-only 行保留为证据但不计为 counter）——无 counter 行 → `no_counter_lines`，不得 complete；report 的 `unparsed_percent_lines` 非空 → `parsed_with_errors` 并中止，不得静默完整通过 | `test_stat_metric_only_not_complete`、`test_report_unparsed_line_not_complete`、`test_stat_empty_output_not_complete`（空文件同归 `no_counter_lines`） |

定向测试增至 **45 项**（41 + 本轮 4 项含既有断言更新），连续 3 轮通过；受影响共享回归（`test_g1_02`+`test_run_02`，36 项）通过。§7 的"Samples 作百分比分母"旧句已删除，函数表口径统一为 period 累加的 Self overhead。其余边界与授权状态见顶部；本轮未新增框架或实验，未运行真实 perf/Docker，未创建真实批准/marker。

## 10. B 单次执行记录（2026-09-16）

本节为实际运行证据，仅追加。授权：用户原话批准按 §5–6 清单执行一次（批准人 lcq，`approved_at_utc=2026-09-16T01:35:04Z`，完整身份绑定于 `reports/cpu/CPU-01/APPROVAL.json`，`checklist_identity` 与执行前实时 `build_plan()["identity"]` 逐字段一致）；工具权限对唯一命令行使一次。执行前核对：identity 无漂移（51 代码 SHA、catalog `6c779676…a05ec`、解释器、目标、perf 配置、预算、命令逐字一致），`reports/cpu/` 不存在，无旧 APPROVAL/ATTEMPT/marker，未复用任何旧批准。

### 10.1 执行与预算

- run_id：`CPU-01-20260916T013510Z-cf30c2dd`；批目录 `reports/cpu/CPU-01/CPU-01-20260916T013510Z-cf30c2dd/`。
- 实际命令（与 §5 登记逐字相同）：`PYTHONPATH=src /usr/bin/python3.11 -B -m agent_workload_characterization.runners.cpu_01_entry --execute --i-approve-the-cpu-01-b`。
- 返回码 `0`，`detail=stat_parsed_record_data_present`；`ATTEMPT_STARTED.json` 由 started（01:35:10Z）更新为 `completed`。
- 预检 READY：perf 二进制存在且可执行、target 脚本存在；`perf_event_paranoid=-1`（仅读取记录，未据此预判）。
- wall：summary `wall_s=9.589`（预算 120s，`budget_overrun=false`）；stat 3.872s + record 5.211s + report 0.134s。
- 清理：stat/record 两阶段后目标身份均确认 `exited`（stat PID 576139 / record PID 576206，PID+starttime 核对，闭式 checksum 一致 `6b834e26…edcd1`）；无 stop_events（无超时/阈值中断），drain 完整，无 group_leftover；未触碰无关进程。

### 10.2 各阶段状态与可用性

| 阶段 | 状态 | 关键结果 |
| --- | --- | --- |
| stat | `parsed`（rc=0） | 10/10 counter 有效（`n_counters=10`，parse_errors=0，metric_only 行不计入）；单一 run-time 列 3756254400ns、100.00% running，metric 尾字段（如 `2.900;GHz`）原样保留于 `extra_fields`——真实输出印证 §8 组 2 修复的格式判断；task-clock 3756.25ms；**硬件事件 cycles/instructions/branches/branch-misses/cache-references/cache-misses 全部支持且非零**（cycles 10892893444、instructions 46014667758、branch-misses 54908590、cache-misses 1146510）；IPC=4.224（同会话双有效、分母正） |
| record | `data_present`（rc=0） | perf.data 258180 B（sha256 `e442d0680173823c…`）；cycles@99Hz；目标同 checksum 完成 |
| report | `parsed`（rc=0） | 354 samples（header `# Samples: 354 of event 'cycles'`），`event_count_approx=10831096379`，98 行函数表，0 个 `[unknown]` 符号，0 未解析行；Top：`_PyEval_EvalFrameDefault` 20.03%、`_Py_NewReference` 4.88%、`_PyLong_New` 4.06% |

### 10.3 归档与产物

`archive_status=complete`，`status=complete`。manifest 输入（catalog sha `6c779676…`、target 脚本 sha `320037ee…`、perf 二进制 sha `4965f91b…`）与 4 个输出（`stat.csv` 595B、`perf.data` 258180B、`report_raw.txt` 7168B、`summary.json` 47490B）的 bytes+sha256 闭环，manifest 不自哈希。原始输出保留：stat.csv 12 行原始 CSV、report_raw.txt 完整 stdio 流、summary.json 含逐事件 `value_raw`。评审更正：4个输出共313,433B，批目录含manifest共325,617B；原“约513KiB”计账不准确。仅更正本文，不修改封存文件。

### 10.4 限制与如实声明

- 本批证明的是：本机（native arm64，`perf_event_paranoid=-1`）对**自有合成进程**的一次 stat/record/report 路径可用，硬件计数器在本次会话全部有效。这不等于容器内 PMU 归因（候选表 #1/#2 的 Agent/Verifier 容器须另立清单），更不是 Agent 热点：top 函数（Python 解释器 eval/long 分配）是合成整数循环的热点。
- report 函数表中 98 行里部分符号是裸地址（如 `0x0000000000109cc0`，libpython 部分符号未解析），非 `[unknown]` 标记；符号版本与 unwind 方法未单独验证（B 未启用 call-graph）。Overhead 为 period 加权 Self overhead，非精确 CPU 时间。
- 目标实测 CPU 3.72s（两次 checksum 一致），高于登记的预期值 `target_expected_cpu_s=1.5`（预期值非硬限制，wall 上限 10s 未超）；如实记录，不据此调预算或重跑。
- 单次批、无重试、无事件替换、无系统配置改动；`unavailable`/零样本路径未触发（本次全部有效）。完整 G2 判定归原评审，本交付不宣布 G2 通过。

## 11. 原评审裁定（2026-09-16）

**REVIEW_ACCEPTED：仅限本机自有合成进程的 perf 可测性。** 只读复核批准/attempt/manifest身份一致，51个代码SHA、3个输入和4个输出哈希匹配；IPC重算4.224283290253399。manifest SHA为 `5ba8b20ece46edc97d88d32727ee156618149a45f2210581da5c88fa3a420924`。清理结论基于封存记录，评审未运行perf或查询当前进程。

符号覆盖：98行中83行为裸地址，显示的period权重合计约62.04%（舍入后的行百分比之和）；0个`[unknown]`不是符号完整的证明。该限制不阻塞可测性验收，不为此重跑CPU-01。G2未通过。

下一步为 [CPU-02 A](cpu_02_handoff.md)：真实Verifier段的目标映射与热点准备，B仍须另批。
