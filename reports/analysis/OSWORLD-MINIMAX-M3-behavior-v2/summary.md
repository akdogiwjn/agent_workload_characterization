# OSWorld MiniMax-M3 首轮有限行为特征 v2

固定 revision `01cb84fcd5fb8ee415e7e065d7aaf3ec8f95fe1f` 下分析 108 个 dataset-local task key；原始 JSONL 记录分母为 35282。不联网、不执行轨迹。

## 统计口径

源码调用节点出现次数、支持规则下的静态动作序列、实际 GUI 执行次数分开：第一项包含未支持语法中的 AST Call，第二项只接受顶层直接已知 pyautogui 调用，第三项无法由静态证据证明。Unknown action 记录打断邻接。

状态：valid=21, partial=87；支持规则调用总数 3241101；源码 Call 节点总数 3241101。有效任务长度统计：{'n': 21, 'median': 50248.0, 'iqr': 37675.0, 'q1': 19797.0, 'q3': 57472.0}。

## 分类与转换

```json
{"click": 9236, "pointer": 636, "scroll": 1867, "text_or_key": 3225612, "wait": 3750}
```

转换包括同类和异类，仅发生在可解释相邻动作之间：

```json
{"click->click": 5522, "click->pointer": 145, "click->scroll": 458, "click->text_or_key": 2823, "click->wait": 265, "pointer->click": 118, "pointer->pointer": 415, "pointer->scroll": 17, "pointer->text_or_key": 75, "pointer->wait": 11, "scroll->click": 522, "scroll->pointer": 16, "scroll->scroll": 1032, "scroll->text_or_key": 268, "scroll->wait": 22, "text_or_key->click": 2613, "text_or_key->pointer": 40, "text_or_key->scroll": 314, "text_or_key->text_or_key": 3221060, "text_or_key->wait": 1503, "wait->click": 441, "wait->pointer": 20, "wait->scroll": 46, "wait->text_or_key": 1379, "wait->wait": 1850}
```

连续段分别登记段个数、段内动作数和长度分布；连续相同类别不解释为相同操作重复。

## 高调用数记录

源码 Call 节点集中度和前三条记录见 summary.json 的 `source_call_concentration`。这些计数可说明源码规模，不能说明实际按键次数、重试、卡顿或低效原因。

## 结果字段

result.json 的 score、result.txt 的数值行、checkpoint 的有限评分字段、每条 reward 和 done 分列保留；数值不转换成成功标签，缺失、零值和失败不互换。

## 能力边界

可支持有限的静态动作组成、可解释序列和记录结构描述；不支持实际执行次数、动作时间、CPU/内存/I/O、热点、思考时间、因果或类别代表性。

代表性序列只从 valid 任务中按支持调用数最短、接近中位数、最长确定选择，并只输出来源行、step、类别和调用名。
