# 三类固定任务：续批完成后的合并复核

## 批次与样本边界

完整续批执行 12/12 个替换槽位，批 wall 1374.0s；未执行 0，验收错误 0。
合并后的预定研究槽位为 27 个：Coding 9、Office 9、Assistant 9，每个固定任务×round 三个观察点。原始错路由 Office 8 次仍保留在 35 次累计启动记录中，但单独标记并排除正常 Office 任务统计。原 Excel 1 次、Coding 5 次、Assistant 9 次不重跑。

本批是固定配置下的重复描述，不是 27 个独立任务，不代表类别总体；各链路指标按任务分别汇总。分位数为 `(n−1)×p` 线性插值，各指标使用自己的有效 n。

## 任务级原始点与摘要

|链路|固定任务|指标|原始点（有效n）|median|IQR|
|---|---|---|---|---:|---:|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`agent_tools`|n=3: [4, 4, 5]|4|0.5|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`attempt_wall_s`|n=3: [18.6049, 21.3686, 22.5051]|21.369|1.9501|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`bootstrap_tools`|n=3: [0, 0, 0]|0|0|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`logical_requests`|n=3: [6, 6, 7]|6|0.5|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`memory_sampled_peak_bytes::worker`|n=3: [1.48395e+09, 1.48895e+09, 1.51504e+09]|1.4889e+09|1.5544e+07|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`observed_cpu_s::worker`|n=3: [368.98, 499.33, 576.57]|499.33|103.8|
|Assistant|`add_reminder_content_and_week_delta_and_time`|`task_result_scalar`|n=3: [1, 1, 1]|1|0|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`agent_tools`|n=3: [6, 7, 7]|7|0.5|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`attempt_wall_s`|n=3: [39.7073, 42.708, 44.5624]|42.708|2.4275|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`bootstrap_tools`|n=3: [0, 0, 0]|0|0|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`logical_requests`|n=3: [8, 8, 9]|8|0.5|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`memory_sampled_peak_bytes::worker`|n=3: [1.66737e+09, 1.77088e+09, 1.81059e+09]|1.7709e+09|7.161e+07|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`observed_cpu_s::worker`|n=3: [1120.95, 1454.94, 1476.55]|1454.9|177.8|
|Assistant|`modify_contact_with_message_recency_multiple_user_turn`|`task_result_scalar`|n=3: [0.974716, 0.974716, 0.996774]|0.97472|0.011029|
|Assistant|`send_message_with_contact_content_cellular_off`|`agent_tools`|n=3: [4, 5, 5]|5|0.5|
|Assistant|`send_message_with_contact_content_cellular_off`|`attempt_wall_s`|n=3: [18.7804, 20.7968, 22.155]|20.797|1.6873|
|Assistant|`send_message_with_contact_content_cellular_off`|`bootstrap_tools`|n=3: [0, 0, 0]|0|0|
|Assistant|`send_message_with_contact_content_cellular_off`|`logical_requests`|n=3: [6, 7, 7]|7|0.5|
|Assistant|`send_message_with_contact_content_cellular_off`|`memory_sampled_peak_bytes::worker`|n=3: [1.51271e+09, 1.55107e+09, 1.62086e+09]|1.5511e+09|5.4073e+07|
|Assistant|`send_message_with_contact_content_cellular_off`|`observed_cpu_s::worker`|n=3: [525.42, 537.35, 586.52]|537.35|30.55|
|Assistant|`send_message_with_contact_content_cellular_off`|`task_result_scalar`|n=3: [0.940148, 0.945507, 0.946944]|0.94551|0.0033983|
|Coding|`astropy__astropy-13236`|`agent_tools`|n=3: [41, 49, 50]|49|4.5|
|Coding|`astropy__astropy-13236`|`attempt_wall_s`|n=3: [151.597, 160.805, 176.73]|160.8|12.567|
|Coding|`astropy__astropy-13236`|`bootstrap_tools`|n=3: [0, 0, 0]|0|0|
|Coding|`astropy__astropy-13236`|`logical_requests`|n=3: [30, 30, 30]|30|0|
|Coding|`astropy__astropy-13236`|`memory_sampled_peak_bytes::agent_container`|n=3: [8.43366e+07, 2.8049e+08, 2.83783e+08]|2.8049e+08|9.9723e+07|
|Coding|`astropy__astropy-13236`|`observed_cpu_s::agent_container`|n=3: [21.7554, 28.4591, 32.2473]|28.459|5.2459|
|Coding|`astropy__astropy-13236`|`task_result_scalar`|n=3: [1, 1, 1]|1|0|
|Coding|`astropy__astropy-13398`|`agent_tools`|n=3: [48, 55, 66]|55|9|
|Coding|`astropy__astropy-13398`|`attempt_wall_s`|n=3: [145.974, 208.265, 252.895]|208.27|53.46|
|Coding|`astropy__astropy-13398`|`bootstrap_tools`|n=3: [0, 0, 0]|0|0|
|Coding|`astropy__astropy-13398`|`logical_requests`|n=3: [30, 30, 30]|30|0|
|Coding|`astropy__astropy-13398`|`memory_sampled_peak_bytes::agent_container`|n=3: [3.20307e+07, 4.73211e+07, 4.94592e+07]|4.7321e+07|8.7142e+06|
|Coding|`astropy__astropy-13398`|`observed_cpu_s::agent_container`|n=3: [10.2481, 13.9149, 16.3121]|13.915|3.032|
|Coding|`astropy__astropy-13398`|`task_result_scalar`|n=2: [0, 0]|0|0|
|Coding|`django__django-16485`|`agent_tools`|n=3: [27, 32, 34]|32|3.5|
|Coding|`django__django-16485`|`attempt_wall_s`|n=3: [142.181, 161.032, 163.487]|161.03|10.653|
|Coding|`django__django-16485`|`bootstrap_tools`|n=3: [0, 0, 0]|0|0|
|Coding|`django__django-16485`|`logical_requests`|n=3: [18, 26, 30]|26|6|
|Coding|`django__django-16485`|`memory_sampled_peak_bytes::agent_container`|n=3: [7.06191e+07, 5.81427e+08, 1.42042e+09]|5.8143e+08|6.749e+08|
|Coding|`django__django-16485`|`observed_cpu_s::agent_container`|n=3: [8.16415, 13.2868, 18.5368]|13.287|5.1863|
|Coding|`django__django-16485`|`task_result_scalar`|n=3: [1, 1, 1]|1|0|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`agent_tools`|n=3: [7, 10, 11]|10|2|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`attempt_wall_s`|n=3: [150.49, 207.26, 288.32]|207.26|68.915|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`bootstrap_tools`|n=3: [2, 2, 2]|2|0|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`logical_requests`|n=3: [8, 11, 12]|11|2|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`memory_sampled_peak_bytes::container`|n=3: [6.78461e+07, 7.31341e+07, 8.04168e+07]|7.3134e+07|6.2853e+06|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`observed_cpu_s::container`|n=3: [7.30292, 10.481, 12.0002]|10.481|2.3487|
|Office|`atomic__excel_001_budget_bucket_totals_seed`|`task_result_scalar`|n=3: [1, 1, 1]|1|0|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`agent_tools`|n=3: [3, 3, 3]|3|0|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`attempt_wall_s`|n=3: [28.88, 29.96, 31.73]|29.96|1.425|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`bootstrap_tools`|n=3: [2, 2, 2]|2|0|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`logical_requests`|n=3: [4, 4, 4]|4|0|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`memory_sampled_peak_bytes::container`|n=3: [7.08444e+07, 8.3329e+07, 8.35502e+07]|8.3329e+07|6.3529e+06|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`observed_cpu_s::container`|n=3: [4.33683, 4.71871, 4.78443]|4.7187|0.2238|
|Office|`atomic__pdf_004_audit_pages_reorder_seed`|`task_result_scalar`|n=3: [1, 1, 1]|1|0|
|Office|`atomic__ppt_008_bullet_editing_seed`|`agent_tools`|n=3: [4, 4, 4]|4|0|
|Office|`atomic__ppt_008_bullet_editing_seed`|`attempt_wall_s`|n=3: [37.39, 38.91, 40.21]|38.91|1.41|
|Office|`atomic__ppt_008_bullet_editing_seed`|`bootstrap_tools`|n=3: [2, 2, 2]|2|0|
|Office|`atomic__ppt_008_bullet_editing_seed`|`logical_requests`|n=3: [5, 5, 5]|5|0|
|Office|`atomic__ppt_008_bullet_editing_seed`|`memory_sampled_peak_bytes::container`|n=3: [6.64125e+07, 7.31382e+07, 7.67058e+07]|7.3138e+07|5.1466e+06|
|Office|`atomic__ppt_008_bullet_editing_seed`|`observed_cpu_s::container`|n=3: [5.35071, 5.39738, 5.42875]|5.3974|0.039021|
|Office|`atomic__ppt_008_bullet_editing_seed`|`task_result_scalar`|n=3: [1, 1, 1]|1|0|

