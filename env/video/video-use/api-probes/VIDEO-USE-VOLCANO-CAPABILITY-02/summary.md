# VIDEO-USE-VOLCANO-CAPABILITY-02 摘要

日期:2026-10-21。对既登记火山路由(`st8tp3ajl0df3n8b8l8qu...volceapi.com/v1`、`deepseek-v4-flash`、`VOLCANO_API_KEY`)的 2 次上限探针,实际发送 **1 次**;无重试、无重定向、凭据发送前读取不留存。CAPABILITY-01 已通过的 Responses 端点与首次工具调用未重测;旧 probe2 上下文(原输入 + 已存 call_id/arguments)完整重建,未新发工具调用请求。

## 判定

| 维度 | 判定 | 说明 |
| --- | --- | --- |
| 工具结果回传 | **FAIL** | 按发送前固定的严格规则:仅去首尾空白后精确比较。模型回复 `The receipt value is: 12f59889dfed49ed9316cdaa3c4b0a0c`——receipt 值与预期**逐字符完全一致**(随机 32-hex 不可能巧合),但附带说明文字,不满足"仅返回值"。归因分类:**模型输出未满足指令的格式要求**(非探针解析错误、非接口/协议故障) |
| 图片理解 | **NOT_EXECUTED** | 按停止规则(请求 1 非 PASS);剩余 1 次配额未使用,未重发、未调整协议再试 |

- 协议事实:HTTP 200、SSE 完整(`response.completed` + `[DONE]`)、`function_call_output`(call_id 匹配 01 存档的 `call_7dnio9riw5qwmml331ilzurv`)被接受、响应模型 `deepseek-v4-flash-ga-260731`。
- 预期 receipt 在发送前已落盘 `expected-receipt.json`(测试数据,非凭据)。
- 发送/接收:客户端发起 1 次、收到响应 1 次(客户端发送观测;网关内部/上游重试 unknown);usage input 466 / output 26 tokens;费用 **unknown**。

## 归因区分(任务要求)

1. **接口或模型返回未满足要求**:本轮 FAIL 属此类——模型确实从工具结果中接收并复述了 receipt(值逐字符正确,强证据表明回传链路工作),但未遵守"只返回值"的输出格式指令;判定规则发送前固定,不因内容正确而事后放宽。
2. **探针自身错误/证据不足**:无(解析、比较、存档均按设计工作;离线 19 项测试含全部规则回归)。
3. **未执行**:图片理解。

## 结论与下一步

- 内容层面,工具结果回传已连续两轮得到积极证据(01:同格式 32-hex;02:逐字符匹配);本轮 FAIL 是格式遵从问题。对程序化消费响应的客户端(如 Codex CLI 解析 function_call/消息),内容正确性比"裸值输出"更关键,但本项目按固定规则记录 FAIL,不主观升级为 PASS。
- 是否值得进入 Codex CLI 容器兼容验证:**值得,且这是下一个合理步骤**——Responses 端点、工具调用、工具结果的内容级回传均有积极证据;剩余不确定性(输出格式遵从、图片理解)可在 CLI 容器验证轮中一并观察,或另行授权一次图片理解探针。
- 边界:两项探针均未全过;不宣布完整 Codex/video-use 可运行,不构成正式实验 READY。
