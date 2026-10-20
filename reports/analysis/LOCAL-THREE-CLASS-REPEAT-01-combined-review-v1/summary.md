# 三类任务固定重复批次：续批合并复核

## 批次完成度

原批已启动 1 次；续批计划 26 个槽位，实际启动 22 次，4 次 Coding 按关键测量缺口停止。总计 23 次已启动运行，不是 27 次执行。

续批整体 wall 为 1338.141 秒，14 小时上限内；Coding 类停止原因是 verifier 容器 CPU 测量缺口。各已启动 attempt 的容器/worker 清理与 raw 归档核验通过。

|链路|本次分析中的实际运行|计划续批|任务/采集结论|
|---|---:|---:|---|
|Coding|5|9|5次启动；3个 reward/resolved true、1个 false、1个结果 unknown/measurement partial；剩4槽 not_executed。|
|Office|9|8|原批 Excel 1 次成功单列；续批8次均 Agent authentication BadRequestError，verifier reward=0；路由配置与冻结身份不一致。|
|Assistant|9|9|9次完整；每个固定任务3次，保留原始官方 similarity。|

## 关键路由偏差

续批 Office 冻结身份声明火山网关，但 8 个 task run_config 均未包含 `model_route`。已绑定的生产 `build_agent()` 在该字段缺失时回退到模块常量 `https://api.deepseek.com/v1`。所有 Office run 保存为 `agent_error/BadRequestError`，没有响应模型；认证失败文本已在原始证据中，本文不复制其正文。
因此这 8 次是已消费的 attempt 和真实资源观察，但不是冻结火山路由下的有效任务结果；不能与旧 Excel 成功运行合并为 Office n=3。HTTP 尝试数、实际目的端收到与否、费用均 unknown。由于凭据路由错配可能涉及凭据被送往非预期端点，建议在后续处置中按凭据安全事件核查；本分析未读取凭据、未重发请求，也未修改历史记录。

## 固定任务统计

下面各任务按 profile_stratum 分行。数值分布对每个指标使用该指标实际有效 n，分位数采用 `(n−1)×p` 线性插值。Office 的路由错配行仅是错误路径诊断，不纳入冻结配置任务推断；Coding 不足三次；Assistant 每任务 n=3。

完整逐 run 原始点与 median/IQR 在 `task_statistics.csv`；每次运行资源曲线在 `figures/`，作图数据在 `series/`。

|链路|任务|profile分层|官方结果原始点（n；中位数/IQR）|attempt wall（秒）|主要共享scope CPU（CPU-s）|
|---|---|---|---|---|---|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`continuation_frozen_profile`|n=3; raw=[1, 1, 1]; med=1; IQR=0|n=3; raw=[18.6049, 21.3686, 22.5051]; med=21.369; IQR=1.9501|n=3; raw=[368.98, 499.33, 576.57]; med=499.33; IQR=103.8|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`continuation_frozen_profile`|n=3; raw=[0.974716, 0.974716, 0.996774]; med=0.97472; IQR=0.011029|n=3; raw=[39.7073, 42.708, 44.5624]; med=42.708; IQR=2.4275|n=3; raw=[1120.95, 1454.94, 1476.55]; med=1454.9; IQR=177.8|
|Assistant|`send_message_with_contact_content_cellular_off`|`continuation_frozen_profile`|n=3; raw=[0.940148, 0.945507, 0.946944]; med=0.94551; IQR=0.0033983|n=3; raw=[18.7804, 20.7968, 22.155]; med=20.797; IQR=1.6873|n=3; raw=[525.42, 537.35, 586.52]; med=537.35; IQR=30.55|
|Coding|`astropy__astropy-13236`|`continuation_frozen_profile`|n=2; raw=[1, 1]; med=1; IQR=0|n=2; raw=[160.805, 176.73]; med=168.77; IQR=7.9629|n=1; raw=[32.2473]; med=32.247; IQR=0|
|Coding|`astropy__astropy-13236`|`planned_not_executed`|n=0; median/IQR=unknown|n=0; median/IQR=unknown|n=0; median/IQR=unknown|
|Coding|`astropy__astropy-13398`|`continuation_frozen_profile`|n=1; raw=[0]; med=0; IQR=0|n=2; raw=[145.974, 208.265]; med=177.12; IQR=31.145|n=1; raw=[13.9149]; med=13.915; IQR=0|
|Coding|`astropy__astropy-13398`|`planned_not_executed`|n=0; median/IQR=unknown|n=0; median/IQR=unknown|n=0; median/IQR=unknown|
|Coding|`django__django-16485`|`continuation_frozen_profile`|n=1; raw=[1]; med=1; IQR=0|n=1; raw=[163.487]; med=163.49; IQR=0|n=1; raw=[18.5368]; med=18.537; IQR=0|
|Coding|`django__django-16485`|`planned_not_executed`|n=0; median/IQR=unknown|n=0; median/IQR=unknown|n=0; median/IQR=unknown|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`continuation_Office_route_mismatch`|n=2; raw=[0, 0]; med=0; IQR=0|n=2; raw=[25.3, 25.65]; med=25.475; IQR=0.175|n=2; raw=[2.09949, 2.15051]; med=2.125; IQR=0.025512|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`historical_original_DeepSeek_identity`|n=1; raw=[1]; med=1; IQR=0|n=1; raw=[207.26]; med=207.26; IQR=0|n=1; raw=[12.0002]; med=12; IQR=0|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`continuation_Office_route_mismatch`|n=3; raw=[0, 0, 0]; med=0; IQR=0|n=3; raw=[25.26, 25.35, 25.65]; med=25.35; IQR=0.195|n=3; raw=[2.1308, 2.17812, 2.2847]; med=2.1781; IQR=0.076948|
|Office|`atomic__ppt_008_bullet_editing_seed`|`continuation_Office_route_mismatch`|n=3; raw=[0, 0, 0]; med=0; IQR=0|n=3; raw=[25.28, 25.36, 25.56]; med=25.36; IQR=0.14|n=3; raw=[2.0816, 2.08593, 2.2175]; med=2.0859; IQR=0.06795|

