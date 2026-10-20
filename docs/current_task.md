# 当前任务与下一步

<a id="current-task"></a>

更新：2026-10-17。目标见[当前范围](current_scope.md)，进度见[项目总览](project_status.md)，事实源为[project_state.json](../project_state.json)。

## 当前任务：LOCAL-THREE-CLASS-REPEAT-01（12次补齐及v3合并复核完成）

风险处置已由用户确认。Complete-02 按冻结顺序完成 12/12 次（Coding 4、Office 8），批 wall 1374.008s；0 failed、0 not_executed、0 cleanup/archive/measurement 验收错误。新 identity：`8a17109cf441e3ae68e3f9820babe5685467657cbcafb56d765dd1158dc4942d`。结合原有效 Excel 1、Coding 5、Assistant 9，27 个预定 task×round 槽位均有三个观察点；旧 Office 错路由 8 次仍作为历史错误路径保留并排除。独立分析：[v3摘要](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)、[逐run](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/per_run.jsonl)、[任务统计](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/task_statistics.csv)、[manifest](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/manifest.json)。固定镜像批后只读核验7/7匹配。每任务n=3是固定任务重复，不是类别总体；共享netns不是任务/API专属流量，HTTP尝试和费用unknown。未更新HTML、未提交Git；G2/G3-R不变，CPU-02与Replay仍暂停。

### 历史阶段：v2续批（后由Complete-02补齐预定槽位）

保留原批 Excel `20261016T182559Z-09-r0-office`，另启动续批 22/26 次；Coding 5、Office 8、Assistant 9。原批加续批共23次已启动运行，27槽中4个Coding槽因历史验收误判而记为`not_executed`，原记录保留。续批 wall 1338.141s，22次清理确认及归档核验通过。分析包：[中文摘要](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2/summary.md)、[逐run JSONL](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2/per_run.jsonl)、[任务统计](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2/task_statistics.csv)。

- **Office route mismatch：**续批8个 Office 单次配置均未带`model_route`；绑定的 `build_agent()` 在路由缺失时采用模块默认 `API_BASE=https://api.deepseek.com/v1`，而冻结身份记为火山网关。8个 attempt 都以 `agent_error/BadRequestError` 结束，verifier reward=0；不作为冻结火山路由下的有效任务结果，不与原批 Excel 合并。HTTP尝试/实际远端接收/费用仍unknown。错误正文含凭据拒绝细节，未复制到分析包；路由错配可能涉及凭据被发往非预期端点，需在后续处置中按安全事件核查。
- **Coding stop（纠正）：**第五次为`no_candidate`、`evaluation_status=not_run`，事件明确verifier未启动，CPU及workspace应为`not_applicable`。原验收无条件要求verifier指标，误判后停止，4槽未执行；不改写历史partial/停止记录。v2新增独立复核结论，并按稳定scope角色修正跨run CPU/内存统计。
- **Assistant：**9次运行，3个固定任务各3次，官方similarity原值及每run请求/工具/资源数据分别保存；不推断类别总体。
- 原批Excel仍保留原 identity、成功结果与原批批验收失败记录；新续批identity为`ad6db92924e5adaf507a81370ebb0bc245ad6be57433d5ca6159813f6e5615af`，不改写旧批准、冻结、raw或报告。
- 分析由23个run实际原始计数生成：逐run SVG/CSV、任务统计、工具操作与目录占用表。Office错路由数据单列；不同scope不相加；共享netns不称API专属流量。本轮离线修复：Office单次路由显式传递并在客户端创建前校验，结构化BadRequestError保守停止；原Excel火山路由标签已纠正。续批11项、分析7项、绘图8项共26项回归通过；v2登记575项输入、8份代码和65项输出。
- 修复后未实测、未创建批准或attempt、未重冻结旧身份。错路由可能涉及凭据误发，建议轮换对应火山密钥；本轮未读取或轮换凭据。
- 未补跑、未更新HTML、未提交Git；Gate不变，CPU-02/Replay继续暂停。额外正式运行未获授权。

### 原批初次停止时记录（保持原义）

