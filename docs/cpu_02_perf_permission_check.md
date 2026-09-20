# CPU-02 最小 perf 权限验证（仅准备）

状态：**离线修复完成，但特权回收未闭合，当前不可执行**。即使后续另行批准，
也须先解决并复核回收边界。本方案不创建 CPU-02-R2，
不重试 CPU-02，不修改历史批准、attempt、raw 或报告。

## 固定范围

使用一个已登记 arm64 digest 容器，`network=none`、`pull=never`、1 CPU、256 MiB；
容器只运行自有阻塞 worker。总 wall 为 60 秒，清理预留 15 秒；worker 计算约 1 秒，
perf 使用 `cycles@99Hz`，采样窗口最多 5 秒。

普通用户负责 Docker、Python、worker、FIFO/ACK、report 解析和清理；仅 `perf record`
可按本页登记范围由 sudo 启动。仅当
普通用户已取得并核验正整数 init PID 或候选 worker PID，且候选 namespace 的
普通读取明确返回 EACCES/EPERM 时，才使用以下 sudo 白名单：

```text
sudo --non-interactive -- /usr/bin/readlink /proc/<validated_init_or_candidate_pid>/ns/pid
```

不使用 sudo 运行 Docker、Python、shell 或 perf 的 stop/kill；不读取凭据、环境变量或完整
cmdline。唯一新增特权命令是：

```text
sudo --non-interactive -- /usr/bin/perf record -D -1 -F 99 -e cycles \
  -p <validated_host_pid> -o <user_owned_perf_data> \
  --control fifo:<user_owned_ctl>,<user_owned_ack>
```

每批最多一次，仅在完整身份核验后调用。停止仍使用普通用户 FIFO `stop` 和进程组核验；
若 root perf 不响应，普通用户不执行 sudo kill，清理未确认即失败。

## 待批准的手动命令

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B \
  scripts/cpu_02_perf_permission_check.py --execute
```

当前待批准身份（执行前需重新核对）：

```text
scripts/cpu_02_perf_permission_check.py
  sha256=34e3e8b515c4377b5f870246d1a6030ad7c6238a196da7b94bc2e52a81c672a2
src/agent_workload_characterization/runners/cpu_02_permission_confirmation.py
  sha256=94f2a191f611048bb76552548ebb715b569ddf1e749ec708d1e77251108d1c1b
src/agent_workload_characterization/runners/cpu_02_entry.py
  sha256=7e0975ca5e86bac7efde9cff84694526dd117774e72f8436802de565fe2e3325
```

入口会在同一进程内固定 Docker endpoint 为 `unix:///var/run/docker.sock`，执行预检，
启动唯一容器和持续 JSONL worker，读取 ready PID/starttime，普通用户扫描 NSpid 与
worker namespace；init namespace 读取以及候选 namespace 的 EACCES/EPERM 降级读取
仅走上述 sudo `readlink`。status/stat 错误、超时、命令不存在或其他候选错误不升级。
映射必须满足 NSpid、starttime、namespace 唯一匹配，不能把 init PID 当作 worker PID。

候选 worker 的降级读取登记为每批最多 1 次 sudo 调用；只有普通候选 namespace
读取在 NSpid/starttime 核验后明确返回 EACCES/EPERM 才触发，status/stat/目标消失及
其他错误不升级。init 与候选读取均受统一 `work_deadline=deadline−15s` 约束，并有更短
的单次调用上限。启动 perf 前再次核对本批容器 ID、init PID/starttime 及选中 worker
的 NSpid/starttime；任一变化均拒绝启动。候选 worker 的 sudo `readlink` 是新增授权范围，
当前仍未批准。

只有以下条件全部满足才报告采样确认成功：目标身份前后一致、perf enable/disable
ACK 成功、perf 进程组已停止且退出码为 0、report parser 有有效样本、worker 已回收、
容器删除已核验。空或元数据文件不算样本。任一 sudo/Docker/协议/PID/预算/清理错误
均保留脱敏证据并停止。

