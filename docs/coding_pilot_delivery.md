# RUN-01 交付：关口 A（离线开发）

日期：2026-09-12。状态：**RUN-01 全程完成：A（七轮离线返修）→ B（arm64 镜像/canary r7/停止链/gold 验证）→ G0 PASSED → C 一次真实 attempt 已执行（run_id `20260912T125202Z-840e49`，resolved=true，147 s，预算内，见 §5.18）并交付。单样本无代表性；G1 不自动通过。按约定停止。**

依据：[RUN-01 任务书](coding_pilot_handoff.md)。本文件记录关口 A 的实际操作、验证结果，以及 B/C 审批清单。不冒充真实 Runner 已跑通：**所有测试数据均为 synthetic（fake model + fake Docker + fake counters），无任何 benchmark_real 观察**。

## 1. 关口 A 实际完成内容

### 1.1 代码交付

| 模块 | 内容 |
| --- | --- |
| `runners/coding_pilot.py` | Runner 编排：`BudgetLimits`/`BudgetTracker`（请求/step/每请求输出 token/阶段 wall/总 wall/新产物字节，全部硬限）、`WallWatchdog`（deadline 到点 SIGKILL 全部已注册真实子进程，支持 cancel）、`FakeVerifier`/`SwebenchVerifierRunner`（骨架，执行需 B/C 授权）、`guard_run_dir`（data/raw/generated 锚定 + symlink 逃逸 + 保护树 + 独占创建）、`CodingPilotRunner`（execution/evaluation/archive 三阶段独立状态机；最终计数器读取先于容器拆除；失败路径也先归档再清理；cleanup 仅按 run_id 身份匹配） |
| `runners/mini_agent_adapter.py` | `FakeAgentHarness`（合成行为脚本：模型调用/工具调用/嵌套重试模拟/真实阻塞子进程供 watchdog 击杀）；`MiniSweAgentHarness`（真实 mini 2.4.6 适配：instance 投影白名单仅 `instance_id`+`image_name`，payload 递归拒绝 patch/test_patch/F2P/P2P/eval_script；子进程引导脚本走 mini Python API `get_sb_environment`+`get_agent`+`agent.run`，**不用** bundled swebench_single CLI（其经 HF `load_dataset` 全量加载）；执行需 gate C 授权，A 批仅构造与隔离检查） |
| `runners/container_runtime.py` | `FakeContainerRuntime`（合成容器生命周期/计数器/身份匹配清理/外来容器不动）；`DockerCliRuntime`（真实 docker CLI：`--network none` 默认断外网、`--memory/--cpus` 限制、run/exec/rm argv 构造、按 `awc-run01-<run_id>-` 名称过滤的 cleanup；**未授权即拒绝执行**，A 批仅 argv 构造经测试） |
| `collectors/semantic_recorder.py` | 语义事件 recorder：单一 monotonic clock domain + UTC anchor；`duration_s()` 跨 clock domain 相减直接 `ClockError`；未闭合事件保留 `unclosed`+null（右删失，不补零）；敏感键/凭据样式值在落盘前拒绝；usage 白名单投影、error 固定白名单类型分类（复用 PREP-01 三轮评审语义）；JSONL append-only，seal 后不可写 |
| `collectors/resource_sampler.py` | 资源采样：`CgroupV2FileReader`（cpu.stat usage_usec、memory.current/peak、io.stat 逐设备求和；读取失败保留 null+原因，不填 0）；`FakeCounterReader`（脚本化 reset/missing/zero）；`ResourceSampler`（边界计数器 + gauge 采样双轨；`cpu_core_seconds()` 统一 core-seconds、reset 检测为 null+reason 而非负增量；memory current/内核 peak/采样 max 三数分开，无 memory.peak 时采样 max 标 `sampled_lower_bound`；io 缺失标 `unsupported_or_missing`；实际采样时刻与 gap 记录；collector 自身开销单独声明在被测 scope 之外） |
| `analyzers/resource_summary.py` | 小型摘要：逐 scope wall/CPU core-seconds/证据类型/avg cores（显式标注非效率指标）/memory 三口径/I-O null 保留；LLM 请求数与 Tool 数分开；逐指标 coverage n_valid/n_applicable；source_type 透传并强制 synthetic 标注；limitations 明示 scope 峰值不可相加、父子 scope CPU 不可直接求和 |
| `tests/test_coding_pilot.py` | 45 项合成回归（详见 1.3） |
| `workload_catalog/coding_pilot.yaml` | 有效配置/预算提案/授权阶段（无秘密；`execution_authorized: false`；digest=null 待 B 固定） |
| CLI `plan-coding-pilot` | 只读验证 catalog（精确凭据键检查——子串 'token' 会误伤 output_tokens_per_request 等计数预算字段；execution_authorized 必须为 false；digest 必须为 null；预算字段齐备）；不写文件 |

### 1.2 接口核对（只读，未执行第三方代码）

- mini 2.4.6（ENV-01 venv 源码）：`run/benchmarks/swebench.py` 的 `get_sb_environment(config, instance)` 仅从 instance 读 `image_name`/`docker_image`（缺失时按 instance_id 推导）；`agent.run(instance["problem_statement"])` 只收 problem_statement。因此 wrapper 以 **instance 投影（instance_id + image_name）** 调用 Python API 即可绕过 HF 全量加载且不把 record 交给 mini。`run.env_startup_command` 会以 Jinja 渲染整个 instance——保持不设（PREP-01 `reject_startup_command` 语义延续）。
- SWE-bench evaluator（references/repos/SWE-bench，实际 HEAD 核对为 `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`，与任务书固定 commit 一致，未更新）：`harness/utils.py:make_test_spec` → `harness/run_evaluation.py:run_instance`（创建容器/apply patch/运行 eval_script/清理）→ `harness/grading.py:get_eval_report`（resolved = F2P ∧ P2P；`infra_failure` 与任务失败分离；SUITE_RAN 防未运行误判）。B 批如需执行，在项目外独立执行副本使用该 commit。

### 1.3 测试与验证（实际执行）

```text
PYTHONPATH=src python3 -B -m unittest tests.test_coding_pilot -v   → 59 OK（45 + 14 返修回归）
PYTHONPATH=src python3 -B -m unittest discover -s tests            → 319 OK（260 基线 + 59）
项目外 cwd 绝对路径 discover（-s tests -t tests）                   → 319 OK
PYTHONPATH=src python3 -B -m agent_workload_characterization plan-coding-pilot → exit 0
python3 -B -m py_compile <全部新模块>                               → OK
git diff --check                                                    → OK
敏感扫描（sk-/api_key=/Bearer 模式，排除显式 SYNTH canary）          → 无命中
```

（关口 B 执行后新增 9 项测试：CgroupV1ReaderTests 6 项 + canary/platform 3 项；当前全量 328 项，见 §5。）

45 项回归按任务书 §6 五组最低回归覆盖：

1. **隔离与输出保护**（9 项）：mini payload 不含 gold/test patch、F2P/P2P、eval_script canary；嵌套答案注入被拒；recorder 拒绝凭据键与凭据样式值；usage 嵌套假键丢弃、error 折叠为 `AuthenticationError:<sanitized>`；guard 拒绝 data/raw/public、symlink 逃逸、已存在目录。
2. **全路径与状态分离**（10 项）：成功（三状态 ok/ok/ok，run 目录五文件齐全）；agent_error→evaluation=not_run；no_candidate；verifier_timeout 时 execution 保持 ok；verifier wall 预算超限→verifier_timeout；patch_apply_failed；verifier infra_failure 与 execution 分离；agent 运行时 infra_failure；archive 失败（samples 序列化异常）时 events.jsonl 仍保留。
3. **预算与 watchdog**（7 项）：请求/step/execution wall/每请求输出 token 四类硬限各自触发；嵌套重试（同 step 双请求）被计数入请求预算且 `nested_retry_detected` 记录为 budget 事件与 metadata 字段（不是"免费重试"）；watchdog 对真实阻塞子进程 SIGKILL（returncode -9）后 execution=watchdog_timeout 且证据文件存活；cleanup 仅清本次 run_id 容器，外来容器原样保留。
4. **计量语义**（8 项）：CPU 单位（usage_usec 差/1e6=core-seconds）；reset→null+`counter_reset_detected`；missing→null+原因；**真实零保留**（cpu=0→0.0 而非 null）；无内核 peak 时采样 max 标 `sampled_lower_bound`；多 scope 峰值/CPU 不产生求和字段；io 缺失保留 null；不同 clock domain 的事件相减抛 ClockError、unclosed 返回 null。
5. **生命周期**（6 项）：创建→基线→执行→最终快照→导出→清理全流程（manifest 哈希逐一核对；agent/verifier/host_agent_runtime/collector 四 scope 齐备）；失败路径证据先于清理保留（events 首尾为 run open/sealed）；两次 attempt 独立目录均保留；**最终计数器读取发生于容器拆除之前**（fake runtime read_log 证明 boundary 读时容器状态 running）；未授权 DockerCliRuntime 拒绝执行；docker run argv 构造（--network none、--memory、--cpus）静态核对。

另有 analyzer/CLI 5 项（summarize_run synthetic 标注、报告独占创建、CLI 合法/越权/含密配置三分支）。

### 1.4 明确未做 / 未证明

- 真实 mini 子进程执行、真实 Docker 容器、真实 cgroup 读取、真实模型请求：**全部未执行**（`authorized=False` 硬拒）。fake 通过不构成真实兼容性证明。
- verifier 真实链路（make_test_spec→run_instance→get_eval_report）为接口骨架，B/C 批实现。
- `DockerCliRuntime.read_counters` 的 cgroup 路径解析（docker inspect → /sys/fs/cgroup）为待实现项（B 批 canary 验证时完成）。
- 正式 `data/raw/generated/RUN-01-*/` 与 `reports/resource/RUN-01-*/` 目录**未创建**：A 批无真实采集，合成数据只存在于测试临时目录，不冒充采集产物。
- mini `model_kwargs` 序列化、litellm 异常回显等第三方动态行为以 ENV-01/SMOKE-01R 已验证结论为准，本批不重复执行。

## 2. B 审批清单（环境准备与无 API 验证；批准后执行，到限即停）

### B-1 evaluator 独立执行副本

