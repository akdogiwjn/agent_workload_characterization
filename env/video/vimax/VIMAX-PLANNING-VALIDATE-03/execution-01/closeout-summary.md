# ViMax 规划验证 03 收尾摘要

## 上次不兼容点及实际触发条件

`VIMAX-PLANNING-VALIDATE-02` 保存的规划中，第 3 镜头为 `large`，第 5、6 镜头为 `medium`。这三个枚举会进入 `script2video_pipeline.py` 的 medium/large 分支：额外生成 `last_frame`，并在视频请求中传入 first+last 两张图。当前适配器的 `wan2.6-i2v-flash` 路径只接受单张首帧参考；这才是能力冲突。schema 中必需的 `lf_desc`/`lf_vis_char_idxs` 是字段本身，不会单独触发末帧图片生成。本轮没有修改历史规划来试错。

## 结果

- 命名空间：`VIMAX-PLANNING-VALIDATE-03`
- run_id：`vimax-planning-validate-03-20261024T014216Z-3d8d561a`
- attempt：1；retry：0
- 规划契约：通过。session 为 `script`，冻结剧本 SHA-256 `447e4d88ccd76f9cb4a206f799993620a3c832238dd873c9ae9e905c2452b59a`；原生工具成功返回。人物 1 项、storyboard 8 项、shot descriptions 8 项、camera tree 8 项。索引和顺序、schema、人物/相机引用、相机树无环及八镜头覆盖均通过。
- 首帧视频能力预检：通过。真实生成约束到达 storyboard、shot decomposition、camera tree 节点。8 项 shot description 的 `variation_type` 都是 `small`；schema 要求的 `lf_desc` 等文字字段保留。最终能力预检无拒绝项。
- 内容核对：主要人物、场景和动作顺序与冻结脚本相符。部分镜头把原计划的运镜简化为静态机位；这些镜头仍包含主体或环境运动描述，因此没有全部退化成静帧。没有官方评分，自动 verifier 不证明逐镜头语义完全等价。
- 媒体生成：未授权且未执行。图片/视频/render 工具没有注册，plan-check 中媒体文件列表为空。

## 模型请求

- 逻辑请求 13 次：外层 Agent 2 次、内部规划 11 次；项目层 attempt 记录 2 条。HTTP 交换次数 unknown。
- 已返回 usage 合计 36,753 tokens；250,000 是已返回 usage 的软阈值，不是硬输入或费用上限。本次未触及阈值。
- 请求和响应模型均为 `qwen3.7-plus`。内部 11 条解析诊断均为 success；无 length 截断、空正文、解析失败、未闭合请求或请求关联缺失。两条外层请求未提供 finish_reason，记录为 unknown。工具结果的 request_id 没有独立关联字段，不依据邻近请求补配。
- API 账单 unknown。运行时读取已登记凭据；凭据值未保存、打印或哈希。

## 时间、资源与清理

- attempt wall：70.54 秒；Agent 阶段：69.91 秒；Agent/容器返回码：0；Agent 正常结束。工作 deadline 未触发。
- 容器 cgroup：135 点，目标 0.5 秒，有效窗口 67.34 秒；CPU 4.442988 core-seconds，平均 0.06598 core。memory.current 结束 122,187,776 bytes，采样峰值 122,662,912 bytes，内核 peak 122,789,888 bytes。cgroup I/O 差分读 0、写 98,304 bytes。
- 容器 netns：35 点、34 个有效间隔，间隔中位数 1.998 秒；eth0 RX/TX 从 90/0 到 92,738/178,554 bytes。该数据仅表示容器接口流量。
- 工作目录边界：workspace 4 个文件/9,459 bytes → 29 个文件/131,749 bytes；attempt 子目录最终 8 个文件/64,892 bytes。
- 采样窗口短于完整 attempt wall；资源值限于记录的容器 scope 和窗口。清理无错误，容器删除已核验，镜像保留。

## 执行身份与验证

- 镜像：`vimax-task-bailian:arm64-v7-capability-planning-01`，`sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`，linux/arm64；89 个适配源码文件与宿主哈希相同。
- Frozen identity SHA-256：`7d1f3ce8d4ad081b56e4031f93a21d93f894eef1cc759ae0ab0339eda14e26a2`。
- Approval SHA-256：`3804206daa1657357b07cb4687906e6b55c96aba767b9f1b5b5390792f975929`。
- 百炼路由：`qwen3.7-plus` Chat Completions；内部 `enable_thinking=false`；内外层输出上限 8192；SDK retries 0。
- 单请求/会话预算：40 个逻辑请求，累计已返回 total_tokens 250,000 软阈值；工作 deadline 1800 秒、收尾 120 秒；图片/视频额度 0。
- 最终镜像禁网定向测试 33/33 通过，日志记录测试名、耗时和退出码。

本轮结果足以申请下一阶段的媒体生成授权，但不会自动授权、启动或重试图片/视频生成。真实任务与镜头语义的逐项人工评分未执行；自动校验能证明冻结脚本、数量、顺序、原生结构和引用约束，不证明语义完全等价。