## 已完成的离线验证

fake 外部命令和现有控制链回归覆盖：计划零副作用、正整数 PID 与 namespace 输出校验、
sudo 非零/超时拒绝、候选 EACCES 才升级、既有 worker/perf/report/清理链的映射失败、perf 拒绝、零样本、
正常采样、目标身份变化、预算停止和清理失败。未调用真实 Docker、sudo、perf、网络、
模型或权限探测。

候选 worker sudo `readlink` 属新增授权范围，当前尚未批准。该检查若成功，仅证明普通用户对该固定合成目标的 perf attach 和样本解析条件；不证明
Django、Agent、Verifier 或 CPU-02 正式任务可运行，也不授权任何提权或重试。

## ACK 超时失败批次复核与日志修复

复核批次 `CPU-02-PERF-PERMISSION-CHECK-01-20260917T045049Z-a15cc803` 的实际文件后，
确认仅有 `perf.data`、`report.json`、`summary.json` 和 `manifest.json`；没有 perf
stdout/stderr、启用阶段退出码或 drain 完成状态。因此现有证据不能区分 perf 在启用等待
期间已退出，还是 ACK 超时后由清理终止；不能据此归因于权限不足。该批次原始文件未修改，
缺失日志也无法事后恢复。

现有链已补为：启动后持续有界排空 stdout/stderr，记录字节数、截断标志、drain 状态，
分别保留启用等待阶段观察到的退出码与清理后的退出码，并在有界收尾后写出
`perf_stdout.txt`、`perf_stderr.txt`，两者纳入 manifest。日志仅作固定模式脱敏投影；
启用失败、超时和正常路径均进入相同收尾链。旧 ACK 超时批次不因本修复而获得新证据。

本轮 fake perf 实际子进程定向回归 4 项通过：提前非零退出并保留 stderr/退出码、存活无
ACK 超时并清理、大量输出不堵塞且正确标记截断、正常 ACK 控制管道。共享确认链原有
9 项及权限入口原有 12 项回归此前均通过；另经 `py_compile` 与 `git diff --check`。

此前日志修复记录身份（历史，不作为当前执行清单）：

```text
src/agent_workload_characterization/runners/cpu_02_entry.py
  sha256=6ebf1b10ec5ac38fc2a1482e1253ea93a47514d1d698018d2acbc855782f80f7
src/agent_workload_characterization/runners/cpu_02_permission_confirmation.py
  sha256=405e80cd98a901e02c27adfc17404856e16eb46ef745d22ff19c120213e0414b
```

如需再次验证，仍须沿用本页固定范围和唯一待批命令，并重新获得用户批准及工具权限；
本轮没有创建新批次、批准或 attempt。

## 仅 perf record 的待批变体

最新失败批次 `CPU-02-PERF-PERMISSION-CHECK-01-20260917T062839Z-69731a2b` 的
`perf_stderr.txt` 记录了普通用户 perf 在 ACK 前以 `255` 退出并报告访问受限；这
解释了该次失败，但不证明 sudo 运行可行。该批次 manifest 与所有输出哈希已核对，
历史文件未修改。

离线实现了一个受控变体：编排、Docker、worker、FIFO、report 和清理仍由普通用户
执行，只有固定目标、固定 `cycles@99Hz`、固定输出路径的 `/usr/bin/perf record`
可通过一次 `sudo --non-interactive --` 启动。perf.data 先由普通用户以 0600 独占
创建，避免 root 新建后普通用户不可读；拒绝路径会清除 FIFO 和预创建文件，不使用
chmod 777 或递归 chown。sudo 客户端退出不被当作 perf 成功；普通用户仅发送 FIFO
`stop` 并核验进程组，无法确认时失败，不暗中追加 sudo kill。

本轮定向回归覆盖 sudo argv/文件归属、sudo 拒绝后的 FIFO 清理、提前退出、ACK 超时、
正常控制管道、脱敏归档与 manifest 哈希；均通过。既有权限入口 12 项也通过。
未调用真实 sudo/Docker/perf，未创建新批准或 attempt。

