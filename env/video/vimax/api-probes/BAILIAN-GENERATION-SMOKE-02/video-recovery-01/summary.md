# video-recovery-01 摘要（BAILIAN-GENERATION-SMOKE-02 补验）

日期：2026-10-23。授权范围仅限：查询既有任务、下载结果、本地媒体检查。未创建新任务、未重新生成、未调用 LLM、未重跑 smoke。原始 UNKNOWN 判定与 40×401 记录保留在 `../verification.json`，未覆盖。

## 结果

| 项 | 结果 |
| --- | --- |
| 原任务终态 | **SUCCEEDED**（task_id `ebd1a3dd-ea65-41d5-9b98-eb930eb377c9`，自原始创建响应读取，完整 36 字符；第 1 次查询即命中，request_id `f797509c-3324-9593-ab88-9c68542f21a5`） |
| 视频技术有效性 | **PASS**（H.264 / **1280×720** / 30 fps / yuv420p；时长 **5.0 s**（与请求 5 s 一致）；**无音轨**（audio=false 生效）；完整解码成功；5 帧抽取正常） |
| 动作符合程度 | **PASS（有限证据）**：首尾帧采样差异 2.72%（存在动态变化）；全部抽帧左绿（≥0.437）/右蓝（≥0.529）/白底（≥0.459）布局保持。**不声称严格动作质量评分**——"左侧圆形缓慢上下移动"的精确轨迹未逐帧验证 |
| 视频文件 | MP4，**730,447 bytes**，SHA-256 `a01d56f858537dccd9046cd1f1cd0c339355bce6951b5d433f38a0b3975a359f` |
| 供应商 usage | `video_count=1, duration=5, SR=720, input_video_duration=0, output_video_duration=5, audio=false`（与请求参数完全一致） |

## 计数与耗时

- 本轮发送（客户端观测）：**0 次模型操作**、**1 次查询**、**1 次下载**、0 跳转、0 客户端异常、0 重发；网关/上游内部请求 unknown。
- 耗时：总 wall **1.166 s**（预算 180 s；12 次查询上限仅用 1 次）。轮询/下载单项耗时未留存——recovery.py `persist()` 曾整体覆盖 `timings` 字典，执行后已修复（合并式写入），原始 verification.json 保留缺值现状，不做无依据补算。
- 认证预检（执行前）：修复后的轮询代码带 Authorization、401/403 立即停止、下载函数不向媒体域名转发授权头——3 项定向离线测试通过后才执行。

## "0 失败"统计口径澄清（不改写原始记录）

原 `../counts.json` 的 `send_failures: 0` 口径为**客户端传输层异常**（连接失败/超时/抛异常的发送）；40 次轮询 401 属于**收到了 HTTP 响应**（`ok=true`），故未计入该字段。若按"HTTP 失败响应"口径，该轮存在 **40 次 401 失败响应**（完整记录在 `../verification.json` 的 poll log）。两口径并列陈述，原始文件未改动。

## 费用边界

- 本轮 0 次生成操作；视频生成费用在原任务成功完成时即已锁定：5 s × 无声 720P 0.15 元/s = **0.75 元**（北京原价，与是否下载无关）。本轮查询/下载不产生模型费用，但不宣称"必定免费"（以百炼实际账单为准；免费额度余额 unknown）。

## 视频链路是否补齐 & ViMax 下一步

**已补齐**：创建（SMOKE-02 主轮 PASS）→ 轮询（本轮 200/SUCCEEDED）→ 下载（无授权头媒体客户端）→ ffprobe/解码/抽帧检查，全链路真实走通。至此 SMOKE-02 四项验证最终状态：**图片生成 PASS、图片编辑 PASS、语言/视觉+工具调用 PASS、视频生成+回收 PASS（技术+有限语义）**。

**下一步可以进入**：ViMax 生成器适配（OpenRouter Images/Videos 协议 → 百炼新域名 OpenAI 兼容 images + 原生 video-synthesis 的映射层）与 ARM64 镜像构建的依赖安装验证。注意边界：单轮 smoke 不证明多图一致性、多镜头并发、长时稳定性与费用规模；正式八镜头任务仍需单独批准与预算。

## 证据

`verification.json`（本轮完整记录）、`manifest.json`（含 bytes/SHA-256 回读）、`D-video.mp4`、`frames/f01–f05.png`、`recovery.py`（含执行后 persist 修复）。原始目录的 `verification.json`/`counts.json`/`manifest.json` 及阻断轮快照均未改动。
