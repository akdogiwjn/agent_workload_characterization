# G1-01-B0 交付：无模型容器验证入口的离线组装与最终审批清单

日期：2026-09-13。状态：**B0 第四轮完成，`B_user_approval=pending`；未执行任何 Docker/镜像/模型/网络操作**。

## 历史更正（按任务书 §1，不覆盖 R3/R4 原件）

R3 manifest 有 `files` map，缺陷是 `summary.md` 登记哈希过期。首批审批文件已按原哈希恢复。

## 实际改动文件（本轮）

| 文件 | 变更 |
| --- | --- |
| `runners/container_runtime.py` | `verify_removal()` 三态接口（removed / still_exists / check_failed）——DockerCliRuntime 用 `docker ps --filter id=` 核验（rc≠0 / 超时 / OSError → `check_failed`，**不映射为 removed**）；Fake 用内存 containers map（**无 Docker 调用**）；`ContainerSpec.pull` 字段 + `--pull=never` argv |
| `runners/b_entry.py` | 五组修复（见下） |
| `tests/test_g1_01_b0.py` | 37 项离线回归（含 8 项 Group8 第四轮反例） |
| `docs/g1_01_b_delivery.md` | 本文件 |

## 第四轮修复摘要（评审五组；全部离线，未运行容器或模型）

**R41 路径守卫**：`_guard_report_root()` 重写——**先检查原始路径各段**（symlink 在 resolve 前捕获，评审反例"resolve 后检查失效"修复），再核验 resolved 路径**等于固定位置** `reports/resource/G1-01-B`（**项目内另一目录的 redirect 也拒绝**，评审反例"指向项目内另一目录仍放行"修复），最后保护树（references / catalog 旧源 / 封存数据）。

**R42 清理核验与测试隔离**：`verified_cleanup()` 改用 `runtime.verify_removal()` 三态接口——**check_failed / still_exists 不映射为 removed**（评审反例"注入 daemon 错误仍 removed=True"修复）；未确认移除的 handle **保留在待清理列表**（不静默丢弃）；全局 `batch_status=FAIL` 反映未确认。**离线测试零 Docker 调用**：reader_factory 注入（不读 /sys/fs/cgroup）+ Fake 的 verify_removal 检查内存 map（评审"离线测试触达 Docker"消除）。

**R43 本地执行与预算**：生产 `main()` 显式固定本地 endpoint——`DOCKER_HOST` **和** `DOCKER_CONTEXT` 清除 + `docker context show` 核验为 `default`（非 default → rc=4）；所有容器启动携带 `--pull=never`（ContainerSpec.pull）；**预检纳入批 deadline**（`execute_batch(_batch_deadline=...)` 接收 main() 的 deadline，预检/执行/清理同一时钟）；报告 20 MiB 阈值检测 + 超限反映到 result。

**R44 观测与判定**：sleep 的 **open-persistence 在调用进行中验证**——专用 reader 线程在 execute 未返回时轮询 events 文件读取 open 行（读取时刻 `read_at_ns` 记录），非调用结束后看行序；宿主 **原始快照**（逐条 cpu_ticks/rss/stat）与 summary 一同持久化，scope 名修正为 `host_runner_process`（runner 进程，非 mini 子进程 `host_mini_child`）和 `host_short_child`（本批自有短程序，非 Agent）；**容器 1 的 CPU 证据门控**——基线→末边界 cpu_usage_usec 无增量 → case1 FAIL（不再"缺 CPU 证据仍 PASS"）。

**R45 降级与失败交付**：`_apply_io_degradation()` **无条件**应用于所有 scope summary（成功+失败路径、两容器）——formal null + reason、原数值块保留为 diagnostic（评审反例"`reason` 恒在故旧条件不生效"修复）；**异常路径保存完整原始 scope 证据**（c1/c2_scope_evidence.json 均写）；`execute_batch` 捕获任意基础设施异常（RuntimeError 等）→ abort FAIL + 完整归档 + 清理（不穿透）；`main()` **失败批次返回非零**（rc=5）——case FAIL 或清理未确认均触发。

