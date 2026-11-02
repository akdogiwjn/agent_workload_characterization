# 文档索引

日常只读当前文档，不再默认打开旧任务书。事实源为[project_state.json](../project_state.json)。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-11-02 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前目标：分析Agent单任务的CPU、内存、磁盘I/O与占用、网络、时长及工具/软件使用，保留过程曲线、环境与采样质量；不要求GPU或函数热点。
- 公开trace已完成限定操作/软件汇总v3：SWE-rebench 9,435轨迹、SWE-bench现登记20,023对象/41组（原v3为19,876，后补147）、OSWorld 755模型×任务记录/108任务（命令解析扩展至v4，原生/源码分层）、H-EPM 414轨迹；AgentX Full/256k及Applied提供宏观证据：AgentX两版同393会话，98,827/68,266请求，仍无业务工具明细或本地资源。未穷尽语义解析，不混合来源分母或把软件声明当实际启动。
- SWE-bench逐任务评价补全：轨迹登记仍20,023对象/41组，另下载20,098份评价/配套文件，40/41组有公开评价产物。原8,730个未列项补出8,476未解决、140已解决、9未生成、1超时，余74空报告/30缺报告；MAYA补出222项，Mindlink同名公开来源仍缺366项评价。5个结果冲突单列；KGCompass更正300个任务身份，跨组去重实际2,294任务。仍无资源证据。
- H-EPM/ToolSandbox复核v3完成：414轨迹、2,021次调用/返回，按保存请求静态核实全部原生工具身份，原24次未知及2次仅有活动分类的调用均补出确切名称。406条有用户侧结束请求，402条有返回，4条仅保存请求、8条无请求；Agent终止原因及资源等未记录。两组不同源码且均有local changes，只作描述比较。
- SWE-rebench复核v3完成：85分片、9,435轨迹/111任务/17 participant完整核验；598,148请求/616,980结果的差额按589,061唯一ID配对、27,059未调用报告、860提取错误及其1,875候选、7,201提交分支请求与11复杂提交末尾请求核清。Junie 555轨迹的31,449步骤摘要另列，不当作零工具行为；任务失败不等于分析未完成，仍无本地资源证据。
- Coding、Office、Assistant合并分析v3保留9个固定任务各3点，共27个task×round观察；累计35次启动包含8次排除的Office错路由记录。不同scope/配置分层，失败记录不删除，不代表类别总体。
- 新口径已记录可用CPU、内存、有限I/O、共享netns及任务目录边界；旧run缺失字段不回填。资源不是整机、远端模型或单工具独占成本；实际HTTP次数、费用及共享cache归属仍unknown/unsupported。
- G1仅登记限定小闭环；G2/G3-R未通过，CPU-02/Replay暂停。当前准备门禁未通过；不将此前授权延伸为新执行授权。
- 状态防丢失保护完成：独立worktree规则、自动快照、协作锁和读取时SHA256校验已接入，33项状态/AgentX测试通过。本次远程检查点继续排除视频修改；完整恢复状态保留本机，Git HEAD不能代替完整本地状态。
- 当前范围：本地单任务CPU、内存、磁盘I/O与占用、网络、时长、工具/软件统计和过程图；模型用量、阶段/错误、环境和采样质量一并记录。GPU、热点/PMU/微架构/优化不必交，Replay/并发仅可选。
- 本地三个既有批次的27个显式run已完成字段与manifest盘点；历史区间覆盖v3按CPU、cgroup I/O及可用/proc I/O分列候选/有效/gap，网络字节和任务目录边界占用没有观测，未回填。
- 新口径三链各一次已完成：Office目录扫描cwd修正后0→6629B；Coding Agent/verifier目录分别增长4874269/4614250B；Assistant场景内存状态N/A。主项采集和归档通过，cache仍unsupported导致supplement aggregate partial；共享netns不是任务/API专属字节。
- 火山三链各n=1限定离线分析完成：3张独立四面板资源SVG、作图CSV和目录占用表已生成。请求Office8、Coding20、Assistant Agent/User6/1；原生工具、Submitted控制流与业务错误分别统计。Coding宿主末次process_exited保留gap；共享netns不代表API字节，不合并旧27次。报告：reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/summary.md。
- LOCAL-THREE-CLASS-COMPLETE-02已顺序执行12/12次，identity 8a17109cf441e3ae68e3f9820babe5685467657cbcafb56d765dd1158dc4942d；合并原有效样本后27个固定task×round槽位各n=3，累计35次启动含8个永久排除的旧Office错路由attempt。v3独立复核及资源图已生成；7/7固定镜像批后身份匹配，raw归档哈希回读通过。n=3不代表类别总体，HTTP次数/费用unknown。报告：reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md。
- G1仅登记小闭环通过；G2/G3-R未通过，CPU-02/Replay继续暂停。状态、建议、旧批准和旧execute命令都不是新授权。
- AgentX深入分析第1步完成：Full/256k同393会话、98,827/68,266请求；上下文演化、已完成历史前缀潜力、容量简化模型、请求重叠、筛选影响及时间局部性已分析，生成10张4K PNG/SVG、作图CSV和10页PPT。20项测试与216次真实请求穷举核对通过；模拟潜力不当作缓存命中/硬件并发。后续本地mock回放与DeepSeek客户端重复测量见AgentX五类重复实测报告。
- AgentX后续客户端测量收尾：Full全量分析为393会话/98,827请求；所选5会话各执行3次，为117个唯一源请求、351次正式客户端执行。仅测客户端，未执行原始业务工具，原始长输出负载未完整复现；这三项为证据边界，不是待补跑任务。
- 2026-10-25视频代码与文档远程检查点：合并远程AgentX收尾与状态工具更新，保存四仓库运行/观测代码、122项限定离线回归及小型配置报告；上游适配差异另存文本补丁。模型、媒体、raw轨迹/采样、安装包及local_archive留本机；本次无新执行授权。
- 2026-10-25按用户偏好统一原目录main工作流：本地main已安全对齐远程合并检查点；后续默认在原目录提交和非强制推送，不自动创建分支/worktree，多对话协调文件并串行Git操作。模型、媒体、原始运行证据和本机归档继续留本地；历史分支不自动删除。
- 2026-10-24 AgentX运行依赖归位：八个旧AgentX工作树已合并收拢入main（输入迁入data/raw/agentx-*并保持Git忽略，mock环境接入.venvs/agentx-replay，脚本经scripts/agentx_worktree_locations.py解析历史路径）；最终原始证据保留在/home/lcq/agentx_evidence_backup_20261023/（SHA已核验）；main离线路径可用（AgentX 91项单测＋合成fixture mock链通过），未调用真实API、未重跑正式实验，无新执行授权。
- 视频当前成果：16个历史保留仓库×任务组合／9个输入（四仓各4项）；7组连续主流程raw可定位、3组ViMax规划/媒体分阶段、5组含独立恢复、1组video-use E03 raw待定位。16不是连续成功或逐条回放验收数；ViMax musicians原运行＋独立拼接恢复已纳入索引。
- video-use E01/E02/E03历史报告记载连续剪辑并完整评分reward=0，其中E03当前索引raw父目录为空，不能凭摘要判原始trace可用；OpenStoryline E01/E02/E03为原render＋独立恢复评分，原失败保留。完整研究记录不要求正reward。
- ViMax、VideoWeaver均有G01/G02/G03真实生成成片；ViMax规划/媒体分阶段，G03原规划离线复验后完成媒体。百炼远端生成不计入本地资源；来源/usage缺口与原FAIL/修订PASS保留。
- 2026-10-29按用户要求直接删除2093个无用视频中间文件（468109547表观字节），不归档内容；1110个保留结果文件SHA核对不变，删除清单见docs/video_cleanup_20261029_receipt.json。生产依赖、素材、模型/环境及非视频数据不动。
- 视频下一阶段按用户明确目标准备9组完整流程重跑：保留OpenStoryline四组与ViMax四组（分阶段G01/G02/G03也重跑），加入video-use E03完整trace补采；不缩减为5/6组。逐项新身份/预算/批准，当前仅计划、未授权/未启动。
- 2026-10-30 ViMax musicians 规划接线离线完成（v7入口参数化13镜头）：真实plan_verifier对13镜头合成workspace ok=true＋8/9/10/缺镜头/重复/错引用/环/剧本变更/媒体ledger反例全拒绝；planning_entry自检（首帧capability/allowlist/8192/30逻辑/250000观测/900s/enable_thinking=false）；plan-check.ok为成功判定。模型/媒体零真实发送，真实规划与声音适配待用户授权。
- 2026-10-30 ViMax musicians 规划链四项缺口收尾完成：真实run_attempt全链（身份绑定config/task_context/生产代码、采样就绪放行、容器退出五状态判定、netns RX/TX独立）离线验收，50项测试通过；模型/媒体零真实发送，真实规划与声音适配待用户授权。
- 2026-10-30 OpenStoryline assembly task1 离线接线完成：task_kind=assembly 路由+12文件门禁+solution来源导出+技术验收；本轮接通 understand_clips/filter_clips/group_clips 任务作用域注册、视频抽帧→image_url→vlm 视觉路由与原生 RenderVideoPipeline 四段整段拼接（均容器内禁网实测），40项测试通过；真实供应商视觉兼容性与12选4选片 needs_real_validation、官方评估 not_integrated、capability_blocked 保留；模型/媒体零真实调用。
- OPENSTORYLINE-ASSEMBLY-RELIABILITY-REPAIR-01完成通用assembly可靠性修复（截断/解析/预算贯通、模式语义、render计划门禁、递归参数化）与离线生产链验收；既有task1失败保留，真实语义选片与端到端仍待新授权。
- OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-03完成一次基于可靠性修复版本的真实assembly attempt：截断被正确标记为工具错误、严格默认拒绝生效、无旧计划复用；但供应商在filter节点2048上限下反复截断，Agent于32步递归超限（GraphRecursionError）无提交物，记为完整失败观察（不增加完成覆盖）。
- OPENSTORYLINE-ASSEMBLY-FILTER-BUDGET-PROBE-01完成：filter输出额度2048→8192单次真实文本请求返回完整可解析结果（stop/2345tokens/解析通过/选中10候选全属输入）；归因确认EXECUTION-03的10次length含understand overall 1次1024+filter 9次2048；非正式attempt，不增加覆盖。
- OPENSTORYLINE-ASSEMBLY-SELECTION-CONTRACT-REPAIR-01完成：storyboard assembly内部选择/排序提示与配置契约一致（filter按K槽位选K段、group已选K段按slot排序，取消通用80%保留与通用叙事重排），assembly专用模板/契约传递/校验与预算8192落地，通用与interview不变，离线生产链验证通过。
- OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04原运行记录：storyboard选择、group、plan、render真实完成；当时入口误用interview完成判定而failed且无自动提交，原状态保留。现已在独立recovery-COMPLETION-01命名空间从同一render/timeline恢复solution并通过修订技术验收，不追溯为原attempt连续成功。
- OPENSTORYLINE-ASSEMBLY-COMPLETION-AND-RECOVERY-01完成：assembly完成判定按任务类型贯通（persist_completion_check成功路径写render_artifact_id）、时间策略分开（源/连续性10ms、成片帧周期容差），并对EXECUTION-04独立恢复导出solution.mp4/solution.json通过技术验收（旧10ms策略如实FAIL、新帧周期策略通过、完整解码、逐字节一致、原状态未改）。
- 2026-10-31视频文档收尾：assembly独立恢复成果已纳入14组合／8输入索引；原21项overlay运行身份与后续23项overlay修复版本分列，恢复不额外计attempt/输入、不并入原资源窗口。task1无需专门重跑，未来自动收尾可随另行授权的新任务验证；musicians音频能力与适配范围先核查，不默认批准无声版。本轮无代码修改、无API或新运行。
- VIDEO-MUSICIANS-AUDIO-READINESS-01完成：musicians有声能力审计（故事要求环境声/演奏声/静默/人声/同步；两仓生成侧无声但拼接保留音轨；wan2.6公开音频文档未检索到=unknown）；限定离线修复VideoWeaver有声media_profile（aac+非静音验收），测试通过；audio=true真实启用与方案选择待用户决定。
- VIDEO-MUSICIANS-NATIVE-AUDIO-INTEGRATION-AND-PROBE-01完成：官方确认wan2.6-i2v-flash有声能力（更正上轮404结论），两仓配置→payload audio接线补齐+有声媒体验收profile驱动，离线验收通过，一次真实720P/5s/audio=true探针成功输出AAC非静音可解码视频；完整故事未运行，语义未评估。
- VIDEOWEAVER-MUSICIANS-AUDIO-EXECUTION-01完成一次真实13镜头有声任务：13首帧+13段wan2.6 audio=true+原生merge→65.13s AAC非静音final，judge 44/44；语义not_evaluated、官方not_run；探针记录已整理不计组合；成果索引更新为15组合/9输入。
- VIMAX-MUSICIANS-PLANNING-EXECUTION-01完成一次ViMax musicians真实规划：plan_verifier通过（13镜头/3角色/13相机/12过渡），0媒体、18 LLM请求、54k tokens，容器自然退出与清理；音频路线native非visual_only；媒体阶段未运行，规划不计完整生成覆盖。
- VIMAX-MUSICIANS-IMAGE-THROTTLING-AND-CLOSEOUT-REPAIR-01: 离线修复图片流控/取消收尾并归档历史失败（未调真实服务/未启动正式媒体）
- VIMAX-IMAGE-POLICY-FOUR-POINT-FINAL-CLOSEOUT-01: 离线闭合 manifest/deadline/数值校验/Retry-After 四点（未调真实服务/未启动正式媒体）
- VIMAX-MUSICIANS-AUDIO-MEDIA-EXECUTION-02: 唯一正式媒体运行已执行——媒体生成/下载成功（11图+25视频、audio=true）、原生拼接失败（无final）、未补跑/未追加attempt
- VIMAX-MUSICIANS-AUDIO-CONCAT-RECOVERY-01: 原运行+独立本地拼接恢复成功（根因=读取器线程超pids限制；修复=线程有界+AAC+clip关闭；final 65.13s/720p/H264/AAC）
- 2026-10-31视频完整流程目标更新：16组合／9输入不变，重跑清单扩为9组R01–R09（OpenStoryline四组、ViMax四组、video-use E03）；全部目标为完整跑通和声明阶段trace/资源留存，旧结果保留，本轮仅更新文档。
- R01 completed (OPENSTORYLINE-E01-FULL-FLOW-R01-02, 2026-10-31): complete normal flow - native interview chain to render, Agent rc=0, host export output.mp4/cuts.json from final rendered timeline, technical check passed, official verifier complete reward=0.0 (legal), container removed; R01-01 failure observation preserved unchanged
- R02 completed (OPENSTORYLINE-E02-FULL-FLOW-R02-01, 2026-11-01): complete normal flow - native interview chain to render, Agent rc=0 (479.66s), host export output.mp4/cuts.json from final rendered timeline, technical check passed (frame-rate exact 60000/1001, 0 ppm), official verifier complete reward=0.0 (legal), container removed; E02-EXPANSION-01/02 observations preserved unchanged
- R03-01 remains a fully collected failed observation, not completed: first rough-cut incomplete; second full per-sentence pass exhausted 60 requests before 31 local rejections were misclassified as parse failures. Offline typed budget propagation repair verified; no budget/strategy change or rerun; R01/R02 remain complete.
- E03 request-budget readiness (OPENSTORYLINE-E03-REQUEST-BUDGET-READINESS-01, 2026-11-01): offline derivation - recommended single-task max_logical_requests=100 (2 validation+7 agent+82 two-round rough-cut+9 margin; floor 91, alternate 96), draft E03-full-flow-r03-02-budget-draft.json unreviewed/zero-send, minimal generic request_budget passthrough wired (default 60 preserved); zero real services/Agent/identity/approval/attempt; R03-01 failure preserved, no run started
- E03 budget fence and chain offline closeout (OPENSTORYLINE-E03-BUDGET-READINESS-FINAL-CLOSEOUT-01, 2026-11-01): only max_logical_requests may follow frozen identity (100 proposal); token-soft 1M and output 32768 fixed ceilings restored; real freeze->approval->execute_once request->container configure_budget->ledger chain verified offline (host 6 + container 11 PASS); formula corrected 82+2+16=100, 91=estimate basis, E01 tail 43.646s, two-round ~1424.6s estimate; zero real services/Agent/identity/approval/attempt; R03-01 failure preserved; 100 still awaits approval
- R03 completed normal workflow and trace/resource collection (OPENSTORYLINE-E03-FULL-FLOW-R03-02, 2026-11-01): Agent rc=0; 52/52 requests closed; 8 Agent tools + 2 automatic dependencies; technical PASS; official evaluation complete reward=0 (not semantic success). Agent requested [29190,38760]ms but actual deletion [29190,30810]ms; 41/41 call/parse successes do not prove correct deletion. Approved cap 100 is headroom, not proven necessary (52 also below old cap 60). R01/R02/R03 complete; R04 next, not started; historical failures unchanged.
- R04 completed (OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01, 2026-11-01): complete normal assembly flow - understand(12)->filter(K=4 distinct)->group(slot order)->plan->render, Agent rc=0 (475.00s), task-kind-aware completion gate, host export solution.mp4/solution.json (byte-identical, structural 10/10 PASS), official not_integrated reward=null semantic not_evaluated; assembly budget 60 preserved; EXECUTION-02/03/04 preserved unchanged
- R05 planning phase completed (VIMAX-G01-FULL-FLOW-R05-PLANNING-01, 2026-11-01): new G01 planning passed - 8 shots/1 character/8 cameras/7 transitions, plan_verifier 14/14 checks, 0 media requests, 13 logical requests 37873 tokens, attempt 77.99s, container removed; media budget draft (image_creates 5, video_creates 15, downloads 20) prepared not authorized; media phase pending approval; historical plans not reused
- R05 media budget and resource closeout (VIMAX-G01-R05-MEDIA-BUDGET-AND-RESOURCE-CLOSEOUT-01, 2026-11-01): media budget corrected to 19 images/15 videos/34 downloads from the real production branch (8 cameras all candidate + 3 portraits); resource periodic-window derivation (77.068s, 4.575 core-s, 98KiB write) added; planning sampling final-boundary ordering fixed (sampler.stop before docker wait, container-verified); media phase still pending separate approval; zero real services, no media identity/approval
- R05 four-gap offline closeout (VIMAX-R05-FOUR-GAP-OFFLINE-FINAL-CLOSEOUT-01, 2026-11-01): planning completion handshake (boundary ack) closes exit race (real container protocol test PASS); real control-chain tests replace stubs (final_boundary 4 + container PASS); poll upper bound per task 92 (floor(window/interval)+2) and 15-task 1380 vs ledger cap 1800 separate; media budget helper aligned to production missing_info is not None + strict param validation (helper 27 PASS; poll 6 PASS); media still pending approval; zero real services, no media identity/approval
- R05 production boundary and validation final (VIMAX-R05-PRODUCTION-BOUNDARY-AND-VALIDATION-FINAL-01, 2026-11-01): shared read_boundary_and_send_ack production function wired into run_attempt and tested directly (no mirror, run_attempt real control-path + container protocol PASS); ACK schema v2 full validation with per-resource boundary_metrics flowing into run-report (stale/duplicate/partial/timeout/write-fail bounded); helper derived-zero conflict + strict-int attempts (helper 40 + boundary 24 + poll 6 PASS); media still pending approval; zero real services, no media identity/approval
- R05 observation quality and ACK semantics closeout (VIMAX-R05-OBSERVATION-QUALITY-AND-ACK-SEMANTICS-CLOSEOUT-01, 2026-11-01): derive_observation_quality production function wired into run_attempt and run-report (per-metric CPU/IO need start+end, memory gauge/peak need end, zero valid; overall complete/partial/unknown; ack host_write/entry_accept separated; rows_lost != complete); ACK idempotent-message contract (option one, unreachable seen_accept removed); boundary 33 + helper 40 + poll 6 + container protocol PASS; entry dynamic scope = handshake subchain (full run_native source-verified only); media still pending approval; zero real services, no media identity/approval
- R05 observation quality correctness final (VIMAX-R05-OBSERVATION-QUALITY-CORRECTNESS-FINAL-01, 2026-11-01): unified metric schema (_metrics_from_snapshot shared by producer/induction/tests); start boundary per-metric (interval start+end, end>=start, missing->unknown, zero valid); overall aggregates ack/stream-loss/write-error/netns/scope (complete only when all dimensions complete, no internal contradiction); entry observation ownership+complete_token validated (five counterexamples fixed: A consistent complete, B no-start cpu unknown, C ack-fail not complete, D lost-rows not complete, E wrong-token entry not ok); boundary 40 + helper 40 + poll 6 + container protocol PASS; media still pending approval; zero real services, no media identity/approval
- ViMax媒体最终路径限定离线修复完成：原生工作区相对路径与容器绝对路径均安全映射到本次workspace；42项测试通过，历史267项归档回读一致。未重新规划/生成/拼接/启动正式attempt；R05原媒体失败状态保留，未来执行需新身份及批准。
- R06 planning phase completed (VIMAX-G02-FULL-FLOW-R06-PLANNING-01, 2026-11-01): new G02 planning passed - 10 shots/2 characters/10 cameras/9 transitions, plan_verifier ok, 0 media requests, 15 logical requests 43675 tokens, attempt 95.92s, measurement complete; media budget draft (image_creates 12, video_creates 19, downloads 31, natural poll upper 1748) not authorized; R05 stays completed with MEDIA-01 failure preserved; R07-R09 not started
- R06 media attempt interrupted (VIMAX-G02-FULL-FLOW-R06-MEDIA-01, 2026-11-01): in-container media pipeline SUCCEEDED (12 images/19 videos/31 downloads/native concat/final 50.000s H.264 720p30fps no-audio SHA feb348a7...; COMPLETE v3 valid), but production host_runner was killed by an outer tool 120s timeout ~2 min after start (operator launch error, not production defect) so host termination=native_agent_done was not recorded and resource/netns measurement is partial; manual bounded closeout done. R06 NOT marked complete; no second attempt, no host-side stitch, no independent recovery; R07-R09 not started
- VIMAX-MEDIA-MANAGED-LAUNCH-REPAIR-01：新增持久媒体启动器与同执行域证明门禁；59项离线测试及130秒真实采样探针通过；未启动正式任务，R06旧失败/partial保留。
- R06 media COMPLETE normal flow (VIMAX-G02-FULL-FLOW-R06-MEDIA-02, 2026-11-01): launched via scripts/vimax_managed_launch.py (supervisor own session/PGID, runner_exited rc=0, survived past 120s with sampling growth); 12 images/19 videos/31 downloads/native concat/final 50.000s H.264 720p30fps no-audio SHA a85c603d...; COMPLETE v3 all valid, required work within deadline, final path resolution owned/exists/accepted; host native_agent_done rc=0 cleanup verified, resource boundaries complete (5229 samples/netns 1309); remote closeout 19/19 SUCCEEDED audio=false. R06 marked complete; R06-MEDIA-01 interrupted observation preserved; R07-R09 not started
- R07 planning phase completed (VIMAX-G03-FULL-FLOW-R07-PLANNING-01, 2026-11-02): new G03 planning passed via the planning-stage managed launcher - 9 shots/2 characters/9 cameras/8 transitions, plan_verifier ok (15 boolean checks true, semantic not machine-proven kept), 0 media, 14 logical requests 40666 tokens, attempt 87.42s, measurement complete, supervisor rc=0; media budget draft (image 8/video 17/downloads 25/polls 1564) NOT authorized, media phase not started, R07 marked planning_passed_media_not_authorized
- R07 media phase completed (VIMAX-G03-FULL-FLOW-R07-MEDIA-01, 2026-11-02): COMPLETE NORMAL FLOW via scripts/vimax_managed_launch.py (stage=media) - 8 images (6 portraits+2 candidates)/17 videos (9 subject+8 transition)/25 normal downloads/native concat subject 0..8/final 45.000s H.264 1280x720 30fps no-audio SHA d4150200...; COMPLETE v3 all valid, native_agent_done rc=0, container exit 0, cleanup verified, measurement complete, supervisor runner_exited rc=0; remote closeout 17/17 SUCCEEDED audio=false. R07 full normal flow DONE
- R08 planning phase completed (VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-PLANNING-01, 2026-11-02): new musicians audio planning passed via the planning-stage managed launcher - 13 shots/3 characters/13 cameras/12 transitions, plan_verifier ok (15 boolean checks true, semantic not machine-proven kept), audio route native audio=true, 0 media/audio, 18 logical requests 54941 tokens, attempt 102.36s, measurement complete, supervisor rc=0; media budget draft (image 13/video 25/downloads 38/polls 2300) NOT authorized, media phase not started, R08 marked planning_passed_media_not_authorized
- R08 media attempt executed (VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-01, 2026-11-02): via scripts/vimax_managed_launch.py (stage=media) - 13 images (9 portraits+4 candidates)/25 videos (13 subject+12 transition, audio=true)/38 normal downloads/native concat subject 0..12/final 65.15s H.264 1280x720 30fps SHA 8efad313...; COMPLETE v3 all valid, native_agent_done rc=0, container exit 0, cleanup verified, measurement complete, supervisor runner_exited rc=0; remote closeout 25/25 SUCCEEDED usage.audio=true. TECHNICAL GAP: final audio track is MP3 not AAC (expected.audio=aac not met at final-file level) -> R08 NOT complete normal flow
- ViMax audio deployment + technical contract repair closed offline (VIMAX-AUDIO-DEPLOYMENT-AND-TECHNICAL-CONTRACT-REPAIR-01, 2026-11-02): repaired pipeline now really deployed read-only to container import path (in-container SHA + import resolution verified); shared media_technical consumer distinguishes AAC/MP3 and drives host exit semantics (program PASS + tech FAIL -> rc 1, agent facts preserved); native concat resource release fixed; illegal contract values rejected pre-send; 115 tests + 49 subtests fresh; launcher unchanged ff875bc4..., proof valid; R08-MEDIA-01 MP3 failure preserved, no formal media/identity
- ViMax audio contract four-gap closeout offline (VIMAX-AUDIO-CONTRACT-FOUR-GAP-FINAL-CLOSEOUT-01, 2026-11-02): audio effective-value consistency enforced pre-send (omitted/false+aac, true+none, missing/null rejected); media_technical.py + pipeline_fix_mount + technical_contract digest now mandatory frozen bindings (missing/changed/contract-mismatch/deployment-mismatch rejected); technical acceptance shares absolute close_deadline (remaining-budget gate, min(timeout,remaining), zero spawn on exhaustion, timeout reaped); explicit contract fields consumed / unsupported capabilities rejected; duration_tolerance_s required (missing rejected, explicit 0 legal); attempt_wall_s unchanged, total_wall_s includes technical acceptance with phase timing; 146 tests + 49 subtests fresh; launcher unchanged ff875bc4..., proof valid; R08-MEDIA-01 MP3 failure preserved, no formal media/identity; unauthorized 65s next-media contract draft prepared
- R08 media phase complete normal audio flow on the repaired chain (VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02, 2026-11-02): via scripts/vimax_managed_launch.py (stage=media) - 13 images (9 portraits+4 candidates)/25 videos (13 subject+12 transition, audio=true/AAC)/38 normal downloads/native AAC concat (subject 0..12, -acodec aac)/final 65.10s video_stream (65+/-0.5 PASS) H.264 1280x720 30fps AAC SHA ce54ee58...; formal technical acceptance applied+ok (12 checks true, contract digest b15d5f66...), COMPLETE v3 all valid, native_agent_done rc=0, container exit 0, cleanup verified, supervisor runner_exited rc=0; remote closeout 25/25 SUCCEEDED usage.audio=true; attempt 1560.71s/total 1576.92s incl tech acceptance 0.93s. Repaired chain really deployed (pipeline 9a69b0ea... import-verified, media_technical ca96d007... mandatory, technical_contract frozen+gate-recomputed). R08 complete normal flow DONE; R08-MEDIA-01 MP3 failure preserved
- video-use R09 限定离线修复与生产链验收完成：统一结果模型/退出语义、rollout 留存与完整性、技术/评分/清理共享截止、当前执行域 130s 持久启动探针已验证；R09 真实运行仍需新配置/新冻结身份与批准，未启动。
- video-use R09 四遗漏限定离线修复与验收完成：技术汇总严格必需项、技术/评分共享单调绝对截止、有界保存协议贯通 CLI/run-record/报告、采样 sink/线程/边界进入测量质量；原生 trace 与启动器及 130s 证明保持有效；R09 真实运行仍需新配置/新冻结身份与批准，未启动。
- video-use R09 三问题收口完成：Thread.join 误用改真实 is_alive()、正常路径落盘真实证据并总是读回、测试重复 tearDown 改 addCleanup 全恢复；历史 7 报告 PILOT-04/02 五项 VERIFIED、PILOT-01 两项 UNKNOWN；启动器与 130s 证明保持；R09 真实运行仍需新配置/新冻结身份与批准，未启动。
- R01–R09完整流程重跑已完成；R09归档收尾独立绑定65项（含5个control与3个资源报告），62个既有文件未变、raw/副本24/24一致；官方评分完整但reward=0，非语义通过；无补跑、重评或新执行授权。
- 全仓清理仅完成只读清单：202,529文件/链接、约23.47GiB；43个缓存候选约1.68MiB、56个测试式目录待核查、18个raw副本约1.45GiB保留；用户明确暂不删除，零删除/移动，正式与失败trace及回放材料不动。
- 2026-11-02文档检查点：九组流程现状集中到video_status_overview；清理仍不删除，大文件留本机并忽略。本次只发布文档、索引与小型状态清单，不含未提交生产代码或既有历史删除，远程不等于执行环境/raw完整备份。
<!-- PROJECT_STATE:END -->

