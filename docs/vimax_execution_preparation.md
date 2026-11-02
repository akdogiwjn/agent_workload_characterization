# ViMax 当前环境与执行准备

## 媒体长任务启动修复（2026-11-02）

未来媒体执行使用 [持久启动入口](vimax_managed_launch.md)：`scripts/vimax_managed_launch.py launch/status`。禁止依赖交互工具内手拼`nohup`保证采样存活；新身份须绑定启动器及同执行域的离线持久性验证凭据。原媒体runner、生成/拼接/验收及预算不变。R06-MEDIA-01仍是宿主中断、测量partial的失败观察，本修复未启动新媒体attempt。

更新：2026-10-29。已完成G01/G02，不再处于“服务尚未验证/镜像待构建”。结果见 [视频索引](video_results.md)，排障见 [快速复现](vimax_troubleshooting.md)。

## 已固定

上游commit `fd4b72e7731be6e5f88486206d25ea59849b0285`；本机隔离adapter-src，不改参考仓。
v7任务镜像、qwen3.7-plus、qwen-image-3.0、wan2.6-i2v-flash已真实使用；模型在远端，本机不装生成权重、不需GPU。
代码配方和锁文件位于 `env/video/vimax/vimax-task-image/`；实际入口为 `VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py` 与 `generation_entry.py`。当前video adapter修复通过配置只读挂载，核完整ID、import路径和SHA。

## 规划生产入口（当前维护，v7 参数化）

- 规划入口 `env/video/vimax/planning/host_runner.py`（`preflight|run --out <唯一新目录> --approval <APPROVAL> --config <planning-context>`），
  基于已验证 v7 链，参数化而非每任务复制固定数字。统一上下文 `env/video/vimax/planning/task_context.py`
  ＋ config（如 `task-configs/GX-musicians_band_rehearsal_typeC-planning-context.json`）。
- 容器内只读 overlay：`planning_entry.py`（冻结 script session + 预算 gate + 首帧能力）+ `plan_verifier.py`
  （expected_shots 参数化）。镜像仍 `vimax-task-bailian:arm64-v7-capability-planning-01`（未重建）。
- musicians 13 镜头已离线验收：真实 verifier 对 13 镜头合成 workspace ok=true，8/9/10 及各类反例拒绝；
  成功判定=plan-check.ok + 容器正常退出（RC0/COMPLETE 不代替）；完整 run_attempt 控制链（采样就绪放行、
  身份绑定 config/task_context/生产代码、自然退出、netns RX/TX 独立）50 项测试离线通过。
  真实规划与声音适配待用户授权。

## 新任务准备

1. 固定故事来源、剧本字节和任务要求；新script session原生规划，不继承其他故事。
2. 原生schema、顺序、引用、camera tree无环/覆盖及能力检查。
3. 只支持已验证单首帧i2v，variation small；不支持首尾帧/T2V等时明确拒绝，不静默降级。
4. 按真实角色、候选和camera tree核主体/过渡、图片/下载及预算；派生图片文件不当HTTP请求。
5. 规划和媒体分别身份/批准/采样/费用；超授权停止，不删镜头绕过。
6. 复用成功runner握手、cpuset、日志与remote_closeout，不重复拼执行器。
7. 新输出排他创建，API密钥仅运行时；禁止进镜像、构建上下文和报告。

G03（9镜头/45s）仍未执行；其模板not_planned门禁要等新规划通过后才能转正式。E/G任务来源见 [登记](video_task_expansion_registry_20261025.json)。本页不批准构建或API调用。

## 观测和验收

规划/媒体阶段分开；容器cgroup覆盖本地Agent/Python/FFmpeg，不含远端模型。采样窗不冒充总attempt；I/O真实零和缺读区分，netns逐接口。原生事件/账本/媒体task和目录边界均保存。
核心规格、来源、预算与语义质量分层，PARTIAL/unknown不补造；G02验收修订及现有限制从结果页进入。唯一分析入口见 [分析口径](video_analysis_guidelines.md)。

## 清理

失败启动、重复诊断和旧视频专属快照已按2026-10-29用户要求直接删除；必要生产代码/配方/回归fixture及有效规划/媒体原件保留。不要要求恢复旧失败目录后才能复现。删除回执见 [视频结果](video_results.md)。