## 实际验证命令与结果

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests            → 494 OK（420 + 74 B0；项目内）
项目外 cwd 绝对路径 discover                                         → 494 OK
PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python -m unittest tests.integration_run01 → 5 OK
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_swebench   → 5 OK
PYTHONPATH=src python3 -B -m agent_workload_characterization.runners.b_entry          → 计划 OK
PYTHONPATH=src python3 -B -m agent_workload_characterization.runners.b_entry --execute → rc=2
PYTHONPATH=src python3 -B -m agent_workload_characterization.runners.b_entry --execute --i-approve-the-b-validation → rc=3
git diff --check / py_compile / 敏感扫描                              → OK
封存 8/8 哈希复核不变
```

---

## 第五轮修复摘要（评审四组；全部离线）

**R46 main() 崩溃修复**：`_batch_deadline` NameError 修复（deadline 从 `t0 + BUDGET` 初始化，不再引用不存在的变量）；新增 `_LazyRF` reader factory 延迟解析（运行时在 main() 内构造后，reader 才可用）；`_checklist_identity()` 改用 `__file__` 定位真实代码根（不随 PROJECT_ROOT patch 变化）。

**R47 预算闭环**：`runtime.stop(timeout_s=...)` / `verify_removal(timeout_s=...)` 参数化并取剩余预算；后台 busy 的 terminate 超时同时钳制于 `background_busy_max_s`（≤5s 独立保障）；报告 20 MiB 阈值**在执行中**逐用例检查（`_check_report_threshold()` / `stop_batch()`），超限触发 FAIL 并归档；`main()` 的退出码同时反映阈值超限。

**R48 open 证据防误判**：open-persistence 证据增加**时间边界比较**——`read_at_ns < call_end_ns` 才算"调用进行中读取"（读取时刻 + 调用起止三元组归档于 `open_read_evidence`）；新增"故意延迟到返回后读取"反例（InstantRuntime 不 sleep → read_before_call_end=False → case FAIL）。

**R49 容器 2 失败证据**：c2 的 finally 现在写**完整原始 scope 证据**（c2_scope_evidence.json）+ `_apply_io_degradation()`（此前遗漏）；宿主 child 的 wait 包 try/except/finally——`TimeoutExpired` 按 PID+starttime 身份 kill + reap，异常路径也 reap，不泄漏进程；`test_host_child_timeout_killed_by_identity` 回归覆盖。

**本地 Docker 端点**：`DOCKER_HOST` 显式设为 `unix:///var/run/docker.sock`（不仅清除）；context 查询**失败即拒绝**（rc≠0/超时 → rc=4，不视为通过）。

**CLI 全链路回归**（Group9ReviewRound5.test_cli_full_chain_success）：从 `main()` 进入——mock 批准记录（绑定当前代码 SHA）+ fake docker（context/image inspect OK）+ patched DockerCliRuntime + lazy reader factory → exit 0 + batch_status=OK + 两容器 PASS。context 失败路径独立测试（rc=4）。

## 第六轮修复摘要（R47 预算闭环；全部离线）

**R50 后台 busy 独立总预算**：`bg_deadline = time.monotonic() + background_busy_max_s` 于后台启动前建立——观测等待、宿主 child 等待和 terminate 共享**同一 5 秒预算**（`bg_remaining()` 递减），stop chain 不再获 fresh 5s/步。bg 预算耗尽 → case FAIL + `background_budget_remaining_s` 如实记录。回归：BudgetProbeRuntime 观测烧 3s → terminate 收到 <5s。

**R51 批 deadline 全覆盖**：`main()` 的 `t0/deadline` 移到 context 检查**之前**——context 查询、image preflight、execute_batch 和清理全部从同一 deadline 取剩余时间。`runtime.start(timeout_s=cap_timeout(60))`；`cap_timeout()` 到期返回 **0**（拒绝），不再 `max(1,...)` 免费加秒。清理 reserve 不足 → SKIPPED。回归：过期 deadline → 所有用例 SKIPPED/FAIL。

**R52 报告阈值执行中打断**：`_RuntimeExecuteBridge` 增加 `stop_callback`（should_stop），经共享 hook 转发到 runtime.execute 的轮询等待——**阻塞中的用例被中断**（非仅用例间检查）。回归：SlowGrowRuntime 的 sleep 5s 在阻塞中被阈值 should_stop 打断 → rc=124 + stopped_by=external → case FAIL。

**代码变更**：`b_entry.py`、`container_runtime.py`（start/stop/verify_removal 全部接受 timeout_s）。

## 第七轮修复摘要（R50/R51 预算闭环收尾；全部离线）

