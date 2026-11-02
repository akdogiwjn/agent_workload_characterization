# 四视频仓库下一阶段计划

更新：2026-10-31。现有结果统一见 [视频结果索引](video_results.md) 与 [机器登记](video_results_index.json)。本页不批准任何实验。

## 历史保留结果（不等于新完整流程目标均已达标）

| 仓库 | 不同任务覆盖 | 解释 |
| --- | --- | --- |
| video-use | E01、E02、E03、REPURPOSE | 历史采访连续剪辑＋完整评分reward=0；E03当前raw目录为空、trace待定位；Bolt已执行，技术时长门失败保留 |
| OpenStoryline | E01、E02、E03、ASSEMBLY-TASK1 | 采访至render后独立恢复导出/评分；assembly真实Top-K选片→排序→规划→render后独立恢复solution，新策略技术验收通过；原attempt失败保留，恢复成本单列 |
| ViMax | G01、G02、G03、MUSICIANS-AUDIO | G01/G02/G03规划/媒体分阶段；musicians已生成有声媒体并独立恢复65.13s成片，原concat失败保留 |
| VideoWeaver | G01、G02、G03、MUSICIANS-AUDIO | 四组连续生成→merge；musicians 13镜头/65.13s/AAC；G02原FAIL与修订PASS分列 |

共16个历史保留的仓库×任务组合，来自9个输入；不是16次连续成功或同配置重复。当前为7组连续主流程raw可定位、3组正常分阶段、5组含独立恢复、1组raw待定位。恢复不额外计输入；不同代码版本不作受控性能比较。

## 下一步优先级

1. **用户新目标：准备9组完整流程重跑**。原8组全部保留（含ViMax分阶段G01/G02/G03），新增video-use E03；OpenStoryline四组＋ViMax四组＋video-use一组，[统一清单](video_full_flow_rerun_plan.md)列出R01–R09。当前只有计划，尚未授权或启动，不缩减为5/6组。
2. **完整跑通而非事后恢复**：原生执行、正常导出/拼接、技术验收和声明阶段资源覆盖应在同一新执行链完成；采访评分完整但reward=0合法，未集成官方评分的任务不强行新增裁判。
3. **ViMax保留阶段门禁**：新规划→生产验收→实际预算/批准→媒体，新run-family关联各阶段。原G01/G02/G03本来正常分阶段，不改写为失败；不取消批准或假称同一容器连续采样。
4. **恢复历史保留**：OpenStoryline四组和ViMax musicians已有成果仍可作为分阶段记录；现在计划重跑是用户目标改变，不是因reward=0或否定恢复成果。新旧代码/配置及资源窗口分列。
5. **video-use E03列入R09补采**：当前索引raw为空，已查范围未找到完整副本，历史摘要/CSV不代替rollout。用户已决定纳入重跑计划；新执行需完整trace与资源持久化/副本/manifest核验，仍待单独执行批准。
6. **开源扩展已执行**：Bolt、assembly、两仓musicians已有真实结果；musicians有声能力已实测。旧准备文档的未执行/声音待决措辞仅作历史，不能当当前状态。
7. **逐项新授权**：预算与费用先核定，串行、每次至多一个正式attempt、失败停，不无限补跑。CPU-02/Replay不变；本轮仅文档更新，不调用服务或执行重跑。

来源、输入SHA和规格见 [统一任务登记](video_task_expansion_registry_20261025.json)。E02约59.94fps，E01为25fps，不能沿用旧帧率断言。G02=10主体/50s，G03=9主体/45s，不默认8镜头。

## 执行前固定要求

- 使用现行生产入口，新run/config/identity/approval/output；不复用旧批准或覆盖目录。
- OpenStoryline实际Mounts＋容器内SHA/规格通过后才放行Agent；input_dir必传。
- 生成供应商为百炼远端；本地仅Agent/工具/下载/拼接。
- ViMax首帧i2v、variation small；新规划超能力或超预算停止，不删镜头绕过。
- 请求尝试、受理任务、轮询、下载、文件复制分开。正常下载最低预期与预算上限分开。
- 采样目标与实测间隔分开，目录missing/timeout/partial不冒充0。
- 原始失败/评分与独立恢复或修订结论分列；reward=0不自动重跑。
- 无明确新授权不调用API。本次清理不是执行批准。

## 分析与文档入口

```bash
python3 -B scripts/video_analysis_chain.py --run <实际run目录> --repo <video-use|openstoryline|vimax|videoweaver> --out <新目录>
```

[分析口径](video_analysis_guidelines.md) · [剪辑排障](video_editing_troubleshooting.md) · [ViMax](vimax_troubleshooting.md) · [VideoWeaver](videoweaver_troubleshooting.md)

## 中间数据处置

用户于2026-10-29明确要求直接删除无用中间数据，不再归档。现行结果和必要依赖保留；删除文件的轻量回执见 [清理回执](video_cleanup_20261029_receipt.json)。旧轮次不再堆在本页，也不再引用已删失败报告作为开跑前置。状态、代码、fixture按实际保留关系处理；其他项目不在清理范围。