当前代码身份：

```text
src/agent_workload_characterization/runners/cpu_02_entry.py
  sha256=d1de19ba6872ea6c2594a25c39e54365e83ba1363ba03d9648bfe6f37b3c494d
src/agent_workload_characterization/runners/cpu_02_permission_confirmation.py
  sha256=b201be688f0da534f8cb05c5519706168a411ce6fe8f782bd19f7ef5d0deba41
scripts/cpu_02_perf_permission_check.py
  sha256=34e3e8b515c4377b5f870246d1a6030ad7c6238a196da7b94bc2e52a81c672a2
tests/test_cpu_02_permission_confirmation.py
  sha256=b5c75e45d6b277758e501bd44c3ed03c092bd52a443231ee9b31c2e5c71fb63f
```

sudo perf record 属新增授权范围，当前仍待用户和工具权限批准；如 root perf 无法由
普通用户 FIFO 停止并核验，安全结论为阻塞，不登记为可执行成功路径。

## 本轮特权 perf 异常回收修复（仅离线）

本轮没有调用真实 sudo、Docker 或 perf，也没有创建批次、批准或 attempt。
编排侧区分 sudo 启动客户端、实际 perf PID/进程组和进程组停止确认：sudo
成功 exec 后，跟踪的是实际 perf PID；客户端退出不能替代 perf 退出或进程组
消失的确认。FIFO `stop` 先行，随后在同一绝对 deadline 下有界等待；仍存活时，
只有记录的 PID starttime 与 PGID 仍同时匹配，普通用户才尝试该进程组的
SIGINT/SIGKILL。身份无法重核验或已变化时记录 `identity_changed_no_signal`，
不发信号。

本实现没有新增 sudo kill/stop 命令。root perf 无法通过 FIFO 停止且普通用户
无法确认进程组消失时，产物写 `perf_recovery.status=unconfirmed`、批次为 FAIL，
并保留退出观察；FAIL 不等于已回收。裸 PID 的 sudo kill 无法在命令边界原子
绑定 starttime，存在 PID 复用风险，因此未登记为可执行兜底。任何未来特权
兜底都必须另行批准一个能原子绑定进程身份的窄操作，并受清理 deadline 限制；
本页当前不授权或执行该操作。

perf stdout/stderr 的 drain 缓冲只在内存中存在，归档前统一脱敏；归档只包含
脱敏日志、字节数、截断/drain 状态以及启用阶段、清理前后退出观察。`perf.data`
由普通用户预创建，并随后实际以 `O_NOFOLLOW` 打开核验；0600 模式本身不构成
可读性的充分证明。FIFO 无 ACK、sudo 客户端退出而 perf 仍存活、停止权限拒绝
或身份变化，均以回收证据判定，不能用 FAIL 字样替代资源回收确认。

新增离线回归（实际控制/清理路径，外部边界为自有 fake）：FIFO 无响应且 perf
存活、停止权限拒绝、PID starttime/PGID 变化禁止发信号、提前非零退出、大量输出、
正常 ACK、脱敏归档和 manifest 输出哈希；共 31 项确认/权限入口定向测试通过，
另执行 `py_compile` 与 `git diff --check`。未执行真实检查，特权回收仍是待评审
阻塞项，不得标记可执行或授权重跑。

## 特权 perf 回收方案设计（仅方案，未授权实施）

### 推荐方案

推荐由管理员预先安装一个不可由普通用户修改的、功能极窄的特权监督器，
而不是事后对裸 PID 执行 `sudo kill`。监督器以固定 root-owned 可执行文件启动
一个固定的 `/usr/bin/perf record` 子进程，并亲自持有该子进程的进程组、PID
starttime/PGID 和 wait/reap 责任。监督器只接受一次性、结构化且不可变的参数：
已核验的目标 PID 身份、固定事件/频率、已核验的用户拥有输出目录，以及监督器
自己的绝对截止时间。普通用户只负责启动获准监督器和发送 FIFO 控制命令。

