# G1 集中评审：已验证能力与下一步

评审日期：2026-09-15。最新裁定：**G1 资源归因小闭环 `PASSED（登记范围）`**。G1-02 B 的服务/异步与比较条件补证已验收；不等于所有 workload、所有进程或所有采集器均验证，不授权下一项实验。

## 0. 本次裁定及下一步边界（当前有效）

在下述既有 RUN-01/RUN-02、G1-01 证据基础上，追加 [G1-02 B manifest](../reports/resource/G1-02/G1-02-20260915T093254Z-94bb0ee7/manifest.json) 完成原剩余两类证据。该 manifest SHA-256 为 `e914c1393d600a00745803997fe6e52a16e9da05b2c84f5a1dd0a892519b254d`。本次只读核验输入/输出身份、事件与边界，不重跑实验，不查询 Docker。

| 补证 | 集中核验与裁定 |
| --- | --- |
| 服务/异步 | 同一 PID/starttime 的两个同步请求各有 hook；job1 completed、job2 cancelled，身份/时间顺序/原始事件一致。补齐登记机制的小闭环，不声称覆盖所有服务实现。 |
| 比较条件 | 固定6对、12区间；ON各7次周期采样、OFF为0，边界及host观测均保留；checksum一致，诊断 allowance 重算12/12满足，comparison=sufficient。 |
| 开销解释 | 配对差值中位数907787ns，两对负差值保留为噪声；不形成稳定开销百分比或普遍误差上界。已验证的是本配置的资源采集比较条件，不包括后续 perf。 |
| 归档/清理 | 6输出与manifest闭环；wall约19.69s，未越预算；两个容器的移除依据封存证据成立，不冒称当前daemon重查。 |

`baseline_cpu_unreadable:None` 是 v1 数据被 sampler 的 v2 字段检查生成的诊断 note；实际 `cpu_usage_usec` 与 `cpuacct.usage` 状态有效，不是12个区间 CPU 缺失。解释见 [交付 §6](g1_02_delivery.md)，封存内容不改。

**决议**：原六条 Gate 在已登记 Coding scope＋确定性机制范围内满足，M2 小闭环完成，可以准备 P2。正式 I/O null、shared CPU、宿主非完整后代树等继续作为已接受边界；多任务代表性、独占 Tool CPU、PMU 和函数热点仍未完成，不倒挂为新 G1 前置。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-09-20 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- G1：登记小闭环通过；G2 / G3-R 未通过。
- CPU-02：初次 B 准备失败，修复后 R1 映射失败；后续 perf 权限受限。路线暂停，无有效容器热点样本，新 retry 未授权。
- P2-01 小样分析与 P3-01 v3 现有 trace 审计已交付；不授权 Replay。
- 当前：P1-12 小规模独立任务 × 重复的离线选样与预算设计；不启动容器、模型或新实验。
<!-- PROJECT_STATE:END -->

<details>
<summary>G1-02 补证前的裁定（历史：当时为 LIMITED_SCOPE_ACCEPTED / PARTIAL）</summary>

适用范围：已登记 native arm64/cgroup v1、mini-SWE-agent 2.4.6、Django Coding 运行；Agent/Verifier 容器边界 CPU/Wall、memory 分口径，mini 宿主首末可读区间 CPU/RSS，以及原生 hook 工具持续时间和共享 scope 关联。不是所有 Coding 任务或全部 Agent 执行机制的普遍保证。

