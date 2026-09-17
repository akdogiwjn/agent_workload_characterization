# CPU-01 A 执行提示词

将以下内容发给实施模型。本提示词只授权离线准备，不授权 perf 或新实验。

```text
请实施 /home/lcq/agent_workload_characterization/docs/cpu_01_handoff.md
的 A 阶段，完成后停止交回原评审。

当前 G1 已在登记的资源小闭环范围通过，见 docs/g1_consolidated_review.md §0。
不要重做 G1-02、READY、smoke、Docker 启动认证，也不要重跑 Django。

先完整阅读任务书指定材料。一次完成三件事：
1. 用现有 RUN-02 封存证据列 Agent/Verifier/host 候选 scope，说明字段、单位、
   coverage 和边界；没有单工具 CPU 证据，不做 Tool CPU 排名。
2. 实现最小 CPU-01 薄入口和 perf 解析路径：默认无副作用计划，独立批准/
   attempt 身份；以后 B 仅对自有合成进程作一次 stat 和一次 record。
   复用安全写入/进程收尾思路，不复制通用 runner，不创建新服务框架。
3. 用 fake perf 可执行程序及短自有进程走实际入口、解析、归档、清理，
   覆盖任务书五组反例；最后填写真正实现并离线验证的 B 命令和身份。

A 不运行真实 perf（含版本/权限探测），不调用 Docker、网络、模型，
不读生产配置/密钥，不安装、不改 sysctl/capability，不创建真实批准/marker。
只跑定向及受影响回归，遵守 A 短进程预算；旧 raw/reports/references/批准
和 marker 原字节保留，不提交 Git。不得执行历史轨迹中的工具命令。

PMU 权限、硬件事件、符号可用性留给另行批准的 B，不伪造成功；没有实际
perf 运行不是 A 阻塞，缺少生产实现才是。命令/格式无本地文档依据时明确
列缺口，不猜测，不自动联网。硬件缺失不填零，软件计数不冒充硬件支持，
合成热点不冒充 Agent 热点，G1 的开销证据不等于 perf 开销已验证。

交付 docs/cpu_01_delivery.md：候选表、实际测试、接口和证据映射、完整身份、
B 唯一命令/事件/预检/预算/失败规则。user_approval=pending，
tool_execution_permission=pending。完成 A 即停，不运行 B、不宣布 G2 通过。
```
