"""Render v4 behavior findings from hash-bound analysis outputs only."""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from osworld_task_behavior_v4 import hash_record, verify_entry


def quantile(values, p):
    values = sorted(values)
    index = (len(values) - 1) * p
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def render(report):
    report = Path(report)
    targets = [report / name for name in ("findings.md", "static_categories.csv", "static_transitions.csv", "findings-manifest.json")]
    if any(p.exists() for p in targets):
        raise FileExistsError("findings output exists; refusing overwrite")
    manifest = json.loads((report / "manifest.json").read_text())
    for entry in manifest["outputs"]:
        if Path(entry["path"]).name in {"summary.json", "per_trajectory.jsonl"}:
            verify_entry(entry)
    summary = json.loads((report / "summary.json").read_text())
    with (report / "per_trajectory.jsonl").open() as stream:
        rows = [json.loads(line) for line in stream]
    models = summary["models"]
    categories = sorted({c for m in models.values() for c in m["static_category_counts"]})
    md = ["# OSWorld v4：补充解析后的行为发现", "",
          "完整读取同一批755条model×task记录；本报告只描述保存命令的静态调用与保存顺序。每个模型独立统计，不做能力、效率或资源排名。", "",
          "## 修复带来的增量", "",
          "| 模型标签 | v3 / v4识别源码调用 | v4整段已知command | v4部分已知command | v4未知command | 仅元数据command |", "|---|---:|---:|---:|---:|---:|"]
    for model, values in models.items():
        statuses = values["command_status_counts"]
        md.append(f"| {model} | {values['v3_supported_static_call_count']:,} / {values['supported_static_call_count']:,} | "
                  + " | ".join(f"{statuses.get(k, 0):,}" for k in ("known", "partial", "unknown", "metadata_only")) + " |")
    md += ["", "v4已识别调用包含partial命令中有明确证据的顶层调用；partial仍不是整段完整。初始/其他无command记录不进入command覆盖率，具体数量见summary.json。原生动作层保持v3，不能把源码增量当成新增实际执行。", "",
           "## 已识别源码调用的活动构成", "",
           "下表单位均为调用源码出现次数；一个command可以包含多个调用。类别计数仅覆盖白名单识别部分，未知片段不被填成零次业务操作。", "",
           "| 模型标签 | " + " | ".join(categories) + " |", "|---|" + "---:|" * len(categories)]
    with (report / "static_categories.csv").open("w") as stream:
        writer = csv.DictWriter(stream, ["model", "category", "saved_source_call_occurrences", "fraction_of_classified_source_calls"])
        writer.writeheader()
        for model, values in models.items():
            md.append("| " + model + " | " + " | ".join(f"{values['static_category_counts'].get(c, 0):,}" for c in categories) + " |")
            for category in categories:
                count = values["static_category_counts"].get(category, 0)
                writer.writerow({"model": model, "category": category, "saved_source_call_occurrences": count,
                                 "fraction_of_classified_source_calls": count / values["supported_static_call_count"] if values["supported_static_call_count"] else None})
    md += ["", "typewrite/write/hotkey补充的是键盘与文本输入，time.sleep单列wait，pyperclip.copy/paste单列clipboard。clipboard接口出现不证明粘贴成功；文本内容、base64解码和应用业务语义没有执行或恢复。", "",
           "## 逐轨迹分布与源码集中度", "",
           "| 模型标签 | 轨迹n | 已识别源码调用/轨迹 median | IQR | 最大值 / 本地task key |", "|---|---:|---:|---:|---|"]
    for model in models:
        selected = [r for r in rows if r["model"] == model]
        counts = [r["supported_static_call_count"] for r in selected]
        peak = max(selected, key=lambda r: r["supported_static_call_count"])
        md.append(f"| {model} | {len(selected)} | {quantile(counts, .5):.1f} | {quantile(counts, .75)-quantile(counts, .25):.1f} | {peak['supported_static_call_count']:,} / {peak['task_key']} |")
    md += ["", "分位数使用(n−1)×p线性插值，包含该模型全部轨迹的零值；不是按调用量加权的轨迹平均。MiniMax的大量重复press是保存源码的重复出现，不按step/call_id擅自去重，也不解释为用户实际按键量。", "",
           "## 保存序列与未知边界", "",
           "| 模型标签 | 保存源码顺序中计数最高的三个转换 |", "|---|---|"]
    with (report / "static_transitions.csv").open("w") as stream:
        writer = csv.DictWriter(stream, ["model", "from_category", "to_category", "saved_source_order_pairs"])
        writer.writeheader()
        for model in models:
            transitions = Counter()
            for row in rows:
                if row["model"] == model:
                    transitions.update(row["static_sequence"]["transition_counts"])
            md.append(f"| {model} | " + "; ".join(f"{k}={v:,}" for k, v in transitions.most_common(3)) + " |")
            for pair, count in sorted(transitions.items()):
                a, b = pair.split("->")
                writer.writerow({"model": model, "from_category": a, "to_category": b, "saved_source_order_pairs": count})
    md += ["", "转换只在没有未知片段隔断的保存源码相邻调用之间计数。unsupported语句、无command记录或坏JSON会截断；不跨越它们恢复业务流程，也不据转换推断实际执行顺序、并行或耗时。", "",
           "## call_id与批次字段", "",
           "| 模型标签 | 保存ID组 | 索引/size/last完整组 | 不完整或歧义组 | 重复index记录 |", "|---|---:|---:|---:|---:|"]
    for model, values in models.items():
        batch = values["saved_protocol_batch_id_groups"]
        md.append(f"| {model} | " + " | ".join(str(batch.get(k, 0)) for k in ("saved_call_id_groups", "complete_batch_groups", "incomplete_or_ambiguous_groups", "duplicate_batch_index_records")) + " |")
    md += ["", "没有call_id字段的模型此表为0个可分组ID，不代表0次工具执行。组仅按一个model/task内同一保存ID汇集；完整仅指保存的index/size/last一致，不证明结果成功或真实网络调用闭合。", "",
           "## 剩余缺口", "",
           "- Claude的try/属性赋值包装、GPT部分base64解码赋值仍未解析；本轮不穿透控制流猜实际分支。",
           "- GPT computer_call仍是通用包装，原生动作类型未知；命令静态类别是独立证据，不能回填为原生点击/输入。",
           "- task key与历史运行版本绑定、前台应用、动作效果、可靠耗时和资源仍无新增证据。",
           "- 这里补充的是已有语料的解析覆盖；SWE-bench、H-EPM等下一项未启动。", "",
           "[解析覆盖报告](summary.md) · [分类CSV](static_categories.csv) · [转换CSV](static_transitions.csv) · [逐command审计](command_records.jsonl) · [派生manifest](findings-manifest.json)"]
    (report / "findings.md").write_text("\n".join(md) + "\n")
    derived = {"schema": "osworld-v4-findings-manifest-v1", "inputs": [hash_record(report / name) for name in ("manifest.json", "summary.json", "per_trajectory.jsonl")],
               "renderer": hash_record(Path(__file__).resolve()),
               "outputs": [hash_record(p) for p in targets[:-1]], "manifest_self_hash_excluded": True,
               "no_raw_reparse_or_execution": True}
    (report / "findings-manifest.json").write_text(json.dumps(derived, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "findings": str(report / 'findings.md')}, ensure_ascii=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--report", type=Path, required=True)
    render(cli.parse_args().report)
