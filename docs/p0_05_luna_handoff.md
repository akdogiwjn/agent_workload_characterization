# Luna 新会话交接：仅执行 P0-05

## 0. 授权与当前状态

用户要求因额度限制暂停当前实现，改由 Luna 新会话完成。本文是执行计划，不是已完成报告。当前会话没有创建新的 IDE 会话或切换模型，也没有实现 P0-05 代码。

项目根：`/home/lcq/agent_workload_characterization`。P0-00-r2～P0-04 已交付，最近一轮 87 项 unittest 通过；Luna 应重新运行确认，不照抄测试结果。当前 IR 为 0.2.0，包版本为 0.1.0；依赖是 Pydantic 与 PyYAML，测试使用标准库 unittest。

工作树有大量修改和未跟踪文件，包含前述交付。它们不是可清理垃圾；禁止 reset/checkout/clean、删除未跟踪目录或覆盖已有工作。没有自动 commit/push 授权。不要读取或修改用户的 opencode.json、认证文件或模型配置。

仅实现 Applied Compute Adapter、小样验证、测试和文档。不执行全量 ingest，不运行 trie/client、旧 pipeline、benchmark、模型 API，不下载模型/数据，不恢复失败归档，不搬迁旧源，不修改 references 第三方内容。完成 P0-05 后停止，不自动推进 P0-06 或其他任务；G0 不因本任务完成而通过。

## 1. 开始前必读

完整阅读（过长时分段读完，不能以 rg 搜索代替）：

1. `methodology.md`
2. `docs/development_tasks.md`
3. `references/README.md`
4. `references/manifest.yaml`

随后阅读 `docs/data_management.md`、`docs/trace_contract.md`、`docs/adapter_framework.md`、`docs/ir_v0_2.md`、`docs/p0_04_delivery.md`、`data/catalog/sample_candidates.yaml`、sources.yaml 中三个 Applied 来源与 known_issues.yaml 中相关项。

核对代码：

- `src/agent_workload_characterization/adapters/{base,catalog,ingest,agentx,agentx_checks}.py`
- `src/agent_workload_characterization/{ir,metric_contracts,migrations,cli}.py`
- `tests/test_adapters.py`、`tests/test_agentx.py`、`tests/test_ir.py`

AgentX 是接口参考，不复制其 run、clock、request 或时间轴实现到模板来源。公共 ingest 是单文件 JSONL API；discover 默认支持一个 catalog 文件。输出保护、reject、幂等接口复用，不能另造绕过保护的 writer。

## 2. 已核实的本地证据

本会话已只读核对：

- `references/repos/trie/README.md`：length 单位明确为 token，tool_call_latency 是每轮模拟 delay，单位秒；N 个 tool-use turns 对应 N+1 completion。
- `references/repos/trie/src/trie/types.py`：三条逐轮向量长度必须等于 num_turns；cumulative_prompt_tokens 采用初始输入 + 前序 assistant outputs + tool outputs。
- `references/repos/trie/src/trie/client.py` 的 `_run_workload`：循环中一次 completion、拼接 response、sleep(delay)、拼接 tool prompt，循环后再一次 final completion。
- client 初始 prompt 使用 `max(input_prompt_length - 1, 0)` 补偿 BOS。实际 response 文本、tokenizer、服务端包装仍可能造成偏差。不要在模板逻辑算式里再次减 1，也不能把模板 token 当实测 usage。
- 当时 trie HEAD 为 `6918da7915e3ae57ce3750a375ef50e41cad2b36`，`git status --short` 无输出。执行前重新确认；记录所读文件哈希更稳妥。若版本改变，重新核对，不默认为上述证据仍适用。

第三方代码只读，禁止通过 import 或运行 client 进行“验证”。不需要 OpenAI SDK、tokenizer 或服务端依赖。

旧自有 adapter 位于 `/home/lcq/agent_workload/benchmark/benchmark_analysis/src/agent_trace_analysis/adapters/applied_compute.py`。已知错误：N 而非 N+1，初始长度当累计/最大，observed 标签错误，虚构 Tool 行，缺失和零混淆。只能参考字段形状，不能照搬计算。

## 3. 来源与身份设计（先写进新文档，再编码）

来源分别是：

| source_id | 原文件名 | subtype |
| --- | --- | --- |
| applied_agentic_coding | agentic_coding_8k.jsonl | agentic_coding |
| applied_code_qa | code_qa_8k.jsonl | code_qa |
| applied_office_work | office_work_8k.jsonl | office_work |

通过 Catalog 定位，禁止硬编码另一个 data_root 或复制旧文件。三个来源不能合并成一个失去 subtype 的来源。建议 subtype 由固定 source_id 映射并在摘要/文档显式显示，IR provenance.source_id 保留来源即可，不为一个已可表达的分类随意升级 Schema。

