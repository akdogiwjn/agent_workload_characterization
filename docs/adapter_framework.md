# 公共 Adapter 框架 v0.1（P0-03）

本轮提供来源无关的 Python API 和只读 catalog 检查命令；未注册 AgentX/Applied Compute 等具体 adapter，未转换真实数据。服务 RQ1～RQ6 的来源、身份与血缘基础，不提供 CPU 测量。

## 接口与复用边界

公共入口：`agent_workload_characterization.adapters` 导出 `Adapter`、`Catalog`、`RawRecord`、`RecordError`、`stable_id`、`ingest`。

沿用旧 `adapters/base.py` 的分阶段设计（inspect / iterate / normalize / validate），但在新项目重新实现契约，不拷贝旧数据格式或导入旧包。旧读取器的 `errors="replace"`、空行跳过、warning-only 校验不沿用。

- `Catalog(path).source(source_id)`：读取现有 1.1 YAML 中的 root + path + kind，校验重复 key/ID、根引用、路径越界；不重写 catalog，不把 audit_revision 当完整数据快照。
- `Catalog.inspect(source_id)`：只检查 locator 文件属性，返回 exists/missing/unreadable/kind_mismatch；目录存在不表示其全部子文件可读，不递归扫描。
- `Adapter.discover(source)` / `inspect(source)`：默认只接受一个普通 `.jsonl` 文件。目录和 ZIP 留待对应来源定义发现和 record 边界，当前 ingest 明确拒绝，不偷偷解压。
- `Adapter.records(path)`：二进制逐行读取，每行产生 RawRecord，保留 `line:N`（1-based）和原始行 SHA-256。默认每行上限 8 MiB；超长行分块排空后只记一次 reject。此限制只是防护默认值，具体 adapter 若调整必须版本化并记录配置，不能据此声称大记录不存在。
- `Adapter.normalize(record, context)`：来源实现返回一个闭合 TraceDocument；输入语义不合法时抛 RecordError，不返回 None 或空成功。context 包含 source_id、文件内容 snapshot_id、adapter_version、配置副本。
- `Adapter.validate(document)`：重新校验可变模型；框架还会执行统一 IR 校验，要求至少一条当前 source/snapshot/record/version 的 provenance。
- `ingest(adapter, catalog, source_id, project, output=..., config=...)`：生成不可覆盖的批次，或校验并复用相同批次。当前仅支持单个 catalog 文件，与多源适配/流式目录发现分开。

配置必须是可规范化的 JSON 对象，不应包含密钥、prompt 或认证 header。adapter 是受信任的项目代码，不是允许任意第三方插件执行的沙箱；不得运行 trace 内的命令。

CLI 当前增加：

```bash
PYTHONPATH=src python3 -B -m agent_workload_characterization inspect-source agentx_256k --catalog data/catalog/sources.yaml
```

`validate` 仍验证单个 IR JSON，`inspect-source` 只读。尚无通用 `ingest` CLI；来源命令将在 P0-04/05 按已实现 adapter 接入，不提供假成功占位命令。

## 稳定身份、批次与重复

`stable_id(source_id, kind, *identity_parts)` 对带边界的规范 JSON 数组做 SHA-256，输出版本化 ID。它没有路径、snapshot、adapter 参数；来源 adapter 必须选择稳定的原始语义键，并在需要时包含 model/config/attempt 区分。只用 task 文件名仍可能冲突，框架不能替 adapter 猜测源语义。不同 source_id 的副本不会自动合并；跨来源别名需审计证据。

run 身份不因数据移动、snapshot 或转换版本变化而变化。snapshot 使用当前单文件原始字节 SHA-256，不声称冻结来源目录或重建采集历史。batch_id 由 framework/schema/identity/source/snapshot/adapter/config 及 catalog entry 摘要确定；来源角色或 selector 元数据变化也会产生新批次。

输出默认位于 `data/normalized/<batch_id>/`：

