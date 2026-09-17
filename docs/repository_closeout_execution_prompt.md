# CLOSEOUT-01 执行提示词

复制下方内容交给实施模型。本提示词授权离线整理，不授权实验。

```text
请实施 /home/lcq/agent_workload_characterization/docs/repository_closeout_handoff.md，
一次完成 CLOSEOUT-01 后停止，交回原评审。

目标只有三个：
1. 为已验收的 RUN-02-R2 新建修正派生报告，纠正 RUN-01 遗留模板说明。
2. 按既有六条标准整理 G1 集中评审材料，不自行宣布 G1 通过。
3. 整理全仓导航：README 一个当前状态，docs/README 一个文档索引，
   让人能找到当前任务、长期规范、历史交付、权威数据和派生报告。

先完整阅读任务书指定材料，以实际文件与证据为准，不按聊天数字硬编码。
复用既有成果；不开发框架，不重写分析器，不增加实验。
历史文档只在索引中归类和标注，不移动/删除/重命名或批量加横幅。
保留任务编号、研究方法、Gate 标准；不把测试数量解释成任务数量。

本批只允许任务书 §7 的文件范围：新 review-v2 报告、docs/README.md、
README/任务计划/集中评审及 methodology 的进度段、唯一交付文档。
封存 raw、原报告、批准/marker、旧任务书/提示词/交付、catalog、references、
代码/测试和用户配置全部不改。保留用户未提交改动，不提交/推送 Git。
不调用 Docker（含查询）、网络、READY/smoke、模型、Agent/Verifier；
不读真实凭据、不安装/拉镜像、不创建新 attempt/批准或自动运行下一任务。

重点语义：LimitsExceeded 未主动提交但工作树补丁通过验证；
28 工具中有 1 个非零返回码，closed 不等于成功；
原生 hook duration 与历史 receipt 估计分开；宿主 CPU 是可读区间增量；
本次计账按实际全树核对，不能沿用旧“未覆盖文件”模板；
I/O 正式 null、不做独占 Tool CPU 或 RUN-01/02 性能因果比较。

验证只做本批必要的只读核算、输入前后哈希、新报告清单核对、
文档索引覆盖、修改文档链接检查和 git diff --check，不重跑全量测试。
发现证据矛盾一次集中列清，禁止修改原件凑 PASS。

交付 docs/repository_closeout_delivery.md：实际文件和检查、保护证据核验、
报告替代关系、导航入口、G1 建议与剩余缺口、未来迁移建议（不执行）。
完成后停止交回原评审，不生成后续实验授权，不自行宣布 G1 通过。
```
