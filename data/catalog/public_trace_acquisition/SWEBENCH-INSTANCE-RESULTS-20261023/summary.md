# SWE-bench逐任务评价文件补采集

对先前已登记的41组submission逐组、完整分页列举同名公开S3 `logs/` 命名空间；补下载全部逐任务 `report.json`、4个旧格式组的评测日志、可取得的 `all_preds.jsonl`，并读取缺报告任务的39份 `run_instance.log`。

主批次20,097个文件、510,938,578字节：18,306份逐任务报告、1,716份旧评测日志、36份预测文件、39份诊断日志。另检查空报告的配套输出：74份在上游也是0字节，唯一非空的一份为39字节，已另行下载并确认内容为1800秒超时。合计20,098个文件、510,938,617字节。

下载内容位于独立的 `data/raw/public/swebench_instance_results/SWEBENCH-INSTANCE-RESULTS-20261023/`，不覆盖任何历史raw或报告。

- [discovery.json](discovery.json)：41组、逐页listing摘要及原分析范围。初始格式识别只作探测；最终选取按下列plan扫描完整原始listing，包括KGCompass及旧格式日志。
- [plan.json](plan.json)：主批次全部报告/日志/预测的URL、预期字节、ETag。
- [supplement-plan.json](supplement-plan.json)：39份缺报告任务的诊断日志。
- [manifest.json](manifest.json)：主批次逐文件SHA256、HTTP头摘要、完整listing及预测文件HEAD记录。
- [附加测试输出manifest](../../../../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/additional-source-manifest.json)：额外39字节文件与listing/HTTP/MD5/SHA256证据。
- [完整分析与剩余来源缺口](../../../../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/summary.md)。

HTTP均为200，大小与完整listing或预测文件HEAD一致，下载ETag与探测ETag一致；单part ETag检查MD5，并登记本地SHA256。75份报告在上游就是零字节，按原字节封存，不冒充有效JSON或失败下载。Git元数据固定于旧索引，S3本轮为当前可变快照，不能声称是同一历史时点的不可变字节。

代码、清单与汇总可发布；raw、下载HTTP头、listing响应等正文保留本机，不随代码仓库分发。没有执行Agent、模型、保存命令、patch、benchmark或verifier。

[命令与复现](commands.md)
