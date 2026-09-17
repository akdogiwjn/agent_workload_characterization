# RUN-02-R2 A 阶段交付

日期：2026-09-15。状态：A 离线接线完成；R2 B 已按批准执行一次并停止。
`user_approval=approved`；`tool_execution_permission=granted_for_single_command`。

## 范围与身份

RUN-02-R2 是同一 SWE-bench Verified `django__django-16485` 的一次新 attempt，
不是新 benchmark、任务、模型、镜像或预算。固定任务 record SHA-256 为
`762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`；catalog
`workload_catalog/run_02.yaml` SHA-256 为
`fca2c6f094196d4e4a62c285ed6a3fc230c8e4deded11e0c5f5bab573ed13656`；镜像仍为：

`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`

R2 固定 namespace：

- approval：`reports/resource/RUN-02/retries/R2/APPROVAL.txt`
- one-shot marker：`reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json`
- preflight：`reports/resource/RUN-02/retries/R2/PREFLIGHT.json`
- raw：`data/raw/generated/RUN-02/<new_run_id>/`
- report：`reports/resource/RUN-02/<new_run_id>/`

新身份绑定 R1 失败血缘和 READY-01 成功证据。READY-01 summary SHA-256 为
`cc234ad87b9c00189c20f9ec8c1836a3f762aca36a9ac420b83533b323ac2a65`，manifest
SHA-256 为 `af76a6e481d56488f09031eb0702780dbc928174e2998151ef2f01725a4bf942`。
旧 RUN-02、R1 和 READY 文件未修改；A 前后核验的旧文件哈希见文末。

## 实际修改

- 新增 `runners/run_02_r2_entry.py`：固定 R2 路径与身份，复用
  `run_02_entry` 的 runner、hook、host collector、resource sampler、分析和清理。
- 最小扩展 `runners/run_02_entry.py`：一次性登记后凭据解析失败也写入固定脱敏
  `credentials:<exception_type>` 类别并保留 `failed` marker，runner 调用为零。
- R2 入口在同一执行进程中局部清除大小写代理变量、`SMOKE_APPROVED_PROXY`、
  `DOCKER_CONTEXT`，固定 `DOCKER_HOST=unix:///var/run/docker.sock`，退出时恢复父进程环境。
- 入口在内存中强制选定配置字段精确为 `{env:VOLCANO_API_KEY}`，再调用既有
  `smoke_launcher.load_credentials()`，将值仅映射为 runner 接受的
  `OPENAI_API_BASE`/`OPENAI_API_KEY`；不写 argv、日志或临时 env 文件。
- 新增 `tests/test_run_02_r2.py`；仅调整 R1 过时的“R1 approval 必须不存在”断言为
  namespace 隔离断言，没有修改任何 R1 数据。
- 扩展 mini 的离线 fake transport 断言模式：R2 专用测试不覆盖父进程传入的
  `OPENAI_API_BASE/OPENAI_API_KEY`，在封网请求层只做 URL、Authorization 和代理
  隔离的布尔匹配；既有非 R2 fixtures 继续使用原兼容模式。

缺凭据、引用不符、审批身份漂移、预检失败和重复 marker 均在调用 runner 前拒绝；
首次登记后任何失败都保留 marker，不能删除后重试或创建 R3。

## A 实际测试

```text
PYTHONPATH=src:tests .venvs/swebench-eval-02e7a74/bin/python -m unittest \
  tests.test_run_02_r2 tests.test_run_02_r1 tests.test_run_02 tests.test_smoke_launcher
```

结果：本轮合并执行共 57 项通过，其中原 RUN-02/R1/smoke launcher 回归与 R2 单测通过；
另执行既有明确封网 mini＋fake transport/runtime 链路：

```text
PYTHONPATH=src:tests .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_run02
```

