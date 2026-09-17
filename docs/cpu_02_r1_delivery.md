# CPU-02-R1 A 离线准备交付

状态：**B_EXECUTED_FAILED / G2_PENDING_REVIEW**。`user_approval=recorded`，`tool_execution_permission=granted_once`。R1 已按清单执行一次并失败即停，不构成重试或 R2 授权。本交付不宣布 G2 通过。

## 1. 接线与隔离

新增薄入口 `src/agent_workload_characterization/runners/cpu_02_r1_entry.py`。它只负责 R1 namespace、双旗标、批准身份校验、原子一次性 attempt marker、固定本地预检和调用原 `cpu_02_entry.run_batch`；准备/evaluator 生成脚本核验、PID 映射、perf FIFO ACK、ResourceSampler、官方 parser、符号解析、预算和清理均复用已验收 CPU-02 实现。

固定输出根：`reports/cpu/CPU-02/retries/R1/`；批准、attempt、预检分别为该根下的 `APPROVAL.json`、`ATTEMPT_STARTED.json`、`PREFLIGHT.json`，批次目录为独占 `CPU-02-R1-<UTC>-<nonce>`。旧 `reports/cpu/CPU-02/APPROVAL.json`、旧 attempt 和失败批次不参与授权且未改动。

R1 identity 由 `cpu_02_r1_entry.build_plan()["identity"]` 从当前完整 CPU-02 identity 派生，增加 `retry_id=R1`、`collection=CPU-02-R1`，并绑定新的批准/attempt/report 路径；包含全部代码 SHA、catalog/config、record/candidate/image、supervisor 协议、evaluator/生成脚本身份、perf 事件/频率和原预算。当前关键身份：

- `cpu_02_entry.py`: `587357c3be68dd9d72c2578ed78a5fd355c7aba511996f0af96efaf35d42231b`
- `cpu_02_r1_entry.py`: `05121425ad5cc4ce7e88c5d4407c9db3bcd3f23d10a28ebcd942a62f4b5d92bb`
- catalog: `a730aec84fb4fc9e37f8b9025943205b8b29d5bf1fdb396e287330605238b50c`
- record: `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`
- candidate: `d919b1322322abff8ac88cebdb25800d7b57285fbcfffc3216933c232097ebd5`
- image: `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`

生成脚本身份沿用已验收修复：record 脚本 1372 bytes / `17f89072…bca1`，pinned evaluator `02e7a74` 的生成脚本 1453 bytes / `c44c7b80…0a1b`，仅允许 `record_eval_script_plus_exit_code_v1` 两行差异。B 运行前仍重新生成并核对，旧批准不能授权 R1。

## 2. 实际离线回归

使用临时批准/attempt namespace、fake 预检和 fake runtime，均经过实际 R1 入口：

| 用例 | 结果 |
| --- | --- |
| 默认计划零 Docker/perf/写入 | 通过；临时状态根未创建 |
| 缺批准、旧 CPU-02 批准、identity 漂移 | 均经 `r1.main()` 拒绝；runner/start 调用为 0 |
| R1 批准首次执行、第二次 marker 拒绝 | 通过；只允许一次调用 |
| 预检失败 | 通过；写 R1 `PREFLIGHT.json`、attempt=`failed`，不启动 runtime |
| evaluator 不可用/生成脚本漂移 | 均经 `r1.main()` 验证；marker=`failed`，复用入口在 `runtime.start()` 前拒绝 |
| 成功路径 | 通过；实际复用 `run_batch`，批产物仅落入 R1 独立目录，manifest 生成 |

实际命令：

```bash
PYTHONPATH=src python3 -B -W error::ResourceWarning -m unittest tests.test_cpu_02_r1
PYTHONPATH=src python3 -B -W error::ResourceWarning -m unittest tests.test_cpu_02
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m unittest tests.integration_cpu_02
```

结果：R1 **9 项**、CPU-02 36 项、官方 parser 集成 5 项全部通过；R1 测试统一使用 `addCleanup()` 恢复预检 patch、runtime factory 和 grader，`-W error::ResourceWarning` 无警告。未运行全历史套件。原 record SHA、原批准/attempt/失败批次 SHA 保持不变，`git diff --check` 通过。

## 3. 待批准 B 清单与限制

唯一待批命令（当前 A 仅登记，不执行）：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -B -m agent_workload_characterization.runners.cpu_02_r1_entry --execute --i-approve-the-cpu-02-r1
```

保持原 CPU-02 预算与限制：单容器、300s 批 wall（含 30s 清理预留）、准备≤60s、eval≤120s、操作≤15s、4 CPU/8GiB、network none、pull never、固定 arm64 digest、cycles@99Hz、无模型/重试/扩预算。B 前必须由用户批准新的 R1 完整 identity，并单独取得登记命令的工具权限；预检与 runner 须同一获准环境。失败即停，不创建 R2，不修改旧证据。

仍待 B 验证：真实 Docker socket/镜像实际可用性、PMU attach、容器 PID 映射、正式 evaluator 容器写入、perf/符号/资源测量结果。A 完成，重试未授权，交回原评审。

## 4. 本次 R1 B 执行结果（一次，失败即停）

- 执行前 live 完整 identity 与本交付清单一致，R1 attempt 不存在；用户批准已登记为 `lcq`，批准文件 SHA-256 `06c7a1e4fee7776daf069d826d78c34ae7ed46ff3778d0753f7f6bad46b1391e`。唯一登记命令获得一次工具权限并执行；未重试、未扩预算、未创建 R2。
- 批次：`CPU-02-R1-20260916T073500Z-da94a0fc`。入口返回码 **5**，attempt 最终 `failed`；实际 wall `2.95718143414706 s`，批预算 300 s，未越时。
- 预检：`READY`；固定 endpoint `unix:///var/run/docker.sock`、固定 arm64 digest、record/candidate/perf/evaluator 检查通过。准备阶段 `status=ok`，pinned evaluator `make_test_spec(record)` 生成脚本身份核验通过，candidate 应用通过。
- 停止原因：supervisor 已 ready（容器 PID 45、starttime 已记录），但宿主侧映射失败 `init_ns_unreadable`；因此没有释放 eval，`eval`、`grade`、`perf`、符号解析和资源采样均 absent，无请求/性能/资源测量样本。这是运行基础设施失败，不是 Django 测试结论。
- 清理：`workload_termination.confirmed=true` 且 `container_alive=true` 表示工作负载停止后、删除容器前的中间状态；随后 `supervisor=reaped`、`container=removed` 表示 supervisor 已回收且删除核验完成。两者属于不同清理阶段，不能误读为同一时点的矛盾。
- 产物：`reports/cpu/CPU-02/retries/R1/CPU-02-R1-20260916T073500Z-da94a0fc/summary.json` SHA-256 `3de60757af1527618396e4af36356951e3a46d130c119bbb836e01c480c90a3f`；`manifest.json` SHA-256 `77535024c8aa7859cdc9d828fb636791992498d04517a80418a211586d57ab5e`。manifest 输入 identity 与 attempt identity 一致，输出哈希已回读核验。
- 原 CPU-02 批准、marker、失败批次及 record 原字节未改；R1 批准 SHA 保持不变。结论交回原评审，不宣布 G2 通过。
