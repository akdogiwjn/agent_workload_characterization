#!/usr/bin/env python3
"""Supplement the frozen v2 report with per-JSONL-record source statistics."""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path

import osworld_minimax_behavior as behavior


def record_structure(action):
    tree = ast.parse(action)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    statements = [ast.dump(node, include_attributes=False) for node in tree.body]
    frequencies = Counter(statements)
    longest = current = 0
    previous = None
    for statement in statements:
        current = current + 1 if statement == previous else 1
        longest = max(longest, current)
        previous = statement
    # Statement contents/arguments are deliberately not exported.
    return {
        "action_characters": len(action),
        "ast_call_count": len(calls),
        "call_names": dict(sorted(Counter(behavior.call_name(n) for n in calls).items())),
        "top_level_statement_count": len(tree.body),
        "top_level_statement_types": dict(Counter(type(n).__name__ for n in tree.body)),
        "all_statements_direct_calls": bool(tree.body) and all(
            isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) for n in tree.body),
        "distinct_statement_ast_count": len(frequencies),
        "max_identical_statement_occurrences": max(frequencies.values(), default=0),
        "max_consecutive_identical_statements": longest,
    }


def scan_records(paths, root):
    candidates = []
    total = records = unparsed = 0
    for path in sorted(paths):
        with path.open() as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                records += 1
                action = row.get("action")
                try:
                    tree = ast.parse(action) if isinstance(action, str) else None
                except SyntaxError:
                    tree = None
                if tree is None:
                    unparsed += 1
                    continue
                count = sum(isinstance(n, ast.Call) for n in ast.walk(tree))
                total += count
                if count:
                    candidates.append((count, path.parent.name, line_number, path, row))
                    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
                    del candidates[3:]
    top = [{"task_key": task, "jsonl_line": line, "step_num": row.get("step_num"),
            "source_file": str(path.relative_to(root)), **record_structure(row["action"])}
           for _, task, line, path, row in candidates]
    return {"jsonl_record_count": records, "unparsed_action_records": unparsed,
            "parsed_source_ast_call_total": total, "top_jsonl_records": top,
            "top3_jsonl_share": sum(r["ast_call_count"] for r in top) / total if total else None}


def run(root, inventory, v2, output):
    if output.exists():
        raise ValueError("output exists; refusing overwrite")
    _, files = behavior.verify_inventory(root, inventory)
    manifest = json.loads((v2 / "manifest.json").read_text())
    protected = [(behavior.PROJECT_ROOT / r["path"], r) for r in manifest["inputs"]]
    protected += [(v2 / r["path"], r) for r in manifest["outputs"]]
    protected.append((behavior.PROJECT_ROOT / manifest["analysis_code"]["path"], manifest["analysis_code"]))
    v2_manifest_before = behavior.sha256_file(v2 / "manifest.json")

    def verify_protected():
        for path, entry in protected:
            if behavior.sha256_file(path) != (entry["bytes"], entry["sha256"]):
                raise ValueError("protected file hash mismatch: " + str(path))
        if behavior.sha256_file(v2 / "manifest.json") != v2_manifest_before:
            raise ValueError("v2 manifest changed")

    verify_protected()
    result = scan_records([p for p in files if p.name == "traj.jsonl"], root)
    old = json.loads((v2 / "summary.json").read_text())
    assert result["parsed_source_ast_call_total"] == old["coverage"]["source_call_syntax_count_total"]
    result["v2_task_level_concentration"] = old["source_call_concentration"]
    result["correction"] = "v2 top_records are whole task trajectories, not individual JSONL action records."
    result["limits"] = "AST/source occurrences only; execution, retry, latency and origin of repetition remain unknown."
    verify_protected()
    lines = ["# MiniMax-M3 v2 高调用数补充核验", "",
             "v2 的前三条记录集中度实际按完整 task 轨迹累计，应称为“前三个 task 的源码调用集中度”；不是三条 JSONL action 的集中度。原 v2 保持不变，本说明纠正该口径。", "",
             f"本次按 JSONL 单行排序：解析到的 AST Call 总数 {result['parsed_source_ast_call_total']:,}；前三行占比 {result['top3_jsonl_share']:.4%}。语法不可解析/非字符串 action 共 {result['unparsed_action_records']} 条，不给它们猜测调用数。", "",
             "| task | JSONL 行 | AST 调用数 | 顶层语句数 | 不同语句 AST 数 | 最长连续相同语句 |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in result["top_jsonl_records"]:
        lines.append(f"| {row['task_key']} | {row['jsonl_line']} | {row['ast_call_count']} | {row['top_level_statement_count']} | {row['distinct_statement_ast_count']} | {row['max_consecutive_identical_statements']} |")
    lines += ["", "调用名、语句结构与定位见 supplement.json。相同语句按包含参数但不含源码位置的 AST 比较；不输出参数。代码中的重复不证明重复执行、重试、卡顿或低效，也不能确认重复源码的形成原因。", "",
              "本次只补充单行源码结构，不改变 v2 的分类、终止/评分解释或资源分析边界。"]
    output.mkdir(parents=True)
    (output / "supplement.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (output / "summary.md").write_text("\n".join(lines) + "\n")

    def entry(path):
        size, digest = behavior.sha256_file(path)
        return {"path": str(path.resolve()), "bytes": size, "sha256": digest}

    receipt = {"inputs": [entry(p) for p in [inventory, v2 / "manifest.json", v2 / "summary.json"] + files],
               "code": [entry(Path(__file__)), entry(Path(behavior.__file__))],
               "outputs": [entry(output / name) for name in ("supplement.json", "summary.md")],
               "protected_v2_entries_verified_before_and_after": len(protected),
               "manifest_self_hash_excluded": True}
    (output / "manifest.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "inventory", "v2", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.inventory, args.v2, args.output)
    print(json.dumps({"top_jsonl_records": result["top_jsonl_records"], "top3_share": result["top3_jsonl_share"]}))
