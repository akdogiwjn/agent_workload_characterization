# 本轮命令与复现边界

在项目根目录执行。`plan.json`中的147个公开URL来自旧固定计划中尚未存在于旧raw的对象；没有遍历新增submission。实际下载通过本机`source_metadata/download.curl`配置记录各项url/output/dump-header，使用4路并行、重试、失败退出及超时限制。

```bash
curl -fL --parallel --parallel-immediate --parallel-max 4 --config data/catalog/public_trace_acquisition/SWEBENCH-GAP-20261023/source_metadata/download.curl
python3 -B scripts/swebench_coverage_results.py --finalize-gap data/catalog/public_trace_acquisition/SWEBENCH-GAP-20261023/plan.json
python3 -B -m unittest tests.test_swebench_coverage_results -v
python3 -B scripts/swebench_coverage_results.py --gap-manifest data/catalog/public_trace_acquisition/SWEBENCH-GAP-20261023/manifest.json --output-dir reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1
python3 -B scripts/swebench_coverage_findings.py
```

下载及finalize已执行完成，不应对已封存目录重复运行。finalize拒绝覆盖manifest或已有最终文件。下载配置与HTTP头在本机归档，不随代码仓库分发；重新获取时应从公开URL写入另一个独立目录并记录新的时间、ETag和SHA256，不能冒用本轮身份。

只复现离线分析时，需完整本地旧raw、历史报告、固定索引和本轮封存文件，指定尚不存在的新输出目录，例如`--output-dir /tmp/SWEBENCH-COVERAGE-RESULTS-reproduce`。派生发现脚本对固定报告目录执行，并拒绝覆盖已有findings。代码仓库副本不包含全部原始数据。
