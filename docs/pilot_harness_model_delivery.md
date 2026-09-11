# P0-07 Harness/模型配置核实交付（只读轮）

日期：2026-09-10。状态：**P0-07 保持 PARTIAL（选择已定，版本/映射未冻结）；G0/M1 未通过**。

## 实际改动文件

新增：
- `docs/pilot_harness_model_compatibility.md`（版本证据、脱敏映射、兼容性矩阵、输入白名单、proxy 评估）
- `reports/quality/pilot_harness_model_evidence.json`（7 项证据 + 3 项缺口；脱敏配置投影）
- 本文件

增量更新：
- `workload_catalog/pilot.yaml`（harness/model 改为 selected-not-frozen；budget.approval；
  新 evidence_refs；gaps 增补；状态行更新）
- `docs/pilot_execution_spec.md`（§1.3/§1.4/§4 重写：已定项不再询问，余下为有限授权请求）
- `reports/quality/g0_review.md`（第 5 条与缺口表更新：GAP-TASKDATA 已解决，语义更新 3 项）

未修改：分析代码、测试、references、旧工程、用户配置文件、原始任务记录、历史报告包。

## 实际读取范围与命令

只读操作：
- `opencode.json`：经**内存 JSONC 解析器**读取，输出白名单投影（见下）；未 cat/rg 原文，
  未计算全文哈希（有意），未展开/验证 apiKey，未输出 URL userinfo/query/fragment
- 定向查找（非全 home 扫描）：python3/3.11 site-packages、`~/.local`、两个旧工程 venv、项目目录
- 源码静态读取：`swebench/inference/mini_swe_agent.py`（全文）、`uv.lock`（mini 条目）、
  `pyproject.toml`（dev 组与 requires-python）、`run_api.py`（calc_cost）
- 归档成员读取（不解包到磁盘）：TraceBench 一个 miniswe tar.zst 的 `mini.traj.json`
  （读取中发现该成员 config 含明文 api_key——**输出截断保护生效，密钥未进入任何终端输出或本报告**；
  后续读取改用白名单键过滤）
- 哈希：uv.lock、run_api.py、mini_swe_agent.py（沿用）、tar.zst

本轮实际执行：`git diff --check`（通过）。未运行 175 测试（纯文档轮，未改代码）；
未运行任何安装/import/CLI/网络请求。

## 核实结果摘要

### 模型（脱敏，EV-HM-OPENCODE-001）
唯一匹配：provider `火山AI网关`（npm `@ai-sdk/openai-compatible`，OpenAI-compatible 协议类），
配置键=显示名词干 `deepseek-v4-flash`；baseURL https 且路径含 `/v1`；内联 apiKey 字段（未读值）；
声明 256k in / 8192 out。**精确请求映射未验证**（GAP-MODEL-ADAPTER-001）。

### Harness（mini-SWE-agent）
- **未安装**于任何已检查环境；无源码（EV-HM-MINI-NOTINSTALLED-001）
- swebench 02e7a74 `uv.lock` 锁 **2.4.6**（PyPI 哈希在锁内；依赖 litellm+openai 等 14 项；
  requires-python>=3.10）（EV-HM-LOCK-001）
- 本地历史轨迹由 **1.17.3** 产生（版本漂移记录；文本 bash action 协议、无结构化 tool_calls、
  instance_cost=0.0 未核算）（EV-HM-HISTTRAJ-001）
- 入口/配置层叠静态确认（EV-HM-ARGVBUILDER-001）；bundled config schema 不可核实（GAP-MINI-SRC-001）

### 成本（EV-HM-RUNAPI-COST-001，本轮返修更正）
swebench `run_api.py` 的 `calc_cost` 对价格字典**直接索引**：未知模型触发 **KeyError（fail
loudly）**——源码注释明确为避免"静默当免费低估成本"（首轮表述读反，已更正）。该文件不证明
mini 2.4.6 的实际计费路径（litellm 侧待源码核实）。历史轨迹 instance_cost=0.0 仅示记录值为零，
原因不能据此断定。待核实：该模型费用如何记录、未知价格如何处理；用户已定每次运行前确认，
**暂不设金额上限（不再请求设限）**。

## 缺口（3 新增 + 语义更新）

| 缺口 | 内容 | 归属 |
| --- | --- | --- |
| GAP-MINI-SRC-001 | mini 未安装无源码；2.4.6 与 1.17.3 的配置 schema 均不可本地核实 | 需授权获取源码 |
| GAP-MODEL-ADAPTER-001 | model ID 路由、/v1 重复、auth header、流式/usage 解析未验证 | 源码 + 授权连通性测试 |
| GAP-COST-001 | 价格未知；swebench 会低估；记账方式未定 | 用户定上限 + 版本冻结后定 |
| GAP-HARNESS-001（更新） | 选择已定（mini），版本未冻结 | 依赖 GAP-MINI-SRC-001 |
| GAP-MODEL-001（更新） | 选择已定（DeepSeek-V4-Flash），映射未冻结 | 依赖 GAP-MODEL-ADAPTER-001 |
| GAP-VERIFIERSPEC-001（更新） | 字段级已核对；镜像 digest/运行级未定 | P1-00 |

## 下一步需要的授权（明确、有限）

1. **DEC-MINISRC**：获取 mini-SWE-agent 源码/发行包（PyPI；提议 2.4.6，wheel ≈115KB，锁内哈希
   可校验；备选 1.17.3 求行为连续）。用途仅静态核对，不安装不运行。
2. **DEC-CONNECT（可选，另行确认）**：一次模型连通性测试（model ID / baseURL / auth）；
   极小额 API 费用；当前未授权。
3. 沿袭：P1-00 预检（Docker/镜像 digest）；Agent 输入投影生成器（P1 实现项）。

**授权获取不等于缺口已解决，也不等于允许运行 benchmark。** 每次真实运行前仍需按任务说明具体任务
并取得用户明确确认。完成后停止。

## 返修记录（用户复核意见，2026-09-10）

1. **成本逻辑更正**：run_api.py 为直接索引（未知模型 KeyError / fail-loudly），非"按免费计"；
   该文件与 mini 2.4.6 计费路径无关；instance_cost=0.0 原因不可据此断定。evidence/compat/spec
   三处同步更正。
2. **凭据表述收紧**：改为"密钥值未提取、未输出、未持久化"；明确输出截断不是可靠脱敏机制，
   归档/含密钥配置读取今后必须在输出前做白名单键过滤（规程已写入 compatibility.md）。
3. **不再请求费用上限**：用户已明确暂不设金额上限；待核实项改为费用记录方式与未知价格处理，
   保留每次运行前确认要求。
4. **授权请求收敛**：仅申请获取锁定的 2.4.6 wheel（115,037 bytes，锁内哈希校验）做静态阅读；
   不获取 1.17.3，不做连通性测试。
5. **授权状态澄清**（追加）：用户确认的是**版本锁定决定**（2.4.6、115,037 bytes），
   **不是下载授权**。pilot.yaml 中 `version_locked_by_user: true` 与 `download_authorized: false`
   分离表述；DEC-MINISRC 保持待授权状态，建议申请 ≠ 已授权。
