# RUN-02-R1 A 阶段交付

日期：2026-09-14。状态：A 离线准备完成；`user_approval=pending`；
`tool_execution_permission=pending`；未执行 B、未调用 Docker、未申请或执行真实权限探测。

RUN-02-R1 是原 RUN-02 预检失败后的固定一次重试 namespace，不是新 benchmark、
新 task 或新预算。原 RUN-02 失败记录保留原字节，未删除、覆盖或重新登记：

| 原文件 | SHA-256 |
| --- | --- |
| `reports/resource/RUN-02/APPROVAL.txt` | `cf744bf09ac4ba334cf0010dd0be0afdd7859c84046a763bb869f7ef26becd9a` |
| `reports/resource/RUN-02/ATTEMPT_STARTED.json` | `8279e463198d9130496e3f5f43b0aad1d7fa6e42a9e9cfee0a9581f34fa8b437` |
| `reports/resource/RUN-02/PREFLIGHT_DIAGNOSTIC.json` | `ed911efcc6a74cf8f8245b7c47ba6c44e51651bb50b21d8a52ee8bf428db2bdc` |

## 实际修改

- 新增 `runners/run_02_r1_entry.py`：薄 namespace wrapper，只临时绑定 R1
  approval/marker/preflight 路径，复用 RUN-02 runner、hook、collector、分析和清理。
- 最小扩展 `run_02_entry.py`：支持固定 namespace 守卫、R1 失败证据、预检错误安全分类，
  不改变原 RUN-02 默认路径。
- 最小扩展 `report_writer.py`：保护 `reports/resource/RUN-02/retries/R1` 的逐级真实路径。
- 新增 `tests/test_run_02_r1.py`：旧血缘不变、R1 原子单次登记、旧批准隔离、预检分类和
  合成成功路径回归。
- 本文档记录 A 交付。未修改 references、旧源、封存运行或历史报告。

## 固定 R1 身份与输出

- collection：`RUN-02`；attempt label：`RUN-02-R1`。
- task：`django__django-16485`；record SHA-256：
  `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`。
- image：原固定 ARM digest，不改 tag/digest；model：`openai/deepseek-v4-flash`。
- mini venv：`.venvs/mini-swe-agent-2.4.6-env01`；evaluator venv：
  `.venvs/swebench-eval-02e7a74`。
- R1 approval：`reports/resource/RUN-02/retries/R1/APPROVAL.txt`。
- R1 marker：`reports/resource/RUN-02/retries/R1/ATTEMPT_STARTED.json`。
- R1 preflight evidence：`reports/resource/RUN-02/retries/R1/PREFLIGHT.json`。
- 成功进入 runner 后 raw：`data/raw/generated/RUN-02/<new_run_id>/`；报告：
  `reports/resource/RUN-02/<new_run_id>/`。
- 原 RUN-02 approval 不会授权 R1；R1 marker 已存在时只读交付，不删除再执行。

## 预检错误分类

固定本地 socket 的非零结果不再统一解释为镜像缺失。脱敏分类为：
`socket_access_denied`、`daemon_unavailable`、`image_not_found`、`timeout`、
`unknown`。分类只使用 mock stderr 模式，不在 A 阶段调用 Docker。R1 预检失败会在
固定 R1 evidence 文件保存类别和 marker failure 状态，原始错误不写入交付报告。
预检 wall 与 Agent/Verifier wall 分开，仍为 ≤60 秒预检、原 25/5/30 分钟运行预算。
仅 `subprocess.TimeoutExpired` 分类为 `timeout`；`PermissionError` 分类为
`socket_access_denied`，`FileNotFoundError` 及其他无法可靠判定的异常分类为
`unknown`，不输出异常原文。

本轮新增实际 R1 入口链路合成回归：旧批准 JSON 被拒绝且 `runner.run()` 调用为零；
R1 批准首次调用成功、第二次因 marker 拒绝且不再次调用；预检失败写入 R1
`PREFLIGHT.json` 并更新失败 marker，`runner.run()` 调用为零；回归前后原 RUN-02
三件失败文件哈希一致。

## B 前唯一命令与权限要求

计划命令（A 实际运行，零副作用）：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_r1_entry
```

批准后唯一执行命令：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_r1_entry \
  --execute --i-approve-the-run-02-r1
```

该命令必须同时满足用户批准和执行工具的单次沙箱外权限批准；执行工具需对这条
命令显式使用 `sandbox_permissions=require_escalated`，使预检与 runner 在同一环境访问
`unix:///var/run/docker.sock`。不允许 chmod、sudo、远端 Docker、替代 socket、关闭全局
沙箱或宽泛永久 python/bash 授权。A 阶段不申请该权限。

## 原有预算与风险

