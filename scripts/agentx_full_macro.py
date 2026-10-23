"""Read-only AgentX Full/256k analysis; never runs requests or trace contents."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "agentx-full-macro-v1"
REQUEST_TYPES = {"s", "n"}
MEASURES = ("in", "out", "api_time", "ttft", "think_time")


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_record(path):
    path = Path(path)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest_file(path)}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def distribution(values):
    valid = sorted(v for v in values if finite(v))
    def q(p):
        if not valid:
            return None
        x = (len(valid) - 1) * p
        lo, hi = math.floor(x), math.ceil(x)
        return valid[lo] + (valid[hi] - valid[lo]) * (x - lo)
    return {"n": len(valid), "missing_or_invalid": len(values) - len(valid),
            "min": q(0), "q1": q(.25), "median": q(.5), "q3": q(.75),
            "p95": q(.95), "max": q(1),
            "iqr": q(.75) - q(.25) if valid else None}


def scoped_intervals(events):
    """Union within ONE session/agent stream, never across sessions or clocks."""
    spans = sorted((e["t"], e["t"] + e["api_time"]) for e in events
                   if finite(e.get("t")) and finite(e.get("api_time"))
                   and e["api_time"] >= 0)
    if not spans:
        return {"valid_intervals": 0, "union_s": None, "span_s": None,
                "overlap_excess_s": None}
    left, right = spans[0]
    union = 0
    for start, end in spans[1:]:
        if start > right:
            union += right - left
            left, right = start, end
        else:
            right = max(right, end)
    union += right - left
    return {"valid_intervals": len(spans), "union_s": union,
            "span_s": max(end for _, end in spans) - spans[0][0],
            "overlap_excess_s": sum(end - start for start, end in spans) - union}


def flatten(trace):
    """Keep native scope paths and multiplicities; group markers are not requests."""
    if not isinstance(trace, dict) or not isinstance(trace.get("id"), str):
        raise ValueError("invalid trace identity")
    if not isinstance(trace.get("requests"), list):
        raise ValueError("requests must be a list")
    scopes = defaultdict(list)
    groups, errors = [], []
    seen_groups = set()
    def walk(items, scope):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({"scope": list(scope), "index": index, "kind": "non_object"})
                continue
            if item.get("type") == "subagent":
                aid = item.get("agent_id")
                if not isinstance(aid, str) or not aid:
                    errors.append({"kind": "missing_agent_id", "scope": list(scope), "index": index})
                    aid = f"unknown-index-{index}"
                child = scope + (aid,)
                if child in seen_groups:
                    errors.append({"kind": "duplicate_agent_scope", "scope": list(child)})
                seen_groups.add(child)
                groups.append({k: v for k, v in item.items() if k != "requests"})
                nested = item.get("requests")
                if not isinstance(nested, list):
                    errors.append({"kind": "invalid_nested_requests", "scope": list(child)})
                else:
                    walk(nested, child)
            elif item.get("type") in REQUEST_TYPES:
                scopes[scope].append(item)
            else:
                errors.append({"kind": "unknown_request_type", "type": item.get("type"),
                               "scope": list(scope), "index": index})
    scopes[()] = []
    walk(trace["requests"], ())
    return scopes, groups, errors


def payload_digest(event):
    # The cap may shift every surviving timestamp by one uniform session offset.
    # All remaining fields, including hash IDs, are required to match exactly.
    payload = {k: v for k, v in event.items() if k != "t"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def scan(path):
    per_trace, signatures, errors = [], {}, []
    values = {name: [] for name in MEASURES}
    models, types, leaf_fields, group_fields = Counter(), Counter(), Counter(), Counter()
    group_nonnull, group_status = Counter(), Counter()
    group_values = {k: [] for k in ("duration_ms", "total_tokens", "tool_use_count")}
    main_count = inner_count = group_count = above_cap = at_cap = 0
    total_input = total_output = 0
    input_invalid = output_invalid = 0
    gaps, negative_gaps = [], 0
    hash_context_mismatches = hash_context_checked = 0
    prefix_pairs = prefix_shared_blocks = 0
    prefix_shared_per_pair = []
    with Path(path).open() as stream:
        for line_no, line in enumerate(stream, 1):
            try:
                raw = json.loads(line)
                scopes, groups, local_errors = flatten(raw)
            except (ValueError, TypeError) as exc:
                errors.append({"line": line_no, "kind": type(exc).__name__})
                continue
            tid = raw["id"]
            if tid in signatures:
                raise ValueError(f"duplicate trace identity at line {line_no}")
            errors.extend({"line": line_no, **e} for e in local_errors)
            signature = defaultdict(list)
            row_values = {name: [] for name in MEASURES}
            scope_metrics = []
            trace_above_cap = 0
            trace_input = trace_output = 0
            for scope, events in scopes.items():
                interval = scoped_intervals(events)
                backwards = sum(1 for a, b in zip(events, events[1:])
                                if finite(a.get("t")) and finite(b.get("t")) and b["t"] < a["t"])
                scope_metrics.append({"agent_path": list(scope), "requests": len(events),
                                      "intervals": interval, "timestamp_backwards_pairs": backwards})
                if scope:
                    inner_count += len(events)
                else:
                    main_count += len(events)
                for a, b in zip(events, events[1:]):
                    if all(finite(v) for v in (a.get("t"), b.get("t"), a.get("api_time"))):
                        gap = b["t"] - (a["t"] + a["api_time"])
                        gaps.append(gap)
                        negative_gaps += gap < 0
                    ah, bh = a.get("hash_ids"), b.get("hash_ids")
                    if isinstance(ah, list) and isinstance(bh, list):
                        shared = 0
                        for x, y in zip(ah, bh):
                            if x != y:
                                break
                            shared += 1
                        prefix_pairs += 1
                        prefix_shared_blocks += shared
                        prefix_shared_per_pair.append(shared)
                for event in events:
                    signature[(scope, payload_digest(event))].append(event.get("t"))
                    types[str(event.get("type"))] += 1
                    models[str(event.get("model"))] += 1
                    leaf_fields.update(event.keys())
                    for name in MEASURES:
                        v = event.get(name)
                        values[name].append(v if finite(v) and v >= 0 else None)
                        row_values[name].append(v if finite(v) and v >= 0 else None)
                    inp, out = event.get("in"), event.get("out")
                    if finite(inp) and inp >= 0:
                        total_input += inp
                        trace_input += inp
                    else:
                        input_invalid += 1
                    if finite(out) and out >= 0:
                        total_output += out
                        trace_output += out
                    else:
                        output_invalid += 1
                    if finite(inp) and finite(out) and inp >= 0 and out >= 0:
                        trace_above_cap += inp + out > 256000
                        at_cap += inp + out == 256000
                    hashes, block = event.get("hash_ids"), raw.get("block_size")
                    if isinstance(hashes, list) and finite(block) and finite(inp):
                        hash_context_checked += 1
                        hash_context_mismatches += len(hashes) * block != inp
            for group in groups:
                group_fields.update(group.keys())
                group_nonnull.update(k for k, v in group.items() if v is not None)
                group_status[str(group.get("status"))] += 1
                for name in group_values:
                    value = group.get(name)
                    group_values[name].append(value if finite(value) and value >= 0 else None)
            above_cap += trace_above_cap
            group_count += len(groups)
            signatures[tid] = signature
            per_trace.append({"trace_id": tid, "source_line": line_no,
                              "main_requests": len(scopes[()]),
                              "subagent_requests": sum(len(e) for s, e in scopes.items() if s),
                              "model_requests": sum(map(len, scopes.values())),
                              "subagent_groups": len(groups), "requests_above_256k_cap": trace_above_cap,
                              "input_sum": trace_input, "output_sum": trace_output,
                              "hash_id_scope": raw.get("hash_id_scope"), "block_size": raw.get("block_size"),
                              "request_distributions": {k: distribution(v) for k, v in row_values.items()},
                              "scopes": scope_metrics, "errors": local_errors})
    summary = {"trace_count": len(per_trace), "main_request_count": main_count,
               "subagent_inner_request_count": inner_count, "total_model_request_count": main_count + inner_count,
               "subagent_group_count": group_count,
               "sessions_with_subagents": sum(r["subagent_groups"] > 0 for r in per_trace),
               "total_input_tokens_reconstructed": total_input, "total_output_tokens": total_output,
               "input_missing_or_invalid": input_invalid, "output_missing_or_invalid": output_invalid,
               "requests_above_256k_input_plus_output": above_cap,
               "requests_at_256k_input_plus_output": at_cap,
               "models_as_saved": dict(models), "request_types": dict(types),
               "request_field_presence": dict(leaf_fields), "group_field_presence": dict(group_fields),
               "group_nonnull_fields": dict(group_nonnull), "group_status_as_saved": dict(group_status),
               "group_field_distributions": {k: distribution(v) for k, v in group_values.items()},
               "per_session_group_count": distribution([r["subagent_groups"] for r in per_trace]),
               "request_distributions": {k: distribution(v) for k, v in values.items()},
               "per_session_request_count": distribution([r["model_requests"] for r in per_trace]),
               "main_stream_observed_span_s": distribution([r["scopes"][0]["intervals"]["span_s"] for r in per_trace]),
               "recorded_adjacent_stream_gap_s": distribution(gaps), "negative_gap_pairs": negative_gaps,
               "hash_input_check": {"checked": hash_context_checked, "mismatches": hash_context_mismatches},
               "same_stream_prefix": {"adjacent_comparisons": prefix_pairs,
                                      "shared_prefix_blocks_sum": prefix_shared_blocks,
                                      "shared_blocks_per_pair": distribution(prefix_shared_per_pair)},
               "errors": errors}
    return summary, per_trace, signatures, values


def compare_signatures(full, capped):
    per_trace = []
    for tid in sorted(full.keys() | capped.keys()):
        a, b = full.get(tid, {}), capped.get(tid, {})
        ac = Counter({k: len(v) for k, v in a.items()})
        bc = Counter({k: len(v) for k, v in b.items()})
        offsets = []
        ambiguous = 0
        for key in a.keys() & b.keys():
            if len(a[key]) == len(b[key]) == 1:
                x, y = a[key][0], b[key][0]
                if finite(x) and finite(y):
                    offsets.append(x - y)
            else:
                ambiguous += min(len(a[key]), len(b[key]))
        uniform = bool(offsets) and max(offsets) - min(offsets) < 1e-6
        per_trace.append({"trace_id": tid, "full_present": tid in full, "capped_present": tid in capped,
                          "full_requests": ac.total(), "capped_requests": bc.total(),
                          "matched_payloads": (ac & bc).total(),
                          "full_only_payloads": (ac - bc).total(),
                          "capped_only_payloads": (bc - ac).total(),
                          "unique_payload_timestamp_pairs": len(offsets), "ambiguous_pairs_unassigned": ambiguous,
                          "uniform_session_offset": uniform,
                          "full_minus_capped_t_s": offsets[0] if uniform else None})
    return {"match_rule": "same session + native agent path + SHA256(all request fields except t); multiplicity preserved",
            "timestamp_rule": "unique payload matches only; check uniform per-session offset to 1e-6 seconds; ambiguous pairs not assigned",
            "shared_session_ids": len(full.keys() & capped.keys()),
            "full_only_session_ids": sorted(full.keys() - capped.keys()),
            "capped_only_session_ids": sorted(capped.keys() - full.keys()),
            "matched_payloads": sum(r["matched_payloads"] for r in per_trace),
            "full_only_payloads": sum(r["full_only_payloads"] for r in per_trace),
            "capped_only_payloads": sum(r["capped_only_payloads"] for r in per_trace),
            "sessions_with_uniform_offset": sum(r["uniform_session_offset"] for r in per_trace),
            "sessions_with_nonzero_offset": sum(r["uniform_session_offset"] and abs(r["full_minus_capped_t_s"]) > 1e-6 for r in per_trace),
            "per_trace": per_trace}


def declared_stats(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            try:
                out[key.strip()] = int(value.strip().replace(",", ""))
            except ValueError:
                pass
    return out


def validate_declared(summary, declared):
    mapping = {"traces": "trace_count", "main_turns": "main_request_count",
               "subagent_groups": "subagent_group_count", "subagent_inner_requests": "subagent_inner_request_count",
               "total_model_requests": "total_model_request_count",
               "total_input_tokens": "total_input_tokens_reconstructed", "total_output_tokens": "total_output_tokens"}
    return [{"field": source, "declared": declared[source], "observed": summary[target],
             "matches": declared[source] == summary[target]} for source, target in mapping.items() if source in declared]


def create_figure(full_values, cap_values, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), constrained_layout=True)
    for ax, field, label in zip(axes, ("in", "out", "api_time"),
                               ("Reconstructed input tokens", "Output tokens", "Recorded API interval (s)")):
        combined = [v for x in (full_values, cap_values) for v in x[field] if finite(v) and v > 0]
        bins = np.geomspace(min(combined), max(combined), 45)
        for name, values, color in (("Full", full_values, "#2563eb"), ("256k", cap_values, "#d97706")):
            all_valid = [v for v in values[field] if finite(v)]
            positive = [v for v in all_valid if v > 0]
            weights = np.ones(len(positive)) / len(all_valid) * 100
            ax.hist(positive, bins=bins, weights=weights, histtype="step", label=f"{name} (n={len(all_valid):,})", color=color)
        ax.set_xscale("log")
        ax.set_xlabel(label)
        ax.set_ylabel("Requests per bin / all valid requests (%)")
        ax.legend(fontsize=8)
        ax.grid(alpha=.15)
        zeros = [sum(v == 0 for v in x[field] if finite(v)) for x in (full_values, cap_values)]
        ax.set_title(f"Zero values off log axis: Full {zeros[0]}, 256k {zeros[1]}", fontsize=9)
    fig.suptitle("AgentX v1.0: two overlapping variants of the same sessions")
    fig.savefig(out / "full-vs-256k.svg")
    fig.savefig(out / "full-vs-256k.png", dpi=160)
    plt.close(fig)


def write_report(full, capped, acquisition, out, plots=True):
    full, capped, acquisition, out = map(Path, (full, capped, acquisition, out))
    if out.exists():
        raise FileExistsError(out)
    if any(out.resolve().is_relative_to(p.resolve()) or p.resolve().is_relative_to(out.resolve())
           for p in (full, capped)):
        raise ValueError("input/output overlap")
    acq = json.loads(acquisition.read_text())
    verification = []
    for entry in acq["files"]:
        record = file_record(entry["path"])
        if any(record[k] != entry[k] for k in ("bytes", "sha256")):
            raise ValueError(f"acquisition evidence mismatch: {entry['path']}")
        verification.append(record)
    if str(full) not in {x["path"] for x in verification}:
        raise ValueError("Full JSONL not bound by acquisition")
    baseline_manifest = Path("reports/analysis/AGENTX-APPLIED-MACRO-v1/manifest.json")
    expected = next(x for x in json.loads(baseline_manifest.read_text())["inputs"] if x["path"] == str(capped))
    baseline_record = file_record(capped)
    if any(baseline_record[k] != expected[k] for k in ("bytes", "sha256")):
        raise ValueError("256k frozen input mismatch")
    print("Verified inputs; scanning 256k", flush=True)
    cs, cr, ci, cv = scan(capped)
    print("Scanning Full", flush=True)
    fs, fr, fi, fv = scan(full)
    comparison = compare_signatures(fi, ci)
    full_check = validate_declared(fs, declared_stats(full.parent / "stats.txt"))
    cap_check = validate_declared(cs, declared_stats(capped.parent / "stats.txt"))
    cap_rule = (fs["total_model_request_count"] - fs["requests_above_256k_input_plus_output"] == cs["total_model_request_count"])
    comparison_ok = (not comparison["capped_only_payloads"] and not comparison["full_only_session_ids"]
                     and not comparison["capped_only_session_ids"] and cap_rule
                     and comparison["sessions_with_uniform_offset"] == comparison["shared_session_ids"])
    status = "PASS" if (not fs["errors"] and not cs["errors"] and comparison_ok
                        and all(x["matches"] for x in full_check + cap_check)) else "PARTIAL"
    summary = {"schema": SCHEMA, "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": status, "full": fs, "capped_256k": cs,
               "source_declared_validation": {"full": full_check, "capped_256k": cap_check},
               "cap_rule_count_matches": cap_rule,
               "cross_variant_validation": "PASS" if comparison_ok else "PARTIAL",
               "comparison": {k: v for k, v in comparison.items() if k != "per_trace"},
               "semantics": {
                   "in": "reconstructed 64-token hash-block count, not exact tokenizer count or billing",
                   "time": "source-relative t; union/gap computed inside individual session+agent stream only; no cross-session/parent-child time union",
                   "gaps": "adjacent saved request interval gaps; not identified tool latency or thinking time; negative values retained",
                   "matching": comparison["match_rule"],
                   "prefix": "adjacent saved requests inside the same session+agent stream only; shared hash blocks are not measured cache hits or savings",
                   "group_fields": "saved duration_ms/total_tokens/tool_use_count; distributions only, not added to leaf request totals or interpreted as business execution",
                   "unknowns": ["business tool names/arguments/results", "task outcome", "local CPU/memory/IO/network", "billable cost", "provider inference time"],
                   "cohort": "same selected opt-in sessions; overlapping variants, not independent populations or all production sessions"}}
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (out / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n")
    with (out / "per_trace.jsonl").open("w") as stream:
        for variant, rows in (("full", fr), ("256k", cr)):
            for row in rows:
                stream.write(json.dumps({"variant": variant, **row}, ensure_ascii=False, separators=(",", ":")) + "\n")
    with (out / "per_trace_comparison.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparison["per_trace"][0]))
        writer.writeheader()
        writer.writerows(comparison["per_trace"])
    if plots:
        create_figure(fv, cv, out)
    count_delta = fs["total_model_request_count"] - cs["total_model_request_count"]
    ratio = count_delta / fs["total_model_request_count"] * 100
    md = ["# AgentX v1.0 Full：宏观分析及与256k版本对照", "",
          f"生成：{summary['created_at_utc']}；验收：{status}。离线只读全部本地JSONL，不执行轨迹、Agent、工具或模型。", "",
          "## 来源和覆盖", "",
          f"- Full：`{acq['dataset_id']}`，固定revision `{acq['revision']}`，Apache-2.0（数据卡声明）。",
          "- 256k：沿用旧分析manifest绑定的revision `8fecd2fc56694469f758f0afbbb6335ad3043740`；本轮重新扫描实际原始记录。",
          "- Full不是原始业务日志全集：仍是经过版本、请求数、并发、图像、分类器和去重等规则筛选的公开请求流；Full保留更长上下文。", "",
          "| 指标 | Full | 256k |", "|---|---:|---:|"]
    for label, key in (("会话", "trace_count"), ("主Agent请求", "main_request_count"),
                       ("Subagent内部请求", "subagent_inner_request_count"), ("全部模型请求", "total_model_request_count"),
                       ("Subagent group", "subagent_group_count"), ("含Subagent的会话", "sessions_with_subagents"),
                       ("重建输入总量", "total_input_tokens_reconstructed"), ("输出token总量", "total_output_tokens")):
        md.append(f"| {label} | {fs[key]:,} | {cs[key]:,} |")
    md += ["", "## 实际字段分布", "", "分位数按(n−1)×p线性插值；每个字段有自己的有效n。不同variant不能合并分母。", "",
           "| 字段 | Full有效n / median / p95 | 256k有效n / median / p95 |", "|---|---|---|"]
    for name in MEASURES:
        a, b = fs["request_distributions"][name], cs["request_distributions"][name]
        md.append(f"| {name} | {a['n']:,} / {a['median']} / {a['p95']} | {b['n']:,} / {b['median']} / {b['p95']} |")
    md += ["", "`in`来自hash块数×64，既不是精确分词器计数，也不是实际计费输入；总量与分布均保留该限制。`api_time`、`ttft`和`think_time`仅按来源保存字段统计，不能解释为远端纯推理、真实业务工具或用户思考耗时。", "",
           "## 两版本关系与cap影响", "",
           f"- Full较256k多{count_delta:,}个请求；按Full请求数分母，差值为{ratio:.3f}%。两者共有{comparison['shared_session_ids']}个会话ID；各自独有ID见comparison.json。",
           f"- 按会话+原生agent路径+除t以外全部请求payload的SHA-256匹配（保留重复次数）：匹配{comparison['matched_payloads']:,}；Full独有{comparison['full_only_payloads']:,}；256k独有{comparison['capped_only_payloads']:,}。不按位置或仅token长度强配。",
           f"- 唯一payload匹配中，{comparison['sessions_with_uniform_offset']}个会话满足统一时间偏移，其中{comparison['sessions_with_nonzero_offset']}个存在非零偏移；歧义请求不配时间。",
           f"- Full中input+output>256,000的请求为{fs['requests_above_256k_input_plus_output']:,}；按该cap的保留总数与256k相等：{cap_rule}。边界恰为256,000的Full请求为{fs['requests_at_256k_input_plus_output']:,}。",
           "- cap作用于请求；部分Subagent内部请求可能被移除，保留group数量相同不代表内部请求完整。Full本身另有约990k重建输入上限，不是无过滤原始代理全集。", "",
           "## Subagent与前缀结构", "",
           f"Full含Subagent的会话{fs['sessions_with_subagents']}/{fs['trace_count']}；group状态仅按保存标签统计：`{json.dumps(fs['group_status_as_saved'], ensure_ascii=False)}`，不转换为任务成功率。",
           f"保存group duration_ms的median={fs['group_field_distributions']['duration_ms']['median']}；group total_tokens仅单独分布，不与叶子请求token总量相加。",
           f"同一会话/agent stream内相邻hash前缀比较：Full {fs['same_stream_prefix']['adjacent_comparisons']:,}对、256k {cs['same_stream_prefix']['adjacent_comparisons']:,}对；共享block数的median分别为{fs['same_stream_prefix']['shared_blocks_per_pair']['median']}和{cs['same_stream_prefix']['shared_blocks_per_pair']['median']}。cap移除中间请求后相邻关系改变，不将两者差异解释为缓存命中率或性能收益。", "",
           "## 业务工具与资源分析边界", "",
           "发布方methodology明确公开语料不含原始prompt、代码、工具参数或工具返回。实际请求/group字段出现次数和非空次数见summary.json；不能从工具调用间隔或group状态补推业务操作、成功率与工具独占成本。",
           f"本地Full的group.tool_use_count非空{fs['group_nonnull_fields'].get('tool_use_count', 0)}/{fs['subagent_group_count']}；即使有聚合数，也不提供具体工具身份/参数/结果。",
           "没有本地CPU、内存、I/O、网络或任务结果测量。不能从Full恢复这些字段，也不进行性能、模型能力或费用排名。", "",
           "## 核验与产物", "",
           f"输入哈希已核验；Full/256k分别{len(full_check)}/{len(cap_check)}个来源stats字段逐项重算，详情见summary.json。解析/结构问题Full={len(fs['errors'])}，256k={len(cs['errors'])}。",
           "逐会话/agent scope分别统计时间区间，绝不把不同会话的相对时钟拼成统一时间线；跨scope并集、工具耗时与等待/思考时间不推断。旧分析报告与代码不改写。", "",
           "- [逐trace明细](per_trace.jsonl) · [逐会话对照](per_trace_comparison.csv) · [机器摘要](summary.json) · [匹配详情](comparison.json) · [manifest](manifest.json)"]
    if plots:
        md += ["- [分布图SVG](full-vs-256k.svg) · [PNG](full-vs-256k.png)", "", "![请求字段分布](full-vs-256k.png)"]
    md += ["", "来源：[Full固定版本](https://huggingface.co/datasets/" + acq["dataset_id"] + "/tree/" + acq["revision"] + ")；[官方methodology](https://inferencex.semianalysis.com/agentx/methodology)。"]
    (out / "summary.md").write_text("\n".join(md) + "\n")
    inputs = verification + [baseline_record, file_record(baseline_manifest), file_record(acquisition),
                             file_record(capped.parent / "stats.txt"), file_record(capped.parent / "README.md")]
    manifest = {"schema": SCHEMA + "-manifest", "inputs": inputs,
                "analyzer": file_record(Path(__file__)),
                "tests": file_record(Path("tests/test_agentx_full_macro.py")),
                "outputs": [file_record(p) for p in sorted(out.iterdir()) if p.is_file()],
                "manifest_self_hash": "excluded", "execution": "offline file analysis only"}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": status, "full_requests": fs["total_model_request_count"],
                      "capped_requests": cs["total_model_request_count"], "report": str(out / 'summary.md')}), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", required=True, type=Path)
    parser.add_argument("--capped", required=True, type=Path)
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary = write_report(args.full, args.capped, args.acquisition, args.output_dir)
    return int(summary["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
