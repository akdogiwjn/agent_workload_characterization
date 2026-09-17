# CPU-02 A 交付：真实 Verifier 执行段的容器内目标映射与热点小试点

2026-09-16 创建，同日修复轮更新。状态：**OFFLINE_FIX_COMPLETE / RETRY_UNAUTHORIZED**（`user_approval=recorded`，`tool_execution_permission=granted_once`）。原 B 已按批准清单执行一次并在准备阶段失败；本轮仅完成离线修复与复核，不构成重试授权。本交付不宣布 G2 通过。

## 1. 选段理由与边界表

选择 **SWE-bench Verified `django__django-16485` 的 Verifier 段**（RUN-02-R2 封存 candidate.patch、固定 task record、既有 arm64 digest、官方 eval/parser）：任务/补丁/镜像/判定链已有证据，执行段短、无需模型。不是重跑整个 Agent，不取轨迹 shell 命令，不用 gold patch。

| 边界 | 内容 | 计入 eval CPU 窗口 |
| --- | --- | --- |
| 镜像启动 | `docker create/start`（4CPU/8GiB、network none、pull never、固定 digest） | 否 |
| 环境准备 | candidate patch heredoc 写入＋官方 GIT_APPLY_CMDS 链（含 reverse-check "already applied"）＋官方 eval_script 写入 `/eval.sh`（`make_test_spec` 与 record 文本一致性核对，漂移即拒） | 否（准备段，`prepare_wall_s` 预算） |
| 测量起点 | 宿主确认 perf 采样就绪后发送 release（记录 monotonic+UTC anchor） | 是（起点） |
| 官方 eval_script | supervisor 同 PID `exec bash /eval.sh`：conda activate、`git checkout` 基线测试文件、test_patch 应用、`pip install -e .`、`runtests.py template_tests.filter_tests.test_floatformat`、`git checkout` 还原——**脚本内已有步骤如实包含，不删减** | 是 |
| 测量终点 | exec 进程退出（supervisor 会话返回码）；容器 scope 末边界随即读取 | 是（终点） |
| 官方解析 | 宿主 `get_eval_report`（`parse_log_django`，markers 缺失→`tests_not_run`） | 否 |
| 清理 | perf 停止（SIGINT→组空确认）→ 容器内 workload 终止 → supervisor 会话 reap → 容器移除确认 | 否 |

容器 CPU 边界是共享 cgroup scope 证据，不是逐函数 CPU 秒数；函数权重为 period 加权 Self overhead；CPU-01 的 IPC/开销数字不移用。

## 2. A1 身份映射与就绪屏障

**映射证据链**：本批容器 ID → `runtime.container_init_pid`（`docker inspect State.Pid`，最小增补，见 §3）→ init 的 pid-namespace inode → 宿主 `/proc` 扫描：候选须同时满足 (1) NSpid **最内层**等于 supervisor 自报容器 PID，(2) `ns/pid` inode 与容器 init 一致（排除宿主 docker CLI 客户端——它在宿主 namespace），(3) `/proc/<h>/stat` starttime 等于 supervisor 自报值（内核值跨 namespace 相同，PID 复用可检出）；另加宿主侧 `read_starttime` 交叉核对。零或多匹配即拒绝，不猜 PID。仅检查容器 init PID 不足以确认 exec 进程——不这样做。

**就绪屏障与热点窗口（control 协议，修复轮后）**：supervisor 打印 ready（容器 PID+starttime）后**阻塞等待 release**（无 marker busy-loop，等待期零 CPU）。宿主创建 ctl/ack 两个 fifo 并以 O_RDWR 打开，启动 `perf record -D -1 -F 99 -e cycles -p <宿主目标PID> -o perf.data --control fifo:<ctl>,<ack>`——`-D -1` 按 perf-record(1) 以事件禁用状态启动。屏障＝向 ctl fifo 发 `enable\n` 并在 ack fifo 收到 `ack\n`（手册记载的命令应答；非 Popen 成功、非固定 sleep、非 perf.data 增长——增长可能只是元数据）。收到 enable ACK 才 release；eval 结束后发 `disable\n` 并确认 ACK 关窗，再以 `stop\n` 命令停止（SIGINT/SIGKILL 兜底）。采样窗口＝[enable ack, disable ack]，eval 窗口＝[release, exec 退出]，窗口闭合关系与两个窗口的时间戳都记录；等待期被 `-D -1` 排除在采样之外，报告即 eval 执行段样本。（更正：首轮曾误判本地 perf-record(1) 无 `--control` 记录——文档实际明确记载 `--control=fifo:ctl-fifo[,ack-fifo]`、enable/disable/stop 命令与 `ack\n` 应答及 `-D -1`，此前检索模式未命中 roff 转义。）实际支持性留待 B 运行期验证。

