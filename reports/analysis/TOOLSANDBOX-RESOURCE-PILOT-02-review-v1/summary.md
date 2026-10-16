# TOOLSANDBOX-RESOURCE-PILOT-02：单次运行离线行为—资源复核

- 任务：`send_message_with_contact_content_cellular_off`；run：`20261012T091455Z-tsbpilot02`；identity：`3f855a9c70efff83e259093c147e95cd87b7915a7891f2128ecae64021a7ea7b`。本报告仅描述一次运行（n=1）。
- 输入身份与所有登记文件哈希核验：通过。当前执行代码与历史冻结文件身份匹配：True。这两项分别表示归档证据完整性与当前源码对齐。
- 历史事件流中的 run 根事件只有 open 行并列入 right-censored；这与独立 attempt/worker 完成、正常退出、评估完成及进程回收记录并列保留，不把事件跨度误作完整运行时长。

## 四维结论

| 测量完整性 | 官方任务评估 | 终止机制 | 基础设施与归档 |
|---|---|---|---|
| 33个周期样本；窗口与attempt wall不同；CLK_TCK历史运行值未单独保存，CPU秒按当前只读值换算 | 官方评估已完成；similarity=0.918777，四项milestone分数前三项为1、末项为0.675106 | `user_end_conversation`；conversation_active=false；无deadline timeout | 入口/worker退出码0；worker已回收；采样器停止；原始归档哈希匹配 |

## 行为与停止

Agent逻辑请求 5 次，User 1 次；保存的项目层尝试计数为 `[1, 1, 1, 1, 1, 1]`。这不是实际HTTP请求数；本次没有传输层hook，实际传输次数unknown。请求模型标签与响应model分别为 `deepseek-v4-flash` 与 `deepseek-flash`。usage（Agent/User）分别记录prompt 4510/1219、completion 337/37 tokens；这不是账单，实际费用仍unknown。
Agent自主工具调用 4 次，User结束工具 1 次；另有system setup事件 1 次，独立bootstrap tool_call span数为0。共记录 5 个执行批次、5 次ordering。5个逻辑工具调用返回均为ok；wrapper的tool_call_executions=6恰等于逻辑工具调用+system setup，不代表全是模型选择的工具。批次窗口是共享执行范围，不是每个工具的独占耗时/CPU。
保存的Agent路径为：`search_contacts` → `get_cellular_service_status` → `set_cellular_service_status` → `send_message_with_phone_number`；随后User侧单独执行`end_conversation`。另有system setup记录，不计作Agent自主工具。工具ok、会话结束与评分是不同维度。逻辑调用span与请求ID可关联；批次与单工具span没有共同ID，故分别计数、不按位置强配。保存event ID配对无重复/孤立调用返回；只有顶层run事件保持open/right-censored，worker/attempt另有正常完成记录。所有工具返回早于worker结束，end_conversation后无新增模型请求。
## 时间与共享进程资源

| 窗口 | wall（秒） | 共享worker CPU ticks | CPU秒（除以当前只读CLK_TCK） |
|---|---:|---:|---:|
| initialization_setup | 6.550 | 25205 | 252.05 |
| play | 7.074 | 9165 | 91.65 |
| play_to_evaluation_gap | 0.010 | 96 | 0.96 |
| evaluation | 2.051 | 34764 | 347.64 |
| worker_tail | 0.087 | 1396 | 13.96 |
| attempt wall | 16.173 | — | — |
| worker窗口 | 15.772 | — | — |
| 周期采样窗口 | 16.000 | 70658 | 706.58 |

worker窗口 15.772s；周期采样窗口 16.000s，与attempt wall 16.173s不同。清理进程回收核验发生于parent起点后 16.149s；归档验证状态为 `{'valid': True, 'errors': []}`。没有独立归档完整起止时长。