| 原 G1 条款 | 本次裁定 | 依据与边界 |
| --- | --- | --- |
| 1 语义/process/资源关联，独占/共享/未知明确 | 限定范围满足 | R2 的 run/attempt、28 个工具身份与原生窗口、mini PID+starttime、容器 scope 可核对；只声明共享关联，不分摊独占 Tool CPU。后代未完整采集作为缺口，不冒称全进程树。 |
| 2 短进程/后台/服务/异常/时间边界 | 部分满足 | A 的时钟/重叠机制，B 的短宿主进程、后台 CPU、停止与冻结，R2 的非零返回码和 process_exited 有证据；常驻/进程内服务、异步作业生命周期仍未形成相应闭环。不得全项勾选。 |
| 3 CPU/I/O/memory、重叠/残差/遗漏 | 限定范围满足 | R2 CPU 边界重算吻合；memory current/采样最大/内核峰值区分；正式 I/O null、诊断值不作应用字节；host 非生命周期总量；未观测部分不填零。禁止将 scope CPU/峰值无条件相加为完整 E2E。 |
| 4 真实 Runner＋确定性证据与独立状态 | 最小要求满足 | RUN-01 与 R2 是同一 task 的两个真实 attempt；A/B 为机制证据，不增加 task 数。R2 verifier 10 测试通过，管道状态与 LimitsExceeded/未提交分离；原始清单与清理结果保留。 |
| 5 开销量化、正式比较前固定容差 | 部分满足，描述性用途可用 | A 有 3 对开/关监控原始值，R2 有 host reader 717 次读取共 38026291 ns 的耗时；不等于全 collector CPU 或稳定 overhead 百分比。正式比较的区间、误差预算与容差尚未固定，不能进行性能优劣/因果判断。 |
| 6 CPU/Wall/Memory 候选 scope | 容器级满足 | Agent 51.007123 core-s、Verifier 3.64963 core-s；分别有 wall/memory，mini 有区间 CPU/RSS。可选择描述性候选范围，但不宣称函数热点、PMU 或每工具 CPU 排名。 |

证据定位：[R2 review-v2](../reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/manifest.json)、[A R4 机制](../reports/resource/G1-01-A/G1-01-A-R4-20260913T085846Z/mechanism_checks.json)、[A 开销](../reports/resource/G1-01-A/G1-01-A-R4-20260913T085846Z/overhead.json)、[B batch](../reports/resource/G1-01-B/G1-01-B-20260914T070400Z-39f05a/batch.json)。

本轮只读复核 A manifest 的 8 个输出、B 的 5 个输出、review-v2 的 3 个输出，哈希均一致。对应 manifest SHA-256 分别为 `450aa8bbc4e11698921b50285cec4f1f007074fa04afab98bf529ecedf4f7ba2`、`c10aabd2c2360b70f2e1d61d8c523ac265bfbb466f5433c0ea0efd78b6ab96c5`、`de2721e93eeba8b64f8e9298f312c02e22d9edd42e15a36ee741b6c527efa943`。R2 的 17 个输入哈希已在 CLOSEOUT 复核通过。本轮未运行测试、Docker 或模型；清理结论依据封存记录，不是重新查询当前 daemon。

A R4 的机制 JSON 与 overhead JSON 对应开关差值为 +1.553/-8.751/-9.242 ms；历史 g1_evidence.md 中仍有早轮数字与生命周期旧措辞。本裁定采用上述 JSON 的原始值和代码段/首末可读窗口语义，不修改历史文件，也不把差值当计量误差上界或“负开销”。

**可继续的工作**：基于现有封存样本做离线描述性分析、候选 scope 选择和下一实验设计。不需要为此重跑 READY/B1/R2；这不等于 P2 perf/Hotspot 的自动放行。

**完整 G1 的最小剩余证据**只有两类：

1. 对尚未覆盖的服务/异步机制，先固定拟支持范围与可观测生命周期，再补该范围的确定性证据；不要求实现所有 benchmark 或无限扩展进程追踪。
2. 正式性能比较前，明确 collector 成本覆盖范围、相同比较区间、计量容差和降级规则；若现有原始对照不足，再提出最小受控验证。不得用两个真实 attempt 的差异倒推开销。

多任务数量、正式应用 I/O、独占 Tool CPU、完整 host lifetime/peak、PMU 均不是本次新增 Gate 前置。下一批任务书应针对具体研究问题选择上述工作，不再开展通用启动修复；任何新运行、安装、权限查询或付费调用仍需单独授权。

</details>

## 1. 当前能力与输入

RUN-02-R2 已完成同一 `django__django-16485` 的一次真实联合观测：
[原始 raw](../data/raw/generated/RUN-02/20260915T012427Z-2d75aa/)、[原报告](../reports/resource/RUN-02/20260915T012427Z-2d75aa/)、
[review-v2](../reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/)。它补充了 native Tool hook、mini 宿主和 Agent/Verifier 容器 scope 的联合证据，不能替代多任务或独占归因验证。

保留上次评审摘要：2026-09-14 已验收 G1-01 A/B 的限定范围，G1 未通过；RUN-01-C、G1-01 A/B、原 RUN-02/R1、READY-01 的历史证据不重封存。测试数量不等于 benchmark、请求数或独立任务数。

