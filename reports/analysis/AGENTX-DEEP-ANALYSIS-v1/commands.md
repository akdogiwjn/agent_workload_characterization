# AgentX 第一步：复算与材料说明

在项目根目录执行。依赖为Python 3.11、numpy、matplotlib、Pillow；中文图使用本机Droid Sans Fallback字体。原始数据沿用既有Full/256k固定版本，输入身份由AGENTX-FULL-MACRO-v1/manifest.json绑定。这里所有命令均为离线读取、分析、绘图与校验，不调用模型或执行Agent。

正式目录不覆盖。以下使用一个尚不存在的新目录复算；若目录已存在，应改用另一个新名称。

```bash
PYTHONPATH=. python3 -B -m unittest tests.test_agentx_deep_analysis tests.test_agentx_deep_locality -v
PYTHONPATH=. python3 -B -m scripts.agentx_deep_analysis --output-dir reports/analysis/AGENTX-DEEP-ANALYSIS-v1-reproduced
PYTHONPATH=. python3 -B -m scripts.agentx_deep_verify reports/analysis/AGENTX-DEEP-ANALYSIS-v1-reproduced
PYTHONPATH=. python3 -B -m scripts.agentx_deep_locality reports/analysis/AGENTX-DEEP-ANALYSIS-v1-reproduced
PYTHONPATH=. python3 -B -m scripts.agentx_deep_verify --final reports/analysis/AGENTX-DEEP-ANALYSIS-v1-reproduced
```

主分析先生成9页基础材料；时间局部性补充生成第10张图和独立的最终10页PPT，原基础结果和manifest不改写。最新入口是`findings.md`与`AgentX深入分析_汇报版_10页.pptx`。

- 图表：16:9白底，PNG为3840×2160；SVG保留文字元素，CSV保存作图数值和分母。
- PPT：标题为可编辑文字，图表为嵌入的高清PNG。需要改曲线/数据时用CSV重新作图，或导入SVG修改；不是PowerPoint原生可编辑数据图表。
- 已检查全部图的预览，以及PPTX的XML、媒体、关系路径和页数；本机没有Office/LibreOffice，未做实际PowerPoint程序打开测试。
- 图8选择的是主代理输入回退候选次数最多的案例，不是筛选损失最多的案例。该案例186条主代理请求全部符合256k规则，因此没有橙色筛除点；蓝线不代表实际上下文压缩操作。
- 源区间间隔、请求重叠、重建输入和缓存简化模型各有不同含义；图注中的限定应随图一并保留。
- 两份逐请求JSONL只留本机；报告、图表、PPT、CSV和manifest可进入Git。Git不包含完整原始数据，单独克隆不能直接复算。

下一步的小样本地mock回放尚未执行。
