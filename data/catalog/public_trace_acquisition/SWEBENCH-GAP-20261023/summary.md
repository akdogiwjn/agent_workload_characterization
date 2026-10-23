# SWE-bench Sonar 固定清单缺口补齐

仅补充 `test/20251219_sonar-foundation-agent_claude-opus-4-5` 在旧固定计划中的147个缺失对象，39,377,587字节。原有2,147个对象保留原位；新增文件存放在独立的 `data/raw/public/swebench_gap/` 目录。累计2,294个任务及每文件字节数与旧计划中的该组清单完全相同。

- 原计划：[SWEBENCH-SUPPLEMENT-20261006/plan.json](../SWEBENCH-SUPPLEMENT-20261006/plan.json)，SHA256 `cf45105108f3df36999b840fa6cf9e9f801f0131f15a15dc11802792a651a83f`。
- 固定Git元数据索引：`40f164d5b8f1d249bf95a6df8b74b577fd8e519d`。
- 本轮逐对象URL、字节数与目标路径：[plan.json](plan.json)。
- 下载后封存的SHA256、HTTP头摘要及ETag：[manifest.json](manifest.json)。
- 校验：全部HTTP 200；旧listing字节数相符；当前单part S3 ETag MD5与内容相符；JSON可解析；本地SHA256登记。整个批次预校验通过后才将`.part`改名封存。

Git索引固定不代表S3字节不可变；旧listing没有给出历史SHA256，因此不能声称本轮取得了该commit时点完全相同的历史内容。ETag是本轮下载时的证据。

不新增其他submission，不执行Agent、保存命令、patch、benchmark或模型。历史raw/manifest/分析报告不变。下载配置与HTTP头保留本机；原始数据及这些下载元数据不随代码仓库发布。

[下载和分析命令](commands.md) · [分析发现](../../../../reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1/findings.md)
