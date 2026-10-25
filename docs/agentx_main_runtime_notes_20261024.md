# AgentX main 运行与证据说明（2026-10-24）

本页记录 AgentX 证据归位后，今后只在本仓库 `main` 中维护和运行的入口、输入位置、环境路径，以及历史路径的解析方法。本轮将八个 2026-10-23 的独立 AgentX 工作树合并收拢；历史证据不改写，独立备份保留。

## 1. AgentX 入口（main）

| 用途 | 入口 |
| --- | --- |
| 离线分析/审计脚本 | `scripts/agentx_deep_*.py`、`scripts/agentx_deepseek_*.py`、`scripts/agentx_replay_smoke_*.py` |
| 回环 mock 服务 | `scripts/agentx_loopback_mock.py` |
| mock 回放运行/校验 | `scripts/agentx_replay_smoke_run.py`、`scripts/agentx_replay_smoke_verify.py` |
| 路径解析层 | `scripts/agentx_worktree_locations.py`（只读，不授权） |
| 迁移索引 | `docs/agentx_worktree_migration_index_20261024.json` |

## 2. 输入与环境位置

- 六个 AgentX 运行输入批次已从旧工作树迁移到本仓库（Git 忽略，不随提交分发）：
  - `data/raw/agentx-deepseek-pilot-01`
  - `data/raw/agentx-deepseek-branches-01`（含 `agentx-deepseek-branches-01-preparation-failed-01` 四个未备份文件）
  - `data/raw/agentx-deepseek-coverage-01`
  - `data/raw/agentx-deepseek-repeats-01`
  - `data/raw/agentx-deepseek-five-repeats-01`
  - `data/raw/agentx-replay-smoke-01`（tokenizer、hf-cache、sessions、attempts）
- 环境配置（已跟踪）：`env/agentx-{pilot,branches,coverage,repeats,five-repeats,replay-smoke}-01/`，内含 `plan.json`、`requirements-lock.txt`、`status.json` 等。
- mock 回放环境：`.venvs/agentx-replay/`（Git 忽略）。由旧 `agentx_replay_smoke_20261023/.venv` 原样复制并改写绝对路径而来；Python 3.11.6（系统 `/usr/bin/python3`），`agentx-harness==1.0.7`、`transformers==5.20.2`、`numpy==2.4.6`、`tokenizers==0.23.3`、`safetensors==0.8.0`，aiperf commit `0f885254c30522e58b601848ca70d5bed1662694`。运行 mock 链使用显式解释器 `.venvs/agentx-replay/bin/python` 与 `.venvs/agentx-replay/bin/aiperf`。

## 3. 历史路径如何解析

历史 manifest、计划、批准和报告中的旧绝对路径保持原义，不批量改写、不刷新哈希。读取时经 `scripts/agentx_worktree_locations.py` 的 `resolve()` 解析到当前物理位置：

- 旧工作树下 `data/raw/<batch>/…` → `ROOT/data/raw/<batch>/…`
- 旧工作树下 `env/`、`reports/`、`scripts/` 等已跟踪子树 → `ROOT/…`
- 旧→新映射与逐批树哈希见 `docs/agentx_worktree_migration_index_20261024.json`

历史 as-run 脚本身份由 `env/agentx-*/plan.json` 的 `code` 哈希绑定；这些脚本在 main 中与冻结版本字节一致。**历史执行脚本 `agentx_deepseek_repeats.py`、`agentx_deepseek_finish_repeats.py` 保持原字节未改**（其哈希被各自 plan 登记）；仅离线分析/回放脚本做了路径解析接线。后续新执行须使用当前代码并冻结新身份。

## 4. 最终证据备份与恢复

- 独立备份：`/home/lcq/agentx_evidence_backup_20261023/agentx-evidence-20261023-final.tar.gz`
  - SHA-256：`7e0104190ececcab755ba9fee682a8aaa68b5c45bcb7ff94889f4447f384322b`（已核验）
  - 索引：`docs/agentx_evidence_backup_index_20261023.json`；恢复说明：备份目录 `RESTORE.md`
- 备份覆盖六个工作树（replay_smoke/pilot/branches/coverage/repeats/five_repeats）的证据载荷；内容寻址存储于 `objects/sha256/<digest>`。
- 主仓 `local_archive/20261023-agentx-main-integration-snapshots/` 保存 main_integration 的 31 个状态快照（30 个快照 + manifest，逐文件 SHA 登记在迁移索引）。
- 已删除工作树的独有未备份文件已按上述迁移/归档处理，不再保留整树副本。

## 5. 工作树与分支处置（2026-10-24）

已移除的工作树（`git worktree remove`）：

- `/home/lcq/agentx_deepseek_branches_20261023`
- `/home/lcq/agentx_deepseek_coverage_20261023`
- `/home/lcq/agentx_deepseek_five_repeats_20261023`
- `/home/lcq/agentx_deepseek_pilot_20261023`
- `/home/lcq/agentx_deepseek_repeats_20261023`
- `/home/lcq/agentx_main_integration_20261023`
- `/home/lcq/agentx_replay_smoke_20261023`
- `/home/lcq/agentx_state_option_tests_20261023`

已删除的已合并本地分支（及确认合并的对应远程分支）：`task/agentx-deepseek-{branches,coverage,five-repeats,pilot,repeats}-20261023`、`task/agentx-main-integration-20261023`、`task/agentx-replay-smoke-20261023`、`task/agentx-state-option-tests-20261023`。

保留项：

- `main` 与 `origin/main`
- `/home/lcq/agentx_evidence_backup_20261023`（独立备份）
- `/home/lcq/awc_video_publish_20261025`（`task/video-checkpoint-20261025`，不在本轮清理范围）
- 所有视频文件、模型、环境与证据

## 6. 边界

- 本页只作运行/恢复导航，不提供执行授权；`execution_authorization` 未变，Gate/CPU-02/Replay 不变。
- 未重放真实 API 请求、未重跑正式实验、未重新生成历史分析报告；离线验证仅确认 main 内路径可用。