## 3. 实际修改与复用

本轮更正：ACK 接收时间仅是控制协议边界，不是内核事件启停的精确时刻；采样窗口与 eval 窗口的控制延迟分别记录。

| 文件 | 性质 | 说明 |
| --- | --- | --- |
| `runners/cpu_02_entry.py`（新） | 薄入口 | 计划/身份→批准/attempt→预检→容器→官方准备→supervisor→映射→perf 屏障→基线/release/eval→末边界→停采→官方解析→符号链→归档→清理；默认零副作用，双旗标 `--execute --i-approve-the-cpu-02-b` |
| `scripts/cpu_02_supervisor.py`（新） | 容器侧协议 | ready 自报→marker loop→release→同 PID exec；stdin EOF 提前退出不跑 eval |
| `workload_catalog/cpu_02.yaml`（新） | 冻结配置 | 输入 SHA、预算、readiness 协议参数、映射语义；`execution_authorized: false` |
| `runners/container_runtime.py`（最小增补） | 共享修正 | 基类＋`DockerCliRuntime`/`FakeContainerRuntime` 增加 `container_init_pid`（docker inspect 只读）；既有方法逐字节不变，受影响回归通过 |
| `tests/test_cpu_02.py`（新） | 定向回归 | 21 项，fake runtime/perf/proc-view＋真实短 supervisor 走实际入口 |
| `tests/integration_cpu_02.py`（新） | venv 集成 | 真实官方 parser＋合成日志 4 项 |

复用：`SwebenchVerifierRunner` 纯命令构造（patch heredoc/官方 apply 链/eval heredoc）、官方 `make_test_spec`+`get_eval_report`（lazy，与 RUN-02 同链）、`ResourceSampler`（0.2s 周期＋边界）、`perf_adapter.parse_report`（CPU-01 修复后版本：单时间列、period 口径、evidence_status）、`cpu_01_entry` 的 `_drain`/`_group_alive`/`remaining`、`report_writer` guard（`reports/cpu/CPU-02/` 用 §3 增补后的 `guard_cpu_*`）、`DockerCliRuntime` 全部生命周期方法。不复制第二套 verifier/清理框架。

**符号协议（二进制安全，修复轮后）**：第一次 report 以**空目录 `--symfs`** 运行（隔离宿主符号，裸地址）→ 取 DSO 列表 → 仅接受**绝对路径**且经容器内 `python3` `os.path.isfile` 验证存在的 DSO → 通过容器内 `python3` base64 输出、宿主 `b64decode(validate=True)` 回写字节（文本通道传 ASCII base64，ELF 字节原样保留）→ 第二次 report `--symfs <批目录>/symbols`。短名 DSO、容器内未验证、读取失败或 base64 非法 → 逐项记录 `unresolved_dsos` 原因，保持裸地址；**宿主同名库从不参与，不能验证时明确符号不可用**。裸地址、`[unknown]`、已命名符号分别计行数与权重。

## 4. 函数 → 反例 → 证据字段映射

