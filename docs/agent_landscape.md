# Agent Landscape（简版，P0-07）

## 覆盖场景

| 场景 | 主要 Benchmark | 可运行 Agent | 核心 Tool | 公开 Trace | 本地 Trace |
| --- | --- | --- | --- | --- | --- |
| Coding | SWE-bench Verified | OpenHands / SWE-agent | bash, str_replace_editor, python | 1,465 条 | 否（需 Docker 运行） |
| Office | DocOps | codex (Harbor) | LibreOffice, openpyxl | 无 | 68 trial |
| Assistant | ToolSandbox | codex（待验证） | API, state | 无 | 无 |
| Video | VideoWeaver | OpenClaw + codex | FFmpeg, python | 4 bundle | 4 bundle |

## 系统层主要软件
- Coding: Python, gcc, pytest, git, bash
- Office: LibreOffice, python openpyxl/python-pptx, bash
- Assistant: Python, shell, network API
- Video: FFmpeg, Python, model API client

## 试点定位
本简版仅登记现有计划中的候选，不扩 Benchmark 清单。可执行性与预算缺口详见
[benchmark_selection.md](benchmark_selection.md)。
