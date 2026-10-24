# 视频剪辑仓库故障与修复备忘

更新：2026-10-24。范围为本项目已复现的 **video-use** 与 **FireRed-OpenStoryline**，不是上游全部版本的通用缺陷清单。本页用于排障，不构成执行批准。

视频生成仓库 ViMax 的对应记录已独立整理为[ViMax排障与快速复现备忘](vimax_troubleshooting.md)（2026-10-24，含PILOT-04真实闭环、固定入口及CPU线程/冷启动修复）。剪辑仓库的历史修复和评分口径仍以下文为准。

VideoWeaver的对应记录见[VideoWeaver排障与快速复现备忘](videoweaver_troubleshooting.md)（2026-10-24，含login-shell解释器、技能安装说明、SSE用量和分阶段成片验证）。

## 先看结论

两个仓库都已实际生成剪辑视频并进行独立评分。video-use 的 PILOT-03/04、OpenStoryline 的 PILOT-02 均有完整评分记录，reward=0 是剪切范围未达标，不能写成“没有完成剪辑”。video-use PILOT-02 的评分曾缺依赖，应单独标为评分不完整。

反复准备失败主要来自项目非交互入口、镜像环境、MCP数据传递和验收覆盖不一致，不能统称“原仓有很多bug”。当前收尾修复经离线测试通过，不代表修复后的每个异常路径都已再次实测。

| 仓库 | 实际Agent与模型链 | 本地执行与监测范围 |
| --- | --- | --- |
| video-use | 外层Codex CLI；百炼Responses；ElevenLabs Scribe转写 | Python helpers、FFmpeg/ffprobe及其子进程在任务容器内；独立宿主verifier另列 |
| OpenStoryline | 仓库原生LangChain Agent＋MCP；百炼Chat Completions；本地FunASR英文适配 | Agent、MCP、ASR、FFmpeg及其子进程在任务容器内；独立宿主verifier另列 |

同一个模型名、素材或基础镜像，不代表两仓的协议、入口与内部数据契约相同。不同Agent/ASR/适配配置不能当同质重复，也不能直接比较为仓库优劣。

## video-use：出现过什么，怎么处理

| 编号 | 现象与根因 | 修复办法、验证状态及以后检查点 |
| --- | --- | --- |
| V1 | PILOT-01在转写前报缺少requests。依赖实际已在`/opt/video-use-venv`，但`bash -lc`读取profile后重置PATH，裸`python3`落到系统解释器。 | 镜像修复普通/login shell的venv优先路径，后续真实运行转写成功。以后必须按实际工具shell检查`sys.executable`、`sys.prefix`和模块来源，不能仅凭构建时绝对venv路径导入成功。无需往系统Python重装同套包。 |
| V2 | 准备时保存的monotonic值被误用于执行预算，会把准备耗时算进新任务。 | 正式入口调用共享runner前获取本次实时起点；不得从冻结文件或旧run-start读取新运行起点。修复后已有正式执行；每个新授权的计时范围仍需明确。 |
| V3 | PILOT-02 judge缺少skimage，捕获异常后仍以RC0输出reward0；音频检查未执行。 | 使用专用verifier venv和显式解释器，分列评分完整性、得分及返回码。PILOT-03/04完整评分已验证；不能把PILOT-02旧reward当完整评分，也不能因RC0宣称所有检查通过。 |
| V4 | 默认渲染把854×480输入变成1920×1080；默认调色、淡化等也不一定符合只删除片段的任务。 | 项目渲染适配保持源尺寸/帧率，按任务关闭不需要的效果。v6后续真实输出规格通过；这是显式项目适配，不称完全未修改原版。 |
| V5 | timeline参数错误、近结尾截图越界造成命令非零退出；“0协议错误”曾掩盖命令失败。 | 使用实际helper帮助对应的参数，截图限制在有效取帧范围。保留失败命令与恢复记录；调用/返回配对、协议错误、命令退出码要分开统计。生成图片不等于Agent实际通过view_image查看。 |
| V6 | PILOT-03已完成剪辑与归档，报告包装器却递归调用自身，导致入口最终RC1。 | 包装器调用替换前保存的底层writer，报告生成状态单独记录。已离线回归并从封存raw补报，未重跑历史任务；报告错误不能倒推剪辑没有执行。 |
| V7 | PILOT-03/04格式、时长、SSIM和音频检查通过，但剪切范围未过。 | 属于任务质量观察，不是通用渲染失败；保存EDL、cuts和实际render输入的一致性证据。词时间是候选，波形/RMS/静帧不证明听懂音频。保持原生流程，不为追分擅自引入新音频模型或用golden改答案。 |

