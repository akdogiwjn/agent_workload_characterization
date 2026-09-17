# G1-02 B 待批准执行提示词

A 离线集中修复已完成。以下交给执行模型；**转发本提示词不构成用户批准**，没有明确批准应停在核对清单处。

```text
请按 /home/lcq/agent_workload_characterization/docs/g1_02_handoff.md
§7 的最终清单处理 G1-02 B。先读 docs/g1_02_delivery.md 和
docs/project_status.md 当前状态。不要重新开发 A、READY、smoke 或重跑 Django。

先只做离线身份核对：实时 build_plan()["identity"] 必须与
workload_catalog/g1_02_identity.json 的 identity 完全一致。
核对已有 APPROVAL/ATTEMPT；不覆盖、不删除、不复用旧批准。

如果用户尚未明确批准该清单，停止并请用户批准，不运行 Docker。
获得批准后，按任务书独占生成真实批准记录，绑定完整 identity，
真实记录批准人、UTC 时间和授权内容，不代签、不猜测。

再为任务书唯一命令申请一次实际工具权限。预检和执行必须同一进程，
不得绕过沙箱、单独试探权限或改全局 Docker 配置。
用 /usr/bin/python3.11，两个执行旗标，固定镜像、任务、配置、预算。
本批无凭据、无模型、无 API；不要读取生产配置或环境密钥。

只执行一次本地合成批：最多2顺序容器，2CPU/256MiB，各 network none、
pull never；300秒总预算含30秒清理预留；固定6对ON/OFF，20M次/区间。
不要运行历史全量测试，不联网、安装、下载、拉镜像，不扩预算。

失败即停、不自动修复重试、不新建第二次attempt；comparison=inconclusive
也是合法的诚实结果，不调工作量/门槛补跑。正式I/O保持null、CPU shared，
不得宣称独占Tool CPU、稳定开销百分比或完整G1通过。

根据实际产物更新同一 docs/g1_02_delivery.md：run_id、实际命令、返回码、
wall、每用例状态、comparison、cleanup、输入输出哈希、缺失与限制。
原raw、历史报告、旧approval/marker、references不动；不提交/推送Git。
完成即停，交回原评审。
```
