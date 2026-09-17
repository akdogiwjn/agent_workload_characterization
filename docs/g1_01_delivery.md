# G1-01-A 交付：工具时间证据、宿主开销与资源计量核对（A 阶段）

日期：2026-09-13。状态：**A 返修轮完成并停止（R2）；B 仅审批提案（未执行任何容器操作）；不宣布 G1 通过**。

当前有效批：`reports/resource/G1-01-A/G1-01-A-R2-20260913T075652Z-r2/`（8 文件；supersedes 首批 `G1-01-A-20260913T074244Z`，后者保留不覆盖）。封存数据与 RUN-01-C-v2 全程零改动。

## 返修轮（评审四组意见，全部离线修复）

**R24：工具配对与时间可信度**
- `pair_tools()` 增加 **ID 交叉核对**：action 与 tool 消息两侧都有 ID 时必须一致（评审注入 A/B 不一致 → 现报 `id_mismatch` 不接受）；重复 action ID 报 `duplicate_action_id`；孤立 tool 结果（无对应 action）单独跟踪。实测 RUN-01-C：0 异常。
- 新增 `anchor_consistency()`：ok 状态行数 vs assistant-with-actions 数量一致性（26/26 match；不一致时报数量并取短前缀，**不静默吸收**）。
- 残差语义更正：`anchor_residual_ns_max` 语义字段明确 **"observed max spread, NOT a proven calibration error bound"**；下游引用字段同步改名。

**R25：宿主证据完整落盘**
- `host_process.jsonl` 由裸快照行改为**结构化文档**：identity（pid + starttime_ticks + 复用语义说明）、units（clk_tck/page_size/tick 与 RSS 语义）、coverage（首/末 monotonic、快照数、final_read_status）、逐快照 records、**完整 summary**（含 collector 读耗时）。内存-only 缺口消除。
- 写入失败不再静默：`host_archive_status` + recorder infra 事件记录。

**R26：机制脚本控制与计量**
- 每用例/每对的等待循环内**硬 deadline 检查**（超限 kill + `deadline_exceeded`/`child_rc` 留证）；批 deadline 在**每个用例前**检查（超限写 `stopped_batch` 并停止）。
- C1 双源 CPU 比较区间显式声明：两源均覆盖子进程**整个生命周期**（自报 vs 首末可读快照差）。
- 报告 writer 增加 batch 路径防护：绝对路径/`..`/分隔符/symlink 逃逸/已存在批次全部拒绝（独占创建）——含负例验证。

**R27：回归恢复与采样停止覆盖**
- **恢复被误并的 `test_budget_kill_preserves_evidence`**（根因：插入新测试时吞掉了其 def 行，函数体并入了上一个测试——现在恢复为独立方法；集成套件回到 5 项 = 原 3 项 + 新增 2 项）。
- 采样停止新增**真实后台线程**覆盖：`stop_background_sampling()` 后 reader 读取数与样本数冻结（等 0.12s 验证不再轮询）。

**交付文档数字同步（本批实际 JSON，不开单独返修轮）**：C1 自报 0.3408 s vs /proc 0.3500 s（差 9.2 ms < 20 ms 粒度，同区间声明）；C2 span 0.2635 s、w1 0.2400 + w2 0.2500 = 0.4900 s > span；O1–O3 wall 差 −28/+42/−28 ms（噪声级原始值）；collector 读 ~0.044 ms×~38 读≈1.7 ms/运行；批 wall 2.93 s。

## 原有 A1–A4 成果（首轮交付，见下文与 R2 批文件）

[历史正文保留：A1 26/26 配对+锚点校准 3.84 ms+估计窗口语义；A2 ToolEvent hook（open 先持久化/closed/error/安全投影）+真实 mini 离线验证；A3 HostProcessReader/Monitor；A4 机制核对与 ScopeSamples 界内过滤修复。]

