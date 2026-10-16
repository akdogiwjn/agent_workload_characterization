# ToolSandbox Assistant Repeat-01：离线行为—资源特征化

范围：3个固定官方任务，各3次顺序重复；完整identity `1643e0c8c6158734ce7186d24afd5ce36d5a40718d930e7eea2a507f0b32149b`。这是描述性小样本，不代表Assistant类别总体。PILOT-01/02未计入。

## 验收与覆盖

批次完成 9/9，未执行 0；批wall 196.377 秒。身份、计划/冻结/批准、批与raw manifest、显式顺序和实际文件集合均已核验。每run结果计数、调用闭合、清理、sampler停止及归档检查：`True`。
当前工作区执行代码与历史冻结代码逐文件匹配：`True`。该项与历史归档完整性分开记录，不改写历史身份。

## 每次运行

|任务/round|run_id|Agent/User请求|Agent工具/User结束|batch / batch排列执行|wrapper执行（含setup）|similarity|attempt wall|采样窗|采样CPU-s|RSS峰值 MiB|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|A r0|`20261012T135428Z-r0-a-tsbassistant01`|5/1|4/1|5 / 5|6|0.912371|15.275s|15.000s|542.26|1412.3|
|B r0|`20261012T135444Z-r0-b-tsbassistant01`|5/1|4/1|5 / 5|6|1.000000|14.902s|14.500s|511.21|1439.6|
|C r0|`20261012T135459Z-r0-c-tsbassistant01`|7/2|7/1|6 / 8|9|0.964414|30.345s|30.000s|2032.21|1764.9|
|B r1|`20261012T135529Z-r1-b-tsbassistant01`|5/1|4/1|5 / 5|6|1.000000|14.206s|14.000s|418.92|1424.8|
|C r1|`20261012T135543Z-r1-c-tsbassistant01`|7/2|7/1|6 / 8|9|0.906622|26.971s|26.500s|1285.06|1663.3|
|A r1|`20261012T135610Z-r1-a-tsbassistant01`|5/1|4/1|5 / 5|6|0.927953|16.778s|16.500s|645.66|1416.8|
|C r2|`20261012T135627Z-r2-c-tsbassistant01`|9/3|10/1|7 / 13|14|0.764414|49.302s|49.000s|3117.18|1572.6|
|A r2|`20261012T135716Z-r2-a-tsbassistant01`|4/1|4/1|4 / 5|6|0.924314|14.192s|14.000s|578.36|1519.6|
|B r2|`20261012T135730Z-r2-b-tsbassistant01`|5/1|4/1|5 / 5|6|1.000000|14.366s|14.000s|352.91|1396.2|

说明：wrapper执行总数包含system setup；batch排列执行不含setup。批/工具事件没有可用的一一关联ID，不按数量或位置配对。采样CPU-s是共享多线程worker计数差，不能归到单个工具；RSS是采样峰值，无内核memory peak。

## 按任务的重复统计

分位数为 `(n−1)×p` 线性插值。每任务n=3；没有跨任务汇总或显著性检验。

### A — `send_message_with_contact_content_cellular_off`

观察到的Agent工具路径（保存的调用开始顺序，仅描述记录顺序）：[{'sequence': ['search_contacts', 'get_cellular_service_status', 'set_cellular_service_status', 'send_message_with_phone_number'], 'count': 2, 'run_ids': ['20261012T135428Z-r0-a-tsbassistant01', '20261012T135716Z-r2-a-tsbassistant01']}, {'sequence': ['search_contacts', 'send_message_with_phone_number', 'set_cellular_service_status', 'send_message_with_phone_number'], 'count': 1, 'run_ids': ['20261012T135610Z-r1-a-tsbassistant01']}]

