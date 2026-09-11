# mini-SWE-agent 2.4.6 静态阅读交付

日期：2026-09-10。授权：DEC-MINISRC（用户已授权下载并阅读本 wheel；不安装/不运行/不调用模型/不下载依赖）。
P0-07/G0/M1 不自动通过。证据：[mini_2_4_6_static_evidence.json](../reports/quality/mini_2_4_6_static_evidence.json)。

## 实际下载与校验

```text
URL:        https://files.pythonhosted.org/.../mini_swe_agent-2.4.6-py3-none-any.whl
方法:        无认证 HTTPS（urllib），超时 30s，1 MiB 大小上限，独占创建写入
bytes:      115037（与 uv.lock 期望一致）
SHA-256:    a35463c553ac825c7773b03cfa69cd44958e3af20155dcc5711fdf9e4c67cd54（与锁一致）
保存:        data/raw/software/mini_swe_agent/2.4.6/（gitignore 已覆盖 /data/raw/）
读取:        ZIP 原地读取指定成员（未解包到磁盘、未执行任何成员）；15 个成员逐一 SHA 已登记
```

## 已确认（当前版本代码明确表达）

1. **调用链**：swebench argv builder → `minisweagent.run.benchmarks.swebench:main`（typer）→
   `config_spec`（yaml 路径或 `key=value`）`recursive_merge` 层叠，CLI `-m/--model-class` 最后合并
   （最高优先）；`--subset verified` → HF `princeton-nlp/SWE-Bench_Verified`（注意：**princeton-nlp
   旧命名空间**，与 evaluator 侧 `SWE-bench/SWE-bench_Verified` 是两个 id，见 OI-DATASET-NS-001）。
2. **bundled swebench.yaml**：step_limit=250、cost_limit=3.0 USD、cwd=/testbed、per-command 60s、
   docker 环境、`--rm`、container 2h；模型默认 sonnet-4-5 + `drop_params/parallel_tool_calls`。
3. **模型路由**：默认 `LitellmModel`；model_name 直通 `litellm.completion(model=...,
   tools=[BASH_TOOL], **model_kwargs)`；mini 不加前缀、不处理 base_url——全部是 litellm 语义。
   密钥存储路径：`mini-extra config` 写 `.env`（环境变量），litellm 读标准 env vars。
4. **动作协议（2.4.6）**：**结构化 tool call**（`bash` function tool，`{"command":...}`）——
   与 1.17.3 的纯文本协议不同（历史轨迹不能作为 2.4.6 行为证据）；连续 3 次 FormatError 退出；
   重试 tenacity 默认 10 次（4–60s 指数退避），AuthenticationError 等不重试。
5. **成本处理（GAP-COST-001 mini 侧解决）**：`litellm.completion_cost`；**cost<=0 或异常时默认直接
   RuntimeError 崩溃**（critical 日志仅在此非忽略分支输出）；**`ignore_errors` 分支静默返回 0.0——
   无 critical 日志、无标记，不能依赖该日志发现计费缺失；且未计价调用的累计恒为 0.0，agent
   cost_limit 与全局限额对其永不触发（限额保护失效）**。自定义模型正规路径 =
   `litellm_model_registry`（本地 JSON 注册真实价格，限额随之有效）。两级限额：agent 级
   cost_limit（下次查询前检查）+ 全局 `MSWEA_GLOBAL_COST_LIMIT`。
6. **轨迹与凭据落盘（首次运行前阻塞项）**：轨迹 `info.config.model` = `LitellmModelConfig`
   **逐字序列化（含 model_kwargs 全部字段）**——若把 api_key/api_base 放进 model_kwargs，
   **必然写入 traj.json**；`minisweagent.log`（debug 级 messages 转储）同风险。缓解（有源码依据）：
   走 env-var 认证（`mini-extra config`/标准 litellm env），model_kwargs 保持干净。轨迹每条消息
   extra 含完整 litellm response dump（usage/finish_reason/tool_calls）——逐调用 token 记账数据可用。
7. **执行环境（字段适配登记）**：mini 读 `instance.image_name / docker_image`（皆无则按
   instance_id 推导 `swebench/sweb.eval.x86_64.<id>:latest`），**不读 evaluator 消费的 `image`
   字段**——两工具用不同数据集列；试点行的字段值是否一致未核实，不能概括为"自动使用 evaluator
   同一镜像"；即便同名，双方均 `:latest`，**digest 一致性须首次运行前逐字段核实/固定**。
   docker 机制（`--rm`、/testbed、BASH_ENV）已确认。
   **Agent 输入（配置条件性）**：默认 `agent.run(task)` 仅传 `problem_statement`；但可选
   `run.env_startup_command` 会用**整个 instance dict**（含参考答案字段）渲染 Jinja——隔离是
   配置条件性的，试点必须保持该项不设；不能声称参考答案已全链路无条件隔离
   （F-CALLCHAIN-001 修正）。

