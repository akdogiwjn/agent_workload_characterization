# VIDEOWEAVER-GENERATION-PILOT-01 修订说明（PILOT-01-recovery-01）

日期：2026-10-24。只读核对 `evidence/VIDEOWEAVER-GENERATION-PILOT-01/` 的 run-944af65d、run-58dc50b4、run-ce40d6e0；不覆盖/不改写历史 ledger、rollout、报告、manifest、identity。本修订与离线恢复成片独立登记。

## 一、失败归因更正（基于保存的调用/返回时间线，不增加推测）

原报告"Codex 反复安装、空命令循环、纯粹模型能力不足"的表述**需限定或修订**。基于 rollout 逐条 function_call 时间线的事实：

- **早期 1 次安装**（FC#59 `pip install Pillow httpx requests`）：用系统 pip（login shell PATH 解析到 `/usr/local/bin/pip`），装到系统 python（/usr/local）；系统 python 原本**无 requests/PIL**，安装后获得它们——这解释了 image-gen/video-gen 后续能用系统 python 成功执行（8 图 8 视频，脚本 import 成功）。
- **merge 前 1 次安装**（FC#541 `pip install moviepy opencv-python`，按 merge-video/SKILL.md 的前置依赖说明触发，系统 pip）：FCO 显示 `Process running session 44703`（30s 时仍在运行），Codex 随后多次 `ps aux | grep pip install`、空命令（arguments 空）、等待该进程。
- **Codex 从未真正调用 merge 脚本**（rollout 无任何 `merge_videos.py` 调用）；空命令与轮询占用了后续 LLM 预算（80/80 耗尽）。
- **安装为何持续未结束：unknown**——安装进程在 run 结束时被容器删除终止，无最终输出；不猜测为网络或包冲突。
- **正常生成等待 vs 安装等待 vs 模型请求**：8 段视频生成是正常的（video-gen create→poll→download 全程有账本与 exit0）；低 CPU 时段包含安装等待与模型请求等待，不能全部称为"等待远端生成"。

**结论**：根因是（a）merge-video/SKILL.md 要求运行时 pip install，且 login shell PATH 使 `python`/`pip` 解析到系统解释器（非 venv）；(b) 该系统 pip 安装长时未结束；(c) Codex 在等待安装时未进入 merge，空命令耗尽 LLM 预算。

## 二、usage 离线重算（原生 rollout）

- `token_usage_record` 共 **80** 条；`response_id` **80 个全部唯一**。
- 逐响应求和（每响应 final usage，**不累加累计快照**）：input=3,281,314、cached_input=2,965,760、output=16,676、reasoning_output=2,620、**total=3,297,990**。
- 与最后一条 `turn_token_usage`/`thread_token_usage` 累计值**逐项一致**（input/cached/output/reasoning/total 全同），交叉验证通过。
- 说明：cached_input 2,965,760 占 input 的 90%，是缓存上下文输入，**不是独立文本量，也不是账单**；total 是重复上下文的累计转发量。
- **登记 500k 软阈值未有效执行**：原网关在线 usage 采集失败（terminal unknown、usage 未入账），软阈值未在下一次转发前检查，任务在 80 次硬门禁（而非软阈值）处停止。
- **修订**：原报告"usage 全部 unknown、纯模型行为问题"需限定为——网关在线 usage 采集失败，但原生 rollout 保留完整可回算用量；实际账单仍 unknown。

## 三、额外 live 运行核清（只读）

| run | 启动 | 模型转发 | 媒体生成 | 分类 | 依据 |
| --- | --- | --- | --- | --- | --- |
| run-58dc50b4 | 1 | 1（HTTP 404，未受理） | 0 | 批准前预检接线失败（网关上游路径双前缀 bug） | ledger 1 次 llm 转发 404；identity prior_preflight_fixes |
| run-ce40d6e0 | 1 | 1（HTTP 401 InvalidApiKey，未受理） | 0 | 批准前预检接线失败（凭据值引号 bug） | ledger 1 次 llm 转发 401；identity prior_preflight_fixes |
| run-944af65d | 1 | 80（受理） | 8 图＋8 视频 | 唯一正式 attempt（retry=0，授权预算内） | ledger；media-map；identity |

本地 run 启动 3 次；模型转发合计 82 次（其中 2 次未受理 404/401）；媒体生成仅正式 attempt。两份预检 run 的 404/401 为接线错误、未计费、未受理，不并计为正式 attempt 的模型调用；不做违规指控，仅登记事实。不再发请求查询。

## 四、离线恢复成片（独立 scope）

- 输入：run-944af65d 的 8 段真实视频，复制到 `inputs/`，哈希与 manifest 8/8 匹配。
- 命令与解释器：`/opt/videoweaver-venv/bin/python /opt/videoweaver/skills/merge-video/scripts/merge_videos.py --video_paths /in/shot1..8.mp4 --output_filename final-recovered.mp4`（固定 venv：moviepy 2.1.2、cv2 5.0.0、imageio-ffmpeg）。
- 容器：禁网、`--cpuset-cpus 0-7`、`--pids-limit 4096`、`--memory 4g`；merge rc=0，耗时约 29s。
- 输出：`output/final-recovered.mp4`，**h264 / 1280×720 / 30fps / 40.000000s / 无音轨 / 完整解码**；抽帧 8/8 非黑非纯色，各段颜色符合故事弧线（seg1 暖日出→seg5 蓝调→seg7 蓝紫霓虹）。
- 技术验收独立完成；后处理时间/资源与正式 run 分开（不并入原 attempt）。
- **定性**：这是"原始 Agent 未完成任务后的独立离线后处理恢复"；**不是**原生端到端成功，不改写原 run 的 COMPLETE/成功标记，不在原 run 目录写 final.mp4。

## 五、修复（本轮落地）

- `source/skills/merge-video/SKILL.md`：明确依赖已在 `/opt/videoweaver-venv`；禁止运行时 pip/uv pip install；缺依赖报环境错误；用固定 venv Python 绝对路径调用；merge 前确认片段后直接拼接。镜像内旧版通过生产挂载机制覆盖（host_runner 挂载修复版 SKILL.md，纳入 identity）。
- 解释器实测：普通 shell `python`→venv；login shell（bash -lc，即 Codex exec_command）`python`/`pip`→系统 `/usr/local/bin`（无 requests/moviepy）——验证了根因。
- `gateway/gateway.py`：SSE 解析重构（多行 data、data 后有/无空格、CRLF、`[DONE]` 不算成功、按 response_id 去重 usage、区分 input/cached/output/reasoning/total、缺 usage 记 `usage_missing`）；软阈值在下一次 LLM 转发前检查（`soft_threshold_exceeded`）；保持硬门禁/原子预留/持久化。
- SSE 回归：`runner/test_sse.py` 7 项单测通过；最小禁网 Codex 经网关会话验证终态与 usage 落盘、软阈值到达后下一次转发为 0（端到端）。
