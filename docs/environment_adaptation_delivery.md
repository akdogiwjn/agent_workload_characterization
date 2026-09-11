# ENV-01 环境适配交付

日期：2026-09-11。批次：ENV-01。状态：**安装与离线适配完成；真实 smoke 未执行（另批审批）；
执行未授权；G0/G1 不因本批通过**。

## 前情与本次范围

首轮下载因网络吞吐（<75 KB/s 直连）阻塞；用户提供本地代理（127.0.0.1:22111）后重试成功。
本批完成：独立环境安装、真实 SDK 离线适配验证、smoke 入口与审批清单更新。
未拉镜像、未运行容器、未调用真实模型、未运行 benchmark。

## 实际操作与结果

### 1. wheelhouse 下载（代理后重试）

```text
方法:  pip download（PyPI 无认证、--no-cache-dir、--only-binary :all:、约束文件来自 uv.lock+METADATA）
代理:  用户提供的本地代理仅作传输通道
结果:  77 wheels / 132 MB；逐包 SHA-256 清单 → data/raw/software/env01/wheelhouse_manifest.json
```

### 2. 独立环境安装

```text
路径:  .venvs/mini-swe-agent-2.4.6-env01（无 system-site-packages；.gitignore 已覆盖）
方法:  pip install --no-index --no-cache-dir --find-links <wheelhouse> <mini wheel>（完全离线）
校验:  wheel SHA 匹配锁值；pip check "No broken requirements found"；79 包安装
入口:  mini/mini-extra --help 可用；mini 2.4.6 / litellm 1.100.1 / openai 2.54.0
原环境: 零变更（未安装/升级任何系统包）
```

### 3. 离线适配验证（安装版真实 SDK，fake transport，网络三层封禁）

关键实证（此前静态阅读的更正与确认）：

| # | 事实 | 与静态结论的差异 |
| --- | --- | --- |
| 1 | `openai/` 前缀路由：URL=api_base+`/chat/completions`（**无 /v1 重复**），请求 model 字段去前缀 | 与预期一致 |
| 2 | ~~litellm 忽略 model_kwargs 凭证~~ **更正（复核轮）**：mini 将 model_kwargs 展开为 litellm.completion 顶层参数，`api_base`/`api_key` **生效**（实证：mini+fake transport，URL/auth 正确）。此前"被忽略"是旧测试嵌套传参的 bug | 静态阅读与首轮测试双重误判；评审人实证更正。env-var 路线**保留**，理由改为：**防止 mini 把 model_kwargs 逐字序列化进轨迹**（见第 3 行与 S3 测试） |
| 3 | 凭证走环境变量后 model_kwargs 保持无密钥 → mini 轨迹 config 不含密钥 | ~~根除~~ **限定表述**：已测路径（`m.serialize()` 输出、消息对象、自有 record、结果文件）实证无密钥（S3 测试）；litellm 运行时异常链中网关回显文本仍可能含敏感内容（第三方行为），操作规范：原始 traceback 不入报告 |
| 4 | 成本：`default` 模式对未知价格 RuntimeError（实证）；`ignore_errors` 静默 0.0；适配层按 cost_tracking 语义把 0.0 记为 `cost_status=unknown`（来源值保留） | 与静态一致，语义在适配层落实 |
| 5 | **三层重试**：任务 attempt（外层）/ mini tenacity（默认 10 次，`MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1` 禁用）/ **litellm-openai SDK 内部重试（默认额外 2 次，`num_retries=0` 禁用——静态阅读未发现的第三层）** | 静态只识别两层；第三层已实证（500 响应默认 3 次尝试）并纳入适配层默认配置 |
| 6 | mini 消息 extra **无顶层 usage**；usage 在 `extra.response.usage` | 适配层读取路径已修正 |

### 4. 测试与验证（实际执行）

```text
默认项目测试（不依赖 SDK）:  231 OK（项目内 + 项目外 cwd 绝对路径）
显式集成测试（ENV-01 venv）: 10 OK（tests/integration_env01.py）
  - 网络封禁：httpx.HTTPTransport 类级拦截 + litellm 客户端缓存逐测试清空
    （in_memory_llm_clients_cache——跨测试污染根因，已修复）+ LITELLM_LOCAL_MODEL_COST_MAP=True
  - 覆盖：URL/auth/model 构造、/v1 无重复、凭证作用域恢复、mini 全链 tools/usage、
    未知价格 RuntimeError、ignore_errors 保留 usage、重试禁用后失败=1 次请求、
    401 错误脱敏、缺 env/userinfo URL/model_kwargs 带密钥 均拒绝
git diff --check: OK
```

### 5. smoke 入口

