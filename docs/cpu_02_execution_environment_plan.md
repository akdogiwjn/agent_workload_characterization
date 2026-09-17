# CPU-02 执行环境确认方案

状态：**确认批次已执行并失败，等待原评审**。本次未创建 CPU-02-R2，未重试
正式任务；确认批次的批准、attempt 和失败证据已保留。

## 1. 目标与独立判定

本确认批次分别回答：

1. 获准正式执行身份能否读取同一目标的 PID/NSpid、starttime、pid namespace；
2. 在第一步成功且目标仍存活时，该身份能否对同一宿主 PID 做 perf attach 并取得
   可解析样本。

第二项不得在第一项失败时启动。namespace 读取成功不等于 perf attach 成功；
perf attach 成功也不替代目标身份三重核对。

## 2. 固定输入与当前已核实身份

复用 `cpu_02_entry.py` 的 `map_container_pid()`、`start_perf_controlled()`、
`control_cmd()`、`stop_perf()`、`DockerCliRuntime`、输出守卫和清理机制；不新增
通用框架。

当前只读核实的代码/输入 SHA-256：

```text
src/agent_workload_characterization/runners/cpu_02_entry.py
  cc7668e8444ad46f0d8876e311c9fdb6e1306524f5a0e719bdbe44f44eefcdbe
src/agent_workload_characterization/runners/container_runtime.py
  a2608e5549da73581c3a1b036080d64fa641eefe8e4bdf3cf429bc5a55ac1d83
src/agent_workload_characterization/runners/cpu_02_pid_diagnostic.py
  a4b90451f87646fea86c433c696bf7924db469c8852fd637efa992bf3acfa634
workload_catalog/cpu_02.yaml
  a730aec84fb4fc9e37f8b9025943205b8b29d5bf1fdb396e287330605238b50c
record.json
  762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a
candidate.patch
  d919b1322322abff8ac88cebdb25800d7b57285fbcfffc3216933c232097ebd5
```

固定镜像为已登记 arm64 digest：
`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`。

当前检查进程的权限上下文曾只读记录为 UID/GID `1000/1000`、附加组
`[65534,65534,1000]`、effective capabilities 为空、`NoNewPrivs=1`、
Seccomp mode `2`/filters `1`。这是当前检查环境记录，不替代 B 执行时重新
记录的身份，也不证明历史诊断环境完全相同。

## 3. 待批准的一次确认批

- 容器：最多一个固定 digest 容器；1 CPU、256 MiB、`network=none`、`pull=never`。
- 目标：容器内仅运行一个自有阻塞 Python worker；不运行 Django、Verifier、
  Agent、模型或 API。worker 保持存活，先返回容器 PID、starttime、namespace，
  再等待控制输入。
- 总 wall：60 秒，含 15 秒清理预留；第一阶段工作截止为总 deadline 减 15 秒。
- perf：仅在第一阶段通过后，对同一映射出的宿主 PID 短暂采样，建议采样窗口最多
  5 秒，事件沿用登记的 `cycles@99Hz`；不把窗口控制 ACK 时间冒称内核精确启停时间。
- 输出：拟使用独占目录
  `reports/cpu/CPU-02/permission-confirmation/<check_id>/`，保存批准/attempt、
  `PREFLIGHT.json`、PID 三重身份、权限白名单投影、perf 状态/样本状态、清理
  证据及 manifest。该目录在 A 阶段未创建，B 批次已使用其独占子目录。

## 4. 已核实的现有命令形态

以下是现有代码实际构造并已离线核对的命令形态，不是本次执行命令；其中 PID、
FIFO 和输出路径只有在第一阶段运行时由实际证据填充：

```text
docker context show
docker image inspect <固定digest> --format '{{.Os}}/{{.Architecture}}'
docker run -d --name <唯一名> --network none --memory 256m --cpus 1 \
  --pull never --platform linux/arm64 <固定digest> sleep 2h
/usr/bin/perf record -D -1 -F 99 -e cycles -p <映射后的宿主PID> \
  -o <批目录>/perf.data --control fifo:<批目录>/perf_ctl.fifo,<批目录>/perf_ack.fifo
```

现有 perf 控制协议为 `enable`→ACK、释放 worker、`disable`→ACK、`stop`，
每次操作从同一绝对 deadline 重新计算剩余时间。预检和运行必须由同一获准
进程执行；预检、namespace 读取或 perf 任一步权限不足均记录异常类型、errno
和安全类别后停止，不切换管理员身份或替代环境。

