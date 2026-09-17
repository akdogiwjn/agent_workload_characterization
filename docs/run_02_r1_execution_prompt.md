# RUN-02-R1 给实施模型的提示词

后续状态：R1 已在 Docker 预检后因凭据变量未设置停止，原 attempt 不复用。当前改用 [READY-01 提示词](run_02_launch_readiness_prompt.md)准备启动前集中检查；本页保留历史用途，不再执行 R1。

复制下文。本提示词只授权 A 离线准备，不授权沙箱外执行或真实重试。

```text
请实施 /home/lcq/agent_workload_characterization/docs/run_02_r1_handoff.md
的 A 阶段，完成后停止交回原评审。

背景：原 RUN-02 在沙箱内因 Docker socket operation not permitted
预检失败；只读诊断已确认沙箱外 daemon 可达、固定 ARM digest 存在。
不要再拉镜像或重做环境，不把 inspect 非零一概解释成镜像缺失。

本批只做三件事：
1. 登记 RUN-02-R1 固定的新批准/attempt namespace，保留原 RUN-02
   APPROVAL、ATTEMPT_STARTED、PREFLIGHT_DIAGNOSTIC 原字节和哈希。
   新批准绑定原失败血缘、完整代码/配置/task/image/model/预算/路径。
2. 最小复用原入口，支持 R1 原子单次登记、报告与失败证据；
   旧批准不得授权 R1，R1 已登记时只读交付，不删除 marker 再执行。
3. 补齐预检安全错误分类与离线回归；登记实际执行命令和所需权限。

最终执行环境必须让预检和 runner 同处于获准访问本地 Docker socket
的环境。B 前既要用户批准最终清单，也要执行工具对登记单次命令的
沙箱外权限批准。不得用 chmod/sudo/远端 Docker/关闭全局沙箱替代。

A 阶段：不调用 Docker（含只读查询）、不联网、不读凭据、不发模型
请求、不启动容器、不安装/构建/pull，不申请或执行真实权限探测。
仅修改本任务必要的自有入口/测试/文档；复用现有采集分析清理链。
不改 references、旧源、封存数据与历史报告，不提交/推送 Git。
允许现有 venv 的明确封网合成测试，不重跑真实 smoke 或 B1。

按任务书一次完成最小回归，交付 docs/run_02_r1_delivery.md：
实际修改/测试、真实命令、完整身份哈希、准确输出路径、权限申请方式、
预算与风险、原失败文件哈希保持不变。
标 user_approval=pending、tool_execution_permission=pending 后停止。

原任务/模型/镜像和全部预算不变。后续 B 仅在新批准后执行一次，
失败即停，不扩预算、不自动创建 R2、不自行宣布 G1 通过。
```