| 生产函数 | 反例测试（`tests.test_cpu_02.CPU02Tests`） | 证据字段 |
| --- | --- | --- |
| `main`/`build_plan`/守卫 | `test_default_plan_no_subprocess_no_write`、`test_single_flag_returns_2`、`test_identity_drift_refused`、`test_marker_once_refuses_second_attempt`、`test_output_guards` | `PREFLIGHT.json`、`ATTEMPT_STARTED.json`、批目录 |
| `map_container_pid` | `test_map_happy_path_and_rejections`（歧义/PID 复用/错误 namespace 即拒）、`test_perf_attaches_to_mapped_host_pid`（perf `-p` = 映射宿主 PID，≠容器 PID、≠ docker 客户端 42） | `phases.supervisor.mapping.{host_pid,namespace,checks}`、perf argv（`FAKE_PERF_META`） |
| `start_perf_attach`（屏障） | `test_full_chain_barrier_and_archive`（ready_observations 增长序列＋release 在其后）、`test_no_release_without_perf_ack`（无增长→`unavailable`，eval 未跑、`eval_output.txt` 不存在） | `phases.perf.{status,ready_observations,growth_observations,stop_events}` |
| eval/grade 链 | `test_resolved_false_still_complete_and_infra_distinct`、`test_tests_not_run_when_no_markers`；真实 parser：`tests.integration_cpu_02`（resolved true/false、tests_not_run、空日志） | `phases.eval.{eval_rc,wall_s,release_monotonic_ns}`、`phases.grade.{status,resolved,infra_failure}` |
| 边界/符号 | `test_cgroup_boundary_missing_and_reset`、`test_zero_samples_reported_honestly`（header 明确 0 与未知输出区分）、`test_unknown_symbols_kept`、`test_container_binary_unreadable_keeps_bare_addresses` | `phases.resource.boundary_*`、`phases.symbols.files`、`phases.report.{parsed,symfs_parsed}` |
| 收尾 | `test_supervisor_no_ready`、`test_perf_exits_early_during_eval`（`exited_before_stop`→FAIL）、`test_eval_timeout_cleans_everything`（容器/宿主收尾独立）、`test_threshold_abort_leaves_minimal_evidence`、`test_archive_failure_writes_marker`、`test_budget_exhausted_never_starts` | `cleanup.{workload_termination,perf_stop_events,supervisor,container,pending}`、`archive_failure.json` |

## 5. 实际测试

```bash
PYTHONPATH=src python3 -B -W error::ResourceWarning -m unittest \
  tests.test_cpu_02 tests.test_cpu_01 tests.test_g1_02 tests.test_run_02
PYTHONPATH=src python3 -B -m unittest tests.test_coding_pilot
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m unittest tests.integration_cpu_02
```

- CPU-02 定向 **36 项**通过（含生成 eval 脚本身份、启动前 evaluator/漂移拒绝、截断 base64、源端完整性、预算/清理和资源收尾反例；无 ResourceWarning）。
- 官方 parser venv 集成 **5 项**通过（含 pinned evaluator 的真实 `make_test_spec(record)` 脚本 bytes/SHA 核验；不执行 eval_script）。
- 受影响回归：`test_cpu_01`(45)+`test_g1_02`(26)+`test_run_02`(10)+`test_cpu_02`(31) 联合 112 项、`test_coding_pilot` 127 项、`test_preparation` 56 项全部通过。
- AST 解析改动文件通过；系统 python 与 **B 解释器（venv）** 计划模式均 rc=0；`reports/cpu/CPU-02/` 不存在，无 APPROVAL/ATTEMPT/marker。
- 未运行：真实 Docker（含查询）、真实 perf、网络、模型、真实 Django 测试、生产配置/密钥。测试不证明 PMU attach 实际权限、容器内映射真实行为或符号可解析性。

## 6. 完整身份与 B 唯一命令

完整拟批准身份由 `build_plan()["identity"]` 生成：52 个代码 SHA（`src/agent_workload_characterization/**` 51 + `scripts/cpu_02_supervisor.py`）、catalog SHA、record SHA `762de270…`、candidate SHA `d919b132…`、镜像 digest、supervisor 协议、evaluator venv 路径、perf 配置与 readiness 参数。B 命令已离线验证（两种解释器计划模式 rc=0；双旗标无批准 rc=3 有测试）：

