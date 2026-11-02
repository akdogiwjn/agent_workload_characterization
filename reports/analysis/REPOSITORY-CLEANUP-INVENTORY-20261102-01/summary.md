# 全仓库清理清点（仅清单，零删除）

用户已选择：先出完整清单，暂不删除任何文件。
本轮未运行工作负载、容器、模型、评分或旧清理脚本；未移动任何既有文件。

扫描 202,529 个文件/链接、68,468 个目录；按唯一 inode 的文件分配空间约 23.47 GiB。
不跟随符号链接、不跨设备；本清点输出目录不纳入自身扫描。文件分配空间不含目录 inode 块，硬链接/共享块使其不能等同未来可释放空间。

## 顶层占用

| 目录 | 按文件名累计分配空间 |
| --- | ---: |
| data | 11.41 GiB |
| reports | 3.81 GiB |
| references | 3.21 GiB |
| .venvs | 2.44 GiB |
| env | 2.37 GiB |
| local_archive | 0.14 GiB |
| .git | 0.08 GiB |
| docs | 0.00 GiB |
| scripts | 0.00 GiB |
| tests | 0.00 GiB |
| src | 0.00 GiB |
| .pytest_cache | 0.00 GiB |
| workload_catalog | 0.00 GiB |
| schemas | 0.00 GiB |
| .github | 0.00 GiB |

## 清理建议与保护边界

1. 首批仅复核根 pytest cache 及 scripts/tests/src 字节码：43 文件，表观 1.68 MiB。逐文件 SHA/跟踪/引用检查见 inventory.json；现在未批准删除。
2. 测试式命名目录 56 个（含空目录），可能是残留，但须核对 fixture/门禁/并发占用，不能只按名字删。
3. raw-persistent-copy 共 18 个，表观 1.45 GiB；保留的是刻意建立的独立副本。删除或硬链接化会改变保护策略/manifest，不自动处理。
4. 正式运行与失败观察、原生 trace、请求账本、输入、计划/EDL/timeline、图片/视频分段、最终媒体、身份/批准、报告和 manifest 全部保留。回放整理前不能仅保留 final、丢掉中间素材。
5. .venvs、references、模型目录和离线 build 包不是无用中间文件；删除会影响离线复现/构建，需另行决策。
6. local_archive 的状态/编辑快照是恢复依据（已有历史保护核对依赖它），不因名称含 backup/snapshot 就删除。
7. Git 的修改/删除/未跟踪状态不代表可清理，既有改动保持。旧 scripts/cleanup_video_intermediates.py 使用 2026-10-29 固定名单，未覆盖新九组运行，不可直接重跑。

## 完整清单

- file-inventory.csv.gz：全仓逐文件/链接元数据（路径、类型、大小、分配空间、mtime、硬链接数、Git跟踪、当前state登记、分类），不包含凭据或文件正文。
- directory-inventory.csv：所有扫描目录的递归计数/大小；嵌套行不可相加。
- inventory.json：分类统计、逐文件缓存候选SHA、疑似测试目录、保留副本及失败观察、扫描边界与错误。
- manifest.json：本次清点输出与脚本的哈希；不自哈希。

本清单是时间点快照，不是删除批准。未来删除前需重算目标SHA、引用与进程占用，并输出精确目标清单和删除回执。
