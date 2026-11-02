# 仓库清理候选审计（仅分析，零删除）— REPOSITORY-CLEANUP-CANDIDATE-AUDIT-20261102-01

更新：2026-11-02。基于已有清点（REPOSITORY-CLEANUP-INVENTORY-20261102-01）与本轮逐项核验。
本轮未删除/移动/压缩替换/硬链接替换任何文件；未运行旧 cleanup 脚本；未改历史 raw/报告/
身份/批准/manifest；未改 project_state。仅在本报告目录生成分析材料。

## 结论先行

- **真正占空间**：`data`（11.9 GiB 分配，其中 public 输入 6.93 GiB、generated 4.51 GiB）、
  `reports`（4.09 GiB，其中 OSWorld/SWE/AgentX/公开 trace 派生分析占约 2.3 GiB）、
  `references`（3.44 GiB 上游仓库含 .git）、`.venvs`（2.62 GiB 运行时依赖）、
  `env`（2.54 GiB，其中 OPENSTORYLINE 模型 2.0 GiB、build 输入约 0.3 GiB）。
- **A 类（确认可清理）约 2.5 MB**：仅 python 字节码/pytest 缓存、空测试目录、
  2 个几字节的测试夹具、22 个孤儿 synthetic 身份目录、10 个 0 字节根级 launch.log。
  **实质大文件没有能直接判定 A 类的对象。**
- **B 类（需用户改变留存策略后才能清理）约 5.59 GiB**：raw-persistent-copy 独立副本
  （1.56 GiB）、ViMax remote-closeout 复下载（622 MB）、codex build 包重复（105 MB）、
  OSWorld-MiniMax 派生 summary.json（1.29 GiB）、以及其他公开 trace 派生分析大文件
  （约 2.0 GiB，部分证据注册）。
- **C/D（保留或证据不足）**：全部正式 trace/媒体/身份/批准、public 输入、模型、
  venv、references、upstream .git、以及 evidence 注册的派生分析。

## 真正占空间的是什么（并非缓存）