本轮关键身份已重算：catalog `a730aec84fb4fc9e37f8b9025943205b8b29d5bf1fdb396e287330605238b50c`；entry `587357c3be68dd9d72c2578ed78a5fd355c7aba511996f0af96efaf35d42231b`；supervisor `859828a0261dfbefb44caf020810f061814ed88005ca152aa9249c2fff088bce`；runtime `a2608e5549da73581c3a1b036080d64fa641eefe8e4bdf3cf429bc5a55ac1d83`；CPU-02 测试 `55d456a5ca039a642cf38b8b4a9c34bafc4d7ac5dc9ae3a9624acb9b3d085a58`；parser 集成 `96b28099fd6d4d490e32b7b4755a56f41537397e683189a72f2b3731ce95aa4e`。

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m agent_workload_characterization.runners.cpu_02_entry --execute --i-approve-the-cpu-02-b
```

三次固定 perf 子命令：`perf record -D -1 -F 99 -e cycles -p <host_target_pid> -o perf.data --control fifo:<ctl>,<ack>`（attach 模式，宿主执行，`enable/disable/stop` 由 FIFO ACK 控制）；首次隔离报告为 `perf report --stdio --no-children --symfs <批目录>/empty_symfs -i perf.data`；第二次为同命令加 `--symfs <批目录>/symbols`。一次 eval；无 stat、无模型、无重试、无事件替换。

## 7. B 预算、预检、权限与运行期未知

| 项 | 冻结值 |
| --- | --- |
| 批 wall | 300 s（预检前→清理），预留 30 s；准备 ≤60 s；eval+采样窗口 ≤120 s；单控制操作 ≤15 s 且取剩余 |
| 容器 | ≤1 个顺序容器，4CPU/8GiB，network none、pull never、固定 arm64 digest；不挂 socket、无 privileged/host PID/新 capability |
| record | cycles @99 Hz，仅登记目标及其默认继承范围 |
| 产物 | 本批目录 100 MiB 检测停止阈值（含 perf.data、符号副本、日志）；无绝对磁盘配额声明 |
| 结束 | 失败即停；不补采、不换事件/任务/补丁、不重跑 Agent |

## 8. 本次获批 B 执行结果（一次，失败即停）

- 用户批准按本节最终清单执行；批准文件已登记于 `reports/cpu/CPU-02/APPROVAL.json`，SHA-256 为 `93f3469a52114808edf82fd046433bf693d1f3f6b739812942e1807e3d88d7a0`。执行前 live identity 与本清单关键身份核对一致，执行前无 attempt。
- 唯一实际命令：本文件 §6 的 venv `cpu_02_entry --execute --i-approve-the-cpu-02-b` 命令；通过一次沙箱外工具权限执行。批次 `CPU-02-20260916T062211Z-f5091ff5`，入口返回码 **5**，未重试、未扩预算。
- 预检：`READY`；固定 endpoint 为 `unix:///var/run/docker.sock`，固定 arm64 digest 检查通过，`perf_event_paranoid=-1` 仅作记录。准备阶段失败：`eval_script_drift_vs_make_test_spec`（`infra_failure`），因此 eval、perf record/report、符号解析和资源采样均为未开始/无样本，不得解释为 benchmark 失败或性能结果。
- 实际 wall：`2.253635872155428 s`（摘要记录点；批预算 300 s，未越时）。attempt marker 最终为 `failed`，SHA-256 `f7fc27cfe46fa377925adb0f917cf3367125d36169dab650c80a8fef79cc936e`。
- 产物：`reports/cpu/CPU-02/CPU-02-20260916T062211Z-f5091ff5/summary.json`（SHA-256 `2403b9f18612249e7bc995a8af9de8bcbade33e9691484dbf5d4b8b3ea4c2d07`）和 `manifest.json`（SHA-256 `e7528ef9e6b41ce6ef53ac0fdc4f88365fcc34484b12330ce1cf70e068e7087c`）；manifest 声明 `archive_status=complete`、`status=FAIL`。
- 清理证据必须按原样解释：摘要同时记录 `container=removed` 与 `workload_termination.confirmed=true`，但也保留 `container_alive=true`；这组字段存在矛盾，不能据此宣称残留已确认清除。无第二容器、无后续 attempt。
- 结论：本次为准备阶段基础设施失败，不能提供 perf/符号/资源用例结果；保留缺失和矛盾证据，交回原评审核验，不宣布 G2 通过。

