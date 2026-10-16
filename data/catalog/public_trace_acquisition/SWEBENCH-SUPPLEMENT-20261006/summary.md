# SWEBENCH-SUPPLEMENT-20261006 acquisition

本轮为低成本缺口补齐 + 覆盖扩展轮，不追求全量下载，不阻塞离线分析。SWE-bench 索引固定 `40f164d5b8f1d249bf95a6df8b74b577fd8e519d`。预算：2h 墙钟（01:56-03:56Z，下载器 03:35 内部截止）、响应正文上限 5 GiB、并发 3。

## P1 缺口补齐（全部完成）

| 组 | 之前 | 现在 |
|---|---|---|
| 20241108_devlo | 499/500 | **500/500 完整** |
| 20241213_devlo | 3/500 | **500/500 完整** |
| 20240620_sweagent_claude3.5sonnet | 174/500（含旧 326 失败） | **500/500 完整（326 个旧失败对象本轮单次重试全部成功，错误为此前的暂时性连接中断）** |

## P2 新覆盖（6 个选定 submission，5 完整 + 1 partial）

选择依据：先独立 task 证据（task ID 由 S3 listing key 与本地 500-task 集合比对恢复）、再新 harness 家族、再体积小、再字典序；未按成功率/榜单选择。Test split 的 sonar-foundation-agent 为唯一 +task 组（预计 +1794）；其余 Lite 小组在 sonar 之后为 harness 多样性增益（Lite 300-task 集 ⊂ full split 任务集）。

| 组 | split | 对象 | 状态 | 抽样确认 |
|---|---|---|---|---|
| 20251219_sonar-foundation-agent_claude-opus-4-5 | test | 2,147/2,294 | partial（147 缺，deadline） | json 消息列表 77-107 条 ✓ |
| 20240806_SuperCoder2.0 | lite | 300/300 | 完整 | {instance_id, trajectory} ✓ |
| 20251009_MAYA_claude-sonnet-4-5-20250929 | lite | 300/300 | 完整 | {agents, llm_final_response} ✓ |
| 20241127_globant_codefixer_agent | lite | 300/300 | 完整 | Fault Localization 流程记录 ✓ |
| 20240617_moatless_gpt4o | lite | 300/300 | 完整 | {info, initial_message, transitions} 搜索树轨迹 ✓ |
| 20250619_KGCompass_claude-3.5-sonnet-20241022 | lite | 300/300 | 完整 | KG 分析+定位流程记录 ✓ |

## P3 OSWorld 配套（独立目录，不混入旧轨迹）

- 已取得（xlang-ai/OSWorld 钉 commit `b138d348256078fa634fc3b73567a7337c793e6b`，Apache-2.0，6 文件 115,926 bytes）：`lib_run_single.py` 完整确认 traj.jsonl 字段语义——`step_num` 为外层步循环索引+1（同一步的多 action 共享）；`action_timestamp` 为动作执行前捕获的本地 wall-clock（`datetime.now()`，`%Y%m%d@%H%M%S%f`，另有不含微秒的变体函数），非相对耗时/单调时钟；`reward/done/info` 来自 `env.step(action)` 返回；`result.txt` 为 `env.evaluate()` 结果。`test_all.json`、根 README、`desktop_env/actions.py`、examples README 一并保存。
- **数字 task key → 任务定义映射：unknown**。轨迹用三位数字 dataset-local key（001-108），官方仓库任务定义与 `test_all.json` 为 UUID 体系，非同一标识体系；固定 revision 树中唯一候选映射文件 `website_demo/gpt-5.6/manifest.json` 所在 huggingface.co 本机网络不可达（blocked；hf-mirror 可达但未登记，未使用）。按规则停止，不猜任务标题关联。版本说明：代码 commit 为独立固定版本，不冒称与轨迹 revision `01cb84f` 自动对应。

## 数字与核验

- 本轮新增 SWE-bench 文件 4,471 个（S3 key 全量去重，均不在旧 manifest 中）、保存 837,272,535 bytes；全部与 S3 listing 期望字节一致（0 mismatch），SHA-256 从磁盘重算入 manifest；OSWorld 配套 6 文件 115,926 bytes。
- 响应正文计数 838,539,479 bytes（下载器逐块计数，含重试传输；HTTP 头/TLS/GitHub API 未计，unknown）。墙钟：下载器 5,190s；整轮 01:56-03:56Z 之内完成收尾。
- 对象数 4,471 ≠ 轨迹数（各组格式不同：.traj/.log/.json/无后缀/目录式，抽样确认均为真实 agent 记录）。
- **独立 task：500 → 2,206（本轮 +1,706）**；sonar 若补齐剩余 147 对象预计再 +~88。
- 累计视图（引用旧 manifest，不改写）：Verified 35 组完整（32→35）/ 16,229 对象（另 91 组未尝试、1 组 S3 404）；Lite 5 组完整 / 1,500 对象（另 60 组未尝试 + SemAgent 外部已钉 commit 待取）；Test 1 组 partial（sonar 2,147/2,294）/ 14 组未尝试。
- 分类纠正：旧轮“未触碰 93 组”实为 92 未尝试 + 1 不可访问（Skywork+TTS 404）；旧 326 失败即 claude3.5sonnet 组缺口（与部分组重叠，本轮补齐后不再单列）；本登记按 完整/部分/未尝试/已失败/不可访问/无可确认轨迹 六类分列（见 pending.json）。
- 下载与离线分析是两条工作线；本登记仅为下载线增量，G2/G3-R、CPU-02、Replay 状态不变，未提交 Git。