相关证据：[PILOT-02验收修订](../reports/resource/VIDEO-USE-EDIT-PILOT-02/acceptance-revision-01.md)、[解释器离线验证](../env/video/video-use/VIDEO-USE-EDIT-PILOT-02/offline-validation.json)、[PILOT-03报告/边界修订](../reports/resource/VIDEO-USE-EDIT-PILOT-03/boundary-review-revision-01.md)、[PILOT-04验收](../reports/resource/VIDEO-USE-EDIT-PILOT-04/acceptance-revision-01.md)。

## OpenStoryline：出现过什么，怎么处理

| 编号 | 现象与根因 | 修复办法、验证状态及以后检查点 |
| --- | --- | --- |
| O1 | 镜像准备下载停滞，最小依赖子集还漏了emoji/tomli；仅有静态检查不等于环境能运行。 | 本轮构建使用可用包源和官方CPU PyTorch来源，补齐实际导入链，保存freeze；后续真实ASR和Agent已运行。不要照搬本次下载故障为所有ARM64/包源的通用结论，也不为换任务重复安装。 |
| O2 | 英文paraformer-en最初输出“像英语的乱码”，曾被误判为模型不可用；诊断发现当前FunASR 1.3.1解码词表ID空间不匹配，时间戳输出链也不满足节点契约。 | 保留旧诊断并修订：项目适配使用tokens.json解码、真实CIF输出推导词时间、处理VAD偏移及ct-punc句子组装。修复过词/时间数量错位；后续真实ASR已通过。只对已核验模型/版本适用，不能均分时间、伪造timestamp或直接推断新版是否已修。 |
| O3 | wrapper出现artifact_id缺失、cfg闭包和Path/字符串拼接错误；内部媒体/前序参数不在公开schema中。 | 对照原生CLI恢复拦截器与上下文；隔离副本wrapper承担必要schema边界适配。不要仅靠随意生成ID消除KeyError，必须核对生成、返回、持久化及下游读取。 |
| O4 | load_media明明读到视频，split_shots仍为空，history查不到artifact。生产入口漏传原生结果保存拦截器，而旧测试手动save_result掩盖问题；history根目录也曾不统一。 | 以原生CLI启动契约为基线，统一session/store/history和公开工具名到node_id的映射，成功结果自动保存一次。缺前序必须明确报错，不能变成“空clips但成功”。完整禁网冷启动及后续真实运行已验证数据链。 |
| O5 | 宿主有模型权重，禁网容器却找不到configuration.json。 | 测试与正式入口共用只读缓存挂载；按容器内实际本地路径检查16个必需文件，再加载模型，禁网时不自动下载。缓存挂载修复后真实ASR已通过，不需要重建全部依赖。 |
| O6 | fake链路能render，输出却没有声音；测试还把320×240强制变成320×180。 | 原生include_video_audio默认False。显式保留原声和音量，按源尺寸/比例设置画布；禁网重渲染和正式输出均已验证。先查参数，不把所有规格问题归为编码器缺陷。 |
| O7 | 真实Agent只展示计划就结束，入口却把单次回复当completed。 | 原生提示要求计划确认。保留提示，增加awaiting_confirmation等状态；仅在用户明确预授权范围内确认，沿同一session、完整历史、账本和deadline继续。不得自动批准范围外服务或效果；后续真实流程已进入执行。 |
| O8 | “600秒超时”被误读成模型卡了600秒。实际上新会话继承旧起点，启动时已耗370.20秒，仅剩229.80秒；6秒素材有6句，原生粗剪逐句串行请求。 | 新授权使用新起点和独立账本，旧成本另列；真正共同预算则保留共同截止，不能偷偷重置。按句数、Agent轮次及已测请求耗时估算预算。分清单请求输出上限、累计已返回usage软阈值和逻辑请求上限。后续新预算短任务及正式运行已通过该阶段。 |
| O9 | LangChain继承回调曾把MCP sampling重复记成Agent请求；fake交换也容易与真实HTTP次数混淆。 | 统一请求账本，在节点sampling的手动计数范围抑制重复回调；按角色/节点配对。正式记录41个逻辑请求不是41次已证HTTP请求；真实HTTP次数仍unknown，fake传输只作为测试证据。 |
| O10 | 容器/workspace/output被误当宿主路径；随机render文件名与固定提交名不一致；恢复脚本还混用meta.json的created_at与artifact文件的create_time。 | 显式做挂载路径映射，根据当前session状态、成功工具事件和timeline来源选择render，导出并核对哈希。不要只凭mtime或目录最新文件猜。最终来源已在收尾修订核实；两个候选同哈希时，哈希不能单独区分副本来源。 |
| O11 | 正式首轮render报timeline无视频轨；Agent查询history、重规划后成功渲染。 | 保留错误及同会话恢复，不称零工具错误；不能把最初一次失败当整次任务未生成视频。正式事件已记录恢复，但这不保证所有未来任务的规划都会正确。 |
| O12 | 正式剪辑完成后，宿主改写nobody:0644的容器agent-result导致PermissionError；总wall、execute返回码和目录初值没及时落盘。 | 宿主不覆盖容器原始状态，写独立宿主记录；启动、目录前测和execute返回后及时持久化。历史缺值保持unknown，不能把executing原件改成completed。当前生产修复为离线验证，尚未重跑正式任务。 |
| O13 | 收尾错误仍可能CLI返回0；total_wall在归档前计算，漏掉归档耗时。 | 当前入口将关键清理/报告/manifest错误映射为非零（当前为7），reward0本身不改作infra错误。归档后耗时写host-finalization.json；已哈希run-report保留pre_archive_wall和total_wall_source，避免回写破坏manifest。12项离线测试通过，含归档延迟和失败注入；未实测新正式运行。 |
| O14 | 正式提交视频可用、评分完整，但reward0。 | 是选段范围未达标，不是“未剪辑”。8个提交区间与1个官方目标的匹配口径分开报告。不得把评分边界反馈给下一轮Agent；无新授权不补跑。 |