## 每次运行

|链路|round|任务|run_id|官方结果|终止|测量|清理/归档|
|---|---:|---|---|---|---|---|---|
|Office|0|`atomic__excel_001_budget_bucket_totals_seed`|`20261016T182559Z-09-r0-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed+image_retained/raw manifest/hash verified|
|Coding|0|`django__django-16485`|`20261017T023247Z-00-r0-coding`|True|Submitted|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|0|`astropy__astropy-13236`|`20261017T023534Z-01-r0-coding`|True|LimitsExceeded|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|0|`astropy__astropy-13398`|`20261017T023817Z-02-r0-coding`|False|LimitsExceeded|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|1|`astropy__astropy-13236`|`20261017T024149Z-03-r1-coding`|True|LimitsExceeded|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|1|`astropy__astropy-13398`|`20261017T024449Z-04-r1-coding`|None|LimitsExceeded|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|0|`send_message_with_contact_content_cellular_off`|`20261017T025049Z-17-r0-assistant`|0.9401476194637091|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|0|`add_reminder_content_and_week_delta_and_time`|`20261017T025108Z-18-r0-assistant`|1.0|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|0|`modify_contact_with_message_recency_multiple_user_turn`|`20261017T025127Z-19-r0-assistant`|0.9967736293532093|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|1|`add_reminder_content_and_week_delta_and_time`|`20261017T025213Z-20-r1-assistant`|1.0|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|1|`modify_contact_with_message_recency_multiple_user_turn`|`20261017T025234Z-21-r1-assistant`|0.9747160936387214|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|1|`send_message_with_contact_content_cellular_off`|`20261017T025315Z-22-r1-assistant`|0.9469442875374467|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|2|`modify_contact_with_message_recency_multiple_user_turn`|`20261017T025336Z-23-r2-assistant`|0.9747160936387214|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|2|`send_message_with_contact_content_cellular_off`|`20261017T025420Z-24-r2-assistant`|0.9455066862191938|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Assistant|2|`add_reminder_content_and_week_delta_and_time`|`20261017T025442Z-25-r2-assistant`|1.0|{'conversation_active': False, 'user_end_conversation_executed': True, 'reason': 'user_end_conversation'}|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|1|`django__django-16485`|`20261017T041030Z-00-r1-coding`|True|LimitsExceeded|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|2|`astropy__astropy-13398`|`20261017T041313Z-01-r2-coding`|False|LimitsExceeded|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|2|`django__django-16485`|`20261017T041729Z-02-r2-coding`|True|Submitted|only the saved scope windows; not the whole attempt|confirmed/verified|
|Coding|2|`astropy__astropy-13236`|`20261017T041954Z-03-r2-coding`|True|LimitsExceeded|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|0|`atomic__ppt_008_bullet_editing_seed`|`20261017T042227Z-04-r0-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|0|`atomic__pdf_004_audit_pages_reorder_seed`|`20261017T042308Z-05-r0-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|1|`atomic__ppt_008_bullet_editing_seed`|`20261017T042338Z-06-r1-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|1|`atomic__pdf_004_audit_pages_reorder_seed`|`20261017T042417Z-07-r1-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|1|`atomic__excel_001_budget_bucket_totals_seed`|`20261017T042447Z-08-r1-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|2|`atomic__pdf_004_audit_pages_reorder_seed`|`20261017T042720Z-09-r2-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|2|`atomic__excel_001_budget_bucket_totals_seed`|`20261017T042753Z-10-r2-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|
|Office|2|`atomic__ppt_008_bullet_editing_seed`|`20261017T043244Z-11-r2-office`|1.0|finish|only the saved scope windows; not the whole attempt|confirmed/verified|

