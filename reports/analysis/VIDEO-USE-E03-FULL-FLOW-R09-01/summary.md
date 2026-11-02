# VIDEO-USE-E03-FULL-FLOW-R09-01 — 唯一正式完整流程 attempt（成功正常收尾）

更新：2026-11-02（UTC）。R09 唯一正式 video-use E03 完整流程 attempt 经托管启动器执行并
正常收尾。完整原生 rollout、采样、输入/输出、命令/参数/起止/返回、manifest 均已持久化并
读回核验；已建立独立 raw 目录副本。语义评分 reward=0.0 且官方评分完整，按既定规则为合法
结果，不补跑、不改片、不重评。R09 标**完整正常流程完成**。

## 一、执行总览

| 项 | 值 |
| --- | --- |
| task_id | `VIDEO-USE-E03-FULL-FLOW-R09-01` |
| run_id | `20261102T112320Z-video-use-e03-full-flow-r09-01`（UTC） |
| task_kind | interview（content-cut） |
| 镜像 | `video-use-task:arm64-codex-bailian-v6` = `sha256:1a48c7b00da789ec99722ebb2be6e1df72aec9d37cc2a64e83c82e89ecf700c5`（arm64/linux，codex 0.163.0） |
| 输入 | `source.mp4` 11,604,798 B / SHA `c66f380a…`（实算一致） |
| 指令 | `instruction.md` SHA `bc36a568…`（实算一致） |
| 新配置 | `env/video/video-use/task-configs/E03-full-flow-r09-01-formal.json` |
| 冻结身份 | `env/video/video-use/VIDEO-USE-E03-FULL-FLOW-R09-01/frozen-identity.json`，文件 SHA `b1dd3f433339c8c441193644492754c9640cddcbbdfe195b5dd9b5162ed1bb31`（23 绑定文件） |
| APPROVAL | `…/APPROVAL.json`，绑定身份文件完整 SHA `b1dd3f43…`，`no_retry:true` |
| 托管器 | `scripts/video_use_managed_launch.py` SHA `c01ac98e23c127260ed1e21a5ea72cccb391460635e3af780f987f70c86d8442` |
| 持久性证明 | `…/persistence-probe/host-confirmed-probe/verification.json`（同执行域实际 validate 通过；launcher SHA/execution_domain 匹配） |
| raw | `data/raw/generated/VIDEO-USE-E03-FULL-FLOW-R09-01/20261102T112320Z-video-use-e03-full-flow-r09-01/` |
| control | `reports/analysis/VIDEO-USE-E03-FULL-FLOW-R09-01/control/`（独立，不与 raw 重叠） |
| 报告根 | `reports/resource/VIDEO-USE-E03-FULL-FLOW-R09-01/` |

## 二、发送前核验（本会话实际执行）

1. 生产消费者 SHA 与最新验收证据相符（FINAL-STATE-AND-TEST-ISOLATION-CLOSEOUT-01 manifest
   记录与当前磁盘实算一致）：edit_pilot_01 `4acffa7d…`、edit_pilot_03 `d7156ec8…`、
   edit_pilot_04 `8b2b5566…`、task_entry `088a1d04…`、managed_launch `c01ac98e…`。
2. 真实生成 Agent 提示（`starter_instruction` 实测输出）：E03 内容删除目标（移除 phone-case
   stand-up claim 段）存在；无 E01 hesitation-only / E02 filler-only / repurpose 目标；示例
   时间戳已中性化为 `<integer>`；golden 值 `29143/34328` 未串入。
3. 未注入 golden/historical cuts/其他仓库选段/参考答案（配置 golden-leak 检查、提示全文
   检查均无泄漏）。
4. video-use 职责保持：Agent 自主生成 EDL/编辑计划、原生 render、标准提交物；宿主只做
   归档/技术检查/评分；不套用 OpenStoryline timeline 派生 cuts 模式。
5. `stop_sampler` 正常路径被消费；`sampler_thread_ended=True` 来自 `not is_alive()`；
   sink 状态在 close 完成后读取（`closed:true, buffered:0, error:null`）。