原始模板没有真实 run ID，不能把 template ID 当 run/task/attempt。推荐 v1 身份：source namespace + 源文件内稳定记录位置 `line:N`；不包含本机绝对路径、adapter 版本或 snapshot。这样文件搬家、同源重 ingest 保持身份，同内容不同源行仍保留发布的样本 multiplicity，不擅自按内容去重。明确限制：源文件重排/插入后的跨 snapshot 对齐不可靠，不能将两批 snapshot 简单并集统计。若选择不同策略，先说明如何保留重复模板的频数，不能以“防重复”为名消掉合法样本。

provenance 保存 source_id/snapshot_id/source_record_ref/adapter_version。配置只接受明确支持的选项；合成测试必须显式 synthetic，真实默认 production_derived。与 AgentX 同样，关联依据若需要 locator 应经稳定 provenance 引用，避免行位置混入内容等价判断。

## 4. 实现清单与语义

新增 `adapters/applied_compute.py`，继承公共 Adapter；使用现有 Template、Metric、TraceDocument 和 `template_lengths`。本轮优先保持 IR 0.2 不变。

### 输入校验

- num_turns 必须存在，是非负整数；bool、字符串、负数拒绝，不能缺省成 0。
- assistant_response_length、tool_call_output_length、tool_call_latency 必须为列表且长度恰好 N。缺整个向量、标量代替列表、错长度均拒绝，不截断或补齐。
- length 元素、initial、final：非负整数或 null；拒绝 bool、负数和数值字符串。必要标量缺失允许作为未知 null，明确 missing_reason；不能补 0。
- latency 元素：有限非负 int/float 或 null，保留实测意义之外的真实参数零值；拒绝 NaN/Infinity/溢出、bool、负数和字符串。
- 对未支持字段明确策略并测试：推荐拒绝未知键以暴露源格式变化，允许的源字段仅六个已定义字段。不要静默吞掉可能影响身份或语义的新字段。
- 输入预期错误转成 RecordError/IR ValidationError，公共 ingest 负责 reject；不要 broad catch 所有异常后伪报成功。

### IR 与指标

- profile=macro_template；真实 trace_type=production_derived，合成=synthetic。
- 只生成 provenance、Template 和 Metric，不生成 runs/tasks/attempts/agents/requests/events/clocks/processes/resource_scopes。
- Template 保存 N、初始输入、完整两条长度向量、final_output；unit=token，length_definition_ref 指向固定 commit 的本地文档/代码定义。缺长度时 length_missing_reason=not_recorded，完全已知时为 null。
- 时延向量不丢失：每轮一个 Metric，scope_id=template_id，aggregation 使用 `tool_turn:0` 等稳定索引，name 如 simulated_tool_delay，unit=s。不创建 Tool Event 或时间戳来承载它。
- 每轮 context 作为 Metric（`completion:0` … `completion:N`），单位 token，不创建虚构的实际 request。
- 初始上下文、N、N+1、总输入、总输出、最大上下文和 delay 总和另建 template scope 汇总 Metric。
- 所有已知值及确定性展开均标 template_parameter，不标 observed 或一般 derived；null 对应 unavailable + missing_reason。
- source_field_or_rule 写准确字段/公式；scope、denominator 指明模板、轮次、N+1 completion。派生指标如引用输入 Metric，保留模板证据，不产生循环/悬空引用。
- 缺一项必要输入时只传播到受影响的指标：tool output 缺失不应使已知 total output 丢失；final output 缺失不影响最后一个已存在输入 context。delay 缺失不影响 token。
- 时延总和是模拟等待预算，不是 E2E、Tool CPU、API latency。未知真实 run_elapsed、CPU 不填零；可输出 unavailable Metric，也可在能力摘要声明，文档须明确。

公式：`I[0]=initial`；`I[i+1]=I[i]+O[i]+R[i]`；总输入 `sum(I[0:N+1])`；总输出 `sum(O)+final`；final 不再加入不存在的下一个请求输入。复用 `template_lengths`，不要复制另一个有分歧的计算器。

## 5. 测试计划（不依赖真实旧文件的默认测试）

新增 `tests/test_applied_compute.py`，至少覆盖：

1. N=2 手算（下节数值），逐 completion context、所有汇总正确。
2. N=0：initial=32、final=64、三个向量=[]；1 completion、输入32、输出64、最大32、delay总和0；没有任何执行实体。
3. 参数全零且合法 N，0 不变 null；输出证据仍 template_parameter。
4. initial、逐轮 assistant/tool、final 分别缺失；受影响的 context/sum/max 为 null，未受影响指标保留。
5. delay null 与 delay=0 区分，缺 delay 不影响 tokens。
6. 三种向量各自错长度、缺失、不为数组均明确失败；N 类型/值错误失败。
7. 非法长度、bool、数字字符串、负时延、非有限时延失败。
8. profile、trace_type、unit、source subtype 和 provenance 正确；三个来源身份不同。
9. 同源同位置在移动路径/变换 adapter 版本后 template ID 稳定；同内容两行不擅自合并。
10. 临时项目中通过公共 ingest 完成 round-trip/reject/重复批次复用；重复 ingest 不新增模板，run 数保持0。
11. CLI/小样检查失败返回非零，禁止只看输出包含 PASS；旧 AgentX/Schema/框架测试全部回归。