这样 FIFO 失效、sudo 客户端退出或普通用户编排进程消失时，监督器仍能按自己的
截止时间停止并回收 perf；监督器自身也不会因普通用户传入的 PID、路径或 shell
文本而扩大权限。推荐该方案的前提是管理员能够提供不可替换的监督器及原子身份
核验机制；当前“仅 sudo perf record”边界不具备这些条件，不能靠状态字段补足。

### 精确新增权限与所有权要求

待用户、管理员和工具权限另行批准的最小范围是：

```text
sudo --non-interactive -- /usr/local/libexec/cpu02-perf-supervisor
  --target-pid <validated-positive-pid>
  --target-starttime <validated-starttime>
  --target-pgid <validated-pgid>
  --event cycles --frequency 99
  --output <validated-user-owned-perf-data> --owner-uid <ordinary-user-uid>
  --control <validated-user-owned-control-endpoints>
  --deadline-monotonic <fixed-absolute-deadline>
```

以上是待批准的接口示意，不是当前可执行命令。实际监督器必须是 root-owned、
不可由运行用户或其组写入，固定路径、固定哈希并由管理员负责安装/升级；配置、
事件、频率和允许的输出根目录同样由 root-owned 配置固定。`sudoers` 只能允许
该一个固定路径及受限参数接口，禁止参数通配到 shell、Python、Docker、任意
`kill`/`pkill` 或其他 perf 子命令。

监督器启动前必须在普通用户侧完成容器身份、目标 PID、starttime、PGID 和 namespace
核验；监督器启动后还须在其权限域内复核目标仍为同一进程。监督器应使用
pidfd 或等价的内核原子身份绑定；若只能接收裸 PID，方案不满足防 PID 重用要求，
应拒绝启动。输出文件由普通用户预创建为用户所有、不可跟随符号链接；监督器只
打开该已核验文件描述符或使用 `O_NOFOLLOW|O_EXCL` 等价保护，FIFO 所在目录及
父目录均由普通用户独占且受输出守卫保护。监督器不得修改权限、执行 chown 或
写入项目外路径。其 stdout/stderr 只写入受限、脱敏的用户可读日志，不能包含
环境变量、凭据或完整命令行。

### 三条回收路径

1. 正常：普通用户发送 FIFO `disable`/`stop`；监督器确认 perf 正常退出，调用
   `wait/reap`，记录原始退出码、进程组消失和输出可读性，再向普通用户返回
   受限结果。普通用户随后关闭端点并核验监督器、perf 和容器状态。
2. 超时：监督器到达自己的绝对截止时间后，按固定顺序停止 perf、等待并 reap；
   每一步使用同一截止时间的剩余预算。未确认退出、wait/reap、文件可读性或目录
   清理时，结果为失败/未确认并保留证据，不启动后续工作。
3. 断连：FIFO EOF、普通用户客户端退出或监督器父端断开均触发监督器的独立
   watchdog deadline；监督器不等待普通用户重新连接、不接受新参数，执行与超时
   路径相同的停止、wait/reap 和状态落盘。监督器本身退出前必须记录 perf 子进程
   已回收；否则批次保留 `unconfirmed`，不能报告清理成功。

### 离线验证与待用户决定事项

A 阶段可用普通用户测试进程、fake supervisor/fake perf 和 fake FIFO 验证实际
   编排边界：监督器参数篡改、root-owned 配置不可替换、输出/FIFO 符号链接拒绝、
   PID 重用拒绝、正常 ACK、FIFO 无响应、sudo 客户端断连、监督器超时、子进程
   残留、wait/reap 失败、输出不可读及 manifest 证据闭环。测试只替换外部命令，
   不调用真实 sudo、Docker 或 perf，也不证明管理员监督器已经安装可用。

   待决定事项仅包括：管理员是否提供 pidfd/等价原子绑定的监督器、其固定完整
   哈希和 root-owned 安装路径；监督器的精确 watchdog/清理预算；以及是否允许
   它写入预创建的用户文件描述符。上述事项未确认前，现有 sudo perf 方案仍因
   特权回收不可可靠闭合而阻塞，不登记新的可执行批准或命令。

