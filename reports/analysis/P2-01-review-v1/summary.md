# P2-01 review-v1

本报告是对两个已登记、已封存 Coding attempt 的只读描述性分析；未执行新任务、容器或采样。排名全集为两个 attempt 各自的 `agent_container` 与 `verifier_container`，共 4 个可用容器 scope，不代表全局总体。

| attempt | 阶段/时间证据 | Agent 容器 CPU / wall / kernel memory peak | Verifier 容器 CPU / wall / kernel memory peak |
| --- | --- | --- | --- |
| RUN-01-C `20260912T125202Z-840e49-a1` | evaluation 12.216613793 s；total 146.540550945 s | 6.411718 core-s / 134.099304929 s / 68,497,408 bytes | 3.423041 core-s / 11.990780406 s / 70,459,392 bytes |
| RUN-02 `20260915T012427Z-2d75aa-a1` | execution/evaluation/archive/cleanup = ok；总 run wall 未提供 | 51.007123 core-s / 143.651636264 s / 1,434,140,672 bytes | 3.64963 core-s / 12.264456124 s / 72,548,352 bytes |

精确字段定位在 `summary.json`：RUN-01 使用 `budget.*`、`tools.calls`、`scopes[0..1].*`；RUN-02 使用 `run.*`、`tool_observation.*`、`resource_scopes[0..1].*`、`host_observation.*`。四个输入文件的 bytes/SHA-256 和三个输出文件的 bytes/SHA-256 在 `manifest.json`。

工具方面，RUN-01 为 26 次调用且分类不可用；RUN-02 为 28 次 native hook 调用（open 28、closed 28、error 0，另有 1 次非零返回码）。这些是调用次数，不是速率；没有有效时间分母，不作“频率最高”结论，且 `closed` 不等于成功。

RUN-02 宿主观测为 717/716 次快照，首末可读区间 CPU 4.19 s，RSS last-readable 218,214,400 bytes、采样最大 226,713,600 bytes，末态 `process_exited`。它只覆盖登记的宿主 mini 进程区间；不能证明容器或整个 Agent 在等待，也不计算 `wall-CPU`。RUN-01 宿主 Agent 观测缺失。

三项 top 角色（CPU、wall、memory）都指向同一个 RUN-02 Agent scope；六条候选是角色/观察维度，不是六个独立样本。Verifier 仅作同 attempt 的描述性参照，不是相同工作负载的严格控制。容器 kernel memory peak 不是进程 RSS，formal I/O 为 null，不补零。

结论限于现有小样候选选择；两个 attempt 虽为同一任务，但不是受控重复实验，数值差异不用于性能原因或因果解释。P2-02/perf 保持暂停且未授权；G1/G2 裁定不变。真正待评审项是字段/来源核对与该限定候选选择，不包括把多任务、正式应用 I/O 或独占 Tool CPU重新设为本次 Gate 前置。
