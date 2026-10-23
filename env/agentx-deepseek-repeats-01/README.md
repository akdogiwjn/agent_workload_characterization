# AgentX 两类会话重复实测

用户授权单链基线及多子代理各追加 2 次，各类连同历史 R1 共 3 次观察。本轮固定 50 份既有正文和依赖图，新增 100 条正式执行，不新增唯一源样本。独立工作树基于 `c35ff76`，分支 `task/agentx-deepseek-repeats-20261023`；不更改共享状态页、历史文件或视频工作。

环境复用 `/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python`，无新增依赖。精确依赖锁沿用此前五类实验；本轮每次执行也单独保存实际 Python 与包版本。

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_repeats prepare
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_repeats run-batch
```

`prepare` 冻结原计划、正文和执行脚本的哈希；拒绝覆盖冻结目录。`run-batch` 按单链 R2、多子代理 R2、多子代理 R3、单链 R3 执行，每次为独立 HTTP 工作进程，先做 1 次最多 16 token 的连通性探针，总上限 104 个 Chat POST。尝试目录拒绝覆盖；已有证据不删除。读取 `DEEPSEEK_API_KEY`，值与 Authorization 头不落盘，仅向 worker 传递该服务凭证及必要普通环境/代理变量。

固定官方 `https://api.deepseek.com/v1/chat/completions`，不跟随重定向，保留现有代理；模型 `deepseek-flash`、thinking disabled、temperature=0。输入及 max_tokens 与首次执行逐字节一致，最多 8 个在途请求，保留 serial / post-SPAWN / SPAWN_JOIN 依赖，不复现原始时间间隔。新输出不送入后续请求，不追加文本强制生成，不截断上下文。

单请求总时限 900 秒、读取时限 120 秒、单次会话尝试总时限 1800 秒；零自动重试。失败停止新派发并排空已发请求，停止后续批次。采样仅覆盖本任务拥有的 HTTP worker 和子进程，排除采样父进程、其他会话和服务器；worker 生命周期结束后确认清理。每个采样循环工作后 sleep 0.2 秒，报告实际采样间隔。

离线分析不调用 API：

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_repeat_analysis
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m unittest tests.test_agentx_deepseek_repeats tests.test_agentx_deepseek_complete tests.test_agentx_deepseek_branches tests.test_agentx_deepseek_pilot tests.test_agentx_replay_smoke tests.test_agentx_deep_analysis tests.test_agentx_deep_locality -v
python3 -B scripts/check_project_state.py
```

分析需当前密钥做精确值泄漏检查，值不会输出。R1 原始证据只读引用原 pilot / branches 工作树，重新核对历史清单及 SSE。按稳定案例、node_id、源指纹及正文哈希配对，避免完成顺序错配、漏样或重复计数。展示每轮指标及三次 min–max，不进行显著性或总体推断。

R1 多子代理与先前单子代理共用 worker；本轮各次为新进程，因此 RSS 等结果存在进程前置条件差异。远程缓存、服务负载及模型别名对应权重未受控，输出可自然提前结束，不能将重复观察当作原始业务工具复现。

全局检查保留继承的 36 个忽略证据缺失项；不刷新历史哈希掩盖缺口。本任务状态保存在本目录，另附只包含本任务节点的 `project-state-patch.json`，未写入共享项目状态。Git 只备份派生结果、图表、PPT、代码和证据身份清单；忽略原始数据与凭证不在远程备份中。完整结果见 [报告](../../reports/analysis/AGENTX-DEEPSEEK-REPEATS-v1/summary.md)。