| 项 | 内容 |
| --- | --- |
| 源 | 本地 `references/repos/SWE-bench`（HEAD `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`，只读不动） |
| 方式 | 复制到项目外独立执行目录（如 `data/raw/software/swebench-eval-02e7a74/`，约 87 MB 源码拷贝）；**不在 references 内安装、写日志或修改** |
| 依赖 | swebench 依赖（docker SDK 等）安装进**独立 venv**（与 mini venv 分开），预计 200–400 MB 下载、安装后 <1 GB；已有依赖（本机 pip 缓存/wheel）优先复用，不重复安装 |
| 磁盘/下载上限（待批准） | 下载 ≤500 MB；新增磁盘 ≤1.5 GB |
| 验证 | `make_test_spec` 对固定 record 的字段级构造成功（不运行容器）；容器资源参数/自动 pull/资产下载/镜像删除与日志清理行为逐一核对并按需禁用（禁止隐藏联网与广泛 cleanup） |

### B-2 目标镜像

| 项 | 内容 |
| --- | --- |
| 完整引用 | `swebench/sweb.eval.x86_64.django_1776_django-16485:latest`（docker.io） |
| 平台 | x86_64（本机架构待 B 批 `uname -m` 核对后确认） |
| 获取方式 | **只 pull 预构建镜像，不 build**；不可得或需 rebuild 时停止并单独说明 |
| 大小 | **B 批先用 `docker manifest inspect`（只读）查询层大小后填写实际估计**；不沿用未实测的"1～3 GB"作为保证 |
| 待批准上限 | 压缩下载 ≤3 GB、展开存储 ≤5 GB（可按 manifest 查询结果调整后再批） |
| digest 固定 | 批准后 pull 前后 `docker images --digests` 记录 RepoDigest/image ID；Agent 沙箱与 verifier 容器**同 digest** 引用；运行期禁自动拉 latest（DockerCliRuntime 以 digest 全引用启动） |

### B-3 网络与代理边界

- 容器预检默认 `--network none` 断外网（DockerCliRuntime 默认值，A 批已实现并测试）。
- 批准代理（如 SMOKE-01R 的 `http://127.0.0.1:22111`）仅限宿主模型进程的指定路径/用途；**不自动带给 Agent 工具容器或 verifier 容器**。
- 首次真实容器若确需外网（如 pip 安装），在 C 清单单独列出再批。
- `LITELLM_LOCAL_MODEL_COST_MAP=True` 保留（防 litellm 拉远端价格表），C 批确认。

### B-4 容器计量 canary（不调用模型，不执行 Django 任务/verifier）

| 项 | 值 |
| --- | --- |
| 数量 | 2 个（agent scope 1 + verifier scope 1），顺序运行 |
| 内容 | 短时 CPU 工作（busy-loop ≤5 s）+ 固定小内存分配 + ≤16 MiB 文件写入/读取 |
| 单 canary | ≤30 s；合计 ≤3 分钟 |
| 记录 | cgroup cpu.stat 累计增长（core-seconds 口径）、memory.current/peak、io.stat、container ID/cgroup 路径定位方法、最终读取时点（拆除前） |
| 核对 | 同 scope 两种独立读取（cgroup 文件 vs `docker stats --no-stream` 单次快照）交叉核对 CPU 单位/范围，记录可测开销与差异 |
| 产出 | `reports/resource/RUN-01-B-canary/`（scope 摘要 + 覆盖/局限）；不可测项交付降级边界，不标 ready |
| 清理 | 仅 `awc-run01-<canary-run-id>-` 名称匹配的容器；残留记录在案 |

### B-5 预算提案

- B 批 wall 上限 **15 分钟**（含 evaluator 副本准备、镜像 pull、canary）；到限停止，不自动切源/重拉/构建。
- 磁盘/下载上限见 B-1/B-2，按实际查询值提交后由用户批准。
- 不隐藏 setup 时间；B 实际用量在交付文档中如实记录。

## 3. C 审批清单（一次真实 Agent 任务；B 完成后集中 G0 评审，用户明确批准再执行）

### 3.1 G0 评审前置

A/B 完成后集中整理现有 G0 五条证据与实际试点配置，提交一次评审；**C 前确认 Gate 决议与执行授权**。本批 A 的离线证据（隔离/预算/计量语义测试）是 G0 "首个资源试点的任务、配置、可测边界和预算确定"一项的输入，不构成 G0 通过。

### 3.2 执行参数（已于 2026-09-12 以实际实现登记——见任务书 §8.2，非猜测命令）

实际入口、解释器、双旗标执行命令、配置身份与已知缺口已登记于 [任务书 §8.2](coding_pilot_handoff.md)。入口为 `runners/c_entry.py`：默认离线计划；执行需 `--execute --i-approve-the-c-run` 双旗标（用户授权行为，配置文件不能替代）+ 凭据环境（缺则在任何容器/子进程启动前拒绝）。

