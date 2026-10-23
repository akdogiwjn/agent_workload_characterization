# AgentX 原始证据独立备份（2026-10-23）

归档位置：`/home/lcq/agentx_evidence_backup_20261023/agentx-evidence-20261023-final.tar.gz`（仓库与六个工作树之外，**同机独立备份，不是异地备份**）。归档大小 541,310,827 bytes（约 516.2 MiB），SHA-256 `7e0104190ececcab755ba9fee682a8aaa68b5c45bcb7ff94889f4447f384322b`。

归档按 SHA-256 内容寻址并去重，包含 2,635 个来源路径、2,040 个唯一对象；源文件总计 2,744,166,000 bytes，去重后载荷 2,675,809,404 bytes。覆盖六个相关工作树的 report manifest 输入、local-evidence 原始输入/正式请求/SSE/客户端资源采样、冻结计划与配置、状态记录，以及 Full 全量分析的原始轨迹和来源登记。未收集密钥、虚拟环境、模型缓存或视频文件。

## 校验与恢复

- 归档内 2,040 个对象已逐一解包流式回读，字节数和 SHA-256 均与对象名一致；manifest 声明的文件大小与 SHA-256 检查无不匹配项。归档登记的历史文件缺失数为 0。
- 项目级状态检查仍报告 36 条既有证据登记所指文件缺失（属其他历史任务）；本次更新保留原登记与 SHA，不用刷新哈希消除这些问题。AgentX 本次清单登记文件缺失为 0。
- 仓库内已提交索引：[agentx_evidence_backup_index_20261023.json](agentx_evidence_backup_index_20261023.json)，保存每个来源绝对路径到归档对象的映射、原 manifest 期望哈希和来源类别。外部完整索引及校验和文件位于备份目录；归档校验和文件：`/home/lcq/agentx_evidence_backup_20261023/agentx-evidence-20261023-final.tar.gz.sha256`；恢复说明：`/home/lcq/agentx_evidence_backup_20261023/RESTORE.md`。
- 按索引查找 `archive_object`，然后运行 `tar -xOzf /home/lcq/agentx_evidence_backup_20261023/agentx-evidence-20261023-final.tar.gz objects/sha256/<sha256> > <目标路径>`；恢复前后都不要覆盖更新的原件，并用 `sha256sum` 回读确认。原文件均保留。

Git 提交备份索引与本说明，不提交归档本体。归档是本机副本，不能替代远端或异机备份。
