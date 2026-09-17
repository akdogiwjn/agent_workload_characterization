# RUN-02-R1：Docker 权限修正后的单次重试准备

日期：2026-09-14。当前只准备文档；转发实施提示词可进入 A 离线登记，**不授权实际重试**。执行仍按“任务书＋提示词 → 实施交付 → 原评审核验 → 用户批准单次运行”。

配套：[执行提示词](run_02_r1_execution_prompt.md)、[原 RUN-02 任务书](run_02_handoff.md)、[原交付](run_02_delivery.md)。原任务书的观测、数据安全和研究口径继续有效，本文件只覆盖新尝试身份与执行权限差异。

## 1. 原因已清楚，不重做环境

原 RUN-02 在预检阶段停止，未启动 Agent、模型或 Verifier。依据 [只读诊断](../reports/resource/RUN-02/PREFLIGHT_DIAGNOSTIC.json)：沙箱内 socket 访问 operation not permitted；沙箱外 daemon 可达，固定 digest 存在，arm64/linux。诊断是当时状态，不能保证未来永久可达。

原失败应归类为 Docker socket 访问受限，不能归类镜像缺失或 benchmark 失败。保留以下三个文件原字节并在 A 前后核验 SHA-256：

- `reports/resource/RUN-02/APPROVAL.txt`
- `reports/resource/RUN-02/ATTEMPT_STARTED.json`
- `reports/resource/RUN-02/PREFLIGHT_DIAGNOSTIC.json`

不能删除、改名、覆盖 marker，也不能把旧批准改成新批准。不重新拉镜像、安装、构建、smoke 或复测 B1。

## 2. A：最小离线登记，完成即停

先读 methodology.md、docs/development_tasks.md、references/README.md、references/manifest.yaml；再读本任务书、原 RUN-02 任务书/交付、诊断和语义/数据契约。已验收的采集、分析与清理不重新开发。

### 新身份

采用明确的新尝试标签 `RUN-02-R1`，作为 RUN-02 的重试，不是新 benchmark 或独立 task。优先保持 collection=`RUN-02`，新增固定 attempt namespace：

| 内容 | 目标位置 |
| --- | --- |
| 新批准 | `reports/resource/RUN-02/retries/R1/APPROVAL.txt` |
| 新登记 | `reports/resource/RUN-02/retries/R1/ATTEMPT_STARTED.json` |
| 新预检结果 | 同一 R1 目录下的独占预检证据文件 |
| 成功进入 runner 后的 raw | `data/raw/generated/RUN-02/<new_run_id>/` |
| 新派生报告 | `reports/resource/RUN-02/<new_run_id>/` |

路径是本批设计要求，不代表当前入口已支持。允许最小参数化已有入口的批准/marker 路径及身份，或增加薄 R1 入口复用原实现；不要复制 runner/hook/cleanup。不能开放任意路径参数绕过守卫；固定的 R1 子目录仍须原有 symlink、保护树和独占写入校验。

新 checklist_identity 必须含 attempt_label、旧失败 marker 的路径与 SHA、准确批准/登记/输出路径、实际代码与配置完整 SHA、执行权限范围，以及原 task/model/image/预算。旧入口继续命中旧 marker 并拒绝重复执行；R1 缺批准或已存在 marker 时拒绝。即使预检失败也消耗 R1 槽位，不自动新建 R2。

### 执行环境要求

最终审批明确：仅对登记的 R1 单次执行命令申请工具层沙箱外运行，使其能够访问 `unix:///var/run/docker.sock`。项目批准和工具权限是两道要求，缺任一项都不能运行。

- A 阶段不得申请实际执行提权、调用 Docker、读取凭据、联网或创建真实批准/marker。
- B 批用户批准后，通过执行工具的显式权限申请机制运行登记命令；权限拒绝时停止，不改用旁路、其他 socket、远端 daemon 或 sudo。
- 不改变 socket 权限/所属组、daemon 配置、容器 privileged、挂载或网络，不全局关闭沙箱策略。只为该单次命令申请所需权限，不申请宽泛的 python/bash 永久授权。
- 预检和后续 runner 必须处于同一获准执行环境，禁止“沙箱外检查成功、沙箱内继续执行”。

