# 软件、环境与研究复现契约

本页是下一批的设计要求，不授权预检、安装或实验。历史 raw、catalog、批准、marker、manifest 不改写。

后续实测的统一记录与验收清单见 [trace 契约 §10](trace_contract.md#10-后续真实执行的必备记录real-run-measurement-01)。Coding/DocOps 新执行路径自动封存 `environment.json` 与 `measurement.json`；环境是执行当时的宿主观察，不补写历史环境，也不是依赖 lock。采集代码变更进入身份，旧冻结值/批准保持原样，不可授权修改后代码。

## 当前真实缺口

`pyproject.toml` 使用版本范围（含构建依赖），仓库目前没有可验证的全环境 lockfile。`references/manifest.yaml` 是 partial 参考登记，空 commit 不是 latest，也不代表正式实验实际使用版本。当前包清单是环境观察，不是可重建 lock，不提供历史环境证明。

已生成 [本地包版本观察](local_package_observation.json)：2026-09-20 只读两个既有 venv 的 dist-info METADATA，记录包名、版本、元数据哈希及解释器文件哈希；未执行这些解释器、未导入第三方包、未读取环境变量或凭据。它不覆盖实际全部模块字节、wheel来源和系统库，不能宣称完整环境冻结。

不能离线凭空补依赖解析结果或 wheel 哈希。下一批真正使用的 Python/依赖须从指定环境导出，明确直接/传递/构建依赖和平台；优先保留已使用 wheel 的真实哈希，无法取得则列缺口。解析/下载/安装必须另批，禁止为通过检查填造锁文件。

## 下一批必须分别记录

| 类别 | 最小字段 | 缺失处理 |
| --- | --- | --- |
| 软件 | runner代码 SHA、解释器绝对路径/版本、直接与传递包版本、依赖清单哈希 | 环境未指定或关键版本未知时不标 ready |
| 实际使用的来源 | dataset revision、task record SHA、harness commit、容器 digest、来源许可/使用约束 | 不要求冻结未使用的参考仓库；未知许可先审阅 |
| 平台 | CPU 型号、架构、kernel、runtime版本；涉及 PMU 时记录 perf/事件与权限 | 不支持项写 unavailable 和原因；不主动恢复 perf 路线 |
| 比较条件 | CPU/memory limits、governor、SMT、NUMA、文件系统、cache初态/是否受控 | unknown 仍可描述测量，但禁止相应因果推断 |
| 模型 | API/model identifier、harness配置、日期、provider版本可得性、重试/采样参数 | 不保存密钥；服务端漂移作为限制，lockfile不能冻结服务 |
| 血缘 | 采集时刻、采集主体/执行上下文、actual/registered/unknown、输入输出SHA | 计划配置不得冒充运行时观测 |

不要求每次为了未知平台字段额外开发通用探针。优先复用已有预检与封存字段；新增探测只有在任务授权范围内执行。历史缺失不得用今天的主机值补填。

## 状态维护

并发修改须遵守根目录[AGENTS.md](../AGENTS.md)及[状态防丢失流程](project_state_protection.md)：不同对话使用独立worktree；状态通过`python3 -B -m scripts.update_project_state`自动快照、校验读取时SHA256并合并更新。禁止用整文件Git回滚清除未知的未提交状态。

`project_state.json` 是日常进度唯一真源，不被任何 runner 用作批准记录。
其 evidence 保留来源哈希，公开摘要只由README、文档索引和项目总览三个当前页面的PROJECT_STATE块展示；归档旧文档不再跟随当前状态更新。
修改状态时同步对应块；运行 `python3 -B scripts/check_project_state.py` 检查漂移和证据哈希。
脚本只读，不自动修改文档或放行实验。历史 catalog 的 status 是当时计划快照，当前状态以真源为准；安全开关保持原值。

历史文档迁移见[历史索引](history_index.md)与[路径登记](archive_index.json)。历史manifest中的旧路径是原始来源标识，不替换成内容不同的新规范；需要核验时按索引定位，并比较该manifest原登记的SHA-256。原版本与归档版本哈希不同仍是内容漂移，不能因“已找到新位置”而判通过。归档仅在本机，不随GitHub代码分发。

## 纯离线检查

`python3 -B -m unittest tests.test_project_state` 仅使用临时合成文件，标准库即可运行。
`.github/workflows/offline-checks.yml` 只支持手动触发：runner 分配后测试不联网、不安装依赖、不运行实验。GitHub 获取代码和设置 Python 本身仍需平台网络，不能称整个 CI 服务封网。涉及本地未入库 raw 的 P3 回归在本地单独运行，不伪称公开 CI 可恢复全部数据。