| 文件 | 内容 |
| --- | --- |
| documents.jsonl | 每行 `{document_id, trace}`；trace 是通过校验的 IR envelope，不是每 run 一个小文件 |
| records.jsonl | 每一物理行的来源位置、原始哈希、accepted/duplicate/rejected、对应 document_id 或原因 |
| rejects.jsonl | 被拒绝记录的位置、哈希和固定原因码，不复制原始 payload 或异常正文 |
| identity.sqlite3 | 批次内部的 document 内容摘要和 run 唯一索引，避免把全部身份装进 Python 内存 |
| completion.json / manifest.json | 同一完成记录的两个硬链接，manifest 作为原子发布的完成标记；包含 spec、输入 locator、计数、质量状态、文件哈希 |

文档身份基于其顶层 run/template/request/event IDs。相同文档身份且内容等价时只写一个 IR 文档，重复源行仍全部记在 records ledger。比较仅忽略 provenance 的 source_record_ref 值；源位置不丢失，来源/快照/版本和其他字段差异不会被一并抹去。建议 provenance ID 基于稳定实体身份，不要因重复行位置改变它。

相同身份但内容冲突记 `identity_conflict`；重叠 run 出现在不同闭合文档时记 `overlapping_run_document`，不尝试合并部分图。当前保留先到的有效文档、拒绝后续冲突；这不证明先到的正确。含身份冲突的相关 run 在来源人工核对前不得进入正式 cohort。

相同输入、配置、版本、输出根重复调用，会验证已有 manifest/spec 和输出文件哈希后返回 reused，不新增 run 或写入已有批次。改变配置/版本/snapshot 可生成新的转换视图，但稳定 run_id 不变。**不同批次是版本视图，不是可直接相加的独立样本**；跨批次的 active-view 选择、跨来源去重与多版本冲突解决仍需后续明确实现。不能把本轮幂等验收解读成已有全库自动去重系统。

## 失败与质量边界

每条物理行都有 accepted/duplicate/rejected 去向，计数满足 seen = accepted + duplicates + rejected。空行、非对象、非法 UTF-8、重复 JSON key、非有限数/溢出和过大行显式拒绝。预期 RecordError 和 IR ValidationError 按行隔离；未知代码异常、输入/数据库/写盘错误直接中断，不伪装成普通坏数据。

规范化前后分别流式计算源文件哈希，变化时不发布 manifest。这检测常规并发修改，不是对抗恶意瞬时修改的文件系统快照。正式批量输入应封存或固定副本，不能写着原文件同时声称可靠转换。

中断留下无 manifest 的不完整批次，保留现场；重试拒绝覆盖，需要人工检查或明确选择新的输出子目录。框架没有删除/恢复/覆盖开关。并发任务通过批次目录独占创建仲裁，同批次正在写入时第二个调用可能失败，而非等待或假称复用成功。

manifest 的完成只表示遍历和持久化完成，`quality_status=has_rejects` 明确保留拒绝；`no_record_rejects` 也不等于 G0、coverage、代表性或资源计量验收。此版本没有独立质量报告 CLI、Parquet、历史 Schema 迁移器或大规模性能验收。

## 路径与写入保护

只允许显式项目根下的 `data/normalized/` 及子目录。解析真实路径，保护 catalog 文件、所有登记来源、非 project 的旧资产 roots、references 与 data/raw；拒绝输出位于输入内、输出祖先包含输入、以及软链接指向上述保护路径。normalized 根不能经 symlink 重定向。新目录独占创建、输出文件独占创建；不打开已有产物做覆盖写。

保护适用于受信任且路径不被同时重新链接的本地工程目录；不是针对恶意同 UID 进程的 TOCTOU 安全沙箱，也没有宣称断电恢复协议已测试。批次目录权限为 0700，生成文件不适合作为未经隐私审查的公开发布物。SQLite 为标准库提供，不引入第二套数据分析框架。