|指标|n / median / IQR / 原始点|
|---|---|
|agent_logical_requests|n=3; median 5.000; Q1–Q3 4.500–5.000; IQR 0.500; raw=[5, 5, 4]|
|user_logical_requests|n=3; median 1.000; Q1–Q3 1.000–1.000; IQR 0.000; raw=[1, 1, 1]|
|agent_tool_calls|n=3; median 4.000; Q1–Q3 4.000–4.000; IQR 0.000; raw=[4, 4, 4]|
|tool_ok_returns|n=3; median 5.000; Q1–Q3 4.500–5.000; IQR 0.500; raw=[5, 4, 5]|
|tool_not_ok_returns|n=3; median 0.000; Q1–Q3 0.000–0.500; IQR 0.500; raw=[0, 1, 0]|
|tool_batches|n=3; median 5.000; Q1–Q3 4.500–5.000; IQR 0.500; raw=[5, 5, 4]|
|batch_ordering_executions|n=3; median 5.000; Q1–Q3 5.000–5.000; IQR 0.000; raw=[5, 5, 5]|
|proc_rchar_delta_bytes|n=3; median 42830989.000 bytes; Q1–Q3 42826138.000–42853743.500 bytes; IQR 27605.500 bytes; raw=[42830989, 42876498, 42821287]|
|proc_wchar_delta_bytes|n=3; median 127739.000 bytes; Q1–Q3 124414.000–127769.000 bytes; IQR 3355.000 bytes; raw=[127799, 127739, 121089]|
|proc_read_bytes_delta|n=3; median 0.000 bytes; Q1–Q3 0.000–0.000 bytes; IQR 0.000 bytes; raw=[0, 0, 0]|
|proc_write_bytes_delta|n=3; median 155648.000 bytes; Q1–Q3 155648.000–155648.000 bytes; IQR 0.000 bytes; raw=[155648, 155648, 155648]|
|thread_count_max|n=3; median 384.000; Q1–Q3 384.000–384.000; IQR 0.000; raw=[384, 384, 384]|
|attempt_wall_s|n=3; median 15.275s; Q1–Q3 14.734–16.027s; IQR 1.293s; raw=[15.275002731, 16.778466306, 14.19209188]|
|worker_window_s|n=3; median 14.924s; Q1–Q3 14.357–15.674s; IQR 1.317s; raw=[14.923554466, 16.424795431, 13.791003578]|
|setup_wall_s|n=3; median 6.865s; Q1–Q3 6.788–6.987s; IQR 0.199s; raw=[6.710359445, 7.109176427, 6.865103835]|
|imports_wall_s|n=3; median 1.120s; Q1–Q3 1.114–1.129s; IQR 0.015s; raw=[1.139050565, 1.108395583, 1.119533283]|
|play_wall_s|n=3; median 6.471s; Q1–Q3 5.828–7.005s; IQR 1.177s; raw=[6.470613341, 7.539875248, 5.186236612]|
|evaluator_wall_s|n=3; median 1.660s; Q1–Q3 1.657–1.673s; IQR 0.015s; raw=[1.660139251, 1.685030456, 1.654072569]|
|setup_process_cpu_s|n=3; median 275.980s; Q1–Q3 260.580–305.325s; IQR 44.745s; raw=[245.18, 334.67, 275.98]|
|play_process_cpu_s|n=3; median 49.600s; Q1–Q3 49.160–49.860s; IQR 0.700s; raw=[49.6, 50.12, 48.72]|
|evaluator_process_cpu_s|n=3; median 243.220s; Q1–Q3 240.185–246.850s; IQR 6.665s; raw=[237.15, 250.48, 243.22]|
|sample_window_s|n=3; median 15.000s; Q1–Q3 14.500–15.750s; IQR 1.250s; raw=[15.000090215, 16.500074603, 14.00008192]|
|sample_cpu_s|n=3; median 578.360s; Q1–Q3 560.310–612.010s; IQR 51.700s; raw=[542.26, 645.66, 578.36]|
|rss_sampled_peak_bytes|n=3; median 1485660160.000 bytes; Q1–Q3 1483276288.000–1539543040.000 bytes; IQR 56266752.000 bytes; raw=[1480892416, 1485660160, 1593425920]|
|evaluation_similarity|n=3; median 0.924; Q1–Q3 0.918–0.926; IQR 0.008; raw=[0.9123712114660444, 0.9279525731469985, 0.9243141576172959]|

### B — `add_reminder_content_and_week_delta_and_time`

