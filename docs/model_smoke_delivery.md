# SMOKE-01 交付：单次真实工具协议连通性检查（含根因修复与重试）

日期：2026-09-11。状态：**重试成功；执行完毕并停止**。

## 批准记录

- **首次执行**（SMOKE-01-20260911T073120Z）：用户回复"执行，还是用代理访问外网吧"
- **重试**（SMOKE-01R-20260911T080928Z）：用户回复"继续"（根因修复后同范围重试）

## 首次失败与根因

首次执行返回 `AuthenticationError`。经离线配置核对 + 受控诊断（绕过 SDK 直接请求网关）定位根因：

**配置中 `apiKey` 值为 `{env:VOLCANO_API_KEY}`（环境变量引用），launcher 未解析该引用格式，
把字面字符串当作密钥发送**。网关响应头 `x-auth-failure: key_auth:unknown_api_key` 证实
网关不认识发送的"密钥"。opencode 能正常用是因为其运行时解析 `{env:...}` 引用。

修复（重试前完成）：
- `smoke_launcher.py` 引用检查扩展至 6 种格式（`${}`/`{env:}`/`{ENV:}`/`env:`/`{secret:}`/`{op:}`）
- **新增 `{env:VAR}` → `os.environ` 解析**（真实值仅在内存，不打印/不持久化）
- launcher 测试 25 → 29 项（引用解析/空变量/大小写/不可解析格式）

## 重试执行（唯一一次）

```bash
SMOKE_APPROVED_PROXY=http://127.0.0.1:22111 \
PYTHONPATH=src python3 -B -m agent_workload_characterization.runners.smoke_launcher \
  --config data/catalog/smoke_01_config.yaml \
  --result-dir reports/smoke/SMOKE-01R-20260911T080928Z \
  --batch 20260911T080928Z
```

## 结果

| 项 | 值 |
| --- | --- |
| 退出码 | 0 |
| ok | **true** |
| 语义 | tool_protocol_connectivity |
| 模型路由 | `openai/deepseek-v4-flash` → 请求体 `deepseek-v4-flash`（前缀剥离验证） |
| duration_ms | 5446 |
| usage | prompt=308, completion=69, total=377（合法非负整数） |
| cost | source=0.0（ignore_errors 未知价格路径）；amount=null; cost_status=unknown |
| 重试 | 0（三层全禁） |
| 工具执行 | **未执行**（解析了 tool call，未运行任何命令） |

### 任务书 §6 判定

| 观测 | 结论 |
| --- | --- |
| 已解析 tool call 且 usage 合法 | **本次路由/auth/工具协议可用，usage 可记录；非 benchmark 成功** |

### 已证明

- mini → litellm → openai SDK → 批准代理 → 网关 全链路连通
- Bearer 认证被网关接受
- mini bash tool schema 发送成功且模型按协议返回 tool call
- usage（308/69/377）可从响应提取

### 未证明（SMOKE-01 范围外）

- benchmark 可跑、验证器正确、CPU/Tool 归因有效、性能/成本代表性、长期模型稳定性
- 真实费用（价格未知，不宣称免费）

## 产物

- `reports/smoke/SMOKE-01-20260911T073120Z/`：首次失败记录 + offline_auth_check + verdict（保留不改写）
- `reports/smoke/SMOKE-01R-20260911T080928Z/`：成功记录 + verdict + manifest
- `runners/smoke_launcher.py`（29 项离线测试）、`data/catalog/smoke_01_config.yaml`

## 停止与后续

**SMOKE-01 执行完毕（共两次：一次失败 + 一次修复后成功）。** 不再重试、不换端点/模型。

下一候选（需新任务书与审批）：本地单任务 wrapper + 基础资源观测与镜像准备的合并批次。
P0-07/G0/M1/G1 状态由对应范围证据评审，不因本次连通性成功自动通过。
