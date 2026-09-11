# P0-00 审计登记（r2）

2026-09-10 返修。这里只登记来源、证据与候选，不是 Unified IR 或新实现。

## 路径与版本

- sources.yaml 的 locator 为 root + path，root 定义在文件顶部；不再混用相对 benchmark 和相对项目的路径。
- code_components.yaml 的 root + path 同样明确；sample_candidates.yaml 可追加 line_1based / archive_members / record_id。
- 目录存在不等于全部子文件可读。access_status 区分 locator_exists、partial_subtree_permission、root_exists_payload_not_fully_checked。
- source_version/license=null 表示独立核实未完成；reference HEAD 是本地完整 commit，不表示干净 worktree 或完整资产版本。
- snapshot 引用 reports/quality/audit_evidence.json 中指定文件的 SHA-256 或目录清点，非全目录冻结证明。

## 文件

- sources.yaml：当前源、生成快照、当前/历史 sidecar 分开登记；unknown 不进入 real-only cohort。
- code_components.yaml：静态复用建议；不把可复用候选等同通过测试。
- known_issues.yaml：代码证据、数据范围、未修复问题；handled_missing 不代表补回数据。
- sample_candidates.yaml：可定位真实小样＋明确标 synthetic 的边界测试设计；未生成 fixture 文件。
- ../../reports/quality/asset_inventory.csv：标准 CSV，第一行即表头，无注释前导；空数值表示未测，不是零。
- ../../reports/quality/audit_evidence.json：实际扫描结果、历史/当前状态、过滤关系、文件哈希、代码版本。
- ../../reports/quality/audit_commands.md：实际执行的只读命令记录。
- ../../reports/quality/validation.json：返修校验结果。

## 计数与证据规则

数量只对所在 locator、record type 和 selector 成立；CSV 中父级总数与细分类不可再次相加。JSONL 行数不自动等于独立成功 run 数。

Applied Compute 使用 template_parameter，不是 observed latency/token 测量；AgentX 保留生产派生和筛选条件。SWE/OSWorld/SpreadsheetBench 为 benchmark 来源，公开不等于 production；MLPerf 具体生成身份待证据确认。

旧 normalized 数字只作为历史 pipeline 摘要，不当新统计真值。Video 原始 491 条、选中 trace IDs 的 235 条和 complete-only 的 233 条是不同集合。失败/未绑定/不完整数据保留独立范围，不因过滤就消失。

当前 sidecar 不是全部原始 attempts 的清单；尤其 AgenticVBench 当前可见带 trial_name 的 result 有 13 条，而 sidecar 只有 6 条，覆盖缺口已登记，未重建 sidecar。

本轮只读来源，不运行旧 pipeline、不修改/恢复/搬迁旧资产，不进入 P0-01。单靠 mtime 不能证明此前未修改；返修前后 hash 检查只覆盖本轮已登记文件。