其中 mini 集成 4 项通过，另有 R2 入口专用 fake 配置→真实 loader→真实 mini venv 子进程→
归档/报告链路，未 mock 凭据解析；该链路无 Docker、无 API，真实 mini 子进程通过 fake transport，
验证 hook、宿主进程文件、派生时间线/报告、归档和 one-shot runner 语义。另执行
R2 入口的 fake 配置→内存解析→实际受限子进程环境映射回归，验证父代理污染不进入
子进程，且不输出假密钥值；缺失凭据与错误引用均更新失败 marker 且 runner=0。
`py_compile` 和 `git diff --check` 通过。

## 待批准的唯一真实命令

计划命令（A 已执行，仅输出零副作用计划）：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_r2_entry
```

批准后唯一执行命令：

```bash
cd /home/lcq/agent_workload_characterization
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY \
  -u http_proxy -u https_proxy -u all_proxy -u no_proxy \
  -u SMOKE_APPROVED_PROXY -u DOCKER_CONTEXT \
  PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_r2_entry \
  --execute --i-approve-the-run-02-r2
```

执行工具必须仅为上述登记命令申请一次 `require_escalated`，使预检与 runner 在同一
获准环境访问固定本地 Docker socket。操作员须在该新进程环境安全注入
`VOLCANO_API_KEY`；入口只按选定配置引用在内存中解析，不假定 READY 旧进程环境可继承。
不允许 chmod、sudo、远端 Docker、全局关闭沙箱、代理恢复或永久宽泛权限。

## 预算与限制

预算原样沿用：model requests ≤30、steps ≤30、每请求输出 ≤4096；Agent ≤25 min、
Verifier ≤5 min、总运行 ≤30 min；Docker 预检 ≤60 s；最多 Agent/Verifier 两个顺序
容器，各 ≤4 CPU/8 GiB、`network=none`、`pull=never`；采样 0.5/0.2/0.25 s；
run_dir 检测阈值 5 GiB；自动重试 0。I/O 降级、shared scope、退出后末端计数缺失和
清理语义沿用既有验收口径。

## 当前完整身份哈希

| 文件 | SHA-256 |
| --- | --- |
| `runners/run_02_entry.py` | `11aa5d7d74321beb58778519d386b70416ed83de85f62e417deeb15de9ac740b` |
| `runners/run_02_r2_entry.py` | `c1959f3e775d0947ce68cb413547af3769646c368e6ba41eb8782b0ea9e2ca8a` |
| `runners/coding_pilot.py` | `db935008a9e71a2b8421d13a5d6d9d42d0f4efe6f55d468d6eb15c7530bd7377` |
| `runners/mini_agent_adapter.py` | `e84c62fc17f7ca578cd9f8f5f60bb62810747cbeacf0d930f7dfdcf76007f87b` |
| `runners/container_runtime.py` | `01efadaec9e4c9980aa2474990d72378b09d6c247d85de077ead9b00ad99ffac` |
| `runners/tool_event_env.py` | `0de111c16411b30255b47328912395773330c0b9e6f844f7a62b68dd293e967b` |
| `collectors/host_process.py` | `2ec98884c8b0d1ea005881f72e0a5498088e40960eebc3c44d3775ec2e150055` |
| `collectors/resource_sampler.py` | `8418a9d793e170d96ce75d97ddd65a978a38038f80c2e34eb4c9485286bcca72` |
| `analyzers/run_02_analysis.py` | `b1091969e8a41f00eed2137327b21f6925485c5909aed36f8c27c76512a496fa` |
| `runners/smoke_launcher.py` | `ca0937752bbea1905134ba17f15448072da477de2bed7c650548d50aed592852` |
| `runners/report_writer.py` | `af109af2f2c536d5c50145644debfe0359e9b75dad2d8b39b34cc739286d717b` |
| `tests/test_run_02_r2.py` | `93bf084f837953d928cde8acfa01a1c7db381bd98289032206e122305be33533` |
| `tests/integration_run02.py` | `b3e2061275bcbd07c7369e4404b30adf66f254d6bccfd195cbac8e06b0931c42` |
| `tests/test_run_02_r1.py` | `39848dc0d2d32cbfedd0b12e4a0d147ba167f5b3f66373b7612aea877899fe95` |
| `workload_catalog/run_02.yaml` | `fca2c6f094196d4e4a62c285ed6a3fc230c8e4deded11e0c5f5bab573ed13656` |
| task `record.json` | `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a` |

## 旧证据哈希核验

原 RUN-02：`APPROVAL.txt cf744bf09ac4ba334cf0010dd0be0afdd7859c84046a763bb869f7ef26becd9a`；
`ATTEMPT_STARTED.json 8279e463198d9130496e3f5f43b0aad1d7fa6e42a9e9cfee0a9581f34fa8b437`；
`PREFLIGHT_DIAGNOSTIC.json ed911efcc6a74cf8f8245b7c47ba6c44e51651bb50b21d8a52ee8bf428db2bdc`。

R1：approval `1f9442a7196b14a292b0b3ca1bf0f296bbfc0399328a754f754cac78aeb48d74`；
marker `edebe9f82a3fdf91380b1c71e7c35d9954ed4fa330bd99eac9bbdec99503102d`；
preflight `55768beef63d97f3de6abee4facb17a23e94ba83d5c2abcb88692b65bf5ec96d`。

A 完成后停止，交回原评审；不创建真实 R2 身份文件，不执行 B，不自动重试、扩预算、
恢复代理或创建 R3，不宣布 G1 通过。

## B 单次执行结果：审批身份校验失败，任务未开始

用户批准已登记到 `reports/resource/RUN-02/retries/R2/APPROVAL.txt`，并在执行前核对
task/catalog/image/entry 身份；`VOLCANO_API_KEY` 仅确认非空，未输出值。按交付清单
唯一命令申请一次沙箱外权限并执行：

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY \
  -u http_proxy -u https_proxy -u all_proxy -u no_proxy \
  -u SMOKE_APPROVED_PROXY -u DOCKER_CONTEXT \
  PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_r2_entry \
  --execute --i-approve-the-run-02-r2
```

