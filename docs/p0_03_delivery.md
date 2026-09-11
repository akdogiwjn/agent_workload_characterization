# P0-03 交付记录

状态：DONE（单文件 JSONL 公共框架），2026-09-10；G0/M1 未验收。

## 实际交付与复用

- 新增 `src/agent_workload_characterization/adapters/`：catalog.py、base.py、ingest.py 及公共导出。
- 参考旧 Adapter 的分阶段接口，重新实现严格读取、来源血缘、IR 验证与批次存储；没有复制第三方格式或导入旧代码。
- 新增只读 `inspect-source` CLI，保留现有 validate/help/version；没有来源 ingest CLI。
- 新增 `tests/test_adapters.py`，更新依赖断言、README、任务计划、方法论当前进度和 [框架约定](adapter_framework.md)。

新增 PyYAML 依赖 `>=6.0,<7`，用于读取已有 YAML catalog；本机已有 6.0.3，没有下载/安装/升级。Pydantic 继续使用已有 2.13.4，SQLite 和 unittest 使用标准库。不引入 pandas/polars 或重型采集依赖。

## 实际检查

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m agent_workload_characterization inspect-source agentx_256k
git diff --check
```

68 项测试通过：P0-02 原有 42 项 + 本轮 26 项。新增测试覆盖 catalog 安全解析/重复身份/路径越界、逐行错误隔离、超长行排空、稳定身份、不同模型、重复源行的血缘、IR round-trip、幂等复用且 hash/mtime 不变、身份冲突、未完成与损坏批次拒绝覆盖、源修改不发布、配置/位置变化不改变 run 身份，以及直接/软链接/祖先重叠路径保护。

写入与 ingest 测试全部在 `TemporaryDirectory` 创建的合成旧源/新项目中执行；测试清理仅移除这些临时资产。不依赖旧 trace payload 才能运行测试。

实际 catalog 的 AgentX locator 只做 stat，返回 exists、file、568864747 bytes；这是文件属性，不是本轮重新核实 session 数或冻结数据版本。未解析、转换该文件。

## 验收口径与明确限制

1. 流式读取保留每行 locator/hash，拒绝记录不静默丢失；文件前后哈希不一致不会发布完成标记。
2. 合法小样可 round-trip，当前源记录 provenance 必须存在；模板/实测身份仍由 IR 契约限制。
3. 同输入同配置同版本同输出根重复 ingest 复用一个经过完整性校验的批次；相同源行不会重复写 run，不同模型的稳定身份不同。
4. 直接写旧路径、通过软链接写旧路径、输入输出互为祖先均被拒绝；已有/不完整/损坏批次不自动覆盖。
5. 当前只支持单 JSONL 文件，未实现具体 AgentX/Applied/本地 sidecar adapter、ZIP/目录 ingest、跨来源去重、跨版本 active-view、Parquet、迁移器、宏观或 coverage 报告。不同转换批次不能直接合并计数。
6. 路径保护不是对抗同 UID 恶意重链接的沙箱，前后哈希也不等于操作系统快照；正式批量运行仍需固定输入与受信任输出目录。

没有修改旧资产或 references 第三方内容，没有在正式 `data/normalized/` 创建批次，没有运行旧 pipeline、benchmark、远端调用或 CPU/OS 采集；未提交/推送 Git。

下一任务为 **P0-04 AgentX Adapter 与小样回归**。先按 catalog 的真实定位与 gold expectations 建立小样，再讨论批量转换；本次未启动。