## 实际验证命令与结果（返修轮）

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests              → 415 OK（410 + 5 新回归；项目内/项目外双跑）
PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python -m unittest tests.integration_run01 → 5 OK（19.4 s；原 wall-kill 已恢复）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_swebench   → 5 OK
PYTHONPATH=src python3 -B scripts/g1_01_mechanism.py --out /tmp/g1a_mech_v2 → 批 2.93 s（deadline 全生效）
PYTHONPATH=src python3 -B scripts/g1_01_report.py --batch G1-01-A-R2-...-r2 → 8 文件（路径防护负例验证通过）
git diff --check / py_compile / 敏感扫描                                → OK
```

## 输入/输出哈希

封存 8/8 + v2 4/4 前后不变；R2 manifest 登记全部输入与 8 个代码文件哈希；guard 负例（绝对/`..`/`a/b`/已存在/`.`）逐一拒绝验证。

## 缺失与噪声（返修后仍如实）

真 Tool duration 0/26（历史无 hook）；估计窗口高估执行；锚点残差 3.84 ms 为观测散布（非误差上界）；host kernel peak 未读；开销 3 对噪声级；工具分类启发式（P1-06 未接线）；机制脚本冒烟执行共 3 次（均在预算内，R2 批为归档运行）。

## 未执行事项 / B 待批准范围

未执行：容器/镜像、模型请求、trace/candidate、第二次任务、perf/eBPF、安装下载、Git 提交。**B 提案**不变（`container_validation_approval.md`：2 顺序 arm64 容器、network none、≤2 CPU/256 MiB、8 MiB 临时即删、总 wall ≤180 s、无模型无任务），等待用户批准。

## 第三轮返修（评审三项意见，全部离线；未启动容器或模型）

当前有效批：`reports/resource/G1-01-A/G1-01-A-R3-20260913T082046Z/`（supersedes R2，保留）。封存/v2/R2/首批全部零改动。

**R28：CPU 比较区间如实化**：worker 自报改为进程入口（module entry）即读 `process_time`——覆盖含解释器启动的整个生命周期；但 /proc 差仍为首末可读快照（spawn 返回后才可读），二者窗口**本质不同**。故 C1 语义改为 `comparison_semantics`：**"DIAGNOSTIC CROSS-CHECK of two DIFFERENT windows, NOT a same-interval verification"**——差值界定窗口偏斜+调度噪声，小于粒度仅构成单位/合理性一致性检查，不判同区间计量验证通过。tolerance 文本同步更正。

**R29：单 scope 停止冻结**：`sample_once()` 跳过 `boundary_end` 已记录的 scope（读取与追加均冻结，检查-追加竞态窗口双重防护）。新增回归：**后台线程保持运行**，stop("s") 后 s 的 reader 读取数/样本数/边界全冻结，另一活跃 scope "t" 持续采样；`sample_once()` 直调复现（不再 +1 读 +1 样本）。原全线程停止测试保留。

**R30：锚点数量不一致禁用校准**：新增 `_calibration_gate()`——ok 状态行数 ≠ assistant-with-actions 数时，`calibrate()` 直接 `available=false`（原因：中间缺行位置不可靠定位，顺序配对会静默错位缺行之后的每个锚点；小残差不证明正确）。派生 monotonic 窗口与 scope 关联全部 null。**中间缺行回归**（3 请求删中间 status 行）：校准禁用、全部记录窗口 (None,None)、窗口内采样计数 null；**对照回归**（不删行）：校准正常、26 窗口派生。封存 C run：流一致（26/26），门控启用、校准不变。

**本轮实际值（summary.md 与 mechanism_checks.json 同步）**：C1 自报 0.3462s vs /proc 0.3500s（差 3.8 ms，诊断对照）；C2 span 0.2637s、CPU 和 0.4700s；O1–O3 差 +32/+52/+22 ms（噪声级）；批 wall 2.92s。测试：默认 418 项（+3 回归）项目内外双跑、mini 集成 5 项、swebench 5 项全过；封存 8/8 哈希复核不变。

## 第四轮收尾（评审三项；全部离线，未执行容器或模型）

当前有效批：`reports/resource/G1-01-A/G1-01-A-R4-20260913T085846Z/`（8 文件；supersedes R3，保留）。封存/v2/首批/R2/R3 零改动（首批按下述核验恢复一个文件）。

**R31：stop() 停止竞态闭环**：`stop()` 获取该 scope 的 read gate（与采样循环每次读取同一把锁）——**等待在途读取结束后**再取最终边界并返回。确定性并发回归（评审复现的交错）：gated reader 挂起一次读取 → stop() 在另一线程调用 → 150 ms 后仍未返回（证明等待）→ 释放读取 → stop() 完成且边界来自最后一次读取代际；stop 后直调 `sample_once()` 不再读取。跨 scope 变体：A scope 读取在途时 stop(B) 不阻塞不冻结 A。默认套件 420 项（+2）。

**R32：C1 口径更正**（无重跑）：自报改为"**代码段 CPU 增量**"（module 入口→循环结束；排除入口前解释器启动与循环后退出过程）；删除全部"完整生命周期/same interval/差值界定偏斜上界"措辞——`comparison_semantics` 明示两窗口重叠但互不包含、差值不界定任何窗口偏斜、一致性检查不构成同区间验证。docstring 同步。

**R33：报告完整性与更正记录**：
- **R3 summary.md 哈希漂移根因**：manifest dict 从未携带 files map（评审发现的 415bd079 是旧结构残留值）——写入器现在 (a) 必含 files、(b) **写后回读逐一核对**（mismatch/missing/unlisted 任一即硬失败）。R4 批两次独立核验 8/8 全匹配。
- **首批文件丢失根因**：R3 组装时 `replace()` 把 `container_validation_approval.md` 移出首批目录（操作失误，当轮已发现并从 R2 复制到 R3 但未恢复首批）。本轮从 R2 副本恢复首批文件，**恢复前 SHA-256 核验等于首批 manifest 登记值 `5ceee00cefcae855...`**（原哈希精确恢复，未重写冒充）。根因与恢复记录写入 R4 manifest 的 correction_record。

验证：默认 420 项（项目内外双跑）；mini 集成 5 项；封存 8/8 + v2 4/4 哈希不变；`git diff --check`/敏感扫描干净。

A 第四轮收尾交付完毕，停止，交回原评审核验。B 提案继续待批（container_validation_approval.md，本批已复制）。

## 授权范围（用户 2026-09-13 消息）

A：封存数据只读分析 + 工具事件接线 + 宿主最小观测 + 限额内离线/真实 mini fake transport/本地确定性小程序验证 + 新目录派生报告与 B 提案。禁止：安装/下载/联网、真实密钥、容器/镜像操作、trace 命令/candidate 执行、第二次模型任务、perf/eBPF/提权、全局设置/references/旧源/封存数据改动、覆盖历史报告、Git 提交推送。

## A1：历史工具时间与采样窗口审计（封存只读）

- **26/26 身份配对**（`tool_call_id` + 位置配对 assistant↔tool 消息；0 缺失；3 个非零 returncode 如实记录）
- **字段语义表**（`timing_semantics.md`，逐字段核对安装版源码 locator）：assistant `extra.timestamp`=litellm_model.py:104（epoch，查询后/执行前 log_receipt）；tool `extra.timestamp`=actions_toolcall.py:100（epoch，执行后+格式化 log_receipt）；status `t_start/end_ns`=子进程 CLOCK_MONOTONIC 请求边界
- **锚点校准**：26 个 (assistant.timestamp, status.t_end_ns) 同进程锚点对，残差最大 **3.84 ms**（修正了初版按 n_calls 配对的 bug——format 错误请求使序数错位导致残差 10 s，改为按 ok 行顺序配对）
- **估计窗口 26/26**（epoch 域 → monotonic 校准；窗口语义=estimated/bound，高估执行含调度+格式化开销）；**真 duration 0/26**（原因：hook 当年不存在，如实 null）
- **scope 关联**：shared_scope/window only——26 窗口全部落在 agent scope 边界内（校准误差 3.84 ms 声明）；窗口内采样计数（293 个 0.5 s 采样中 13 个落入工具窗口——稀疏如实）
- **采样窗口审计**：agent scope 268/293 界内、25 界外（保留在封存文件，派生视图单列不混入峰值）；verifier 24/24 界内
- **安全投影**：派生 timeline 只含 heuristic_category/sha256/length，无原始命令/输出

## A2：工具事件接线（未来运行）

`ToolEventRecordingEnvironment`（mini 子进程内，attached 与 fake 执行器共用）：每次 `env.execute` 前**先持久化 open 行**（event_id+tool_call_id+command_view{sha256,length}+t_start_ns），执行后写 closed（returncode/异常存在/output_length/t_end_ns）或 error（异常类型，Submitted 等中断保留开口语义）。子进程 CLOCK_MONOTONIC 与父进程同域（Linux 系统级）。

**真实 mini 离线验证**（integration_run01 第 4 项，套件 19 s ≤ 60 s）：3 open / 2 closed / 1 error（Submitted 中断为 error 非 fake closed）；失败 returncode=1 如实记录；命令/输出原文不落事件文件；格式错误分支（第 5 项）零工具事件。

## A3：宿主 mini/collector 最小观测（未来运行）

`collectors/host_process.py`：`HostProcessReader`（/proc stat，pid+starttime 身份钉；utime+stime ticks 按实际 CLK_TCK；RSS 页×实际页大小；读取失败/PID 复用/退出→null+原因）+ `HostProcessMonitor`（轮询快照；最终读通常 process_exited=验证终值 null、最后可读值仅诊断；collector 每读耗时累计）。接入 mini 父进程轮询循环（host_process.jsonl + harness.host_summary）。**历史宿主缺口不回填**（scope_coverage.json 明示 missing_historical）。

## A4：机制核对（预算内实际执行）

**预算（执行前声明）**：每用例 wall≤10 s、busy≤2 s、worker≤2、内存≤64 MiB/worker、临时文件≤8 MiB（未使用）、批 wall≤120 s、报告≤20 MiB（实际 68 KB）。机制批执行 2 次（1 次脚本冒烟 + 1 次报告归档运行），每次 ~3 s。

| 用例 | 结果（原始值，mechanism_checks.json） |
| --- | --- |
| C1 双源 CPU 核对 | 子进程自报 0.3480 s vs /proc 0.3600 s，**差 12 ms < 20 ms 轮询粒度**（容差执行前声明） |
| C2 双 worker 重叠 | span 0.253 s；w1 CPU 0.220 + w2 0.230 = 和 0.450 s > span（重叠如实）；共享计数不复制求和（fixtures 断言） |
| O1–O3 开销对（预先固定 3 对） | wall 差 +3 / −29 / +0 ms（噪声级，原始数据不作百分比）；collector 读耗时 ~0.035 ms/读 × ~35 读 ≈ 1.2 ms/运行 |
| fixtures（test_g1_01 15 项） | 串行+异常/配对缺失/校准残差/命令安全投影/重叠数学/后台超返回/PID 复用/计数 reset/退出 null/单位独立期望/采样停止+出界检测 |

**审计发现并修复（未来运行）**：`ScopeSamples.summary()` 的 sampled_max 原含边界外样本——已改为仅界内并单列 `n_samples_out_of_boundary`（封存数据不动，派生视图正确）。

## 实际改动文件

新增：`analyzers/tool_timeline.py`、`collectors/host_process.py`、`scripts/g1_01_mechanism.py`、`scripts/g1_01_report.py`、`tests/test_g1_01.py`、批报告 8 文件、本文件。
修改：`runners/mini_agent_adapter.py`（ToolEvent hook + 宿主监控接线 + host_summary）、`collectors/resource_sampler.py`（summary 界内过滤）、`tests/integration_run01.py`（+2 项：hook 边界/格式错误分支）。
未修改：封存 run_dir、RUN-01-C 与 RUN-01-C-v2 报告、references、旧源、用户配置。

## 实际验证命令与结果

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests              → 410 OK（395 基线 + 15 新增；项目内）
项目外 cwd 绝对路径 discover                                         → 410 OK
PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python -m unittest tests.integration_run01 → 4 OK（19 s ≤ 60 s）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_swebench   → 5 OK
PYTHONPATH=src python3 -B scripts/g1_01_mechanism.py --out /tmp/g1a_mech_probe → 批 2.8 s（冒烟）
PYTHONPATH=src python3 -B scripts/g1_01_report.py --batch G1-01-A-20260913T074244Z → 8 文件 68 KB
git diff --check / py_compile / 敏感扫描（sk-/Bearer，排除 SYNTH canary）→ OK
```

