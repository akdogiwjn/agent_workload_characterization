# VIDEO-USE-CODEX-BAILIAN-INTEGRATION-01 摘要

日期:2026-10-21。在 `video-use-task:arm64-codex-bailian-v1`(=`sha256:a46db2143d8a…`,派生自已登记 `video-use-task:arm64-v1`)上安装官方 Codex CLI **0.163.0**(GitHub release `rust-v0.163.0` arm64 musl 静态二进制,SHA-256 `a7261e65…fffe4`,无需 Node),容器专属 `CODEX_HOME=/opt/codex-home`,显式百炼 provider(qwen3.7-plus/responses/`env_key=DASHSCOPE_API_KEY`,无默认回退,请求/流重试置零)。凭据仅运行时注入容器环境变量,未进镜像/工作区/报告。

## 一次真实 CLI 会话结论

**Codex＋百炼＋工具＋看图兼容性已验证**(分项判定见下)。会话 wall 约 4.8s(300s 限内);无重试配置生效;HTTP 实际尝试次数 **unknown**(CLI 不可观测,未伪称)。

| 分项 | 判定 | 证据 |
| --- | --- | --- |
| 工具执行 | **PASS** | rollout:`exec_command` `{"cmd":"python3 /task/probe_input.py","workdir":"/task"}`,exit 0;`/task/output/receipt.json` 落盘(receipt `6e7b54f33dc24caf95e31619021e7dc9`) |
| 工具结果回传 | **PASS** | 最终回答精确含 receipt 值 |
| CLI 看图 | **PASS** | rollout:`view_image` `{"path":"/task/input/neutral-test.png"}`(返回 base64 input_image);回答"Left side: 1 red circle / Right side: 3 blue squares"与宿主侧答案(1 红圆左/3 蓝方右)**语义全对** |
| 终止 | 正常(turn.completed;usage input 18267/output 379,reasoning 223) | token usage 非账单 |
| 采集 | 39 点 0.5s cgroup 采样,39/39 有效区间 | 兼容性测试,不作正式视频成本样本 |
| 清理 | 容器删除核验(docker ps -a 空);两镜像保留 | |
| 命令审计 | 干净(无 /task 之外写操作/危险模式) | |

**判定过程说明(透明)**:执行时自动判定三项 FAIL 系探针解析缺陷(0.163 rollout 以 `function_call name=exec_command` 记录命令执行,解析器未识别;英文侧别归属正则错配),非会话失败——会话 stdout/rollout/final_message 均显示真实成功。修复解析器并补 2 项回归(16 项离线测试全绿)后,基于已保存证据**零重发/零新会话**离线重判为三项 PASS;原始 FAIL 判定与重判段并存在 verification.json。

## 原生轨迹

rollout:`session-01/rollouts/2026/10/21/rollout-2026-10-21T06-57-30-01a15d40-….jsonl`(session_meta/turn_context/response_item/event_msg/token_usage_record 完整;SHA 见 manifest);stdout JSONL 摘要与 `final_message.txt` 一并归档;CLI 事件接收时间与真实工具起止时间为 rollout 时间戳,HTTP 边界 unknown。

## 距完整 video-use 还缺

1. **ElevenLabs 转写**:账号/预算授权;transcribe.py 在容器内的真实调用与缓存行为(本轮及之前均 not_tested)。
2. **真实素材与策略确认**:20–60s 授权口播素材;用户确认剪辑策略交互流程(SKILL.md 的 ask→confirm→execute 在 CLI 下的实现)。
3. **正式路由冻结**:本轮百炼集成配置为候选,未修改 model-route.json,未创建 APPROVAL/ATTEMPT。
4. video-use 技能已可在容器内被发现(符号链接验证),但其工作流未被本轮执行。

边界:一次受控 CLI 会话的兼容性验证;不代表完整 video-use 可运行、非正式实验 READY、不构成执行授权。
