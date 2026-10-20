# 本地历史测量字段覆盖盘点 v2

范围：三个已登记批次各自显式选择的run，共27个；未扫描或混入其他run。
本报告只读历史记录，不回填或改写raw。

状态：A=已有原始观测；B=可从有效原始相邻计数离线补算；C=部分可用；D=无历史观测、需新采；E=该scope不适用。

| 指标 | Coding（9） | Office（9） | Assistant（9） | 本轮接入/限制 | 新运行？ |
|---|---|---|---|---|---|
| CPU累计/时间/scope | A | A | A | 保留cgroup usec与进程ticks两种scope，记录monotonic原始值 | 否 |
| CPU区间平均core | B | B | B | 从相邻有效计数差分；缺读/回退/无效时间为gap | 否，历史可补算 |
| memory.current | A | A | E | 与RSS、内核peak分列；Assistant为进程RSS而非容器memory.current | 否 |
| 进程RSS | A | A | A | 宿主共享进程scope，不等同容器峰值 | 否 |
| 内核memory peak | A | A | D | Coding/Office cgroup；Assistant历史无进程内核peak | Assistant需新采 |
| 磁盘I/O累计/速率 | A/B | A/B | A/B | cgroup块服务字节与/proc rchar/wchar/read_bytes/write_bytes分列 | 否，速率可补算 |
| 网络tx/rx | D | D | D | 新接口仅为共享network namespace网卡累计计数；不是PID、HTTP正文或TLS精确字节 | 是 |
| 工作目录/输出/缓存占用 | D | D | D | 本轮边界扫描只量可见run输出目录表观大小；私有workspace/共享cache未知 | 是 |
| attempt/阶段时间 | A | A | A | 原始阶段事件保留；观测窗口不混称attempt wall | 否 |
| 请求/工具/返回/bootstrap | A | A | A | 按各自原生事件；没有transport hook时HTTP尝试数仍unknown | 否 |
| 机器/软件/限制/采样质量 | C | C | C | 字段按链路分散；环境/镜像、limits、PID与采样缺口不强行同口径 | 部分 |

## 历史累计计数的实际区间覆盖

计数来自上述逐run实际记录。区间分母按每个相邻采样对×指标计；一个采样对中CPU有效而I/O无效时分别计数。
| 批次 | 指标区间候选数 | 有效指标区间 | gap指标区间 |
|---|---:|---:|---:|
| P1-12-CODING-REPEAT-01 | 11251 | 11242 | 9 |
| DOCOPS-OFFICE-REPEAT-02 | 2760 | 2760 | 0 |
| TOOLSANDBOX-ASSISTANT-REPEAT-01 | 1935 | 1935 | 0 |

## 历史网络/磁盘边界候选字段扫描

计数是含候选字段的run数，不把字段名本身当作确认的语义测量。

| 批次 | 已选run | 含网络候选键run | 含目录占用候选键run |
|---|---:|---:|---:|
| P1-12-CODING-REPEAT-01 | 9 | 0 | 0 |
| DOCOPS-OFFICE-REPEAT-02 | 9 | 0 | 0 |
| TOOLSANDBOX-ASSISTANT-REPEAT-01 | 9 | 0 | 0 |

## 当前实现的接线边界

共享实现位于 `collectors/execution_measurement.py`：monotonic网络命名空间rx/tx累计采样、边界目录表观大小前后扫描、通用累计计数器相邻差分。Coding、DocOps/Office、ToolSandbox/Assistant生产入口均消费该实现；采集失败记录partial，不替代原清理/归档。
Coding测量容器中的 `/testbed`；Office测量容器中的 `/root/submission`；Assistant情景状态为内存态（not_applicable），其宿主run输出目录另测。宿主日志/归档目录与容器任务目录分列；共享缓存仍unsupported。容器内依赖 `python3`，离线fake已验证调用边界，真实容器工具可用性尚未验证。
历史记录没有这些磁盘边界；本轮接线不回填历史。历史网络字段候选计数按实际选定run生成，字段名本身不代替语义确认。

## 当前采集能力与限制

新网络读数来自采集进程所在network namespace的接口累计计数。它包含该namespace其他进程流量，不是PID/API专属；未实现透明且覆盖三条模型客户端路径的HTTP请求/流式响应正文计数，TLS/链路开销也不在可测范围。
宿主输出目录按表观大小扫描，不量allocated blocks。容器私有workspace现仅限上述明确任务路径；共享缓存、镜像大小、宿主剩余空间不由其替代。扫描失败/超时为partial/null，不填0。
历史报告v1保持原字节。其manifest记录的分析源码哈希与本轮修改前工作区该源码哈希已不同；本轮未声称重建v1所用源码，v2 manifest记录本轮实际分析代码。
真实运行验收尚未进行。建议后续按Coding、Office、Assistant各授权一条小样本生产链，核实实际容器 `python3`、目录范围、网络scope、清理及归档；此建议不是执行授权。
