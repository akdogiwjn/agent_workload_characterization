# P0-01 最小项目骨架交付

状态：DONE。范围：最小包、CLI、配置与基础测试；不包含 P0-02 Schema 或 P0-03 adapter 框架。服务 RQ1～RQ6 的工程基础，不产生研究结论。

## 输入与复用边界

依据 P0-00-r2 审计、data/catalog/code_components.yaml、Trace 契约，以及旧 benchmark_analysis/pyproject.toml（只读）。

- 延续旧工程 Python >=3.11、setuptools 与 src 布局；使用独立的 agent_workload_characterization 包和 awc 命令，避免与旧 agent_trace_analysis/agent-trace 混淆。
- 当前 CLI 仅帮助/版本，使用标准库 argparse；不为两个选项引入 Typer。
- 测试采用标准库 unittest，当前机器无 pytest，未为骨架安装依赖。不是用“零测试通过”代替验收。
- 旧工程的数据栈为 Polars/PyArrow，后续数据处理优先评估复用；本轮无 DataFrame 功能，不引入 Polars、Pandas、DuckDB 等运行时依赖，也不提前固定其版本。
- 没有复制、导入、修改或运行旧 adapter/sidecar；后续复用须先满足语义和回归测试要求。
- 包内 adapters/analyzers/collectors 等目录按未来任务创建，本轮不铺设空目录或虚假可执行 stub。任务计划中的目录树是职责划分，实际 Python 模块统一位于 src/agent_workload_characterization/ 下。

## 修改文件

- pyproject.toml：构建元数据、独立发行名、Python 版本、console entry point，零运行时依赖。
- src/agent_workload_characterization/{__init__,__main__,cli}.py：包版本、模块入口与只读 CLI。
- tests/test_skeleton.py：10 项带断言测试，使用临时空目录运行子进程，不依赖旧源。
- .gitignore：追加环境、构建缓存、原始/normalized 数据与凭据规则，保留原规则与 catalog/审计证据。
- README.md、methodology.md、docs/development_tasks.md：同步运行方式、实际布局及下一任务状态。

## 实际执行与结果

环境：Python 3.11.6，setuptools 68.0.0。未安装新包，未修改系统环境。

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m agent_workload_characterization --help
PYTHONPATH=src python3 -B -m agent_workload_characterization --version
git diff --check
```

结果：10 tests passed；帮助退出码 0；版本输出 awc 0.1.0；diff 空白检查通过。

测试覆盖包/发行版本一致、entry point 可调用、直接调用 main、python -m 帮助/版本、空参数帮助、未知选项/未实现命令/缩写选项退出码 2、安静且轻量的 import，以及 CLI 不在空工作目录创建文件。

## 限制与下一步

- 未执行 pip 安装、wheel/sdist 构建或安装后的 awc 包装脚本；当前验证源码运行与声明的入口可调用，安装分发验收留待需要时补充。
- 临时目录测试不构成 OS 级全文件系统/网络副作用隔离证明；当前 CLI 本身无采集、文件写入或网络代码。
- 当前测试不验证 trace 数据、ID/指标契约、来源写入保护、旧 adapter 正确性或 CPU 归因；这些属于后续任务。
- P0-01 已满足最小骨架验收；G0 仍未通过。下一候选为 P0-02 最小 Trace IR 与指标契约，本次不执行。
- 未转换/搬迁原始数据、未生成新 sidecar、未修改第三方、未运行 benchmark、未调用模型 API、未 commit/push。
