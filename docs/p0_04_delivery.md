# P0-04 AgentX Adapter 与小样回归

状态：DONE（小样范围），2026-09-10；G0/M1 未验收。

## 实际交付

- `adapters/agentx.py`：AgentX v7 normalize、明确 main/all 范围、token/time/null/prefix、子 Agent 树和原始标签。
- `adapters/agentx_checks.py` 与只读 `check-agentx-samples` CLI：通过 catalog 对 AX-7/AX-SUB 做定位、预期核对、完整 prefix 比较和 IR round-trip，不写正式 IR 批次。
- IR 0.2：请求模型/类型、Agent 原始标签、未知 clock precision；旧 Schema 归档，新增显式纯函数迁移和测试。理由与兼容边界见 [IR v0.2](ir_v0_2.md)。
- `tests/test_agentx.py`：合成语义/数值、批次重复 ingest 和迁移测试；已有当前 fixtures 同步至 0.2。
- [AgentX 语义文档](agentx_adapter.md)、任务状态及 [真实小样检查摘要](../reports/quality/agentx_sample_validation.json)。

没有新增第三方依赖。旧 adapter 和本地 dataset card 只读参考，未导入或修改旧代码；没有修改 references 第三方内容。

## 实际验证

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples
git diff --check
```

87 项测试通过（此前 68 项 + 本轮 19 项）；实际 AX-7 和 AX-SUB 检查均 PASS。默认测试不依赖旧 trace，合成数据显式 synthetic；真实检查单独运行，只处理两条选中记录。

| 小样/范围 | 请求数 | 输入 token | 输出 token | API 累计 work | 区间 busy | observed span |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AX-7，main/all 相同 | 7 | 194368 | 4097 | 50.406 s | 48.950 s | 385.681 s |
| AX-SUB，main | 2 | 50624 | 1200 | 6.743 s | 5.911 s | 5.911 s |
| AX-SUB，all | 21 | 818752 | 3949 | 41.836 s | 41.004 s | 70.593 s |

请求/token 数匹配 catalog；AX-7 时间口径另有合成标量手算回归。两条真实记录所有请求的 prefix 向量逐项相等，未截断。AX-SUB 的 19 个子请求不重复添加父起点，source group tool_use_count=null；分组 total_tokens 未重复加到逐请求汇总中。表内秒数仅为归一化源字段表示，不宣称毫秒级真实时钟精度。

全部样本 run_elapsed、turn_count、全 run Tool count、local_cpu_time 均为 null/unavailable；不把 observed span 当运行 E2E。

真实记录哈希（原始行字节，含换行）：

- AX-7，line 39：`01249bbdf3f1311acf0519a36956e546ddd3e0be61251e05f5e1e4bed5b697ea`
- AX-SUB，line 307：`2b46fc38faf30610e44560aeae37d5bb34a4bdf6bcf0bf1badbd05d809fbbfdd`

读取至最高 selector，但未解析非选中行；没有重新计算整个 568 MB 源文件的历史 checksum，不宣称全来源冻结或全量回归通过。检查摘要另存实际检查时间。

## 边界与下一步

- 没有全量 ingest、复制生产原始记录到 fixtures、创建正式 normalized 批次、跑 benchmark/CPU 采集或发远端请求。
- 合成临时项目验证了 AgentX 接入 P0-03 的 round-trip 与重复 ingest；不是全来源、跨 snapshot 请求去重或性能验收。
- 未迁移已有真实 IR 批次；未知 request 类型、非法数值、重复子 Agent ID 等拒绝而非猜测修复。
- 请求身份暂基于源数组位置，重新筛选/重排后的跨 snapshot 请求等价仍需独立解决；前后文件属性检查不等于对抗性文件系统快照。
- 仍缺 Applied Compute 和一种本地 trace 的真实小样、macro/coverage 和试点选样，因此 G0 不勾选。

下一任务：**P0-05 Applied Compute Adapter 与小样回归**；本次未启动。未提交或推送 Git。