不用承诺一个测试数量后凑数；按实际测试结果写交付记录。仅临时目录写合成输入/输出，测试不修改真实旧源。

## 6. 真实小样与可复核产物

AC-N2 已在 sample_candidates.yaml 登记：applied_agentic_coding，line 1729（1-based）。

```json
{"input_prompt_length":6318,"assistant_response_length":[101,1084],"num_turns":2,"tool_call_latency":[0.431,2.339],"tool_call_output_length":[6118,23],"final_assistant_response_length":801}
```

验收：N+1=3；contexts=[6318,12537,13644]；总输入32499；总输出1986；最大13644；模拟 delay 总和2.770s（浮点比较需预定容差或 Decimal，不宣称测量精度）。

新增只读 `check-applied-samples` 命令及对应检查模块，参考 AgentX 的接口但不要复制 run 汇总假设：

- 通过 catalog + sample_candidates 定位 AC-N2；核对原始六字段与登记值，再规范化、逐指标比对、IR round-trip。
- coding/QA/office 的 subtype 默认测试必须全覆盖。可额外只读选择 QA 和 office 各第一条作为结构 smoke，记录实际 locator/行哈希；没有独立手算预期的记录不能标成 gold 回归。不要为了三个 subtype 全量扫描 24576 条。
- 读取只到所需 selector，处理只限选中的记录。保存原始行 SHA-256，明确 snapshot_scope=selected_records，不把 P0-00 全文件哈希当本轮重新验证。
- stdout 输出结构化摘要；CLI 本身不创建正式批次或把原始生产记录写进仓库。
- 主执行者将小样检查摘要写入 `reports/quality/applied_sample_validation.json`，包含真实检查时间、版本、来源/selector、expected/actual、失败项、profile/evidence 和范围。
- 不导入或执行 trie 代码；不访问外网获取“最新”版本。当前任务验证固定本地参考，不做实时推荐。

## 7. 文档与问题状态

新增 `docs/applied_compute_adapter.md`、`docs/p0_05_delivery.md`；更新 README、任务计划与 methodology 顶部/当前下一步，保持历史交付记录不被改写成新结果。

将“length 单位待核实”限定更新为“本地固定 trie 版本已核实为模板 token；不代表实际 tokenizer/server usage”。不要把未知 license、所有来源版本或全量质量标为已完成。known_issues 若更新，明确旧 adapter 问题仍存在，新项目有回归修正，旧代码未修改。

模板参数仍是生产派生：不要用 token 单位已确认这个事实，将 evidence 改成 observed。references/manifest.yaml 的其他空 commit 与本任务无关，不顺手补齐。

P0-05 完成后按现有计划评估下一项：编号顺序候选 P0-06，但 G0 最小闭环也仍需 P0-10 本地 trace、P0-07/08/09。交付可以提出候选，不自动执行，也不宣称 G0 或 M1 已通过。

## 8. 实际命令与停手条件

先跑基线：

```bash
cd /home/lcq/agent_workload_characterization
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

实现后跑全量 unittest、新只读样例命令、现有 AgentX 样例回归（如源可访问）及 `git diff --check`。如旧源缺失/权限受限，可完成合成部分，真实验收标 PARTIAL，不虚构 PASS。

工具编辑用 apply_patch；不安装新依赖，不改 Python 全局环境。遇到需要 schema 新版本、文件迁移、付费请求、提权、全量运行等超出本文范围的情况，先报告原因请求确认。若仅代码难度无需停手，继续在本任务内修复测试。

最终答复简述：实际修改文件、实际命令/通过数量、AC-N2结果、不能证明什么、剩余 Gate；提供交付文档链接。不要只把计划标 DONE，没有实现和测试不能验收。

## 9. 可直接发给 Luna 的启动指令

```text
请接手 /home/lcq/agent_workload_characterization，只执行 P0-05。
先完整阅读 docs/p0_05_luna_handoff.md，再按其中要求完整阅读四份必读文档，
检查工作树和测试基线。遵循交接计划实现 Applied Compute Adapter、
合成回归、只读真实 AC-N2 小样检查和交付文档，不只是给我建议。
保留已有修改；不全量 ingest、不运行 trie 或远端 API、不修改旧源或 references，
不自动 commit/push。完成后给实际验证结果；不要继续后续任务。
```
