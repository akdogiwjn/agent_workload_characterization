# B 容器验证审批提案（G1-01-B；仅提案，未执行任何容器操作）

## 目的

在无模型、无真实任务的前提下，于真实 arm64 容器内验证 G1-01-A 新增
采集链：工具事件真实边界、容器 scope 计数器窗口关联、宿主进程采集、
停止后边界。

## 固定输入

- 镜像：`swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`（本地已有，不 pull/build）
- 代码：G1-01-A 交付身份（manifest.json code_identity）
- 无模型请求、无真实 Agent 任务、无 gold/candidate 执行

## 用例（2 个顺序容器；各 ≤2 CPU/256 MiB；合成写入 ≤16 MiB；总 wall ≤180 s）

### 容器 1：工具事件 + 容器计数器窗口

启动 arm64 容器（network none），经 `AttachedDockerEnvironment`（即
真实 hook 路径）执行 4 条确定性命令：

1. `sleep 1`（固定时长——验证 open 先于执行持久化、closed 边界 ≥1s）
2. `dd if=/dev/urandom of=/tmp/g1b.bin bs=1M count=8 && sync && rm -f /tmp/g1b.bin`（8 MiB 合成写入——验证 io 诊断计数与边界）
3. `false`（失败 returncode 记录）
4. `python3 -c "x=sum(range(2_000_000))"`（固定工作量 CPU——验证容器 cpu.stat 增量与工具窗口关联为 shared_scope）

断言：mini_tool_events.jsonl 4 open + 4 closed、t_start≤t_end、
容器 cgroup 边界计数在窗口内增长、无原始命令/输出落盘。

### 容器 2：宿主采集 + 停止后边界

同镜像容器内启动后台 busy（`nohup sh -c 'while :; do :; done' &`），
父进程同时运行 HostProcessMonitor 采集自身与子进程；随后执行
terminate_workload 停止链，验证：停止确认状态三分类、停止后无新
有效采样、最终计数器读取语义（存活确认→可读；docker stop→不可读
如实记录）。

## 预算与清理

- 总 wall ≤180 s；每容器 ≤2 CPU/256 MiB；磁盘写入 ≤16 MiB（容器 1
  的 8 MiB 临时文件用后即删；容器可写层仍无配额——已知降级，非新风险）
- 清理：仅 `awc-run01-<run_id>-` 身份匹配容器；残留记录
- 产物：`reports/resource/G1-01-B/<batch>/`（独占创建）

## 明确不在本提案内

- 任何模型 API 调用、真实 Agent 任务、gold verifier 重跑
- perf/eBPF、磁盘配额变更、网络开放（容器 1/2 均 network none）
- 第二次真实任务或预算放宽

**等待用户明确批准后执行；本文件不构成执行授权。**