观察到的Agent工具路径（保存的调用开始顺序，仅描述记录顺序）：[{'sequence': ['get_current_timestamp', 'timestamp_to_datetime_info', 'datetime_info_to_timestamp', 'add_reminder'], 'count': 3, 'run_ids': ['20261012T135444Z-r0-b-tsbassistant01', '20261012T135529Z-r1-b-tsbassistant01', '20261012T135730Z-r2-b-tsbassistant01']}]

|指标|n / median / IQR / 原始点|
|---|---|
|agent_logical_requests|n=3; median 5.000; Q1–Q3 5.000–5.000; IQR 0.000; raw=[5, 5, 5]|
|user_logical_requests|n=3; median 1.000; Q1–Q3 1.000–1.000; IQR 0.000; raw=[1, 1, 1]|
|agent_tool_calls|n=3; median 4.000; Q1–Q3 4.000–4.000; IQR 0.000; raw=[4, 4, 4]|
|tool_ok_returns|n=3; median 5.000; Q1–Q3 5.000–5.000; IQR 0.000; raw=[5, 5, 5]|
|tool_not_ok_returns|n=3; median 0.000; Q1–Q3 0.000–0.000; IQR 0.000; raw=[0, 0, 0]|
|tool_batches|n=3; median 5.000; Q1–Q3 5.000–5.000; IQR 0.000; raw=[5, 5, 5]|
|batch_ordering_executions|n=3; median 5.000; Q1–Q3 5.000–5.000; IQR 0.000; raw=[5, 5, 5]|
|proc_rchar_delta_bytes|n=3; median 42788021.000 bytes; Q1–Q3 42787079.000–42807798.500 bytes; IQR 20719.500 bytes; raw=[42788021, 42827576, 42786137]|
|proc_wchar_delta_bytes|n=3; median 102097.000 bytes; Q1–Q3 101846.500–109249.000 bytes; IQR 7402.500 bytes; raw=[102097, 116401, 101596]|
|proc_read_bytes_delta|n=3; median 0.000 bytes; Q1–Q3 0.000–0.000 bytes; IQR 0.000 bytes; raw=[0, 0, 0]|
|proc_write_bytes_delta|n=3; median 114688.000 bytes; Q1–Q3 110592.000–124928.000 bytes; IQR 14336.000 bytes; raw=[114688, 135168, 106496]|
|thread_count_max|n=3; median 384.000; Q1–Q3 384.000–384.000; IQR 0.000; raw=[384, 384, 384]|
|attempt_wall_s|n=3; median 14.366s; Q1–Q3 14.286–14.634s; IQR 0.348s; raw=[14.901895625, 14.206141949, 14.366460025]|
|worker_window_s|n=3; median 14.022s; Q1–Q3 13.944–14.255s; IQR 0.311s; raw=[14.487712355, 13.865844834, 14.02243925]|
|setup_wall_s|n=3; median 6.799s; Q1–Q3 6.748–7.014s; IQR 0.267s; raw=[7.229723388, 6.798742063, 6.696342686]|
|imports_wall_s|n=3; median 1.119s; Q1–Q3 1.119–1.120s; IQR 0.001s; raw=[1.11930498, 1.119391121, 1.121052133]|
|play_wall_s|n=3; median 6.569s; Q1–Q3 6.479–6.616s; IQR 0.138s; raw=[6.569057584, 6.3886794, 6.663811989]|
|evaluator_wall_s|n=3; median 0.608s; Q1–Q3 0.602–0.612s; IQR 0.011s; raw=[0.615893911, 0.608439161, 0.594588455]|
|setup_process_cpu_s|n=3; median 274.010s; Q1–Q3 249.915–321.965s; IQR 72.050s; raw=[369.92, 274.01, 225.82]|
|play_process_cpu_s|n=3; median 47.080s; Q1–Q3 45.750–47.540s; IQR 1.790s; raw=[47.08, 48.0, 44.42]|
|evaluator_process_cpu_s|n=3; median 89.210s; Q1–Q3 87.875–91.055s; IQR 3.180s; raw=[92.9, 89.21, 86.54]|
|sample_window_s|n=3; median 14.000s; Q1–Q3 14.000–14.250s; IQR 0.250s; raw=[14.500083452, 14.0001333, 14.000103039]|
|sample_cpu_s|n=3; median 418.920s; Q1–Q3 385.915–465.065s; IQR 79.150s; raw=[511.21, 418.92, 352.91]|
|rss_sampled_peak_bytes|n=3; median 1494028288.000 bytes; Q1–Q3 1479034880.000–1501792256.000 bytes; IQR 22757376.000 bytes; raw=[1509556224, 1494028288, 1464041472]|
|evaluation_similarity|n=3; median 1.000; Q1–Q3 1.000–1.000; IQR 0.000; raw=[1.0, 1.0, 1.0]|