6. `finalize_run` 正常路径读回最终状态（manifest 绑定最终 run-record 字节，实算一致）。
7. 技术必需项全部显式成功；共享单调绝对截止生效（verifier_deadline 单点，各子步剩余递减）。
8. 原生 rollout 完整（见第七节），非空/可解析/可归属/已配对/无右删失 → trace complete。
9. 独立 verifier 环境存在（`/home/lcq/.venvs/video-use-pilot03-verifier`，venv python 实际
   存在）；golden 仅在宿主评分范围（`verifier_private/`，容器移除后创建）。
10. 必要定向测试本轮 fresh 执行（隔离写入，未触碰历史 reports/resource）：
    - `r09_closeout + managed_launch + r09_four_gap_closeout + task_entry_gates + e03_readiness`
      125 PASS；
    - 上述 + `production_dispatch + task_entry_final` 146 PASS；
    - pilot01 单独 11 PASS；pilot03/04/02/boundary 28 PASS（组合同进程运行中 pilot01 4 项
      失败为既有跨文件顺序依赖，单独运行全过，与本轮无关）。
    测试后 `find reports/resource -newermt …` 无新增非本任务文件。

## 三、托管启动与存活证据

- 只读 gate（`--gate-only`）：`{"gate":"PASS"}`，binding 绑定完整身份 SHA。
- 正式 launch：`READY`（supervisor 独立 session/PGID，PID 3020596，sid==pgid==pid）。
- `status` 轮询：phase 依次 `runner_running → runner_exited`，runner PID 3020602，
  `runner_rc=0`；supervisor 与 runner 均在结束后不存活（自然收尾）。
- 生产 runner 自行收尾：`removal_verification="removed"`，容器已删除（`docker ps -a` 无残留）。

## 四、ASR、Agent、原生 render 与终止

- **ASR**：至多一次真实提交。phase `official_elevenlabs_transcribe` rc=0，
  `request_count=1`（6.4s 保存 source.json，611 words）。缓存 `transcripts/source.json`
  为本 run 实际产生；Agent 提示明确"读缓存、不重转写"。
- **Agent**：rc=0，timeout=False，duration 177.83s（<1800s）。自主链：读 SKILL.md →
  读转写 → ffprobe 源 → 定位 "stand up / easier to hold" 语句 → timeline_view 检查候选区 →
  写 EDL（删除 29.17s–34.43s）→ 原生 render → ffprobe 输出 → 输出截图验证 → 写 cuts.json。
  28 次工具调用/28 次返回，配对无缺失/无重复/无孤立（`rollout_summary`）。
- **终止原因**：Agent 正常完成（无超时/异常），`termination_reason=None`。

## 五、提交物与职责

- `workspace/output/output.mp4`：13,793,213 B，H.264/yuv420p/854×480/24000-1001/AAC，
  video 84.793s / container 84.857s；完整解码 pass；源规格匹配 `matches_source_dimensions_and_rate=true`。
- `workspace/output/cuts.json`：`{"cuts":[{"start_ms":29170,"end_ms":34430,"reason":"off-topic segment"}]}`
  （Agent 自主从转写与相邻画面证据选择）。
- 编辑计划：`workspace/project/edit/edl.json`（Agent 自主生成，ranges 0–29.17 / 34.43–90.0）；
  render 来源为容器内 `/opt/video-use/helpers/render.py` 原生调用，输出 `base.mp4`→`output.mp4`
  （同一规格、同为合法解码；非宿主代做、非注入 golden）。
- 职责：Agent 自主剪辑与 render；宿主归档、技术检查、评分。

## 六、技术检查与官方评分

- **技术检查**（共享 verifier_deadline 单点）：`files_present=true`、输出 ffprobe pass
  （h264/854×480/yuv420p/24000-1001）、源 ffprobe pass、完整解码 pass、cuts.json parseable
  （cut_count=1）、`matches_source_dimensions_and_rate=true`。全部通过。
- **官方评分**（至多一次）：`evaluation_complete=true`、wrapper rc=0、judge rc=0、
  reward=**0.0**。原因：cut 区间命中 golden（start_offset 0.027s / end_offset 0.102s，均在容差
  内，per_cut passed=true），但 **ssim 0.7244 < 0.8** → `honesty_pass=false`（"content lie
  suspected"）；audio_xcorr 0.998、duration diff 0.057s 均通过。judge_sha256
  `cb5486ba…` 与 verifier 登记一致，judge_identity_match=true。