本批原先只启动1次Excel：`20261016T182559Z-09-r0-office`，finish、reward=1、run入口RC0，容器删除及镜像保留已确认。批次入口RC7；原记录为executed=0/failed=1/not_executed=26，其中failed是批验收失败，不是任务失败。见[集中收尾](../env/local-three-class-repeat-01/closeout.json)与[初次限定分析](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-characterization-v1/summary.md)。

- Coding两个固定Astropy镜像引用及完整config ID均不存在，未找到登记的本地恢复上下文；未拉取、未替用Django，Coding9槽位未执行。
- 首个Excel结束后，本轮新增`key_measurements()`误读`resource_intervals.host_agent`，实际键为`host_agent_process`，触发KeyError，全批停止；Office余8、Assistant9未启动。早期fixture未覆盖此门禁，离线测试通过不等于生产接线已完整验证。
- 独立只读验收通过：raw26个输出文件集合/bytes/SHA、98项输入与冻结身份关联、请求12、自主工具11、bootstrap2全部配对、finish后无新增请求。386样本/385有效CPU区间，采样窗192.110s不等于attempt wall207.260s；共享容器CPU12.00025s，提交目录0→6632B。
- 执行身份`460c9c28e4799d864ff2aa3a2bf7cf2e272fa095eabb917f4bec4f1b45893b22`不改。停止后先保存精确执行源码，再离线修正键名并补回归；当前源码与执行时身份存在已解释漂移，未重冻结、未混配置续跑、未补跑。Coding wrapper的ok归档状态映射已修，历史RC7原件保留。
- 最终定向回归32项通过（15批接线/清理、3 Coding生命周期、3 Assistant函数式真实fake链、11分析/绘图），无未完成用例；开发期fixture失败及正式验收漏测均单独记录。分析1136项输入、18项输出回读通过；30个历史目录/884个文件未变。仅1张真实run四面板，其余任务n=0；不能给出n=3变异结论。
- 网络仍为共享netns，cache unsupported、HTTP次数/费用unknown；未更新HTML、未提交Git，Gate不变，CPU-02/Replay暂停。状态不是继续执行授权。

## 前次任务：VOLCANO-THREE-CHAIN-LIMITED-OFFLINE-CHARACTERIZATION

状态：本轮限定离线分析完成，产物见[中文摘要](../reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/summary.md)。仅分析Office02 `20261016T143948Z-excel001`、Coding01 `20261016T144518Z-django16485-91776c`、Assistant01 `20261016T145056Z-tsbvolcano01`；每类n=1，不混入旧27次重复，不做跨类别效率或因果判断。

- 已核验保存计划/冻结完整identity、批准、报告与raw关联；三份raw文件集合/SHA和外层归档、集中记录引用通过。当前执行源码漂移检查为空；没有执行生产入口或读取凭据。旧输入前后哈希及文件集合未变。
- 生成三张独立四面板SVG、三份可追溯作图CSV及目录占用表：[Office](../reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/figures/office.svg)、[Coding](../reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/figures/coding.svg)、[Assistant](../reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/figures/assistant.svg)。不同scope共用同run保存monotonic原点；平均core、current/RSS、I/O和共享netns逐接口分列。其余网络接口保留统计，不跨接口求和，不把展示接口称API出口。
- Office8请求、7自主工具+2bootstrap；Coding20请求、30个mini原生工具终态（29普通返回、1 Submitted控制流）；Assistant Agent/User请求6/1、5个业务工具+1用户结束工具，1个ConnectionError业务工具返回不当作infra失败。两种响应model标识分别统计，HTTP次数/费用unknown。
- Office容器179点；Coding Agent/verifier周期点243/27、各另有起止边界，宿主597点末次process_exited形成一个gap；Assistant39点。scope采样窗与attempt wall分开，不把无缺读写成全生命周期覆盖。Coding宿主实际约0.2s，未伪填0.5s目标。
- 资源统计从原始累计计数重算；CPU峰值只与保存阶段/调用区间作共现。Assistant初始化、play、evaluator的共享CPU分列，不能把初始化/评估统称工具成本。目录扫描本身位于观测窗内，未剔除成纯任务成本；日志扫描早于最终归档结束。
- Coding真实RC7保留：入口要求archive_status==complete，runner成功值是ok，实际归档哈希与清理通过。本轮未修入口、未改返回码、未重跑。
- 定向unittest发现/执行/通过8项，失败0、未完成0；覆盖完整fixture入口/SVG/CSV、单位、0与missing、gap、原生工具与响应字段、scope、网络选择、哈希篡改拒绝及历史保护。未安装渲染器；SVG XML、数据路径、离线资源及本地链接检查，不冒称浏览器实渲染。