### C — `modify_contact_with_message_recency_multiple_user_turn`

观察到的Agent工具路径（保存的调用开始顺序，仅描述记录顺序）：[{'sequence': ['get_current_timestamp', 'search_contacts', 'search_messages', 'search_messages', 'search_contacts', 'modify_contact', 'search_contacts'], 'count': 1, 'run_ids': ['20261012T135459Z-r0-c-tsbassistant01']}, {'sequence': ['search_contacts', 'get_current_timestamp', 'search_messages', 'search_messages', 'search_contacts', 'modify_contact', 'search_contacts'], 'count': 1, 'run_ids': ['20261012T135543Z-r1-c-tsbassistant01']}, {'sequence': ['search_contacts', 'search_messages', 'search_messages', 'search_messages', 'search_contacts', 'search_contacts', 'search_contacts', 'get_current_timestamp', 'modify_contact', 'search_contacts'], 'count': 1, 'run_ids': ['20261012T135627Z-r2-c-tsbassistant01']}]

|指标|n / median / IQR / 原始点|
|---|---|
|agent_logical_requests|n=3; median 7.000; Q1–Q3 7.000–8.000; IQR 1.000; raw=[7, 7, 9]|
|user_logical_requests|n=3; median 2.000; Q1–Q3 2.000–2.500; IQR 0.500; raw=[2, 2, 3]|
|agent_tool_calls|n=3; median 7.000; Q1–Q3 7.000–8.500; IQR 1.500; raw=[7, 7, 10]|
|tool_ok_returns|n=3; median 8.000; Q1–Q3 8.000–9.000; IQR 1.000; raw=[8, 8, 10]|
|tool_not_ok_returns|n=3; median 0.000; Q1–Q3 0.000–0.500; IQR 0.500; raw=[0, 0, 1]|
|tool_batches|n=3; median 6.000; Q1–Q3 6.000–6.500; IQR 0.500; raw=[6, 6, 7]|
|batch_ordering_executions|n=3; median 8.000; Q1–Q3 8.000–10.500; IQR 2.500; raw=[8, 8, 13]|
|proc_rchar_delta_bytes|n=3; median 42799454.000 bytes; Q1–Q3 42798661.500–42823736.000 bytes; IQR 25074.500 bytes; raw=[42799454, 42797869, 42848018]|
|proc_wchar_delta_bytes|n=3; median 169901.000 bytes; Q1–Q3 169790.500–205600.000 bytes; IQR 35809.500 bytes; raw=[169680, 169901, 241299]|
|proc_read_bytes_delta|n=3; median 0.000 bytes; Q1–Q3 0.000–0.000 bytes; IQR 0.000 bytes; raw=[0, 0, 0]|
|proc_write_bytes_delta|n=3; median 147456.000 bytes; Q1–Q3 143360.000–169984.000 bytes; IQR 26624.000 bytes; raw=[147456, 139264, 192512]|
|thread_count_max|n=3; median 384.000; Q1–Q3 384.000–384.000; IQR 0.000; raw=[384, 384, 384]|
|attempt_wall_s|n=3; median 30.345s; Q1–Q3 28.658–39.823s; IQR 11.166s; raw=[30.344633141, 26.97095524, 49.302069275]|
|worker_window_s|n=3; median 29.952s; Q1–Q3 28.294–39.443s; IQR 11.149s; raw=[29.951525455, 26.637245363, 48.934839787]|
|setup_wall_s|n=3; median 7.194s; Q1–Q3 6.937–7.203s; IQR 0.266s; raw=[7.212417595, 7.193796745, 6.681065991]|
|imports_wall_s|n=3; median 1.127s; Q1–Q3 1.125–1.144s; IQR 0.019s; raw=[1.122200529, 1.12746602, 1.160023667]|
|play_wall_s|n=3; median 12.800s; Q1–Q3 12.548–15.025s; IQR 2.477s; raw=[12.29623673, 12.800251837, 17.250310711]|
|evaluator_wall_s|n=3; median 10.363s; Q1–Q3 8.465–17.648s; IQR 9.183s; raw=[10.362790244, 6.566286387, 24.93304629]|
|setup_process_cpu_s|n=3; median 383.700s; Q1–Q3 314.345–385.645s; IQR 71.300s; raw=[387.59, 383.7, 244.99]|
|play_process_cpu_s|n=3; median 99.670s; Q1–Q3 85.875–100.115s; IQR 14.240s; raw=[100.56, 72.08, 99.67]|
|evaluator_process_cpu_s|n=3; median 1536.270s; Q1–Q3 1190.710–2151.085s; IQR 960.375s; raw=[1536.27, 845.15, 2765.9]|
|sample_window_s|n=3; median 30.000s; Q1–Q3 28.250–39.500s; IQR 11.250s; raw=[30.000094218, 26.500085669, 49.000084235]|
|sample_cpu_s|n=3; median 2032.210s; Q1–Q3 1658.635–2574.695s; IQR 916.060s; raw=[2032.21, 1285.06, 3117.18]|
|rss_sampled_peak_bytes|n=3; median 1744093184.000 bytes; Q1–Q3 1696557056.000–1797345280.000 bytes; IQR 100788224.000 bytes; raw=[1850597376, 1744093184, 1649020928]|
|evaluation_similarity|n=3; median 0.907; Q1–Q3 0.836–0.936; IQR 0.100; raw=[0.9644141377627158, 0.9066224545383553, 0.7644141377627156]|

