# CPU-02 PID 映射诊断 A 离线准备交付

状态：**A_READY_FOR_REVIEW / DIAGNOSTIC_B_PENDING_APPROVAL**。`user_approval=pending`、`tool_execution_permission=pending`。本批未创建诊断 approval/attempt，不创建 CPU-02-R2，不重试 CPU-02/R1。

## 1. 范围与独立身份

新增薄入口 `src/agent_workload_characterization/runners/cpu_02_pid_diagnostic.py`，仅用于一次短暂 PID 映射诊断；复用 `cpu_02_entry` 的路径守卫、`map_container_pid()`、有界 ready 读取和 `DockerCliRuntime` 生命周期，不复制 runner、采集或清理框架。

独立 namespace：`reports/cpu/CPU-02/pid-diagnostic/`，其下预留 `APPROVAL.json`、`ATTEMPT_STARTED.json`、`PREFLIGHT.json` 和唯一诊断 run 目录。旧 CPU-02/R1 approval、marker、raw、报告及 R1 失败批次不参与授权且未修改。

完整待批 identity 由 `cpu_02_pid_diagnostic.build_plan()["identity"]` 生成，包含完整 CPU-02 代码/config、record、candidate、固定 arm64 image、evaluator/生成脚本身份、诊断 ID、PID 三重映射规则、预算和新路径。关键身份：

- diagnostic entry：`a4b90451f87646fea86c433c696bf7924db469c8852fd637efa992bf3acfa634`
- record：`762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`
- candidate：`d919b1322322abff8ac88cebdb25800d7b57285fbcfffc3216933c232097ebd5`
- image：`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`

## 2. 诊断实现

- 容器使用固定 digest、`network=none`、`pull=never`、1 CPU/256 MiB；仅启动一个阻塞等待的自有 Python worker。
- worker 返回白名单 `pid`、`starttime_ticks`、`pid_namespace`；宿主仅记录自身 PID/NSpid、pid namespace、starttime 和 `/proc` mount options，不读取 cmdline、环境变量或凭据。
- 保持 `NSpid` 最内层、pid namespace inode、starttime 三重唯一匹配；零匹配、多匹配、身份不一致均失败，不猜 PID。
- `/proc` 读取错误记录操作阶段、目标 PID、异常类型、errno 和安全类别，不写异常原文：`EACCES/EPERM→permission_denied`，`ENOENT/ESRCH→process_missing_or_not_visible`，其他→`unknown`。`ENOENT` 不被解释为进程已退出。
- 入口共享 60 秒绝对 deadline；工作阶段使用 `deadline-15s`，15 秒仅留给清理。清理 finally 独立执行 interactive 客户端 wait/reap（必要时 kill 后再 wait）、容器 stop、verify removal 和 pending cleanup；任一步未确认或预算耗尽都不能成功。`container_alive` 若出现，仅表示工作负载停止后、删除核验前的阶段状态。
- 诊断结果另记录 `diagnostic_process`（宿主自身 PID/NSpid、namespace、starttime 的白名单投影），与 `host_init_proc` 分列；不把容器 init 读取当作诊断进程自身证据。

## 3. 实际离线回归

实际只使用临时 `/proc` fixtures、临时输出和 fake runtime：

| 路径/反例 | 结果 |
| --- | --- |
| PermissionError、FileNotFoundError、其他 OSError 分类 | 通过；仅白名单字段 |
| 唯一、零、多匹配 | 通过；三重门槛未放宽 |
| 默认计划无 subprocess/Docker/写入 | 通过 |
| 真实诊断逻辑成功路径 | 通过；fake worker→ready→init PID→`map_container_pid`→归档/清理 |
| init PID 读取失败 | 通过；脱敏类别保留，映射仍失败 |
| 诊断失败归档与清理 | 通过；显式 worker reap、容器 stop/verify |
| R1/旧批准不匹配、重复 attempt（实际 `main()`） | 通过；拒绝、零容器启动，已完成 marker 字节保持不变 |

命令及结果：

```bash
PYTHONPATH=src python3 -B -W error::ResourceWarning -m unittest tests.test_cpu_02_pid_diagnostic tests.test_cpu_02
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m unittest tests.integration_cpu_02
```

诊断 **9 项**、CPU-02 42 项、官方 parser 5 项通过；未运行真实 Docker/perf、网络、模型、Django 或实际权限探测。`ResourceWarning` 检查和 `git diff --check` 通过。

