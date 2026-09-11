# Benchmark Selection (P0-07 试点设计)

状态：**设计已核实至静态证据极限（2026-09-10）**；试点执行未授权。详细配置见
[pilot_execution_spec.md](pilot_execution_spec.md) 与机器可读 [pilot.yaml](../workload_catalog/pilot.yaml)；
证据索引 [pilot_evidence.json](../reports/quality/pilot_evidence.json)。

## 首选真实资源试点：Coding (SWE-bench Verified)

选择依据：
- 独立容器边界 + shell 命令型工具（execute_bash/str_replace_editor），适合 Tool-call 粒度资源观测设计
- 公开轨迹（500 条同批 OpenHands/Sonnet 提交）可作宏观参照
- Verifier 判定链（F2P/P2P→resolved）已静态核实

候选任务：`django__django-16485`（floatformat 崩溃修复）
- 轨迹（只读证据）：`agent_benchmark_traces/swebench_experiments/verified/20241029_OpenHands-CodeAct-2.1-sonnet-20241022/trajs/django__django-16485.json`
  SHA-256 `506a5091...`；30 消息、14 turns、execute_bash×7、str_replace_editor×7
- TraceBench 交叉确认 instance 身份（OpenHands/GPT-5 solved）

**配置缺口（未定，不视为已冻结）**：
- 任务数据集记录（base_commit/test_patch/F2P/P2P/image/eval_script/log_parser）：本地无；
  拉取 `SWE-bench/SWE-bench_Verified` 需授权，且目标数据版本是否按 `make_test_spec` 所需字段
  可直接加载**未核实**，可能需转换/构建链（GAP-TASKDATA-001 + GAP-VERIFIERSPEC-001）
- harness：OpenHands 源码不在 references（GAP-HARNESS-001）；mini-SWE-agent 本地仅有 argv 构造器，
  安装/配置未验证；候选 OpenHands / mini-SWE-agent / P1-07 wrapper
- 模型：待用户选择，与 harness 为独立维度。当前 Claude Sonnet 仅为**历史配置连续性候选，
  行为可比性未验证**；备选任意 OpenAI 兼容端点模型。价格/可用性未核实；
  "claude-3-5-sonnet-20241022" 仅为历史记录，不断言当前可用
- Docker/镜像 digest：待 P1-00 预检（GAP-DOCKER-001）

## 备选：DocOps（Office）

- 任务 `word_001`（task.toml SHA `541e0d24...`，任务树 commit `ccf7a75`）
- verifier：pytest artifact 级 semantic-strict（test.sh → test_outputs.py）
- 任务声明资源：1 CPU / 4 GiB / 10 GiB 存储；本地无 word_001 历史运行
- 历史 codex+Harbor 批次为 surrogate 配置，不作为冻结 harness

## 未选择场景
- VideoWeaver：远端媒体生成 CPU 不可测量，不作为 CPU 试点
- ToolSandbox：尚无本地运行证据

## 预算（待批准）

1 task / 1 attempt / 总 30 min 硬上限（Agent 25 + Verifier 5，任何分段不得越总限）/
4 CPU / 8 GiB / 5 GiB 新产物 / 0 重试；build/setup 另计（建议 15 min 上限，待批准）。
Agent 停止后 verifier 仅在剩余预算内运行；超出即中止并记 verifier_timeout（评估未完成）。
