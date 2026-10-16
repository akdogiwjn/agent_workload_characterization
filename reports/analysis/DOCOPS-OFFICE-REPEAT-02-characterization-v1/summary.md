# DOCOPS-OFFICE-REPEAT-02 限定行为—资源分析

显式9次、3个固定任务；46逻辑请求、37自主工具、18 bootstrap。finish=9、reward=1=9；配对问题0。旧批和单次Excel不纳入。

## 原始点：阶段与调用窗口

| run | 请求/工具 | attempt s | Agent s | 请求并集 s | bootstrap并集 s | 自主工具并集 s | uncovered s | verifier s | stop s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20261011T104235Z-r0-excel001 | 7/6 | 42.970000 | 29.969887 | 23.422489 | 1.201104 | 5.336966 | 0.009327 | 1.225959 | 10.265671 |
| 20261011T104318Z-r0-ppt008 | 5/4 | 25.270000 | 12.172110 | 7.376924 | 1.153493 | 3.636305 | 0.005388 | 1.342365 | 10.272787 |
| 20261011T104344Z-r0-pdf004 | 4/3 | 21.500000 | 8.419824 | 4.608464 | 1.167051 | 2.640086 | 0.004222 | 1.167545 | 10.381493 |
| 20261011T104406Z-r1-ppt008 | 5/4 | 24.640000 | 11.660896 | 7.059307 | 1.144630 | 3.450629 | 0.006330 | 1.251836 | 10.271334 |
| 20261011T104431Z-r1-pdf004 | 4/3 | 22.050000 | 8.957069 | 5.021325 | 1.300446 | 2.630160 | 0.005138 | 1.299003 | 10.393752 |
| 20261011T104454Z-r1-excel001 | 6/5 | 49.050000 | 36.115955 | 30.368674 | 1.043000 | 4.696151 | 0.008130 | 1.288533 | 10.236682 |
| 20261011T104543Z-r2-pdf004 | 4/3 | 21.160000 | 8.251279 | 4.478660 | 1.225445 | 2.542189 | 0.004985 | 1.223317 | 10.256406 |
| 20261011T104605Z-r2-excel001 | 6/5 | 35.950000 | 22.874867 | 16.694217 | 1.263802 | 4.908998 | 0.007850 | 1.396260 | 10.249221 |
| 20261011T104641Z-r2-ppt008 | 5/4 | 25.880000 | 12.685035 | 7.543610 | 1.306075 | 3.828118 | 0.007233 | 1.335013 | 10.344973 |

请求、工具、bootstrap列为并集，不能在重叠时直接相加；互斥mask分解、overlap及整数ns守恒残差见per_run。uncovered不称思考/等待/框架独占开销。归档只保存marker span，不当成完整归档耗时。

## 共享容器资源原始点

| run | 观测窗 s | 总CPU core-s | setup / Agent / verifier 边界CPU core-s | current / 内核peak / 宿主RSS MiB |
| --- | --- | --- | --- | --- |
| 20261011T104235Z-r0-excel001 | 31.596575 | 6.840446 | 0.030872 / 5.822586 / 0.986988 | 78.828125 / 79.320312 / 159.246094 |
| 20261011T104318Z-r0-ppt008 | 13.867275 | 5.368005 | 0.026042 / 4.223849 / 1.118114 | 58.843750 / 76.812500 / 161.246094 |
| 20261011T104344Z-r0-pdf004 | 9.933848 | 4.270158 | 0.025329 / 3.300820 / 0.944009 | 72.675781 / 80.417969 / 161.246094 |
| 20261011T104406Z-r1-ppt008 | 13.300808 | 5.034718 | 0.029444 / 3.993457 / 1.011817 | 67.960938 / 75.910156 / 161.246094 |
| 20261011T104431Z-r1-pdf004 | 10.625234 | 4.518449 | 0.025962 / 3.432810 / 1.059677 | 78.234375 / 78.234375 / 161.246094 |
| 20261011T104454Z-r1-excel001 | 37.760334 | 6.053172 | 0.022016 / 4.974882 / 1.056274 | 67.132812 / 76.214844 / 161.246094 |
| 20261011T104543Z-r2-pdf004 | 9.860872 | 4.461739 | 0.027396 / 3.423393 / 1.010950 | 64.515625 / 78.398438 / 163.246094 |
| 20261011T104605Z-r2-excel001 | 24.654851 | 6.733122 | 0.026670 / 5.532569 / 1.173883 | 82.937500 / 82.937500 / 163.246094 |
| 20261011T104641Z-r2-ppt008 | 14.417520 | 5.557092 | 0.025880 / 4.420164 / 1.111048 | 65.445312 / 76.937500 / 163.246094 |