## 资源图与作图数据

- Office `atomic__excel_001_budget_bucket_totals_seed` r0: [SVG](figures/20261016T182559Z-09-r0-office.svg) · [CSV](series/20261016T182559Z-09-r0-office.csv)
- Coding `django__django-16485` r0: [SVG](figures/20261017T023247Z-00-r0-coding.svg) · [CSV](series/20261017T023247Z-00-r0-coding.csv)
- Coding `astropy__astropy-13236` r0: [SVG](figures/20261017T023534Z-01-r0-coding.svg) · [CSV](series/20261017T023534Z-01-r0-coding.csv)
- Coding `astropy__astropy-13398` r0: [SVG](figures/20261017T023817Z-02-r0-coding.svg) · [CSV](series/20261017T023817Z-02-r0-coding.csv)
- Coding `astropy__astropy-13236` r1: [SVG](figures/20261017T024149Z-03-r1-coding.svg) · [CSV](series/20261017T024149Z-03-r1-coding.csv)
- Coding `astropy__astropy-13398` r1: [SVG](figures/20261017T024449Z-04-r1-coding.svg) · [CSV](series/20261017T024449Z-04-r1-coding.csv)
- Assistant `send_message_with_contact_content_cellular_off` r0: [SVG](figures/20261017T025049Z-17-r0-assistant.svg) · [CSV](series/20261017T025049Z-17-r0-assistant.csv)
- Assistant `add_reminder_content_and_week_delta_and_time` r0: [SVG](figures/20261017T025108Z-18-r0-assistant.svg) · [CSV](series/20261017T025108Z-18-r0-assistant.csv)
- Assistant `modify_contact_with_message_recency_multiple_user_turn` r0: [SVG](figures/20261017T025127Z-19-r0-assistant.svg) · [CSV](series/20261017T025127Z-19-r0-assistant.csv)
- Assistant `add_reminder_content_and_week_delta_and_time` r1: [SVG](figures/20261017T025213Z-20-r1-assistant.svg) · [CSV](series/20261017T025213Z-20-r1-assistant.csv)
- Assistant `modify_contact_with_message_recency_multiple_user_turn` r1: [SVG](figures/20261017T025234Z-21-r1-assistant.svg) · [CSV](series/20261017T025234Z-21-r1-assistant.csv)
- Assistant `send_message_with_contact_content_cellular_off` r1: [SVG](figures/20261017T025315Z-22-r1-assistant.svg) · [CSV](series/20261017T025315Z-22-r1-assistant.csv)
- Assistant `modify_contact_with_message_recency_multiple_user_turn` r2: [SVG](figures/20261017T025336Z-23-r2-assistant.svg) · [CSV](series/20261017T025336Z-23-r2-assistant.csv)
- Assistant `send_message_with_contact_content_cellular_off` r2: [SVG](figures/20261017T025420Z-24-r2-assistant.svg) · [CSV](series/20261017T025420Z-24-r2-assistant.csv)
- Assistant `add_reminder_content_and_week_delta_and_time` r2: [SVG](figures/20261017T025442Z-25-r2-assistant.svg) · [CSV](series/20261017T025442Z-25-r2-assistant.csv)
- Coding `django__django-16485` r1: [SVG](figures/20261017T041030Z-00-r1-coding.svg) · [CSV](series/20261017T041030Z-00-r1-coding.csv)
- Coding `astropy__astropy-13398` r2: [SVG](figures/20261017T041313Z-01-r2-coding.svg) · [CSV](series/20261017T041313Z-01-r2-coding.csv)
- Coding `django__django-16485` r2: [SVG](figures/20261017T041729Z-02-r2-coding.svg) · [CSV](series/20261017T041729Z-02-r2-coding.csv)
- Coding `astropy__astropy-13236` r2: [SVG](figures/20261017T041954Z-03-r2-coding.svg) · [CSV](series/20261017T041954Z-03-r2-coding.csv)
- Office `atomic__ppt_008_bullet_editing_seed` r0: [SVG](figures/20261017T042227Z-04-r0-office.svg) · [CSV](series/20261017T042227Z-04-r0-office.csv)
- Office `atomic__pdf_004_audit_pages_reorder_seed` r0: [SVG](figures/20261017T042308Z-05-r0-office.svg) · [CSV](series/20261017T042308Z-05-r0-office.csv)
- Office `atomic__ppt_008_bullet_editing_seed` r1: [SVG](figures/20261017T042338Z-06-r1-office.svg) · [CSV](series/20261017T042338Z-06-r1-office.csv)
- Office `atomic__pdf_004_audit_pages_reorder_seed` r1: [SVG](figures/20261017T042417Z-07-r1-office.svg) · [CSV](series/20261017T042417Z-07-r1-office.csv)
- Office `atomic__excel_001_budget_bucket_totals_seed` r1: [SVG](figures/20261017T042447Z-08-r1-office.svg) · [CSV](series/20261017T042447Z-08-r1-office.csv)
- Office `atomic__pdf_004_audit_pages_reorder_seed` r2: [SVG](figures/20261017T042720Z-09-r2-office.svg) · [CSV](series/20261017T042720Z-09-r2-office.csv)
- Office `atomic__excel_001_budget_bucket_totals_seed` r2: [SVG](figures/20261017T042753Z-10-r2-office.svg) · [CSV](series/20261017T042753Z-10-r2-office.csv)
- Office `atomic__ppt_008_bullet_editing_seed` r2: [SVG](figures/20261017T043244Z-11-r2-office.svg) · [CSV](series/20261017T043244Z-11-r2-office.csv)

