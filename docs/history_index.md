# 历史资料索引与迁移说明

更新：2026-10-16。本页用于查历史，不是当前规范或执行授权。当前目标见[current_scope.md](current_scope.md)，进度见[project_status.md](project_status.md)。

## 迁移范围

- 原docs中的76份历史文档及根目录methodology.md，共77份，均已移到local_archive；docs仅保留7份现行文档，另有本索引与机器可读迁移/审计登记。
- 第一轮18份位于local_archive/20261016；本轮59份位于local_archive/20261016-full-docs。原字节不改，逐份记录SHA-256；本轮编辑前的当前入口/代码另有before-edit备份。
- 归档目录被Git忽略，不随GitHub分发；旧已跟踪文档也可查Git历史。迁移不释放磁盘空间，未提交或推送。
- 旧Markdown内部相对链接仍以原目录为基准；阅读时按下表定位，不声称原文在归档位置的每个内部链接自动可点。

## 报告引用如何处理

当前页面、CLI提示、状态渲染与HTML生成器的导航/读取位置已更新。历史报告、HTML、raw、批准、manifest、identity不做批量替换：改路径也会改变其哈希，不能伪装成原交付。
例外收尾：`reports/quality/g0_review.md`仅修正5处阅读链接并明确标记导航修订；修订前原文已按原SHA保存在`local_archive/20261016-repair/before-edit/`。正式运行记录、批准及manifest不改写。
历史记录中的旧路径保留为逻辑来源标识，由[archive_index.json](archive_index.json)给出实际位置；[引用审计](archive_reference_audit.json)逐文件列出引用及能核对的原登记哈希。新目标文档可替代日常阅读入口，不能替代历史批准或身份里的原字节。

只读定位和可选哈希核验示例（不执行实验）：
```bash
python3 -B scripts/audit_document_archive.py --resolve docs/g1_consolidated_review.md
```
核验某份manifest时追加`--sha256 原登记的完整SHA256`。不匹配会报错；迁移前已有的版本漂移仍为漂移，不能当作迁移成功修复。

## 原路径到本机归档

