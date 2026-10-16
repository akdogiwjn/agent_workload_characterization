# OSWorld 任务语义与行为联合分析 v3

固定 trajectory revision 与本地 task/cache 登记，离线覆盖 755 条 model×task 轨迹、7 个模型、108 个任务定义；未执行 task/action。

## 有限观察
- 模型覆盖：{'MiniMax-M3': 108, 'claude-opus-4-7': 108, 'claude-sonnet-4-6-max': 108, 'claude-sonnet-4-6-medium': 108, 'gpt-5.5': 108, 'gpt-5.6': 107, 'qwen3.7': 108}；分析状态：{'partial': 734, 'valid': 21}。GPT-5.6 缺 048，历史版本绑定 unknown。
- 静态源码类别总数：{'click': 49276, 'pointer': 5252, 'scroll': 10804, 'text_or_key': 3272413, 'wait': 14427}；原生结构化动作总数：{'click': 33704, 'pointer': 1862, 'screenshot': 2244, 'scroll': 7771, 'text_or_key': 38608, 'unknown': 51093, 'wait': 8433}。两层不相加，避免同一记录重复计数。
- Claude/GPT 的 dict action 现在保留原生 action/input 与 command 源码；screenshot 与 command 中的占位 sleep 分列。字符串模型的原生动作表示为 not_applicable，不作为零值分布；unknown 只作边界。
- 任务 080 按 id/类名选择 Task080；标签采用边界/短语规则，VP9、hard-coded 等词不会仅因包含 code 而标成 development_terminal。
- MiniMax API usage：35272 calls；来源 missing_usage_count=10，calls 中 usage 缺失=0，字段缺失={}，有效时间相等=4761；输入+缓存派生值使用三项输入字段，汇总核验状态=PARTIAL。不与轨迹按位置配对。

## 证据边界
原生动作记录、command 的保守 AST 调用和实际执行次数是不同指标；静态分析不证明 GUI 执行。related_apps 是任务声明，不是实际应用调用。没有动作耗时、CPU、内存、I/O、热点或模型优劣证据。GPT-5.6 的 107 个 result hash 单独核验，source_run 混合。

## 后续用途
可用于按任务语义、模型格式覆盖和保存动作结构选择有限的后续本地测量线索，不构成执行授权或资源结论。

[summary.json](summary.json) · [task_semantics.jsonl](task_semantics.jsonl) · [per_trajectory.jsonl](per_trajectory.jsonl) · [corrections.md](corrections.md) · [manifest.json](manifest.json)