## 监督器离线实现记录（仅源码，未安装/未执行）

已在仓库加入最小源码 `scripts/cpu_02_perf_supervisor.py`，并在现有入口加入
`build_perf_supervisor_argv()` 与可选 `perf_supervisor_path` 接线。默认入口仍
不调用监督器；只有未来安装了固定 root-owned 副本并另行批准后，才可由现有
编排传入该路径。监督器不接受命令字符串，不执行 shell/Python/Docker，只能构造
固定的 `/usr/bin/perf record -D -1 -F 99 -e cycles -p PID -o OUTPUT --control`
子进程，并负责 watchdog、进程组停止和 wait/reap。

源码的拒绝规则包括：固定 event/frequency、最长 60 秒监督截止时间、输出及 FIFO
必须位于固定报告根目录且父段无符号链接、目标 PID/starttime/PGID 必须匹配，且
尽可能持有 pidfd。目标身份无法核验、路径越界/符号链接、参数漂移均在启动 perf
前拒绝。stdin 只作为普通编排存活通道；EOF 触发断连回收，不提供额外控制命令。
监控器启动的子进程由其自身进程组停止并 reap；这与普通用户是否还能向 root
进程发信号无关。

### 审阅用安装、权限与卸载步骤（不执行）

管理员需先独立审阅并核对源码完整哈希，再在维护窗口执行以下等价步骤；本项目
或模型不得代执行：

```text
install -o root -g root -m 0755 <reviewed-copy> /usr/local/libexec/cpu02-perf-supervisor
sha256sum /usr/local/libexec/cpu02-perf-supervisor
visudo  # 仅登记固定路径及受限参数接口，禁止 shell/Python/Docker/kill 通配
```

卸载同样必须由管理员在另行批准后执行：先确认无运行实例，再删除该单一固定文件
并复核 sudoers 中没有遗留授权。本轮不执行 `install`、`chown`、`visudo` 或删除。
安装后的 root-owned 文件、sudoers 规则、pidfd 支持和监督器实际权限行为均未在
离线环境证明。

### 本轮完整身份与离线测试

```text
scripts/cpu_02_perf_supervisor.py
  sha256=d10c651d911e3736eb7c1aed75e49d17fc1770d411b2349b6817919a7b1af2a7
src/agent_workload_characterization/runners/cpu_02_entry.py
  sha256=1872f3c951952478f175913fce561cf188f6ce447ff5884aab2a9f5fb6bd4340
src/agent_workload_characterization/runners/cpu_02_permission_confirmation.py
  sha256=bcff5a5c0967f85276c68b28eedbfeca69d0373dc949fe444359ee4c82c85e45
tests/test_cpu_02_perf_supervisor.py
  sha256=98e6129075c19b65e5cbda1763ff881cdec93ece9ccac2494eb9a598108dc69b
```

定向测试使用普通用户创建的 `sleep` 子进程及 fake perf/FIFO 边界，经过固定 argv、
路径/参数拒绝、目标身份变化、watchdog 停止和实际子进程 wait/reap 路径；监督器
定向测试与既有 CPU-02 权限确认测试合计 36 项通过。执行了 `py_compile` 和
`git diff --check`。这些测试不能证明 root-owned 安装、sudoers 约束或真实 perf
退出行为。

待单独批准的最小真实验证仅包括：管理员安装后核对固定文件/配置哈希，普通用户
在一个固定 digest、network none、pull never、1 CPU/256 MiB 容器中运行自有 worker，
监督器 watchdog 在 60 秒内完成正常、超时和断连回收，并核验 perf 子进程已退出、
已 wait/reap、输出由普通用户可读且路径无残留。不得借此授权 CPU-02 重试或修改
历史证据；若任一特权回收/文件所有权证据缺失，仍保持不可执行。
