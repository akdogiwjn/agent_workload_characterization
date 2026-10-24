# VIMAX-MEDIA-ENTRY-REPAIR-01：媒体生成入口修复记录

日期：2026-10-24。范围：修复 ViMax 媒体生成入口的本地启动与取证问题，用真实生产入口完成一次禁网冷启动全链验收，并验证异常清理。未读取真实凭据、未调用真实 API、未创建正式 APPROVAL/ATTEMPT、未消费付费生成额度。基线镜像 `vimax-task-bailian:arm64-v7-capability-planning-01`（`sha256:a97ea607…1f176f3`，linux/arm64，与宿主 adapter-src 89 文件逐哈希一致，未重建镜像——本轮全部修复在宿主侧/挂载入口层）。

## 一、已确认问题与修法（4 项用户指定 + 3 项本轮新发现）

| # | 问题 | 根因证据 | 修法 |
| --- | --- | --- | --- |
| 1 | PILOT-02 宿主 runner 字典切片（`record["k":"v"]` 语法合法、运行时 TypeError） | PILOT-02 run-01 `primary_error: TypeError: unhashable type: 'slice'`（该行已在 PILOT-03 修正） | **防复发**：`test_host_lifecycle.py` 用 FakeOps 驱动 `start_attempt` 全代码路径（4/4 通过），此类错误会在生命周期测试执行时抛出，编译检查不再作为唯一防线 |
| 2 | PILOT-03 `seed_session` 顺序：先读 `.vimax/sessions.json` 后构造 `SessionIndex`（构造器才初始化该文件）→ 全新 workspace 必现 FileNotFoundError，容器在 ACK 后 rc1 退出 | PILOT-03 run-01 失败分析：workspace 仅 STARTUP-* 三文件、无 session/media；本修复目录 `before-snapshots/generation_entry.pilot-03.py` 112-114 行 | 修复版 `generation_entry.py`：先 `SessionIndex(ROOT)`（构造器安全初始化），再 `index.get(SESSION_ID)` 判重（同名仍拒绝、不覆盖，反例 A 验证）；全程 ENTRY-PHASES.jsonl 阶段记录 |
| 3 | `VIMAX_STARTUP_HANDSHAKE_ONLY=1` 握手即退出，不能证明冷启动 | PILOT-03 handshake-probe 通过但正式 run 立即失败 | 修复版 entry **删除握手捷径**：只有一条生产路径（gate → seed → agent → render）。冷启动验收（cold-start-acceptance）与正式 run 用**同一 runner/entry**，仅 env/网络 overlay 不同 |
| 4 | 容器退出后未保存 stdout/stderr 与 Docker logs 即删除 | PILOT-03 failure-analysis：`exception_type: unknown; Docker stdout/stderr was not persisted` | 修复版 `host_runner.py`：容器启动即起 `docker logs --follow` 线程（写 container-stdout.log），删除容器前限时补取全量（container-logs-final.log），follow 线程独立 join；反例 B/C 验证失败路径日志均在 |
| 5 | **（新）fake/生产 URL 域名未过 provider 检测**：`api_provider_from_base_url` 按 `maas.aliyuncs.com` 关键字路由，裸 `127.0.0.1` 的 fake URL 触发 `Unsupported video base_url` | 冷启动 run 1：`Render failed: Unsupported video base_url ... http://127.0.0.1:8666` | fake 域名走 `--add-host ws-fake.cn-beijing.maas.aliyuncs.com:127.0.0.1` + `FAKE_PUBLIC_HOST`（runner 新增 `add_hosts` 配置；仅验收配置使用，正式路由不变） |
| 6 | **（新）MoviePy concat 稳定失败（"failed to read the first frame"，第 4-5 个 reader）** | 决定性证据：宿主 256 核 → 容器 nproc=256 → imageio_ffmpeg 每个 reader 的 ffmpeg 自动开 ~116 线程；`--pids-limit 512` 下第 4 个 reader 的 ffmpeg `pthread_create` 失败、静默退出（audit 捕获 rc=255、MoviePy 读到 0 字节帧）。手动单开正常、并发 4+ 必挂 | runner 加 `--cpuset-cpus 0-7`（与 `--cpus 8` 配额对齐）：容器 nproc=8，ffmpeg 每进程 ~8 线程，8 reader 并存稳定（修复后连续两次全链 concat 成功，40.0s 成片）。附带收益：资源采样语义与配额一致 |
| 7 | **（新）SIGTERM 收尾路径伪造失败标记**：握手等待中的 `SystemExit(0)` 被 `except BaseException` 捕获 → 写 ENTRY-FAILED 且容器 rc 变 1 | 冷启动 run 5：render 成功但 ENTRY-FAILED 存在（`SystemExit: 0` traceback） | entry 的 `main()`/`run_attempt()` 异常处理显式放行 `SystemExit`（成功收尾不写失败标记）；run 6 验证：无 ENTRY-FAILED、容器 rc 0 |

**候选（未定论）**：无——上述 7 项均有直接复现证据。另记录：PILOT-03 时代 `VIMAX_LLM_API_KEY` 等注入为真实凭据值；本轮冷启动验收的 `AcceptanceOps` 完全不触碰登记凭据文件（fake key + 127.0.0.1/回环域名）。

