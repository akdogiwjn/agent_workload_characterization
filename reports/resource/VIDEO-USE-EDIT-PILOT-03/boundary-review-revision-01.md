# PILOT-03 离线修订 01

本修订对应 [边界诊断](../../analysis/VIDEO-USE-EDIT-PILOT-03-boundary-review-v1/summary.md)，不覆盖原始摘要、raw、评分、APPROVAL 或冻结身份。按 raw 的 monotonic 起止纳秒复算，attempt wall 为 365.166784699 秒（此前状态字段中的 365.067 秒不准确）；采样窗口仍为 340.583442641 秒，两者不是同一指标。报告函数递归已在后续源码修复：包装器使用替换前保存的底层 writer，状态另行记录；修改不属于 PILOT-03 执行身份。

Agent 37 次工具调用/返回中有 0 个协议错误，但一条 timeline 截图命令因参数形式错误以 RC 2 退出，随后改用位置参数成功并查看了图像。边界选择来自 Agent 自己的词级转写和整段短语删除；cuts.json、EDL、render 使用边界一致。范围评分未通过，但评分未提供偏差方向/大小。该离线诊断不使用 oracle/golden，不推断正确时间。