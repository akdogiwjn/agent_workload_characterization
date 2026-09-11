# PREP-01 首次运行准备包交付

日期：2026-09-11。批次：PREP-01。状态：**准备包交付，READY_FOR_REVIEW；执行未授权；
P0-07/G0/M1/P1-00/G1 不因本批通过**。

## 完成了什么

| 工作包 | 交付 |
| --- | --- |
| A1 安全任务投影 | `runners/preparation.py`：`load_task_record`（hash+instance 校验）、`agent_view`（白名单仅 instance_id + problem_statement，新字段默认不传播）、`environment_view`、`evaluator_view`（仅字段校验，不复制 patch/脚本内容）、`reject_startup_command` |
| A2 镜像/加载计划 | `image_plan`（mini 读 image_name/docker_image/推导 vs evaluator 读 image 的显式适配；冲突拒绝；digest=None 不捏造；实测两名字在 tag 级一致）；`local_task_input_route`（本地单记录 wrapper 路线，接口已写，本批不实现 wrapper） |
| A3 模型/费用/重试 | `check_model_config`（敏感键全域拒绝；api_base/auth 仅环境变量名；model_kwargs 白名单）；`record_call`（usage/cost 分离；cost_status=unknown/error 不当免费不丢 usage；原生 0.0 保留来源值）；`retry_policy`（三层：attempt=1 / 外层 0 / mini 内部默认 10 次须运行时 env 禁用——离线不可确认，列为运行前检查）；`limits_plan`（cost_limit 标注 mini 默认非用户预算；ignore_errors 下限额无效） |
| B 只读预检 | `collectors/preflight.py`：7 探针（python/packages/cpu_mem_disk/cgroup/process/perf/docker）；逐探针 5 s 界、单项失败不阻断；状态四值 observed/unavailable/permission_denied/not_checked；Docker 仅本地 socket（DOCKER_HOST 指远端即拒绝 not_checked）；不读 /proc/*/environ |
| C 离线测试 | `tests/test_preparation.py` 35 项：8 组矩阵全覆盖（单任务输入/答案隔离 canary/凭据保护含异常路径/模型准备/费用记录四种形态/镜像适配含冲突与无 digest/预检降级含超时与远端 context/输出安全含软链接与不覆盖 + CLI 无 --execute） |
| CLI/报告 | `prepare-pilot` 命令（默认只读 stdout；`--output-dir` 才写包；无 `--execute`）；`reports/preparation/PREP-01/`（plan/preflight/offline_checks/summary/manifest，独占创建不覆盖） |
| 审批清单 | `docs/first_run_approval.md`：3 个批准项（环境安装/连通性 smoke/真实任务），每项含规模、预算、未决原因；8 项运行前检查 |

## 实际执行的命令

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests -v        → 210 OK（175 基线 + 35 新增）
（项目外 cwd：cd /tmp && PYTHONPATH=<abs src>:<abs tests> unittest discover → 210 OK）
PYTHONPATH=src python3 -B -m agent_workload_characterization prepare-pilot --output-dir reports/preparation/PREP-01 → exit 0
git diff --check                                                   → OK
```

真实任务记录在 `prepare-pilot` 中只读核对（hash/instance_id/problem_statement 校验 + 白名单投影），
未复制 gold/test patch 到任何报告。主机预检在上述命令中实际运行（7/7 observed，见 preflight.json）。

## 哪些接口仅 fake 验证

- 模型路由：合成端点/模型映射检查通过；**litellm 真实路由（前缀/base_url/auth）未验证**
  （OI-LITELLM-DEEPSEEK-001）——fake 成功不构成真实兼容
- 假 transport 的 `record_call`：usage/cost/error 路径已测；**mini 真实计费/重试/日志行为未执行**
  （"mini 凭据落盘验证已通过"不在本批结论内）
- Docker 预检仅本地 socket 状态与 client version；**daemon 容器可用性、镜像拉取未验证**

## 主机限制（实测 preflight 结果）

全部 7 探针 `observed`（cgroup v2 控制器可读、perf 二进制存在、Docker 本地 socket 在）。
这是**降级证据**：不宣称 PMU 可用、容器可运行、或已测任何 workload。详细字段见
`reports/preparation/PREP-01/preflight.json`。

## 关键未决项（下一批输入）

1. 批准项 1（安装 mini 2.4.6 + 依赖到独立 venv；下载/磁盘开销已列）
2. 批准项 2（连通性 smoke：需用户给出网关模型标识或授权探测）
3. 批准项 3（真实任务：依赖 1+2；wrapper 实现属 P1-07 下一批）
4. 运行前检查 8 项（见 first_run_approval.md；含 digest 固定、重试禁用验证、凭据注入验证）

## 文件变更

新增：`runners/preparation.py`、`runners/report_writer.py`、`runners/__init__.py`、
`collectors/preflight.py`、`collectors/__init__.py`、`tests/test_preparation.py`、
`data/catalog/pilot_run_config.yaml`（合成模板，无凭据）、`reports/preparation/PREP-01/`（5 文件）、
`docs/first_run_approval.md`、本文件。
修改：`src/.../cli.py`（prepare-pilot 入口）。
未修改：adapter/macro 分析代码、references、旧工程、原始任务记录、历史报告包。

## 自检

- YAML/JSON 可解析；报告包 manifest 覆盖 4 文件（不含自身）；独占创建验证（重复写被拒）
- 敏感扫描：无密钥/凭据模式（合成 fixtures 用 SYNTH 标记；真实配置未读取）
- `plan.json` 含 `execution_authorized: false`、`runtime_compatibility` 6 项未决、`next_authorizations` 3 项
- 项目外 cwd 全量测试通过（不依赖工作目录）

完成后停止，等待评审。不自动安装、联网或运行任务。

## 返修记录（用户安全复核意见，2026-09-11 第二轮）

### 本批阻塞项（已修复 + 回归）

1. **输出保护可被绕过**（B1）：`report_writer.guard()` 重写——锚定可信项目根
   （resolve(strict=True)）；`reports/preparation` 根自身不得为 symlink 且真实路径须在项目内；
   目标以**完全解析后的真实路径**判定归属（子目录 symlink 逃逸失效）；接入审计 catalog 的
   全部旧源根保护（roots + sources locator，catalog 缺失时静态保护仍生效）；相对路径锚定到
   项目根而非 cwd。回归：`reports_root_symlink`、`subdir_symlink_to_legacy`、
   `catalog_legacy_roots_protected`、`writer_full_path_success` 四项完整 writer 路径测试。
2. **凭据保护覆盖实际输出路径**（B2）：`_validate_env_name`（合法 NAME 正则——
   `FAKE_CANARY=value`、非法字符、payload 一律拒绝，forward_env 逐项验证）；
   `_reject_url_values`（userinfo URL 全域拒绝）；`_sanitize_usage`（usage 白名单数值投影——
   第三方回显的 `api_key_echo`/`endpoint` 等键不落记录）；`_sanitize_error`（错误仅保留类型级
   摘要 + `<sanitized>`，原始消息中的密钥/URL 不保留）。回归：`env_name_with_value_rejected`、
   `url_with_userinfo_rejected`、`usage_whitelist_projection`、`error_sanitized`、
   `canary_end_to_end_through_report`（canary 经 writer 进入最终报告包的全链路验证）。

### 同批顺手修正（已修复 + 回归）

3. **镜像比较规范化**：`_normalize_image_ref` 比较**完整引用**（registry+namespace+repo+tag），
   仅允许 docker.io 默认前缀等价与 Docker Hub official library/ 隐含——不同 registry/namespace
   同 tag 不再判 match。回归：`different_registry_same_tag_not_match`、
   `different_namespace_same_tag_not_match`、`dockerhub_prefix_equivalence_allowed`、
   `tag_difference_not_match`。
4. **request_id 关联**：`record_call(..., request_id=)` 由调用方传入并保留（默认空串仅向后兼容）。
   回归：`request_id_preserved`。
5. **报告证据完整**：`plan.json` 保存脱敏 `model_plan`（结构上无密钥——上游拒绝任何敏感键）；
   `offline_checks.json` 由 preparation 实际结果派生（`digest_pinned`/`litellm_routing_verified`
   等随输入变化），不再硬编码。回归：`plan_includes_model_plan`、
   `offline_checks_derived_not_hardcoded`（含 pin digest 后翻转为 True 的对照）。

### 附带代码缺陷（返修中发现）

- `check_model_config` 中 `for name in ...` 循环变量遮蔽 `model_name` 导致返回错误值——已改名并回归覆盖。

### 验证

```text
unittest（项目内）                → 228 OK（210 + 18 新增回归）
unittest（项目外 cwd，绝对路径）    → 228 OK
prepare-pilot（重新生成报告包）     → exit 0；offline_checks 派生值随输入翻转验证
git diff --check                  → OK
```

安装、镜像 digest、网关路由、第三方日志行为仍留在运行前检查清单，不因本批修复视为已解决。

## 返修记录（用户安全复核意见，2026-09-11 第三轮）

### 泄漏路径收紧（两点）

1. **错误分类固定白名单**：`_sanitize_error` 不再从原文正则截取"异常类型"
   （`FAKE_SECRET_CANARY_42` 这类标识符样文本曾被原样保留）。改为
   `_ERROR_TYPE_WHITELIST`（约 24 个已知异常类型）**精确匹配** `error.split(":")[0]`；
   无法识别一律输出通用 `error:<sanitized>`。回归：
   `error_unknown_text_collapses_to_generic`、`error_whitelist_type_preserved`。
2. **usage 嵌套键固定白名单**：`_sanitize_usage` 的嵌套 dict（如
   `prompt_tokens_details`）原先只检查值是否为数字——任意键名
   （`{"FAKE_SECRET_CANARY_42": 1}`）被保留。改为 `USAGE_DETAIL_WHITELIST`
   （cached_tokens/reasoning_tokens 等 OpenAI 明细键）固定键集投影。
   回归：`usage_nested_arbitrary_key_dropped`。
3. **端到端 canary 扩展**：上述两个反例已并入既有的
   `canary_end_to_end_through_report`——canary usage（嵌套假键）、canary error
   （假类型文本）经 writer 进入最终报告包，断言两个 canary 均不出现，且错误为
   通用 `error:<sanitized>` 标签。

### 验证

```text
unittest（项目内）              → 231 OK（228 + 3 新增）
unittest（项目外 cwd 绝对路径）  → 231 OK
prepare-pilot 重新生成报告包     → exit 0；报告包敏感扫描（含 FAKE_SECRET 模式）通过
git diff --check                → OK
```
