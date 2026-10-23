# AgentX v1.0 Full：获取与复现

固定上游revision；原始JSONL完整下载，来源图表不作为分析输入。

下载过程使用curl HTTPS（失败重试/续传），未发送模型请求或执行轨迹。

```bash
curl -fL --connect-timeout 20 --max-time 1800 --retry 2 --retry-delay 3 -C - -o data/raw/public/agentx_full/23f152f6f0f9399a85901b89a6458def0ef16729/traces.jsonl.part https://huggingface.co/datasets/semianalysisai/cc-traces-weka-062126/resolve/23f152f6f0f9399a85901b89a6458def0ef16729/traces.jsonl
curl -fL -o data/raw/public/agentx_full/23f152f6f0f9399a85901b89a6458def0ef16729/README.md https://huggingface.co/datasets/semianalysisai/cc-traces-weka-062126/resolve/23f152f6f0f9399a85901b89a6458def0ef16729/README.md
curl -fL -o data/raw/public/agentx_full/23f152f6f0f9399a85901b89a6458def0ef16729/stats.txt https://huggingface.co/datasets/semianalysisai/cc-traces-weka-062126/resolve/23f152f6f0f9399a85901b89a6458def0ef16729/stats.txt
```

完成后先核对manifest登记的上游文件大小与LFS SHA-256，再将.part封存为traces.jsonl；小文件另核对Git blob身份。原始文件不回写。

```bash
python3 -B -m unittest tests.test_agentx_full_macro -v
python3 -B scripts/agentx_full_macro.py --full data/raw/public/agentx_full/23f152f6f0f9399a85901b89a6458def0ef16729/traces.jsonl --capped data/raw/public/agentx/8fecd2fc56694469f758f0afbbb6335ad3043740/traces.jsonl --acquisition data/catalog/public_trace_acquisition/AGENTX-FULL-20261022/manifest.json --output-dir reports/analysis/AGENTX-FULL-MACRO-v1
```

输出目录已存在时拒绝覆盖；复现应使用新的输出目录。脚本重新核对Full获取清单和旧256k冻结manifest，逐行处理两份原始JSONL。

运行环境：Python 3.11及现有Matplotlib/NumPy用于静态绘图；统计与解析仅使用标准库。

Full与256k为同一筛选会话集的重叠版本；Full不是原始prompt/业务工具日志全集。
