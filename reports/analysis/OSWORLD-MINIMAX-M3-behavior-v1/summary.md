# OSWorld MiniMax-M3 首轮有限行为特征

本报告只分析固定 revision 下本地 MiniMax-M3 的 108 个 dataset-local task key；不执行轨迹、不联网、不做资源分析。

## 记录与动作关系

每个 JSONL 行是一个原始轨迹记录，不自动等于一次动作。`action` 实际为 Python-like 字符串；分析器只用 AST 静态提取无控制流的 `pyautogui.*` 调用。一个记录可含多个调用，调用按 AST 行号保留；无调用、语法错误、控制流或无效行成为 Unknown 边界。步骤号只报告，不去重。

记录总数 108；状态：valid=21, partial=87；静态调用总数 3241101。有效记录长度统计（静态调用数）为 {'n': 21, 'median': 50248.0, 'iqr': 37675.0, 'q1': 19797.0, 'q3': 57472.0}，全部记录为 {'n': 108, 'median': 26308.5, 'iqr': 37066.75, 'q1': 9682.0, 'q3': 46748.75}。

## 动作分类规则

- click：click/doubleClick/tripleClick/rightClick。
- pointer：moveTo/dragTo/mouseDown/mouseUp。
- text_or_key：press/keyDown/keyUp；不把 response 文字当输入动作。
- scroll：scroll/hscroll。
- wait：sleep。
- other：已解析但未登记的调用；unknown：无法静态确定。

## 汇总

### Pooled 调用计数

```json
{"click": 9236, "pointer": 636, "scroll": 1867, "text_or_key": 3225612, "wait": 3750}
```

### 按记录组成

按每条记录的已识别调用数归一化后取算术平均，不把长记录隐藏在 pooled 数中：

```json
{"click": 0.026954119956991342, "other": 0.0, "pointer": 0.005111904616926312, "scroll": 0.007102428034581616, "text_or_key": 0.9585396473233548, "wait": 0.0022919000681455685}
```

相邻转换只在连续的静态已知调用之间计数；Unknown 边界不跨越。

```json
{"click->click": 5522, "pointer->pointer": 415, "scroll->scroll": 1032, "text_or_key->text_or_key": 3221060, "wait->wait": 1850}
```

## 结果与缺口

每个 task 的 done、reward、result.json、result.txt、checkpoint_results.json 均在 summary.json 分列登记。它们不合并成成功标签。三类结果文件有缺失且 schema 不同；截图路径不代表本地截图存在。

没有报告动作耗时、速率、思考时间、等待占比、CPU、内存、I/O、热点或模型排名。`action_timestamp` 语义未确认。

代表性片段采用静态调用数最短、最接近中位数、最长，平局按 task key；只保留来源行号、step_num、类别和调用名，不复制原始参数。