| 原逻辑路径 | 本机历史原文 | 日常应读 |
| --- | --- | --- |
| <a id="docs-cpu_01_execution_prompt-md"></a>`docs/cpu_01_execution_prompt.md` | [归档原文](../local_archive/20261016/docs/cpu_01_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-cpu_01_handoff-md"></a>`docs/cpu_01_handoff.md` | [归档原文](../local_archive/20261016/docs/cpu_01_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-cpu_02_execution_prompt-md"></a>`docs/cpu_02_execution_prompt.md` | [归档原文](../local_archive/20261016/docs/cpu_02_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-g1_01_b_delivery-md"></a>`docs/g1_01_b_delivery.md` | [归档原文](../local_archive/20261016/docs/g1_01_b_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-g1_01_b_execution_prompt-md"></a>`docs/g1_01_b_execution_prompt.md` | [归档原文](../local_archive/20261016/docs/g1_01_b_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-g1_01_b_handoff-md"></a>`docs/g1_01_b_handoff.md` | [归档原文](../local_archive/20261016/docs/g1_01_b_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-g1_01_delivery-md"></a>`docs/g1_01_delivery.md` | [归档原文](../local_archive/20261016/docs/g1_01_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-g1_01_execution_prompt-md"></a>`docs/g1_01_execution_prompt.md` | [归档原文](../local_archive/20261016/docs/g1_01_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-g1_01_handoff-md"></a>`docs/g1_01_handoff.md` | [归档原文](../local_archive/20261016/docs/g1_01_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-mini_2_4_6_static_handoff-md"></a>`docs/mini_2_4_6_static_handoff.md` | [归档原文](../local_archive/20261016/docs/mini_2_4_6_static_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-p0_05_delivery-md"></a>`docs/p0_05_delivery.md` | [归档原文](../local_archive/20261016/docs/p0_05_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-p0_05_luna_handoff-md"></a>`docs/p0_05_luna_handoff.md` | [归档原文](../local_archive/20261016/docs/p0_05_luna_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-p0_10_handoff-md"></a>`docs/p0_10_handoff.md` | [归档原文](../local_archive/20261016/docs/p0_10_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-pilot_harness_model_delivery-md"></a>`docs/pilot_harness_model_delivery.md` | [归档原文](../local_archive/20261016/docs/pilot_harness_model_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-pilot_harness_model_handoff-md"></a>`docs/pilot_harness_model_handoff.md` | [归档原文](../local_archive/20261016/docs/pilot_harness_model_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-repository_closeout_delivery-md"></a>`docs/repository_closeout_delivery.md` | [归档原文](../local_archive/20261016/docs/repository_closeout_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-repository_closeout_execution_prompt-md"></a>`docs/repository_closeout_execution_prompt.md` | [归档原文](../local_archive/20261016/docs/repository_closeout_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-repository_closeout_handoff-md"></a>`docs/repository_closeout_handoff.md` | [归档原文](../local_archive/20261016/docs/repository_closeout_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-adapter_framework-md"></a>`docs/adapter_framework.md` | [归档原文](../local_archive/20261016-full-docs/docs/adapter_framework.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-agent_landscape-md"></a>`docs/agent_landscape.md` | [归档原文](../local_archive/20261016-full-docs/docs/agent_landscape.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-agentx_adapter-md"></a>`docs/agentx_adapter.md` | [归档原文](../local_archive/20261016-full-docs/docs/agentx_adapter.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-applied_compute_adapter-md"></a>`docs/applied_compute_adapter.md` | [归档原文](../local_archive/20261016-full-docs/docs/applied_compute_adapter.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-benchmark_selection-md"></a>`docs/benchmark_selection.md` | [归档原文](../local_archive/20261016-full-docs/docs/benchmark_selection.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-coding_pilot_delivery-md"></a>`docs/coding_pilot_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/coding_pilot_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-coding_pilot_handoff-md"></a>`docs/coding_pilot_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/coding_pilot_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-cpu_01_delivery-md"></a>`docs/cpu_01_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_01_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-cpu_02_delivery-md"></a>`docs/cpu_02_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-cpu_02_execution_environment_plan-md"></a>`docs/cpu_02_execution_environment_plan.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_execution_environment_plan.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-cpu_02_handoff-md"></a>`docs/cpu_02_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-cpu_02_namespace_sudo_compare-md"></a>`docs/cpu_02_namespace_sudo_compare.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_namespace_sudo_compare.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-cpu_02_perf_permission_check-md"></a>`docs/cpu_02_perf_permission_check.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_perf_permission_check.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-cpu_02_permission_review-md"></a>`docs/cpu_02_permission_review.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_permission_review.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-cpu_02_pid_diagnostic_delivery-md"></a>`docs/cpu_02_pid_diagnostic_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_pid_diagnostic_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-cpu_02_r1_delivery-md"></a>`docs/cpu_02_r1_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/cpu_02_r1_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-development_tasks-md"></a>`docs/development_tasks.md` | [归档原文](../local_archive/20261016-full-docs/docs/development_tasks.md) | [当前任务](current_task.md) |
| <a id="docs-environment_adaptation_delivery-md"></a>`docs/environment_adaptation_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/environment_adaptation_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-environment_adaptation_handoff-md"></a>`docs/environment_adaptation_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/environment_adaptation_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-first_run_approval-md"></a>`docs/first_run_approval.md` | [归档原文](../local_archive/20261016-full-docs/docs/first_run_approval.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-first_run_preparation_delivery-md"></a>`docs/first_run_preparation_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/first_run_preparation_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-first_run_preparation_handoff-md"></a>`docs/first_run_preparation_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/first_run_preparation_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-g1_02_delivery-md"></a>`docs/g1_02_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/g1_02_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-g1_02_execution_prompt-md"></a>`docs/g1_02_execution_prompt.md` | [归档原文](../local_archive/20261016-full-docs/docs/g1_02_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-g1_02_handoff-md"></a>`docs/g1_02_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/g1_02_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-g1_consolidated_review-md"></a>`docs/g1_consolidated_review.md` | [归档原文](../local_archive/20261016-full-docs/docs/g1_consolidated_review.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-ir_v0_1-md"></a>`docs/ir_v0_1.md` | [归档原文](../local_archive/20261016-full-docs/docs/ir_v0_1.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-ir_v0_2-md"></a>`docs/ir_v0_2.md` | [归档原文](../local_archive/20261016-full-docs/docs/ir_v0_2.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-legacy_asset_audit-md"></a>`docs/legacy_asset_audit.md` | [归档原文](../local_archive/20261016-full-docs/docs/legacy_asset_audit.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-macro_coverage-md"></a>`docs/macro_coverage.md` | [归档原文](../local_archive/20261016-full-docs/docs/macro_coverage.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-mini_2_4_6_static_delivery-md"></a>`docs/mini_2_4_6_static_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/mini_2_4_6_static_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-model_smoke_delivery-md"></a>`docs/model_smoke_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/model_smoke_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-model_smoke_handoff-md"></a>`docs/model_smoke_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/model_smoke_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-p0_01_delivery-md"></a>`docs/p0_01_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_01_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-p0_02_delivery-md"></a>`docs/p0_02_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_02_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-p0_03_delivery-md"></a>`docs/p0_03_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_03_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-p0_04_delivery-md"></a>`docs/p0_04_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_04_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-p0_07_08_09_delivery-md"></a>`docs/p0_07_08_09_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_07_08_09_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-p0_07_08_09_handoff-md"></a>`docs/p0_07_08_09_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_07_08_09_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-p0_07_g0_delivery-md"></a>`docs/p0_07_g0_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_07_g0_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-p0_07_g0_handoff-md"></a>`docs/p0_07_g0_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_07_g0_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-p0_10_delivery-md"></a>`docs/p0_10_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/p0_10_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-pilot_execution_spec-md"></a>`docs/pilot_execution_spec.md` | [归档原文](../local_archive/20261016-full-docs/docs/pilot_execution_spec.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-pilot_harness_model_compatibility-md"></a>`docs/pilot_harness_model_compatibility.md` | [归档原文](../local_archive/20261016-full-docs/docs/pilot_harness_model_compatibility.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-pilot_taskdata_delivery-md"></a>`docs/pilot_taskdata_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/pilot_taskdata_delivery.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_delivery-md"></a>`docs/run_02_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-run_02_execution_prompt-md"></a>`docs/run_02_execution_prompt.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_handoff-md"></a>`docs/run_02_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_launch_readiness_delivery-md"></a>`docs/run_02_launch_readiness_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_launch_readiness_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-run_02_launch_readiness_handoff-md"></a>`docs/run_02_launch_readiness_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_launch_readiness_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_launch_readiness_prompt-md"></a>`docs/run_02_launch_readiness_prompt.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_launch_readiness_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_r1_delivery-md"></a>`docs/run_02_r1_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_r1_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-run_02_r1_execution_prompt-md"></a>`docs/run_02_r1_execution_prompt.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_r1_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_r1_handoff-md"></a>`docs/run_02_r1_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_r1_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_r2_delivery-md"></a>`docs/run_02_r2_delivery.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_r2_delivery.md) | [当前目标/规范](current_scope.md) |
| <a id="docs-run_02_r2_execution_prompt-md"></a>`docs/run_02_r2_execution_prompt.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_r2_execution_prompt.md) | [当前任务](current_task.md) |
| <a id="docs-run_02_r2_handoff-md"></a>`docs/run_02_r2_handoff.md` | [归档原文](../local_archive/20261016-full-docs/docs/run_02_r2_handoff.md) | [当前任务](current_task.md) |
| <a id="docs-videoweaver_adapter-md"></a>`docs/videoweaver_adapter.md` | [归档原文](../local_archive/20261016-full-docs/docs/videoweaver_adapter.md) | [当前目标/规范](current_scope.md) |
| <a id="methodology-md"></a>`methodology.md` | [归档原文](../local_archive/20261016-full-docs/methodology.md) | [当前目标/规范](current_scope.md) |

## 报告引用核查结果

已扫描当前源码、文档、reports、env登记、catalog及generated raw文本，规模约1.98GB；准确文件数、字节数与逐项结果见[引用审计JSON](archive_reference_audit.json)。未扫描公开trace正文、第三方源码和虚拟环境，因为它们不是本项目文档的现行引用消费者。

13处保存了SHA的历史引用均指向旧methodology或development_tasks，现存文档在本轮迁移前已经不是它们登记的版本，保持`preexisting_content_drift`，不认作哈希通过。其余无原登记SHA的引用只能确认迁移定位，不能宣称原版本一致。

以下是报告到归档原文的阅读导航，不改写报告本体或其manifest：

| 原报告/记录 | 新的历史文档阅读位置 | 哈希说明 |
| --- | --- | --- |
| [reports/analysis/CODING-RESOURCE-LINK-feasibility-v1/manifest.json](../reports/analysis/CODING-RESOURCE-LINK-feasibility-v1/manifest.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md) | 1项迁移前版本漂移，未修复哈希 |
| [reports/analysis/PROJECT-characterization-synthesis-v1/evidence_matrix.json](../reports/analysis/PROJECT-characterization-synthesis-v1/evidence_matrix.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md) | 仅作定位；不新增历史一致性结论 |
| [reports/analysis/PROJECT-characterization-synthesis-v1/manifest.json](../reports/analysis/PROJECT-characterization-synthesis-v1/manifest.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md)、[docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 2项迁移前版本漂移，未修复哈希 |
| [reports/analysis/PROJECT-characterization-synthesis-v2/evidence_matrix.json](../reports/analysis/PROJECT-characterization-synthesis-v2/evidence_matrix.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md) | 仅作定位；不新增历史一致性结论 |
| [reports/analysis/PROJECT-characterization-synthesis-v2/manifest.json](../reports/analysis/PROJECT-characterization-synthesis-v2/manifest.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md) | 1项迁移前版本漂移，未修复哈希 |
| [reports/analysis/PROJECT-characterization-synthesis-v3/evidence_matrix.json](../reports/analysis/PROJECT-characterization-synthesis-v3/evidence_matrix.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md) | 仅作定位；不新增历史一致性结论 |
| [reports/cpu/CPU-01/APPROVAL.json](../reports/cpu/CPU-01/APPROVAL.json) | [docs/cpu_01_delivery.md](../local_archive/20261016-full-docs/docs/cpu_01_delivery.md) | 仅作定位；不新增历史一致性结论 |
| [reports/cpu/CPU-02/APPROVAL.json](../reports/cpu/CPU-02/APPROVAL.json) | [docs/cpu_02_delivery.md](../local_archive/20261016-full-docs/docs/cpu_02_delivery.md) | 仅作定位；不新增历史一致性结论 |
| [reports/cpu/CPU-02/permission-confirmation/APPROVAL.json](../reports/cpu/CPU-02/permission-confirmation/APPROVAL.json) | [docs/cpu_02_execution_environment_plan.md](../local_archive/20261016-full-docs/docs/cpu_02_execution_environment_plan.md) | 仅作定位；不新增历史一致性结论 |
| [reports/cpu/CPU-02/pid-diagnostic/APPROVAL.json](../reports/cpu/CPU-02/pid-diagnostic/APPROVAL.json) | [docs/cpu_02_pid_diagnostic_delivery.md](../local_archive/20261016-full-docs/docs/cpu_02_pid_diagnostic_delivery.md) | 仅作定位；不新增历史一致性结论 |
| [reports/cpu/CPU-02/retries/R1/APPROVAL.json](../reports/cpu/CPU-02/retries/R1/APPROVAL.json) | [docs/cpu_02_r1_delivery.md](../local_archive/20261016-full-docs/docs/cpu_02_r1_delivery.md) | 仅作定位；不新增历史一致性结论 |
| [reports/html/PROJECT-RESULTS-v1/manifest.json](../reports/html/PROJECT-RESULTS-v1/manifest.json) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 1项迁移前版本漂移，未修复哈希 |
| [reports/html/PROJECT-RESULTS-v1/verification.json](../reports/html/PROJECT-RESULTS-v1/verification.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md)、[docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 仅作定位；不新增历史一致性结论 |
| [reports/html/PROJECT-RESULTS-v2/manifest.json](../reports/html/PROJECT-RESULTS-v2/manifest.json) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md)、[methodology.md](../local_archive/20261016-full-docs/methodology.md) | 2项迁移前版本漂移，未修复哈希 |
| [reports/html/PROJECT-RESULTS-v2/verification.json](../reports/html/PROJECT-RESULTS-v2/verification.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md)、[docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 仅作定位；不新增历史一致性结论 |
| [reports/html/PROJECT-RESULTS-v3/manifest.json](../reports/html/PROJECT-RESULTS-v3/manifest.json) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md)、[methodology.md](../local_archive/20261016-full-docs/methodology.md) | 2项迁移前版本漂移，未修复哈希 |
| [reports/html/PROJECT-RESULTS-v3/verification.json](../reports/html/PROJECT-RESULTS-v3/verification.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md)、[docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 仅作定位；不新增历史一致性结论 |
| [reports/html/PROJECT-RESULTS-v4/manifest.json](../reports/html/PROJECT-RESULTS-v4/manifest.json) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md)、[methodology.md](../local_archive/20261016-full-docs/methodology.md) | 2项迁移前版本漂移，未修复哈希 |
| [reports/html/PROJECT-RESULTS-v4/verification.json](../reports/html/PROJECT-RESULTS-v4/verification.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md) | 仅作定位；不新增历史一致性结论 |
| [reports/html/PROJECT-RESULTS-v5/manifest.json](../reports/html/PROJECT-RESULTS-v5/manifest.json) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md)、[methodology.md](../local_archive/20261016-full-docs/methodology.md) | 2项迁移前版本漂移，未修复哈希 |
| [reports/html/PROJECT-RESULTS-v5/verification.json](../reports/html/PROJECT-RESULTS-v5/verification.json) | [methodology.md](../local_archive/20261016-full-docs/methodology.md) | 仅作定位；不新增历史一致性结论 |
| [reports/quality/g0_review.md](../reports/quality/g0_review.md) | [docs/coding_pilot_handoff.md](../local_archive/20261016-full-docs/docs/coding_pilot_handoff.md)、[docs/p0_07_08_09_delivery.md](../local_archive/20261016-full-docs/docs/p0_07_08_09_delivery.md)、[docs/coding_pilot_delivery.md](../local_archive/20261016-full-docs/docs/coding_pilot_delivery.md)、[docs/legacy_asset_audit.md](../local_archive/20261016-full-docs/docs/legacy_asset_audit.md)、[docs/model_smoke_delivery.md](../local_archive/20261016-full-docs/docs/model_smoke_delivery.md) | 仅作定位；不新增历史一致性结论 |
| [reports/quality/pilot_evidence.json](../reports/quality/pilot_evidence.json) | [docs/pilot_execution_spec.md](../local_archive/20261016-full-docs/docs/pilot_execution_spec.md) | 仅作定位；不新增历史一致性结论 |
| [reports/resource/G1-01-A/G1-01-A-20260913T074244Z/g1_evidence.md](../reports/resource/G1-01-A/G1-01-A-20260913T074244Z/g1_evidence.md) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 仅作定位；不新增历史一致性结论 |
| [reports/resource/G1-01-A/G1-01-A-R2-20260913T075652Z-r2/g1_evidence.md](../reports/resource/G1-01-A/G1-01-A-R2-20260913T075652Z-r2/g1_evidence.md) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 仅作定位；不新增历史一致性结论 |
| [reports/resource/G1-01-A/G1-01-A-R3-20260913T082046Z/g1_evidence.md](../reports/resource/G1-01-A/G1-01-A-R3-20260913T082046Z/g1_evidence.md) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 仅作定位；不新增历史一致性结论 |
| [reports/resource/G1-01-A/G1-01-A-R4-20260913T085846Z/g1_evidence.md](../reports/resource/G1-01-A/G1-01-A-R4-20260913T085846Z/g1_evidence.md) | [docs/development_tasks.md](../local_archive/20261016-full-docs/docs/development_tasks.md) | 仅作定位；不新增历史一致性结论 |
| [reports/resource/G1-02/APPROVAL.json](../reports/resource/G1-02/APPROVAL.json) | [docs/g1_02_handoff.md](../local_archive/20261016-full-docs/docs/g1_02_handoff.md) | 仅作定位；不新增历史一致性结论 |

## 验证限制

REPEAT-02历史输入中的`docs/trace_contract.md`及`semantic_recorder.py`与当前工作区存在既有版本漂移。阅读器现区分“封存实验/身份/分析产物”和“当前规范/采集源码上下文”：前者不匹配仍拒绝，后者逐项记录原SHA、当前SHA及`match=false`，页面与verification均显式标为`PARTIAL`，不宣称历史源码一致或当前代码可复现旧身份。分析代码本身仍严格核验。

HTML完整生成回归已在临时目录通过，未覆盖v1～v5正式阅读包；没有恢复不存在的旧源码、修改原登记哈希或执行新实验。