## 5. 实际执行顺序与验收字段

1. 记录本次实际 UID/GID、附加组、effective capabilities、NoNewPrivs、Seccomp
   和安全域；记录固定 endpoint/digest 预检结果。
2. 创建唯一容器并启动阻塞 worker；保存容器 ID、`State.Pid`、worker 自报
   PID/starttime/namespace。
3. 在容器仍存活时读取 init namespace，并以 NSpid 最内层、namespace inode、
   starttime 做唯一匹配；同时记录宿主目标 PID/starttime。零匹配、多匹配、
   PID 复用、身份不一致或读取异常立即停止，记录 `EACCES/EPERM`、`ENOENT/ESRCH`
   或 `unknown` 安全类别。
4. 仅当第 3 步成功，对**同一宿主目标 PID**启动既有 perf 控制协议；确认
   enable ACK 后采样不超过 5 秒，再 disable ACK/stop，保存 `perf.data` bytes、
   SHA-256、退出状态和 parser 状态。空文件、rc=0 无样本或解析失败均不算取得样本。
5. 无论哪一步失败，独立关闭管道、回收 worker、停止并核验容器删除；清理每步
   重新取剩余预算，未确认删除或越时不得标记成功。

结果字段至少包括：`execution_identity`、`target_identity`、`mapping`、
`namespace_read_status`、`perf_attach_status`、`sample_status`、`errors`、
`cleanup`、`wall_s`、`budget_overrun`、输入输出 bytes/SHA-256。

## 6. 权限边界与最小后续授权

本方案不要求 sudo、su、nsenter、`--privileged`、`--pid=host`、新增 capability、
sysctl/挂载/用户组修改或 Docker 全局配置修改。执行前需要：

1. 用户批准本方案的最终 check identity；
2. 对登记的唯一确认命令单独授予一次沙箱外工具权限，使预检、namespace 读取和
   perf attach 在同一实际身份/环境内完成。

若第 1 阶段失败，最小管理员协助仅应是对同一正式执行身份提供白名单只读核对：
proc namespace 读取所需的实际安全域/能力、proc 可见性限制和 LSM 拒绝类别。
不得以管理员成功替代正式身份成功；任何权限变更或动态实验须另行批准。

本方案不授权 CPU-02 正式任务重试，也不证明 G2 或 perf 生产可用性。

## 7. 最小入口已组装（仍待重新批准）

已新增薄入口
`src/agent_workload_characterization/runners/cpu_02_permission_confirmation.py`，
复用现有 `ContainerSpec`、`DockerCliRuntime`、`map_container_pid()`、
`start_perf_controlled()`、`control_cmd()`、`stop_perf()`、路径守卫和清理接口。
此前 A 阶段只完成代码与 fake 验证；本节后的 B 批次已按批准命令执行一次，未重试。

worker 的实际 JSONL 协议为：

```text
ready {pid, host_pid, starttime_ticks, pid_namespace}
<- {"cmd":"release"}
started {pid, host_pid, started_monotonic}
（有界 CPU 合成计算，默认 1 秒；确认批配置最多 5 秒）
done {pid, host_pid, finished_monotonic, iterations, checksum}
```

ready、started、done 的报告 PID 保持不变；宿主映射使用 worker 的容器 PID、
starttime、init namespace 与宿主 PID 三重核对。`_read_event()` 使用 selector
和有界字节缓冲，partial line、EOF、超时和非法 JSON 均不会无限阻塞。

入口门禁要求双旗标、独立 approval identity 和不存在的
`ATTEMPT_STARTED.json`；批准与 attempt 均为独占创建，已有 attempt 不再执行。
工作阶段使用总 deadline 减 15 秒；清理独立 reap worker、stop/verify 容器及
pending cleanup，任何未确认清理或越时均失败。正式入口的 PREFLIGHT、Docker
runtime 与 perf 仍需同一获准进程执行。

当前入口完整 identity 的新增字段包括：

```text
confirmation_id=CPU-02-PERMISSION-CONFIRMATION-01
confirmation_entry.sha256=17c1c2195e676266a22ecebe2dd6a9a736f767b0bad8c7c82325c283488124fc
confirmation_entry.protocol=ready -> release -> started -> bounded_cpu -> done
confirmation_entry.same_pid=true
```