命令在审批身份校验处返回 `rc=3`（工具 wall `0.459661447 s`），安全输出为
`RUN-02 approval identity mismatch`。字段级只读诊断显示唯一差异为审批内容缺少
入口实际身份要求的顶层 `approval` 字段；其余已登记身份字段一致。按规则未重新登记、
未覆盖审批、未重试。R2 attempt marker 不存在，未执行 Docker 预检，未启动 Agent、
Verifier、容器、模型或 benchmark；没有新增 raw/run/资源测量样本。

这是执行前授权身份阻塞，不是 benchmark 失败。原 RUN-02/R1/READY 证据保持不变，
不创建 R3。后续如需修正审批登记，必须由原评审和用户另行决定。

## 审批身份单字段修正记录

原 R2 批准记录因缺少入口要求的顶层 `checklist_identity.approval` 字段，在执行前
校验阶段被拒绝。按用户授权，未执行 B、未创建 attempt marker，也未改变批准人、
批准时间、任务、模型、镜像、预算或其他身份字段。

- 原文件已独占备份为：`reports/resource/RUN-02/retries/R2/APPROVAL.identity-mismatch.original.txt`
- 备份 SHA-256：`989b8c9825c835274df5633ebb339140d466cccd184d8f6efae70b6cf07f3a64`
- 唯一修改字段：`checklist_identity.approval`
- 修正值：`/home/lcq/agent_workload_characterization/reports/resource/RUN-02/retries/R2/APPROVAL.txt`
- 修正后 APPROVAL.txt SHA-256：`18627b227218957cb6aadeb0836707fb7778cab4e1bf1b7175d67c6f34ae2394`
- 修正后 checklist identity 与实际 R2 `build_plan()["identity"]`：完全相等
- `reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json`：不存在

