# VIDEO-USE-VOLCANO-VISION-01 摘要

日期:2026-10-21。对既登记火山路由的一次图片理解探针,发送 **1/1 次**;无重试、无重定向、凭据发送前读取不留存。01/02 已通过的结论未重测;图片与预期答案在发送前落盘(`neutral-test.png` 512×256 白底、`expected-answer.json`),未发送给模型、未在发送后修改。

## 逐项报告(任务六)

1. **Responses/SSE**:HTTP 200;SSE 流正常终止(`response.incomplete` + `[DONE]`);但响应状态为 **incomplete(`incomplete_details.reason="length"`)**——max_output_tokens 1024 被 reasoning 全部消耗,没有产出任何最终文本。
2. **图片是否成功传入**:请求侧 `input_image`(base64 data URL)已构造并发送,网关接受未报错。但模型 reasoning 摘要(完整保存)显示它收到的是**以 `<image_base64>` 标签包裹、以 `...` 截断的 base64 文本**,并试图从压缩字节推断图片内容("Let's decode the partial base64"、"maybe zlib compressed"、"The base64 seems cut off")——**强旁证指示网关把 input_image 降级为截断文本传给模型,图像未以视觉形式到达**。这是行为证据,非网关显式声明。
3. **视觉内容判断:UNKNOWN**——按发送前固定规则:无有效最终回答(内容不足);FAIL 需明确答错或模型声明不能处理图片,两者均不满足。附注:reasoning 旁证强指示该路由图片降级为文本,即图片理解在该路由很可能不可用,但本轮证据按规则不足以判 FAIL。
4. **回答格式**:无回答可评(N/A;无任何可解析行)。
5. **发送/接收**:1/1(客户端观测;网关内部/上游重试 unknown);请求模型 `deepseek-v4-flash`;响应模型 `deepseek-v4-flash-ga-260731`(incomplete 事件内);usage **unknown**(incomplete 事件超 4000 字符保存上限,usage 字段未完整保留——记录缺陷,非网关故障);费用 **unknown**。
6. **是否进入 Codex CLI 容器兼容验证**:**文本路径值得,视觉路径不值得**。文本+工具调用+工具结果内容回传(01/02)均积极,Codex CLI 容器验证可推进;但若 video-use 完整流程需要视觉自检(timeline_view PNG),该路由强指示不满足——需换支持图像输入的模型/端点(用户决策),或接受视觉降级方案。

## 归因区分

- **网关/模型图片降级(疑似)**:input_image 被转为截断 base64 文本(模型 reasoning 直接引用);网关未显式报"不支持图片"。
- **网络/认证/协议故障**:无(200、SSE 正常终止)。
- **探针侧**:incomplete 事件的 4000 字符保存截断导致 usage 未保留(记录缺陷);判定按固定规则执行,未因旁证改判。

## 边界

一次探针、一张合成图片;UNKNOWN 不等于视觉能力确认存在或缺失的直接证明,但旁证偏向"该路由图片降级为文本"。不代表视觉能力全面结论、不代表完整 video-use 已验证、不构成执行授权。
