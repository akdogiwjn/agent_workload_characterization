# RUN-02 A 阶段交付：独立 attempt 联合观测准备

日期：2026-09-14。状态：**集中反例修订完成；待集中验收；`user_approval=pending`；未执行 B。**

本交付依据 `docs/run_02_handoff.md` 与 `docs/g1_consolidated_review.md`。
RUN-02 仍是同一 SWE-bench Verified `django__django-16485` 的下一次独立
attempt，不新增 benchmark，不重跑 G1-01 B1，不修改 RUN-01-C 原始数据。

## 范围与安全边界

- 本阶段未调用 Docker（包括只读查询），未启动容器，未发送模型/API 请求。
- 未联网、安装、下载、拉取或构建；未读取凭据值；未执行 benchmark 或 verifier。
- 未修改 `references/`、旧源、封存运行或历史报告；未提交/推送 Git。
- 真实 mini 验证使用已有 mini 2.4.6 venv、fake transport 和 fake 环境；HTTP
  transport 在子进程内被拦截，工具执行脚本为合成输入。
- `user_approval=pending`；未创建 `reports/resource/RUN-02/APPROVAL.txt`。

## 实际修改

| 文件 | 用途 |
| --- | --- |
| `src/agent_workload_characterization/runners/run_02_entry.py` | 独立 RUN-02 计划/执行入口；固定任务、镜像、catalog、解释器、预算与批准门禁；完整身份哈希、一次性 attempt 登记、本地 Docker 预检和派生报告接线。 |
| `workload_catalog/run_02.yaml` | 独立 RUN-02 配置与预算提案，`execution_authorized: false`。 |
| `src/agent_workload_characterization/analyzers/run_02_analysis.py` | 只读派生分析：以原生 hook 起止构造 duration，分别报告 duplicate/orphan/unclosed/missing，并核对宿主证据身份/单位/快照。 |
| `src/agent_workload_characterization/runners/coding_pilot.py` | 执行容器固定 `network=none`/`pull=never`；Agent 清理核验后才启动 Verifier。 |
| `src/agent_workload_characterization/runners/container_runtime.py` | RUN-02 使用独立容器命名前缀，避免与 RUN-01 身份混用；Fake runtime 暴露顺序证据。 |
| `tests/test_run_02.py` | 入口隔离、身份、catalog pin、一次性登记、预检拒绝、失败退出和派生文件安全性回归。 |
| `tests/integration_run02.py` | 完整入口→runner→归档→派生报告封网合成集成；验证工具/宿主文件、顺序容器边界和重复执行拒绝。 |

没有复制 hook、runner、budget 或 cleanup 状态机。RUN-02 入口仍调用已有共享
`ToolEventRecordingEnvironment`、`HostProcessMonitor`、`ResourceSampler` 和
清理路径。

## 实际 A 阶段命令与结果

计划命令（零副作用）：

```text
PYTHONPATH=src python3 -B -m agent_workload_characterization.runners.run_02_entry
```

结果：JSON 计划成功生成并通过 `python3 -m json.tool`；计划声明 Docker、网络、
模型和凭据读取均为 false，输出集合为独立 `RUN-02`。

封网真实 mini 集成命令：

```text
PYTHONPATH=src python3 -B -m unittest tests.integration_run02 -v
```

结果：3 项通过。该测试只使用现有 mini venv 的真实 mini 代码；fake HTTP
transport 阻断真实网络，fake environment 不调用 Docker。

新增 A 回归：

```text
PYTHONPATH=src python3 -B -m unittest tests.test_run_02 -v
```

结果：10 项通过。

既有相关回归：

```text
PYTHONPATH=src python3 -B -m unittest tests.test_c_entry tests.test_coding_pilot -q
```

结果：本轮限定相关回归共 136 项通过（`test_run_02`、`integration_run02`、
`test_coding_pilot`）；未重跑既有 135 项集合。另执行了 `py_compile` 和
`git diff --check`，均通过。

## 封网 mini 证据链

RUN-02 集成测试在临时独占目录中完成并随后清理，未写入 raw 运行集合。真实
mini 子进程产生并由现有 harness 写入：

- `mini_tool_events.jsonl`：3 个 open、2 个 closed、1 个 error；非零工具返回
  保留真实语义，异常完成不伪造成 closed；事件只含 command 的 SHA-256/长度，
  不含原始命令或输出。
- `host_process.jsonl`：PID+starttime 身份、CLK_TCK、页大小、原始快照、首末
  可读覆盖和 collector 读取耗时；文件按结构化 JSON 文档读取，不按扩展名误作
  JSONL 行记录。
- `mini_status.jsonl` 与 `mini_trajectory.json`：模型请求边界、退出/提交状态及
  工具动作来源，均为合成 fake transport 结果，不是模型运行证据。