**R53 bg_deadline 建立提前**：`bg_deadline` 移到 `env.execute(bg start)` **之前**——启动命令本身的超时从 bg 预算派生（`cap_timeout(min(per_command_timeout, bg_remaining()))`），启动阶段计入 5s 总预算。

**R54 停止链逐步扣减**：`terminate_workload(timeout_s=N, step_share_deadline=<absolute>)`——DockerCliRuntime 内部每步（pkill → process check → docker stop）经 `_step_timeout()` 从**绝对 deadline 的剩余量**取超时（递减，不重新派生）；deadline 耗尽 → 该步拒绝执行并报 `budget_exhausted_before_stop`。Fake runtime 记录每次调用的 `timeout_s` + `step_share_deadline` + `monotonic` 供预算断言。

**R55 零预算拒绝**：`_RuntimeExecuteBridge.execute(timeout=0)` → **refuse**（returncode=124 + stopped_by=budget_exhausted），不再 `timeout or default` 静默变 20s。清理路径保留 1s 强制下限（清理是必须的）但**超支如实记录**（`budget_overrun: true` 在每个 cleanup 条目）。

**测试无条件化**：`test_bg_busy_total_budget_not_per_step` 改为**无条件断言** terminate_workload 被调用（`assertGreaterEqual(len(runtime.terminate_calls), 1)`），断言 `timeout_s < 5`（非 fresh 额度）且 `step_share_deadline` 非空；新增 `test_zero_timeout_refused_not_defaulted`（timeout=0 → refuse，timeout=None → 正常默认）和 `test_step_share_deadline_decrements`（源码断言 `_step_timeout` 从绝对 deadline 递减）。

## 第八轮修复摘要（B0-A～E 一次修完；全部离线）

**B0-A 预算全下游覆盖**：`_resolve_cgroup(timeout_s=)` 共享调用方预算（不再固定 30s）；`DockerCliRuntime.execute()` 超时/外部停止后的 `terminate_workload` 传 `step_share_deadline=execute_deadline`（不再恢复默认逐步额度）；清理越时记录 `budget_overrun` 并进入统一 FAIL 判定。

**B0-B 清理独立于采集/归档**：`DockerCliRuntime.start()` 在 docker 调用前派生并保留容器名（`_last_created_name`，响应丢失仍可按名清理）；`_resolve_cgroup` 失败**非致命**（handle 正常返回，计数器 null+reason 不丢容器）；清理移出可能被跳过的 try 块（采集/summary/序列化异常不阻断）；`runner_mon.poll_once`/`summary` 各自 try-except。

**B0-C 统一最终状态**：`_compute_final_status()` 一处判定——case FAIL / 清理未确认 / 归档失败 / 清理越时 / 全部 SKIPPED（未验证≠OK）/ 证据缺失 均为 FAIL。`b1-fail` 的 rc=124/timed_out 与预期非零明确区分（timeout=FAIL，非零=expected）；`b1-cpu` rc=124 也是 FAIL。CLI 退出码由 `batch_status` 驱动。

**B0-D 采集证据**：`_check_evidence_quality()`——`c2_sampling_worked`（样本数>0，非 None==None）、`c2_reader_had_reads`（可计数的 reads，非两 None）、`c2_scope_frozen`（必须 is True 非 None）、`host_child_two_interval_snapshots`（≥2 可读区间快照，否则 partial/None）；所有 False 进入 FAIL 判定。宿主 child 增加第二次 mid-life poll。

**B0-E 交付包身份**：manifest 新增 `identity` 块（image/budget/code_sha256/approval_record_sha256/wall_s/batch_started_utc/cleanup_overrun/report_threshold_exceeded）+ `output_bytes` + `batch_status` + `batch_fail_reasons`；最终状态写入 batch.json 后封 manifest。

**反例回归**（Group11B0Final 7 项）：archive 失败→FAIL、false 超时→FAIL（非预期非零）、全 SKIPPED→FAIL、monitor summary 异常→清理仍执行+FAIL、start 后 cgroup 异常→无孤儿、0 样本→证据缺失、manifest 含完整身份。

## 第九轮修复摘要（四个残余反例；全部离线）

