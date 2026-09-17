# RUN-02 Launch Readiness A 阶段交付：READY-01

日期：2026-09-14。状态：A 离线准备完成；
`read_only_check_approval=pending`；未执行 B 只读检查；未创建 R2。

## 范围与不变量

- 未调用 Docker（包括只读查询）、网络、API、模型、Agent、Verifier 或 benchmark。
- 未读生产配置或真实密钥，不改用户配置；只使用临时合成配置和假密钥。
- 原 RUN-02/R1 批准、marker、预检证据未改写；未创建 R2 身份、批准或 marker。
- 未重写 runner/collector；READY-01 仅复用 `smoke_launcher.load_credentials()` 和
  `build_restricted_env()`。
- readiness 报告固定在 `reports/preparation/READY-01/<check_id>/`，不是运行授权，
  不创建 raw run 或资源测量样本。

## 唯一凭据注入路线

选定路线为：

```text
选定 OpenCode provider/model 的 {env:VOLCANO_API_KEY}
  → 获准 readiness 进程内存解析
  → smoke_launcher.build_restricted_env()
  → 子进程 PILOT_API_BASE / PILOT_API_KEY
```

生产配置候选路径只登记为 `/home/lcq/.config/opencode/opencode.json`；A 阶段没有
读取它。最终 B 检查时由操作员在同一获准检查进程环境设置 `VOLCANO_API_KEY`；
readiness 代码不 source shell、不读取其他 provider、不在命令 argv、临时 env 文件、
日志、异常原文或报告中保存密钥。子进程只返回 `base_present`、`key_present`、
`proxy_absent`、`docker_host_absent`、`argv_safe` 等固定布尔值。

inline 值、缺失值、空值和未解析引用仅在合成测试中验证；生产选定路线仍固定为
`{env:VOLCANO_API_KEY}`。任何 proxy、非本地 Docker host/context 或不明确错误均拒绝，
不静默切换 endpoint/provider。

## 实际修改

- `src/agent_workload_characterization/runners/run_02_launch_readiness.py`：默认零副作用
  计划；独立 `--check` 逻辑；固定 endpoint/digest 只读检查；内存凭据解析；一个 ≤5 秒
  封网短子进程；READY-01 独占报告。
- `tests/test_run_02_launch_readiness.py`：五组最低回归。
- `docs/run_02_launch_readiness_delivery.md`：本交付和待批准清单。

没有调用 smoke launcher 的 `launch_smoke()`，没有调用模型 SDK 或 RUN-02/R1 入口。

## A 实际命令与结果

计划命令：

```bash
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_launch_readiness
```

结果：计划 JSON 生成并通过 `json.tool`；声明 Docker、网络、API、凭据读取、runner
和 R2 均为 false。

定向回归命令：

```bash
PYTHONPATH=src:tests .venvs/swebench-eval-02e7a74/bin/python -m unittest \
  tests.test_run_02_launch_readiness tests.test_smoke_launcher
```

结果：40 项通过。另执行 `py_compile` 与 `git diff --check`，均通过。没有重跑真实
smoke、RUN-02/R1 B、B1 或全量测试。

覆盖内容：

1. 计划模式不读凭据、不触达 Docker/网络/runner。
2. 合成 `{env:VAR}` 成功、缺失、空值、`${VAR}`/`env:VAR` 未解析引用拒绝。
3. 真实短子进程只接收受限环境，结果只返回固定布尔值；假密钥 canary 不进入报告。
4. 代理、远端 Docker host/context 被拒绝；不会继承未批准环境。
5. 报告软链接/覆盖被拒绝；错误只返回安全类别；原 RUN-02 三个失败文件哈希核对。
6. `run_check()` 对子进程和 Docker 必需项逐项严格要求原生布尔 `true`；false 或非布尔
   结果均为 `NOT_READY`。selected `apiKey` 必须精确为 `{env:VOLCANO_API_KEY}`，inline
   key 和其他引用均拒绝。

## 待批准的最终环境只读检查清单（不是运行批准）