| 项 | 建议待批准值 |
| --- | --- |
| 任务/attempt | `django__django-16485`；1 task、1 attempt（record SHA `762de270...`，只读） |
| Harness/模型 | mini-SWE-agent 2.4.6（ENV-01 venv）/ `openai/deepseek-v4-flash`；凭据仅环境变量 `PILOT_API_BASE`/`PILOT_API_KEY`，不进 argv/config/日志 |
| 模型请求硬上限 | 30 次（多轮；协议纠正提示产生的新调用计入；失败不重试） |
| 每请求输出上限 | 4096 tokens（自有 wrapper 注入，C 批以出站请求体断言） |
| Agent step 上限 | 30（与请求分别计数；mini step 语义=一次 agent loop 迭代） |
| Agent wall | 25 分钟（watchdog SIGKILL 硬停） |
| Verifier | 5 分钟且受剩余总预算限制；无可验证 candidate 不强跑 |
| 总执行 wall | 30 分钟（初始化/导出计入；setup/pull 不计入） |
| CPU/内存 | Agent 沙箱与 verifier 顺序运行，各 4 CPU/8 GiB（容器限制）；宿主 runtime/collector 开销另列并说明限制方式 |
| 新产物 | **限定范围超限检测停机机制（非绝对硬配额）**：5 GiB 仅为 run_dir 树检测阈值，0.25 s 为配置轮询间隔，非停机延迟上界。r7 已实测本机不支持 `--storage-opt size=6g`；容器可写层不受此阈值/配额限制，删除仅事后回收，存在磁盘峰值与超调风险。批准前展示可用空间并明确接受此风险；详见 [最终清单 8.3](coding_pilot_handoff.md#83-本次须明确接受的降级与风险) |
| 镜像 | B 批固定的 digest；Agent 与 verifier 同 digest、独立容器 |
| 费用 | 未设金额上限；预计总 token 未知；请求数×单请求上限只是输出上界非费用上界；amount=null、usage 逐请求保留 |
| 停止规则 | 任一硬限即停；不恢复同一任务继续跑；后续重试另批；取消远端请求不保证停止计费 |
| 输出 | `data/raw/generated/RUN-01-<collection>/<run_id>/`（candidate/轨迹/事件/采样/metadata/manifest）；`reports/resource/RUN-01-<batch>/` 摘要 |
| 残留清理 | 仅本次 run_id 身份匹配容器/目录；失败样本与全部 attempts 保留 |

执行前确认最终无秘密命令一次；运行中只给阶段状态，不输出完整 prompt/密钥/环境/原始 traceback。任务 resolved=false 不自动导致工程验收失败。

2026-09-12 文档收尾：本节预算仍待批准；最终入口/配置登记与审批流程以 [任务书第 8 节](coding_pilot_handoff.md#8-c-审批清单一次真实-agent-任务) 为准。当前 CLI 仅支持离线 plan；组件已验收不表示 C 命令已组装/冻结。第 5 节保留历史交付原文；本补充不执行 C，也不追认授权。

## 4. 文件变更

新增：`runners/coding_pilot.py`、`runners/container_runtime.py`、`runners/mini_agent_adapter.py`、`collectors/semantic_recorder.py`、`collectors/resource_sampler.py`、`analyzers/resource_summary.py`、`tests/test_coding_pilot.py`、`workload_catalog/coding_pilot.yaml`、本文件。
修改：`src/.../cli.py`（`plan-coding-pilot` 入口）。
未修改：references、旧数据、历史报告包、PREP/ENV/SMOKE 代码、`.venvs`。

## 5. 关口 B 执行记录（2026-09-11，用户已批准）

执行时段 11:04–11:22 UTC，**实际 wall ≈ 18 分钟**（超 15 分钟提案约 3 分钟；超因：canary 需 5 轮迭代适配本机 cgroup v1 差异，每轮 25 s，均已保留为证据 r1–r5）。无模型 API 调用；无 Django 任务/verifier 执行；清理仅限 `awc-run01-*` 名称前缀，无残留（`docker ps -a --filter name=awc-run01-` 为空）。

### 5.1 预检发现（改变执行方式的事实）

| 事实 | 影响 |
| --- | --- |
| 主机架构 **aarch64**（kernel 6.6 oe2403） | 目标镜像仅 **amd64** manifest（无 arm64 变体）；pull 必须 `--platform linux/amd64`，运行经 **qemu-x86_64 binfmt**（已启用）。C 批若经该路径，CPU 数字为模拟执行口径（r5/r6 原始测量：同 12 s busy loop 下 qemu 15.68 core-s vs native 12.25 core-s；**不据此推算单位工作开销倍率**——忙循环未统计完成工作量）。后经 §5.7/§5.8 改用官方 arm64 镜像，native 口径 |
| docker 25.0.5，cgroupfs driver，**cgroup v1** | PREP-01 preflight 的 "v1-or-unknown" 实为 v1；实现并实测 `CgroupV1FileReader`（cpuacct.usage ns / memory.usage+max_usage_in_bytes / blkio.throttle.*） |
| 代理（127.0.0.1:22111）可用 | pip 走代理；docker pull 走 daemon 直连（实测 ~4.2 MB/s，未改任何 daemon 配置） |

### 5.2 B-1 evaluator 独立副本与依赖

```text
副本: git archive 02e7a74ffd0b707aab73d203fe87bdc7c76afc8e → data/raw/software/swebench-eval-02e7a74/（9.3 MB，无 .git）
venv: .venvs/swebench-eval-02e7a74（独立，79 包，433 MB；pip --find-links ENV-01 wheelhouse 复用 + 代理补缺，--no-cache-dir）
离线验证: make_test_spec(record) 成功构造 TestSpec——image/eval_script(1453B)/log_parser=parse_log_django/eval_type=pass_and_fail/F2P=1/P2P=9 全部就绪（GAP-VERIFIERSPEC-001 运行前字段级核对完成；eval_script 仅构造未执行）
references/repos/SWE-bench: 零修改（git status 干净，HEAD 02e7a74 复核一致）
```

run_evaluation 行为核对（源码阅读，C 批须落实的开关）：`run_instance` 默认在容器内 apply patch + 跑 eval_script；容器资源参数、自动 pull、资产下载与清理的具体默认值在 C 批实现 `SwebenchVerifierRunner` 时逐一固定并禁用自动行为（本批未运行该代码路径）。

### 5.3 B-2 镜像获取与 digest 固定

```text
manifest 查询（docker CLI 经代理，只读）: index 含 amd64 + unknown(attestation)；无 arm64
amd64 层: 10 层压缩 1183.3 MiB
pull: docker pull --platform linux/amd64 ...（daemon 直连 4m44s，~4.2 MB/s）
RepoDigest: sha256:570eb343d44b9ef6ddd5bfffbbe0c80217c926c79f164205cc328b51c5676020
Image ID:   sha256:5fe07904aeca850bb40f45087f3cf47c38512d0661ee9c329530681b6aaa4f66
展开大小: 3.07 GB（< 5 GB 上限）；压缩下载 1183 MiB（< 3 GB 上限）
```

首次 pull 未带 `--platform` 被 daemon 以 `no matching manifest for linux/arm64/v8` 拒绝——作为架构事实证据保留。Agent 沙箱与 verifier 将按同一 RepoDigest 引用（canary 已按 digest 全引用启动并成功）。

### 5.4 B-4 容器计量 canary（无模型；5 轮迭代全部保留）

最终轮 r5（`reports/resource/RUN-01-B-canary-r5/`，run_id RUN01BCANARY-20260911T112150Z-534e71，总 wall 25.5 s）：

| 指标 | canary A（native arm64，python:3.11-slim 本地已有） | canary B（目标镜像 digest，qemu amd64） |
| --- | --- | --- |
| workload | 5 s busy-loop + 128 MiB 内存分配 + 16 MiB 写读+sync | os-release + 12 s busy-loop + 8 MiB 写读+sync |
| rc | 0 | 0 |
| CPU（边界差，core-seconds） | **5.101**（5 s 单核 busy ✓ 单位/范围验证） | **15.713**（qemu 模拟口径，已标注） |
| CPU 交叉核对 | 容器内自读 5.133 core-s（差 0.6%，读取时点差）；docker stats 快照 0.00%（workload 后 idle，证明单次 stats 不可作累计证据） | 自读 15.758 core-s ✓ |
| memory current / v1 peak | 0.6 MB / **138.9 MB**（128 MiB 分配 + python 开销 ✓） | 5.6 MB / 56.9 MB（qemu python 启动） |
| io interval（read/write） | 0 / 72 KiB | 0 / 136 KiB |
| 采样 | 15 样本/7.5 s（0.5 s 间隔）✓ gap 全记录 | 36 样本/17.8 s ✓ |
| 单 canary wall | 7.7 s（≤30 s） | 17.8 s（≤30 s） |

**I/O 降级边界（如实记录，不标 ready）**：本机 v1 blkio 仅 `blkio.throttle.io_service_bytes_recursive` 可用；16 MiB 写入仅记账 72 KiB（**约 0.4%**——writeback 归 root cgroup 的已知 v1 行为），读全为 page cache 命中（Read=0）。**scope 级 block I/O 在本机不可靠**：C 批 I/O 观测默认 null+原因（io.interval 有真实数字但不代表应用读写量）；如需可靠 I/O 须 cgroup v2 io.stat（本机 docker 为 v1）或直连块设备，属另行决策。

canary 迭代史（全部保留于 `reports/resource/RUN-01-B-canary{,-r2,-r3,-r4,-r5}/`）：r1 `python -c` 内嵌 `\n` 语法错误；r2 发现 v1 blkio 文件名前缀差异（旧 CFQ 名已移除）；r3/r4 发现 `Total 0`（无记录标记）与"文件存在但空"应判真实零而非缺失，以及 dd 不 sync 时写停留 page cache 不产生 block I/O（缓存影响的实测例证）。对应 reader 修复均带离线单测（6 项 CgroupV1ReaderTests）。

### 5.5 预算对账

| 项 | 上限 | 实际 |
| --- | --- | --- |
| B wall | 15 分钟 | **≈18 分钟**（超 3 分钟，canary 迭代；如实记录不隐藏） |
| evaluator 下载 | ≤500 MB | venv 433 MB 展开后（pip 经代理，逐包字节数未单独累计——已知记录弱点） |
| evaluator 新增磁盘 | ≤1.5 GB | 433 MB venv + 9.3 MB 副本 ✓ |
| 镜像压缩下载 | ≤3 GB | 1183.3 MiB ✓ |
| 镜像展开 | ≤5 GB | 3.07 GB ✓ |
| canary 合计 | ≤3 分钟，单 canary ≤30 s | 25.5 s 总；7.7/17.8 s ✓ |

### 5.6 B 结论与 C 前置决策项

**B 判定：环境就绪（含显式降级项）**。就绪：evaluator 执行副本+venv、make_test_spec 字段级构造、镜像 digest 固定（双 canary 均按 digest 引用启动成功）、cgroup v1 CPU/memory 计量链路（三路读取交叉核对通过）、身份匹配清理。降级：scope block I/O 不可靠（v1 writeback 归属）；`docker stats` 单次快照不可作累计证据（仅作交叉参考）。

**C 批前需用户决策**：
1. ~~执行架构口径~~ **已决策（2026-09-11）：采用官方 arm64 镜像，native 口径**（执行记录见 §5.8）。
2. G0 集中评审（A/B 证据 + 试点配置）后再批 C 清单（§3）。

### 5.7 ARM64 镜像调查（2026-09-11，只读网络查询，未 pull）

针对 qemu 模拟口径问题调查了 arm64 替代方案（GitHub API + Docker Hub API + docker manifest 只读查询，均经批准代理）：

**发现 1：官方 arm64 镜像已存在且覆盖目标任务。**
- Docker Hub 官方 `swebench/` namespace 下有约 281+ 个 `sweb.eval.arm64.*` 仓库（SWE-bench Multilingual 系列；推送者 `carlosejimenez`，2025-04-20，与 SWE-bench Multilingual 发布期吻合；对应官方 task repo `SWE-bench/swe-bench-multilingual-tasks`）。
- **`swebench/sweb.eval.arm64.django_1776_django-16485:latest` 存在**：arm64/v8 单架构 manifest，**digest `sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`**，14 层压缩 1.06 GiB，层结构与 x86_64 版同构（base+conda+repo 分层），2026-09-11 仍有人拉取（活跃）。
- 若采用：CPU/memory 回归 native 口径（r5/r6 原始测量：同 12 s busy 下 qemu 15.68 vs native 12.25 core-s；不推算单位工作开销倍率）；需要 (i) 扩展 B 批准 pull 该镜像并重固定 digest；(ii) wrapper 层把 record 的 x86_64 image 引用映射为 arm64 digest 引用（record 本身不动）；(iii) 环境准备检查（/testbed、conda env、eval_script 可用）须 pull 后实测——评估兼容性另需 verifier 链路验证，不预设等价。

**发现 2：自建 arm64 镜像可行但非首选。**
- 本地固定 02e7a74 的 `image_builder` 已原生支持 `arch="arm64"`（ImageSpec 平台校验 + buildx `--platform linux/arm64/v8`）；上游存在完整 ARM64 化社区工作（PR #521 未合并，含 JS/Java 任务修复；issue #523 已关闭；第三方 ARM64 benchmarking 笔记公开）。
- 历史失败模式（issue #224/#249，2024）：旧 Python 任务（如 astropy py3.6 + setuptools 38）在 linux-aarch64 conda 频道缺包导致 `sweb.env.arm64.*` 构建失败；**django__django-16485 为 Django 5.0 + python 3.11，aarch64 依赖齐全，属低风险**。
- 自建需要：task repo Dockerfile（02e7a74 起从独立 task repo 获取）、`sweb.base.arm64` 自建、conda/pip 走代理、预计 15–30 分钟 + 数 GB 磁盘；**任务书 B 约束"默认只 pull 预构建镜像，不 build"——自建需单独批准**。
- 与官方已发布镜像相比无优势，仅当 Multilingual 镜像内容验证失败时作为后备。

### 5.8 B 扩展执行：官方 arm64 镜像采用（2026-09-11，用户批准后执行）

```text
pull:        swebench/sweb.eval.arm64.django_1776_django-16485:latest（daemon 直连 4m32s）
RepoDigest:  sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2（与 pull 前 manifest 查询一致）
Image ID:    sha256:bba60201758effbb3e4795367d470e3d0e00427f0e2e86636801b9f93df0b664（与 manifest config digest 一致）
展开大小:    2.45 GB
```

**环境准备检查**（受控容器 `awc-run01-armcheck-tmp`，只读环境验证，未运行任何测试/未应用 patch，验证后已删除；**评估兼容性未验证**——verifier 链路从未在此镜像上运行）：

| 检查 | 结果 |
| --- | --- |
| 执行架构 | `uname -m` = **aarch64（native，无 qemu）** ✓ |
| /testbed | django repo，`template/defaultfilters.py` 存在 ✓ |
| base_commit | `39f83765...` 在 git 对象库（eval_script 运行时 `git checkout` 可用）✓ |
| conda 环境 | testbed env 激活，Python 3.11.11 + pip 25.0 ✓ |
| eval_script 依赖路径 | `/opt/miniconda3/bin/activate`、`tests/template_tests/filter_tests/test_floatformat.py` 均存在 ✓ |
| 构建链对照 | 与 x86_64 版同构（同分层布局、同 "SWE-bench" 标记 commit 模式）；两镜像 HEAD 标记 hash 不同（4c2a128a vs c7a6b3c4），不影响 eval——eval_script 在运行时 checkout base_commit；x86_64 版 base_commit 同样在对象库 |

**native 口径 canary（r6，`reports/resource/RUN-01-B-canary-r6/`，总 22.9 s）**：目标镜像（arm64 digest）作为 canary B。**注（第三轮评审更正）：r6 canary A 的内存子步骤失败（bytearray 扩展切片赋值数量不匹配）被 `;` 序列后的 sync 成功掩盖（workload_rc=0 不真实）；r6 不能标"2/2 全通过"。修复见 §5.9，容器复测待批。** 原始测量值仍有效（CPU/memory 计量不受该子步骤影响——bytearray 分配本身成功，峰值 139 MB 含该 128 MiB）：

| 指标 | canary B（arm64 目标镜像，native） | 对照（qemu x86_64，r5，同 workload 原始值） |
| --- | --- | --- |
| CPU | **12.246 core-s**（12 s busy ≈ 12.2 core-s；均值 0.82 核） | 15.683 core-s |
| 三路核对 | 自读 12.279 core-s（差 0.3%，读取时点差）✓ | — |
| memory peak | 15.3 MB（v1 max_usage） | 56.9 MB |
| io | write 104 KiB（v1 blkio 已知低估，降级不变） | write 136 KiB |
| wall | 15.1 s（≤30 s） | 17.8 s |

**结论**：目标镜像切换为官方 arm64 构建后，CPU/memory 计量回到 **native 口径**；qemu 路径（x86_64 digest `570eb343...`）保留为 fallback 记录（仅保留原始测量值，不推算开销倍率）。C 批的 Agent 沙箱与 verifier 均按 arm64 digest `19d403c2...` 引用；record 的 x86_64 image 字段经配置层映射（record 只读不动）。I/O 降级边界不变（v1 blkio writeback 归属，§5.4）。

### 5.9 C 前离线实现包（2026-09-11，第三轮评审后的集中返修）

评审结论：arm64 方向与 native CPU 采集链认可；r6 canary 存在被掩盖的子步骤失败（不能标 2/2 全通过）；"内容等价性"表述过度（未跑 verifier）；C 执行链仍为 NotImplementedError 骨架；"qemu 约 3 倍 CPU/单位工作"推导方法错误（忙循环未统计完成工作量）。本轮按评审要求集中完成四项，全部离线（无镜像操作、无模型请求、无容器复测）：

**R5：canary workload 修复 + 失败传递**
- 内存步骤改为 `b = bytearray(N); b[:65536] = b'x'*65536`（分配 + 显式提交物理页；r6 的 `b[::4096] = b'x'` 是 1 字节对 32768 槽的赋值量错误）。
- workload 以 `set -e` 开头——任一子步骤失败使整体失败，尾部 sync 不再掩盖（busy-loop 因 timeout 预期非零退出而显式 `|| true` 豁免）；canary 摘要新增 `workload_ok` 显式字段。
- 离线回归（5 项 CanaryWorkloadTests）：本地真 bash 执行快速参数 workload（rc=0 + mem_alloc_ok）、失败注入传递（`set -e; cat 不存在; echo survived` → rc≠0 且无 survived 输出）、`set -e` 前置断言、buggy 模式消除断言。
- **容器复测（r7）待批**：修复后的 workload 需一次批准的 canary 重跑确认。

**R6：C 执行链实现（替换 NotImplementedError 骨架）**
- `MiniSweAgentHarness.run` 真实路径：venv 子进程运行 mini agent loop，经 `AttachedDockerEnvironment` 附加到 runner 已创建并计量的容器（保留 mini 原动作协议与 agent loop；mini 不自建容器，计量边界保持在 runner：创建→基线→执行→最终读取→归档→拆除）。子进程每步向 `mini_status.jsonl` 追加状态行（n_calls=模型请求数、n_steps、cost、usage）；父进程轮询喂入外部预算计数器（`_count_status_line` 按 n_calls 增量计数），超限即 kill 子进程（外部第二道防线；第一道是 mini 原生 `step_limit`（其语义即 gates n_calls/模型请求数，已文档化）与 `wall_time_limit_seconds`，经 `default_mini_config` 从批准预算注入）。candidate patch 从容器工作树 `git -c core.fileMode=false diff` 提取（必须来自本次工作树）；轨迹/状态文件归档于 run_dir。测试以注入 fake child code（讲同一 status 协议）覆盖父进程编排：正常计数/预算 kill/子进程失败/无 diff→no_candidate/payload arm64 映射与答案隔离。
- `SwebenchVerifierRunner.run` 真实路径：复刻官方 run_instance 语义于 runner 提供的干净容器——heredoc 写入 candidate patch → 官方 `GIT_APPLY_CMDS` 四策略链（含失败间 `git checkout -- . ; git clean -fd` 复位与 `--check --reverse` 已应用验证）→ heredoc 写入固定 eval_script 并执行（verifier wall 由 exec timeout 强制）→ 官方 `get_eval_report`（make_test_spec over 只读 record；`>>>>> Start/End Test Output` 标记缺失 → tests_not_run，对齐官方 SUITE_RAN 语义）→ resolved/infra_failure 分离。swebench import 延迟，默认套件无依赖。
- **真实链路仍未运行**（authorized=False 拒绝执行）；fake 覆盖的是编排与构造，真实 mini/evaluator 行为需 C 批（或批准的容器复测）验证。

**R7：评估解析链离线验证（新显式集成入口）**
- `tests/integration_swebench.py`（5 项，swebench venv 运行，纯离线无容器）：真实 record → `make_test_spec` 字段级构造；合成 Django 格式 log（含官方 Start/End 标记）→ `get_eval_report` 全通过 resolved=True / F2P 失败 resolved=False / P2P 回归 resolved=False / 无标记（suite 未运行）resolved=False。**评估兼容性的解析部分已验证；容器内执行部分仍待批**。

**R8：口径修正（全文）**
- "内容等价性" → "环境准备检查通过，评估兼容性未验证"（catalog 键名 `equivalence_checks_gate_b`→`environment_preparation_checks_gate_b` + `eval_compatibility: not_verified`；交付文档 §5.8 标题与表格；canary note）。
- 删除"qemu 每单位工作约 3 倍 CPU"结论——保留 r5/r6 原始测量值（同 12 s busy：15.68 vs 12.25 core-s），显式声明"不推算单位工作开销倍率（忙循环未统计完成工作量）"（catalog fallback note、交付文档 §5.1/§5.8）。
- B 状态改为 `partially_accepted`（arm64 环境准备成果可认可；canary r6 失败项已修复待容器复测；评估兼容性未验证）。

**验证**：

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests            → 345 OK（328 + 17 新增：5 canary + 7 mini 编排 + 5 verifier 构造）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_swebench → 5 OK
项目外 cwd 绝对路径 discover                                         → 345 OK
py_compile / git diff --check                                        → OK
```

**B 批剩余待办（需批准的容器操作）**：canary r7 复测（修复后 workload 的双 canary 重跑 + `--storage-opt size=6g` 支持性实测）；评估兼容性容器验证（官方 GIT_APPLY_CMDS + eval_script 在 arm64 镜像上的 gold-patch 干跑——属 verifier 链路验证，建议与 G0 评审一并批准或并入 C）。

### 5.10 第四轮返修：C 链路离线补齐（2026-09-11，用户评审后集中执行）

评审结论（本轮阻塞项）：真实配置未接通（payload 空 config）；预算计数不可靠（累计 n_calls=3 只计 1、单次 10000 tokens 未触发）；verifier 超时不终止容器内工作负载且各命令独立 300s 预算可叠加超支；空 patch 覆盖原始停止原因、模型事件事后补建且一律 ok=True；运行中产物硬限制未接通。验收重点改为**真实安装版 mini 的离线贯通测试**。全部离线完成（无模型请求、无容器操作）：

**R9：真实配置接通**
- `run()` 经 `_effective_config()` 构造并实际传入完整 mini config：调用方 config（model_name/模板/environment）+ 预算强制字段（step_limit=max_model_requests、wall_time_limit_seconds、cost_limit=0、num_retries=0、max_tokens=每请求上限）；**model_name 缺失即拒绝运行**（不再可能给子进程发空 config）。`load_bundled_config()` 从 venv 读 mini 官方 swebench.yaml 模板（C 装配时使用）。凭据经子进程环境变量注入（`Popen env`，内存中；payload/文件均不含——fake transport 模式下注入的是显式假值且网络在子进程内被封）。
- **真实 mini 离线贯通**（新 `tests/integration_run01.py`，3 项，mini venv 运行）：真实 DefaultAgent loop + LitellmModel + StatusTrackingAgent 经 venv 子进程跑通——提交链（2 次 tool call → Submitted → candidate 提取 + 轨迹归档 + 事件时间戳）；格式错误链（3 次 plain-text → RepeatedFormatError，每次计费请求均计数且 ok=False）；外部 wall kill 链（慢工具 + 4s wall → 父进程 kill + 证据保留）。

**R10：预算计数修复**
- status 钩子从 step 级改到 **query 级**（`DefaultAgent.query` 覆盖）：FormatError 的计费请求与退出前最后一次请求都写行（ok=False 标注格式错误）；每行携带请求自身 monotonic 起止（t_start_ns/t_end_ns）。
- 父进程按**累计差值**计数（`count_requests(delta)`：一行从 n_calls=1 跳到 3 计 2 次——用户复现的丢计数场景）；输出 tokens 走**单请求上限检查**（`count_request_output`——单次 10000 tokens 触发超限）；快速完成的 child 在 drain 后统一 check（超限事实不因未 kill 而丢失）。
- 回归：跳变计数、单请求超限、format-error 计数、`remaining_s` 相位/总限取小、`_effective_config` 拒绝空 model_name 与预算合并。

**R11：verifier 剩余 deadline 与工作负载终止**
- 单一 `deadline = now + budget.remaining_s("evaluation")`（相位 wall 与总 wall 取小、扣除已耗时间）；patch 上传/每步 apply/复位/eval 执行全部 `op_timeout()=max(1, remaining)`——**不再有可叠加的每命令 300s**。
- 超时后调用 `runtime.terminate_workload(container)`（新 runtime 接口）：容器内 `pkill` 失败则 `docker stop -t 0`（本地 exec 超时只杀 docker CLI 客户端，不终止容器内命令——现在终止后才由 runner 读取最终计数器）；`terminate_workload` 的调用与结果记入 verifier detail。Fake runtime 记录 `terminated` 清单供断言。
- 回归：deadline 耗尽 → verifier_timeout + terminated 记录；eval timed_out → 同路径。

**R12：失败与时间证据保真**
- 空提取/失败提取**不再覆盖**原始停止原因：`budget_exceeded`/`agent_error` 时仅追加注解（"candidate extraction also failed"）；只有原本 ok 的运行才因空 diff 转 no_candidate。回归覆盖 budget-kill+空 diff、child 失败+diff 失败两个用户场景。
- llm_request 事件改为**轮询时实时发射**（含最终 drain），attrs 携带子进程记录的 `t_start_ns/t_end_ns` 与 `timing_source="child_status"`；ok 取行内真实值（格式错误=False）。不再事后用归档时间编造请求耗时。
- recorder 白名单增加 t_start_ns/t_end_ns/timing_source。

**R13：运行中产物硬限制接通**
- 新 `_ArtifactMonitor` 线程（runner 全程覆盖 execution+evaluation，1s 轮询 run_dir 实际字节数）：超限即标记 `budget.artifact_exceeded`，`BudgetTracker.check()` 随之抛出 → harness 停止（mini 子进程被 kill）→ execution=budget_exceeded。这是 C 批 5 GiB 硬上限的运行时保证；归档期软计账保留用于精确记账。修复 `_dir_size_bytes` 的 3.11 兼容问题（`follow_symlinks` 参数 3.13+ 才有，曾使 monitor 线程静默崩溃）。
- 回归：上限 1 byte + 真实 wall 的 harness → execution=budget_exceeded（new_artifact_bytes）且最小证据归档；archive 软计数场景独立保留（上限介于运行文件与可选归档之间 → execution ok + archive budget_exceeded + samples.json 跳过）。

**验证**：

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests            → 358 OK（345 + 13 新增 R9–R13 回归）
PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python -m unittest tests.integration_run01 → 3 OK（真实 mini 贯通）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_swebench → 5 OK
项目外 cwd 绝对路径 discover                                         → 358 OK
py_compile / git diff --check / 敏感扫描（排除显式 fake 凭据字面量）   → OK
```

**边界（如实声明）**：集成贯通中的模型响应与工具输出是脚本化 fake——验证的是**编排与真实 mini 代码的对接**，不是模型质量；真实模型路由/凭据注入/容器执行仍需 C 批。gold-patch 干跑（verifier 真实容器执行）属单独批准项，参考答案与 Agent 隔离不变。canary r7 容器复测仍待批。

### 5.11 第五轮返修：停止链与限制口径（2026-09-12，用户评审后集中执行）

评审阻塞项：(1) `pkill -f "/eval.sh;bash /eval.sh;python"` 的分号不是正则"或"，匹配不到进程，且 pkill rc=1 直接返回不触发兜底；Agent 超限杀 mini 子进程不能证明其启动的容器命令已停止；(2) 产物限制非全程硬上限（verifier 阻塞期间不持续检查、容器可写层不在检查范围、轮询允许超调）；(3) `test_budget_kill_preserves_evidence` 的 status 断言是条件式的。全部离线修复（无容器操作、无模型请求）：

**R14：停止链统一（Agent/verifier 同一套语义）**
- `DockerCliRuntime.terminate_workload` 重写：模式改为 ERE 交替 `bash -c|/eval.sh|pytest|python`（`;` 修正为 `|`）；pkill 后以 **pgrep 复核**——无残留 → `confirmed=True, container_alive=True`（计数器仍可读）；pkill 匹配但有残留/exec 卡死 → 兜底 `docker stop -t 0`（容器 EXITED，**cgroup 可能已不可读——如实记录**）；docker stop 也失败 → `confirmed=False`。pkill rc=1（无匹配）**不再提前返回成功**，一律走复核/兜底。
- **Agent 侧接通**：mini 子进程被预算 kill 或 watchdog kill 后，runner/harness 调用 `terminate_workload(agent_container)`——`docker exec` 客户端死亡不会停止容器内命令，现在统一终止并把确认状态写入 `stop_reason`（`workload_stop_confirmed=...`）与 container 事件。
- **verifier 侧**：`_deadline_exceeded` 记录三分类停止状态（`stopped_confirmed` / `stopped_via_docker_stop; container exited; final counters may be unreadable` / `stop_not_confirmed`）。
- `DockerCliRuntime.execute` 改为 Popen+轮询等待：超时或外部 `should_stop` 触发时杀本地客户端**并**终止容器内工作负载（原 `subprocess.run(timeout=)` 只杀客户端）。

**R15：产物限制口径修正（放弃"硬上限"表述）**
- 机制如实定名：**限定范围超限检测停机**——范围 = run_dir 树（0.25 s 轮询，原 1 s）+ 容器可写层另经 `ContainerSpec.storage_size`（`--storage-opt size=...`）约束（**支持性依赖 overlay2+xfs pquota，待 r7 实测**；不支持则声明该层仅靠容器删除回收）；检测延迟与突发超调显式声明。
- **verifier 阻塞期间可中断**：verifier 的全部容器执行传入 `should_stop=lambda: budget.artifact_exceeded`——monitor 标志在阻塞的 eval 执行期间由 execute 轮询感知并打断（原实现中标志只会在下一个命令边界生效）。
- C 审批表格（§3）新产物行已改写为上述口径；**不再称 5 GiB 硬上限**。

**R16：测试修正**
- `test_budget_kill_preserves_evidence`（集成）改为**无条件断言**：kill 前 ≥1 条模型请求记录（mini_status.jsonl）且 ≥1 条工具命令执行（新增 `mini_env_log.jsonl`——FakeScriptedEnvironment 记录每次 execute，证明工具阶段真实进入而非仅 SDK 导入期超时）；并断言 Agent 侧容器工作负载终止与 `workload_stop_confirmed` 记录。
- 新增 Round5StopChainTests（8 项）：模式为交替正则（无分号）；Agent 预算 kill → 容器终止 + 事件 + confirmed 记录；未确认停止路径（注入 docker_stop_failed）→ `workload_stop_confirmed=False`；watchdog kill → 容器终止 + 事件；verifier 未确认停止 → `stop_state=stop_not_confirmed`；verifier docker stop 路径 → `counters may be unreadable` 如实记录；`should_stop` 打断 execute；`--storage-opt` argv 构造。

**验证**：

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests            → 366 OK（358 + 8 新增）
PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python -m unittest tests.integration_run01 → 3 OK（含无条件 kill 断言）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_swebench → 5 OK
```

**停止状态三分类（C 批资源证据口径）**：最终资源证据将区分 **已停止（confirmed, 容器存活，计数器可读）/ 经 docker stop 停止（容器 EXITED，最终计数器可能不可读——按 not_found 记录而非零）/ 未确认停止（stop_not_confirmed，测量边界的诚实缺口）**。

### 5.12 第六轮返修：执行可靠性（2026-09-12，用户评审后集中执行）

两组阻塞，全部离线修复（无容器操作、无模型请求）：

**R17：管道排空（execute 与 mini 父进程统一修复）**
- `DockerCliRuntime.execute`：reader 线程**执行期间持续排空** stdout（旧实现在退出后才读——输出超管道缓冲 ~64 KiB 的命令被卡成假超时）；累积带 16 MiB 硬帽；**正常/超时/外部停止三条路径统一** `[:output_limit]` 截断并回报 `output_truncated`（旧超时分支曾无视 limit 返回 65536 字节）。超时/外部停止仍先杀本地客户端再终止容器内工作负载。
- mini 父进程同模式修复：drain 线程持续读子进程输出（litellm 日志可能超管道），summary 从保留尾部解析。
- 回归（Round6PipeDrainTests 4 项，本地假 docker 可执行脚本替代 Docker——与评审复现方法一致）：1 MiB 输出 → rc=0 非超时；output_limit=100 → 三路径均恰 100；sleep+短超时 → timed_out+termination；mini 子进程写 1 MiB 后正常完成。

**R18：停止确认语义收紧**
- 旧实现 `if check.returncode != 0: confirmed=True` 把 pgrep rc=2（检查错误）当成功——评审注入 pkill=0、pgrep=2 仍 confirmed。且"名称模式无匹配"≠"工作负载已停"（工具可启动不匹配名称的进程）。
- 重写为**进程树核查**：pkill 仅作尽力快速路径（非证明）；证明来自容器内 `/proc` 扫描（纯 shell，无 ps 依赖）：仅当**显式**"非 PID 1 且非 zombie 的进程为零"（rc==1）才 `confirmed=True, container_alive=True`；检查错误（rc==2）/仍有进程（rc==0）/exec 超时一律兜底 `docker stop`（容器 EXITED，计数器可能不可读——如实记录）。
- 回归（Round6TerminateConfirmationTests 4 项）：check rc=2 → docker_stop 兜底（评审反例）；rc=0 → 兜底；rc=1 → confirmed+容器存活；模式无分号。

**验证**：默认 374 项（366+8，项目内/项目外双跑，`-W error::ResourceWarning` 下管道测试亦过）；mini 集成 3 项；swebench 集成 5 项；`py_compile`/`git diff --check` OK。容器验证审批与 C 模型运行审批保持分开（未变）。

### 5.13 第七轮返修：执行可靠性二（2026-09-12，用户评审后集中执行）

两组阻塞（均已离线复现），全部修复（无容器操作、无模型请求）：

**R19：进程检查返回值反转与自身排除**
- 旧扫描脚本 `exit $busy`（发现活跃进程 → rc=1），调用方却把 rc==1 解释为"无残留"——评审以实际扫描 + mock 调用链复现出错误的 confirmed=True；且扫描未排除检查进程自身、检查错误未真正返回 2。
- 重写：返回值约定统一为 **0=idle（确认停止）/ 1=busy / 2=检查错误**；纯 POSIX sh（无 awk 子进程，仅需排除 PID 1 与 $$ 自身）；stat 解析用"最后一个 `)` 之后"的字段（comm 含空格/括号安全）；`PROC_ROOT` 参数化（生产恒为 /proc，测试用 fixture 树**执行同一脚本**）。调用方仅 rc==0 确认；1/2/超时/OSError 一律 docker stop 兜底。
- 回归（Round7ProcessCheckTests 6 项，fixture 执行实际扫描、不注入返回码）：idle→confirmed（容器存活）；busy（活跃非主进程）→docker stop（覆盖旧反转反例）；zombie 不计；空 fixture（无 PID 1，真 rc=2）→docker stop；FAKE_SELF 注入检查进程自身条目→仅凭 $$ 排除才 confirmed；模式无分号。

**R20：reader 改固定大小二进制块（两处）**
- 旧 `for chunk in proc.stdout` 按行迭代：无换行的超长行先整行缓冲再检查大小（16 MiB 帽失效），超帽整行被丢弃——评审复现：帽 1024、单行 2048 字符、保留前 100 → 返回空串。
- 两处 reader（DockerCliRuntime.execute 与 mini 父进程）均改为 `read(65536)` 固定大小二进制块：内存与换行无关地有界；超帽后继续排空（child 不阻塞）但停止累积并**保留前缀**；新增 `output_bytes_total`/`output_truncated` 如实回报。
- 连带修复：kill 后 `stdout.close()` 会阻塞在 reader 的缓冲锁上直至 EOF（本地复现 29.5s）——close 移入 daemon 线程，主流程不被孤儿孙进程拖死；fake docker 的 sleep 模式改 `exec sleep`（与真实 CLI 语义一致）。
- 回归（Round6PipeDrainTests 6 项）：评审反例（帽 1024/单行 2048/limit 100 → 恰 100 字符且 total=2048）；1 MiB 输出正常完成；三路径统一 limit；mini 父进程 2 MiB 无换行单行 + 帽 1024 → 完成且计数回退到 status 文件。

**验证**：默认 378 项（374 - 4 注入式 + 8 实扫/帽回归；项目内/项目外双跑，`-W error::ResourceWarning` 干净，9s）；mini 集成 3 项；swebench 集成 5 项。r7、隔离 verifier 验证与 C 模型运行保持分别审批（未变）。

### 5.14 容器验证执行（2026-09-12，用户分别批准后执行）

#### canary r7（`reports/resource/RUN-01-B-canary-r7/`，run_id RUN01BCANARY-20260912T103943Z-1259a4，总 23.7 s）

| 项 | 结果 |
| --- | --- |
| canary A（native） | rc=0（**修复后 workload 全过**：`mem_alloc_ok 134217728` 确认内存子步骤成功）；CPU 5.122 core-s；mem peak 138.8 MB（v1 max_usage）；io write 96 KiB（v1 blkio 降级不变）；自读/stats 交叉核对 ok |
| canary B（arm64 目标镜像 digest） | rc=0（`target_workload_ok`）；CPU 12.276 core-s；mem peak 16.0 MB；自读/stats ok |
| **停止链分支 A**（canary B 内实测） | 后台 `sh -c` busy loop（**名称模式外进程**——评审要求的场景）→ pkill 不匹配 → 进程树核查发现 busy → **docker stop 兜底**：`confirmed=true, container_alive=false`——名称外进程由兜底确认停止，容器 EXITED 如实记录 |
| **停止链分支 B**（`RUN-01-B-canary-r7-stopchain/`，独立容器） | 后台 `bash -c` busy loop（mini interpreter 模式内）→ pkill 命中 → 进程树核查 idle → **`confirmed=true, method=pkill+process_tree_check, container_alive=true`**，且停止后计数器仍可读（cpu_usage_usec=774372 ✓） |
| **--storage-opt 支持性** | **不支持**：daemon 拒绝（`--storage-opt is supported only for overlay over xfs with 'pquota'`，本机 xfs 无 pquota）——C 口径按 §3 声明：容器可写层无配额，仅靠容器删除回收，峰值期间占宿主空间 |

**canary 结论**：停止链两分支（名称内/名称外进程）均在真实容器验证；三分类停止状态（confirmed+容器存活 / docker_stop+EXITED / 未确认）语义成立；修复后 workload 双 canary 全过（r6 的失败掩盖问题闭环）。

#### 隔离 gold-patch verifier 验证（`reports/resource/RUN-01-B-goldverify/RUN01BGOLD-20260912T104224Z-617538/`，wall 12.28 s / 预算 600 s）

**评估兼容性：已验证（arm64 目标镜像上官方链全通）**：

| 步骤 | 结果 |
| --- | --- |
| record 校验 | SHA-256 复核一致；gold patch 仅从只读 record 提取 |
| 官方 apply 链 | gold patch `git apply --verbose` 一次成功（patch_applied=True） |
| eval_script 真实执行 | base 测试文件 checkout + test_patch 应用 + `runtests.py` 运行：**`Testing against Django installed in '/testbed/django'`**（测试导入 /testbed 工作树代码）→ **10/10 测试 ok**（F2P `test_zero_values` + 9 P2P），`Ran 10 tests ... OK`，`SWEBENCH_TEST_EXIT_CODE=0` |
| 官方 parser | `get_eval_report` → **resolved=true，infra_failure=False** |
| 隔离 | gold patch 仅传入 `SwebenchVerifierRunner`（verifier 允许读测试规格）；**本次验证无 Agent、无模型**；events.jsonl 仅含 status/detail，gold 文本不落任何 agent 侧路径 |

已知无害项（如实记录）：eval_script 的 `pip install -e .` 步骤在离网容器中失败（无 build deps 下载）——不影响正确性：镜像预装 editable 指向 /testbed，测试日志证实导入的是 /testbed 代码，F2P 通过即 gold 修复真实生效；官方 classify_logs 未标记 infra_failure。

**verifier 结论**：arm64 环境的评估兼容性由 gold-patch 干跑证实（apply→eval→parse→resolved 全链）；C 批候选 patch 将走同一条已验证的链路。

#### 遗留（如实声明）

- 容器可写层无配额（--storage-opt 不支持）：C 批容器峰值磁盘占用依赖停机机制 + 容器删除回收，§3 口径已声明
- v1 blkio I/O 降级、`docker stats` 单快照不可作累计证据：不变（§5.4）

### 5.15 C 执行入口组装与最终审批材料（2026-09-12，用户授权离线开发；未执行 C）

按用户指令组装最小 C 执行入口（不另建框架、不试跑）：

**入口（`src/agent_workload_characterization/runners/c_entry.py`，SHA-256 前缀 `65f4d62faa02c0db`）**：
- 组装已验收四组件（CodingPilotRunner / MiniSweAgentHarness / SwebenchVerifierRunner / DockerCliRuntime），固定身份硬编码于入口：record 路径+SHA、arm64 digest `19d403c2...`、双 venv 解释器、`openai/deepseek-v4-flash`、collection `RUN-01-C`、source_type `benchmark_real`。
- **默认离线计划**：组装并复核身份（record hash/venv 存在性/bundled 模板/catalog 预算与容器限制），输出无秘密计划 JSON（预算=30 请求/30 step/4096 tokens/25+5 min/30 min/5 GiB、容器 4 CPU/8 GiB ×2、执行命令、授权状态 pending、三已知缺口）。
- **执行门禁**：`--execute --i-approve-the-c-run` 双旗标（用户键入=授权行为）；单旗标 rc=2；凭据环境缺失在任何容器/子进程前 fail-fast（报变量名不报值）；catalog `execution_authorized: true` 直接拒绝组装（配置不能授权）。
- **凭据接线**：`PILOT_API_BASE`/`PILOT_API_KEY` 执行时读取 → 映射子进程 `OPENAI_API_BASE`/`OPENAI_API_KEY` → 经 `CodingPilotRunner.credentials`（仅内存）→ `harness.run(credentials=...)` → mini 子进程环境；runner→harness 凭据传递与容器资源限制（4 CPU/8 GiB）为本轮新增接线。
- 解释器=swebench venv（verifier lazy import + pydantic 已装）；mini 子进程=mini venv；已在登记解释器下实测计划模式与拒绝路径。

**验证（实际执行）**：

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests            → 386 OK（378 + 8 入口测试）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m agent_workload_characterization.runners.c_entry → 计划 OK（登记解释器实测；身份检查全过；无秘密）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m agent_workload_characterization.runners.c_entry --execute → rc=2 拒绝
PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python -m unittest tests.integration_run01 → 3 OK（真实 mini 贯通不变）
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m unittest tests.integration_swebench → 5 OK
git diff --check                                                    → OK
```

入口测试（`tests/test_c_entry.py` 8 项）：计划无秘密且完整；单旗标拒绝；缺凭据先于组装失败（build_c_runner 未被调用的顺序证明）；配置篡改 `execution_authorized: true` 被拒；record hash 漂移拒绝；离线组装断言（digest/model/budget/容器限制/答案不在 agent 输入/bundled 模板真实加载）；凭据经 runner→harness 传递且不落 run_dir 任何文件。

**代码身份**：git HEAD `b4437fb8c7563ccfb384a422c23994e43c9ac957`（工作区含未提交 RUN-01 变更，21 项）。关键文件 SHA-256 前 16 位：c_entry `65f4d62faa02c0db`、coding_pilot `7a6a96c70cade821`、mini_agent_adapter `cf24c87940a7f886`（执行前修正，见 §5.17）、container_runtime `f8535ee133d5c1da`、semantic_recorder `b2575fc4ac1e0c45`、resource_sampler `de3eda70e8e6dafa`、resource_summary `57fd885fb2165fd8`、canary `668c880beb74b41e`、coding_pilot.yaml `aee38eaca781df01`。

**顺带修复**：`coding_pilot.yaml` 多处未加引号的多行标量含裸冒号导致 YAML 解析失败（上一轮引入、未验证解析）——已加引号并实际解析验证；gates 状态行同步至七轮/r7/入口现状。

**未做（按边界）**：未安装/下载/pull/build、未启动容器、未跑 gold verifier、未发模型请求、未读密钥值、未改 references/旧数据/封存报告/用户配置、未提交 Git；G0 不代签、C 未标已授权（catalog `C_real_single_task: awaiting G0 decision + user approval`）。

**第一轮评审后收紧（2026-09-12，用户复核三项意见）**：
1. **预算与审批身份绑定**：入口硬编码登记 catalog SHA-256 `aee38eaca781df014117c4af14ce6df4fce91e2808dde09b03271b1e94902f83`，内容漂移（含评审复现的请求数 30→300）在**计划与执行两种模式**均拒绝组装；预算字段增加类型/有限性/正值校验（`agent_wall_min=NaN`、负值、零值、字符串类型均拒绝；容器 CPU/mem 字段同样校验）。
2. **测试有效化**：凭据不落盘扫描移入 TemporaryDirectory 存续期内（原实现在目录删除后扫描=空检查），并断言实际检查了产物文件（scanned>0 且含 events.jsonl/metadata.json）；入口测试 12 项**全部改为合成 fixtures**（合成 record/catalog/venv 树 + 常量 monkeypatch），默认套件不再依赖本地真实 record、catalog 与 venv；新增预算校验与 catalog 哈希漂移回归。
3. **审批清单合并**：任务书 §8 重排为唯一有效版本（8.1 预算 / **8.2 实际入口与最终命令登记（已登记）** / 8.3 已完成证据 / 8.4 风险 / 8.5 G0 决议 / 8.6 批准后顺序）；删除重复的"待填"8.2 与编号冲突；G0 评审材料同步冻结状态（`C_command_frozen=true`）与新入口哈希；任务书 §8.2/§8.5 明确**双旗标仅为软件门禁、不证明输入者身份，授权以用户明确批准记录为准**。

**代码身份（第二轮后）**：c_entry `65f4d62faa02c0db`（哈希绑定+预算校验+双旗标声明）、coding_pilot `7a6a96c70cade821`（不变）、test_c_entry `e14ac54fa47c0054`（合成化 12 项）；catalog `aee38eaca781df01...`（入口 pin 同值）。验证：默认 390 项（项目内/项目外双跑）通过；登记解释器计划模式通过（真实 catalog 哈希核对通过）。

### 5.17 执行前缺陷修正与环境核验（2026-09-12，C 授权后、执行前）

C 授权后、启动前核验发现并修正一处实现缺陷（不改变已登记语义，还原 mini 原生行为）：

- **缺陷**：`AttachedDockerEnvironment`（mini 子进程内的容器执行器）未转发 mini 配置的 env 变量（`BASH_ENV=/root/.bashrc` 等）。mini 2.4.6 原生 `DockerEnvironment.execute` 经 `docker exec -e KEY=VALUE` 转发（源码 docker.py:107-113）；缺此转发时 `bash -c` 工具命令运行于镜像 base conda python（`/opt/miniconda3/bin/python`）而非 testbed env。子进程 docstring 本就声称"Same execution semantics as mini's DockerEnvironment"——修正是使实现与已登记语义一致。
- **修正**：`AttachedDockerEnvironment` 增加 env 参数并按 mini 原生方式 `docker exec -e` 转发；`main()` 传入 `environment.env`（含 BASH_ENV/PAGER 等，无秘密）。变更仅 `runners/mini_agent_adapter.py`：SHA-256 前缀 `00dd559479411ed1` → **`cf24c87940a7f886`**。
- **实测验证**：`docker exec -w /testbed -e BASH_ENV=/root/.bashrc <arm64 digest> bash -c "which python"` → `/opt/miniconda3/envs/testbed/bin/python`（Python 3.11.11）✓；对照无 BASH_ENV → base python（django 仍可从 /testbed 导入，但非 eval 所用 env）。修正后默认 390 项 + mini 集成 3 项 + swebench 集成 5 项全部通过。
- **其余身份未变**：c_entry `65f4d62faa02c0db`、catalog `aee38eaca781df01...`（冻结哈希核对通过）、镜像 digest、record SHA、双 venv。
- **凭据核验（值不读取/不输出）**：OpenCode 配置（用户指定）确认 baseURL `https://st8tp3ajl0df3n8b8l8qu.apigateway-cn-beijing.volceapi.com/v1`（含 /v1，非秘密）+ apiKey 为 `{env:VOLCANO_API_KEY}` 引用；`VOLCANO_API_KEY` 在环境中（长度 37，值未读）。执行时由入口映射为子进程 `OPENAI_API_BASE`/`OPENAI_API_KEY`，仅内存。直连连通性依据：SMOKE-01 首次尝试曾直连到达网关并获得认证响应；子进程环境按 §8.2 不自动继承代理变量。

### 5.16 G0 正式决议与磁盘风险展示（2026-09-12T12:39Z）

**G0 决议：PASSED**（正式记录见 [g0_review.md](../reports/quality/g0_review.md) 决议节：评审人=用户 2026-09-12 消息原文、UTC 时间、代码/配置身份、五条结论与随决议携带的限制；G1/M1 不自动通过）。

**C 执行授权状态**：预算与观测限制已认可（用户原文记录于决议节）；命令已冻结；**磁盘风险确认 pending——确认后执行，一次即停，不自动重试/扩预算/换任务/改环境**。

**磁盘实际可用空间（2026-09-12T12:39Z 只读实测）**：

| 盘 | 文件系统 | 总量 | 已用 | 可用 | 用途 |
| --- | --- | --- | --- | --- | --- |
| 输出盘 | `/dev/sdg`（/home） | 3.5T | 410G | **2.9T** | run_dir（5 GiB 检测阈值）、reports |
| Docker 数据盘 | `/dev/mapper/vg_sda-lv_root`（/） | 442G | 44G | **399G** | 容器可写层（**无配额**，仅事后回收） |

背景：目标镜像（arm64 digest）已在本地，无新拉取；Docker 现有 Images 64.42GB / Containers 23.38GB / Build Cache 29.81GB（无关本次运行的既有占用）。

**风险陈述（§8.4-1 磁盘降级的具体化）**：容器可写层峰值无配额约束——Agent 沙箱与 verifier 顺序运行（同时至多一个活动容器写入），参照同镜像 gold 验证（12.28s、写入量 KB 级）与本机可用空间（399G），单次 C 运行的可写层写入与本批 5 GiB run_dir 检测阈值相比余量充足；但机制上仍是"检测+事后回收"而非防满保证。等待用户对上述单次运行磁盘风险的明确确认。

### 5.18 C 执行记录（2026-09-12T12:52:02Z–12:54:29Z，用户确认磁盘风险后执行，一次即停）

**授权链**：G0 PASSED（§5.16）→ 用户认可预算与观测限制 → 用户确认磁盘风险（输出盘 2.9T / Docker 盘 399G 可用）→ 用户"执行"→ 按 §8.2 冻结清单执行。无自动重试、未扩大预算、未换任务/模型/镜像、未修改环境。

**实际执行命令**（与登记一致；凭据值经 shell 环境传递，未打印/未落盘）：

```bash
cd /home/lcq/agent_workload_characterization
export PILOT_API_BASE="https://st8tp3ajl0df3n8b8l8qu.apigateway-cn-beijing.volceapi.com/v1"
export PILOT_API_KEY="$VOLCANO_API_KEY"   # OpenCode 配置 {env:VOLCANO_API_KEY} 引用解析
PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
  -m agent_workload_characterization.runners.c_entry --execute --i-approve-the-c-run
```

**结果**：run_id `20260912T125202Z-840e49`，wall 147 s（预算 1800 s）。

| 项 | 结果 |
| --- | --- |
| execution / evaluation / archive | ok / ok / ok（三状态独立记录） |
| **resolved** | **true**（官方 verifier：patch_applied=True、infra_failure=False；eval 日志 `SWEBENCH_TEST_EXIT_CODE=0`，F2P+P2P 全过） |
| 模型请求 | **30/30（恰在硬上限）**：26 次正常 + 4 次格式错误（全部计入预算；无嵌套重试） |
| steps | 26（上限 30） |
| 输出 tokens | 10,777（每请求上限 4096 未触发） |
| 产物 | 293,859 字节（阈值 5 GiB；未触发） |
| Agent 退出 | mini 内部 `LimitsExceeded`（第 30 次请求边界），未键入提交命令、submission 为空——**candidate 由工作树提取路径捕获**（`git diff`，本次工作树来源），正是该设计使无提交运行的修复得以验证 |
| candidate | `django/template/defaultfilters.py`：`Context(prec=max(prec, 1))`（floatformat 精度钳制修复） |

**资源观测（native arm64，cgroup v1 边界计数）**：

| scope | CPU | wall | memory peak（v1 max_usage） | 采样 | io（降级口径） |
| --- | --- | --- | --- | --- | --- |
| agent_container | 6.412 core-s | 134.1 s | 68.5 MB | 293 样本 | write 48 KB |
| verifier_container | 3.423 core-s | 12.0 s | 70.5 MB | 24 样本 | write 1.66 MB |
| host_agent_runtime | 未仪表化（已声明缺口；请求/wall 边界来自 status 协议） | — | — | — | — |

**产物（封存，append-only）**：`data/raw/generated/RUN-01-C/20260912T125202Z-840e49/`（candidate.patch、events.jsonl、mini_status.jsonl、mini_trajectory.json、samples.json 含完整边界+逐次采样证据、metadata、manifest、verifier/test_output.txt）；摘要 `reports/resource/RUN-01-C/`。

**清理与安全**：0 残留容器（仅清理本次 run 身份）；敏感扫描——凭据值不出现在任何产物（events/轨迹/摘要仅含任务内容与数值 usage）；无代理变量进入子进程环境。

**执行后修正（派生视图，封存数据未动）**：`analyzers/resource_summary.py` 对真实事件流的 llm 计数修正（open+closed 成对被计为 60 → 计 closed=30；ok/failed 按闭合事件 attrs；新增 censored 字段与两条 limitations：工具级事件仅 fake 流程发射、host scope 无逐进程仪表化）。SHA-256 前缀 `57fd885fb2165fd8` → `a6dac1ef4626d699`；摘要已按修正后口径重新生成。默认 390 项测试执行后复跑通过。

**结论**：RUN-01 一次真实 attempt 完成且 resolved=true；资源观测按声明的 scope/单位/缺口如实交付（CPU/memory 有效、I/O 降级、host scope 缺口）。**单条样本不构成生产代表性结论；G1 不因此自动通过。按约定交付后停止。**

### 5.19 第八轮：派生报告收尾（2026-09-13，用户复核三组问题后离线执行）

评审确认（用户核对）：30 请求=26 正常+4 格式错误、输出 10,777 tokens、单请求最大 1,981<4096；verifier 日志自 /testbed/django 导入、10 测试通过；原 manifest 与摘要哈希匹配。三组修正**全部限于派生视图**（封存 run_dir 与历史摘要 `reports/resource/RUN-01-C/` 未动——8 文件 520,090 字节逐哈希复核不变）：

**R21：行为与退出状态**
- 摘要 tools 块改为多源提取，**不再假零**：mini 轨迹（真实运行权威源）→ `calls=26, observation_messages=26, source=mini_trajectory`；fake 流程回退 runner 事件；无源时 null+unknown。分类未接线（P1-06）显式标 `not_available`。
- 新增 `agent` 块显式保留：`exit_status=LimitsExceeded`、`submitted=false`、`candidate_source=container_working_tree_git_diff`，并注明 "execution=ok 描述管道而非 agent 干净完成"——非提交退出经工作树提取路径产生已验证 candidate 的事实不再被 ok 掩盖。

**R22：I/O 降级落实**
- 摘要 scope 的 io 改为**正式/诊断分离**：`formal=null` + `reason=degraded_host_v1_blkio（writeback 归 root cgroup；读为 page cache 命中；非应用字节）`；原数值（区间增量/累计/cumulative_end）整体降为 `diagnostic`。判定依据为边界 read_status 中的 v1 throttle 源（自动检测，封存 samples.json 数值不动）。

**R23：归档完整性与计账**
- 根因两处并修：(a) 原 manifest 只遍历顶层文件 → `verifier/test_output.txt`（16,033 B）遗漏——runner `_archive` 已改为 rglob 递归（未来运行生效）；(b) 计账只覆盖 runner 归档文件 → harness 子进程（mini_status 13,174 + mini_trajectory 197,024）与 verifier 日志（16,033）共 226,231 B 在计账范围外——runner 已改为全树计账（未来运行生效）。
- 摘要新增 `archive` 对账块：reported（metadata 快照 291,873，注记快照语义）/actual 520,090/files 8/原 manifest 列表/缺失清单/范围外字节（226,231，三个文件逐项）/计账范围说明。区分两个集合：manifest **列出**在场文件（含子进程产物），计账只覆盖 runner 归档集——二者不再混淆。
- **补充完整性清单** `reports/resource/RUN-01-C-v2/supplement_manifest.json`：完整 8 文件清单（bytes+SHA-256）、原 manifest 链接（路径+其自身 SHA-256+缺口说明）、对账（293,859 runner 归档 + 226,231 范围外 = 520,090 实际；metadata 快照 291,873 与终值 293,859 的差异注记）。

**产物**：`reports/resource/RUN-01-C-v2/`（summary.json/md + supplement_manifest.json + manifest，`supersedes` 注记指向未覆盖的历史摘要）；封存数据零改动（哈希快照前后比对通过）。

**验证**：默认 395 项（+5 Round8 回归：verifier 子目录文件进 manifest+计账、轨迹提取 tools/agent、io 正式 null+诊断、对账块、fake 流程回退）项目内外双跑通过；`py_compile`/`git diff --check` OK。执行后代码身份：resource_summary `a6dac1ef4626d699`→`eb166def99012cd9`、coding_pilot `7a6a96c70cade821`→`ce227d8a09c278d4`（未来运行生效的归档修复）。

**验收范围（按用户口径）**："真实任务运行＋基础容器资源采集"成果待本轮报告收尾后验收；G1 不自动通过；不启动第二次任务。

## 6. 返修记录（用户安全复核意见，2026-09-11 第二轮：四项离线路径缺陷）

均为用户以合成反例确认的问题；全部在离线路径内修复，不涉及提前运行 B/C。

### R1：Verifier 测量未绑定真实 handle

- **问题**：`_VerifierScopeReader` 构造虚假 container id 读取计数器；FakeVerifier 自行 start/stop 容器，最终边界读取发生在容器拆除之后（read_log 状态 absent）——verifier scope 的计量证据与真实容器无关。
- **修复**：容器生命周期统一收归 runner——`VerifierRunner.run` 签名改为接收 runner 创建的 `ContainerHandle`（verifier 不再自建/自拆容器）；evaluation 阶段顺序固定为 **创建→基线→执行→最终读取→归档→拆除**（拆除在外层 finally，晚于 archive）。删除 `_VerifierScopeReader`，verifier scope 复用与 agent 相同的 `_RuntimeScopeReader`（真实 handle）。
- **回归**：`test_final_counter_read_happens_before_teardown` 扩展为同时检查 agent 与 verifier 两 scope（最后读取状态 running、无 absent 读取）；新增 `test_verifier_reads_use_real_handle`（FakeVerifier 收到的 container id == runtime 实际创建并停止的容器；container start 事件引用同一身份）。

### R2：资源证据不完整 + I/O 口径错误

- **问题**：samples.json 只保存摘要（`all_scope_summaries`），逐次快照、边界值与采样间隔未落盘，摘要不可事后核对；I/O 直接输出边界累计值（100→130 报 130）。
- **修复**：`ScopeSamples.evidence()` 序列化完整原始证据（boundary_start/end 全字段快照、逐次样本含时间戳与 read_status、sample_gaps_ns、notes），`samples.json` 同时保存 `scopes`（摘要）与 `evidence`（原始证据）；新增 `io_interval_bytes()`：I/O 区间增量 = end−start，read/write **独立**处理缺失（任一端 None→null+`io_*_missing_at_boundary`）与 reset（end<start→null+`io_*_reset_detected`，不受影响方向的真实零保留），累计值仅作 `cumulative_end` 参考字段并显式标注 "NOT the interval amount"。
- **回归**：`test_io_interval_is_delta_not_cumulative`（100→130 输出 30）、`test_io_reset_detected_as_null`、`test_io_one_sided_availability`（单边缺失时另一边仍报 delta）、`test_io_missing_kept_null`、`test_evidence_serialized_with_boundaries_and_gaps`、`test_samples_json_keeps_raw_evidence_not_only_summary`（run 目录内边界值与 reader 脚本值逐字段一致）、`test_analyzer_evidence_check_present`（analyzer 输出 evidence_check：boundary 存在性/原始样本数/缺口数）。analyzer limitations 同步声明 io 为区间增量口径。

### R3：collection 软链接逃逸

- **问题**：`guard_run_dir` 以 `collection_root.resolve()` 为锚——collection 目录本身是指向项目外的 symlink 时，目标目录解析后仍在"该锚"内而被放行。
- **修复**：锚定改回 `data/raw/generated` 的**真实解析路径**；collection 路径**逐段检查**，任何 symlink 段（无论指向项目内或外）一律拒绝；`.`/`..`/分隔符段拒绝；接入审计 catalog 旧源根保护（复用 PREP-01 `report_writer._catalog_protected_roots`，catalog 缺失时静态保护仍生效）；destination 真实路径必须在 collection 真实路径内。
- **回归**：`test_guard_rejects_collection_symlink_escape`（用户反例原样复现，现被拒）、`test_guard_rejects_collection_symlink_even_inside_project`（指向项目内也拒）、`test_guard_rejects_ancestor_symlink_escape`（中间祖先 symlink）、`test_guard_rejects_dotdot_collection`、`test_guard_rejects_catalog_protected_generated_root`（sources.yaml 旧源根覆盖 generated 时 writer 完整反例）。

### R4：产物预算异常破坏交付流程

- **问题**：`count_artifact_bytes` 超限抛 `BudgetExceeded`，`_archive` 的 except 不含 RuntimeError——异常穿透 runner，无法返回独立状态；且产物计数只覆盖 candidate.patch。
- **修复**：归档产物预算改为**软计数**（`would_exceed_artifacts` 预检 + `account_artifact_bytes` 记账不抛异常）：可选大产物（candidate.patch、samples.json）超限时**跳过写入**并记入 `skipped_files`；最小失败证据（metadata.json、manifest.json）**强制写入**（仍计账）；events.jsonl 于封存后按最终大小补记。`archive_status` 值域扩展 `budget_exceeded`（ok | failed | budget_exceeded）。metadata 显式声明 `artifact_accounting_scope`（runner 归档文件 + events.jsonl，**不宣称**覆盖进程全部输出如 harness/verifier 工作目录、容器层）。
- **回归**：`test_artifact_budget_exceeded_still_delivers`（上限 1 byte：三状态 ok/ok/budget_exceeded、metadata 保留 execution/evaluation 状态与 skipped 清单、无异常抛出、容器清理完成）；`test_artifact_budget_counts_all_archived_files`（正常路径计账 == run 目录全部文件字节总和，含封存后补记的 events.jsonl）。

### 返修验证

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests            → 319 OK
项目外 cwd 绝对路径 discover                                         → 319 OK
用户反例复现脚本（collection symlink / io 100→130 / 产物上限 1 byte）→ 拒绝 / 30 / budget_exceeded
py_compile / git diff --check / 敏感扫描                             → OK / OK / 无命中
```

骨架声明（维持）：`SwebenchVerifierRunner`、`MiniSweAgentHarness.run`、`DockerCliRuntime` 的真实执行路径仍是明确标注的**接口骨架**（未授权即拒绝执行）；本轮修复不改变该状态，不构成真实链路已实现。

骨架声明（维持）：`SwebenchVerifierRunner`、`MiniSweAgentHarness.run` 的真实执行路径仍是明确标注的**接口骨架**（未授权即拒绝执行）；B 批仅运行了自有 canary 路径（`DockerCliRuntime` + `CgroupV1FileReader`），未运行 mini、未运行 swebench evaluator 代码。

## 7. 停止声明

C 前离线实现包（§5.9–§5.13 七轮返修）与容器验证（§5.14：canary r7 双分支停止链 + storage-opt 实测、隔离 gold-patch verifier 评估兼容性验证）执行完毕并停止。当前状态：arm64 环境准备与**评估兼容性均已实测验证**；C 执行链离线实现并经真实 mini 贯通；停止链/管道/产物口径修复完毕。剩余唯一前置：G0 集中评审 + C 清单（§3）批准。未批准前不启动真实模型请求、不执行 Agent 任务。