前次真实验证的16列集中表仍保留：[validation-summary.md](../env/docops-measurement-volcano-02/validation-summary.md)，批准、raw和identity均未改。三次运行额度已经消费，本轮仅分析；未更新HTML、未提交Git，Gate与CPU-02/Replay暂停状态不变。

## 已完成任务：MEASUREMENT-COVERAGE-UNIFIED-01

## 当前任务：MEASUREMENT-COVERAGE-UNIFIED-01

状态：本轮补齐了采集初始化失败的停止/失败归档路径，并将历史速率区间按CPU、cgroup I/O和`/proc` I/O分别重算，生成[覆盖报告v3](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)。Office入口25项、共享采集/Office批次34项、Coding生命周期3项、覆盖分析6项定向回归通过；ToolSandbox函数式回归顺序运行前9项通过，第10项中断，不能称整套通过。没有真实运行验证、没有创建批准/attempt、没有提交Git。

历史文档迁移与引用整理仍按旧记录保留。本轮盘点只读取批摘要明确选择的Coding、Office、Assistant各9个run，核验raw manifest文件集与SHA；没有回写历史数据。v3将CPU和各I/O计数器的候选/有效/gap区间分列；v1/v2原件及输出哈希保持不变。v2绑定源码的修改前快照与SHA登记见[`source-snapshot-manifest.json`](../env/local-measurement-coverage-v3/source-snapshot-manifest.json)，不声称当前源码等于历史分析代码。

- Coding `/testbed`与Office `/root/submission`容器路径在Agent写入前后边界扫描，宿主run输出另列，cache仍unknown；扫描依赖容器`python3`，未真实容器验证。扫描失败留下partial/null并继续原清理。
- 共享网络接口速率按interface/netns身份计算，不跨接口求和；不是任务/API专属字节。三条模型客户端的请求与流式响应正文bytes尚未实现，HTTP/TLS开销不可得。
- 通用速率差分要求两端读取状态有效、身份一致、累计值合法；Office CPU、cgroup I/O与宿主`/proc` I/O分开判断。未知CLK_TCK/身份保持gap。
- 代码接线、离线测试通过、真实运行验证是三个不同状态；当前只达到前两项，不据此宣称实测覆盖完整。
- ToolSandbox函数式测试不能用`unittest`自动发现（发现0项）；直接调用实际测试函数的本轮扫测前9项通过，在第10项运行期间停止，10项未开始。单个完整fake链测试实测耗时约60秒，说明测试成本较高，但不能据此解释旧九次批次超时。旧报告的13/16及3个失败没有保存测试名/断言，当前证据仍不足以分类；九次Assistant fake批次的旧180秒超时原因仍unknown，不归因为线程争用。
- 下一步先分别对三条链各授权一次小规模验证，之后再决定是否需要新口径重复批次；本建议不构成执行授权。

## 本轮停止点

当前批已停止：1次attempt已消费，26槽位未执行；不修改历史批次状态，不在同一冻结批次里修复后续跑。单样本分析与离线回归完成，仍未形成三类各3×3的新口径重复样本。缓存/API专属字节未知，不启动后续实验、不更新HTML。

## 保留事项与停止边界

原始trace、正式raw、报告、批准/attempt、manifest、冻结身份、源码快照、参考仓库、虚拟环境和Docker镜像均未删除或搬迁。原大报告保留本机路径，大型JSON被忽略不代表已失效。

历史归档授权不扩展到删除、压缩后移除原件、安装、联网/API、Docker或实验。代码中文档路径/导航变化也可能影响未来计划身份；旧批准不适用于修改后代码，不重冻结旧批。Gate未通过项、CPU-02与Replay暂停状态不变。
