#!/usr/bin/env python3
"""Offline MiniMax-M3 OSWorld behavior analysis, v2.

Only a deliberately small, non-executing action grammar is supported: a module
body made entirely of direct calls to known pyautogui functions. Everything else
is retained as an unknown boundary, while AST call-node occurrence counts are
reported separately.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

EXPECTED_REVISION = "01cb84fcd5fb8ee415e7e065d7aaf3ec8f95fe1f"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL = "MiniMax-M3"
CATEGORIES = ("click", "pointer", "text_or_key", "scroll", "wait", "other", "unknown")
CALL_CATEGORY = {
    "pyautogui.click": "click", "pyautogui.doubleClick": "click",
    "pyautogui.tripleClick": "click", "pyautogui.rightClick": "click",
    "pyautogui.moveTo": "pointer", "pyautogui.dragTo": "pointer",
    "pyautogui.mouseDown": "pointer", "pyautogui.mouseUp": "pointer",
    "pyautogui.press": "text_or_key", "pyautogui.keyDown": "text_or_key",
    "pyautogui.keyUp": "text_or_key", "pyautogui.scroll": "scroll",
    "pyautogui.hscroll": "scroll", "pyautogui.sleep": "wait",
}
UNSUPPORTED_NODES = (
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.For, ast.AsyncFor, ast.While, ast.If, ast.Try, ast.With,
    ast.AsyncWith, ast.Match, ast.NamedExpr,
)


class AnalysisError(ValueError):
    pass


def sha256_file(path: Path):
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            h.update(block)
    return size, h.hexdigest()


def call_name(node):
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        parts = [function.attr]
        value = function.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return type(function).__name__


def _has_nested_call(call_node):
    return any(isinstance(node, ast.Call) for node in ast.walk(call_node) if node is not call_node)


def static_calls(action):
    """Return source-call occurrences and calls accepted by the small grammar."""
    base = {"source_call_syntax_count": 0, "calls": [], "status": "unknown"}
    if not isinstance(action, str):
        base["reason"] = "action_not_string"
        return base
    try:
        tree = ast.parse(action)
    except SyntaxError:
        base["reason"] = "syntax_error"
        return base

    source_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    base["source_call_syntax_count"] = len(source_nodes)
    if not source_nodes:
        base["reason"] = "no_static_call"
        return base
    if any(isinstance(node, UNSUPPORTED_NODES) for node in ast.walk(tree)):
        base["reason"] = "unsupported_structure"
        return base

    calls = []
    for statement in tree.body:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            base["reason"] = "non_direct_statement"
            return base
        call = statement.value
        if _has_nested_call(call):
            base["reason"] = "nested_call"
            return base
        name = call_name(call)
        if name not in CALL_CATEGORY:
            base["reason"] = "unknown_call"
            return base
        calls.append({
            "call_name": name,
            "category": CALL_CATEGORY[name],
            "line_in_action": getattr(call, "lineno", None),
            "column_in_action": getattr(call, "col_offset", None),
        })
    if not calls:
        base["reason"] = "no_direct_action"
        return base
    for index, call in enumerate(calls, 1):
        call["call_index"] = index
    base.update({"status": "known", "reason": None, "calls": calls})
    return base


def quantiles(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "median": None, "iqr": None, "q1": None, "q3": None}

    def q(point):
        if len(values) == 1:
            return float(values[0])
        position = (len(values) - 1) * point
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return float(values[low] + (values[high] - values[low]) * (position - low))

    q1, q3 = q(.25), q(.75)
    return {"n": len(values), "median": q(.5), "iqr": q3 - q1, "q1": q1, "q3": q3}


def scalar_value(value):
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        if not math.isfinite(value):
            return {"type": "float", "value": None, "finite": False}
        return {"type": "float", "value": value, "finite": True}
    if isinstance(value, str):
        return {"type": "str", "value_present": bool(value), "length": len(value)}
    return {"type": type(value).__name__, "value_present": True}


def safe_result(path: Path, kind: str):
    if not path.exists():
        return {"status": "missing"}
    if kind == "txt":
        lines = path.read_text(errors="replace").splitlines()
        numeric = []
        nonnumeric_lines = []
        for line_number, line in enumerate(lines, 1):
            text = line.strip()
            if not text:
                continue
            try:
                value = float(text)
            except ValueError:
                nonnumeric_lines.append(line_number)
                continue
            numeric.append({"line": line_number, **scalar_value(value)})
        return {
            "status": "present", "line_count": len(lines),
            "numeric_values": numeric,
            "nonnumeric_line_count": len(nonnumeric_lines),
            "nonnumeric_line_numbers": nonnumeric_lines,
            "semantic": "unknown; numeric text preserved without success interpretation",
        }
    try:
        value = json.loads(path.read_text(errors="replace"))
    except Exception as exc:
        return {"status": "invalid", "error_type": type(exc).__name__}
    if kind == "result":
        record = {
            "status": "present", "top_type": type(value).__name__,
            "keys": sorted(value) if isinstance(value, dict) else None,
            "score": {"status": "missing"},
        }
        if isinstance(value, dict) and "score" in value:
            score = scalar_value(value["score"])
            score["status"] = "present" if score["type"] in {"int", "float"} and score.get("finite", True) else "present_non_numeric_or_nonfinite"
            record["score"] = score
        return record
    rows = value if isinstance(value, list) else []
    allowed = {"score", "reward", "success", "done", "passed", "partial_score"}
    fields = []
    for entry_index, entry in enumerate(rows):
        if not isinstance(entry, dict):
            continue
        for key, item in entry.items():
            if key in allowed:
                fields.append({"entry": entry_index, "field": key, **scalar_value(item)})
    return {
        "status": "present", "top_type": type(value).__name__,
        "entry_count": len(rows),
        "entry_key_union": sorted({key for row in rows if isinstance(row, dict) for key in row}),
        "recognized_scalar_fields": fields,
        "semantic": "field names/values retained; task-success meaning unknown",
    }


def reward_summary(rows):
    type_counts = Counter()
    values = Counter()
    missing = nulls = 0
    for row in rows:
        if "reward" not in row:
            missing += 1
            continue
        value = row["reward"]
        if value is None:
            nulls += 1
        info = scalar_value(value)
        type_counts[info["type"]] += 1
        if info["type"] in {"int", "float", "bool"} and info.get("finite", True):
            values[json.dumps(info["value"], sort_keys=True)] += 1
    return {
        "missing_count": missing, "null_count": nulls,
        "type_counts": dict(sorted(type_counts.items())),
        "numeric_or_bool_value_counts": {key: values[key] for key in sorted(values)},
        "semantic": "raw reward values; not mapped to task success",
    }


def finish_segments(tokens):
    transitions = Counter()
    segment_counts = Counter()
    segment_actions = Counter()
    segment_lengths = Counter()
    previous = None
    length = 0

    def finish():
        nonlocal previous, length
        if previous is not None:
            segment_counts[previous] += 1
            segment_actions[previous] += length
            segment_lengths[(previous, length)] += 1
        previous = None
        length = 0

    for token in tokens + [None]:
        if token is None:
            finish()
            continue
        if previous is not None:
            transitions[(previous, token)] += 1
        previous = token if previous is None else previous
        if length == 0:
            previous = token
            length = 1
        elif token == previous:
            length += 1
        else:
            # The transition above belongs to the preceding and current token.
            # Close the old segment, then begin the current one.
            old = previous
            old_length = length
            segment_counts[old] += 1
            segment_actions[old] += old_length
            segment_lengths[(old, old_length)] += 1
            previous = token
            length = 1
    return transitions, segment_counts, segment_actions, segment_lengths


def verify_inventory(input_root: Path, inventory_path: Path, model=MODEL):
    inventory = json.loads(inventory_path.read_text())
    if inventory.get("requested_revision") != EXPECTED_REVISION:
        raise AnalysisError("inventory revision mismatch")
    registered = {item["path"]: item for item in inventory["files"]}
    base = input_root / "website_demo" / model
    if not base.is_dir():
        raise AnalysisError("model directory missing")
    actual = sorted(path for path in base.rglob("*") if path.is_file())
    for path in actual:
        relative = str(path.relative_to(input_root))
        item = registered.get(relative)
        if not item:
            raise AnalysisError("input not registered: " + relative)
        size, digest = sha256_file(path)
        if size != item["bytes"] or digest != item["sha256"]:
            raise AnalysisError("input hash mismatch: " + relative)
    return inventory, actual


def analyze_task(task_dir: Path, input_root: Path):
    trajectory = task_dir / "traj.jsonl"
    rows, invalid, steps = [], [], []
    tokens, source_calls = [], []
    supported = []
    parse_reasons = Counter()
    with trajectory.open(errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                invalid.append({"line": line_number, "error_type": type(exc).__name__})
                tokens.append(None)
                parse_reasons["invalid_json"] += 1
                continue
            rows.append(row)
            steps.append(row.get("step_num"))
            parsed = static_calls(row.get("action"))
            source_calls.append(parsed["source_call_syntax_count"])
            parse_reasons[parsed.get("reason") or "known"] += 1
            if parsed["status"] != "known":
                tokens.append(None)
                continue
            for call in parsed["calls"]:
                call = {"source_line": line_number, "step_num": row.get("step_num"), **call}
                supported.append(call)
                tokens.append(call["category"])

    integer_steps = [value for value in steps if isinstance(value, int) and not isinstance(value, bool)]
    step_info = {
        "missing": sum("step_num" not in row for row in rows),
        "duplicate_value_count": len(integer_steps) - len(set(integer_steps)),
        "descending_adjacent_pairs": sum(right < left for left, right in zip(integer_steps, integer_steps[1:])),
    }
    transitions, segment_counts, segment_actions, segment_lengths = finish_segments(tokens)
    unknown_records = sum(value is None for value in tokens)  # call-level unknown boundaries
    action_unknown_records = sum(key != "known" for key in parse_reasons for _ in range(parse_reasons[key]))
    status = "valid" if supported and not invalid and not action_unknown_records else ("partial" if supported else "unanalysable")
    done = [row.get("done") for row in rows]
    done_true = [index for index, value in enumerate(done) if value is True]
    result = {
        "result_json": safe_result(task_dir / "result.json", "result"),
        "result_txt": safe_result(task_dir / "result.txt", "txt"),
        "checkpoint_results": safe_result(task_dir / "checkpoint_results.json", "checkpoint"),
    }
    return {
        "task_key": task_dir.name,
        "source_file": str(trajectory.relative_to(input_root)),
        "record_count": len(rows),
        "invalid_json_lines": invalid,
        "step_num": step_info,
        "source_call_syntax_count": sum(source_calls),
        "supported_action_call_count": len(supported),
        "unknown_action_record_count": action_unknown_records,
        "unknown_call_boundary_count": unknown_records,
        "parse_reason_counts": dict(sorted(parse_reasons.items())),
        "analysis_status": status,
        "category_counts": dict(sorted(Counter(call["category"] for call in supported).items())),
        "transition_counts": {f"{left}->{right}": count for (left, right), count in sorted(transitions.items())},
        "contiguous_segment_counts": dict(sorted(segment_counts.items())),
        "contiguous_segment_action_counts": dict(sorted(segment_actions.items())),
        "contiguous_segment_length_counts": {f"{category}:{length}": count for (category, length), count in sorted(segment_lengths.items())},
        "action_order_sources": supported,
        "done_counts": dict(Counter(str(value) for value in done)),
        "done_true_record_indexes": done_true,
        "records_after_first_done": max(0, len(rows) - (done_true[0] + 1)) if done_true else 0,
        "reward": reward_summary(rows),
        "results": result,
        "timestamp_semantics": "unknown; not reported as duration",
    }


def _relative(path):
    return str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path)


def run(input_root: Path, inventory_path: Path, output_dir: Path):
    if output_dir.exists():
        raise AnalysisError("output directory exists; refusing overwrite")
    inventory, files = verify_inventory(input_root, inventory_path)
    tasks_root = input_root / "website_demo" / MODEL / "tasks"
    tasks = sorted(path for path in tasks_root.iterdir() if path.is_dir())
    records = [analyze_task(task, input_root) for task in tasks]
    pooled = Counter()
    pooled_transitions = Counter()
    lengths, valid_lengths = [], []
    statuses = Counter()
    for record in records:
        pooled.update(record["category_counts"])
        pooled_transitions.update(record["transition_counts"])
        lengths.append(record["supported_action_call_count"])
        statuses[record["analysis_status"]] += 1
        if record["analysis_status"] == "valid":
            valid_lengths.append(record["supported_action_call_count"])
    per_record_props = []
    for record in records:
        total = sum(record["category_counts"].values())
        if total:
            per_record_props.append({category: record["category_counts"].get(category, 0) / total for category in CATEGORIES if category != "unknown"})
    mean_props = {category: sum(item.get(category, 0) for item in per_record_props) / len(per_record_props) for category in CATEGORIES if category != "unknown"} if per_record_props else {}
    source_total = sum(record["source_call_syntax_count"] for record in records)
    top_source = sorted(records, key=lambda record: (-record["source_call_syntax_count"], record["task_key"]))[:3]
    source_concentration = {
        "top_records": [{"task_key": record["task_key"], "source_call_syntax_count": record["source_call_syntax_count"], "supported_action_call_count": record["supported_action_call_count"], "unknown_action_record_count": record["unknown_action_record_count"]} for record in top_source],
        "top3_share_of_source_call_syntax": (sum(record["source_call_syntax_count"] for record in top_source) / source_total) if source_total else None,
        "source_call_syntax_total": source_total,
    }
    valid_records = [record for record in records if record["analysis_status"] == "valid"]
    ordered = sorted(valid_records, key=lambda record: (record["supported_action_call_count"], record["task_key"]))
    median = quantiles([record["supported_action_call_count"] for record in valid_records])["median"]
    nearest = sorted(valid_records, key=lambda record: (abs(record["supported_action_call_count"] - median), record["task_key"]))[0] if valid_records else None
    representatives = []
    for label, record in [("shortest", ordered[0] if ordered else None), ("median_nearest", nearest), ("longest", ordered[-1] if ordered else None)]:
        if record:
            representatives.append({"selection": label, "task_key": record["task_key"], "supported_action_call_count": record["supported_action_call_count"], "analysis_status": record["analysis_status"], "sequence_preview": [{"line": item["source_line"], "step_num": item["step_num"], "category": item["category"], "call_name": item["call_name"], "column_in_action": item["column_in_action"]} for item in record["action_order_sources"][:12]]})
    summary = {
        "schema": "osworld_minimax_behavior.v2",
        "input": {"root": str(input_root), "model": MODEL, "revision": EXPECTED_REVISION, "task_record_count": len(records)},
        "rules": {
            "action_source": "action field only",
            "source_occurrence_count": "all AST Call nodes, including unsupported or non-executed syntax; not an action count",
            "supported_action_grammar": "module body of direct, non-nested calls to listed pyautogui functions only",
            "unsupported": "function/class definitions, comprehensions, lambda, control flow, nested calls, unknown calls, non-direct statements",
            "static_vs_execution": "supported static order is not proof of GUI execution count; actual execution remains unknown",
            "unknown_boundary": "unsupported/invalid action record breaks adjacency",
            "step_num": "reported, never used for deduplication",
            "time": "not analyzed",
            "result_semantics": "score/reward/done/result fields remain separate; no success label inferred",
        },
        "coverage": {
            "task_records": len(records),
            "status_counts": dict(statuses),
            "records_with_any_supported_action": sum(record["supported_action_call_count"] > 0 for record in records),
            "records_with_no_supported_action": sum(record["supported_action_call_count"] == 0 for record in records),
            "record_count_denominator": "all JSONL records with nonblank lines",
            "sequence_length_denominator": "valid task records only for valid_length_stats; all task records separately retained",
            "valid_length_stats": quantiles(valid_lengths),
            "all_task_supported_action_length_stats": quantiles(lengths),
            "supported_action_count_total": sum(lengths),
            "source_call_syntax_count_total": source_total,
        },
        "pooled_category_counts": dict(sorted(pooled.items())),
        "mean_per_record_category_proportion": mean_props,
        "pooled_transition_counts": dict(sorted(pooled_transitions.items())),
        "source_call_concentration": source_concentration,
        "representative_sequences": representatives,
        "tasks": records,
        "limitations": [
            "dataset-local numeric task keys are not independently mapped to official task definitions",
            "source/supported static calls are not proof of executed GUI effects",
            "result/done/reward/checkpoint are separate fields",
            "no CPU/memory/I/O/usage evidence",
            "timestamp semantics unknown",
            "screenshot paths are not local screenshots",
        ],
    }
    output_dir.mkdir(parents=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    pooled_json = json.dumps(summary["pooled_category_counts"], ensure_ascii=False, sort_keys=True)
    transition_json = json.dumps(summary["pooled_transition_counts"], ensure_ascii=False, sort_keys=True)
    corrections = {
        "v1_errors": [
            "v1 counted only same-category transitions and omitted cross-category transitions",
            "v1 named accumulated run action totals contiguous_known_run_counts rather than segment counts",
            "v1 treated every AST Call found by ast.walk as ordered action evidence, including unsupported structures",
            "v1 classified unknown calls as other and did not retain actual score/reward values",
        ],
        "v2_changes": {
            "status_counts": dict(statuses),
            "source_call_syntax_count_total": source_total,
            "supported_action_count_total": sum(lengths),
            "pooled_category_counts": dict(sorted(pooled.items())),
            "pooled_transition_counts": dict(sorted(pooled_transitions.items())),
        },
        "withdrawn_observations": [
            "v1 valid/partial counts and pooled static counts are not retained as complete-action coverage",
            "v1 other/sequence claims for unsupported or unknown calls are withdrawn",
        ],
        "still_supported": [
            "the fixed MiniMax-M3 local scope and input hashes",
            "descriptive static composition within the explicitly supported grammar",
            "separate done/reward/result evidence without a derived success label",
        ],
        "limits": [
            "actual GUI execution count, timing, resources, and semantic success remain unknown",
            "numeric result values are preserved without assigning task-success meaning",
        ],
    }
    (output_dir / "corrections.md").write_text("# v1→v2 修正记录\n\n```json\n" + json.dumps(corrections, ensure_ascii=False, indent=2, allow_nan=False) + "\n```\n")
    summary_md = [
        "# OSWorld MiniMax-M3 首轮有限行为特征 v2", "",
        f"固定 revision `{EXPECTED_REVISION}` 下分析 {len(records)} 个 dataset-local task key；原始 JSONL 记录分母为 {sum(record['record_count'] for record in records)}。不联网、不执行轨迹。", "",
        "## 统计口径", "",
        "源码调用节点出现次数、支持规则下的静态动作序列、实际 GUI 执行次数分开：第一项包含未支持语法中的 AST Call，第二项只接受顶层直接已知 pyautogui 调用，第三项无法由静态证据证明。Unknown action 记录打断邻接。", "",
        f"状态：{', '.join(f'{key}={value}' for key, value in statuses.items())}；支持规则调用总数 {sum(lengths)}；源码 Call 节点总数 {source_total}。有效任务长度统计：{quantiles(valid_lengths)}。", "",
        "## 分类与转换", "", "```json", pooled_json, "```", "", "转换包括同类和异类，仅发生在可解释相邻动作之间：", "", "```json", transition_json, "```", "", "连续段分别登记段个数、段内动作数和长度分布；连续相同类别不解释为相同操作重复。", "",
        "## 高调用数记录", "", "源码 Call 节点集中度和前三条记录见 summary.json 的 `source_call_concentration`。这些计数可说明源码规模，不能说明实际按键次数、重试、卡顿或低效原因。", "",
        "## 结果字段", "", "result.json 的 score、result.txt 的数值行、checkpoint 的有限评分字段、每条 reward 和 done 分列保留；数值不转换成成功标签，缺失、零值和失败不互换。", "",
        "## 能力边界", "", "可支持有限的静态动作组成、可解释序列和记录结构描述；不支持实际执行次数、动作时间、CPU/内存/I/O、热点、思考时间、因果或类别代表性。", "",
        "代表性序列只从 valid 任务中按支持调用数最短、接近中位数、最长确定选择，并只输出来源行、step、类别和调用名。",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_md) + "\n")
    inputs = []
    for path in [inventory_path] + files:
        size, digest = sha256_file(path)
        inputs.append({"path": _relative(path), "bytes": size, "sha256": digest})
    code = Path(__file__).resolve()
    code_size, code_digest = sha256_file(code)
    outputs = []
    for name in ("summary.json", "summary.md", "corrections.md"):
        size, digest = sha256_file(output_dir / name)
        outputs.append({"path": name, "bytes": size, "sha256": digest})
    manifest = {
        "schema": "osworld_minimax_behavior_manifest.v2",
        "input_root": str(input_root),
        "input_scope": {"model": MODEL, "task_records": len(records), "file_count": len(files)},
        "inputs": inputs,
        "analysis_code": {"path": _relative(code), "bytes": code_size, "sha256": code_digest},
        "outputs": outputs,
        "manifest_self_hash_excluded": True,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.input_root, args.inventory, args.output_dir)
    except AnalysisError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "PASS", "task_records": result["input"]["task_record_count"], "coverage": result["coverage"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