## Agent/User与工具执行口径

合计 65 个逻辑请求（Agent 52、User 13）；每个请求对应项目层尝试总数 65。实际HTTP传输数因无transport级hook而unknown。响应model为 `deepseek-flash`，请求model别名与响应model分别记录。
保存到 48 个Agent工具调用、9 个User `end_conversation`、48 个执行batch、59 次batch内部排列执行；另有 9 次system setup。wrapper执行计数 68 包含这些setup执行，不应再与setup重复相加。
工具路径按任务分列；多工具请求的保存时间顺序不证明实际并发次序。一次batch可对应多个排列执行；batch中的native call IDs与逻辑tool-call event之间未保存直接映射。末次返回和User结束工具均已记录；9/9 conversation stop reason为`user_end_conversation`，结束后没有新增请求。

## 2次工具错误与后续路径

- `20261012T135610Z-r1-a-tsbassistant01` / `991d77e64b634445a1385cdc4fe01c86`：`send_message_with_phone_number` 返回 `ConnectionError`（request `agent-2`）。下一同角色请求 `agent-3` 的工具调用为 `[{'tool_name': 'set_cellular_service_status', 'status': 'closed', 'ok': True, 'event_id': '2b0f27bee9704a0ab7d521b8baf8cdb4'}]`。参数正文未复制。
- `20261012T135627Z-r2-c-tsbassistant01` / `fb00651c23854a678df10554a9e1bbd6`：`search_messages` 返回 `ValueError`（request `agent-1`）。下一同角色请求 `agent-2` 的工具调用为 `[{'tool_name': 'search_messages', 'status': 'closed', 'ok': True, 'event_id': '001c32438a73491b993d9f3258244654'}, {'tool_name': 'search_messages', 'status': 'closed', 'ok': True, 'event_id': 'f81927ed7ddd432eab2c522e2145c2e5'}]`。参数正文未复制。