- **Office / atomic__excel_001_budget_bucket_totals_seed / r0** — `20261016T182559Z-09-r0-office`；profile `historical_original_DeepSeek_identity`；结果 `1.0`；终止 `finish`；attempt wall `207.26` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261016T182559Z-09-r0-office.svg) · [作图数据](series/20261016T182559Z-09-r0-office.csv)
- **Coding / django__django-16485 / r0** — `20261017T023247Z-00-r0-coding`；profile `continuation_frozen_profile`；结果 `True`；终止 `Submitted`；attempt wall `163.486785312` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T023247Z-00-r0-coding.svg) · [作图数据](series/20261017T023247Z-00-r0-coding.csv)
- **Coding / astropy__astropy-13236 / r0** — `20261017T023534Z-01-r0-coding`；profile `continuation_frozen_profile`；结果 `True`；终止 `LimitsExceeded`；attempt wall `160.804685196` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T023534Z-01-r0-coding.svg) · [作图数据](series/20261017T023534Z-01-r0-coding.csv)
- **Coding / astropy__astropy-13398 / r0** — `20261017T023817Z-02-r0-coding`；profile `continuation_frozen_profile`；结果 `False`；终止 `LimitsExceeded`；attempt wall `208.265025286` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T023817Z-02-r0-coding.svg) · [作图数据](series/20261017T023817Z-02-r0-coding.csv)
- **Coding / astropy__astropy-13236 / r1** — `20261017T024149Z-03-r1-coding`；profile `continuation_frozen_profile`；结果 `True`；终止 `LimitsExceeded`；attempt wall `176.730464194` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024149Z-03-r1-coding.svg) · [作图数据](series/20261017T024149Z-03-r1-coding.csv)
- **Coding / astropy__astropy-13398 / r1** — `20261017T024449Z-04-r1-coding`；profile `continuation_frozen_profile`；结果 `None`；终止 `LimitsExceeded`；attempt wall `145.974060254` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024449Z-04-r1-coding.svg) · [作图数据](series/20261017T024449Z-04-r1-coding.csv)
- **Office / atomic__ppt_008_bullet_editing_seed / r0** — `20261017T024718Z-09-r0-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.36` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024718Z-09-r0-office.svg) · [作图数据](series/20261017T024718Z-09-r0-office.csv)
- **Office / atomic__pdf_004_audit_pages_reorder_seed / r0** — `20261017T024744Z-10-r0-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.65` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024744Z-10-r0-office.svg) · [作图数据](series/20261017T024744Z-10-r0-office.csv)
- **Office / atomic__ppt_008_bullet_editing_seed / r1** — `20261017T024811Z-11-r1-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.56` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024811Z-11-r1-office.svg) · [作图数据](series/20261017T024811Z-11-r1-office.csv)
- **Office / atomic__pdf_004_audit_pages_reorder_seed / r1** — `20261017T024837Z-12-r1-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.35` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024837Z-12-r1-office.svg) · [作图数据](series/20261017T024837Z-12-r1-office.csv)
- **Office / atomic__excel_001_budget_bucket_totals_seed / r1** — `20261017T024904Z-13-r1-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.3` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024904Z-13-r1-office.svg) · [作图数据](series/20261017T024904Z-13-r1-office.csv)
- **Office / atomic__pdf_004_audit_pages_reorder_seed / r2** — `20261017T024930Z-14-r2-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.26` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024930Z-14-r2-office.svg) · [作图数据](series/20261017T024930Z-14-r2-office.csv)
- **Office / atomic__excel_001_budget_bucket_totals_seed / r2** — `20261017T024956Z-15-r2-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.65` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T024956Z-15-r2-office.svg) · [作图数据](series/20261017T024956Z-15-r2-office.csv)
- **Office / atomic__ppt_008_bullet_editing_seed / r2** — `20261017T025023Z-16-r2-office`；profile `continuation_Office_route_mismatch`；结果 `0.0`；终止 `agent_error`；attempt wall `25.28` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025023Z-16-r2-office.svg) · [作图数据](series/20261017T025023Z-16-r2-office.csv)
- **Assistant / send_message_with_contact_content_cellular_off / r0** — `20261017T025049Z-17-r0-assistant`；profile `continuation_frozen_profile`；结果 `0.9401476194637091`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `18.78036287` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025049Z-17-r0-assistant.svg) · [作图数据](series/20261017T025049Z-17-r0-assistant.csv)
- **Assistant / add_reminder_content_and_week_delta_and_time / r0** — `20261017T025108Z-18-r0-assistant`；profile `continuation_frozen_profile`；结果 `1.0`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `18.604938471` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025108Z-18-r0-assistant.svg) · [作图数据](series/20261017T025108Z-18-r0-assistant.csv)
- **Assistant / modify_contact_with_message_recency_multiple_user_turn / r0** — `20261017T025127Z-19-r0-assistant`；profile `continuation_frozen_profile`；结果 `0.9967736293532093`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `44.562384261` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025127Z-19-r0-assistant.svg) · [作图数据](series/20261017T025127Z-19-r0-assistant.csv)
- **Assistant / add_reminder_content_and_week_delta_and_time / r1** — `20261017T025213Z-20-r1-assistant`；profile `continuation_frozen_profile`；结果 `1.0`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `21.368563949` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025213Z-20-r1-assistant.svg) · [作图数据](series/20261017T025213Z-20-r1-assistant.csv)
- **Assistant / modify_contact_with_message_recency_multiple_user_turn / r1** — `20261017T025234Z-21-r1-assistant`；profile `continuation_frozen_profile`；结果 `0.9747160936387214`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `39.707318054` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025234Z-21-r1-assistant.svg) · [作图数据](series/20261017T025234Z-21-r1-assistant.csv)
- **Assistant / send_message_with_contact_content_cellular_off / r1** — `20261017T025315Z-22-r1-assistant`；profile `continuation_frozen_profile`；结果 `0.9469442875374467`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `20.796802672` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025315Z-22-r1-assistant.svg) · [作图数据](series/20261017T025315Z-22-r1-assistant.csv)
- **Assistant / modify_contact_with_message_recency_multiple_user_turn / r2** — `20261017T025336Z-23-r2-assistant`；profile `continuation_frozen_profile`；结果 `0.9747160936387214`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `42.707991654` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025336Z-23-r2-assistant.svg) · [作图数据](series/20261017T025336Z-23-r2-assistant.csv)
- **Assistant / send_message_with_contact_content_cellular_off / r2** — `20261017T025420Z-24-r2-assistant`；profile `continuation_frozen_profile`；结果 `0.9455066862191938`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `22.154995868` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025420Z-24-r2-assistant.svg) · [作图数据](series/20261017T025420Z-24-r2-assistant.csv)
- **Assistant / add_reminder_content_and_week_delta_and_time / r2** — `20261017T025442Z-25-r2-assistant`；profile `continuation_frozen_profile`；结果 `1.0`；终止 `{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}`；attempt wall `22.505062415` s；测量 `only the saved scope windows; not the whole attempt`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。
  [资源图](figures/20261017T025442Z-25-r2-assistant.svg) · [作图数据](series/20261017T025442Z-25-r2-assistant.csv)

