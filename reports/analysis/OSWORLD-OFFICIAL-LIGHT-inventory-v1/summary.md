# OSWorld 官方数据仓库轻量轨迹子集：离线盘点

日期：2026-09-29。仅读取用户已下载目录；未联网、未补下载、未执行轨迹/benchmark。

## 结论

本地集合可做有限的行为序列盘点，但不能据此证明上游匹配文件全部下载、不能验证本地 SHA 是上游 SHA，也不能支持 CPU/内存/I/O/热点或模型身份结论。用户命令声明的 revision 为 `01cb84fcd5fb8ee415e7e065d7aaf3ec8f95fe1f`；本地 2,058 个 Hugging Face `.metadata` 文件首行均记录该 revision。没有本地完整上游文件清单，因此来源绑定是“缓存 revision 一致”，不是“下载集合完整性已证明”。

## 本地规模

- 模型目录：7 个。
- 模型×任务目录：755 个；去重后的 dataset-local task key：108 个（`001`–`108`）。这些数字目录仍只是本地 key，未由本地任务定义证明为官方 task ID。
- 数据文件：2,058 个，787,052,044 bytes；包括 755 `traj.jsonl`、754 `result.txt`、185 `result.json`、364 `checkpoint_results.json`。
- cache 文件：4,119 个，60,544,675 bytes；总文件 6,177 个、847,596,719 bytes。cache 包含 lock、metadata、`CACHEDIR.TAG` 等，不计入轨迹样本。
- 结果文件缺失：相对于现有 755 个模型×任务记录，`result.json` 缺 570，`result.txt` 缺 1，`checkpoint_results.json` 缺 391。缺失结果不自动解释为下载失败或任务失败。

## 模型覆盖

| 模型目录 | 任务目录 | traj | traj bytes | result.json | result.txt | checkpoint | step 重复值 | 倒序相邻对 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `MiniMax-M3` | 108 | 108 | 108,536,589 | 26 | 108 | 94 | 0 | 0 |
| `claude-opus-4-7` | 108 | 108 | 148,719,474 | 26 | 107 | 95 | 0 | 0 |
| `claude-sonnet-4-6-max` | 108 | 108 | 132,514,999 | 26 | 108 | 77 | 0 | 0 |
| `claude-sonnet-4-6-medium` | 108 | 108 | 174,116,689 | 27 | 108 | 83 | 0 | 0 |
| `gpt-5.5` | 108 | 108 | 46,652,599 | 27 | 108 | 15 | 6167 | 1 |
| `gpt-5.6` | 107 | 107 | 146,474,219 | 27 | 107 | 0 | 23576 | 0 |
| `qwen3.7` | 108 | 108 | 28,709,725 | 26 | 108 | 0 | 3146 | 0 |

`gpt-5.6` 有 107 个任务目录；其余模型目录各有 108 个，`048` 因此只有 6 个模型记录。模型目录名只是发布方标签，未验证真实 API/model identity。

## 结构核验

755 个 `traj.jsonl` 全部可解析：201,665 行、0 个无效 JSON 行、0 个空行。全局观测：

- `step_num`：201,664 个整数、1 个缺失；按文件统计有 32,889 个重复值、1 个倒序相邻对。起始值未强制假设。
- `action_timestamp`：201,664 个字符串可解析为无时区时间、1 个非字符串；没有证据确定这是动作开始、结束或记录时间，也不能计算工具耗时。
- `action` 类型：dict 144,221、string 57,335、null 108、missing 1。
- `response` 类型：dict 51,278、string 150,070、list 3、null 108、missing 206。任意 response 不自动等于结构化工具返回。
- `done`：true 685、false 200,774、missing 206；与 reward、result、checkpoint score 分开。
- `reward`：integer 201,351、float 108、missing 206。
- `info`：dict 201,459、missing 206；常见键为 `done`、`initial_observation`、`fail`，未据此统一语义。
- `screenshot_file`：有 168,919 个字符串引用，但按任务目录相对路径查找，本地对应截图文件为 0；路径不等于截图已下载。

结果文件中，185 个 `result.json` 均为可解析对象且有 float `score`，但结构分为 `safety`、`partial_scores` 或 `evaluation_error` 等不同形态；754 个 `result.txt` 均为一行可解析数字；364 个 checkpoint 文件均为可解析列表，但字段集合和条目数不同。它们不是同一个“成功”字段，不能合并成单一结果。

## 来源与完整性分层

| 事实 | 结论 |
|---|---|
| 用户提供了固定 revision 的筛选下载命令 | 已登记为输入声明，不是本地命令执行日志 |
| cache `.metadata` 首行 revision | 2,058/2,058 与指定 revision 一致 |
| 本地文件 SHA-256 | 已对每个数据/cache 文件计算并登记；只证明当前本地 bytes 稳定 |
| 上游完整文件清单/逐文件期望哈希 | 本地没有，不能证明所有匹配文件均已下载 |

## Evidence → Allowed Analysis

| 证据 | 允许分析 | 当前排除 |
|---|---|---|
| `traj.jsonl` 字段和逐行结构 | 动作类型组成、动作序列、步骤记录数、done/reward/info 的分列描述 | 不把 action/step 当工具执行或模型请求；不解释动作实际效果 |
| dataset-local task key 与模型目录 | 在明确本地 key 集合内做有限覆盖/缺失盘点 | 不称官方 task ID，不验证实际模型身份或任务类别 |
| `action_timestamp` 字符串 | 记录字段存在性、解析性和文件内顺序 | 时间占比、单动作耗时、思考时间、等待时间 |
| result/checkpoint 文件 | 按文件类型报告字段和结果结构差异 | 不把 done、reward、score、result 合并为成功率 |
| 无资源字段/无截图正文 | — | CPU、内存、I/O、热点、单工具独占耗时 |

## 最小下一步

只做一个受控离线行为分析：固定 `MiniMax-M3` 模型目录，取其 108 个 dataset-local task key 中有完整 `traj.jsonl` 的记录；先按文件结构验证动作/step 序列，再按模型目录分别报告，不跨模型合并任务语义。选样按 task key 字典序或预先登记的固定全量集合，不按成功率、reward 或 score 筛选。该分析仍只描述动作序列、步骤和结果字段，不能扩展为资源特征化或模型排行榜。

详细逐文件 bytes/SHA、cache metadata、模型统计和结构结果见 [inventory.json](inventory.json)。原始下载目录及 `.cache` 未修改。
