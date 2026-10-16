# OSWORLD-20260929 离线验收与字段盘点

日期：2026-09-29。本轮只读已有 acquisition 证据，不联网、不执行轨迹。

## 五项独立结论

| 项目 | 结论 | 依据 |
|---|---|---|
| A 文件完整性 | PASS（仅文件层面） | manifest 登记的 14 个文件均存在，bytes/SHA-256 回读一致；三条 JSON 可解析 |
| B 来源/版本绑定 | PARTIAL | Hcompany 完整 revision `ede2a362c99ddba0d03f439c47a0b8fea6abae22` 已登记；三条正文 URL 固定到该 revision，响应头也记录相同 commit。README/index 使用 `main` 地址，虽响应头显示同一 commit，但这不是独立不可变地址。第三方镜像与官方 OSWorld task/version 的精确等价性未证明 |
| C 获取预算 | UNKNOWN | 可确认下界为 24 次 HTTP 操作、已知响应正文 8,603,911 bytes；已保存正文 5,197,002 bytes。发现页响应字节和重定向逐跳数不可从现存记录完整恢复，不能写成“24/30 且未超限”，也不能认定超限 |
| D 选样覆盖 | PARTIAL PASS | 规则已预先写入原 manifest，且可由保存的 index 复现；仅是 Hcompany 镜像中 `OSWorld / Holo4 27B / run=1` 分层的前三个 task ID，不是随机抽样或总体代表 |
| E 下游可用性 | LIMITED | 可开展第三方浏览器动作序列描述；不能开展可靠逐步时间、CPU、内存、I/O、热点或官方版本特征化 |

## 三条记录

| 镜像记录 ID | task 字段 | 模型/run | 步骤/动作 | 可证明关联 |
|---|---|---|---:|---|
| `chrome-1-2c59a0c1` | `chrome_1` | Holo4 27B / 1 | 9 / 9 | Hcompany 内部记录，Chrome 标签；官方 task/version unknown |
| `chrome-10-a6282ce2` | `chrome_10` | Holo4 27B / 1 | 8 / 8 | 同上 |
| `chrome-11-0c8292b4` | `chrome_11` | Holo4 27B / 1 | 10 / 10 | 同上 |

`id` 是镜像记录 ID，不能自动当作官方 task ID 或 episode ID。`run=1` 表示镜像中的发布字段；它不是三条记录共享的同一 episode，也不能据此推出同一完整配置或同一发布批次。三条属于“镜像标注的浏览器/Chrome 轨迹小样”，不能升级为官方 OSWorld 或完整 Computer/Office 类别结论。

## 字段盘点

- 消息数：unknown；保存结构没有 message 数组。`steps` 分别为 9、8、10，是可见步骤记录数，不自动等于模型请求数。
- 动作：可识别动作名称和顺序；参数字段名可见，但本报告不复制参数值。
- 结果关联：动作对象只有 `name`/`args` 等字段，未发现 action/result 关联 ID。前两条没有结构化 `results`，第三条有 3 个字符串结果；完整性 unknown。
- 时间：只有顶层 `duration_s`；没有逐步 timestamp、时钟、单位解释或观测窗口，因此不能拆分动作耗时或时间占比。
- usage：顶层和每步均有 usage 字段，但数据未说明它们是累计还是独立计量；可做字段存在性和发布值盘点，不当成账单。
- verifier：三条都有 `execution_time_s`、`exception`、`details` 字段。可记录镜像报告的结果，但不把它解释为已核验的官方任务完成。
- 资源：CPU、内存、I/O、热点均 missing。
- 完整性：JSON 解析成功且下载文件哈希一致，但没有独立上游文件哈希/期望长度可供比对，不能仅凭可解析声明内容未截断。

## 可分析性

| 可分析 | 不可分析 |
|---|---|
| 镜像记录中的 task/model/run 标签；动作类型与顺序；可见步骤数；发布的总 duration；usage/verifier 字段存在性 | 官方 task/version 精确匹配；逐步时间占比；CPU/内存/I/O/热点；完整工具返回；动作实际效果的独立核验；总体代表性 |

与 Coding 的比较只能停留在字段级描述：GUI action 不等于 shell tool call，step 不等于模型请求，汇总 duration 不等于同口径 wall。

## 唯一下一步

暂不批准 adapter 或新分析。先由评审决定是否接受 Hcompany 第三方镜像作为行为分析来源；若不接受，应另行获得官方 OSWorld 轨迹的合规、可计量访问方式，并重新固定 task/version 关联。原 acquisition manifest、review 和 raw 文件保持不变。详细逐条证据和文件哈希见 `offline_review.json`。