## 允许的观察与边界

1. Assistant 三个固定任务均完成 3 次，原始 similarity 在 per-run 数据中；这是固定场景描述，不代表 Assistant 类总体或成功率。
2. Coding 的有效完成路径只覆盖已执行的5个槽；Astropy-13398 r1 的 verifier CPU 区间缺失触发停止，4个剩余槽没有补跑。
3. Office 路由错配让 Agent 在首请求失败；资源采样窗口仍可描述初始化/失败/清理期间的共享容器变化，但不能解释为 Office 文档操作成功路径。
4. Coding 的 Agent 与 verifier 容器 CPU、内存和目录分别保留；共享宿主进程、共享 netns、磁盘I/O各自不与容器合并。资源区间与阶段/工具只作共现，不作单工具独占或因果归因。
5. 共享网络按接口单独统计，图中最多选择3个完整窗口非 lo 接口，仅为可读展示，不是 API 出口识别；接口不求和。任务目录为 apparent size，缓存仍 unsupported；扫描可贡献于观察窗口内 CPU/I/O。
6. 旧 Office Excel 使用旧 identity 与 DeepSeek 配置，独立保留；不与续批 Office 错误路由数据合并。PILOT/其他实验不纳入。
7. 逻辑请求数不等于 HTTP 发送次数；请求耗时不称思考时间；token 与框架 cost 不代表账单。

## 证据与产物

- 新续批：22 次已执行、4 次 not_executed；stop=`critical_measurement_gap`（Coding），global_stop=null。
- 新续批 identity：`reports/resource/LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01/manifest.json` 对应完整 SHA 见冻结文件；原 identity 不覆盖。
- 文件集合、raw manifests、外层清单及历史保护目录均在 manifest/summary 中登记；SHA-256 回读通过。
- 没有将批验收解析异常称为任务失败；本次确认的 Office 问题是冻结 route 与实际单次 config 接线不一致。
- 本分析不修改 raw、批准、冻结身份、原报告或 HTML；不提交 Git。
