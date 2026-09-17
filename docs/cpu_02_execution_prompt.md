# CPU-02 A 执行提示词

将下面内容发给实施模型，只执行 A：

```text
请实施 /home/lcq/agent_workload_characterization/docs/cpu_02_handoff.md
中的 A 离线准备，完成后停止交回原评审。

CPU-01 B 已验收，不再重跑。当前目标是一个真实 SWE-bench Verifier 段，
不是整个 Agent：使用 RUN-02-R2 封存 candidate.patch、固定 task record、
既有 arm64 digest、官方 eval/parser。不要换成 gold patch，不执行轨迹命令。

先完整阅读任务书指定材料。按三单元一次完成：
A1 固定准备/eval/采样/解析边界与容器PID→宿主PID身份映射、采样就绪屏障；
A2 最小入口复用现有 verifier/runtime/sampler/perf_adapter，接通一次record
   与同期容器CPU边界、符号依据、独立状态、归档和清理；
A3 fake Docker/perf＋短自有进程走实际入口，完成任务书六类反例。

宿主 perf 必须采本批容器内真实eval目标，不能采docker客户端或猜宿主PID。
Popen成功/固定sleep不算perf就绪；没有协议依据就列出具体设计缺口交回，
不能切成全机采样、privileged或安装工具。不要复制新runner/清理框架。
符号必须对应容器binary/library；裸地址与unknown如实保留，不用宿主同名库
冒充。CPU-01 IPC和开销不能移用，函数权重不等于CPU秒数。

A不调用真实Docker（含查询）、perf、网络、模型、凭据或权限探测，不安装，
不运行真实Django。只用临时fake与任务书预算内短测试进程，跑定向及受影响
回归。旧raw/reports/references/批准/marker原字节不动，不提交Git。
不创建CPU-02实际approval/attempt。真实环境未知留给B，不因此无限返修A。

交付 docs/cpu_02_delivery.md：实际修改/测试、边界与协议、完整身份、
真正实现并离线验证的唯一B命令、最终预算/预检/权限需求与限制。
user_approval=pending、tool_execution_permission=pending。A完成即停。
B提案是一个容器、一次Verifier＋record、300秒总预算，无模型无重试；
本提示词不是B授权，不自行运行或宣布G2通过。

当前指引（2026-09-16）：原 CPU-02 B 命令已执行过并在准备阶段失败，
不得直接复用原批准或原 namespace。后续如需一次独立重试，只能按
`docs/cpu_02_r1_handoff.md` / `docs/cpu_02_r1_delivery.md` 的
CPU-02-R1 新 identity、批准路径和 attempt marker 执行；R1 A 仍需原评审
及用户批准，A 阶段不创建 R1 状态文件、不执行 Docker/perf。
```
