# 并发工作与状态防丢失

2026-10-23。针对共享工作区中的未提交状态被整文件回滚的问题，当前采用以下约束。规则入口是根目录[AGENTS.md](../AGENTS.md)。

1. **不同对话使用不同worktree和分支。** 避免多个对话同时编辑同一物理文件；每个任务只提交自己的路径/改动，再通过Git合并。示例：`git worktree add -b task/agentx-review /home/lcq/awc-agentx-review HEAD`。新worktree不自动包含忽略的原始数据、凭据和本地归档，按需使用明确的只读数据位置，不复制凭据进仓库。
2. **禁止为清理工作区回滚未知修改。** 不使用`git checkout -- project_state.json`、整文件`git restore`、`reset --hard`或`git clean`来消除不属于自己任务的修改。不确定来源的文件先保留。
3. **状态写入必须先读后合并。** 使用[安全更新工具](../scripts/update_project_state.py)，递归合并本任务字段，不覆盖其他任务条目；必须提供读取时的SHA256，版本已变化即拒绝写入。自动生成三个当前页面的状态块，显式更新当前证据，历史哈希不自动重置。
4. **每次写入前自动保留准确快照。** 状态和三个页面存于`local_archive/project-state-snapshots/`；工具同时使用协作文件锁和原子文件替换。它不能拦截绕过工具的编辑器/Git命令，因此独立worktree仍是第一层保护。
5. **完成一个可核验步骤就提交、推送。** 显式暂存任务路径，检查暂存区，运行相关测试和状态核查。Git只备份已提交文件；原始数据、凭据和本地快照另行备份。用户排除视频修改时，远程提交不应冒称备份了完整视频工作区。

## 使用方式

在仓库根目录执行，均不运行Agent、模型或实验。

```bash
PYTHONPATH=. python3 -B -m scripts.update_project_state snapshot
```

输出包含当前`state_sha256`和准确快照目录。创建只含本任务字段的补丁，例如：

```json
{
  "completed_limited_deliverables": {
    "my_task": {"status": "complete", "report": "reports/my-task/summary.md"}
  }
}
```

写入时提供刚才的SHA256；不要使用更早对话缓存的值：

```bash
PYTHONPATH=. python3 -B -m scripts.update_project_state apply --patch /tmp/my-task-state-patch.json --expected-sha256 "读取时的完整SHA256" --append-summary "本任务的新状态摘要"
python3 -B scripts/check_project_state.py
```

若更新了一个已审阅的当前文件，可显式添加`--refresh-evidence docs/example.md`。不要把此选项批量用于历史报告或原始数据以掩盖不一致。补丁不允许直接替换`execution_authorization`、完整`evidence`或完整`public_summary`。

出现`stale`或`concurrent writer`时停止该次写入，重读最新状态并重新合并；不要改用整文件覆盖绕过保护。若写入过程中遇到错误，快照仍保留，可据此逐项恢复，不覆盖新出现的并发内容。

## 本次检查点的范围

用户确认本次继续排除视频修改。因此远程检查点包含AgentX深入分析、PPT、状态恢复记录、并发保护工具/测试/规则，以及对应的**非视频状态增量**。完整恢复状态继续保存在本机快照中；视频源码、环境、报告、素材及其状态增量未随本次推送。工作区中仍可看到这些未提交修改，这是范围隔离的预期结果，不能再用Git HEAD覆盖它们。