`runners/smoke.py`：默认离线输出计划（不发送）；`--execute` 需叠加 `--i-approve-the-smoke`
双确认，且 ENV-01 不执行真实请求。计划内容：单条非任务消息、≤100 token、总 30s、
0 自动重试（三层全部禁用配置已内置）、费用未知即 unknown。

## 交付物

- `runners/model_adapter.py`（resolve/sdk_credential_scope/mini_model_config/record_sdk_call）
- `runners/smoke.py`（离线计划 + 双门真实模式）
- `tests/integration_env01.py`（10 项显式集成测试）
- `data/catalog/env01_environment.json`（环境登记，无密钥）
- `reports/preparation/ENV-01/`（environment_snapshot/offline_checks/manifest）
- 本文件；`docs/first_run_approval.md` smoke 部分已更新为确切命令

## 预算用量

| 项 | 上限 | 实际 |
| --- | --- | --- |
| 下载量 | 1 GiB | 132 MB（77 wheels） |
| 新增磁盘 | 3 GiB | ~500 MB（wheelhouse 132MB + venv ~350MB） |
| 下载/安装时间 | 15 分钟 | 代理后 ~6 分钟（首轮直连失败已如实记录） |

## 仅离线验证（不冒充真实）

真实网关是否接受请求、真实路由别名、镜像 digest、容器运行、第三方日志在真实进程中的表现
——均未验证，属 smoke 批次与 P1-00。litellm 导入时的远端价格表获取在测试中被
`LITELLM_LOCAL_MODEL_COST_MAP=True` 禁用（官方离线开关）；**真实运行时该开关是否保留需在
smoke 审批中确认**（保留=完全离线定价；不保留=litellm 可能拉远端价格表，已列入清单）。

## 返修记录（用户复核意见，2026-09-12）

| # | 问题 | 修复 |
| --- | --- | --- |
| S1 | smoke 执行入口是占位 | 实现真实单请求路径 `execute_smoke`（SIGALRM 30s 总 deadline、≤100 token、三层重试全禁、结果脱敏落盘 `reports/smoke/<run-id>.json`）；`--execute --i-approve-the-smoke` 双门生效；5 项 fake-transport 测试（单请求/失败即停/文件脱敏/缺 env 拒绝/CLI 双门） |
| S2 | "litellm 忽略凭证参数"结论错误 | 确认评审人实证：mini 顶层展开后 model_kwargs 凭证**生效**（旧测试嵌套传参 bug）；更正文档与测试（新增 `test_model_kwargs_credentials_DO_work_via_mini`）；env-var 保留理由改为**防序列化泄漏** |
| S3 | 序列化/异常回显证据不足；offline_checks.json 缺失 | 新增 `SerializationLeakTests`（`m.serialize()` 含密钥路径实证 + env-var 路径全序列化无密钥 + 异常回显 canary 不入自有产物）；集成检查结果落盘 `offline_checks.json` 并入 manifest；"根除"表述限定为已测路径 |

集成测试 10 → **19 项**（全 OK）。

## 下一步（等待审批）

**模型连通性 smoke**（批准后执行，详见 [first_run_approval.md](first_run_approval.md) 批准项 2）：

```bash
cd /home/lcq/agent_workload_characterization
# 先注入（会话内）：PILOT_API_BASE=<网关 base URL 含 /v1>、PILOT_API_KEY=<真实密钥>
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  LITELLM_LOCAL_MODEL_COST_MAP=True MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1 \
  PYTHONPATH=src \
  .venvs/mini-swe-agent-2.4.6-env01/bin/python -m agent_workload_characterization.runners.smoke \
    --execute --i-approve-the-smoke
```

（`PYTHONPATH=src` 为必需——独立 venv 不安装本项目包；首轮命令遗漏已修正。）

单请求、非任务消息、30s 总限、0 重试（三层全禁）、费用 unknown 记录 usage、失败即停。
成功仅记录路由事实，不启动 benchmark。ENV-01 到此停止。

## 返修记录（用户复核意见，2026-09-12 第二轮：smoke 真实 SDK 路径）

