# OSWorld v4：补充解析后的行为发现

完整读取同一批755条model×task记录；本报告只描述保存命令的静态调用与保存顺序。每个模型独立统计，不做能力、效率或资源排名。

## 修复带来的增量

| 模型标签 | v3 / v4识别源码调用 | v4整段已知command | v4部分已知command | v4未知command | 仅元数据command |
|---|---:|---:|---:|---:|---:|
| MiniMax-M3 | 3,241,101 / 3,241,101 | 35,169 | 0 | 113 | 0 |
| claude-opus-4-7 | 39,053 / 39,057 | 26,857 | 0 | 7,421 | 0 |
| claude-sonnet-4-6-max | 27,184 / 27,186 | 20,323 | 0 | 6,926 | 0 |
| claude-sonnet-4-6-medium | 31,706 / 31,708 | 23,302 | 0 | 7,890 | 0 |
| gpt-5.5 | 0 / 114,995 | 16,053 | 126 | 103 | 0 |
| gpt-5.6 | 0 / 101,247 | 34,716 | 167 | 1 | 0 |
| qwen3.7 | 13,128 / 237,411 | 17,516 | 0 | 4,367 | 0 |

v4已识别调用包含partial命令中有明确证据的顶层调用；partial仍不是整段完整。初始/其他无command记录不进入command覆盖率，具体数量见summary.json。原生动作层保持v3，不能把源码增量当成新增实际执行。

## 已识别源码调用的活动构成

下表单位均为调用源码出现次数；一个command可以包含多个调用。类别计数仅覆盖白名单识别部分，未知片段不被填成零次业务操作。

| 模型标签 | click | clipboard | pointer | screenshot | scroll | text_or_key | wait |
|---|---:|---:|---:|---:|---:|---:|---:|
| MiniMax-M3 | 9,236 | 0 | 636 | 0 | 1,867 | 3,225,612 | 3,750 |
| claude-opus-4-7 | 12,749 | 0 | 1,680 | 0 | 2,123 | 18,949 | 3,556 |
| claude-sonnet-4-6-max | 9,973 | 0 | 585 | 0 | 2,549 | 10,574 | 3,505 |
| claude-sonnet-4-6-medium | 10,990 | 0 | 597 | 0 | 3,099 | 13,406 | 3,616 |
| gpt-5.5 | 3,006 | 126 | 3,967 | 0 | 230 | 104,385 | 3,281 |
| gpt-5.6 | 6,488 | 167 | 7,931 | 0 | 343 | 74,895 | 11,423 |
| qwen3.7 | 6,336 | 0 | 1,754 | 367 | 1,166 | 227,788 | 0 |

typewrite/write/hotkey补充的是键盘与文本输入，time.sleep单列wait，pyperclip.copy/paste单列clipboard。clipboard接口出现不证明粘贴成功；文本内容、base64解码和应用业务语义没有执行或恢复。

## 逐轨迹分布与源码集中度

| 模型标签 | 轨迹n | 已识别源码调用/轨迹 median | IQR | 最大值 / 本地task key |
|---|---:|---:|---:|---|
| MiniMax-M3 | 108 | 26308.5 | 37066.8 | 102,174 / 062 |
| claude-opus-4-7 | 108 | 325.5 | 275.8 | 1,113 / 081 |
| claude-sonnet-4-6-max | 108 | 226.5 | 225.0 | 676 / 094 |
| claude-sonnet-4-6-medium | 108 | 287.0 | 246.0 | 678 / 088 |
| gpt-5.5 | 108 | 947.5 | 1204.0 | 3,120 / 064 |
| gpt-5.6 | 107 | 707.0 | 871.5 | 3,487 / 090 |
| qwen3.7 | 108 | 484.5 | 2566.8 | 38,165 / 067 |

分位数使用(n−1)×p线性插值，包含该模型全部轨迹的零值；不是按调用量加权的轨迹平均。MiniMax的大量重复press是保存源码的重复出现，不按step/call_id擅自去重，也不解释为用户实际按键量。

## 保存序列与未知边界

| 模型标签 | 保存源码顺序中计数最高的三个转换 |
|---|---|
| MiniMax-M3 | text_or_key->text_or_key=3,221,060; click->click=5,522; click->text_or_key=2,823 |
| claude-opus-4-7 | text_or_key->text_or_key=12,967; click->click=7,244; text_or_key->click=2,037 |
| claude-sonnet-4-6-max | text_or_key->text_or_key=7,386; click->click=5,703; text_or_key->click=1,385 |
| claude-sonnet-4-6-medium | text_or_key->text_or_key=9,345; click->click=6,519; scroll->scroll=1,627 |
| gpt-5.5 | text_or_key->text_or_key=101,658; pointer->click=3,006; text_or_key->wait=1,826 |
| gpt-5.6 | text_or_key->text_or_key=67,275; pointer->click=6,488; text_or_key->wait=6,459 |
| qwen3.7 | text_or_key->text_or_key=225,380; click->click=4,000; click->text_or_key=1,655 |

转换只在没有未知片段隔断的保存源码相邻调用之间计数。unsupported语句、无command记录或坏JSON会截断；不跨越它们恢复业务流程，也不据转换推断实际执行顺序、并行或耗时。

## call_id与批次字段

| 模型标签 | 保存ID组 | 索引/size/last完整组 | 不完整或歧义组 | 重复index记录 |
|---|---:|---:|---:|---:|
| MiniMax-M3 | 0 | 0 | 0 | 0 |
| claude-opus-4-7 | 0 | 0 | 0 | 0 |
| claude-sonnet-4-6-max | 0 | 0 | 0 | 0 |
| claude-sonnet-4-6-medium | 0 | 0 | 0 | 0 |
| gpt-5.5 | 10069 | 10069 | 0 | 0 |
| gpt-5.6 | 11307 | 11293 | 14 | 0 |
| qwen3.7 | 0 | 0 | 0 | 0 |

没有call_id字段的模型此表为0个可分组ID，不代表0次工具执行。组仅按一个model/task内同一保存ID汇集；完整仅指保存的index/size/last一致，不证明结果成功或真实网络调用闭合。

## 剩余缺口

- Claude的try/属性赋值包装、GPT部分base64解码赋值仍未解析；本轮不穿透控制流猜实际分支。
- GPT computer_call仍是通用包装，原生动作类型未知；命令静态类别是独立证据，不能回填为原生点击/输入。
- task key与历史运行版本绑定、前台应用、动作效果、可靠耗时和资源仍无新增证据。
- 这里补充的是已有语料的解析覆盖；SWE-bench、H-EPM等下一项未启动。

[解析覆盖报告](summary.md) · [分类CSV](static_categories.csv) · [转换CSV](static_transitions.csv) · [逐command审计](command_records.jsonl) · [派生manifest](findings-manifest.json)