完整memory.current点、I/O读写计数器、采样质量、CPU sample partition与工具前后共享变化均在per_run。阶段边界CPU和纯采样CPU分箱使用不同读窗口，不互相替代；跨边界mixed不分摊。内核peak为累计高水位，不是阶段独立峰值，三个内存口径不相加。

## 任务内重复统计

| task | 指标 | 原始三个点 | 有效n | median | IQR |
| --- | --- | --- | --- | --- | --- |
| Excel | request_count | 7.000000, 6.000000, 6.000000 | 3 | 6.000000 | 0.500000 |
| Excel | agent_tool_count | 6.000000, 5.000000, 5.000000 | 3 | 5.000000 | 0.500000 |
| Excel | attempt_wall_s | 42.970000, 49.050000, 35.950000 | 3 | 42.970000 | 6.550000 |
| Excel | agent_wall_s | 29.969887, 36.115955, 22.874867 | 3 | 29.969887 | 6.620544 |
| Excel | request_union_s | 23.422489, 30.368674, 16.694217 | 3 | 23.422489 | 6.837229 |
| Excel | agent_tool_union_s | 5.336966, 4.696151, 4.908998 | 3 | 4.908998 | 0.320408 |
| Excel | cpu_core_s | 6.840446, 6.053172, 6.733122 | 3 | 6.733122 | 0.393637 |
| Excel | agent_boundary_cpu_core_s | 5.822586, 4.974882, 5.532569 | 3 | 5.532569 | 0.423852 |
| Excel | verifier_boundary_cpu_core_s | 0.986988, 1.056274, 1.173883 | 3 | 1.056274 | 0.093448 |
| Excel | memory_current_peak_bytes | 82657280.000000, 70393856.000000, 86966272.000000 | 3 | 82657280.000000 | 8286208.000000 |
| PPT | request_count | 5.000000, 5.000000, 5.000000 | 3 | 5.000000 | 0.000000 |
| PPT | agent_tool_count | 4.000000, 4.000000, 4.000000 | 3 | 4.000000 | 0.000000 |
| PPT | attempt_wall_s | 25.270000, 24.640000, 25.880000 | 3 | 25.270000 | 0.620000 |
| PPT | agent_wall_s | 12.172110, 11.660896, 12.685035 | 3 | 12.172110 | 0.512070 |
| PPT | request_union_s | 7.376924, 7.059307, 7.543610 | 3 | 7.376924 | 0.242151 |
| PPT | agent_tool_union_s | 3.636305, 3.450629, 3.828118 | 3 | 3.636305 | 0.188744 |
| PPT | cpu_core_s | 5.368005, 5.034718, 5.557092 | 3 | 5.368005 | 0.261187 |
| PPT | agent_boundary_cpu_core_s | 4.223849, 3.993457, 4.420164 | 3 | 4.223849 | 0.213354 |
| PPT | verifier_boundary_cpu_core_s | 1.118114, 1.011817, 1.111048 | 3 | 1.111048 | 0.053149 |
| PPT | memory_current_peak_bytes | 61702144.000000, 71262208.000000, 68624384.000000 | 3 | 68624384.000000 | 4780032.000000 |
| PDF | request_count | 4.000000, 4.000000, 4.000000 | 3 | 4.000000 | 0.000000 |
| PDF | agent_tool_count | 3.000000, 3.000000, 3.000000 | 3 | 3.000000 | 0.000000 |
| PDF | attempt_wall_s | 21.500000, 22.050000, 21.160000 | 3 | 21.500000 | 0.445000 |
| PDF | agent_wall_s | 8.419824, 8.957069, 8.251279 | 3 | 8.419824 | 0.352895 |
| PDF | request_union_s | 4.608464, 5.021325, 4.478660 | 3 | 4.608464 | 0.271332 |
| PDF | agent_tool_union_s | 2.640086, 2.630160, 2.542189 | 3 | 2.630160 | 0.048948 |
| PDF | cpu_core_s | 4.270158, 4.518449, 4.461739 | 3 | 4.461739 | 0.124146 |
| PDF | agent_boundary_cpu_core_s | 3.300820, 3.432810, 3.423393 | 3 | 3.423393 | 0.065995 |
| PDF | verifier_boundary_cpu_core_s | 0.944009, 1.059677, 1.010950 | 3 | 1.010950 | 0.057834 |
| PDF | memory_current_peak_bytes | 76206080.000000, 82034688.000000, 67649536.000000 | 3 | 76206080.000000 | 7192576.000000 |

分位数为(n−1)×p线性插值，missing不填零，n由每个指标独立确定；三个repeat不是三个task。

## 有限观察与证据

