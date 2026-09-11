# P0-07 收尾与 G0 评审交付（只读核实轮）

日期：2026-09-10。状态：**P0-07 保持 PARTIAL（设计证据完成，3 项用户决策未定）；G0 READY_FOR_REVIEW，待用户/评审裁定**。

## 实际改动文件

新增：
- `docs/pilot_execution_spec.md`（试点任务/harness/model/verifier/边界/预算/非目标）
- `workload_catalog/pilot.yaml`（机器可读设计清单，execution_authorized=false）
- `reports/quality/pilot_evidence.json`（18 项证据 + 4 项缺口索引）
- 本文件

增量修订：
- `docs/benchmark_selection.md`（替换为核实后状态与缺口）
- `workload_catalog/coding.yaml`、`workload_catalog/office.yaml`（unfrozen 字段、SHA、缺口）
- `reports/quality/benchmark_matrix.csv`（版本/SHA/缺口更新）
- `reports/quality/g0_review.md`（五条证据重写，READY_FOR_REVIEW）
- `docs/p0_07_08_09_delivery.md`（顶部加 superseded 说明）
- `docs/development_tasks.md`、`methodology.md`（状态行校正）
- `README.md`（范围校正）

未修改：分析代码、测试、旧数据、references、历史报告包字节。

## 读取范围与实际命令

只读操作：文件读取、`git rev-parse/status`、`sha256sum`、grep、python 静态 JSON 解析（trajectory/manifest/task.toml 读取）。
基线重跑（本轮实际执行）：

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests   → Ran 175 tests, OK
```

其余三个小样命令与 analyze-macro-pilot 在本轮未重跑（上一轮隔离验收记录仍有效，
`reports/macro/macro-pilot-v6/` 为当前依据）；未运行 benchmark/容器/API/验证器。

## 核实结果摘要

### 首选 django__django-16485（静态确认）
- trajectory 存在且行为已读（SHA 506a5091...；30 消息、14 turns、bash×7+editor×7；
  PR=floatformat 崩溃；workspace django__django__5.0）
- verifier 链静态核实：make_test_spec → run_evaluation（Docker+patch+eval_script）
  → get_eval_report（F2P=1 ∧ P2P=1 → resolved；infra_failure 与任务失败分离；SUITE_RAN 防未运行误判）
- verified split → HF `SWE-bench/SWE-bench_Verified`（submit/package.py 确认）
- swebench 02e7a74 的 inference 只内置 mini-SWE-agent；OpenHands 不在本地

### 缺口（5）
- GAP-TASKDATA-001（instance 数据集记录本地无）
- GAP-VERIFIERSPEC-001（目标数据版本是否按 make_test_spec 所需字段可直接加载未核实；拉取不等于输入齐备）
- GAP-HARNESS-001（OpenHands 源码/commit 缺失；mini-SWE-agent 安装/配置未验证）
- GAP-MODEL-001（模型未选；当前 Sonnet 仅为历史配置连续性候选，行为可比性未验证）
- GAP-DOCKER-001（Docker 预检属 P1-00）

### 备选 DocOps word_001（静态确认）
- task.toml/Dockerfile/test.sh/test_outputs.py 均在（SHA 已登记）；
  声明 1 CPU/4096MB/600s verifier；本地无 word_001 历史运行

## 用户需决定（三问；模型与 harness 为独立维度）

1. **模型/provider**（DEC-MODEL）：当前 Claude Sonnet（历史配置连续性候选，行为可比性未验证）
   或任意 OpenAI 兼容端点模型；需确切 model ID、endpoint、费用上限
2. **任务数据**（DEC-TASKDATA）：是否授权拉取 `SWE-bench/SWE-bench_Verified` 该 instance 记录；
   授权范围须含按 `make_test_spec` 字段要求（image/eval_script/log_parser/eval_type/F2P/P2P/repo/version）
   的字段级核对，并允许「需要转换/构建链」作为结论（GAP-VERIFIERSPEC-001）
3. **harness**（DEC-HARNESS）：OpenHands pinned（需另取源码）/ mini-SWE-agent（本地仅有 argv
   构造器，安装配置未验证）/ 推迟 P1-07 wrapper

## 剩余缺口

见 `reports/quality/pilot_evidence.json` gaps 与 `reports/quality/g0_review.md`。
G0 是否通过由评审在 DEC-* 解决后裁定；不自动进入 P1-00 预检。

完成后停止，交回验收。

## 返修记录（评审意见修正，2026-09-10 第二轮）

1. EV-DATASETS-001 locator 修正（benchmark/DATASETS.md → DATASETS.md）；补 test.sh、
   TraceBench manifest、v6 manifest、DATASETS.md 四处 SHA-256
2. 模型与 harness 拆为独立维度；「可比性最高」改为「历史配置连续性候选，行为可比性未验证」；
   mini-SWE-agent 标注「构造器存在不证明已安装/配置可用」
3. 新增 GAP-VERIFIERSPEC-001：make_test_spec 字段级兼容性未核实，拉取不承诺输入齐备
4. 预算停止规则：总 30 min 硬上限 = Agent 25 + Verifier 5；任何分段不得越总限；
   build/setup 另计（15 min 待批准）；verifier 超配额记 verifier_timeout