8 组统一描述性分析（`VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01`）已完成并完成 6 项已确认问题离线修订：
内存字段、attempt wall、ViMax `video_download`、硬编码/阶段耗时、因果归因、netns 有效增量。
修订入口 `reports/analysis/VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01/revision-CORRECTION-01/`
（correction-notes.md、stage-timing.csv、修正后总表/覆盖/用量媒体/局限、manifest 递归回读）。
4 类残留已最终收尾（时间口径分列、网络身份分组、工具区间可追溯、可复现 CLI 与覆盖保护），
最终交付 `reports/analysis/VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01/revision-FINAL-WIRING-01/`
（由 `scripts/video_eight_final_aggregate.py` 一条命令生成，manifest 递归回读）。
3 处残留已收尾（非工具事件过滤、网络 gap 真实接线、ViMax Agent 时长独立），最新交付
`reports/analysis/VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01/revision-THREE-POINT-CLOSEOUT-01/`
（CLI `--netns-gap-s`；92 项测试通过；manifest 递归回读 0 错）。

## 当前入口

| 内容 | 入口 |
| --- | --- |
| 项目目标、必采指标和排除项 | [current_scope](current_scope.md) |
| 已有证据、实现能力和缺口 | [project_status](project_status.md) |
| 当前工作、下一建议和授权边界 | [current_task](current_task.md) |
| 四仓视频最新概览：九组重跑已完成、回放边界、清理暂缓 | [视频现状总览](video_status_overview.md) |
| 四仓16组合／9输入、9组完整流程重跑记录（含分阶段与E03补采） | [完整流程重跑清单](video_full_flow_rerun_plan.md)、[扩展计划](video_task_expansion_plan.md)、[成果索引](video_results.md) |
| 采样字段与统计语义 | [trace_contract](trace_contract.md#11-当前目标的连续采样与图表要求2026-10-16) |
| 环境、身份和状态维护 | [reproducibility](reproducibility.md) |
| 并发工作与状态保护 | [自动快照、版本校验与独立worktree](project_state_protection.md) |
| 数据与原始证据保护 | [data_management](data_management.md) |
| 两个视频剪辑仓库的故障、修法与开跑检查 | [视频剪辑排障备忘](video_editing_troubleshooting.md) |
| ViMax生成仓库的故障、固定成功入口与复现清单 | [ViMax排障与快速复现备忘](vimax_troubleshooting.md) |
| VideoWeaver适配、解释器/SSE修复、连续闭环与复现清单 | [VideoWeaver排障与快速复现备忘](videoweaver_troubleshooting.md) |
| ViMax原生入口、API依赖、任务镜像与验收方案 | [ViMax执行准备分析](vimax_execution_preparation.md) |
| VideoWeaver固定环境、生产入口与新任务检查清单 | [VideoWeaver执行准备分析](videoweaver_execution_preparation.md) |

## 成果入口

| 内容 | 报告 |
| --- | --- |
| 公开操作构成/工具接口 | [操作v3](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md) |
| 公开数据集收尾 | [最新分析与保存核查](../reports/analysis/PUBLIC-DATASET-CLOSEOUT-20261023/summary.md)，各数据集限定范围完成；HTML及旧综合报告保留历史时点 |
| SWE-bench补充分析 | [逐任务评价补全](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/summary.md)、[剩余来源问题](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/remaining_source_gaps.csv)；新增20,098份评价/配套文件，KGCompass身份更正；[原下载/覆盖复核](../reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1/findings.md)及90条选择保留 |
| SWE-rebench复核 | [调用协议与行为v3](../reports/analysis/SWE-REBENCH-behavior-v3/findings.md)、[逐participant协议](../reports/analysis/SWE-REBENCH-behavior-v3/participant_protocol_details.csv)；598,148调用/616,980结果差额按harness错误与提交请求解释，Junie步骤摘要另列 |
| 具体软件与程序库 | [软件工具集v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md) |
| 三类本地最新分析 | [合并复核v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)，9个固定任务各3次，旧错路由样本单列排除 |
| 本地Coding | [特征化v3](../reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md) |
| 本地Office | [REPEAT-02](../reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md) |
| 本地Assistant | [REPEAT-01](../reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md) |
| 本地历史测量字段与新采集接线 | [覆盖盘点v3](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)，后续新测量见三类合并v3 |
| OSWorld | [命令解析与行为v4](../reports/analysis/OSWORLD-task-behavior-v4/findings.md)、[未知项审查](../reports/analysis/OSWORLD-task-behavior-v4/remaining_unknown_review.md)；[任务与原生层v3](../reports/analysis/OSWORLD-task-behavior-v3/summary.md) |
| H-EPM / ToolSandbox | [工具身份与终止复核v3](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/summary.md)、[26次身份补全](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/recovered_tool_identities.csv)；[原行为v2](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v2/summary.md)保留 |
| AgentX/Applied | [AgentX Full与256k对照](../reports/analysis/AGENTX-FULL-MACRO-v1/summary.md)；[既有256k/Applied宏观分析](../reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md) |
| AgentX深入分析第1步 | [发现与10页PPT](../reports/analysis/AGENTX-DEEP-ANALYSIS-v1/findings.md)、[逐页讲解](../reports/analysis/AGENTX-DEEP-ANALYSIS-v1/presentation_notes.md)；10张4K PNG/SVG、CSV，尚未运行本地回放 |
| AgentX DeepSeek客户端测量收尾 | [五类会话各三次](../reports/analysis/AGENTX-DEEPSEEK-FIVE-REPEATS-v1/summary.md)：Full 393会话/98,827请求；所选5会话各3次、117个唯一源请求、351次正式执行。仅测客户端；未执行原始业务工具，原始长输出未完整复现。|
| AgentX原始证据备份 | [同机独立备份索引与恢复说明](agentx_evidence_backup_20261023.md)；归档本体留在仓库及工作树之外 |
| AgentX main 运行入口 | [运行/输入/环境/历史路径说明](agentx_main_runtime_notes_20261024.md)、[工作树迁移索引](agentx_worktree_migration_index_20261024.json)；旧工作树已收拢入 main |
| 视频剪辑与资源 | [四仓16组合](video_results.md)、[机器索引](video_results_index.json)、[运行版本](video_runtime_profiles.md)、[9组完整流程重跑计划](video_full_flow_rerun_plan.md)；原8组全部保留，加入video-use E03 trace补采；本轮不执行 |
| 后续可选工具覆盖 | [暂缓待办](current_task.md#video-use-optional-coverage-backlog)，不构成新运行批准 |
| 离线HTML | [v5](../reports/html/PROJECT-RESULTS-v5/index.html)，最新成果最后统一更新 |

## 历史只按需查询

旧方法、逐轮任务、交接、批准说明、CPU/G1/IR/适配器设计等77份历史文档已移入本机Git忽略的local_archive。见[历史索引](history_index.md)、[迁移登记](archive_index.json)、[引用审计](archive_reference_audit.json)。2026-10-16编辑前快照位于local_archive/20261016-full-docs/before-edit；最新文档整理快照见[2026-10-21历史入口](history_index.md#docs-refresh-20261021)与[2026-10-24历史入口](history_index.md#docs-cleanup-20261024)。

保留结果的报告原文及manifest不改写。2026-10-29按用户要求直接删除的视频中间资料不另归档，旧中间路径不再保证可访问；见[删除凭单](video_cleanup_20261029_receipt.json)。非视频历史资料不动。不能把当前新目标当作旧批准或旧运行证据；GitHub克隆仍不包含全部本地数据。