## 2. CLOSEOUT-01 提交的六条建议（历史评审输入，当前裁定见 §0）

| G1 要求 | 当前状态 | 本次新增证据与已满足范围 | 剩余缺口／建议判定 |
| --- | --- | --- | --- |
| 1. 语义、进程、资源关联及归因范围 | PARTIAL | R2 的 `mini_tool_events.jsonl` 28 open/28 closed，`host_process.jsonl` 有 PID+starttime 和 717 快照；容器 scope 与 run/attempt 关联。 | Tool/资源仍 shared-scope，后代关联不完整；保持 PARTIAL。 |
| 2. 短进程、后台、服务、异常、时间边界 | PARTIAL | 28 个 native hook 边界和 0 个 hook error；1 个非零 Tool returncode 被保留，closed 不等于成功；host 末次为 `process_exited`。 | 短命后代、常驻服务、异步作业覆盖不足；保持 PARTIAL，不扩范围。 |
| 3. CPU/I/O/memory、重叠与遗漏口径 | PARTIAL（限定指标可用） | 容器边界 CPU、wall、memory 分口径；host CPU 4.19 s 为首末可读区间增量；RSS last-readable/sample-max 分开；formal I/O=null。 | 当前仅需评审测量范围、重叠和遗漏的解释；formal I/O、独占 Tool CPU 与完整 host lifetime/peak 是已接受降级/后续扩展，不是新增 G1 前置。 |
| 4. 真实 Runner＋确定性机制证据及三状态 | EVIDENCED（单 attempt 限定范围） | R2 `execution/evaluation/archive/cleanup=ok`、report complete、resolved=true；Agent `LimitsExceeded`/未提交但工作树补丁通过 verifier，三状态独立保留。 | 单任务/单 attempt 不证明代表性或普遍可靠性；维持限定 EVIDENCED。 |
| 5. 开销量化及正式比较容差 | PARTIAL | R2 记录 runner wall 156.609939194 s、collector 读取成本独立保留，原始事件/资源文件可复核。 | 未固定稳定 overhead 百分比和正式比较容差；不开展 A/B。 |
| 6. 可找到 CPU/Wall/Memory 候选 scope | EVIDENCED（容器级） | Agent/Verifier scope 有 CPU、wall、memory 与采样证据；mini host 有 CPU/RSS 区间证据。 | 函数热点、PMU、独占 Tool CPU 与多任务排名属于后续研究方向；保持限定 EVIDENCED。 |

G1 全项不勾选。按既有六条标准，真正待评审的缺口是：Tool/资源 shared-scope 下的后代
关联、短命后代与服务/异步边界覆盖、以及开销量化和正式比较容差。I/O null、shared CPU、
退出末端缺失是已接受降级；多任务/多 attempt、正式应用 I/O、独占 Tool CPU、函数热点/PMU
和多任务排名是后续研究方向，不是本次 G1 的新增前置。P2 perf/Hotspot、批量任务和 replay
仍未授权。

## 4. B1 的降级是结果，不是重跑理由

- c1 四次工具调用；sleep 窗口 1.254 s，open 在返回前可读；false 的 rc=1 为预期结果。
- c2 CPU 从 216354 增至 1215628 usec；随后 docker_stop，容器退出，末边界文件 not_found，正式 CPU 总量保持 null。
- 采样线程存活，stop(scope) 后 0.45 s 内读取数 20、样本数 18 均冻结。
- 宿主短子进程有两次可读快照；它不是 mini，也不证明后代进程树完整。
- 批 wall 报告为 6.83 s；报告无越时、无阈值超限。UTC 字段不是额外的高精度开始锚点，预算与时长依据 monotonic 证据。
- 容器正式 I/O 不可用、磁盘无配额、scope-kind 标签不能把合成容器解释成真实 Agent/Verifier 工作。

上述限制保留，不修改 B1 包，不为取得“更漂亮的结果”再跑。

## 5. 收敛规则

下一次集中评审只阻塞：未经授权的副作用、秘密泄漏、工作负载无法停止/清理、证据丢失或伪造、失败误报成功、下一批核心工具/宿主证据未接通。样式、历史措辞、非目标服务/PMU 支持不单开返修轮。发现阻塞一次列全；失败运行保留，不自动修复重试。