| # | 问题 | 修复 |
| --- | --- | --- |
| F1 | 100 token 上限未传给 SDK | `max_tokens=100` 注入 model_kwargs（litellm 顶层展开后进入**真实请求体**）；测试断言 fake transport 捕获的出站请求体 `body["max_tokens"]==100`，非仅报告回显 |
| F2 | 正常回答被判失败 | 语义明确为 **tool-protocol connectivity**（实证：mini 硬编码 BASH_TOOL 且解析器强制 tool-call——plain-text 回复必触发 FormatError，model_kwargs 传 tools 会造成 duplicate-kwarg TypeError）。成功条件=收到 tool-call 回复含 usage；plain-text 回复记 `unexpected_plain_text` 且 **usage 保留**（从 FormatError messages 提取） |
| F3 | 超时静默降级 | 非主线程/无 SIGALRM 时**请求前拒绝**（`DeadlineExceeded` 抛出，transport 计数=0 断言）；补真实触发测试（慢 transport 3s + deadline 1s → DeadlineExceeded；含第三方包装异常检测：alarm 在第三方 except 内触发被包装时按 wall-clock 判定） |
| F4 | writer 绕过保护 | `guard_result_dir`：锚定项目根、`reports/smoke` 包含、catalog 旧源根+references+data 保护、symlink 拒绝、**请求前验证**（invalid 位置 → transport 计数=0）；结果文件独占创建（`open("x")`，重复写 FileExistsError 断言） |

测试重构：FakeSdk（忽略配置、掩盖缺口）→ **真实 mini LitellmModel + fake httpx transport**；
集成 19 → **20 项**（+5 真实 SDK smoke 测试、-4 FakeSdk 占位）。
语义变更已同步 plan/文档（tool-protocol connectivity）。

## 返修记录（用户复核意见，2026-09-12 第三轮：硬 deadline + 序列化回归恢复）

| # | 问题 | 修复 |
| --- | --- | --- |
| 1 | deadline 可被吞掉失效（fake transport 捕获 alarm 后 ~1.2s 仍 ok=True） | **重设计为子进程 watchdog**：查询在子进程运行，父进程 `communicate(timeout=deadline_s)` + 超时 `proc.kill()`（SIGKILL，SDK 不可捕获）。测试：AlarmSwallowTransport（吞 alarm + 睡 3s）→ 子进程被杀、DeadlineExceeded(killed)、永不为 ok=True；SlowTransport → 同样硬停 |
| 2 | SerializationLeakTests 被删除、报告仍标 true | 恢复三项序列化回归并实际运行：serialize 含密钥路径（文档化第三方行为）、env-var 路线 serialize/msg 无密钥、异常回显 canary 不入自有产物 |
| 3 | F2 语义未对齐 | 消息改为请求一个**无害 tool call**（`echo smoke-ok`，只解析不执行）；record `semantics="tool_protocol_connectivity"`；plan/docstring 同步 |
| 4（返修中发现） | `_captured_requests`（含 auth 头/完整 URL）被写入结果文件——**真实凭据泄漏路径** | 落盘前剥离 `_captured_requests`（仅测试内存证据，永不持久化）；canary 文件断言验证 |

附带：子进程捕获的出站请求体经 `_captured_requests` 回传父进程，测试断言
`body["max_tokens"]==100`、bash tool schema、请求数=1——全部基于真实 SDK 出站请求。
集成测试 20 → **23 项**（+swallowed-alarm 硬停、+3 序列化回归恢复；FakeSdk 时代测试已全部替换为真实 SDK）。

## 返修记录（用户复核意见，2026-09-12 第四轮：子进程 fake transport 行为模式 + started 证据）

| # | 问题 | 修复 |
| --- | --- | --- |
| 1 | `_transport` 只提取 responses/status，子进程重建固定 `_FT`，不执行测试里的延迟/吞 alarm 逻辑；两个超时测试可能只是子进程导入 SDK 耗尽 1s | 子进程实现 `_fake_delay_ms` / `_fake_swallow_alarm` **行为模式**（经 payload 序列化，在子进程的 handle_request 内真实执行：delay=睡眠、swallow=装 1s 一次性 SIGALRM 并吞掉 + 睡 60s） |
| 2 | 无"查询已开始"的同步证据 | **started-marker 侧信道**：子进程 handle_request 进入即刻写标记文件（先于任何延迟）；父进程 kill 后检查该文件 → `request_started_before_kill` 字段 |
| 3 | 离线封网只在父进程（monkeypatch 不随 Popen 继承） | **子进程内独立封网**：fake 安装前对 `httpx.HTTPTransport.handle_request` 类级替换为 NetworkViolation 拒绝 |
| 4 | deadline=1s 杀在导入期（marker 诚实 False——首次运行即暴露） | 测试 deadline 调整为 10s（覆盖 ~3s SDK 冷导入）+ in-child delay 12s / swallow 60s：导入 → 请求开始（marker）→ 阻塞 → 10s SIGKILL。**证据链完整**：marker 证明请求开始、killed 错误证明硬停、ok 永不为 True |

修正后的语义证据：此前第三轮两个超时测试通过确属导入期耗尽（评审判断正确）；本轮
started-marker 首跑即证伪并修正。集成测试仍为 **23 项**（两个超时测试重写为模式化 + 证据链断言）。