| 对象 | 分配空间 | 性质 |
| --- | ---: | --- |
| data/raw/public（agentx_full 1.8G、agentx 544M、osworld2 829M、open_source 等） | 6.93 GiB | 公开输入，受保护 |
| OPENSTORYLINE-ENV-01/models（paraformer/punc/fsmn 模型） | 2.0 GiB | 运行时 ASR 依赖，受保护 |
| data/raw/generated 视频正式运行（R01–R09 及相关） | 3.26 GiB | 正式 trace/媒体，受保护 |
| references/repos/*/.git packs（agentic-vbench 479M、agentcgroup/* 706M 等） | ~2.9 GiB | 上游仓库 git 历史 |
| reports/analysis 非视频派生分析（OSWorld/SWE/AgentX/公开 trace） | ~2.3 GiB | 派生分析，多数证据/交付物注册 |
| .venvs（5 个）+ video-use verifier venv | 2.62 GiB | 运行时依赖，均有消费者 |
| reports/analysis 视频分析 + raw-persistent-copy | 1.61 GiB + 1.56 GiB | 正式分析 + 独立副本 |

## A/B 可清多少

- **A 类合计约 2.5 MB**（字节码/缓存 1.85 MB + synthetic 身份 0.64 MB + 空目录块 + 0 字节日志）。
- **B 类合计约 5.59 GiB**，分四类：
  1. **raw-persistent-copy 18 个副本 ≈ 1.56 GiB**：逐文件 SHA 与正式 raw 内部 run 目录
     字节一致（15/18 IDENTICAL；3 个 SUBSET-MATCH，差异仅为副本内额外的 README/manifest）。
     删除会破坏 18 个分析 manifest 的文件行引用，并放弃"独立副本"保护承诺；
     需用户明确选择"只保留一份"策略。
  2. **ViMax remote-closeout 复下载 ≈ 622 MB（10 个 run）**：与各自 workspace
     `.working_dir` 媒体 100% 字节一致（已流式 SHA 全量核验）。账本/run-record 已记录
     "closeout SUCCEEDED 复下载"，删除媒体副本不改写成功事实；但 8 个分析 manifest
     引用这些文件行，需用户选择保留策略。
  3. **codex build 包重复 105 MB**：`env/video/videoweaver/build/` 与
     `env/video/video-use/codex-bailian-integration-01/build/` 两个 tar 字节一致
     （SHA a7261e65…）。各被各自 Dockerfile COPY，删除任一影响对应镜像重建。
  4. **公开 trace 派生分析 ≈ 3.3 GiB**：OSWorld-MiniMax summary.json v1/v2
     （1.29 GiB）、SWE-REBENCH/AGENTX/PUBLIC-TRACE-v3/SWEBENCH-COVERAGE 等大 JSONL
     （约 2.0 GiB）。可由已保留的 public 输入 + scripts 重新生成（未验证字节级一致）；
     部分目录在 project_state evidence 注册（OSWORLD-task-behavior-v4、
     PUBLIC-TRACE-v1/v2、SWEBENCH-INSTANCE-RESULTS-v1），删除需先解除证据登记。

## 最值得用户决策的前 20 项

| # | 路径 | 大小 | A/B/C/D | 理由 |
| --- | --- | ---: | --- | --- |
| 1 | 18 个 reports/analysis/*/raw-persistent-copy | 1.56 GiB | B | 字节级重复副本，破坏独立副本保护与 18 manifest |
| 2 | ViMax 各 run remote-closeout/*.mp4 | 622 MB | B | 与 working_dir 100% 一致，账本已记成功 |
| 3 | reports/analysis/OSWORLD-MINIMAX-M3-behavior-v1/v2/summary.json | 1.29 GiB | B | 派生分析，可重生成，state deliverable 引用目录 |
| 4 | env/video/videoweaver/build/codex-aarch64…tar.gz | 105 MB | B | 与 video-use build tar 一致；Dockerfile 依赖 |
| 5 | reports/analysis/SWE-REBENCH-behavior-v1/v2/v3 per_trajectory.jsonl 等 | ~120 MB | B | 派生分析，非证据注册 |
| 6 | reports/analysis/AGENTX-DEEP-ANALYSIS-v1/*.jsonl | ~124 MB | B | 派生分析，非证据注册 |
| 7 | reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/*.jsonl | ~132 MB | B | 派生分析，v3 未注册为 evidence |
| 8 | reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1/*.jsonl | ~79 MB | B | 派生分析，非证据注册 |
| 9 | reports/analysis/OSWORLD-task-behavior-v2/v3 per_trajectory.jsonl | ~68 MB | B/D | 派生；v4 已注册，v2/v3 未注册 |
| 10 | data/raw/generated 35 个空测试目录（CLI-*/OSL-*） | ~0.1 MB | A | 空目录，测试 setUp 会重建 |
| 11 | env/video/openstoryline 22 个 A-/B-/C-/D-/I1-/I2-<hex> synthetic 身份目录 | 0.64 MB | A | 孤儿 synthetic 夹具，无消费者 |
| 12 | scripts/tests/src __pycache__ + .pytest_cache（43 文件） | 1.85 MB | A | 字节码/缓存，自动重建 |
| 13 | 根级 *.launch.log（10 个 0 字节） | 0 MB | A | 空文件，仅路径引用 |
| 14 | data/raw/generated/OSL-ASSEMBLY-IDENTITY-FREEZE-REPAIR-TEST evil/outside.mp4 | 11 B | A | 测试夹具残留，测试自建 |
| 15 | 根级 *.launch.json（10 个） | ~8 KB | C | 正式 launch 证据；8 个有报告副本（B dedup 候选）、2 个无副本必须保留 |
| 16 | data/raw/public/agentx_full/*traces.jsonl | 1.8 GiB | C | public 输入，受保护 |
| 17 | OPENSTORYLINE-ENV-01/models（3 个模型） | 2.0 GiB | C | 运行时 ASR 依赖 |
| 18 | .venvs 5 个 + video-use verifier venv | 2.62 GiB | C | 运行时依赖 |
| 19 | references/repos/*/.git packs | ~2.9 GiB | C | 上游仓库 git 历史/校验依据 |
| 20 | 正式视频 run 媒体/rollout/身份/批准（R01–R09 等） | 3.26 GiB | C | 正式 trace，受保护 |

## 无需删除的保护对象（节选）

- 全部正式视频运行：OpenStoryline R01–R04、ViMax R05–R08（含 MEDIA-01 失败观察）、
  video-use R09；其原生 rollout、资源采样、身份/批准、报告、raw manifest、容器日志。
- 公开输入（agentx/agentx_full/osworld2/open_source 等）与上游 references 仓库及 .git。
- 模型（OPENSTORYLINE-ENV-01/models）、所有 venv、离线 build 材料。
- local_archive 状态/编辑快照（恢复与历史字节核对依赖）。
- 凭据与敏感配置（未读取、未打印）。
- 已 evidence 注册的派生分析文件与全部历史 manifest。

## 口径

- 表观/分配均来自 inventory；A/B 统计扣除目录 inode（目录块未计入文件统计）。
- raw 与副本未同时计为可删：raw-persistent-copy 列为 B，原始 raw 始终保留。
- 硬链接：全仓无共享 inode 的重复名（nlink=1，逐对核验），无因硬链接多路径造成的
  可释放空间虚增。
- 无法精确计算因素：目录块按 ~4KiB/目录估算；B 类派生分析的"可重生成"未做字节级
  验证（标记 medium/low 置信度）；容器镜像占用（约 10+ GiB）不在本仓库文件统计内，
  且本轮禁止操作 Docker。
