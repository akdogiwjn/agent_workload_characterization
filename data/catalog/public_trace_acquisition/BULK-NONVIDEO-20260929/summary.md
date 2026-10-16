# BULK-NONVIDEO-20260929 acquisition

本轮只登记公开文件获取，不执行 benchmark、Agent、轨迹、模型或资源采集。保存字节是本地文件大小，不等同于精确网络响应量。

| 来源 | 获取状态 | 文件数 | 保存字节数 | 可确认轨迹数 | 独立 task 数 | 版本 | 尚未取得什么 |
|---|---|---:|---:|---:|---:|---|---|
| SWE-bench Verified S3 + experiments index | partial | 4606 | 633,248,212 | 2578 | 500 | `40f164d5b8f1d249bf95a6df8b74b577fd8e519d` | 5 selected prefixes complete, 1 partial; 326 selected objects failed; remaining prefixes; Lite/Test trajectories |
| SWE-rebench | complete local payload; transfer record gap | 91 | 480,862,314 | 85 gzip shards | 555 stated by source manifest | `cdae27cdd16673f0c682871ad55d325f24cc7020` | 53 local trajectory payloads absent from saved per-file transfer records |
| AgentX | complete | 8 | 569,694,616 | 1 JSONL corpus / 393 traces | unknown | `8fecd2fc56694469f758f0afbbb6335ad3043740` | No other release files |
| Applied Compute | reused existing source | 5 | 13,921,018 | 0 (derived templates) | n/a | `6918da7915e3ae57ce3750a375ef50e41cad2b36` | Raw execution traces |

## 结果

SWE-bench experiments 索引和 Verified 元数据固定到 commit；轨迹只取得六个选定提交前缀中的实际对象，5 个完整、1 个 `174/500`，未把失败对象计入成功。不同提交实际使用 `.traj`、`.log` 和无后缀对象，按原样保留。Verified metadata 有 182 submissions，而本次 S3 listing 中发现有轨迹对象的前缀组为 127，不能把 metadata 数量当成已获取样本。Lite/Test 仅登记索引/结果元数据。

SWE-rebench payload 之外，本地还保留了 185 个 HF cache/下载元数据文件、39,227 bytes；它们不是轨迹 payload，也不计入上述可确认轨迹。

SWE-rebench 本地 manifest 声称 85 shards、9,435 rows、17 participants/5 runs；它是第三方 normalized corpus，不称官方原始轨迹。另有 53 个本地 trajectory payload 不在保存的逐文件传输记录中，已保留并在 manifest 标记 provenance gap。

AgentX 的 `traces.jsonl` 与 README/stats/plots 已按固定 revision 保存；stats 记录 393 traces，定位为请求流量/宏观结构，不是完整本地工具执行或 CPU trace。Applied Compute 三个 JSONL 是 workload 模板，不是原始消息、具体工具操作或独立 Office 执行轨迹。

本轮新响应正文上限为 20 GiB；已选 Verified 对象的成功落盘字节为 530,810,447，但 git/HF 重定向、失败重试和各工具的统一响应计数不能独立精确复核，故不能把保存文件总和写成严格预算证明。下一步仅建议对评审接受的来源做离线 schema/字段盘点，不自动继续下载或分析。
