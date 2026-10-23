# AgentX 剩余会话与输出控制核查

用户授权继续补充串行样本 20 条、长上下文 26 条，并核查远程输出长度控制。新实验只测客户端，保留官方依赖投影、完整正文和原始输出长度对应上限，零自动重试。独立分支基于 `70860fe`，不改视频会话文件或共享状态。

环境复用 `/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python`，没有新增依赖。准备时离线使用固定 HF 缓存及官方 `agentx-harness==1.0.7`；真正请求体取自第二步已核验的捕获，未使用本次离线重建的新文本。

实际执行命令：

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_complete prepare --source-root /home/lcq/agentx_replay_smoke_20261023
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_complete run --name 01-complete-cases
```

`prepare` 与 `run` 拒绝覆盖历史目录。运行读取当前 `DEEPSEEK_API_KEY`，需要工具网络权限。固定官方 HTTPS 地址，不跟随重定向，沿用已有代理；只向工作进程传递该服务密钥，值不落盘。新增正式请求 46 条及 3 条分别有界的探针；每条探针最多 64 token。探针对默认、`min_tokens=64`、`ignore_eos=true` 分别测试，正式样本没有这些额外字段。

最多 8 个在途请求；900 秒单请求超时、120 秒读取超时、2400 秒尝试总时限。正式请求遇到失败停止新派发、排空已发请求，不裁剪上下文或静默重试。预期的探针参数拒绝可作为能力结果，但认证、配额和传输失败会停止运行。本轮所有 49 条新请求实际均为 HTTP 200。

离线核验与作图不调用 API：

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_coverage_analysis
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m unittest tests.test_agentx_deepseek_complete tests.test_agentx_deepseek_branches tests.test_agentx_deepseek_pilot tests.test_agentx_replay_smoke tests.test_agentx_deep_analysis tests.test_agentx_deep_locality
python3 -B scripts/check_project_state.py
```

分析仍需当前密钥做精确值泄漏检查，不会输出该值。历史单链与两子代理实验只读引用其清单和原始证据，未再次发送 API 请求。请保留历史工作树与原始目录，Git 远程只包含派生结果和身份清单。完整结论见 [summary.md](../../reports/analysis/AGENTX-DEEPSEEK-FIVE-CASES-v1/summary.md)。
