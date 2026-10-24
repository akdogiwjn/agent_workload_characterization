# ViMax Generation Pilot 02 — preflight blocked

本目录是 `VIMAX-GENERATION-PILOT-02` 的前置检查记录，不是正式 attempt。固定 v7 镜像身份已核验，上一轮规划来源按原 manifest 校验并复制 15 个必要文件；没有读取凭据，没有创建批准/attempt，也没有发送模型或媒体请求。

## 阻断原因

本次禁网容器调用了固定镜像中的 `preflight_render_capability`，并把相机过渡视频上限配置为 0，以便在八段镜头视频预算之外禁止隐藏视频创建。门禁返回：`camera transitions require 7 extra video calls; configured cap is 0`，进程正常以 0 退出；媒体请求计数为 0。

保存的 camera tree 有 8 个相机，7 个子相机均声明 parent 与 `missing_info`。原生 `Script2VideoPipeline` 在每个子相机上调用 `generate_transition_video()`，随后仍为八个 shot 各调一次 `generate_video_for_single_shot()`，因此需要 7+8=15 个视频创建任务，超过本次授权的 8 次硬上限。没有关闭 transition 分支、删镜头或改规划来绕过预算。

## 调用量与费用估算

实际模型、图片、视频、轮询、下载、HTTP 请求数均为 0；本次没有生成成本或资源采样数据。按源码默认每镜头两个候选图估算，约 3 张人物肖像 + 16 张镜头候选图 = 19 张输出图。每个视频创建分支使用 5 秒配置，15 个 job 共 75 秒。按百炼公开北京价格估算，wan2.6-i2v-flash 无声 720P 为 0.15 元/秒，qwen-image-3.0 1K 输出为 0.18 元/张，已知媒体输出部分约 11.25 + 3.42 = **14.67 元**。此估算未含参考图输入计费、qwen3.7-plus token、账单免费额度/促销及实际服务地域；总费用仍 unknown。价格来源：[百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)（核对日期 2026-10-24）。20 元是估算目标，不是金额硬上限。

轮询上限若按 15 个 job 全部用满，最多 1,800 次；按 19 张图和 15 个视频各下载一次，估算 34 次下载，重定向单独计。以上是静态上限估算，不是实际发生次数。

## 状态

- 正式 attempt：未创建；批准：未创建。
- 图片/视频任务：未创建；远端任务状态不适用。
- 规划：复用 `VIMAX-PLANNING-VALIDATE-03`，未改写、未回写历史 session。来源路径、字节数和 SHA-256 映射见 [source-map.json](source-map.json)。
- 容器：只运行禁网预检；使用 `--rm`，无残留任务容器。镜像保留。
- 成本、正式 wall、资源曲线：本轮没有相应正式运行，均不适用/未知。

继续前需要另行授权至少 15 次视频创建，或先以新的明确批准定义不同执行方案。当前授权上限下不能启动生成。