## 输入/输出哈希核对

- 封存 8 文件（520,090 B）前后快照比对 **8/8 不变**；v2 报告 4 文件不变
- 批 manifest 登记全部输入哈希（sealed:* + v2report:*）与 8 个代码文件哈希
- 输出 8 文件均入 manifest（含 g1_evidence.md 与 B 提案）

## 缺失与噪声（如实）

- 真 Tool duration 0/26（历史无 hook）；估计窗口高估执行（调度+格式化）
- 26 窗口共仅覆盖 13 个容器采样（0.5 s 间隔 vs ~0.3 s 均值窗口——稀疏，非覆盖证明）
- host scope 历史缺失不回填；宿主 kernel peak（VmHWM）本批未读
- 开销 3 对为噪声级原始数据，不构成稳定百分比
- 工具分类为启发式（P1-06 未接线，报告标注 heuristic_category）
- 机制批执行 2 次（冒烟+归档），均在声明预算内

## 未执行事项 / B 待批准范围

未执行：容器/镜像操作、模型请求、trace/candidate 命令、第二次任务、perf/eBPF、安装下载、Git 提交。
**B 提案**（`container_validation_approval.md`）：2 个顺序 arm64 容器（network none，各 ≤2 CPU/256 MiB，合成写入 ≤8 MiB 临时即删，总 wall ≤180 s）——验证真实 hook 窗口+容器计数器+宿主采集+停止后边界；无模型无任务。等待用户批准。

A 交付完毕，停止，交回原评审核验。