核心证据：[ASR诊断](../env/video/openstoryline/OPENSTORYLINE-ENV-01/evidence/asr-diag2/diagnosis.json)、[原生CLI契约对照](../env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01/cli-contract-comparison.md)、[真实短任务门禁](../env/video/openstoryline/edit-pilot-02/preparation/native-agent-gate.json)、[正式原报告](../reports/resource/OPENSTORYLINE-EDIT-PILOT-02/summary.md)、[收尾修订](../reports/resource/OPENSTORYLINE-EDIT-PILOT-02/revisions/closeout-review-01/summary.md)。

当前修复实现：[宿主入口](../env/video/openstoryline/edit-pilot-02/runtime/openstoryline_pilot_entry.py)、[收尾定向测试](../tests/test_openstoryline_closeout_repair.py)。2026-10-23追加修复前的源码/测试快照保存在[快照目录](../env/video/openstoryline/edit-pilot-02/recovery/closeout-final-fix-20261023/)。当前源码不是旧运行身份；旧修订manifest中的源码哈希按当时版本保留。

## 为什么以前“测试通过”仍然实跑失败

1. **入口不同**：直接调用节点或MCP客户端，不等于生产LangChain入口。
2. **测试代做**：手动存artifact、注入前序payload、搬运输出，会掩盖生产缺口。
3. **只测skip/续跑**：能注册、空结果成功、复用旧ASR或分次续跑，都不等于新session冷启动全链通过。
4. **fake响应太快**：fake证明协议和数据链，不证明真实逐句请求的耗时、预算与模型决策质量。
5. **只看返回码**：单轮对话结束不等于任务结束；judge RC0不等于评分完整；协议无错误不等于命令无错误。

正确回归应使用同一生产入口，只模拟远端模型边界；MCP、自动存储、节点、导出、预算和收尾真实经过。fake结果、真实短任务和正式benchmark样本分别登记。

## 后续开跑前的短清单

- 复用既有镜像、入口、适配和缓存；只换素材/说明时不要重新拼执行链。完整ID、输入哈希和实际解释器现场核对。
- 确认模型协议与实际客户端匹配：video-use的Codex使用已验证Responses路径，OpenStoryline使用Chat Completions；请求被接受不等于工具回传、图像理解或完整链路均通过。
- 输入文件在容器内可读，模型缓存只读可用；预检媒体非空，路径映射和目录写入责任明确。
- 新session、独立日志、账本及授权预算；本次起点及时落盘，确认后继续不重置deadline。禁止覆盖server日志或历史状态。
- 计划确认遵循范围内预授权；异常只做有边界的恢复，不无限重试。正式代码修改需新身份，不能修改后冒称仍是旧冻结配置。
- 渲染显式保原声、源尺寸/帧率；最终视频、cuts和实际timeline一致；评分环境独立且依赖齐全。
- 分别记录目标/实际采样周期、采样窗/Agent窗/总wall；bytes、GB、GiB不混用。容器、宿主verifier及共享netns口径分开。
- 当前收尾的最终wall读host-finalization.json；run-report中的pre_archive_wall不是总wall，manifest明确排除了可变控制记录。不把未哈希控制记录声称为已由manifest覆盖。
- 收尾必须回收进程、停止采样、核验删除容器并保留镜像。任务失败、预算终止、infra错误、报告错误和unknown各自保留。
- 需要新工具类别、外部服务或依赖升级时再补对应验证；不为reward=1擅自扩大预算或重跑同题。

## 维护规则

历史raw、评分、批准、冻结身份与原报告不改写；新发现追加修订或更新本备忘。不要把上面的历史现象当成当前全部仍未修复，也不要把离线回归写成真实运行已验证。共享仓库另有对话并行修改时，只更新本任务涉及的文件和当前证据登记，不回退他人的改动。
