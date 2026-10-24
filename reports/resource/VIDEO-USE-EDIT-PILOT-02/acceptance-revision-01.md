# VIDEO-USE-EDIT-PILOT-02 验收修订 01

本文件补充解释，不改写原始执行记录、评分文件、冻结身份、批准记录或 manifest。依据：

- 原始归档：`data/raw/generated/VIDEO-USE-EDIT-PILOT-02/20261021T0937Z-video-use-edit-02/`
- 原执行摘要：同目录 `run-record.json`、`manifest.json`、Codex 原生 rollout 与 `verifier_private/reward.json`
- 原报告：`reports/resource/VIDEO-USE-EDIT-PILOT-02/summary.md`
- 原任务输入登记：`data/workloads/video/editing/avb-disfluency-interview-3-v1/{acquisition.json,files.json}`

## 修订判定

- 剪辑流程确实运行：一次官方转写成功，Agent 生成视频和 cuts，并执行截图自检；原始轨迹和产物仍有效。
- 任务结果未达标：官方 judge 的剪切时间门未通过。ffprobe 显示输入为 854×480、25 fps，输出为 1920×1080、25 fps，未保持输入分辨率。
- 原 judge 在当前宿主解释器中缺少 `skimage`。judge 捕获 SSIM 异常后写出了 reward 0.0，但 returncode 0；因此该 reward 不是完整的质量评分。SSIM 失败后音频相关性没有运行，应记为 unknown/not_evaluated，而非实际音频失败。
- rollout 中有 36 个 function-call 事件和 36 个 function-call-output 事件，协议 error 事件为 0；这不表示命令都成功。根据每个返回内容，至少两个命令进程非零退出：生产 render 命令和近结尾 timeline screenshot 命令。
- 资源数据继续可用于描述该次运行，但采样周期须按实测值报告：0.5 秒为目标；312 个区间均有计数，间隔中位数 0.601377 秒、最大 0.802106 秒。不得将目标周期写成实际周期。

后续评分应使用 PILOT-03 的专用 verifier venv 与状态解释层。该准备不对 PILOT-02 历史视频重评分，也不改变历史 reward；oracle 验证只用于确认评分环境，不代表 Agent 结果。
