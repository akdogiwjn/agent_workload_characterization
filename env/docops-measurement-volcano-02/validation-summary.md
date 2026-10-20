# 扫描修复与三链单次验证集中收尾

正式attempt：3，未执行：0，补跑：0，网关探针：0。

|链路|任务|run_id|identity|实际响应模型|测量完整性|任务结果|终止|wall|CPU|内存|I/O|网络scope|磁盘占用|清理|归档|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|Office|atomic__excel_001_budget_bucket_totals_seed|20261016T143948Z-excel001|15732b6a4202cf967895050f16c940d7d78f6508969f74539ad1a8a81763ec89|deepseek-v4-flash-ga-260731 ×5；deepseek-v4-flash-0731 ×3|主项complete；supplement aggregate partial（cache unsupported）|reward=1|finish|101.830s|7.773932 core-s（88.533s采样窗）|current峰66785280／内核peak 78888960 B|0/40960 B（cgroup读/写）|共享宿主netns逐接口；非任务/API专属|`/root/submission`：0→6629 B|容器删除、任务镜像保留确认|SHA/文件集通过；入口RC=0|
|Coding|django__django-16485|20261016T144518Z-django16485-91776c|0930d98985a5a5974db684a05bbb39fb777f84c5bc453de959f09ed812ee914f|deepseek-v4-flash-0731 ×4；deepseek-v4-flash-ga-260731 ×16|主项complete；supplement aggregate partial（cache unsupported）|resolved=true；execution/evaluation/archive=ok|Submitted|138.612s|Agent 14.268578/verifier 3.560612 core-s（各自边界窗）|Agent current采样峰816259072／内核peak 1042989056；verifier 79110144／79851520 B|Agent 374398976/49152；verifier 7303168/1699840 B（cgroup读/写）|共享宿主netns逐接口；非任务/API专属|`/testbed` Agent：332749843→337624112 B；verifier：332749843→337364093 B|容器删除、任务镜像保留确认|SHA/文件集通过；入口RC=7|
|Assistant|send_message_with_contact_content_cellular_off|20261016T145056Z-tsbvolcano01|2d7b147e74c37cbaefbb997ff51f627be7691fb4397f8571aceb20c962c8fef9|deepseek-v4-flash-0731 ×2；deepseek-v4-flash-ga-260731 ×5|主项complete；supplement aggregate partial（cache unsupported）|官方similarity=0.9484251274276947；不自设成功阈值|user_end_conversation|19.808s|609.08 process CPU-s（19.000s采样窗）|RSS采样峰1494155264 B；不是内核peak|read/write_bytes 0/118784 B；rchar/wchar 42906340/114365 B|共享宿主netns逐接口；非任务/API专属|内存场景not_applicable；宿主输出另列|worker/采样器回收确认|SHA/文件集通过；入口RC=0|

修复仅涉及Office采集handle显式cwd=/、共享扫描包装的失败诊断和Office02独立profile/薄入口。未改变Coding默认/testbed、网关、模型、依赖、任务或预算。

无模型容器检查首次通过，0.742s，合成文件增长32768B，固定镜像身份与架构匹配，容器删除且镜像保留。定向测试38项最终通过（扫描4、共享测量26、清理8）；首轮一个测试错误是argparse以SystemExit(2)拒绝旧旗标，已修正测试断言，未放宽门禁。

Coding入口真实返回7：入口要求archive_status==complete，而共享runner的成功值为ok。raw归档13项SHA及文件集合、外层7项bytes/SHA均回读通过，cleanup_status=ok。未修改已启动attempt的实现、报告或返回码，也未重跑；不是已证明的实际归档失败。

Assistant共有Agent/User逻辑请求6/1，5次Agent业务工具（含一次已保存ConnectionError工具返回）、1次用户end_conversation；6个执行batch与一次system setup边界。项目层尝试7；实际HTTP次数unknown。Office8请求、7自主工具、2bootstrap；Coding20请求、30工具，末次工具以已保存的Submitted控制流异常结束（29 closed、1 error），不是伪造的普通成功返回。全部调用配对与末次终态已核验，终止后无新增请求。

宿主日志/输出占用与任务目录分列，完整原始边界在[validation-closeout.json](validation-closeout.json)。cache无任务专属注册路径，保持unsupported/null，故原始supplement aggregate仍partial。网络只覆盖共享netns接口，不是任务/API专属字节；未新增HTTP正文/TLS计量。CPU为共享容器/worker窗口，不是单工具或远端模型CPU；内存不同指标不相加。不同CPU窗口不强行相等。Assistant阶段壁钟/CPU见JSON，初始化及evaluator不统称任务工具成本。

旧Office01的41个受保护文件及文件集合、3份修改前源码快照回读不变；旧运行缺完整错误输出，不将已确认cwd缺陷宣布为其唯一根因。Coding/Assistant仅保留并更新本次未批准准备身份，未改已执行批次冻结值。历史输入代码路径允许漂移，快照留存，不改旧manifest。

完成后停止；未更新HTML、未提交Git、未宣布Gate通过；CPU-02与Replay仍暂停。
