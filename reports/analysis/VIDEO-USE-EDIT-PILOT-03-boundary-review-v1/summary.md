# VIDEO-USE-EDIT-PILOT-03 边界诊断与报告修订

## 范围

这是一次离线复核，分析 `20261021T1310Z-video-use-edit-03`。没有调用 API、启动 Agent、verifier 或 oracle；边界判断只使用 Agent 侧转写、任务说明、技能说明、原生 rollout、EDL、cuts.json、截图和实际 render helper。评分侧只采用“cut range 检查未通过”这一汇总结论；未查看 golden、oracle、目标剪切时间或私有评分材料。报告递归发生在 raw manifest 写入后，本修订不改 raw、原始评分、批准、冻结身份或历史镜像。

## 报告递归修复

冻结执行入口中的包装器被赋值给 `runner.write_resource_report` 后，又通过该同名属性调用报告函数，形成递归。修改前的脚本原字节快照已保存，SHA-256 与 PILOT-03 冻结输入一致。当前后执行代码在替换属性前保存 `_BASE_RESOURCE_REPORT_WRITER`，由包装器调用底层 writer 一次，再生成 PILOT-03 摘要；报告状态单独记录 Agent、verifier、清理和 raw 文件存在性。报告写入失败会返回带错误类型/消息的状态，不改写 raw。

实际使用归档 `run-record.json` 的临时目录报告调用成功，生成 summary 和曲线；定向测试覆盖正常单次调用、底层异常记录、raw 字节保持不变。历史入口 RC 1 是报告阶段异常，不代表 Agent、评分或容器清理失败。

## 时间与行为口径

- 从 raw 起止 monotonic 纳秒相减，attempt wall 为 **365.166784699s**。采样覆盖窗为 **340.583442641s**，两者分列。
- 566 个采样点、565 个 CPU/I/O 有效相邻区间；目标为 0.5s，实测间隔中位 **0.601359236s**、最大 **0.801727690s**。这次采样窗不覆盖整个 attempt。
- rollout 是 **37 次工具调用 / 37 次返回 / 0 个协议错误**；另有 **1 次命令非零退出**（`timeline_view.py`，RC 2）。它不等于“所有命令成功”。Agent 查阅 help 后改用位置参数重试，RC 0，并实际通过 `view_image` 打开了生成的 timeline PNG。截图命令失败来自调用参数形式，不支持“通用截图工具缺陷”的结论。
- 保存了 **30 条 usage 记录 / 30 个不同 response_id**。逐响应汇总 input **1,012,494**、cached input **798,080**、output **14,555**、reasoning output **11,167**、total **1,027,049**。cached input 是 input 的组成部分，不另加；response_id 不是 HTTP 传输次数，后者 unknown。
- Agent RC 0、未超时；独立 verifier 完整执行，原始 reward 仍为 0，剪切范围未通过，其余已执行检查通过。容器资源不包含独立宿主 verifier。

## 剪切边界证据

### 转写字段

Scribe JSON 有 **293** 个逐词/spacing 条目，含 `start`、`end`、`type`、`speaker_id` 和 `logprob`；标点写在词文本中。没有专门的犹豫/事件标签。边界附近的转写把 “Yeah,” 标为 25.160–25.280s，将后续 `in / the / f- / in, / in / the...` 连续列出；“Right” 从 27.240s 开始，其前 spacing 为 0.560s。这些是 ASR 给出的时间候选，不是真值。

### Agent 如何选择

- rollout event 30 首次把候选定位在约 25–27s；event 175 明确说从 “Yeah,” 起点剪到 “Right” 起点，删除整段重启短语。
- `cuts.json` 为 25160–27240ms；EDL 保留区间到 25.160s，并从 27.240s 接回。转换 `ms / 1000` 后精确相同。
- event 43 的 timeline 命令误用了不支持的命名参数，exit 2；Agent 在 event 50 看 help，event 57 用位置参数成功、event 60 保存图，event 64 实际查看图像。随后查看了源帧与输出前后截图。event 81 表示要检查波形，event 82 的 FFmpeg `astats` 是全片音量扫描；没有证据表明它做了局部音素边界或语音语义分析。
- 有截图生成，也有实际 `view_image` 查看。它们证明 Agent 检查过图像/波形外观，不能证明它听辨了语音含义。当前模型的文本/图片能力记录不构成音频输入能力验证。

### 渲染与自检

event 185 调用生产 `render.py`，携带 `--preserve-source-spec --no-grade --no-audio-fades --no-loudnorm --no-subtitles`。实际 EDL 与 cuts 一致，两端都落在 25fps 整帧边界；没有发现毫秒/秒、绝对/相对时间或取整造成边界变化。输出规格自检有效，但截图只能支持视觉连续性的判断，不能验证听觉/语义连续性。工具没有改变 Agent 写入的边界。

## 结论与下一步

**直接证据支持**：Agent 依据词级转写，选择删除整个重启词组并把两端放在 “Yeah,” 与 “Right” 的词起点；它查看过 timeline 波形图和真实画面，但没有可确认的音频语义判断。EDL、cuts 和 render 一致。非零截图命令是参数选择错误，随后恢复成功。

**合理但未证实**：词级时间有声学偏差；整段短语删除的语义策略不合适；官方标注容差较严。现有评分摘要不说明哪端或偏差量，不能把任何一个解释成唯一根因。

**建议**：先改选段策略，不增加预算。把词级时间只当候选；对短应答、停顿和重启分别判断哪些内容必须保留，并用局部音频线索复核边界。现有 Scribe、`timeline_view` 波形/画面、FFmpeg 和修复后的 render helper 可复用。若需要判断语音语义，而转写不足以支持决策，应先单独验证并授权可听音频的能力；强制对齐最多改善时间戳，不能决定内容是否应删。此后若要验证策略效果，需要新一轮单次正式执行的独立授权与批准，不在本次离线诊断范围内。

## 可追溯证据

详细字段、事件索引、hash 清单见同目录 `summary.json` 与 `manifest.json`。原始 run、rollout、transcript、EDL、cuts 和截图均保留在 PILOT-03 raw；此修订不含正确边界或评分反馈。