## 二、禁网冷启动全链（核心验收）

命令（可复用的固定入口）：
```
python3 env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py cold-start-acceptance \
  --out <新目录> \
  --config env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/configs/acceptance-cold-start.json \
  --env-overlay env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/configs/acceptance-env-overlay.json
```
环境：空 workspace、`--network none`、`--read-only` 根 + tmpfs、uid=当前用户、`--memory 8g --cpus 8 --cpuset-cpus 0-7 --pids-limit 512`、无真实凭据（fake key 仅入容器 env）。

**连续经过（同一次运行，宿主启动→归档）**：容器创建 → 归属核验（label 匹配）→ cgroup 采样就绪（0.5s，91 点）→ READY/RELEASE/ACK 握手 → session 初始化（空 workspace，SessionIndex 安全建档）→ 原规划复制 + 12 文件哈希核对 → 原生 `main_agent --jsonl --once`（真实 Agent/runtime/工具注册）→ 媒体专用工具策略（仅 vimax_render_video，单次渲染锁，caps 校验）→ 真实原生 render pipeline：3 肖像 + 8 首帧×2 候选（19 图）+ reference/best 视觉选择（LangChain 结构化输出）+ 7 过渡视频 + 8 主体视频（15 create）→ scenedetect 过渡切帧 → 原生 FFmpeg concat（只拼 8 主体）→ 导出 final_video.mp4 → 完成握手 → 最终采样边界 → 容器 stop/logs 补取/rm/删除核验 → 归档。

**fake 只替换外部 API 边界**：LLM chat（agent tool-call + 内部 LangChain JSON 路由）、图片生成（合成 PNG）、视频创建/轮询/下载（8 major + 7 transition 合成 MP4，按 prompt 模板区分种类）。未替换：seed_session、main/AgentLoop、render 工具与 pipeline、session 存储、规划复制、宿主生命周期、FFmpeg 执行、验收器。

**验收结果（acceptance.py，22/22 检查通过）**：
- fake 发送计数：图片 **19**（3 肖像 + 8×2 候选）、视频 **15**（**8 major + 7 transition**）、账本与 fake stats 双向一致
- 8 主体 shot→major-clip SHA-256 映射 {0..7→0..7}，final 成片每段（5s 中点抽帧编号）与映射**按序完全一致**；7 个过渡视频映射 transition clip 且**不进入 final concat**
- final：H.264 / 1280×720 / 30fps / **40.0s**（≈8×5s 容差内）/ 无音轨 / 完整解码
- 入口证据：COMPLETE（render_tool_ok=true、agent rc 0）、ENTRY-PHASES 全序、无 ENTRY-FAILED、容器 rc 0、删除核验通过、cleanup_errors=[]
- 资源：91 点@0.5s（cpu 82.8 core·s / wall 45.3s / avg 1.83 cores、内核内存峰值 1.65GB、blkio 写 458,752B 有据）、netns 25 点、逐点样本落盘

## 三、异常反例（10 项全过）

| 反例 | 结果 |
| --- | --- |
| 1 字典切片类错误被生命周期测试检出 | FakeOps 全路径 4/4（normal/netns-fail/write-fail/deadline） |
| 2 空 workspace session 初始化 | 冷启动验收本体（SessionIndex 安全建档） |
| 3 已有同名 session 拒绝不覆盖 | A：`already exists` 拒绝、sessions.json 未改、零发送 |
| 4 规划哈希不符发送前拒绝 | B：`frozen source script hash mismatch` + traceback、零发送 |
| 5 采样/握手失败时发送计数 0 | 生命周期 netns-fail：无 model-events |
| 6 初始化抛错时堆栈保存 | B：ENTRY-FAILED traceback 非空 |
| 7 首次 API 失败错误与请求记录保留 | C：agent error 事件 + 容器日志保存 |
| 8 ACK 后 rc1 退出仍保存日志再删除 | B：container-stdout.log + logs-final 均存、删除核验 |
| 9 导出/报告失败仍清理 | 生命周期 write-fail：清理命令照发、错误保留 |
| 10 deadline 回收 + partial 归档 | 生命周期 deadline：kill + phase_boundaries 保留 |

## 四、正式任务复用入口（唯一命令）

后续正式生成（真实凭据、真实 API）使用同一 `host_runner.py` + `generation_entry.py`：
```
python3 env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py run \
  --out <正式输出目录> --config <正式配置 JSON>
```
正式配置与验收配置的差异仅：`network: bridge`、真实 LLM/图片/视频 base_url（runner 内置注入，凭据运行时读取）、`entry_command` 无 fake、无 extra_mounts。**注意**：`--cpuset-cpus 0-7` 已内置（问题 6 修复对正式任务同样必需——正式 concat 同样会并发开 8 个 reader）。

## 五、状态

**禁网生产接线通过 ≠ 真实供应商生成成功**（后者需下一次授权）。未覆盖的生产分支：真实 API 的鉴权/限流/失败重试路径（429-only 重试策略已在代码中但未在真实端验证）、真实媒体质量、bridge 网络下的外网路由（本轮验收为 network=none；bridge 黑洞问题此前已登记，正式 run 需现场 DNS/TLS 预检——host_runner 已具备）。
