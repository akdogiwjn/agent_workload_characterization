# AgentX 五类各三次：补齐剩余三类

用户授权单子代理、原始区间串行、长上下文各追加 2 次，新增 134 条正式请求；每次另做一个最多 16 token 的连通性探针，共 140 次 Chat POST 上限。每轮独立 HTTP 工作进程，按 A B C C B A 顺序执行；不是随机实验。此前单链及多子代理已各完成三次，本轮只读引用历史证据。

独立分支 `task/agentx-deepseek-five-repeats-20261023` 基于 `eec0a05`，不更改共享状态或视频文件。复用 `/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python`，无新依赖。逐次保存实际 Python / 包版本；锁文件沿用前轮同一环境。

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_finish_repeats prepare
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_finish_repeats run-batch
```

准备从已核验的 branch / coverage 原计划取固定正文，逐字节核对并复制 67 个 gzip payload；拒绝覆盖冻结目录。计划冻结运行脚本、原计划和正文哈希。运行使用官方 `https://api.deepseek.com/v1/chat/completions`，不跟随重定向；模型 `deepseek-flash`，thinking disabled，temperature=0。保持原始输出长度对应上限及 serial / post-SPAWN / SPAWN_JOIN 依赖；不复现原始时间间隔，不截断上下文、不补齐输出、不将新输出送入后续请求。

`DEEPSEEK_API_KEY` 只在内存使用，值与 Authorization 头不落盘；子进程只继承该服务凭证及必要的普通环境、代理和证书变量，不继承其他 provider 密钥。最多 8 个在途请求；单请求 900 秒、读取 120 秒、单次会话尝试总时限 2400 秒。零自动重试；失败停止新派发、排空在途并停止后续批次，保留全部证据。尝试目录拒绝覆盖。

资源采样只覆盖自有 worker 及其子进程，排除采样父进程、其他会话和服务器。采样循环工作后 sleep 0.2 秒，报告实际间隔。历史 R1 多子代理、长上下文与先前案例共用进程，串行 R1 先做过三次长度探针；本轮均为新进程加一次连通性探针，报告披露前置条件差异。

离线核验和制图不调用 API：

```bash
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m scripts.agentx_deepseek_five_repeat_analysis
/home/lcq/agentx_replay_smoke_20261023/.venv/bin/python -B -m unittest tests.test_agentx_deepseek_five_repeats tests.test_agentx_deepseek_repeats tests.test_agentx_deepseek_complete tests.test_agentx_deepseek_branches tests.test_agentx_deepseek_pilot tests.test_agentx_replay_smoke tests.test_agentx_deep_analysis tests.test_agentx_deep_locality -v
python3 -B scripts/check_project_state.py
```

分析需当前密钥做精确值泄漏检查，不输出该值。所有 351 次正式执行都重新解析原始 SSE，并对照源指纹、正文、输出上限和依赖。117 个唯一源请求必须分别恰好有 R1/R2/R3 一次；重复观察不能变成独立源样本。只给出逐轮结果和 min–max，不作显著性或总体推断。

12 页汇报 PPT 将 Full/256k 全量结构统计与五类远程实测放在不同页面；全量部分引用既有固定报告并保存 SHA256，本轮不重扫全量原始文件。前缀结构潜力不等于服务缓存命中，实际输出覆盖不是业务成功率。原始长输出负载和业务工具执行仍未完整复现。

本任务状态与只包含本任务节点的待合并补丁保存在本目录，未写入共享 `project_state.json`。全局检查另列 36 个历史忽略证据缺失；不修改历史哈希来使检查通过。Git 只备份脚本、计划、派生报告、图表、PPT 与身份清单，原始请求/SSE/资源采样仍在各工作树忽略目录，离线重算需保留这些工作树。

完整结论见 [报告](../../reports/analysis/AGENTX-DEEPSEEK-FIVE-REPEATS-v1/summary.md)。