再次执行仍待用户批准，工具权限待申请；本次修正本身不构成运行授权。

## B 单次执行结果

修正后的批准文件 SHA-256 为 `18627b227218957cb6aadeb0836707fb7778cab4e1bf1b7175d67c6f34ae2394`；
执行前实际 identity 完全匹配，marker 不存在。执行工具仅为登记的唯一命令申请了一次
沙箱外权限；代理变量和 `DOCKER_CONTEXT` 仅在该进程及子进程中清除，固定 endpoint 为
`unix:///var/run/docker.sock`。`VOLCANO_API_KEY` 仅按选定引用在内存中解析并传递，未进入
argv、日志或报告。

结果：run ID `20260915T012427Z-2d75aa`，attempt ID
`20260915T012427Z-2d75aa-a1`，进程返回码 `0`。预检确认 context=default、固定 endpoint、
镜像 `arm64/linux` 与已登记 digest。`execution_status=ok`、`evaluation_status=ok`、
`archive_status=ok`、`cleanup_status=ok`、`report_status=complete`、`resolved=true`。
清理无错误，R2 marker 最终为 `finished`；未重试、未扩预算、未创建 R3。

预算与实际：runner `elapsed_total_s=156.609939194`，无预算越时；Agent wall
`143.651636264 s`（上限 1500 s），Verifier wall `12.264456124 s`（上限 300 s）。
模型请求 `30/30`，steps `26/30`，output tokens `11007`，run-dir artifact bytes
`647461`（未超过 `5368709120`）。两个容器按 Agent→Verifier 顺序运行，网络 none、
pull never；未发生安装或拉取。

观测与资源证据：工具事件 `n_open=28`、`n_closed=28`、`n_error=0`，有效 duration
`28` 条；mini 宿主 `717` 次快照、`716` 次可读，CPU `4.19 s`（首末可读区间），RSS
采样最大 `226713600` bytes，退出末次读取按约定为 `process_exited`。Agent 容器 CPU
`51.007123 core-s`、wall `143.651636264 s`、memory kernel peak
`1434140672` bytes；Verifier CPU `3.64963 core-s`、wall `12.264456124 s`、memory
kernel peak `72548352` bytes。正式 I/O 按既定降级口径为 null；原始诊断计数保留。
覆盖限制仍包括 shared-scope Tool 归因、后代短进程遗漏可能、host kernel peak 未记录，
不将本次结果解释为独占 Tool CPU 或代表性结论。

证据路径：

- raw：[run directory](../data/raw/generated/RUN-02/20260915T012427Z-2d75aa/)
- raw manifest：[manifest.json](../data/raw/generated/RUN-02/20260915T012427Z-2d75aa/manifest.json)，SHA-256 `7718c8003463158bafc219255f765f1d9f168861e84bf23ae99e5b197a5af2f5`
- report：[summary.json](../reports/resource/RUN-02/20260915T012427Z-2d75aa/summary.json)，SHA-256 `ccd65f5d0a9433d81e78ee8d14b26a612aa80118c0f0a1cbfb889dd82bc68bad`
- report：[summary.md](../reports/resource/RUN-02/20260915T012427Z-2d75aa/summary.md)，SHA-256 `580b4754c7dfdfb2d1fb2bded82e95cd663db46e06bd7ec75e7d923464bebb60`
- report：[manifest.json](../reports/resource/RUN-02/20260915T012427Z-2d75aa/manifest.json)，SHA-256 `1d011702dfdf23d4dfd0e71c69ace0e9e138e42465c37d8e663af762d0b3331a`
- attempt marker：[ATTEMPT_STARTED.json](../reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json)，SHA-256 `7c53b96c0e0c800d5af9c09e1737731683911945f6d987f5d60b63dcb4c0ff55`

原 RUN-02、R1、READY-01 证据未修改。单次 B 已完成，交回原评审；本报告不自行宣布
G1 通过，也不授权新的真实运行。
