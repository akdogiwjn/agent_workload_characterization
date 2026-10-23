# 命令记录与复现

从项目根目录执行。获取和分析均已完成；下载配置指向本轮暂存文件，不应在封存目录重复运行。

```bash
python3 -B -u scripts/swebench_instance_results.py --discover
python3 -B -u scripts/swebench_instance_results.py --plan
curl -fL --parallel --parallel-immediate --parallel-max 24 --config data/catalog/public_trace_acquisition/SWEBENCH-INSTANCE-RESULTS-20261023/source_metadata/download.curl > data/catalog/public_trace_acquisition/SWEBENCH-INSTANCE-RESULTS-20261023/source_metadata/download-results.jsonl
python3 -B scripts/swebench_instance_results.py --supplement-plan
curl -fL --parallel --parallel-immediate --parallel-max 12 --config data/catalog/public_trace_acquisition/SWEBENCH-INSTANCE-RESULTS-20261023/source_metadata/supplement.curl > data/catalog/public_trace_acquisition/SWEBENCH-INSTANCE-RESULTS-20261023/source_metadata/supplement-results.jsonl
python3 -B scripts/swebench_instance_results.py --seal
python3 -B scripts/swebench_instance_results.py --analyze
python3 -B -m unittest tests.test_swebench_instance_results tests.test_swebench_instance_result_review -v
python3 -B scripts/swebench_instance_result_review.py
```

复核前还单独读取了 `verified/20250120_Bracket/logs/sympy__sympy-20428/test_output.txt`（39字节）；URL与校验摘要见报告中的additional-source-manifest.json。其他74份空报告的配套测试输出在完整listing中也为0字节。

curl配置为每请求15秒连接超时、120秒总超时、2次重试，并限制文件大小。全部主批次先检查HTTP/大小/ETag/JSON形态，再统一将`.part`改名；有一个预测文件虽然名为jsonl，实际为JSON数组，已按原生格式读取。

离线复现不需要网络，但需要完整本机raw、旧报告和listing等证据。代码仓库副本不含这些大文件。入口拒绝覆盖原报告；请在独立项目副本中保留相同的相对输入路径、使用尚不存在的输出目录。重新下载应建立新的catalog/raw批次，记录新的时间与字节身份，不能冒用本轮manifest。
