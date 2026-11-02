# VideoWeaver 当前环境与执行准备

更新：2026-10-29。G01/G02已经真实连续生成→拼接，不再处于“修复后完整闭环未实测”。结果见 [视频索引](video_results.md)，故障修法见 [排障](videoweaver_troubleshooting.md)。

## 运行方式与环境

上游commit `c809392fe6c2c8b22472049684aaefc650e31bde`。仓库提供技能/harness，外层使用真实Codex CLI 0.163.0；官方dataset为空，现有ViMax故事转换为项目自建case，不冒充官方benchmark。
独立v2镜像、固定venv、FFmpeg、修复后的技能与统一runner/gateway均已验证；源码在隔离副本，不修改参考仓。构建配方与锁/镜像清单保留，不为换任务重复安装。

模型路由：
- qwen3.7-plus：Codex Responses及技能所需Chat Completions；
- qwen-image-3.0：T2I/I2I；
- wan2.6-i2v-flash：单首帧、5s、720P、无音轨。
图片base64内联，视频理解仅抽帧审阅，不称直接视频理解。首尾帧、T2V、参考视频、音频驱动和延长等未验证能力发送前拒绝。

## 新任务

使用 `env/video/videoweaver/task-configs/` 新正式配置，核case_dir/target_task/case_id、脚本SHA、VW_CASE_TXT和pipeline参数。
G01/G02/G03分别8/10/9镜头，40/50/45s。正常每镜头一图一视频；无ViMax的camera-tree辅助过渡。
预算上限和judge正常预期分开：G02下载20/上限30，G03为18/27。不得拿上限当最低完成数。

启动：
```bash
python3 -B scripts/videoweaver_managed_launch.py --config <新配置> --out <新目录> --mode live
```

新身份和批准绑定镜像完整ID、runner/gateway/技能挂载/配置/case。没有新授权不运行。本页不批准G03或重复实验。

## 观测与收尾

网关发送前持久化账本、原子额度预留、任务task_id表、usage去重、软阈值（非费用硬上限）沿现行实现。
managed心跳/PID/starttime/run绑定；完整ID cgroup与计数器有效后放行；resource/netns流运行中落盘；最终边界在删除前取得。
任务成片/Agent终止/测量质量/清理归档分列，临时失败不通过删目录重试。模型在远端，本地CPU不包含远端推理。
分析入口与数据质量见 [video_analysis_guidelines.md](video_analysis_guidelines.md)。

## 清理与复现依赖

2026-10-29已直接删除旧失败媒体和重复诊断；当前有效原始轨迹、成片、采样、账本和必要测试fixture仍在原路径。详细删除回执及8组结果见 [video_results.md](video_results.md)。不要求重做旧探针/诊断轮次。
