# AgentX 远程子代理会话扩展

用户授权补充单子代理、多子代理两会话。正式请求共 51 条，另 1 条探针；模型服务仍为远程官方 DeepSeek，仅采集客户端资源。完整结果见 [summary.md](../../reports/analysis/AGENTX-DEEPSEEK-BRANCHES-v1/summary.md)。

独立工作树 `/home/lcq/agentx_deepseek_branches_20261023`，基于第一轮提交 `ea0c1ea`，分支 `task/agentx-deepseek-branches-20261023`。Python 环境复用 `/home/lcq/agentx_replay_smoke_20261023/.venv`，无新增依赖，不复制密钥，不修改共享状态或视频文件。

准备与执行：

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_branch_prepare --source-root /home/lcq/agentx_replay_smoke_20261023
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_branches run --name 01-remote-branches
```

准备阶段仅在离线环境调用官方加载器和已下载的固定分词器。`prepare` 不覆盖目录；失败准备完整保留在 `data/raw/agentx-deepseek-branches-01-preparation-failed-01/`。计划固定 51 条正文、50 条依赖、两会话顺序、代码哈希和超时。运行前后核验冻结代码身份，最多 8 个在途请求；900 秒单请求超时、90 秒读取超时、1800 秒批次墙钟限制，零自动重试。

执行需工具允许网络，并从当前进程读取 `DEEPSEEK_API_KEY`。仅官方固定 HTTPS 地址，不跟随重定向；沿用已有 HTTP(S) 代理，其影响计入客户端时延。只传递该服务密钥，不继承其他服务商密钥。

离线分析与检查：

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_branch_analysis
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m unittest tests.test_agentx_deepseek_branches tests.test_agentx_deepseek_pilot tests.test_agentx_replay_smoke tests.test_agentx_deep_analysis tests.test_agentx_deep_locality
python3 -B scripts/check_project_state.py
```

分析不访问 API，但精确密钥泄漏检查仍需当前环境中有密钥；值不会写入结果。历史单链基线和第二步原始正文按固定路径只读引用，结果清单保留哈希。原始文件不随 Git 推送；请保留三个工作树中的原始证据目录。扩展应新建报告版本，避免覆盖本次正式结果。