**B0-A 残余**：`DockerCliRuntime.start(deadline=)` 绝对截止——create 消耗后 `_resolve_cgroup` 取 `deadline - elapsed`（不再拿同一 timeout_s）；`cap_timeout()` 返回 float（0.2s 不扩为 1s，无 int+minimum 舍入）；`bg_deadline = min(now + busy_max, batch_deadline)`（后台不越批预算）。源码断言 + 行为回归。

**B0-B 残余**：`pending_names` 注册于 docker 调用前 + `cleanup_pending()` **消费**（不是只存名字）——execute_batch 在清理阶段调用，按名查找→按身份删除→报告 per-name 结果；未移除的 pending 进入统一 FAIL。

**B0-C 残余**：manifest 写入/回读校验失败→ `manifest_status` 进 `archive_status` → 重新 `_compute_final_status`（不再 pass 吞掉新错误）。反例：manifest.json 为目录 → batch FAIL。

**B0-D 残余**：`freeze_observation` 记录 thread_alive_at_start / observation_actual_s / reads_at_stop / reads_after / reads_countable——冻结证明为 `frozen AND thread_alive_at_start`（线程死→证明无效→case FAIL，不再依赖 None==None）；`if not scope_frozen_after_stop` 用复合值（原 `if not frozen` 检查原始计数但不含线程存活）。反例：stop(scope) 后立即杀全局线程 → FAIL。`c2_reads_countable` 独立检查（reads=None → False）。

## 第十轮修复摘要（三个生产路径反例；全部离线）

**B0-A 残余（生产层修复）**：所有 `max(1,...)` / `max(0.1,...)` 从 DockerCliRuntime 的 `start`/`_resolve_cgroup`/`_step_timeout`/`stop`/`verify_removal` 中移除——超时传 **float 剩余量**直接到 `subprocess.run(timeout=)`，0.2s 不再扩额。`cleanup_pending(timeout_s)` 共享单一 deadline（不每步 fresh 10s）。**mock subprocess 回归**：0.2s 预算下 terminate_workload 的每次 subprocess timeout ≤ 0.25s；_resolve_cgroup 同理；cleanup_pending 同理。

**B0-B 残余（三态语义）**：`cleanup_pending()` 重写——list rc≠0/timeout/OSError → `removed=False`（error=listing_*）；rm rc≠0/timeout → `removed=False`（error=rm_*）；rm "成功" 后 **verify by re-listing**（仍有输出 → `removed=False` error=still_exists_after_rm）；not_found → `removed=True`（真无容器）。**mock 反例回归**：listing 失败 / rm 失败 / rm 后仍存在 → 均 `removed=False`。

**B0-D 残余（生产 reader 计数）**：`CgroupV1FileReader` / `CgroupV2FileReader` 增加 `self.reads = 0` 计数器（每次 `read()` 递增）——生产读取路径可计数，不再依赖 fake reader。**生产 fixture 回归**：temp cgroup 树 + 真实 CgroupV1FileReader 跑冻结流程（reads > 0 / boundary 有值 / stop 后 reads 冻结）。

**附带修复**：`DockerCliRuntime.terminate_workload` / `execute` / `_resolve_cgroup` / `PROCESS_CHECK`（含 PROC_ROOT 重定向 + 语义修正 rc=0=confirmed）在重构中被意外移除——已恢复；进程树检查从 `returncode == 1`（语义反转）修正为 `returncode == 0`（idle → confirmed）。

## 第十一轮修复摘要（集中收尾）

**DockerCliRuntime.read_counters 生产实现恢复**：此前 base class 的 `read_counters` 为 `NotImplementedError` 占位（DockerCliRuntime 未实现）——现在实现为：v1 路径经 `CgroupV1FileReader`（按 container_id）、v2 路径经 `CgroupV2FileReader`（按已解析 cgroup_dir）、未解析时返回 `not_resolved` snapshot。

**verified_cleanup float 化**：`int(min(60, max(1, rem)))` → `min(60.0, max(0.1, rem))`——0.2s 不再扩为 1s。同步修 `_run_container_1/2` 的 fallback `cap_timeout` 和 per-command timeout。

**接口完整性核对**（本轮实际验证）：
- DockerCliRuntime 实现 8/8 方法（start/execute/read_counters/terminate_workload/stop/cleanup_run/verify_removal/cleanup_pending），无 NotImplementedError 占位。
- FakeContainerRuntime 同 8/8。
- 共享 hook（tool_event_env）单一源文本，两入口同用。
- 采集器（resource_sampler）reads 计数器就位（V1/V2 均有）。
- 宿主 monitor（host_process）PID+starttime 身份。

