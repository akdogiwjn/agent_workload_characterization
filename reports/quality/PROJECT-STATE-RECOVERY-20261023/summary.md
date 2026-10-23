# project_state.json 回滚后的恢复记录（2026-10-23）

已确认当前状态文件曾回退至Git HEAD并重新补写少量条目。AgentX深入分析的报告、10页PPT、图表、逐请求明细及manifest仍在；本次检查的63条AgentX文件哈希登记全部匹配（原始大语料未在本次重复哈希）。丢失的是未提交的状态登记，不是这些分析产物。

本会话先前为隔离非视频提交，保存过一份完整的工作区状态快照：`/tmp/public-closeout-index-content-20261023/before-local-update/project_state.json`。该快照与Git提交中经过范围隔离的状态文件用途不同；它包含视频和OpenStoryline等未提交条目，因此可以恢复Git HEAD没有的内容。

恢复已完成：

- 从快照逐字段精确恢复20个缺失顶层条目，包括video-use环境、能力验证、codex-bailian集成、PILOT-01至04，以及OpenStoryline准备、正式运行与收尾记录。名单见[verification.json](verification.json)。
- 恢复快照内的`research_scope`、`current_work`及相关证据登记；保留当前HEAD内已提交的公开数据集收尾条目。
- 保留另一个对话新增加的`bailian_generation_smoke_01`及原始事故说明，不用旧快照整文件覆盖。
- AgentX深入分析第1步的新增状态条目根据完好的报告、摘要、manifest及核验结果重建；不宣称该新增条目与丢失前逐字相同。三个当前页面中仍完好的13条状态摘要保持原样。
- 仅更新四个已知发生变化的当前导航/忽略文件的证据哈希；其余旧证据与快照登记匹配，未改写历史哈希以掩盖差异。

恢复前文件、原始快照、合并候选和恢复后文件均已保存到本机忽略目录：`local_archive/20261023-project-state-recovery/fad338c1b7ef/`。恢复脚本在写入前比较当前文件内容，若发现新的并发修改则拒绝覆盖；本次比较通过后才原子替换。

恢复后`check_project_state.py`通过，471项登记证据与当前文件匹配，三个导航页面与状态摘要一致。本次没有执行Agent、模型、工具或评分，也未改动视频原始数据、报告或正式运行身份。

并发维护共享状态文件时，应按条目合并并保留写入前快照；不能用`git checkout -- project_state.json`清除未知来源的工作区修改。