A/r1：保存返回只保留`ConnectionError`类别；官方`send_message_with_phone_number`在cellular未启用时会抛该异常，冻结任务初态为cellular off。Agent随后调用`set_cellular_service_status`，之后再次调用发送工具并获得ok返回。它是后续新的工具调用，不是transport重试；最终outgoing-message milestone得分为1，但确认消息milestone为部分分。不能据此断言前次错误没有影响。
C/r2：`search_messages`返回`ValueError`类别；参数摘要与空JSON对象的SHA-256一致，冻结官方实现说明未提供任一搜索条件会抛ValueError。该调用发生在包含`search_contacts`和`search_messages`的多工具请求中，batch计划2种顺序但在1次执行后因失败停止。后续请求中保存了两次成功的`search_messages`调用，随后继续联系人搜索、修改与结束。任务mapping中的search_messages milestone得分为0；其与错误、后续恢复以及最终评估之间不能做单一因果归因。

错误类别由保存的sanitized终态和固定源码支持；没有读取完整参数、返回正文或模型消息正文。工具错误不是模型协议错误、harness/infra失败的同义词。

## 任务评估与任务内差异

所有评估均完成，但similarity不是统一成功标签；任务milestone数量和语义不同，不能跨任务排名。官方固定任务语义来自冻结源码中的milestone定义：A检查cellular状态、联系人搜索trace、目标消息状态及确认文本；B检查当前时间trace及明天下午5点的提醒内容/时间；C检查时间、联系人/消息搜索trace、基于最近消息的联系人更新及确认文本。逐run实际mapping、snapshot index、score见summary.json/per_run.jsonl。

Task C的三点显示波动主要落在 evaluator 阶段：按任务内统计，evaluator wall IQR 大于 setup/play wall IQR；evaluator边界CPU IQR也最大。r2/C同时有更多Agent请求、逻辑工具、batch排列执行，并有一次search_messages错误；这些是共现差异，不能证明导致评估wall/CPU增加。冻结源码显示评估器用带剪枝/记忆的DFS匹配milestones与snapshots；执行环境也会对多工具调用做排列和深拷贝。这仅是静态候选机制，没有profile证明任何函数是热点或解释了大部分CPU。

## 时间与资源边界

attempt wall、worker边界窗口、周期采样窗口分别报告。setup定义为`worker_start→play_begin`，包含imports及场景/client初始化；imports另列为setup子窗口。play/evaluator/间隙/tail使用同宿主monotonic阶段边界。请求时长是客户端逻辑调用边界，不是思考时间；tool_batch为共享执行环境窗口，不复制成单工具耗时。

phase CPU使用各run `environment.json.sc_clk_tck` 从边界user/system/total ticks换算；采样CPU差使用相邻有效样本且使用同一run保存的CLK_TCK。阶段边界与周期样本窗口的端点不同，不强求两者相等。采样间隔若跨阶段或请求/batch事件边界，标为mixed，不插值、不按比例分摊。平均CPU秒可大于wall，因为是多线程共享worker的累计进程CPU。

RSS只报告采样worker RSS峰值；线程数是观测线程数量，不是核心数/并行度。I/O分`rchar/wchar`与`read_bytes/write_bytes`，来源为worker进程`/proc`计数器，不代表完整文件系统流量。环境记录的在线CPU/affinity数量不等于进程配额；cgroup字段为unknown。usage不是账单，实际费用unknown。

## 可支持与不可支持

这批新增了三个固定ToolSandbox任务的真实Agent/User/工具时序、阶段边界、共享worker资源和官方evaluation对应证据，可描述每个任务三次运行内的路径及观测差异。仍不能证明工具独占CPU、函数热点、错误对成绩/时间的因果、实际HTTP传输次数、账单、Assistant类别规律或跨任务能力排名。

建议的唯一后续方向：先评估是否需要扩展更多固定Assistant任务来提高任务覆盖，而非对这三条路径追加重复；该建议不构成执行授权。

来源批manifest SHA-256：`3d001363448c2f10cc3a9f02f794f31147126e4cb4bd5c06310091cf6f6fa518`；批摘要SHA-256：`444fb8a93a1680b912ef8cb3537811f23848e1dcd3594eb530d0f4af80f7643b`。本报告manifest另列实际输入与输出哈希，不自哈希。