实际执行的唯一命令：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m agent_workload_characterization.runners.cpu_02_permission_confirmation --execute --i-approve-the-cpu-02-permission-confirmation
```

## 8. 实际离线贯通回归

```text
PYTHONPATH=src:. .venvs/swebench-eval-02e7a74/bin/python -m unittest -v tests.test_cpu_02_permission_confirmation
Ran 9 tests ... OK (also verified with `-W error::ResourceWarning`)
```

回归覆盖：

- 真实本地 JSONL worker → PID fixtures → 三重映射 → fake perf 控制 → 归档/清理；
- worker ready/release/started/done 同一 PID，CPU 合成区间为合成缩短值，不是正式计量；
- 缺失 `done` 在 perf 已启动后失败，并回收本地 worker；
- perf 数据存在但解析为零样本时失败；enable 失败也进入独立 perf 停止收尾；
- perf stop 事件必须确认进程组已停止，且报告解析链必须返回有效样本；
- perf 正常退出码必须为 0；非零退出即使 report 有样本也保留证据并失败；
- ready/started/done 三个协议事件的 worker PID 必须完全一致；
- 采样控制与 worker 事件共用一个绝对采样截止时间，归档后再次核对总预算；
- identity 漂移通过实际入口门禁拒绝，`runtime.start()` 为零；
- 首次 attempt 在预检失败时保留失败 marker，第二次实际入口拒绝且不启动 runtime；
- 默认计划零副作用。

测试使用 fake runtime/fake perf 和短暂本地合成 worker；没有证明正式 Docker
socket 可达、真实 namespace 读取或真实 perf attach。后续必须重新核对该完整
identity、取得用户批准和一次工具权限后，才能执行上述唯一命令；失败即停，
不重试 CPU-02、不扩权限、不创建 R2。

## 9. CPU-02 执行环境确认 B 实际结果（一次，失败即停）

本次已按用户批准的最终 identity 和唯一命令执行一次；预检与运行在同一获准
沙箱外进程中完成。未重试、未扩预算、未创建 CPU-02-R2，历史 CPU-02/R1/PID
诊断证据未修改。

- `run_id`：`CPU-02-PERMISSION-CONFIRMATION-01-20260916T120120Z-e8e8cd94`
- 返回码：`5`；attempt：`failed`，detail=`FAIL`
- 预检：`READY`（context/image 均为 true）
- worker ready：PID `7`、starttime 已记录、pid namespace 已记录；映射阶段读取
  容器 init namespace 失败，`EACCES (errno=13) / permission_denied`，未启动 perf。
- perf：未启动，因此 ACK、退出码、有效样本和 report 解析均为 unavailable；不能
  推断 perf 权限结论。
- 清理：worker=`reaped`，container=`removed`，pending=`[]`；未发现残留。
- wall：`0.7977646347135305 s`，`budget_overrun=false`。该值仅为入口记录的
  截止口径，不作跨环境精确耗时结论。
- 实际执行身份白名单投影：UID/GID `1000/1000`，附加组 `[10,989,1000]`，
  `CapEff=0`，`NoNewPrivs=0`，`Seccomp=0`，安全域已记录为白名单字段。

证据目录：
`reports/cpu/CPU-02/permission-confirmation/CPU-02-PERMISSION-CONFIRMATION-01-20260916T120120Z-e8e8cd94/`

manifest 输出哈希核验：

```text
report.json  bytes=3      sha256=ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356
summary.json bytes=16458  sha256=b4b5393ab83dd792966f72ba610b3d3c3b6eb37dbd6f708ca98c034b3014168d
manifest.json sha256=95675b5e5a557e0c1d4bc05f591621131f6915ea5976743e41ce6850d5a0cf22
```

状态证据哈希：

```text
APPROVAL.json        sha256=eb324665c44fa7fdff36157b193a5c27d28eafbe8fab0ae7fe42da8ed6a45fe4
ATTEMPT_STARTED.json sha256=d0761e03ea5372a9fc2098e44b2e4bf77041a7212b2000d21ac48e8e4c168d19
```

本批结论仅确认：在本次实际执行身份和环境中，容器 init namespace 信息读取被
拒绝；由于第一步失败，未对同一目标执行 perf attach。它不区分 Yama、hidepid、
capability 或其他安全策略，也不证明 perf attach 必然失败。
