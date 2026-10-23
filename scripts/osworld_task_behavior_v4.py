"""Offline OSWorld v4 command coverage; native v3 evidence remains separate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osworld_task_behavior as legacy
from osworld_static_actions_v4 import Sequence, static_calls

PROJECT = Path(__file__).resolve().parents[1]


def hash_record(path):
    path = Path(path)
    size, digest = legacy.sha(path)
    try:
        name = str(path.relative_to(PROJECT))
    except ValueError:
        name = str(path)
    return {"path": name, "bytes": size, "sha256": digest}


def verify_entry(entry, path=None):
    path = Path(path if path is not None else entry["path"])
    if not path.is_file():
        raise ValueError(f"missing frozen input: {path}")
    record = hash_record(path)
    if (record["bytes"], record["sha256"]) != (entry["bytes"], entry["sha256"]):
        raise ValueError(f"frozen evidence mismatch: {path}")
    return record


def batch_summary(groups):
    counts = Counter()
    for rows in groups.values():
        sizes = {r["batch_size"] for r in rows if type(r["batch_size"]) is int and r["batch_size"] > 0}
        indices = [r["batch_index"] for r in rows if type(r["batch_index"]) is int]
        duplicates = len(indices) - len(set(indices))
        coherent_size = len(sizes) == 1 and all(type(r["batch_size"]) is int and r["batch_size"] > 0 for r in rows)
        size = next(iter(sizes)) if coherent_size else None
        index_valid = coherent_size and len(indices) == len(rows) and all(0 <= i < size for i in indices)
        flags_valid = index_valid and all(type(r["batch_last"]) is bool and
                                         r["batch_last"] == (r["batch_index"] == size - 1) for r in rows)
        complete = bool(flags_valid and not duplicates and len(indices) == size)
        counts["saved_call_id_groups"] += 1
        counts["records_in_call_id_groups"] += len(rows)
        counts["complete_batch_groups" if complete else "incomplete_or_ambiguous_groups"] += 1
        counts["duplicate_batch_index_records"] += duplicates
        counts["size_conflict_groups"] += not coherent_size
        counts["invalid_index_groups"] += not index_valid
        counts["last_flag_issue_groups"] += not flags_valid
    return dict(counts)


def numbered_lines(path):
    with path.open() as stream:
        yield from enumerate(stream, 1)


def analyze_trajectory(path, root, baseline, audit_stream=None):
    source = str(path.relative_to(root))
    status, categories, names = Counter(), Counter(), Counter()
    reasons, metadata, native_fields = Counter(), Counter(), Counter()
    total_ast = command_count = missing_command = saved_rows = invalid = supported = 0
    sequence = Sequence()
    examples, unknown_examples = [], []
    groups = defaultdict(list)
    for line_no, line in numbered_lines(path):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("row not object")
        except (ValueError, UnicodeError):
            invalid += 1
            sequence.add(None)
            continue
        saved_rows += 1
        action = row.get("action")
        command = action if isinstance(action, str) else action.get("command") if isinstance(action, dict) else None
        if isinstance(action, dict):
            native_fields.update(k for k, v in action.items() if v is not None)
            cid = action.get("call_id")
            if isinstance(cid, str) and cid:
                groups[cid].append({"batch_size": action.get("batch_size"),
                                    "batch_index": action.get("batch_index"),
                                    "batch_last": action.get("batch_last")})
        if not isinstance(command, str):
            missing_command += 1
            sequence.add(None)
            continue
        command_count += 1
        parsed = static_calls(command)
        status[parsed["status"]] += 1
        total_ast += parsed["source_call_syntax_count"]
        supported += len(parsed["calls"])
        reasons.update(parsed["reason_counts"])
        metadata.update(parsed["metadata_statements"])
        per_categories = Counter(call["category"] for call in parsed["calls"])
        categories.update(per_categories)
        names.update(call["canonical_name"] for call in parsed["calls"])
        for token in parsed["tokens"]:
            sequence.add(token)
        code_hash = hashlib.sha256(command.encode()).hexdigest()
        if parsed["status"] in {"unknown", "partial"} and len(unknown_examples) < 12:
            unknown_examples.append({"source_line": line_no, "command_sha256": code_hash,
                                     "status": parsed["status"], "reasons": parsed["reason_counts"]})
        if len(examples) < 12:
            examples.extend({"source_line": line_no, "command_sha256": code_hash, **c}
                            for c in parsed["calls"][:12 - len(examples)])
        if audit_stream is not None:
            audit = {"model": baseline["model"], "task_key": baseline["task_key"],
                     "source_file": source, "source_line": line_no,
                     "command_sha256": code_hash, "command_bytes": len(command.encode()),
                     "status": parsed["status"], "source_ast_calls": parsed["source_call_syntax_count"],
                     "accepted_calls": len(parsed["calls"]), "category_counts": dict(per_categories),
                     "unknown_reasons": parsed["reason_counts"], "metadata_statements": parsed["metadata_statements"]}
            audit_stream.write(json.dumps(audit, ensure_ascii=False, separators=(",", ":")) + "\n")
    if saved_rows != baseline["record_count"] or command_count != baseline["command_record_count"]:
        raise ValueError(f"baseline record set differs: {source}")
    if "source_call_syntax_count" in baseline and total_ast != baseline["source_call_syntax_count"]:
        raise ValueError(f"lexical AST occurrence count differs from frozen v3: {source}")
    if supported > total_ast:
        raise ValueError("accepted calls exceed lexical AST call nodes")
    command_coverage = ((status["known"] + status["partial"]) / command_count if command_count else None)
    return {"model": baseline["model"], "task_key": baseline["task_key"], "source_file": source,
            "record_count": saved_rows, "invalid_json_lines": invalid,
            "command_record_count": command_count, "command_missing_count": missing_command,
            "v3_supported_static_call_count": baseline["supported_static_call_count"],
            "v3_known_command_records": baseline["unknown_reason_counts"].get("known", 0),
            "supported_static_call_count": supported, "source_call_syntax_count": total_ast,
            "command_status_counts": dict(status), "commands_with_identified_call_ratio": command_coverage,
            "static_category_counts": dict(sorted(categories.items())), "static_call_names": dict(sorted(names.items())),
            "unknown_statement_reasons": dict(reasons), "metadata_statements": dict(metadata),
            "static_sequence": sequence.finish(), "call_source_examples": examples,
            "unknown_source_examples": unknown_examples, "examples_are_bounded_not_counts": True,
            "saved_protocol": {"nonnull_action_fields": dict(native_fields), "batch_id_groups": batch_summary(groups),
                               "semantic": "saved call_id groups inside one model/task; not actual HTTP requests, execution count or concurrency"},
            "native_v3": {k: baseline[k] for k in
                          ("native_representation_status", "native_action_record_count", "native_unknown_action_count",
                           "native_action_category_counts", "native_sequence")},
            "results_v3": baseline["results"], "done_counts_v3": baseline["done_counts"],
            "reward_v3": baseline["reward"], "task_labels_v3": baseline.get("task_label"),
            "evidence_semantics": "top-level saved source calls only; native records and source calls are separate denominators"}


def aggregate(rows):
    out = {}
    for model in sorted({r["model"] for r in rows}):
        selected = [r for r in rows if r["model"] == model]
        record = {"trajectories": len(selected)}
        for key in ("record_count", "command_record_count", "command_missing_count", "source_call_syntax_count",
                    "supported_static_call_count", "v3_supported_static_call_count", "v3_known_command_records", "invalid_json_lines"):
            record[key] = sum(r[key] for r in selected)
        for key in ("command_status_counts", "static_category_counts", "static_call_names", "unknown_statement_reasons", "metadata_statements"):
            total = Counter()
            for r in selected:
                total.update(r[key])
            record[key] = dict(sorted(total.items()))
        for key in ("batch_id_groups", "nonnull_action_fields"):
            total = Counter()
            for r in selected:
                total.update(r["saved_protocol"][key])
            record["saved_protocol_" + key] = dict(total)
        record["v3_known_command_ratio"] = record["v3_known_command_records"] / record["command_record_count"]
        statuses = record["command_status_counts"]
        record["v4_commands_with_identified_call_ratio"] = (statuses.get("known", 0) + statuses.get("partial", 0)) / record["command_record_count"]
        out[model] = record
    return out


def plot_comparison(models, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = list(models)
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    positions = list(range(len(labels)))
    ax.barh([v + .19 for v in positions], [models[m]["v3_known_command_ratio"] * 100 for m in labels],
            height=.36, label="v3: whole command recognized", color="#94a3b8")
    ax.barh([v - .19 for v in positions], [models[m]["v4_commands_with_identified_call_ratio"] * 100 for m in labels],
            height=.36, label="v4: at least one classified call (includes partial)", color="#2563eb")
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("Command records (%) within each model; different coverage definitions")
    ax.set_title("OSWorld saved-source parser coverage; not execution or model performance")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=.15)
    fig.savefig(output / "command-coverage.svg")
    fig.savefig(output / "command-coverage.png", dpi=150)
    plt.close(fig)


def run(trajectory_root, baseline_dir, output, plots=True):
    trajectory_root, baseline_dir, output = map(Path, (trajectory_root, baseline_dir, output))
    if output.exists():
        raise ValueError("output directory exists; refusing overwrite")
    for raw in (trajectory_root, baseline_dir):
        if output.resolve().is_relative_to(raw.resolve()) or raw.resolve().is_relative_to(output.resolve()):
            raise ValueError("input/output overlap")
    manifest_path = baseline_dir / "manifest.json"
    original_manifest_record = hash_record(manifest_path)
    codes = [hash_record(Path(__file__).resolve()), hash_record(Path(__file__).with_name("osworld_static_actions_v4.py").resolve()),
             hash_record(PROJECT / "tests/test_osworld_task_behavior_v4.py")]
    manifest = json.loads(manifest_path.read_text())
    verified = []
    for entry in manifest["inputs"] + manifest["analysis_code"]:
        verified.append(verify_entry(entry))
    for entry in manifest["outputs"]:
        verified.append(verify_entry(entry, baseline_dir / entry["path"]))
    inventory = next(Path(x["path"]) for x in manifest["inputs"]
                     if x["path"].endswith("OSWORLD-OFFICIAL-LIGHT-inventory-v1/inventory.json"))
    _, original_files = legacy.verify_inventory(trajectory_root, inventory)
    with (baseline_dir / "per_trajectory.jsonl").open() as stream:
        baseline_rows = [json.loads(line) for line in stream]
    expected_paths = {str(trajectory_root / r["source_file"]) for r in baseline_rows}
    actual_paths = {str(p) for p in trajectory_root.glob("website_demo/*/tasks/*/traj.jsonl")}
    if expected_paths != actual_paths:
        raise ValueError("baseline and actual trajectory sets differ")
    output.mkdir(parents=True)
    rows = []
    previous = None
    with (output / "command_records.jsonl").open("w") as audit:
        for baseline in baseline_rows:
            if baseline["model"] != previous:
                print("Parsing saved commands: " + baseline["model"], flush=True)
                previous = baseline["model"]
            rows.append(analyze_trajectory(trajectory_root / baseline["source_file"], trajectory_root, baseline, audit))
    models = aggregate(rows)
    with (output / "per_trajectory.jsonl").open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    baseline_summary = json.loads((baseline_dir / "summary.json").read_text())
    summary = {"schema": "osworld-task-behavior.v4", "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": "PASS_WITH_EXPLICIT_UNKNOWNS" if not any(r["invalid_json_lines"] for r in rows) else "PARTIAL",
               "scope": f"same frozen {len(rows)} model-task records; no new downloads or task execution",
               "baseline": str(baseline_dir), "input_provenance": baseline_summary["inputs"],
               "models": models, "trajectory_count": len(rows),
               "command_record_count": sum(r["command_record_count"] for r in rows),
               "invalid_json_lines": sum(r["invalid_json_lines"] for r in rows),
               "native_v3_counts_preserved": True,
               "rules": {"accepted": "top-level direct calls to explicit whitelist; known imports/aliases and literal declarations recognized without execution",
                         "unknown": "unsupported imports, assignments, control flow, functions, dynamic calls and nested-call arguments become ordered boundaries; no loop expansion",
                         "binding": "pyautogui is a documented per-command predefined name; time/pyperclip/aliases require explicit import; rebinding invalidates aliases",
                         "ordering": "saved record/source order only; unknown segments break transitions; no reconstruction of true execution or concurrency",
                         "native": "v3 native records unchanged; computer_call wrapper is not converted into a fictitious native click record",
                         "coverage": "v3 requires complete command recognition; v4 separately reports whole known, partial, unknown, metadata-only; percentages are not identical metrics",
                         "batch": "call_id/batch_index/batch_size/batch_last are scoped to one model-task; duplicate or inconsistent groups remain ambiguous; no deduplication or HTTP count inference"},
               "remaining_unknowns": ["historical task version binding", "runtime foreground application", "actual action execution/duration",
                                      "CPU/memory/IO/network", "unknown branches/imports/dataflow and clipboard decode assignments"],
               "usage_and_task_semantics": "reuse frozen v3 evidence; no new API usage, model ranking or task-result reinterpretation"}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    with (output / "coverage.csv").open("w") as stream:
        fields = ["model", "trajectories", "command_record_count", "v3_supported_static_call_count", "supported_static_call_count",
                  "known", "partial", "unknown", "metadata_only", "v3_known_command_ratio", "v4_commands_with_identified_call_ratio"]
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for model, record in models.items():
            writer.writerow({"model": model, **{k: record[k] for k in fields if k not in {"model", "known", "partial", "unknown", "metadata_only"}},
                             **{k: record["command_status_counts"].get(k, 0) for k in ("known", "partial", "unknown", "metadata_only")}})
    md = ["# OSWorld v4：命令静态解析覆盖与保存序列复核", "",
          f"生成：{summary['created_at_utc']}。本地同一固定语料，{len(rows)}条model×task记录、{len(models)}个来源模型标签、{baseline_summary['inputs'].get('task_semantics_count', len({r['task_key'] for r in rows}))}个任务定义/本地任务键。未执行任何轨迹、GUI动作、模型或benchmark；v1/v2/v3原件保留。", "",
          "## 覆盖变化", "",
          "v3整段只接受白名单直接调用，import、赋值或任一未知语句会拒绝整段。v4支持已知import/别名和字面量声明，按顶层语句分别识别；未知语句保留边界。新增hotkey/typewrite/write、time.sleep、screenshot和clipboard等明确函数名。", "",
          "| 来源模型标签 | command记录 | v3识别源码调用 | v4识别源码调用 | v4整段已知 / 部分 / 未知 / 仅元数据 |", "|---|---:|---:|---:|---|"]
    for model, record in models.items():
        statuses = record["command_status_counts"]
        md.append(f"| {model} | {record['command_record_count']:,} | {record['v3_supported_static_call_count']:,} | {record['supported_static_call_count']:,} | "
                  + " / ".join(f"{statuses.get(k, 0):,}" for k in ("known", "partial", "unknown", "metadata_only")) + " |")
    md += ["", "源码调用数是保存代码中的顶层调用出现次数，不是实际执行次数。一个command可有多个调用，不能用调用数除以记录数当覆盖率。v4的“部分”保留已识别调用及未知边界，绝不把整段称完整。", "",
           "## 行为构成与保存序列", "",
           "逐model/task的分类计数、函数名、转换与连续段见per_trajectory.jsonl；每个command的状态、分类、源码SHA及原始行号见command_records.jsonl。None边界不产生跨未知片段转换，循环/分支/函数体不展开。重复记录不按step_num、call_id或相同代码擅自去重。", "",
           "本轮同时增加Qwen对typewrite/hotkey的识别。MiniMax极大量press保留为重复源码出现，不能解释为用户真实按键量。Claude文本输入包装中的try/赋值仍是未知结构；其原生type记录在v3原生层已存在，不能据静态未知声称没有输入动作。", "",
           "## 原生动作与batch协议", "",
           "原生层v3的native_action_category_counts/native_sequence逐项保留，未将GPT的computer_call包装转换成原生动作。新的命令分类提供另一层源码证据；两层不相加。screenshot与其command中的sleep占位分别保留，不把占位时间当真实截图耗时。", "",
           "保存call_id按同一model/task聚合，检查batch_size、index范围、重复index、last标记和完整性；结果在summary.json的saved_protocol字段。ID组不等于实际HTTP请求或真实执行批次，更不证明并行；同ID重复或冲突保留为歧义。", "",
           "## 核验与边界", "",
           f"v3全部输入/输出及分析代码逐项验哈希；inventory覆盖{len(original_files)}个原始/缓存文件。每条轨迹的保存记录数和command数与v3一致；未新增或筛除任务。",
           "任务定义、评分/终止字段、MiniMax usage沿用已冻结v3证据；版本绑定、前台应用、动作实际效果、耗时与资源仍未知。源码中不含某函数或被标为unknown均不证明该动作没有执行。", "",
           "[机器摘要](summary.json) · [覆盖表](coverage.csv) · [逐轨迹](per_trajectory.jsonl) · [逐command审计](command_records.jsonl) · [manifest](manifest.json)"]
    if plots:
        plot_comparison(models, output)
        md += ["", "![命令覆盖](command-coverage.png)", "", "[SVG](command-coverage.svg) · [PNG](command-coverage.png)",
               "图中v3为整段识别、v4为至少有一条已识别调用，分母均为该模型command记录；完整/部分须结合上表，图不表示模型能力。"]
    (output / "summary.md").write_text("\n".join(md) + "\n")
    # Verify all evidence again after the pass, including files only used by v3.
    for record in verified:
        verify_entry(record)
    for record in codes + [original_manifest_record]:
        verify_entry(record)
    legacy.verify_inventory(trajectory_root, inventory)
    out_manifest = {"schema": "osworld-task-behavior-manifest.v4", "baseline_manifest": original_manifest_record,
                    "verified_baseline_evidence": verified, "analysis_code_and_tests": codes,
                    "outputs": [hash_record(p.resolve()) for p in sorted(output.iterdir()) if p.is_file()],
                    "manifest_self_hash_excluded": True, "source_and_history_preserved": True}
    (output / "manifest.json").write_text(json.dumps(out_manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": summary["status"], "trajectories": len(rows),
                      "commands": summary["command_record_count"], "report": str(output / 'summary.md')}), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory-root", type=Path, default=Path("data/raw/public/osworld2_trajectory_light"))
    parser.add_argument("--baseline-dir", type=Path, default=Path("reports/analysis/OSWORLD-task-behavior-v3"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.trajectory_root, args.baseline_dir, args.output_dir)


if __name__ == "__main__":
    main()