唯一检查命令：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_launch_readiness --check
```

检查要求：

- 总 wall ≤60 秒；自建短子进程最多一个、≤5 秒；报告 ≤1 MiB。
- 只在获批检查进程内存读取选定配置和 `VOLCANO_API_KEY` 引用；不输出值、长度、
  前后缀或 hash。
- Docker 仅检查固定本地 context/daemon/digest；不 pull/build/run，不使用 sudo、
  替代 socket、远端 Docker 或修改权限/配置。
- 不调用 API、模型、smoke、runner、Verifier 或 benchmark。
- 必须由用户另行批准，并由执行工具对这条命令单次申请沙箱外权限；权限拒绝即停止。

成功只表示当时该检查进程的固定环境可用，不证明网关认证成功、后续任务可运行、
凭据会自动传给其他进程，也不授权 RUN-02/R1 重试或证明 G1。
报告中的 task/catalog SHA-256 仅是登记身份；READY-01 不在本批重新读取或核验它们，
报告明确标记为 `registered_not_checked`，不将其解释为全部启动条件已验证。

## 当前身份哈希

| 文件 | SHA-256 |
| --- | --- |
| `src/agent_workload_characterization/runners/run_02_launch_readiness.py` | `6b432998c12ee28af850c6c7bee973474899b8d7cd29584272adf7b965d1cba1` |
| `src/agent_workload_characterization/runners/smoke_launcher.py` | `ca0937752bbea1905134ba17f15448072da477de2bed7c650548d50aed592852` |
| `tests/test_run_02_launch_readiness.py` | `d84f2dba5d0309d9b78f65d11663c8d08ba6c5b7e44e3b65c4a4ffcd39ac50db` |
| `workload_catalog/run_02.yaml` | `fca2c6f094196d4e4a62c285ed6a3fc230c8e4deded11e0c5f5bab573ed13656` |

READY-01 A 阶段完成后停止，交回原评审；不执行 B 检查，不创建 R2，不宣布 G1 通过。

## READY-01 B 只读检查结果

用户批准并授予登记命令单次沙箱外权限后，先在同一获准进程中确认
`VOLCANO_API_KEY` 非空（仅布尔结果，未读取或输出值），再执行唯一检查命令。
检查 ID：`20260914T110734Z-3ab12e`；命令返回码：`4`；wall 约 `0.25 s`。

结果为 `NOT_READY`：固定 Docker host/context 条件为真，但获准进程继承了未批准
代理环境，`proxy_unset=false`，因此在凭据解析/子进程/Docker 检查继续前停止。未调用
API，未启动容器、Agent、Verifier 或 benchmark；没有新增任务或资源测量样本，也未重试。

报告：[READY-01 summary](../reports/preparation/READY-01/20260914T110734Z-3ab12e/summary.json)，
其 manifest：[manifest](../reports/preparation/READY-01/20260914T110734Z-3ab12e/manifest.json)。
报告中的 task/catalog 哈希仍明确为 `registered_not_checked`。本次检查完成后停止，
不授权 RUN-02/R1 重试，不创建 R2，不宣布 G1 通过。

## READY-01 代理清除后的授权重检

用户另行批准仅清除本次进程代理变量后重检一次。执行工具以单次沙箱外权限运行：

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy \
  -u all_proxy -u NO_PROXY -u no_proxy -u SMOKE_APPROVED_PROXY \
  PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.run_02_launch_readiness --check
```

检查 ID：`20260914T111017Z-7eb3c4`；状态：`READY_FOR_APPROVAL`；返回码 `0`；
检查内部 elapsed `0.054518 s`，工具 wall 约 `0.56 s`。该进程内代理变量均未设置；
选定配置解析、子进程布尔传递、固定 Docker context/endpoint/digest 的只读检查均为真。
`api_called=false`、`task_started=false`、`container_started=false`。task/catalog 仍为
`registered_not_checked`，不代表本次重新核验。

证据：[summary.json](../reports/preparation/READY-01/20260914T111017Z-7eb3c4/summary.json)
SHA-256：`cc234ad87b9c00189c20f9ec8c1836a3f762aca36a9ac420b83533b323ac2a65`；
[manifest.json](../reports/preparation/READY-01/20260914T111017Z-7eb3c4/manifest.json)
SHA-256：`af76a6e481d56488f09031eb0702780dbc928174e2998151ef2f01725a4bf942`。

本次仅证明该获准检查进程在当时可用，不证明网关认证成功，不授权新的真实运行或
R2，也不宣布 G1 通过。