## 9. 准备阶段失败的离线修复（重试未授权）

- 根因核实：固定 record 原始 `eval_script` 为 1372 bytes，SHA-256 `17f89072e31422786c1f91ffc6b6a0ba0d5741511439209f119ed3eaaf55bca1`；pinned evaluator `02e7a74` 的 `make_test_spec(record).eval_script` 为 1453 bytes，SHA-256 `c44c7b80f030a1352063585330d30f75c9252169e8668a14b6f0d0a812ce0a1b`。唯一登记差异为 `record_eval_script_plus_exit_code_v1`：测试命令后增加 `SWEBENCH_TEST_EXIT_CODE=$?`，结束标记后增加其 echo。原 record bytes/SHA 未修改。
- 生产入口现在在 `runtime.start()` 前通过登记的 evaluator venv 重新生成脚本，严格核对原始 SHA、生成 SHA 和上述唯一差异；evaluator 不可用、脚本漂移或出现其他差异均拒绝，容器实际写入的是已核验生成脚本。该元数据已进入 `build_plan()["identity"]` 与 `prepare.eval_script`。
- 离线回归：CPU-02 定向 36 项、官方 parser 集成 5 项通过；真实 pinned `make_test_spec(record)` 仅做生成/bytes/SHA 核验，未执行 eval_script。fake runtime 经实际 `run_batch` 捕获并验证生成脚本写入；脚本漂移和 evaluator 不可用均断言 `runtime.start` 调用为 0。
- 清理语义：`workload_termination.container_alive=true` 是“工作负载停止后、删除容器前”的中间状态；`container=removed` 是随后删除核验结果。代码不修改既有停止/删除机制，历史失败批次原字节保持不变。
- 最新代码身份：`cpu_02_entry.py` SHA-256 `587357c3be68dd9d72c2578ed78a5fd355c7aba511996f0af96efaf35d42231b`；CPU-02 测试 `55d456a5ca039a642cf38b8b4a9c34bafc4d7ac5dc9ae3a9624acb9b3d085a58`；parser 集成 `96b28099fd6d4d490e32b7b4755a56f41537397e683189a72f2b3731ce95aa4e`。
- 旧 B approval/attempt/失败批次未改动；本次没有新建 R1 或新 attempt。更新后的 identity 仍需重新获得用户批准；离线修复完成，重试未授权。真实 Docker/perf、生产容器写入和正式测量仍未验证。

预检（同进程、不运行 Docker 查询以外的 docker 命令）：① perf 二进制存在且 X_OK；② evaluator venv python 存在；③ record/candidate 文件存在（SHA 由 `load_config` 恒校验）；④ `docker context show`＝default 且固定 digest `image inspect`＝linux/arm64（G1-02 同款）；⑤ `perf_event_paranoid` 仅读取记录（不预判成败）。缺镜像即停（rc=4），不 pull/build。

权限需求：宿主 perf 对容器内目标进程的 `perf_event_open`（attach + 继承）；`docker inspect/exec/cat` 只读；容器停止/移除。**权限不足 → `unavailable` 停止，不提权、不 privileged、不安装**。运行期未知项（B 待测，不因 CPU-01 成功自动通过）：PMU attach 跨 namespace 权限、容器内映射真实行为（NSpid/inode 实际形态）、`--symfs` 对镜像内 binary 的解析效果、容器 python/库符号可用性、eval 实际时长、readiness 阈值在真实机器上的时序。CPU-01 IPC 与开销数字不可移用；函数权重不等于 CPU 秒数；B 结果只支持这个 Verifier 执行段，不声明完整 Agent 热点、CPU 架构建议或 G2 通过。

## 8. 评审修复轮（2026-09-16，五组一次修完）

本轮补充：容器端源文件 bytes/SHA-256 与严格 base64 解码后的宿主副本逐项比对；合法但截断的 base64 或哈希不一致均记录 unresolved，不进入第二次 symfs report。归档异常会同步回写磁盘 `summary.json` 的 `status=FAIL` 与 `archive_status=failed`。

