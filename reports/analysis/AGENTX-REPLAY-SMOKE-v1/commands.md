# 复现与核验

工作目录 `/home/lcq/agentx_replay_smoke_20261023`，只在独立工作树执行。安装依赖和首次取得公开分词器需要网络；回放和核验使用本地文件，不连接真实模型。

```bash
uv venv .venv --python /usr/bin/python3
uv pip install --python .venv/bin/python -r env/agentx-replay-smoke-01/requirements-lock.txt
```

分词器来自 `Qwen/Qwen3-0.6B` revision `c1899de289a04d12100db370d81485cdf75e47ca`，只需 `tokenizer.json`、`tokenizer_config.json`、`config.json`、`merges.txt`、`vocab.json`，保存在 `data/raw/agentx-replay-smoke-01/tokenizer/`。首次样本准备还需该目录下原始下载的 `hf-api.json`，其 `sha` 须与上述 revision 相同。每个文件的哈希见样本清单；不要下载模型权重。

首次准备仅运行一次，已有完整样本会拒绝覆盖：

```bash
python3 -B -m scripts.agentx_replay_smoke_prepare --source-root /home/lcq/agent_workload_characterization
```

实际成功执行的命令如下（本机沙箱需要允许仅监听 loopback 的进程）：

```bash
.venv/bin/python -B -m scripts.agentx_replay_smoke_run --name 03-full-sample --timeout 600
.venv/bin/python -B -m scripts.agentx_replay_smoke_audit --attempt 03-full-sample
.venv/bin/python -B -m scripts.agentx_replay_smoke_verify
.venv/bin/python -B -m unittest tests.test_agentx_replay_smoke tests.test_agentx_deep_analysis tests.test_agentx_deep_locality
```

完整底层 CLI、允许的环境变量名、耗时和清理结果保存在每次 `attempt.json` 及报告 [attempts.json](attempts.json)。再次回放必须使用新的 `--name`，脚本拒绝覆盖历史目录。重复离线 audit / verify 会重建当前报告，正式扩展建议使用新报告版本保留本次冻结清单。

仅离线核验可以重复，不会启动服务或发送请求。`scripts/check_project_state.py` 也已执行同等 `check(ROOT)` 检查，结果保存于 `final-verification.json`；此 worktree 缺少 36 个历史本地证据，故全局检查单独记录为 FAIL，未把它冒充 PASS。