## 结论边界

1. 本次 12 个替代槽位与历史 15 个可用观察在固定任务、请求模型、Volcano 路由、任务工具与预算上可按登记配置合并；执行入口仅增加批次 profile/namespace/替换映射，底层 Coding runner 配置一致，Office 原 Excel 绑定检查为可比。
2. 八个历史 Office 错路由 attempt 是真实已启动运行和资源记录，但不是预期 Volcano 路由下的任务结果；原记录和花费信息未改写。
3. 原 Coding no_candidate 路径没有运行 verifier，verifier资源与目录占用保持 not_applicable；不把它当采集故障。
4. 容器/进程 CPU、memory.current/RSS、内核 peak、I/O 与宿主输出目录分别保留；共享 netns 是共享网络命名空间逐接口观测，不是任务/API专属流量，虚拟接口不相加。
5. 工具/请求区间和资源窗口只作共现，不称思考时间、不归因单工具独占资源。HTTP传输次数与账单仍 unknown；token 和框架 cost=0 不是账单证据。
6. 目录大小为 apparent bytes；共享缓存 unsupported；宿主日志目录扫描在最终归档写入前完成，不能作为最终归档总大小。

## 验收与保护

批后固定镜像只读核验：7/7 个镜像完整 ID、linux/arm64 与适用的 registry digest 匹配；逐镜像结果见 `image-retention.json`。

独立验收核对 35 个 raw manifest、运行报告/marker、批准与identity关系；新批 12 个目录无额外/fake run，文件集合与 SHA-256 一致。v1/v2报告和历史原始数据由冻结前保护快照核验；v2所绑定而当前已修改的源码以本批 `source-before/` 字节快照复核，未改写v2 manifest。

v2 的八次 Office 错路由结论保留为历史错误路径证据；本版用 12 次明确替换及 4 次 Coding 未执行槽位完成 27 个预定槽位，不覆盖旧批身份。
