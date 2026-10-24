# VIDEOWEAVER-GENERATION-PILOT-01 中文执行摘要

日期：2026-10-24。一次正式 attempt，retry=0，经统一生产入口（host_runner v2）＋受控网关（gateway.py）真实调用百炼。

## 结果

**8 张首帧图＋8 段主体视频已真实生成并保留；final.mp4 未生成**——Codex 在 8 段视频完成后陷入低效循环（反复检查 `pip install`/空命令，未发 merge-video），80 次 LLM 发送预算耗尽后由网关阻止，任务在拼接前预算性停止。judge 因缺 final 判 FAIL；不是基础设施失败（清理核验通过）。

- run_id：`videoweaver-generation-pilot-01-20261024T104827Z-944af65d`
- 镜像：`videoweaver-task-bailian:arm64-v1`＝`sha256:60cf9b9fe2317a7b92cdba48f70cb74c77321642ddb75e3c64ccbb84e92062d8`（linux/arm64 已核验）
- 命令：`python3 -B runner/host_runner.py --mode live --config runner/live-config.json --out evidence/VIDEOWEAVER-GENERATION-PILOT-01/run-944af65d`
- 凭据：运行时仅注入网关进程 env（`export` 格式已修复、值去引号）；未回显/保存/哈希/归档

## 模型、工具与媒体统计（网关账本）

| 项 | 数值 |
| --- | --- |
| LLM Responses 实际转发 | **80**（上限 80，耗尽） |
| 图片创建发送 | 8（上限 16） |
| 视频创建发送 | 8（上限 8，每镜恰好一次） |
| 视频轮询 | 64（上限 960；每任务 1–21 次，全部 <120） |
| 媒体下载 | 16（8 图＋8 视频，上限 48） |
| 账本终态 | `budget_exhausted:llm_calls`（发送前阻断第 81 次） |
| usage | 网关未解析到真实 SSE usage（终端 unknown），**已返回 token 累计 unknown**；软阈值 500k 未触发 |
| 费用边界 | **unknown**（无供应商账单）；≈20 元仅参考，非硬上限 |

## 八镜头完成情况与媒体

- 首帧图：shot1–8 `*_firstframe.jpg` 全部生成（qwen-image-3.0）
- 视频：shot1–8 `.mp4` 全部生成（wan2.6-i2v-flash 单首帧）
  - 每段 **H.264 / 1280×720 / 30fps / 5.000s / 无音轨**（ffprobe 8/8 通过）
  - 抽帧（中间帧）：8/8 **非黑、非纯色**；色调整体符合故事弧线（shot1 暖日出→shot5 蓝调→shot7 蓝紫霓虹→shot8 暗夜）
  - task_id→shot 映射完整（见 `evidence-frames/media-map.json`、`manifest.json`）
- final.mp4：**未生成**（merge 前预算耗尽）

## 时间与资源

- 入口 wall：**1564.0 s**（10:48:36→11:14:40 UTC）
- 采样：**3128 点**@0.5s；CPU **25.86 core·s**，avg **0.0165 cores**（主要等待远端生成）；内存 current 终值 226.9 MB、内核 peak 537.4 MB；I/O 与 netns 记录见 `samples/`
- 清理：容器 stop/rm 成功、删除核验通过；删除前 docker logs 已补取

## 诚实声明

- 抽帧/ffprobe 是技术＋有限内容检查，**不是**完整语义评分；无官方评分器，不编造 reward。
- 8 段视频规格达标，但**任务未完成**（缺 final.mp4），judge FAIL。
- 远端视频 task 全部 SUCCEEDED（8 个，账本记录终态）；无未知在途任务（本地清理≠远端取消）。
- 原生 `cost=0` 是占位；实际账单 unknown。

## 下一步（不自动执行）

- 该 run 预算已消费；再次执行需另行批准。Codex 的真实自主循环在 8 视频后未及时进入 merge——建议下次授权时把 merge-video 命令纳入明确工作流提示，或在 LLM 预算中为收尾预留余量。
