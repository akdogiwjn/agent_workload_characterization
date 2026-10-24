# VIDEO-USE-VOLCANO-CAPABILITY-01 摘要

日期:2026-10-21。对既登记火山网关路由(`https://st8tp3ajl0df3n8b8l8qu.apigateway-cn-beijing.volceapi.com/v1`,请求模型 `deepseek-v4-flash`,凭据 `VOLCANO_API_KEY`)的 3 次上限协议/视觉探针,实际发送 **2 次**,第 3 次配额未使用。无重试、无重定向跟随、凭据仅发送前读取且不留存。

## 判定

| 维度 | 判定 | 依据 |
| --- | --- | --- |
| Responses 接口 | **PASS** | probe1:HTTP 200 + SSE 终止事件 |
| SSE 完整性 | **PASS** | probe1:完整 `response.completed` + `[DONE]` 事件流 |
| 工具调用 | **PASS** | probe1:强制 `tool_choice` 下返回合法 `function_call`(call_id `call_7dnio9riw5qwmml331ilzurv`、`smoke_echo`、参数 `{"value": "ok"}` 可解析);Responses 格式,未与 Chat Completions 的 tool_calls 混淆 |
| 工具结果回传 | **FAIL(保守)** | probe2:HTTP 200 + SSE 完成,`function_call_output` 被接受,模型返回 32-hex 文本(与本地生成 receipt 格式一致);但执行期客户端解析缺陷导致文本提取为空而误判,且 receipt 值未存档,**无法字节级核对**。修复解析器后基于已保存事件离线重判(零重发),证据形态强指示回传成功;保守维持 FAIL,确证需单独授权重跑 |
| 图片理解 | **NOT_EXECUTED** | 按停止规则(probe2 非 PASS)未执行;未生成测试图片 |

- 实际请求模型:`deepseek-v4-flash`;响应模型:`deepseek-v4-flash-ga-260731`(probe1/probe2 一致)。
- 客户端发送 2 次、收到响应 2 次(客户端发送观测;网关内部/上游重试次数 unknown)。
- usage:probe1 input 367 / output 70(含 reasoning 24)tokens;probe2 input 473 / output 20 tokens(来自各自 response.completed)。
- 费用:**unknown**(无独立账单证据)。

## 失败归因(问题 2)

- 接口:无(Responses 端点存在且工作)。
- 模型能力:工具调用已证明;工具结果回传**强指示支持但未确证**(归因下条);图片理解未测。
- 认证:无问题(Bearer 通过,200)。
- 暂时无法判断:probe2 的字节级 receipt 核对——归因是**探针自身缺陷**(文本嵌套结构解析错误 + receipt 未存档),不是网关行为异常。

## 边界

三次探针仅覆盖该路由的协议/视觉维度。即使全部通过也不能宣布 Codex CLI 容器运行兼容、video-use 完整流程可用或正式实验 READY。本轮未验证 Codex CLI、未启动 video-use 任务、未安装任何依赖。凭据值未保存、未哈希、未打印;鉴权头与密钥样式文本已从所有留存记录中脱敏。

## 建议(问题 3)

值得进入单独的 Codex CLI 容器兼容验证:Responses 端点与工具调用(最关键的两个协议前提)已 PASS。建议下一轮:(a) 单独授权一次 probe2 重跑(receipt 存档已修复)确证工具结果回传;(b) 同轮或另行授权 probe3 图片理解;(c) 通过后再做 Codex CLI 容器内安装与运行验证。
