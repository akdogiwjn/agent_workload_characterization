# ViMax 长任务的持久启动（media 默认；planning 新增显式阶段）

更新：2026-11-02（Asia/Shanghai）。本页不批准任何模型或媒体调用。

R06-MEDIA-01 的媒体产物完整，但宿主记录停在 `container_started`，采样仅约110秒且无结束边界。操作端报告外层120秒超时；现存证据未保存完整信号链，不能把唯一根因写成已取证。该历史运行继续标失败观察，不补写成功或缺失资源。

VIMAX-AUDIO-CONTRACT-FOUR-GAP-FINAL-CLOSEOUT-01（2026-11-02）：媒体正式身份必须绑定 `media_technical.py`（必需文件集单一来源）与 `pipeline_fix_mount` 宿主源，并强制 `technical_contract`（schema/policy + 确定性 digest）与当前 config 重算摘要一致；漏绑/helper 字节变化/契约摘要不匹配/config 容差或口径变化/部署源错配均发送前拒绝。`verify_media_technical` 与宿主共享同一绝对 close_deadline：每步先算剩余预算，timeout=min(声明,剩余)，耗尽零启动并记 `deadline_exhausted`，超时被回收。`duration_tolerance_s` 必须显式（缺失发送前拒绝；显式 0 合法）；duration_basis/A-V 阈值/audio_tracks 显式消费，不支持显式能力（vp9/channels/audio_codec!=aac）拒绝。`attempt_wall_s` 保持 Agent 窗口，`total_wall_s` 含技术验收阶段（分阶段计时记录）。

## 正式运行入口

未来正式运行使用 `scripts/vimax_managed_launch.py`，不再手拼 `nohup ... &`。启动器支持两个白名单阶段，共享同一持久传输层（独立session supervisor、token握手、stdin DEVNULL、日志文件、PID/starttime/PGID/SID、心跳、退出码、防重复启动）：

- **media（默认）**：执行原媒体 `host_runner.py run`，不更改预算、生成、拼接、资源采样或收尾逻辑。`--out` 必须尚不存在。
- **planning**：执行真实规划 `env/video/vimax/planning/host_runner.py run`。先运行真实 `preflight --out <OUT> --config <context>`，其会创建必要文件；`run` 必须允许该次合法预检目录（不再套用 media“整个OUT存在即拒绝”的规则）。planning 门禁用真实规划 `task_context.load_context` + `host_runner.validate_approval`（非媒体 `verify_identity_approval`），并实际校验本轮 out/context/approval 归属（preflight.json 的 config_sha256/task_context_sha256/session_id/task_id/entry_sha256）与 ATTEMPT-STARTED 已有 attempt 保护。

启动器先执行真实阶段/身份批准门禁（不读凭据、不启动容器），要求新冻结身份绑定启动器源码、阶段适配及持久性验证凭据；独立新会话supervisor经带token握手放行后再次校验身份，再启动原runner。stdin为DEVNULL，输出落文件，不继承交互工具管道。supervisor保存PID/starttime/PGID/SID、心跳和实际runner退出码，不自动重试。

### media（默认）启动

```bash
python3 -B scripts/vimax_managed_launch.py launch \
  --config <新正式配置绝对路径> \
  --out <尚不存在的新输出绝对路径> \
  --control <本次唯一控制目录绝对路径> \
  --persistence-proof <已通过的宿主持久性验证JSON绝对路径>
```

### planning 阶段启动

```bash
# 先真实预检（同一 context，创建 OUT/workspace）
python3 -B env/video/vimax/planning/host_runner.py preflight \
  --out <OUT绝对路径> --config <规划context绝对路径>

# 再经规划阶段托管启动器（OUT 为该预检目录；APPROVAL-01.json 旁为 identity-01.json）
python3 -B scripts/vimax_managed_launch.py launch --stage planning \
  --config <规划context绝对路径> \
  --out <同一预检OUT绝对路径> \
  --control <本次唯一控制目录绝对路径> \
  --approval <APPROVAL-01.json绝对路径> \
  --persistence-proof <已通过的宿主持久性验证JSON绝对路径>
```

### status（两个阶段一致）

```bash
python3 -B scripts/vimax_managed_launch.py status --control <同一控制目录绝对路径>
```

两条命令都必须在已验证的**持久宿主执行域**运行；如果工具需要提升权限才能脱离临时沙箱，使用产品审批机制，不绕过。不得将长runner前台挂在120秒命令上，也不得启动后再等待整段任务才让启动命令返回。

`--control`默认无隐式值，必须显式提供；它与`--out`互不包含，排他创建，不能位于`--out`里。身份、批准和启动控制文件不得提前创建runner的输出目录。重连时只查询status，不再launch；控制目录或输出已存在就拒绝，绝不覆盖历史证据。

`READY`只证明supervisor身份握手/放行，不代表容器启动、采样就绪或任务完成；`runner_exited/runner_rc=0`也不能替代原run-record的技术/程序/测量验收。正式报告仍需原runner终态、COMPLETE、成片、账本、边界、远端收尾和清理证据。

## 执行域证明与边界

`nohup`不防进程组SIGTERM；新session可以隔离进程组，却不防整组cgroup/PID命名空间销毁。已实际观察到：当前临时文件系统沙箱在工具调用退出后清掉子进程，即使用新session也会丢失。

因此正式launch必须提供同一启动器SHA、同一boot/PID命名空间/cgroup/UID的离线长驻探针证明，并将该文件路径及bytes/SHA加入新冻结身份。换执行域、重启宿主或修改启动器后先重新离线验证；不能拿宿主成功证明给临时沙箱放行。status也拒绝在别的PID命名空间中推断进程死亡。

本轮最终探针文件（需以实际 `verification.json` 验收为准）：
`reports/analysis/VIMAX-MEDIA-MANAGED-LAUNCH-REPAIR-01/host-confirmed-probe/verification.json`
（绑定启动器 SHA `f6e3c0…`）。修改启动器新增 planning 阶段后，同一持久宿主域以最终启动器 SHA `ff875bc4…` 重新离线探针：
`reports/analysis/VIMAX-G03-FULL-FLOW-R07-PLANNING-01/probe/host-confirmed-probe/verification.json`；旧证明保留，未刷新冒充新代码已验证。

探针仅运行130秒本地fixture进程，使用真实ResourceSampler及该进程CPU计数。它不是正式Agent、不是媒体容器、不是新增宿主性能监测，不调用模型/媒体/网络服务。测试分别验证外层进程组终止和工具父命令退出；并不声称复现了历史opencode工具未留存的全部超时实现。

主机宕机、OOM、管理员杀整个cgroup或平台取消持久执行域仍可能中断。此时status应报告supervisor丢失/未知，不自动重启或虚构完成；保存证据并按授权有界收尾。

## 持久归档

控制目录保存 `launch.json`、`RELEASE.json`、`lifecycle.json`、`supervisor.log`、`runner.log`。结束后与原raw分别归档并纳入新报告manifest；不把外层等待时间或启动器心跳冒充Agent资源采样。

失败握手在未放行时不启动runner，证据保留；已启动后supervisor异常也不盲目杀runner、重试或删除输出。完成状态与异常均需检查，不能只看最后有无mp4。
