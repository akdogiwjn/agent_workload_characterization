# ViMax generation pilot 03 preflight

通过固定 v7 镜像的禁网生产入口检查。固定规划的 camera tree 有8台 camera、7条父子边；原生 pipeline 因此需要8个主体视频和7个过渡视频。主体片段按 storyboard 顺序拼接，过渡片段用于子 camera 的首帧连续性，不进入最终 concat。图片配置沿用默认每个首帧2个候选，共16个首帧候选与3张人物肖像；图片发送由独立40次发送门禁保护。

原生输出时长依配置为8×5秒，预期40秒，最终容差±1秒；每段5秒容差±0.25秒。北京 list-price 媒体成本估计最多约15.81元（含最高57张输入参考图的估算，不含 qwen3.7-plus tokens）；实际账单未知，20元只是参考。镜像、规划、路由、权限和预算详见 `preflight-report.json`。
