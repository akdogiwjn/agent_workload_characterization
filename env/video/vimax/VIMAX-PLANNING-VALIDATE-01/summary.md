# ViMax 有限真实规划验证：结果

**结果：规划契约未通过；媒体生成未开始。** 唯一会话 `20261023-170240-planning-validation-01` 保持 `script` 模式，但模型保存的 script 与冻结输入有两处标点差异：两个弯引号变为直引号。Agent 两次以相同参数调用原生 `vimax_narrative_planning`，都在 `plan_script` 阶段因 `RetryError` 包裹 `OutputParserException` 失败；AgentLoop 随后按相同失败早停，没有新会话或补跑。

本次生成的 `characters.json` 存在，禁网核验通过 `CharacterInScene` schema；`script.txt` 存在。`storyboard.json`、8份 shot description 和 `camera_tree.json` 均缺失，所以八镜头顺序、相机引用和后续生成能力无法验收。输出中没有图片或视频。实际 Agent return code 与容器 return code 均为0；这只表示进程完成，不代表规划成功。

模型账本记录8条逻辑请求：外层3条、LangChain内部5条；项目attempt记录3条。全部请求ID均闭合，累计已返回 `total_tokens` 为 **59,294 / 250,000**，没有触及门禁。四条内部结构化响应的 `finish_reason=length`，每条 `completion_tokens=4096`；reasoning usage 分别为3252、4096、4096、4096。保存文本长度为3436、0、0、0字符，均不能解析为JSON；保存副本未被长度截断。它们与顶层规划错误同属规划阶段，但持久化的解析错误没有request ID，故不把特定异常猜配给某一响应。外层响应模型为 `qwen3.7-plus`；内部响应模型名未保存。实际HTTP交换次数和费用 unknown。

Attempt wall **389.45秒**，未触及1800秒工作deadline。容器cgroup观测窗口约388.59秒：777个目标0.5秒采样点，CPU累计5.928 core-seconds、有效区间平均0.0153 core；memory.current结束值121,020,416 bytes，采样峰值125,292,544 bytes，内核peak 126,787,584 bytes；cgroup I/O读0、写139,264 bytes。容器netns逐接口采样196点（eth0与lo），实测中位间隔1.997秒、无缺口；流量不是API专属。容器删除已核验，镜像保留，清理错误为0。

预算/工具策略在请求前已生效：40次共享逻辑请求尝试上限、8192外层和4096内部单请求输出上限、返回usage累计250k软门禁、SDK retries=0；render、图片/视频生成、通用shell和手工JSON写入工具没有注册。没有调用媒体生成或评分。

这次观察支持的主要结论是：在当前登记路由和原生内部LangChain规划节点中，规划结构输出耗尽4096 completion-token上限并返回 `finish_reason=length`；八镜头规划没有形成。它不证明所有模型响应都会如此，也不授权再次验证。下一步若继续，需要单独授权新的真实会话/attempt，并先离线修复或明确接受 script 标点规范化及内部请求响应/解析错误关联缺口。

机器证据：[run report](execution-01/run-report.json)、[run record](execution-01/run-record.json)、[离线评估](offline-assessment.json)、[原生事件](execution-01/workspace/attempt/agent-events.jsonl)、[模型账本](execution-01/workspace/attempt/model-events.jsonl)、[资源点](execution-01/resource-samples.jsonl)、[netns点](execution-01/netns-samples.jsonl)。
