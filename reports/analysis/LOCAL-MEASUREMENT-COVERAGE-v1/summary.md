# 本地历史测量字段覆盖盘点

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

## 本轮统一接线

共享实现位于 `collectors/execution_measurement.py`：monotonic网络命名空间rx/tx累计采样、边界目录表观大小前后扫描、通用累计计数器相邻差分。Coding、DocOps/Office、ToolSandbox/Assistant生产入口均已调用该实现；采集失败落为partial，不替代原清理/归档。
现有cgroup采样器同时保存CPU及block-I/O有效相邻区间速率；原始累计字段和缺读状态仍在。ToolSandbox宿主/proc区间速率使用运行时CLK_TCK。新增输出进入各自当前manifest流程；Coding identity按src清单覆盖，DocOps/Assistant清单含共享collector，Coding run-02显式增加collector路径。没有重冻结历史identity。

## 解释边界

网络读数来自采集进程所在network namespace的接口累计计数。DocOps/Coding任务容器禁网不意味着宿主模型API流量为零；Assistant worker与宿主共享网络命名空间。读数包含同namespace其他活动，不能归属于单PID、某个API请求或某个工具，也不包含可分离的HTTP正文/TLS字节。
磁盘只在run输出目录起止边界扫描，按表观文件大小，不量allocated blocks；不扫描项目、镜像仓库、用户目录。容器私有workspace、共享缓存、镜像大小、宿主剩余空间仍分别不可由该测量替代。
历史记录的计划/批次/attempt关联仅按所保存的摘要、批manifest和raw manifest核验；本轮当前采集代码已改变，不把当前代码哈希或新字段反推为历史执行证据。
真实运行验收尚未进行。建议后续按Coding、Office、Assistant各一条生产链分别授权一次小样本测量，先核实网络scope、输出目录边界、清理归档和缺测行为；三条都核验前，不决定是否扩大到新口径重复批次。
