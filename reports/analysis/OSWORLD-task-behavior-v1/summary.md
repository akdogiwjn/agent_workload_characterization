# OSWorld 任务语义与行为联合分析 v1

固定本地输入、只做静态任务提取和保存轨迹分析；不执行任务或 action。

## 覆盖
- 755 条 model×task 轨迹，模型数 7；任务语义文件 108 个。各模型覆盖：MiniMax-M3=108, claude-opus-4-7=108, claude-sonnet-4-6-max=108, claude-sonnet-4-6-medium=108, gpt-5.5=108, gpt-5.6=107, qwen3.7=108。
- 行为状态：partial=195, unanalysable=539, valid=21；保守静态动作类别计数：{'click': 15572, 'pointer': 2390, 'scroll': 3033, 'text_or_key': 3229484, 'wait': 3750}。
- 任务标签允许重叠，源 `related_apps` 仅是任务声明，不等价于实际应用调用。历史运行与当前 task revision 的绑定保持 unknown。

## 任务 workload 语义
任务静态提取了 instruction、related_apps、snapshot、setup/evaluator 存在性及少量基于文本的多标签；任务编号与轨迹目录可关联，但不证明历史执行使用当前 task 版本。

## 行为观察
- step_num 缺失/重复/相邻倒序汇总：{'missing': 1, 'duplicate_value_count': 32889, 'descending_adjacent_pairs': 1}；每个轨迹保留原始记录与保守解析边界。
- 不同模型与任务的行为只能按保存的静态类别、Unknown 边界、段和转换描述；不推断实际执行次数、耗时或资源。
- MiniMax usage：35272 calls，missing_usage_count=10，request_time=response_time 的记录数=4761；numeric_totals 与逐调用重算分列保存。

- MiniMax usage 请求级字段分布与 task 级 numeric_totals 分布分别记录在 summary.json；input_tokens、output_tokens、cache_read/cache_creation 分列，`input_tokens_including_cache` 仅作逐字段相加的派生核对，不当作额外可加总字段。

## 结果与限制
done、reward、result.txt、result.json、checkpoint 分列；不生成新的成功标签。GPT-5.6 manifest 的 result hash 单独核对，不将混合 source_run 当统一单批。
不支持动作耗时/速率、CPU、内存、I/O、热点、模型优劣或因果解释。候选行为模式仅供后续资源测量选样，不构成执行授权。

[summary.json](summary.json) · [task_semantics.jsonl](task_semantics.jsonl) · [per_trajectory.jsonl](per_trajectory.jsonl) · [manifest.json](manifest.json)