### 最小错误分类

现有非零 inspect 不得继续统一报告 image_missing。按安全投影区分 socket_access_denied、daemon_unavailable、明确 image_not_found、timeout、unknown；不确定就 unknown，不凭非零码断言镜像缺失。错误原文、环境、认证信息、完整 inspect 不进入终端或报告。

把预检失败保存到 R1 证据并结束新 marker；区分预检耗时与任务耗时。保留 rc=4 的预检失败语义，不发起真实探测来开发分类器，使用模拟返回值测试即可。

### 最小验收

1. 旧 marker 存在不被改写；旧批准不能授权 R1；R1 缺批准、身份漂移、重复登记均拒绝，原子登记保留。
2. 默认计划不触达 Docker/网络/凭据；新状态目录保护和独占写入有效。
3. mock 预检覆盖访问拒绝、daemon 不可达、明确镜像缺失、未知错误、成功；失败有脱敏证据，runner 调用次数为零。
4. fake runner 经过 R1 入口跑通身份→预检→登记/执行→原报告链；重复执行不新增 runner 调用。保留原安全顺序：批准核对及一次性登记在外部操作之前。
5. 复用已有 RUN-02 回归和明确封网 mini 集成，不为此次身份调整重跑全部研究任务或真实容器验证。报告实际命令/数量，不照抄历史数字。

交付 `docs/run_02_r1_delivery.md`，给出唯一最终清单：真实可运行解释器/module/argv、请求工具权限的方式、完整身份哈希、原失败血缘、测试与限制。执行命令必须实现后登记，本任务书不提供猜测命令。标 `user_approval=pending`、`tool_execution_permission=pending`。A 后停止交回评审。

## 3. B：另行批准后只执行一次

冻结不变的范围：SWE-bench Verified `django__django-16485`；mini 2.4.6、evaluator 02e7a74 现有 venv；既有 DeepSeek-V4-Flash 网关路由；固定原任务 record SHA。

镜像保持：`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`。不得换 tag/digest 或自动 pull。

| 约束 | 上限／语义 |
| --- | --- |
| 尝试次数 | R1 一次；预检失败或任务失败均停止，不自动重试 |
| 预检 | 独立 ≤60 秒，本地固定端点与现有镜像，无安装/构建 |
| 模型请求／step | 各 ≤30；三层自动重试禁用，格式错误请求计入 |
| 输出 token | 每请求 ≤4096 |
| 运行 wall | Agent ≤25 分钟、Verifier ≤5 分钟，总运行 ≤30 分钟 |
| 容器 | Agent/Verifier 最多两个、顺序，各 ≤4 CPU/8 GiB，network none、pull=never |
| 新产物 | run_dir 5 GiB 检测阈值，不是容器可写层配额 |
| 采样 | 容器 0.5 秒、mini 宿主 0.2 秒、产物监控 0.25 秒 |
| 模型费用 | 不新增费用上限；未知价格记 unknown＋usage，不当免费 |
| 网络凭据 | 仅获选宿主模型网关；既有环境变量认证仅执行时读入内存；若需要代理须另列批准，不隐式继承 |

未授权新的 smoke、镜像恢复、第二个 benchmark、PMU/perf 或规模实验。权限环境改变不扩大清理范围；只清理本次身份匹配容器/子进程。沿用 I/O 降级、shared_scope、退出末边界可缺失、清理越时如实记录。

运行完成交付：新尝试与旧预检失败分开统计，任务未启动时不能生成虚假 task outcome；预检、三状态、清理、工具/宿主/容器证据、报告与哈希按原任务书交付。已有 R1 marker 时只读交付，不清除再执行。停止交回原评审，G1 不自动通过。

## 4. 集中收尾原则

本批只解决“独立重试身份＋正确执行权限＋预检错误分类”。不重做已验收观测链，不因历史措辞或已接受降级开启返修。只有授权、安全、一次性限制、证据保存或本批入口不可运行的问题阻塞；一次集中列出。