预算完全沿用：model requests ≤30、steps ≤30、每请求 output ≤4096；Agent ≤25 min、
Verifier ≤5 min、总运行 ≤30 min；预检 ≤60 s；最多 Agent/Verifier 两容器，各 ≤4 CPU/8 GiB、
`network=none`、`pull=never`；采样 0.5/0.2/0.25 秒；run_dir 5 GiB 检测阈值；自动重试 0。
主要风险是获准 socket 环境在 B 时仍不可达、daemon 状态变化或固定 digest 不可用；均须
分类记录并停止，不扩大权限或创建 R2。

## A 实际测试

计划命令：

```text
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m agent_workload_characterization.runners.run_02_r1_entry
```

结果：计划 JSON 生成并通过 `json.tool`；未触达 Docker/网络/凭据。

限定回归命令：

```text
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest \
  tests.test_run_02_r1 tests.test_run_02 tests.integration_run02 tests.test_coding_pilot
```

结果：本轮 R1/RUN-02/mini 集成定向回归 22 项通过；`py_compile` 和 `git diff --check` 通过。未重跑全部 145 项、真实 smoke、B1
或全量研究任务。

## 当前完整身份哈希

| 文件 | SHA-256 |
| --- | --- |
| `src/agent_workload_characterization/runners/run_02_entry.py` | `108e939749fc3f20f90a79d56139c6f90b0984e6df2ab3a6e96c26091e1ef67d` |
| `src/agent_workload_characterization/runners/run_02_r1_entry.py` | `cefe94bacd8a8fb5d678e49a12d5da91f7bcab467a60515d96fae8739a6a754e` |
| `src/agent_workload_characterization/runners/report_writer.py` | `af109af2f2c536d5c50145644debfe0359e9b75dad2d8b39b34cc739286d717b` |
| `src/agent_workload_characterization/analyzers/run_02_analysis.py` | `b1091969e8a41f00eed2137327b21f6925485c5909aed36f8c27c76512a496fa` |
| `src/agent_workload_characterization/runners/coding_pilot.py` | `db935008a9e71a2b8421d13a5d6d9d42d0f4efe6f55d468d6eb15c7530bd7377` |
| `src/agent_workload_characterization/runners/container_runtime.py` | `01efadaec9e4c9980aa2474990d72378b09d6c247d85de077ead9b00ad99ffac` |
| `workload_catalog/run_02.yaml` | `fca2c6f094196d4e4a62c285ed6a3fc230c8e4deded11e0e5f5bab573ed13656` |
| `tests/test_run_02_r1.py` | `7312bc41c7526f71bb359e541ae8fdc508565dd0dec9da5815e39ecb284a7d64` |

附加完整接线代码哈希在 R1 计划的 `identity.code_sha256` 中保留，R1 wrapper 自身和
`report_writer.py` 由 `entry_code_sha256`/`support_code_sha256` 登记。A 完成后停止，
交回原评审；不自行宣布 G1 通过。

## R1 B 一次执行结果

用户批准后，批准身份与执行前重新生成的完整 identity 逐字段匹配。批准记录：
`reports/resource/RUN-02/retries/R1/APPROVAL.txt`，SHA-256：
`1f9442a7196b14a292b0b3ca1bf0f296bbfc0399328a754f754cac78aeb48d74`。

实际唯一命令：

```bash
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_r1_entry \
  --execute --i-approve-the-run-02-r1
```

该命令已获得一次性沙箱外执行权限。预检与 runner 处于同一 Docker socket 环境；
固定 context/endpoint 和 digest inspect 通过。随后凭据门禁发现
`PILOT_API_BASE`、`PILOT_API_KEY` 未设置，命令返回码 `3` 并停止。未启动 runner、
Agent/Verifier 容器或模型请求，未生成 raw/report 运行样本，未重试或扩预算。

本次应记为“R1 预检通过、凭据门禁失败，真实任务未开始”，不是 benchmark 失败，
也没有新增资源测量样本。工具命令 wall 约 `0.5 s`。

证据：

- [R1 marker](../reports/resource/RUN-02/retries/R1/ATTEMPT_STARTED.json)，最终状态
  `failed`，SHA-256：`edebe9f82a3fdf91380b1c71e7c35d9954ed4fa330bd99eac9bbdec99503102d`。
- [R1 preflight](../reports/resource/RUN-02/retries/R1/PREFLIGHT.json)，记录预检通过、
  runner 未启动，SHA-256：`55768beef63d97f3de6abee4facb17a23e94ba83d5c2abcb88692b65bf5ec96d`。
- 原 RUN-02 三个失败文件未修改，哈希保持原登记值。

R1 已按一次 attempt 失败即停，交回原评审；不创建 R2，不自行宣布 G1 通过。
