# SWEBENCH-CONTINUATION-20260930 acquisition

本轮为 BULK-NONVIDEO-20260929 的独立续接轮，只登记公开文件获取，不执行 benchmark、Agent、轨迹、模型或资源采集。轮内包含一次服务器关闭中断（2026-09-30 ~03:41Z）与恢复（2026-10-05 15:27Z）；中断前已落盘文件完好，恢复后按断点续传。索引仍固定 experiments commit `40f164d5b8f1d249bf95a6df8b74b577fd8e519d`，未更新到 main。

| split | 本轮新增 submission/对象 | 累计完整 submission/对象 | 失败对象 | 尚未处理 | 保存字节 |
|---|---|---|---|---|---:|
| Verified | 29 组 / 12,827 对象（27 组新完成） | 32 组完整 / 15,405 对象（另 3 组部分） | 13（10×S3 404 + 3×deadline 边缘） | 93 组 / 111,898 对象 | 795,797,082 |
| Lite | 0 | 0 / 0（65 组 / 64,492 对象未动） | 0 | 65 组 / 64,492 对象 | 0 |
| Test | 0 | 0 / 0（15 组 / 153,250 对象未动） | 0 | 15 组 / 153,250 对象 | 0 |
| 旧326失败重试 | 0（tier 4 未到达） | — | 0 | 326 | 0 |

## 结果

- Verified S3 listing 中 127 个有 trajs 对象的提交前缀组里，本轮按"组内 trajs 总字节升序"处理以最大化覆盖：新增 12,827 个对象（0.74 GiB），27 个组完整新获取，`20241125_enginelabs`（499/499）等小体积组全部完成；累计完整组 5 → 32，部分组 3（旧轮 `20240620_sweagent_claude3.5sonnet` 174/500、`20241108_devlo` 499/500、`20241213_devlo` 3/500——最后一个为 deadline 中断组）。
- 全部 12,827 个新文件与 S3 listing 期望字节逐一比对一致（0 mismatch），SHA-256 已从磁盘重算并登记于 manifest（中断前的逐对象传输记录因服务器关闭丢失，bytes/SHA 以磁盘为权威重建）。
- `20250616_Skywork-SWE-32B+TTS_Bo8` 组 10 个对象在 S3 返回 404（listing 快照与当前桶状态不一致），按连续失败规则暂停该来源，未反复重试。
- 内容抽样（29 组每组每后缀 1 个文件）：绝大多数为真实 agent 轨迹（json message list / trajectory、THOUGHT/ACTION 结构、含 `llm_call_data` 的 .traj）；边缘对象已如实登记：`20250112_ugaiforge` 在 S3 仅有 4 个配套产物+Google Drive 外链（无对话轨迹本体），`20241128/20250306_SWE-Fixer` 仅检索统计/模型各 1-2 个对象，`20241212_google_jules` 含 README/说明文件。对象数不等于轨迹数。
- 本轮 12,827 个对象覆盖的独立 dataset task 仍为 Verified 固定 500 个（不同提交的同一 task 不是不同独立 task）。
- Lite/Test 轨迹未获取（优先级顺序在 Verified 之后，本轮预算耗尽于 tier 1）；Lite 的外部来源 `AnvithPabba/SemAgent_Multi` 已完成索引登记并钉住 commit `826396fa30f002e126762bdb90ef934d2aad3afa`（MIT），待下轮按字节快照获取。Verified 外部来源 `john-bang/20260901_mini-v2.4.2_gemini-3-5-flash` 仓库 404，无可确认轨迹。
- Verified metadata 182 个 submission 中：162 个声明 s3:// trajs，其中 49 个在 listing 中无对象（mini-* 系列完全缺席，部分仅 logs）→ 登记为无可确认轨迹；11 个 `trajs: null`；2 个其他（1 悬空内部链接但 S3 有对象已获取、1 外部 404）。
- 预算核验：resumed 段响应正文计数 501,285,623 bytes（精确，仅 S3 GET 响应体）；中断前段记录丢失，按落盘 0.27 GiB + 重试开销估算 ~0.29 GiB，合计约 0.76 GiB / 20 GiB，远未触顶——**约束是墙钟与单请求延迟（恢复后 ~0.5 对象/s），不是字节预算**。HTTP 头/TLS/listing API/GitHub API 未计入（unknown）。
- 获取状态仍为 **partial**：固定索引范围内 Verified 127 组中 32 完整、3 部分、92 未触碰（其中 1 组 S3 404）；Lite/Test/旧326 全部待办，见 pending.json。下载完成不等于分析完成；G2/G3-R、CPU-02、Replay 状态不变，未提交或推送 Git。