Agent/User play观测窗请求/批次互斥分解：request-only 6.352s，batch-only 0.387s，overlap 0.000s，uncovered 0.335s；守恒残差 0s。uncovered不解释为思考或等待时间。请求区间是客户端调用区间，不是模型思考时间。
周期采样：33点，最大线程数观测384；RSS采样峰值 1536806912 bytes。无独立内核peak。样本CPU差分为 70658 ticks（当前只读CLK_TCK换算 706.58 process CPU-s；按有效采样间隔计算平均约44.16个process core-equivalents）。`rchar/wchar`差分为42824476/111750 bytes；`read_bytes/write_bytes`为0/135168 bytes。它们是不同proc I/O计数口径，不代表完整文件系统流量。采样窗口不覆盖整个attempt。

采样状态：stat/io/status缺读计数分别为0/0/0；CPU计数回退区间0、非递增时间区间0，最大采样间隔0.500074s。样本CPU区间中outside-play 56894 ticks、跨事件mixed 7689 ticks、跨阶段mixed 6075 ticks；本次没有纯请求/批次区间可用于周期样本CPU归因。

阶段CPU ticks分段守恒残差为0 ticks。样本计数器区间采用保存顺序；缺读/回退/时间异常区间保持缺口或mixed，不插值。阶段边界计数器与周期采样端点不同，二者总量不要求相等；所有阶段值属于共享worker进程。线程数不是核心数或实际并行度。RSS采样峰值不是内核峰值。

## 官方评分解释

任务定义的四项检查及保存匹配如下（不展示消息正文、收件人或参数）：

| Milestone | 检查对象 | 保存映射snapshot | 分数 |
|---:|---|---:|---:|
| 0 | cellular setting state | 21 | 1.000000 |
| 1 | contact-search tool trace in sandbox state | 17 | 1.000000 |
| 2 | outgoing message state matching target recipient/content constraints | 23 | 1.000000 |
| 3 | Agent-to-User confirmation message matching target | 24 | 0.675106 |

保存的overall similarity=0.918776593；四项分数的平均与该值一致，minefield mapping为空。第三项（消息状态检查）满分，因此未满整体分不能笼统说成消息未发送。末项部分分对应Agent→User确认消息检查；仅凭aggregate mapping无法唯一分解它为何为0.675106，本次没有重跑evaluator，也未另设成功阈值。

## 批次窗口内共享进程变化

下表是工具批次前后读取到的共享worker进程计数器差，不是单工具独占成本；调用与批次之间没有共同的可回查逐工具ID，因此不据批次名字按位置配对。

| 批次 | 保存的工具名 | 窗口wall（秒） | 共享进程CPU ticks差 | RSS差（bytes） |
|---:|---|---:|---:|---:|
| 1 | search_contacts | 0.111818 | 1618 | 17010688 |
| 2 | get_cellular_service_status | 0.056273 | 813 | 36696064 |
| 3 | set_cellular_service_status | 0.073397 | 1014 | -1007616 |
| 4 | send_message_with_phone_number | 0.081267 | 1104 | 6348800 |
| 5 | 未记录 | 0.063907 | 778 | 0 |

## 高CPU机制：证据边界

初始化/准备、play和evaluator的共享进程边界计数器差分均为可观察事实；evaluator阶段CPU较高。静态源码显示初始化构造场景/角色；官方执行环境在多工具并行消息分支存在排列与深拷贝处理，但本run每批仅记录一次ordering，不能证明该多排列分支实际执行；evaluator用DFS匹配milestone与snapshot。它们只是静态候选机制，缺少函数级profile，不能据此判定哪个机制主导CPU。未运行perf。

## 测量限制与建议

本次没有受控重复，不推断变异、Assistant类别规律、因果或架构敏感性；不推算账单、思考时间或单工具独占资源。没有保存运行时在线CPU数量或历史CLK_TCK快照；当前只读CLK_TCK仅用于条件换算。PILOT-01是首次客户端初始化失败，不是本run的受控重复。

建议：优先扩大固定配置下的任务覆盖，再判断是否需要重复；本建议不是执行授权。