原评审对首轮 A 注入离线替身复核，判定"A 暂不能验收、B 不放行"，五组生产接线缺口一次修复（`cpu_02_entry.py`/`cpu_02_supervisor.py`/`cpu_02.yaml`/`test_cpu_02.py`）：

| 组 | 评审复现 | 修复 | 反例测试 |
| --- | --- | --- | --- |
| 1 屏障与热点窗口 | "本地无 `--control` 文档"的判断错误；perf.data 增长可能只是元数据；marker busy-loop 被采样却未从报告中排除 | 更正判断：perf-record(1) 明确记载 `--control=fifo:ctl[,ack]`、enable/disable/stop、`ack\n` 应答与 `-D -1`。实现 control 协议：`-D -1` 禁用态启动 → `enable`+ACK 才 release → eval 后 `disable`+ACK → `stop` 命令（信号兜底）；supervisor 改纯阻塞等待（删除 marker busy-loop），等待期零 CPU 且被 `-D -1` 排除；采样窗口/eval 窗口时间戳与闭合语义入 `phases.perf.window_*` | `test_full_chain_barrier_and_archive`（enable/disable ACK＋窗口闭合断言）、`test_no_release_without_control_ack`（无 ACK→unavailable、eval 不跑）、`test_perf_exits_before_control` |
| 2 符号链损坏与来源 | ELF 经 `runtime.execute` 文本解码再编码即损坏；DSO 短名可能一个库都没复制；裸 report 可能用到宿主符号 | 二进制安全：容器内 `python3` base64 输出（ASCII 走文本通道）→ 宿主 `b64decode(validate=True)` 原样写字节；DSO 仅接受绝对路径且容器内 `os.path.isfile` 验证存在，短名/未验证/读取失败/base64 非法逐项记 `unresolved_dsos`，不猜路径；第一次裸 report 以空目录 `--symfs` 隔离宿主符号 | `test_symbol_copy_is_binary_safe`（任意字节含 0x00/0xff 完整往返）、`test_short_dso_not_substituted`、`test_container_binary_unreadable_keeps_bare_addresses`、`test_bare_report_isolated_from_host_symbols` |
| 3 失败仍 complete | 容器移除核验 `check_failed` 仍 complete；两次 report rc=0 空输出仍 complete | 终态消费清理结果：`container!='removed'`/`supervisor!='reaped'`/pending 有未确认 → FAIL（unavailable 同样受约束）；`run_report_phase` 检查 `evidence_status=='empty_output'` → 不得 parsed；`tests_not_run` 不再算验证成功；官方 `infra_failure` 标志位被消费（非仅 grader 异常）；resolved=false 与 infra 失败仍分开记录 | `test_container_removal_check_failed_fails`、`test_pending_cleanup_unconfirmed_fails`、`test_report_empty_output_is_not_parsed`、`test_tests_not_run_is_not_validation_success`、`test_grade_infra_failure_flag_fails` |
| 4 Docker 端点只是文字 | `docker_preflight` 报告固定 socket 但调用未固定，生产 runtime 未置于受限环境 | `main` 以 `g1_02_entry.local_docker_environment()` 包住预检与整个执行（同进程清除远端 context/代理覆盖、固定 `unix:///var/run/docker.sock`，退出恢复原环境） | `test_local_docker_env_fixed_for_whole_execution`（预检时 env 固定、外层环境恢复、rc=4 即停） |
| 5 日志与预算收尾 | 先写日志后 join reader 丢尾部行；清理与归档耗时未进预算判定 | 顺序改为：eval 结束 → `disable` ACK → 停采 → **有界 join reader** → 拼接写 `eval_output.txt`；`budget_overrun` 最终判定移到清理与归档完成之后（`wall_s` 同步在收尾后记录） | `test_eval_log_tail_not_lost`（50 行＋末行标记完整） |

测试基建同步修正：fake runtime 改用 `bash -c`（无登录配置；此前 `-lc` 的登录脚本 netlink 报错污染 ready 协议是评审复现的入口阻塞），`read_supervisor_ready` 改为循环读行并保留噪音行证据。代码 SHA 变化使 identity 更新（批准仍 pending 无需迁移）。未新增框架，未运行真实 Docker/perf/模型。