**调用关系**：
```
main() → _verify_approval() → DockerCliRuntime → execute_batch()
  → _run_container_1() → _run_container_2() → _compute_final_status()
  → cleanup_pending() → manifest
```

**资源所有权**：
- 容器：runtime.start() 在 docker 调用前注册 pending_names → handle 注册 live_handles → verified_cleanup + cleanup_pending
- 宿主 child：Popen → PID+starttime 身份 → try/except/finally 逐层 kill+reap
- 截止时间：main() 设一个 batch deadline → cap_timeout(float) 传到所有 subprocess 调用

## 第十二轮修复摘要（pending 清理预算闭环）

**cleanup_pending 预算传递**：`execute_batch` 中 `runtime.cleanup_pending(timeout_s=...)` 现在接收 **min(10, max(0.1, remaining))**（不是默认 10s）；预算耗尽时用 **0.1s 强制下限**（清理必须执行），并按 pending_overrun 标记 `budget_overrun=True` 进入统一 FAIL 判定。

**回归**（Group14PendingBudget 3 项）：
- 过期预算：cleanup_pending 收到的 timeout ≤ 0.15s（非默认 10s），batch FAIL
- 正常预算：收到 remaining（≤10s ceiling）
- verified_cleanup 的下限为 0.1s（非 1s）

## B1 最终审批清单（`B_user_approval=pending`）

### 命令与解释器

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src python3 -B -m agent_workload_characterization.runners.b_entry \
  --execute --i-approve-the-b-validation
```

退出码：0=成功 / 2=单旗标 / 3=批准记录缺失或内容不符 / 4=镜像缺失或 context 非本地 / 5=批次 FAIL 或清理未确认。

### 批准记录

批准时写入 `reports/resource/G1-01-B/APPROVAL.txt`，内容含 `checklist_identity`（image + budget + code SHAs）、`approved_by`、`approved_at_utc`。身份漂移自动拒绝。

### 代码身份（SHA-256 前缀）

| 文件 | 前缀 |
| --- | --- |
| `runners/b_entry.py` | `9e20c7b855f43562` |
| `runners/container_runtime.py` | `d4bbcc5c8432d25c` |
| `runners/tool_event_env.py` | `0de111c16411b302` |
| `runners/mini_agent_adapter.py` | `ae2949cad66af14b` |
| `collectors/resource_sampler.py` | `8418a9d793e170d9` |
| `collectors/host_process.py` | `2ec98884c8b0d1ea` |

### 固定环境

- 镜像：`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c2...7b7d2`（仅本地；预检在批预算内；`--pull=never`）
- 本地 docker endpoint：`DOCKER_HOST`/`DOCKER_CONTEXT` 清除 + context 核验为 `default`
- 最多 2 个严格顺序容器（容器 1 清理并核验移除后容器 2 才启动），各 ≤2 CPU / 256 MiB / network none

### 容器 1（4 次独立 execute，唯一 tool_call_id）

```sh
sleep 1
dd if=/dev/urandom of=/tmp/g1b.bin bs=1M count=8 && sync && rm -f /tmp/g1b.bin
false
python3 -c "x=sum(range(2_000_000))"
```

PASS 门控：open 在调用中可读 / sleep 窗口 ≥1 s / 容器 CPU 增量 / I/O formal null。

### 容器 2

后台 `setsid`（管道断开）；PASS 门控：CPU 增长 / terminate confirmed / scope 冻结。

### 预算与降级

| 项 | 值 |
| --- | --- |
| 批 wall | 180 s（预检纳入；所有等待取剩余） |
| 清理预留 | ≥30 s |
| 单命令 | ≤20 s 且不越批剩余 |
| 合成文件 | ≤16 MiB |
| 宿主子进程 | ≤1 个 ≤5 s |
| 报告阈值 | 20 MiB |
| I/O | 正式 null + degraded_host_v1_blkio（原值 diagnostic） |
| 磁盘 | 无容器可写层配额 |

### 明确不在本批

模型/网络、Agent loop、任务/gold/candidate 执行、第二次真实任务、perf/eBPF、G1 决议。

---

**B0 到此停止。B1 待用户针对本清单明确批准（写入 APPROVAL.txt）。**
