# READY-01 给实施模型的提示词

后续状态：READY-01 `20260914T111017Z-7eb3c4` 只读检查已通过验收。本页保留历史用途，不再重跑检查；当前使用 [RUN-02-R2 提示词](run_02_r2_execution_prompt.md)，先离线接线，真实运行另批。

复制下文。本轮仅做离线准备，完成后交回原评审。

```text
请实施 /home/lcq/agent_workload_characterization/docs/run_02_launch_readiness_handoff.md
的 A 阶段，不执行其 B 只读检查，也不创建 R2。

目标：把最终执行环境的权限、固定配置、输出路径、凭据引用解析和
父→子进程环境传递集中核对，避免再次用真实任务启动发现准备缺口。

先阅读任务书指定文档。复用 smoke_launcher 中合适的凭据解析/受限环境
逻辑，但绝不调用 smoke 或模型。只用合成配置、假密钥和封网短子进程
完成必要实现与五组回归，不重写 runner/collector 或引入配置框架。

A 不读真实密钥或生产配置值，不调用 Docker（包括只读查询）、不联网、
不启动容器/Agent/Verifier，不执行权限探测，不安装/下载，不改用户配置。
不得把密钥写入 argv、日志、临时 env 文件、错误原文或报告；结果只能
输出固定白名单布尔值和安全类别，不能输出密钥前缀/长度/哈希。

原 RUN-02/R1 批准、marker、预检证据保持字节不变；不创建 R2 身份、
批准或 marker，不改变旧入口 attempt 消耗顺序。新 readiness 报告用
reports/preparation/READY-01/<check_id>/ 独占目录，不是运行授权。

交付 docs/run_02_launch_readiness_delivery.md：
实际修改/测试、唯一凭据注入路线与设置责任、真实检查命令和代码哈希、
待批的最终环境只读检查清单（60 秒、无 API/容器、仅内存解析凭据）。
标 read_only_check_approval=pending 后停止；不要自行进行 B 检查。

后续必须先经原评审、用户批准及工具单次权限批准，才能执行最终环境
只读检查。检查成功也不授权任务重试，不证明网关认证有效或 G1 通过。
```
