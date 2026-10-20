# LOCAL-THREE-CLASS-REPEAT-01：限定执行与特征化

计划27槽位；实际启动 1。原批次状态 {'executed': 0, 'failed': 1, 'not_executed': 26}。批wall 208.936s。

Coding两个固定Astropy镜像缺失，无登记本地禁网恢复上下文；全类9槽位未执行。未拉取、未换任务或用旧样本充数。首个Office Excel完成后，新增批次验收错误读取host_agent（实际为host_agent_process），触发KeyError并全批停止。其余Office8与Assistant9未启动，不补跑。
原批次archive_verified=false是该验收异常路径写出的状态，不是已证明raw损坏。独立只读验收重新核对文件集合与哈希、容器删除和镜像保留；不改写原batch-summary/VALIDATION。停止后仅修正验收键并离线回归，执行时源码已保存精确快照，不重冻结、不续跑。

## 逐run四维结果

|链路/round|run_id|请求/自主工具/bootstrap/User工具|测量主项|官方结果|终止|infra/归档|wall s|主scope CPU-s|内存峰值MiB|曲线|
|---|---|---|---|---|---|---|---:|---:|---:|---|
|Office/r0|20261016T182559Z-09-r0-office|12/11/2/0|complete_in_observed_main_windows|{"status": "completed", "rewards": {"reward": 1.0}, "reward": 1.0, "verifier_budget_s": 600.0}|"finish"|independent raw file set and SHA verified; original batch acceptance failed|207.2600|12.0002|64.703|[SVG](figures/20261016T182559Z-09-r0-office.svg)|

## 固定任务内重复（不跨task混合）

|链路|任务|实际n|wall median / IQR s|主scope CPU median / IQR CPU-s|内存median / IQR MiB|图|
|---|---|---:|---|---|---|---|
|Coding|django__django-16485|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-0-points.svg)|
|Coding|astropy__astropy-13236|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-1-points.svg)|
|Coding|astropy__astropy-13398|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-2-points.svg)|
|Office|atomic__excel_001_budget_bucket_totals_seed|1|原始点 [207.26] (n=1；不足3次)|原始点 [12.00025] (n=1；不足3次)|原始点 [64.703125] (n=1；不足3次)|[原始点/median/IQR](figures/task-3-points.svg)；[已有run四面板：n=1](figures/task-3-small-multiples.svg)|
|Office|atomic__ppt_008_bullet_editing_seed|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-4-points.svg)|
|Office|atomic__pdf_004_audit_pages_reorder_seed|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-5-points.svg)|
|Assistant|send_message_with_contact_content_cellular_off|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-6-points.svg)|
|Assistant|add_reminder_content_and_week_delta_and_time|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-7-points.svg)|
|Assistant|modify_contact_with_message_recency_multiple_user_turn|0|not_executed|not_executed|not_executed|[原始点/median/IQR](figures/task-8-points.svg)|

## 范围与限制

- 三次重复不是三个独立任务；分位数采用(n−1)×p线性插值，缺测按指标实际n，不补零。原始点与阶段CPU/wall详见per_run.jsonl及task_statistics.csv。
- CPU为有效相邻区间累计差分/同窗口wall的平均core，不是瞬时值；共享容器/共享worker、宿主RSS分列，不是单工具独占资源。内核peak不是独立阶段peak，内存指标不相加。
- 请求时长不是思考时间；业务工具错误、bootstrap失败、官方评分和infra分列。没有HTTP hook和账单证据，HTTP次数及费用unknown。别名与响应model不保证后端不可变。
- 网络为共享netns逐接口观测，最多展示3个完整窗口有效非lo接口，按rx+tx变化量及名称确定性选择；不是API出口，虚拟接口不得相加。完整接口统计保留在JSON。
- I/O是cgroup block service或/proc原口径；rchar/wchar和read/write_bytes分列，不是完整文件系统流量。目录采用apparent size；扫描活动未从资源中剔除，宿主目录结束扫描早于最终归档，不称最终归档总大小。cache仍unsupported。
- 采样窗不是attempt wall；gap断线，不插值，实际阶段边界见每run SVG。小多图每run保持真实时长和轴标签，不绘制平均轨迹。
- ARM64适配DocOps不声称与官方amd64字节等价；Assistant为模拟业务工具，不映射真实外部品牌。无跨类别因果、排名、Office/Assistant总体结论。
- Coding历史RC7保留。本轮只修wrapper按runner的ok/failed状态契约映射，不更改旧运行或历史身份。
- 仅完成SVG XML/数值/链接核验，未完成浏览器实际渲染；未安装新平台。G2/G3-R不变，CPU-02/Replay暂停。

## 原始行为路径

- 20261016T182559Z-09-r0-office: bootstrap:get_task_metadata → bootstrap:inspect_document → agent:xlsx_read_sheet → agent:xlsx_read_sheet → agent:copy_file → agent:xlsx_set_formula → agent:xlsx_set_formula → agent:xlsx_read_sheet → agent:xlsx_set_formula → agent:xlsx_set_formula → agent:xlsx_set_formula → agent:xlsx_read_sheet → agent:inspect_document。
