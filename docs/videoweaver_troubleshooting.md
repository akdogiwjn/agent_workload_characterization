# VideoWeaver 排障与快速复现

更新：2026-10-29。G01/G02已真实连续生成→merge，见 [结果索引](video_results.md)。官方dataset仍为占位，本项目故事case不称其官方benchmark。

## 固定成功路径

- 外层真实Codex CLI 0.163.0＋原生pipeline/skills。
- 镜像 `videoweaver-task-bailian:arm64-v2`，完整ID `sha256:933363d720001f71a74bd261c14a3480595942ec4612857797f3ca1814dbb6eb`。
- 启动：`python3 -B scripts/videoweaver_managed_launch.py --config <新配置> --out <新目录> --mode live`，没有run子命令。
- 查询：`python3 -B scripts/videoweaver_run_status.py --run-root <目录>`。READY仅代表启动。
- qwen3.7-plus Responses、qwen-image-3.0、wan2.6-i2v-flash；供应商远端生成，本地Agent/下载/FFmpeg拼接。
- venv绝对Python，禁止pip/uv运行时安装；merge_skill_fix生产挂载纳入身份。

## 问题与修法

| 问题 | 固定修法/边界 |
| --- | --- |
| login shell重置PATH，Agent系统pip安装卡住 | v2 /etc/profile venv优先；技能使用/opt/videoweaver-venv/bin/python，缺依赖报环境错误 |
| SSE usage缺失导致软阈值无效 | 按真实response_id或本地request_id去重；SSE终态/usage与rollout对账；summary非SSE单独入账 |
| 1M本地软阈值停止被误写余额耗尽 | 显式observed_total_tokens_soft；当前成功配置3M，发送前检查；不将cached/reasoning重复加到total |
| 宿主断线、短ID cgroup导致采样空窗/null | managed独立进程、PID/starttime/run绑定、完整ID/计数器有效后放行、流逐行落盘 |
| 生命周期set只收kwargs，main却传位置dict | 7处生产调用统一关键字；真实main回归，不只测试writer辅助函数 |
| set/beat固定.tmp并发覆盖 | 唯一临时文件＋原子replace；生产路径保留错误日志 |
| 启动器删旧lifecycle/截断日志 | out已存在拒绝；日志O_EXCL；不删除证据重试；有界握手和异常回收 |
| 缺final仍RC0 | judge检查实际成片、数量/规格、测量质量、日志和清理；进程返回不代表任务成功 |
| G02下载上限30误作最低预期30 | judge_media最低正常预期20，budget上限30；G03分别18/27，原FAIL与离线修订PASS分开 |
| fake过了却真实main失败 | 回归驱动真实runner/launcher，只fake外部边界，不替换被验证控制分支 |

## 下次开跑

新run、case、脚本SHA、完整镜像ID、runner/gateway/挂载/配置哈希与预算全部冻结。pipeline的target_task和VW_CASE_TXT必须跟随任务；G01=8/40s、G02=10/50s、G03=9/45s。
本机cpuset 0-7、pids4096、memory4g沿已验证配置，不宣称主机通用。请求、创建、轮询、下载分别限额，normal expected与cap分开；软阈值不是费用硬上限。

完整保存rollout、网关账本、远端task_id/终态、资源/netns流和目录边界。原生merge调用和输入顺序有证据，不能由宿主补成片冒充Agent完成。
本地媒体文件存在不替代远端任务终态记录；未保存则unknown，不再写“本地生成所以无远端任务”。

分析见 [口径](video_analysis_guidelines.md)。旧失败媒体和重复诊断已按用户要求删除；保留一份最小预算ledger与audit-verify fixture仅供测试，不能计入正式结果。当前无新执行授权。
