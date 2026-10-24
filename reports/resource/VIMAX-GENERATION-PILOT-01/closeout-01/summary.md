# ViMax 首次真实任务停止与收尾

本次已停止且容器不存在；宿主未发现对应运行器/driver/Agent残留，使用镜像保留。停止检查时，原运行器已经因LLM调用门禁结束并完成清理；本轮没有再发停止信号、模型请求或重跑。

## 任务结果与终止

**未生成图片或视频，没有完成八镜头任务；评分未执行，reward=null，不是0分。** 原始 `ok=true` 仅指完成握手，Agent进程返回0不代表任务成功。最终error/done明确为 `llm_calls cap=80; already_sent=80`。原始记录保持不变。

80条LLM逻辑开始记录：外层27、内部53；68条保存闭合返回，12条内部开始记录未闭合，保持unknown，不能当成12次HTTP失败或零费用。另27条项目attempt记录与外层调用重叠，不加总为107次逻辑请求。实际HTTP次数unknown。

已保存闭合返回usage：输入761,124、输出172,774、合计933,898 tokens；不是全部请求的完整账单。登记软门禁实际针对输出token，不是输入输出合计；输出累计172,774，不能把总量933,898与500,000输出阈值混为一谈。费用unknown。

原生事件260条，工具开始/返回均44条：规划12次失败、3次成功返回（不代表完整可渲染）；read_file 8、list_files 1、glob_files 3次成功；write_json 12、run_shell 5次失败。可见解析异常、camera tree长度不符、修订目标不存在及重复规划；没有render工具调用。尚未做唯一根因诊断，不擅自断言模型不支持或需要更多预算。

## 本地资源（仅规划/恢复路径）

- attempt wall：3028.907s；资源边界窗：3025.117s，不混用。
- CPU：5.804161 core-s，平均0.001919 core；远端模型计算不在本机范围。
- 周期采样6047点，中位间隔0.500300s，最大0.501279s，无非递增周期。
- memory.current采样峰：136,265,728 B；内核peak：136,450,048 B，分列不相加。
- cgroup v1 throttle I/O：读0、写999,424 B，原始状态支持真零；不代表完整文件系统流量。
- 网络是共享宿主netns；图只展示eno1原始累计计数，不是任务/API字节，且历史未保存netns inode。
- 工作目录前后10,042→745,603 B，包括输入、轨迹和规划文件，不是视频产物占用或最终归档大小。

原始baseline提示 `baseline_cpu_unreadable:None` 未删改；实际v1起止 `cpuacct.usage` 都是有效读取，提示不能覆盖读数证据。

## 证据入口

- [机器报告](run-report.json)
- [停止核验](stop-verification.json)
- [资源曲线](resource-curves.svg)
- [资源点CSV](resource-samples.csv)
- [共享网络选定接口CSV](network-selected-interface.csv)
- [原始文件清单](raw-manifest.json)
- [输入/代码/输出清单](manifest.json)

本次没有修复执行代码、补跑、调用verifier、更新HTML或提交Git。下一步只能先离线诊断规划输出/解析与原生工具失败，不自动续跑。本报告是收尾记录，不是新执行批准。
