# 视频任务登记（注册于2026-10-25，状态更新2026-10-30）

输入来源、固定commit、instruction/素材/剧本SHA保存在[机器登记表](video_task_expansion_registry_20261025.json)，未因本次整理更换素材或修改任务要求。

| 输入 | 内容 | 当前状态 |
| --- | --- | --- |
| E01 | 采访口吃剪辑，37秒/25fps | video-use完整评分；OpenStoryline真实render后独立恢复评分，均reward=0 |
| E02 | 采访两处填充词剪辑，约30秒/60000÷1001fps | video-use完整评分；OpenStoryline真实消费E02、render后经FPS容差独立恢复评分，均reward=0 |
| E03 | 约90秒/24000÷1001fps语义内容删除 | video-use连续完成评分；OpenStoryline真实render后独立恢复导出/评分，均reward=0；记录有效不等于官方任务通过 |
| G01 | 摄影师城市故事，8镜头/40秒 | ViMax、VideoWeaver均真实完成生成与成片 |
| G02 | 陶艺工作室故事，10镜头/50秒 | ViMax、VideoWeaver均真实完成生成与成片 |
| G03 | 双人健身故事，9镜头/45秒 | VideoWeaver连续生成拼接；ViMax原规划离线复验后完成媒体阶段，9主体＋8过渡 |

这是6个输入、12组已保留的仓库×任务覆盖结果，四仓各3任务；不是12个独立输入、12次连续成功或同质重复实验。完整路径和验收限制见[成果索引](video_results.md)与[机器索引](video_results_index.json)。机器登记中的offline_readiness、原规划FAIL等为历史时点，当前状态看ready/per_repo_status及成果索引。

OpenStoryline原attempt与恢复状态、VideoWeaver G02原FAIL与修订PASS均分列；ViMax G02逐文件来源和媒体total用量仍有partial。技术规格通过不代替全面语义评分。本地采样不包含百炼远端生成模型资源。

此前失败中间资料按用户要求直接清理，见[清理凭单](video_cleanup_20261029_receipt.json)；不表示随后新产生的失败证据已获删除授权。本轮文档整理不删除任何数据。下一步离线整理CPU工具回放材料；实际Replay、新任务、重复执行与付费调用仍需另行批准。
