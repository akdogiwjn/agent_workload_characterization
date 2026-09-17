# CLOSEOUT-01 交付

日期：2026-09-15。状态：本批收尾已完成，交回原评审；不宣布 G1 通过，也不产生下一项运行授权。

## 实际修改

本批只整理既有证据与导航，未开发框架、重写分析器或增加实验：

- 新增 `reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/` 下的
  `summary.json`、`summary.md`、`corrections.md`、`manifest.json`。
- 新增 [`docs/README.md`](README.md)，作为文档唯一索引。
- 更新根 [`README.md`](../README.md)、[`docs/development_tasks.md`](development_tasks.md)、
  [`docs/g1_consolidated_review.md`](g1_consolidated_review.md) 和根目录
  [`methodology.md`](../methodology.md) 的当前进度段；任务编号、研究方法和六条 Gate 标准保留。
- 新增本交付文档。

review-v2 是原始报告的派生修正，不覆盖原报告；它纠正 RUN-01 遗留模板的 native hook、
closed/成功、LimitsExceeded/提交、全树计账和资源口径说明。原始 raw、原报告、批准、marker、
READY 证据、catalog、references、代码和测试均未改。未提交的工作树补丁仍按证据说明为
`LimitsExceeded` 后的候选结果，不能解释为主动提交完成。

## 证据与保护核验

已只读核对 R2 的 `run_id=20260915T012427Z-2d75aa`、
`attempt_id=20260915T012427Z-2d75aa-a1`，以及 review-v2 manifest 所列 17 个输入文件的
存在性、字节数和 SHA-256。raw 全树为 10 个文件、647461 bytes，raw manifest 哈希为
`7718c8003463158bafc219255f765f1d9f168861e84bf23ae99e5b197a5af2f5`；metadata 的
645154 bytes 仅作为另一计账口径保留。

保护证据哈希核对如下：

- R2 `APPROVAL.txt`：`18627b227218957cb6aadeb0836707fb7778cab4e1bf1b7175d67c6f34ae2394`；
  R2 `ATTEMPT_STARTED.json`：`7c53b96c0e0c800d5af9c09e1737731683911945f6d987f5d60b63dcb4c0ff55`。
- 原 RUN-02 approval、attempt marker、preflight diagnostic：
  `cf744bf09ac4ba334cf0010dd0be0afdd7859c84046a763bb869f7ef26becd9a`、
  `8279e463198d9130496e3f5f43b0aad1d7fa6e42a9e9cfee0a9581f34fa8b437`、
  `ed911efcc6a74cf8f8245b7c47ba6c44e51651bb50b21d8a52ee8bf428db2bdc`。
- R1 approval、marker、preflight：
  `1f9442a7196b14a292b0b3ca1bf0f296bbfc0399328a754f754cac78aeb48d74`、
  `edebe9f82a3fdf91380b1c71e7c35d9954ed4fa330bd99eac9bbdec99503102d`、
  `55768beef63d97f3de6abee4facb17a23e94ba83d5c2abcb88692b65bf5ec96d`。
- READY summary、manifest：
  `cc234ad87b9c00189c20f9ec8c1836a3f762aca36a9ac420b83533b323ac2a65`、
  `af76a6e481d56488f09031eb0702780dbc928174e2998151ef2f01725a4bf942`。

原 R2 报告目录的三个文件也保持原哈希：manifest
`1d011702dfdf23d4dfd0e71c69ace0e9e138e42465c37d8e663af762d0b3331a`、summary.json
`ccd65f5d0a9433d81e78ee8d14b26a612aa80118c0f0a1cbfb889dd82bc68bad`、summary.md
`580b4754c7dfdfb2d1fb2bded82e95cd663db46e06bd7ec75e7d923464bebb60`。

## 结果、判定与剩余缺口

R2 的执行、评估、归档和清理均为 `ok`，报告为 `complete`，`resolved=true`；Agent 为
`LimitsExceeded` 且未主动提交，Verifier 验证了工作树补丁。30 个模型请求中 27 成功、3
失败；28 个 native hook 为 28 open/28 closed，含 1 个非零返回码，故 closed 不等于成功。
原生 hook duration 与历史 receipt 估计分开。宿主 CPU 是 4.19 秒首末可读区间增量，RSS
的末次可读值与采样最大值分开；正式 I/O 为 null，不做独占 Tool CPU 或 RUN-01/RUN-02
性能因果比较。

G1 六条集中评审已更新为 `PARTIAL / REVIEW_PENDING`，不自行勾选通过。按六条标准，当前
真正待评审的缺口是：Tool/资源 shared-scope 下的后代关联、短命后代/常驻服务/异步边界，
以及开销量化和正式比较容差。I/O null、shared CPU、退出末端计数缺失是已接受降级；多任务
扩展、正式应用 I/O、独占 Tool CPU、函数热点/PMU 和多任务排名属于后续研究方向，不是本次
G1 的新增前置条件。测试数量不解释为任务数量、请求数量或独立实验数量。

## 导航与检查

根 [`README.md`](../README.md) 指向当前状态、方法、集中评审、review-v2 和本交付；
[`docs/README.md`](README.md) 覆盖当前任务、长期规范、历史交付、任务书/提示词、全部现有
`docs/*.md` 和 raw/报告地图。历史文件仅分类索引，未移动、删除、重命名或批量加横幅。

本批执行的核验限于：输入/输出文件清单和 SHA-256、受保护证据前后核对、docs 索引覆盖、
修改文档的本地链接检查和 `git diff --check`。未重跑全量测试，未调用 Docker（含查询）、
网络、READY/smoke、模型、Agent/Verifier，未读真实凭据，未安装、拉镜像或创建新 attempt/
approval；未提交或推送 Git，并保留用户未提交改动。

## 未来迁移建议（不执行）

如未来合并历史文档，应先建立来源→目标映射、扫描引用、核对哈希并取得评审批准，再做可
回滚迁移；不得把历史提示词改写成当前授权。若扩展 G1，应先预注册多任务/多 attempt、
后代服务边界、I/O 与独占归因定义及比较容差。