- reward=0 且评分完整 → 合法结果，不重评、不改片。语义局限：Agent 实际删除段与 golden 中心
  区间高度一致，但 SSIM 显示输出内容与源剪切期望不完全匹配（可能是区间边缘差异的编码/
  重采样影响），官方判分为 0。

## 七、原生 rollout、配对与 usage

- 原生 JSONL：`workspace/export/rollouts/2026/11/02/rollout-2026-11-02T11-26-14-01a19c02-….jsonl`
  （2,076,088 B，SHA `7df7a4c5…`），派生索引与摘要并存但不替代原生文件。
- `trace_integrity`：status=complete，1 file，0 empty/corrupt，session `01a19c02-…`
  attribution=confirmed，28 tool_call / 28 tool_return，missing/orphan/duplicate 全空，
  right_censored=false，task_complete=1。
- usage：21 条 token 记录 + 21 条 token_count 事件。按原生 `usage` 字段逐次（非累计）合计：
  input 552,780 / output 6,683 / total 559,463 / reasoning 3,640 / cached_input 395,648
  （turn_token_usage 末次累计一致，累计快照未重复相加）。HTTP 次数/费用：`http_attempts=unknown`
  （原生无可靠字段），未声明不存在硬上限。

## 八、资源与时间

- 采样：302 行 / 301 有效间隔，中位 0.6014s（目标 0.5s）、最大 0.7518s；first sample
  = agent 开始时刻（2544378090742344），采样窗 184.68s 覆盖 agent 相位。
- CPU 60.82 core-s / 0.329 avg cores（容器 cgroup 及子进程）；memory.current 峰
  487.31 MB、kernel peak 487.82 MB；io read 0 / write 1,667,072 B。net 为共享 bridge
  netns 逐接口（非 API 专属）。
- 时间（UTC）：preflight 0.1s → ASR 6.67s（11:26:07→11:26:14）→ Agent 177.83s
  （11:26:14→11:29:12）→ export 0.1s → 技术检查+评分（11:29:13→11:30:14，含提交核验
  0.57s）。total 起止 11:26:06→11:30:14 ≈ 248s，远低于 2700s 共享截止。容器 CPU 不扩称
  宿主整链，远端推理不计入本地资源。

## 九、最终状态、manifest 与清理

- `final_state`（run-record / CLI / report-generation-status 三方一致）：overall
  `{"status":"ok","full_flow":true,"blockers":[],"host_exit_code":0}`；8 维度
  program/submission/technical/official/trace/measurement/cleanup/evidence 全 ok。
- manifest `files["run-record.json"]` SHA `fcb39ed1…` == 磁盘实算（绑定最终字节）；
  manifest 从其他 cwd 读回可解析（root 明确、self-hash 省略）。
- raw manifest 23 项 + 24 实际文件；独立副本 `raw-persistent-copy/` 24/24 文件逐字节
  SHA/bytes 比对一致（同一物理存储，不称异地备份）。
- 清理：生产 runner 自行完成（容器 removal=removed，docker 无残留）；未清理镜像/缓存/正式
  证据；仅生成正式产物与副本。

## 十、判定

| 维度 | 判定 |
| --- | --- |
| 程序 | PASS（Agent rc=0、无超时/异常、托管 runner rc=0、容器与宿主正常收尾） |
| 技术 | PASS（技术检查全通过） |
| 官方语义 | complete，reward=0.0（合法；cut 命中 golden 但 ssim 0.7244<0.8，语义局限如实记录） |
| trace | PASS（原生 rollout 非空/可解析/可归属/已配对/无右删失） |
| 测量 | PASS（采样/边界/thread/sink 完整，质量 complete） |
| 清理 | PASS（生产 runner 自行收尾，回验 removed） |

**R09 达到完整正常流程。** 历史 E03 raw 缺失事实、历史失败与报告、PILOT-01 两项
UNKNOWN 保护状态全部保留，未覆盖、未用 git HEAD 恢复；重跑不增加组合数/不同输入计数。
