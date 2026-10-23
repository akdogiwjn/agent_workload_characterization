# AgentX 远程 DeepSeek 客户端试点

用户选择使用已有远程 DeepSeek，不测服务端资源，并明确要求开始。实际执行为 1 条连通性探针 + 1 个完整会话的 20 条固定请求，零自动重试。已有旧试点文件的授权字段只属于其历史实验，未使用或修改。

工作树 `/home/lcq/agentx_deepseek_pilot_20261023` 与视频会话隔离。复用第二步 Python 环境 `/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python`；没有安装新依赖、复制密钥或启动模型服务。依赖实际版本在本轮忽略目录 `environment.json`，`requirements-lock.txt` 保存可提交的版本列表。

实际准备及执行命令如下。`prepare`、`run` 拒绝覆盖历史目录；再次调用真实 API 需要新的尝试名，仍应核对当前模型文档。

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_pilot prepare --source-root /home/lcq/agentx_replay_smoke_20261023
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_pilot run --name 01-remote-session
```

`run` 会读取当前进程 `DEEPSEEK_API_KEY`，并访问固定 HTTPS 官方地址 `https://api.deepseek.com/v1/chat/completions`；需工具网络权限。不会使用其他服务商密钥，不记录 Authorization 头，不跟随重定向。沿用已有本地 HTTP(S) 代理；客户端耗时包含代理影响。

仅离线分析和测试（不会调用 API）：

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_analysis --attempt 01-remote-session
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m unittest tests.test_agentx_deepseek_pilot tests.test_agentx_replay_smoke tests.test_agentx_deep_analysis tests.test_agentx_deep_locality
python3 -B scripts/check_project_state.py
```

离线分析为了检查精确密钥值没有泄漏，仍需该环境变量存在；它不会将值写入结果。分析可重复，会重建本轮图表及清单，扩展实验应采用新版本报告。正式结果见 [summary.md](../../reports/analysis/AGENTX-DEEPSEEK-CLIENT-v1/summary.md)。
