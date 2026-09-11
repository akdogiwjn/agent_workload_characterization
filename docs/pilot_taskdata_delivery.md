# django__django-16485 官方任务记录获取与字段核对

本次按用户明确授权获取任务数据并只读核对；未运行 benchmark、Agent、模型 API、Docker、验证器或数据内脚本，未安装依赖。DeepSeek 配置未读取。

## 来源与保存

- 数据集：SWE-bench/SWE-bench_Verified，default/test。
- 固定 revision：`78f471bf655a3137b2e8a75af1501690ec009ec3`。
- 官方单行 filter 接口返回索引加载中；改为读取固定 revision 的唯一 Parquet 分片（6,304,616 bytes），使用本机已有 pyarrow 过滤目标 instance。
- 分片仅在内存读取，不保留其他499条记录，不进行其他任务分析。
- 保存目录：`data/raw/public/swebench_verified/78f471bf655a3137b2e8a75af1501690ec009ec3/django__django-16485/`，包含 `record.json` 和 `manifest.json`。目录由现有 gitignore 排除。
- Parquet SHA-256：`030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25`。
- 目标 JSON SHA-256：`762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`。这是 JSON 序列化产物哈希，不是 Parquet 原始行字节哈希。
- record 含参考 patch/test_patch，必须与未来 Agent 可见输入分离；本轮没有创建 Agent 输入投影，不能将整个 record 交给 Agent。

## 静态核对结果

目标 instance 唯一，属于该 revision 的 Verified/test；repo=`django/django`，version=`5.0`，base_commit=`39f83765e12b0e5d260b7939fc3fe281d879b279`。

当前参考 evaluator commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` 的 `utils.py:251 make_test_spec` 要求的 instance_id/image/eval_script/log_parser/eval_type/repo/version 均为非空字符串；FAIL_TO_PASS/PASS_TO_PASS 均为字符串列表，数量分别1和9，符合源码接受 list 的分支。eval_script 只做字符串/字段检查，绝不执行。

`log_parser=parse_log_django` 在本地 parser registry 存在，`eval_type=pass_and_fail` 在本地 EvalType 枚举存在。可确认字段形态匹配，当前没有因这些必需字段缺失而要求转换的证据；不等于已运行 make_test_spec 或 evaluator。

镜像引用为 `swebench/sweb.eval.x86_64.django_1776_django-16485:latest`。tag 不是不可变 digest；尚未查询镜像、下载/构建镜像或核实本机架构。镜像 digest、环境可执行性、验证脚本运行结果、Agent harness/provider 兼容性仍未确定。

## 状态与后续

DEC-TASKDATA：本次获取与字段级核对授权已执行完成。GAP-TASKDATA-001 的目标记录缺失已解决；GAP-VERIFIERSPEC-001 的必需字段/类型及 parser/enum 静态兼容性已核对，但镜像与运行级兼容性不在本次结论内。

本记录优先于此前设计文档中“目标记录本地缺失、字段是否齐备未知”的历史描述。P0-07/G0/M1 不自动通过：mini-SWE-agent 版本配置、DeepSeek-V4-Flash 接口适配等仍需独立核实。

后续任何安装、构建、运行仍需先列明具体任务、资源/时间和费用风险，等待用户明确确认。没有金额上限不等于无限运行授权。本次不触发 P1 预检。