## 可设计但未运行（提案，非运行授权）

DeepSeek-V4-DeepSeek-V4-Flash 接入配置模板（**未执行**；每字段有源码依据；占位符非凭据）：

```yaml
# custom_config.yaml（层叠于 bundled swebench.yaml 之后，-c 传入）
agent:
  cost_limit: 3.0          # F-BUNDLED-CONFIG-001；用户无金额上限，运行前逐次确认
  step_limit: 250          # 同上
model:
  model_name: "<LITELLM_PREFIX>/deepseek-v4-flash"   # OI-LITELLM-DEEPSEEK-001：前缀待 litellm 核实
  model_kwargs:
    drop_params: true      # F-MODEL-ROUTING-001
    api_base: "<VOLCANO_GATEWAY_URL>"  # 经 model_kwargs 直通 litellm；注意 /v1 重复风险（OI-LITELLM-DEEPSEEK-001）
  # 认证不走 model_kwargs：使用环境变量（F-TRAJECTORY-PRIVACY-001 缓解）
  cost_tracking: "ignore_errors"   # 或提供 litellm_model_registry 注册价格（OI-PRICE-001，二选一待定）
```

环境变量（仅名称）：litellm 标准 key 变量（如 `OPENAI_API_KEY`，具体名随前缀定）。

## 仍阻塞

| 项 | 内容 | 何时解决 |
| --- | --- | --- |
| OI-LITELLM-DEEPSEEK-001 | 网关的 litellm 前缀/base_url/auth 变量名、/v1 行为 | 需 litellm 源码/文档或授权连通性测试 |
| OI-PRICE-001 | 价格注册（registry JSON，限额有效）或 ignore_errors（**静默 0.0 无日志，限额失效**，须独立"成本未知"标记/核算） | 运行前必须二选一，否则首次查询即 RuntimeError |
| 凭据落盘 | model_kwargs 含密钥必落轨迹；须走 env-var 路线并在首次运行前验证 | 首次运行前阻塞项 |
| OI-DATASET-NS-001 | princeton-nlp vs SWE-bench 数据集 id 等价性 + revision 固定 | 任务身份等价确认 |
| 镜像字段适配 | mini 读 image_name/docker_image，evaluator 读 image——试点行字段值一致性未核实；digest 一致性要求 | OI-DATASET-NS-001 扩展，首次运行前 |
| 镜像 `:latest` | digest 未固定 | 沿袭，P1-00 |

## 后续动态验证（须单独授权）

模型连通性测试、镜像拉取/构建、真实 task 运行——均不在本授权内；每次运行前列明任务与风险并单独确认。

## 文件变更

新增：本文件、`data/catalog/mini_2_4_6_artifact.yaml`、
`reports/quality/mini_2_4_6_static_evidence.json`、wheel 本体（gitignore 内）。
增量更新：`docs/pilot_harness_model_compatibility.md`、`workload_catalog/pilot.yaml`、
`docs/pilot_execution_spec.md`、`reports/quality/g0_review.md`。
未修改：分析代码、测试、references、用户配置、原始任务记录。

## 返修记录（用户复核意见，2026-09-10）

1. **ignore_errors 无 critical 日志**：该分支静默返回 0.0（日志仅非忽略分支输出）；未计价调用
   累计恒 0.0 使限额保护失效。evidence F-COST-001 / compatibility 成本行 / delivery 已更正为
   "静默 0.0 + 独立成本未知标记要求"。
2. **镜像字段适配**：mini 读 image_name/docker_image（皆无则推导），不读 evaluator 的 image 字段；
   删除"自动使用 evaluator 同一镜像"表述，登记字段级一致性核实与 digest 固定要求
   （F-ENVIRONMENT-001 / OI-DATASET-NS-001 扩展）。
3. **输入隔离为配置条件性**：默认仅 problem_statement；可选 env_startup_command 以整个 instance
   渲染。白名单设计保留且加强（明确不得设置该项）；不再声称全链路无条件隔离
   （F-CALLCHAIN-001 修正）。
