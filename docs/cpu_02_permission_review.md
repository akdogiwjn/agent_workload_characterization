# CPU-02 宿主 `/proc` 权限拒绝只读归因

检查状态：**已完成，只读**。本次未调用 Docker、未启动容器或自建测试进程，
未运行 perf、Django、模型、网络或权限修改；未修改历史报告、批准或 marker。
本报告不创建 CPU-02-R2，也不构成 CPU-02 重试授权。

## A. 已证实事实

历史诊断批次：
`CPU-02-PID-DIAGNOSTIC-01-20260916T092657Z-5ac9efa6`。

- 历史诊断进程投影：PID `843382`，NSpid `[843382]`，pid namespace
  `pid:[4026531836]`，starttime ticks `235667717`。
- 历史容器 init 投影：host PID `843505`，NSpid `[843505,1]`，starttime
  ticks `235667851`；pid namespace 链接读取结果为 `PermissionError`、errno
  `EACCES（errno=13）`、安全类别 `permission_denied`。
- worker 报告容器 PID `7`、starttime ticks `235667860`、pid namespace
  `pid:[4026558673]`。映射结果为 `map_failed / init_ns_unreadable`。
- worker 已 `reaped`，容器已 `removed`。历史记录没有删除后的原进程信息；
  不能用当前系统中可能复用的 PID `843382` 或 `843505` 代表历史进程。
- 历史批次的 `summary.json` 和 `manifest.json` 均为 `FAIL`，且 summary
  bytes/SHA-256 已由 manifest 核对。

历史证据路径：

```text
reports/cpu/CPU-02/pid-diagnostic/CPU-02-PID-DIAGNOSTIC-01-20260916T092657Z-5ac9efa6/summary.json
reports/cpu/CPU-02/pid-diagnostic/CPU-02-PID-DIAGNOSTIC-01-20260916T092657Z-5ac9efa6/manifest.json
```

本次只读检查进程（不是历史诊断进程）：

```text
pid=60
uid=1000
gid=1000
supplementary_groups=[65534,65534,1000]
effective_capabilities=0x0000000000000000 (none)
NoNewPrivs=1
Seccomp=2
Seccomp_filters=1
security_domain=unconfined_u:unconfined_r:unconfined_t:s0-s0:c0.c1023
```

当前检查环境的白名单系统配置读取结果：

- `/proc` 挂载观测到两条 `proc` 挂载记录；选项分别为
  `nodev,noexec,nosuid,ro` 和 `nodev,noexec,nosuid,rw`。未见 `hidepid`、
  `gid` 或 `subset` 选项。未读取全量 mountinfo。
- `kernel.yama.ptrace_scope=0`，读取成功。
- `fs.suid_dumpable=2`，读取成功。
- LSM 启用信息为 `lockdown,capability,yama,selinux,bpf`，读取成功。
- 本地 proc/LSM man page 或 kernel-doc 路径不存在，因此没有使用本地文档
  对具体 `ns/pid` 访问规则作进一步断言。

## B. 可能原因及支持/反对证据

1. **访问者在当前获准环境中缺少必要权限或 capability。** 当前检查进程的
   effective capability 集合为空，这支持“受限环境”解释；但它不是历史诊断
   进程的完整环境证明，也不能单凭此断定该 `readlink` 必然被 capability 拒绝。
2. **容器/进程的 pid namespace 链接受运行时安全策略保护。** 历史失败发生在
   `/proc/<container_init_pid>/ns/pid` 的链接读取，而不是在三重匹配之后；这与
   namespace 可见性或安全策略限制相容。当前 LSM 列表包含 SELinux、Yama、BPF，
   但未取得历史时刻对应的决策日志或策略命中证据。
3. **hidepid 或 proc 挂载选项造成不可见。** 当前检查所见 `/proc` 记录没有
   `hidepid`、`gid`、`subset`，因此没有支持这些选项是当前原因的证据；但当前
   检查环境不保证与历史诊断环境完全相同，不能据此排除历史环境差异。
4. **Yama ptrace 限制。** 当前 `ptrace_scope=0` 不支持把 Yama 作为本次拒绝的
   直接解释；同时，读取 namespace 链接不等同于一次已证实的 ptrace attach。
   因此不能由该 sysctl 值单独推出或排除所有 LSM/运行时限制。

## C. 当前无法区分的原因

现有证据只能确证一次 `EACCES（errno=13）`/`permission_denied`，不能唯一区分：

- 历史获准进程的 capability、NoNewPrivs、Seccomp、SELinux/其他安全域与本次
  检查进程是否相同；
- 历史容器的 `/proc` 挂载选项、pid namespace 可见性及运行时安全配置；
- 拒绝来自 procfs 可见性、LSM/容器策略、进程身份关系，还是其他内核路径。

因此不能把它直接归因于 Yama、`hidepid`、缺 capability 或 perf attach 不可用。
也不能把历史 PID 当前是否存在解释为历史进程状态。

## D. 最小下一步建议及所需授权

最小下一步是由管理员或运行诊断的同一获准环境提供白名单只读核对：历史运行
上下文的 effective capability/NoNewPrivs/Seccomp/security domain、相关 proc
挂载限制，以及适用的 LSM/容器策略命中类别；不读取环境变量、cmdline、凭据、
全量日志或审计日志。若仍需动态验证，应另行批准一次不启动工作负载的最小
procfs 访问实验，并单独取得工具权限。

本建议不包含 `sudo`、`nsenter`、`--privileged`、`--pid=host`、新增 capability、
sysctl/挂载/用户组修改或 Docker 配置修改。任何权限变更或动态实验均留待用户
另行批准。
