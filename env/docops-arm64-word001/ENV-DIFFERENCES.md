# 环境差异说明：DocOps 原生 arm64 适配环境（word_001）

正式名称：**DocOps 原生 arm64 适配环境**（非官方环境、非字节等效、未证明性能等效、不可直接与官方结果比较）。

## 方案变更记录（2026-10-08）

原方案（build-context/ 中保留，未使用）：基于 python:3.12-slim 自建文档工具栈镜像。用户确认本地已有镜像后放弃自建，改用本地已有的 `harbor-claude-code-base:2.1.114`（arm64）。

## 实际使用的基础镜像身份

- 标签：`harbor-claude-code-base:2.1.114`（同时带 `harbor-codex-base:2.1.114` 标签，同一 image ID）
- Image ID：`sha256:062bf50871c0e9d7d4a175643343746f27c785732596252d7ebe9ae0c08fe9b1`
- 架构：**linux/arm64**（原生，无 QEMU）；Created 2026-08-31；本地 buildkit 构建，无 RepoDigest（不补造）
- **来源（provenance）：unknown**——本地已有、项目内无构建登记；docker history 显示其层构成（见下），内容经本轮运行时核验（pip freeze、模块导入、工具与 verifier smoke）
- 与官方 amd64 归档（LFS oid `1b1f4682…`，787,773,358 bytes）**无字节级对应关系**；官方归档未下载未核对

## docker history 核验的层构成（自底向上）

1. Python 3.12.14 官方基础（debian bookworm arm64，`debian.sh --arch 'arm64'`）
2. apt（阿里镜像源）：bash、curl、ca-certificates、git、ripgrep、procps、xz-utils
3. Node.js v22.23.2 linux-arm64（腾讯镜像）+ npmmirror
4. pip（阿里镜像）：pytest、**pytest-json-ctrf**（test.sh 的 `--ctrf` 所需）、openpyxl、python-docx、python-pptx、pypdf、pdfplumber、reportlab、PyMuPDF、Pillow、pandas、numpy——与 DocOps requirements.txt 逐项对应
5. npm 全局：@anthropic-ai/claude-code、@openai/codex@0.80.0

同源中间镜像 `docops-base:arm64`（`ca38db159ecb`，757MB）= 上述 1–4 层（无第 5 层 CLI）。

## 与官方环境的已知差异 / unknown

1. 官方 base 的实际内容（OS 细节、预装工具版本、CLI 版本）：unknown（amd64 归档未下载）
2. pip 依赖为构建时（2026-08-31，阿里镜像源）解析版本，**非官方 base 实际版本**；实际版本以本轮容器内 pip freeze 登记为准
3. 渲染工具：render_docx.py 需要 soffice + poppler + pdf2image，本环境未提供（word_001 任务路径与 verifier 不使用）
4. 构建使用国内镜像源（aliyun/tencent/npmmirror）——与官方构建的源不同
5. claude-code/codex CLI 层存在但本试点不使用（DocumentToolsAgent 不依赖 CLI）

## 任务镜像

- 构建方式：按官方任务 Dockerfile（`references/repos/DocOps/tasks/atomic__word_001_engineering_report_toc_hierarchy_seed/environment/Dockerfile`，只读使用未修改）构建
- 唯一标签：`docops-word001-task:arm64-adapted-v1`（不覆盖任何已有标签）