派生分析 `summarize_run_02()` 以 `mini_tool_events.jsonl` 的原生
`t_start_ns/t_end_ns` 构造每次工具 duration，不再使用历史 receipt 时间或固定 0。
duplicate、orphan、unclosed、missing 分别进入 `structural_checks`、
`missing_required_files` 和对应计数；终端 error 保留为未闭合语义，不伪造成 closed。
缺少工具/宿主文件时报告状态为 `partial`，不会返回正常 `complete`。
空工具轨迹只有在 `mini_trajectory.json` 明确显示零工具动作时才按零工具解释；
宿主身份、单位或快照缺失仍为 `partial`。有效 duration 必须来自原生 hook，不能
用空文件或固定零值假完成。
`write_run_02_report()` 已由真实入口在 raw run 封存后调用，独立写入
`reports/resource/RUN-02/<run_id>/`，不覆盖 raw。工具/资源只作 shared-scope
关联，不生成 exclusive Tool CPU；未知值不补零、不插值。

集中反例修订的执行边界：

- identity 现在包含 catalog SHA-256、全部实际接线代码完整 SHA-256 和任务 record
  SHA-256；`ATTEMPT_STARTED.json` 使用 exclusive create，一旦登记即不可再次执行，
  失败也不自动释放重试。
- B 路径固定 `DOCKER_HOST=unix:///var/run/docker.sock`、清除
  `DOCKER_CONTEXT`，在同一 60 秒预检预算内核验 `context=default` 与本地 arm64
  digest；不 pull/build。
- Agent `ContainerSpec` 固定 `network=none`、`pull=never`；Agent stop+verify
  removal 完成后才创建 Verifier，清理失败进入 infra/archive 失败证据。
- 报告和 attempt 状态目录复用独立输出守卫：逐段拒绝软链接、拒绝保护树、拒绝
  已存在目标，并独占创建。
- CLI 对 execution/evaluation 的基础设施失败或 Verifier 超时、清理失败、归档
  失败或派生报告非 complete 返回 `5`；`resolved=false` 且基础设施正常不被误判。
- Agent/Verifier 的 stop、removal verify 和最终 cleanup_run 均使用同一剩余预算；
  每个资源独立尝试，失败/越时保留脱敏 cleanup 状态，不能因前一资源异常跳过后续。

## 待批准的 B 清单（提案，不是授权）

批准前唯一允许的计划入口命令：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_entry
```

用户另行批准 RUN-02 最终清单后，真实一次 attempt 的登记命令为：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_entry \
  --execute --i-approve-the-run-02
```

该命令当前会因缺少 `APPROVAL.txt` 拒绝，不可由 A 阶段自行放行。B 入口会要求
批准记录的 `checklist_identity` 与入口生成的完整身份逐字段相等，并要求
`approved_by`、`approved_at_utc` 存在；仅有命令旗标或任意空文件不能放行。入口还
会检查独占 attempt 登记；已有登记只读交付，不再次执行。

完整身份：

- task：`django__django-16485`；record SHA-256：
  `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`。
- image：
  `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`；
  arm64/v8；`pull=never`。本阶段未查询 Docker 镜像。
- mini interpreter：`.venvs/mini-swe-agent-2.4.6-env01/bin/python`。
- evaluator interpreter：`.venvs/swebench-eval-02e7a74/bin/python`。
- model route：`openai/deepseek-v4-flash`；价格 unknown，不宣称免费。
- credentials：仅在 B 执行时从 `PILOT_API_BASE`、`PILOT_API_KEY` 读取，映射到
  子进程 `OPENAI_API_BASE`、`OPENAI_API_KEY`；值不写入产物。当前未读取。
- proxy：静态计划不要求代理；如实际需要，必须写入用户批准清单，不能隐式使用。

预算提案：1 task/1 attempt；model requests ≤30；steps ≤30；每请求 output
tokens ≤4096；Agent ≤25 min；Verifier ≤5 min；总运行 ≤30 min；预检独立 ≤60 s；
Agent/Verifier 各 ≤4 CPU、8 GiB、network none；`pull=never`；run_dir 5 GiB
检测阈值；资源采样 0.5 s；mini 宿主采样 0.2 s；产物监控 0.25 s；自动重试 0。
5 GiB 是 run_dir 检测阈值，不是容器写层硬配额。I/O 沿用 v1 blkio 降级，正式值
不可用时保留 null 与原因。

输出路径：

```text
data/raw/generated/RUN-02/<run_id>/
reports/resource/RUN-02/<run_id>/
reports/resource/RUN-02/APPROVAL.txt
```

失败即保存并停止；不自动修代码、重试、扩预算或进入下一阶段。真实 B 运行结束后
交回原评审，不自行宣布 G1 通过。

