# AgentX 本地回放环境

第二步已完成 5 个完整会话 / 117 请求的模拟回放。报告在 [summary.md](../../reports/analysis/AGENTX-REPLAY-SMOKE-v1/summary.md)。本目录不保存凭据、模型权重或原始请求正文。

- Python 3.11.6，Linux aarch64；官方 `agentx-harness==1.0.7`；分词器使用 `transformers==5.20.2` / `tokenizers==0.23.3`。
- `.venv` 仅属于本工作树；[requirements-lock.txt](requirements-lock.txt) 记录本次完整安装版本。分词器身份和文件哈希记录于样本清单。
- [status.json](status.json) 是本任务状态；[project-state-patch.json](project-state-patch.json) 只含本任务新节点，供后续安全合并共享状态。没有修改执行授权字段，不代表授权第三步真实模型实验。
- 原始会话、两次失败和一次成功回放均在 `data/raw/agentx-replay-smoke-01/`。成功请求体为 gzip，实际 token ID 为 npz；它们被 Git 忽略，远程只有可核对的清单，不包含原始证据文件。
- 当前工作树与视频会话物理隔离。未在共享仓库运行还原、清理、整文件状态替换，也没有合并共享状态或视频变更。