- Excel attempt wall原始范围35.950–49.050s；最大与最小run的Agent阶段差13.241088s，请求并集差13.674457s，自主工具并集差-0.212847s。这里只定位观测差异，不解释模型慢、缓存或因果。
  保存的自主工具序列：r0: copy_file → xlsx_read_sheet → xlsx_read_sheet → xlsx_set_formula → xlsx_set_formula → xlsx_read_sheet → finish；r1: xlsx_read_sheet → copy_file → xlsx_set_formula → xlsx_set_formula → xlsx_read_sheet → finish；r2: xlsx_read_sheet → copy_file → xlsx_set_formula → xlsx_set_formula → xlsx_read_sheet → finish
  请求并集/Agent观测窗口逐run比例median=78.153%（n=3），不是推理时间占比。Agent共享边界CPU median=5.532569、verifier=1.056274core-s；这些窗口共现不说明单工具独占成本。
- PPT attempt wall原始范围24.640–25.880s；最大与最小run的Agent阶段差1.024139s，请求并集差0.484303s，自主工具并集差0.377489s。这里只定位观测差异，不解释模型慢、缓存或因果。
  保存的自主工具序列：r0: copy_file → ppt_list_slides → ppt_replace_text → ppt_list_slides → finish；r1: copy_file → ppt_list_slides → ppt_replace_text → ppt_list_slides → finish；r2: copy_file → ppt_list_slides → ppt_replace_text → ppt_list_slides → finish
  请求并集/Agent观测窗口逐run比例median=60.538%（n=3），不是推理时间占比。Agent共享边界CPU median=4.223849、verifier=1.111048core-s；这些窗口共现不说明单工具独占成本。
- PDF attempt wall原始范围21.160–22.050s；最大与最小run的Agent阶段差0.705790s，请求并集差0.542665s，自主工具并集差0.087970s。这里只定位观测差异，不解释模型慢、缓存或因果。
  保存的自主工具序列：r0: copy_file → pdf_reorder_pages → inspect_document → finish；r1: copy_file → pdf_reorder_pages → inspect_document → finish；r2: copy_file → pdf_reorder_pages → inspect_document → finish
  请求并集/Agent观测窗口逐run比例median=54.734%（n=3），不是推理时间占比。Agent共享边界CPU median=3.423393、verifier=1.010950core-s；这些窗口共现不说明单工具独占成本。
- Agent区间互斥时间分解残差范围0–0ns；保存请求与工具重叠并集范围0.000000–0.000000s；不是通过假定无重叠得到。
- 调用边界mixed采样区间包含各run观测CPU的42.215%–63.302%；不将这部分均匀摊给请求或工具。调用分箱使用整个资源采样窗口，uncovered还可能包含setup/verifier，不能与Agent时间分解的uncovered混用。
- bootstrap失败窗口原始wall点：0.997828s, 0.970350s, 1.135901s；窗口内共享容器CPU变化：0.928511core-s, 0.844926core-s, 0.988125core-s。失败已被计时和记录，不代表没有资源变化。

## PPT bootstrap异常

独立工具终态确认3次ok=false。第一及后续保存请求包含AttributeError返回；按返回SHA与工具终态关联，而非位置强配。后续自主ppt_list_slides / ppt_replace_text及finish均有保存事件，verifier均完成。setup完成≠bootstrap全部成功。

Agent bootstrap -> project runtime dispatch -> official tool_inspect_document .pptx branch -> runtime catches exception class -> Agent saves false payload and continues
prs.slides[:max_items] in document_tools_runtime.py; local container python-pptx implementation/traceback not archived; exact inner raising attribute unconfirmed
initial PPT document inspection yielded no successful inspection payload; failure was supplied to subsequent requests; later ppt_list_slides/text edit/finish observed
counterfactual path, extra requests/cost/quality impact and deeper dependency stack are unknown; reward=1 does not establish no impact

没有保存内部traceback或容器内python-pptx源文件，不能把可疑切片表达式升级为已证实的具体抛错行。本轮不执行工具或依赖重现，也不修复运行时。

## 边界与下一步

- No transport hook: actual HTTP tries unknown; usage and cost=0 are not bills.
- Resource read timestamps precede event timestamps; offsets saved; tool windows are shared-scope changes, not exclusive cost.
- 0.5s periodic sampling undercovers short calls; boundary/mixed bins retained, no interpolation.
- Three repetitions per fixed task, not nine independent tasks or representative Office population.
- ARM64 adaptation not byte-equivalent official amd64 environment; alias not immutable model pin.
- No CPU hotspots, remote inference cost, thinking time, causal effects or rankings; old batch/Excel smoke excluded.

本批限定分析完成；下一步唯一建议：对PPT inspection切片路径及固定依赖接口进行独立离线诊断/修复评审，保留这批历史错误，不以reward=1抹去。无需为了分析自动扩样或恢复CPU-02/Replay。

机器可读结果：[summary.json](summary.json)、[per_run.jsonl](per_run.jsonl)、[manifest.json](manifest.json)。
