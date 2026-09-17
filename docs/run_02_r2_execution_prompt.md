# RUN-02-R2 给实施模型的提示词

复制下文。本轮只做 A 离线接线，不授权真实重试。

```text
请实施 /home/lcq/agent_workload_characterization/docs/run_02_r2_handoff.md
的 A 阶段，完成后停止交回原评审。

READY-01 最新只读检查已经通过；不要再开发或重跑 READY/smoke/B1。
本批只把已验证的启动方式接到一次新的 RUN-02-R2 attempt：
独立 R2 批准/marker、仅本进程代理清除、获准执行环境内解析
{env:VOLCANO_API_KEY}、实际映射给既有 mini 子进程，再复用原 runner。

先读任务书及指定材料。保持 task/model/image/catalog/预算不变，
不复制 runner/hook/collector/cleanup。旧 RUN-02/R1 与 READY 证据原字节保留。
新批准绑定实际完整身份与 READY 成功证据。旧批准不能放行 R2。

A 仅允许自有接线/测试/文档和现有 venv 的明确封网合成测试：
不读生产配置或真实密钥、不调用 Docker（含只读查询）、不联网、
不申请实际权限探测、不安装或拉镜像、不执行模型/Agent/Verifier。
不创建真实 R2 approval/marker，不修改旧 marker，不提交/推送 Git。

关键回归必须经过实际 R2 入口：fake 凭据引用→实际环境映射→mini
封网子进程，不用 mock 正确 credentials 掩盖接线；验证父进程代理污染
被局部清除、缺凭据/预检失败不调用 runner、一次性登记、旧批准隔离、
最终工具/宿主文件和派生报告。沿用已有测量与清理语义。

交付 docs/run_02_r2_delivery.md，登记真正实现并离线验证的唯一命令、
全部代码/config/task/image 身份、输出路径、预算、凭据设置责任、
单次沙箱外权限申请方式、实际测试和限制。
标 user_approval=pending、tool_execution_permission=pending，停止等待验收。

B 只有在用户批准该最终清单且工具权限获批后才执行一次；预检和 runner
必须同一获准进程环境，凭据重新安全注入，不依赖 READY 检查的旧进程。
失败即停，不自动重试/扩预算/恢复代理，不创建 R3，不宣布 G1 通过。
```