## 完整 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `src/agent_workload_characterization/runners/run_02_entry.py` | `64214bfb76fec72e762cb25873518b78f9b73a4e22172e63180e5984f471fffa` |
| `src/agent_workload_characterization/analyzers/run_02_analysis.py` | `b1091969e8a41f00eed2137327b21f6925485c5909aed36f8c27c76512a496fa` |
| `src/agent_workload_characterization/runners/coding_pilot.py` | `865c08ba4a012a71d13fb307afbacbcb23ff0068232e25c38ab7a4eda54c2806` |
| `src/agent_workload_characterization/runners/container_runtime.py` | `fdcad676f59dfcdfa18f033cba0a277bba5733224a9f5f8bc815f9435891b2f1` |
| `workload_catalog/run_02.yaml` | `fca2c6f094196d4e4a62c285ed6a3fc230c8e4deded11e0c5f5bab573ed13656` |
| `tests/test_run_02.py` | `ec5e6f024308d7070dd7ead964bb3e2b3fda76b4b35a329ed2ef2a6dee0cb453` |
| `tests/integration_run02.py` | `764540dcb3d1d46cb0989e58a927d10d94f76e199a2bb139ef18e121a0917df0` |
| fixed task record | `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a` |

RUN-02 完成 A 阶段，保持 `user_approval=pending`，现在停止。

## 清理失败闭环修订（本轮）

本轮仅修订清理结果契约及其回归。`DockerCliRuntime.cleanup_run()` 现在区分：

- `confirmed`：列表检查成功、删除成功且逐容器 removal verify 确认无残留；
- `failed`：列表成功但删除或删除后核验失败；
- `check_failed`：初始列表检查失败；
- `not_checked`：剩余预算耗尽，未执行检查或无法完成核验。

返回值保持 list 兼容，同时携带 `status`、`errors`、`unconfirmed`。runner 不再
忽略返回值；任何非 `confirmed` 结果都会令 `cleanup_status=failed`，并保留脱敏
错误与未确认容器身份。预算耗尽不会伪造为空列表；未确认资源不会被丢弃。

新增回归覆盖：列表 rc=1、删除 rc=1、零预算，以及实际 runner 消费失败结果。
本轮未调用真实 Docker、网络或模型。

本轮相关完整 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `src/agent_workload_characterization/runners/container_runtime.py` | `01efadaec9e4c9980aa2474990d72378b09d6c247d85de077ead9b00ad99ffac` |
| `src/agent_workload_characterization/runners/coding_pilot.py` | `db935008a9e71a2b8421d13a5d6d9d42d0f4efe6f55d468d6eb15c7530bd7377` |
| `tests/test_coding_pilot.py` | `fdce060449b6c38d7213a0c4e5ab5b246f767b3d40c411237c70717b0f4bdc35` |

本轮定向回归：140 项通过；`py_compile` 与 `git diff --check` 通过。`user_approval=pending`，B 仍未批准。

## 已批准 B 的一次执行结果

用户已批准按当前完整身份执行一次 RUN-02 B。已登记批准记录：
`reports/resource/RUN-02/APPROVAL.txt`，SHA-256：
`cf744bf09ac4ba334cf0010dd0be0afdd7859c84046a763bb869f7ef26becd9a`。
批准绑定的代码/catalog/task/image/model/预算身份与执行前重新计算值一致。

实际执行命令：

```bash
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_entry \
  --execute --i-approve-the-run-02
```

结果：一次性 attempt 已登记，随后本地预检拒绝，返回码 `4`：
`RUN-02 fixed digest image is not locally present`。本次未启动容器、未执行
Verifier、未发模型请求、未读取凭据值、未重试或扩预算。工具侧 wall 约 `0.5 s`
（命令进程从启动到返回）。

失败证据：

- attempt marker：`reports/resource/RUN-02/ATTEMPT_STARTED.json`，最终状态为
  `failed`，failure 为脱敏的 `Run02PreflightError`；SHA-256：
  `30f7b79a3cc4ae283ae64b033cd28caaa8c6d980f3f1d12a4a7fce6522a3e863`。
- 未生成 raw run 目录、报告目录、容器事件、工具事件或宿主观测；这是预检失败，
  不是任务/Verifier 结果。
- 预检只检查了固定本地 Docker context/endpoint 与已登记 digest 的本地存在性；
  未执行 pull/build/install。清理无容器可清理，未进行第二次 Docker 查询。

本次 B 已按失败即停完成；交回原评审复核，不自行宣布 G1 通过。

## 失败原因只读复核

按后续复核要求，仅做了一次本地只读诊断，未重新执行 RUN-02。沙箱内固定
`/var/run/docker.sock` 的 client→server/version、info 和 image inspect 均因
`operation not permitted` 被拒绝；这不能证明镜像缺失。经受控沙箱外只读检查：
Docker client/server 均为 `25.0.5`，daemon 报告 18 个容器、72 个镜像，固定
digest inspect 成功，返回 `arm64/linux`。最终分类为：
`docker_accessible_outside_sandbox_and_fixed_digest_present`。

脱敏诊断证据：[PREFLIGHT_DIAGNOSTIC.json](../reports/resource/RUN-02/PREFLIGHT_DIAGNOSTIC.json)，
SHA-256：`ed911efcc6a74cf8f8245b7c47ba6c44e51651bb50b21d8a52ee8bf428db2bdc`。
原失败 attempt marker 保留且身份未改；已将失败文字修正为“执行沙箱拒绝 Docker
socket，镜像存在性未验证”。没有删除 marker、没有重试、没有启动容器或调用模型。
