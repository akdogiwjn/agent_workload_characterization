# 保留与证据不足（retained-and-unknown）

本页记录：为什么默认保护、为什么不能直接判 A、以及哪些结论仍是猜测/证据不足。

## 一、默认保留（C）的对象与原因

| 对象 | 原因 |
| --- | --- |
| 正式视频 run 的 workspace/输出/rollout/采样/身份/批准/报告/raw manifest | 用户保护清单第 3、5、6 项；回放整理与独立核验依赖原始证据 |
| 失败观察（R01-01、R03-01、R05-MEDIA-01、R06-MEDIA-01、R08-MEDIA-01、旧 assembly/musicians 失败） | 保护清单第 3、5 项；"selected_for_coverage=false"≠无用，失败事实与 trace 需保留；R05/R06/R08 MEDIA-01 是唯一不可重新获得的远端生成结果的一部分 |
| `.working_dir` 内 subject/transition 视频、first_frame、cache、EDL、timeline | 保护清单第 6 项（图片/视频分段、节点产物）；回放必需 |
| data/raw/public 全部、references/repos 全部（含 .git packs） | 保护清单第 2 项；`git rev-parse HEAD`/skill_preflight 校验依赖 references 仓库；.git 是其提交校验依据 |
| OPENSTORYLINE-ENV-01/models（2.0 GiB） | 保护清单第 2 项；openstoryline 本地 ASR 运行时依赖；root 属主、需离线重建/重新下载 |
| .venvs 5 个 + video-use verifier venv（2.62 GiB） | 保护清单第 2 项；每个都有当前测试/脚本/生产消费者（grep 命中） |
| local_archive/project-state-snapshots | 保护清单第 8 项；历史字节核对与恢复依据 |
| 根级 *.launch.json（10 个） | 正式 launch 证据；2 个（e03-runtime-confirm-03、assembly-task1-execution-02）无报告副本，删除即丢唯一 launch 记录；8 个虽有报告副本，仍属正式证据，dedup 需用户决策 |
| 已 evidence 注册的派生分析（OSWORLD-task-behavior-v4、PUBLIC-TRACE-v1/v2、SWEBENCH-INSTANCE-RESULTS-v1） | 删除会破坏 project_state evidence 行，需先按状态更新协议解除登记 |
| OSWorld-MiniMax behavior_analysis 目录（state deliverable 字段） | project_state `completed_limited_deliverables.public_trace_acquisition.behavior_analysis` 引用 v2、`behavior_analysis_v1_preserved` 引用 v1；删除需同步改 state（本轮不改） |

## 二、B 类为什么不能算 A

1. **raw-persistent-copy**：不是"可重建缓存"，是刻意建立的独立副本；被 18 个分析
   manifest 的文件行引用。删除改变"独立副本/异地可核对"保护承诺，且会让 manifest
   文件行失去对应文件。属 B（需用户明确"只保留原始一份"策略）。
2. **remote-closeout**：与 working_dir 字节一致，但它是"closeout 复下载独立记账"的
   证据集合；8 个 manifest 引用。删除虽不改写 ledger 成功事实，但放弃该证据集合。
3. **codex build tar 重复**：不是同一 run 的重复，是两仓各自 build 输入；Dockerfile
   `COPY build/...` 相对路径依赖各自目录。删除任一会破坏对应镜像重建；去重需改
   build 配置（本轮禁止）。
4. **派生分析大文件**：可由 public 输入 + scripts 重生成，但未做字节级一致性验证；
   部分已在 evidence 注册。因此不是"确认可清理"，而是"需用户选择留存策略"。

## 三、D 类 / 结论仍是猜测或证据不足

| 项 | 为什么证据不足 |
| --- | --- |
| OSWorld-MiniMax summary.json 重新生成的字节级一致性 | 未验证 `scripts/osworld_minimax_behavior.py` 输出与现有文件完全一致（生成确定性未证明） |
| 非视频派生分析的消费者全集 | 仅确认部分在 evidence/state deliverable 注册；未逐一证明"无其他脚本读取"（引用查找不是无依赖证明） |
| A-/B-/C-/D-/I1-/I2- 22 个 synthetic 身份目录的并发归属 | 仅能证明当前 tests/scripts/docs/state 无引用、git 未跟踪；不排除属于其他会话未完成工作的可能（建议删除前再次确认无并发会话占用） |
| 根级 8 个有报告副本的 launch.json 是否可 dedup | 未逐份核对报告 manifest 是否把它们列为 evidence 行（仅核对 launch-record 副本字节一致）；不排除个别 manifest 引用根级路径 |
| 35 个空测试目录是否被其他会话占用 | 当前 tests setUp 会重建（mkdir exist_ok），但无法证明此刻无并发进程使用 |
| OPENSTORYLINE-ENV-01/models 恢复成本 | 未核实是离线可重建还是需联网重新下载（模型源/许可未知）；本轮不做此判断 |
| Docker 镜像占用与容器运行态 | 没有可靠执行域视野，未判断是否有容器正在使用候选目录；一律标 unknown，不假定无人使用 |

## 四、清理前的必要前置（供用户参考，本轮不执行）

1. 重算每个目标目录/文件的当前 SHA、bytes、inode/nlink、mtime。
2. 复查并发会话 git 状态与进程占用（ps/docker ps）确认无持有者。
3. 对 manifest 引用的对象：用独立退役回执（如既有 video-cleanup-deletion-receipt-v1
   协议）登记"原文件已删、原始 SHA 留存、失败事实保留"，不改写旧 manifest/state。
4. A 类删除仍需用户下一次明确批准；B 类需用户改变留存策略后另行批准。