## 4. 唯一待批诊断命令

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m agent_workload_characterization.runners.cpu_02_pid_diagnostic --execute --i-approve-the-cpu-02-pid-diagnostic
```

该命令不是 CPU-02/R1 重试授权。后续必须另行批准本诊断完整 identity，并为该命令取得一次工具权限；失败即停，不创建 R2。禁止 sudo、nsenter、privileged、host PID、新 capability、proc/sysctl/Docker 全局配置修改、换用户绕过限制。

## 5. 证据能证明与不能证明

成功只能证明在获准环境中，该合成 worker 的容器 PID 能否按 NSpid、namespace inode、starttime 唯一映射到宿主候选；失败只能提供具体的安全分类或身份证据不足。它不能证明 perf 权限、镜像一般可用性、Django/eval 成功、CPU-02 workload 结果，也不授权重试 CPU-02/R1 或宣布 G2。

## 6. 本轮预算收尾修正

离线时钟反例显示归档写入本身越过绝对 deadline 时，旧实现会保留归档前的
`wall_s` 和 `complete` 状态。本轮仅修正
`runners/cpu_02_pid_diagnostic.py:run_diagnostic()`：清理完成后先写归档，
再在最终 manifest 写入后统一判定 `budget_overrun`；越时将返回值、磁盘
`summary.json`、`manifest.json` 的 `status` 同步为 `FAIL`，并以
`wall_cutoff=after_final_archive_write` 明确计时截止点。manifest 不自哈希，
其 summary bytes/SHA-256 会在最终状态写回后重新核对。

实际回归（未调用 Docker/perf/网络/模型）：

```text
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest -v tests.test_cpu_02_pid_diagnostic
Ran 9 tests ... OK
```

新增 `test_archive_overrun_updates_disk_state_and_hashes` 使用注入单调时钟和
manifest 写入后的越时，检查返回值及磁盘摘要/manifest 均为 `FAIL`、
`budget_overrun=true`、`wall_s` 已包含归档阶段，且 summary 的 bytes/SHA-256
与 manifest 一致。当前新增文件哈希：

```text
src/agent_workload_characterization/runners/cpu_02_pid_diagnostic.py  a4b90451f87646fea86c433c696bf7924db469c8852fd637efa992bf3acfa634
tests/test_cpu_02_pid_diagnostic.py                                  f0a3a91385ca33be041b7127a37ebaa398cdef8d2380c648a7b7df6d91c96f6f
```

上述 A 阶段未创建诊断批准/attempt；本次 B 已另行按最终清单登记并执行一次，
结果见下节。

## 7. 本次 B 诊断实际结果

用户批准已绑定完整 identity，批准文件为
`reports/cpu/CPU-02/pid-diagnostic/APPROVAL.json`，SHA-256：
`1519f5f63feffc81bd90a97d5ad249e4544361effb72dec3fef34dd459bd0af7`。
文档唯一命令已获得一次工具权限并执行一次；未重试。实际 run：
`CPU-02-PID-DIAGNOSTIC-01-20260916T092657Z-5ac9efa6`。

执行摘要：

- 命令：`PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m agent_workload_characterization.runners.cpu_02_pid_diagnostic --execute --i-approve-the-cpu-02-pid-diagnostic`
- 预检：`READY`；固定 Docker endpoint 和固定 arm64 digest 检查通过。
- 返回码：`5`；marker `ATTEMPT_STARTED.json`：`status=failed`，`detail=mapping_map_failed`。
- 容器：实际创建并运行一个容器，`container_id` 记录于 summary；worker 返回容器 PID `7`、starttime 和 pid namespace。
- 自身进程与容器 init 的白名单投影均已分列保存；未读取 cmdline、环境变量或凭据。
- 映射：`status=map_failed`、`reason=init_ns_unreadable`；目标 init PID `843505` 的 pid namespace 读取异常为 `PermissionError`、errno `13`、安全类别 `permission_denied`。这不能证明 perf 权限不足，也不把它解释为进程退出。
- 清理：本地 worker `reaped`，容器 `removed`，pending 清理为空；未操作其他容器。
- 预算：`wall_s=0.5582019565626979`，`budget_overrun=false`；`wall_cutoff=after_final_archive_write`。该值仅按登记口径报告，不作精确耗时结论。

证据文件：

```text
reports/cpu/CPU-02/pid-diagnostic/PREFLIGHT.json
  sha256 080e4ec7a02e30841fc3bdf4b75c2469c9db7fb9e8af6337204274101255ad70
reports/cpu/CPU-02/pid-diagnostic/ATTEMPT_STARTED.json
  sha256 bf46cb497aaa8213f68d6075e8429cabe6e03a344009c3645d4aebe715b7908c
reports/cpu/CPU-02/pid-diagnostic/CPU-02-PID-DIAGNOSTIC-01-20260916T092657Z-5ac9efa6/summary.json
  sha256 284bb23bae96e6e481b6f9de7a8f402b631cbb182608a02b476122238649f26e
reports/cpu/CPU-02/pid-diagnostic/CPU-02-PID-DIAGNOSTIC-01-20260916T092657Z-5ac9efa6/manifest.json
  sha256 47b0d9077b51d57b01acb7a8655600237d6ab357484bda6bddafee1a6c27963b
```

manifest 对 `summary.json` 的记录为 bytes `15741`、SHA-256
`284bb23bae96e6e481b6f9de7a8f402b631cbb182608a02b476122238649f26e`，已回读核对。
历史 CPU-02/R1 批准、marker、报告和 raw 未修改。此次诊断失败即停；不授权
CPU-02 重试、不创建 R2、不宣布 G2。
