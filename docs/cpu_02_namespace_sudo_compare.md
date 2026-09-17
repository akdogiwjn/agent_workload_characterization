# CPU-02 namespace 读取权限管理员对照检查

状态：**仅准备完成，待用户手动批准后执行**。本方案不是 CPU-02 重试、
不执行 perf，也不创建 CPU-02-R2。历史批准、attempt、raw 和报告不变。

## 用途与边界

本检查只比较同一个仍存活的临时容器 init PID：普通用户读取
`/proc/<PID>/ns/pid` 与管理员只读 `readlink` 的结果。它不测试 perf attach，
不运行 Django、模型或 benchmark，也不把 SSH 用户等同于历史模型执行身份。

固定条件：一个已登记 arm64 digest，`network=none`、`pull=never`、1 CPU、
256 MiB；Docker endpoint 固定为 `unix:///var/run/docker.sock`；总预算 60 秒，
其中清理预留 15 秒。容器仅运行 `sleep 2h`，并使用唯一名称和 CPU-02 标签。

## 用户手动执行

先在普通 SSH 终端确认 sudo 已由用户自行认证；脚本不接收密码：

```bash
sudo -v
```

然后仍以普通用户执行脚本（不使用 sudo 包裹 Python 或 Docker）：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  scripts/cpu_02_namespace_sudo_compare.py --execute
```

脚本的 sudo 白名单只有以下完整 argv，且使用 `--non-interactive`，不会提示或
读取密码：

```text
sudo --non-interactive -- /usr/bin/readlink /proc/<State.Pid>/ns/pid
```

Docker 的所有 argv 都由普通用户、固定 `--host unix:///var/run/docker.sock` 调用；
脚本不调用 `sudo docker`、`sudo python`、shell 或权限修改命令。

## 顺序、判定与清理

脚本先检查唯一容器名不存在，再以固定参数创建容器，记录并核对实际容器 ID、
`awc.check` 标签和 `State.Pid`，后续清理只使用已核验的容器 ID。创建响应丢失时，
必须先按本批唯一标签找到并核验 ID，不能仅凭名称删除。普通用户失败不会改用
另一个 PID，而是对同一 PID 执行一次 sudo `readlink`。两次读取前后重新核对
容器 ID、标签、PID 和该 PID 的 starttime；PID 非正整数、目标退出、身份变化或
身份无法核验均为 `inconclusive`/失败，不作权限结论。

结果只投影必要的 namespace、PID、starttime、退出码、错误安全类别、当前 SSH
用户 UID/GID、耗时和清理状态。比较结果分别为 `both_success_same`、
`ordinary_failed_sudo_success` 或 `indeterminate`；超时、命令不存在、无效输出和
其他非权限失败不自动解释为权限拒绝。sudo 失败只报告安全类别，不输出错误原文、
环境变量、凭据或完整 cmdline。

正常、异常、Ctrl-C 和超时路径都尝试按本批唯一名称执行 `docker rm -f`，随后
使用固定 endpoint 的 `docker ps -a --filter name=<本批名称>` 核验；未确认删除
或清理越时不得报告成功。创建响应丢失时仍按本批名称进入清理核验。

## A 阶段离线验证

本阶段只使用 fake Docker/读取命令替身调用 `run_check()`，覆盖非法 PID、普通
读取失败、sudo 读取失败、目标 starttime 变化、命令超时和清理失败；验证默认
计划不调用 subprocess，且不存在 `sudo docker`、`sudo Python` 或未校验字符串
传给 sudo。未调用真实 Docker、sudo、perf、网络或权限探测。

管理员成功不能替代正式执行身份，也不证明 perf attach 可用；任何权限变更、
动态实验或 CPU-02 重试均需另行批准。
