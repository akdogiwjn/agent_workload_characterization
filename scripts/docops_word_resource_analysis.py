#!/usr/bin/env python3
"""Offline, narrowly scoped analysis of the archived DOCOPS-03/04 runs."""
from __future__ import annotations

import hashlib
import ast
import json
import re
import statistics
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}
RUNS = (
    ("DOCOPS-WORD-RESOURCE-03", "20261010T105013Z-word001", "03"),
    ("DOCOPS-WORD-RESOURCE-04", "20261010T110820Z-word001", "04"),
)
TASK_REL = "references/repos/DocOps/tasks/atomic__word_001_engineering_report_toc_hierarchy_seed"
OUT_REL = "reports/analysis/DOCOPS-WORD-RESOURCE-03-04-review-v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_record(root: Path, path: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _manifest_check(root: Path, run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    missing, mismatched = [], []
    for item in manifest.get("outputs", []):
        path = run_dir / item["path"]
        if not path.is_file():
            missing.append(item["path"])
        elif path.stat().st_size != item.get("bytes") or sha256(path) != item.get("sha256"):
            mismatched.append(item["path"])
    task_dir = root / TASK_REL
    input_mismatch, input_missing = [], []
    input_map = {
        "task.toml": task_dir / "task.toml",
        "instruction.md": task_dir / "instruction.md",
        "environment/task_metadata.json": task_dir / "environment/task_metadata.json",
        "input.docx": task_dir / "environment/word_001_engineering_report_toc_hierarchy_seed.docx",
    }
    for item in manifest.get("inputs", []):
        path = input_map.get(item["path"])
        if path is None or not path.is_file():
            input_missing.append(item["path"])
        elif sha256(path) != item.get("sha256"):
            input_mismatch.append(item["path"])
    return {
        "outputs_declared": len(manifest.get("outputs", [])),
        "outputs_verified": len(manifest.get("outputs", [])) - len(missing) - len(mismatched),
        "output_missing": missing,
        "output_mismatched": mismatched,
        "inputs_declared": len(manifest.get("inputs", [])),
        "input_missing": input_missing,
        "input_mismatched": input_mismatch,
        "passed": not (missing or mismatched or input_missing or input_mismatch),
    }


def _tool_category(name: str | None) -> str:
    return {
        "copy_file": "file_copy",
        "inspect_document": "document_structure_inspection",
        "word_inspect_format": "format_inspection",
        "word_replace_text": "text_edit",
        "word_set_format": "format_edit",
    }.get(name or "", "unknown_or_other")


def _extract_action(call: dict[str, Any]) -> dict[str, Any]:
    try:
        response = json.loads(call.get("original_response") or "{}")
        content = response["choices"][0]["message"]["content"]
        action = json.loads(content)
        if not isinstance(action, dict):
            raise ValueError("action is not object")
        return {"action": action, "response_model": response.get("model"), "parse_status": "parsed"}
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return {"action": None, "response_model": None, "parse_status": "unparseable_or_missing"}


def _safe_arguments(tool: str | None, args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {"status": "unknown_non_object"}
    result: dict[str, Any] = {"field_names": sorted(args)}
    if tool in {"copy_file", "inspect_document", "word_inspect_format", "word_replace_text", "word_set_format"}:
        if isinstance(args.get("path"), str):
            result["path_basename"] = Path(args["path"]).name
        if isinstance(args.get("src"), str):
            result["src_basename"] = Path(args["src"]).name
        if isinstance(args.get("dest"), str):
            result["dest_basename"] = Path(args["dest"]).name
        for key in ("paragraph_index", "max_items"):
            if isinstance(args.get(key), int) and not isinstance(args.get(key), bool):
                result[key] = args[key]
        if isinstance(args.get("style_name"), str):
            result["style_name"] = args["style_name"]
        fmt = args.get("format")
        if isinstance(fmt, dict):
            result["format_fields"] = sorted(fmt)
            result["direct_format_values"] = {
                k: fmt[k] for k in ("font_name", "font_size", "bold", "italic", "color", "alignment")
                if k in fmt and isinstance(fmt[k], (str, int, float, bool, type(None)))
            }
        replacements = args.get("replacements")
        if isinstance(replacements, list):
            result["replacement_count"] = len(replacements)
            replacement_summaries = []
            for item in replacements:
                if not isinstance(item, dict):
                    replacement_summaries.append({"status": "unknown_non_object"})
                    continue
                item_summary = {}
                for out_key, source_keys in (("old", ("old", "old_text")), ("new", ("new", "new_text"))):
                    value = next((item[k] for k in source_keys if isinstance(item.get(k), str)), None)
                    if value is not None:
                        item_summary[out_key] = {"chars": len(value), "sha256": hashlib.sha256(value.encode()).hexdigest()}
                replacement_summaries.append(item_summary)
            result["replacement_summaries"] = replacement_summaries
        for key in ("old_text", "new_text", "text", "replacement"):
            if key in args:
                value = args[key]
                result[key + "_present"] = value is not None
                if isinstance(value, str):
                    result[key + "_chars"] = len(value)
                    result[key + "_sha256"] = hashlib.sha256(value.encode()).hexdigest()
    return result


def _action_history(run_dir: Path, n_calls: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    calls = []
    response_models = Counter()
    for index in range(1, n_calls + 1):
        path = run_dir / "agent" / f"llm_call_{index}.json"
        if not path.is_file():
            calls.append({"call_index": index, "action": "unknown", "parse_status": "call_log_missing"})
            continue
        log = load_json(path)
        extracted = _extract_action(log)
        action = extracted["action"]
        response_model = extracted["response_model"]
        if response_model:
            response_models[response_model] += 1
        if action is None:
            calls.append({"call_index": index, "action": "invalid_or_unknown", "response_model": response_model,
                          "parse_status": extracted["parse_status"], "request_model": log.get("model")})
        else:
            tool = action.get("tool_name") if action.get("action") == "call_tool" else None
            calls.append({
                "call_index": index,
                "action": action.get("action") if action.get("action") in {"call_tool", "finish"} else "invalid_or_unknown",
                "tool_name": tool,
                "activity_category": _tool_category(tool) if tool else ("finish" if action.get("action") == "finish" else "unknown_or_other"),
                "arguments": _safe_arguments(tool, action.get("arguments")),
                "request_model": (f"{log.get('custom_llm_provider')}/{log.get('model')}"
                                  if log.get("custom_llm_provider") and log.get("model") else log.get("model")),
                "response_model": response_model,
                "parse_status": extracted["parse_status"],
                "return_status": "pending_history_check",
            })

    # The frozen DocOps harness appends the tool-result message immediately after
    # the assistant action. Read the latest saved conversation history, never pair
    # by equal counts or by call index alone.
    last_log = run_dir / "agent" / f"llm_call_{n_calls}.json"
    if last_log.is_file():
        messages = load_json(last_log).get("messages", [])
        for i, message in enumerate(messages):
            if message.get("role") != "assistant" or not isinstance(message.get("content"), str):
                continue
            try:
                payload = json.loads(message["content"])
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("action") != "call_tool":
                continue
            tool = payload.get("tool_name")
            following = messages[i + 1] if i + 1 < len(messages) else {}
            content = following.get("content") if following.get("role") == "user" else None
            prefix = f"Tool result for {tool}:\n"
            if not isinstance(content, str) or not content.startswith(prefix):
                continue
            try:
                result = json.loads(content[len(prefix):].split("\nDecide the next action.", 1)[0])
                status = "ok_true" if isinstance(result, dict) and result.get("ok") is True else (
                    "ok_false" if isinstance(result, dict) and result.get("ok") is False else "present_status_unknown")
            except (ValueError, TypeError):
                status = "present_unparsed"
            # Match the action payload and history occurrence explicitly; duplicate
            # tool calls remain separate by message position, not by tool name.
            candidates = [c for c in calls if c.get("action") == "call_tool" and c.get("tool_name") == tool
                          and c.get("return_status") == "pending_history_check"]
            if candidates:
                candidates[0]["return_status"] = status
                candidates[0]["return_evidence"] = "immediately_following_tool_result_message_in_saved_request_history"
    for call in calls:
        if call.get("return_status") == "pending_history_check":
            call["return_status"] = "unknown_not_persisted_or_not_linkable"
    return calls, {"response_model_counts": dict(response_models), "logged_request_model": calls[0].get("request_model") if calls else None}


def _docx_paragraphs(path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        styles_root = ET.fromstring(archive.read("word/styles.xml")) if "word/styles.xml" in archive.namelist() else None
    style_names = {}
    if styles_root is not None:
        for style in styles_root.findall("w:style", NS):
            sid = style.get(f"{{{NS['w']}}}styleId")
            name_el = style.find("w:name", NS)
            if sid:
                style_names[sid] = name_el.get(f"{{{NS['w']}}}val") if name_el is not None else sid
    paragraphs = []
    def direct_properties(parent: ET.Element | None) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        if parent is None:
            return result
        for child in list(parent):
            name = child.tag.rsplit("}", 1)[-1]
            attrs = {key.rsplit("}", 1)[-1]: value for key, value in child.attrib.items()}
            result.setdefault(name, []).append(attrs)
        return result
    for index, p in enumerate(root.findall(".//w:body/w:p", NS)):
        text = _paragraph_text(p)
        pstyle = p.find("w:pPr/w:pStyle", NS)
        style_id = pstyle.get(f"{{{NS['w']}}}val") if pstyle is not None else None
        ppr = p.find("w:pPr", NS)
        p_direct = direct_properties(ppr)
        p_direct.pop("pStyle", None)
        run_direct: dict[str, list[dict[str, Any]]] = {}
        for rpr in p.findall(".//w:rPr", NS):
            for name, attrs in direct_properties(rpr).items():
                run_direct.setdefault(name, []).extend(attrs)
        paragraphs.append({
            "index": index, "text_chars": len(text), "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "style_id": style_id, "style_name": style_names.get(style_id) if style_id else None,
            "direct_paragraph_properties": p_direct, "direct_run_properties": run_direct,
            "numbered_prefix": bool(re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+", text)),
        })
    return paragraphs


def _docx_diff(input_path: Path, submitted_path: Path) -> dict[str, Any]:
    before, after = _docx_paragraphs(input_path), _docx_paragraphs(submitted_path)
    # Match unchanged/edited paragraphs conservatively by index; do not infer semantic equivalence.
    changed = []
    for i in range(max(len(before), len(after))):
        a = before[i] if i < len(before) else None
        b = after[i] if i < len(after) else None
        if a != b:
            changed.append({"paragraph_index": i, "before": a, "after": b})
    top_before = [p for p in before if (p["style_name"] or "").casefold() == "heading 1"]
    top_after = [p for p in after if (p["style_name"] or "").casefold() == "heading 1"]
    text_changed = [i for i in range(min(len(before), len(after))) if before[i]["text_sha256"] != after[i]["text_sha256"]]
    text_groups: dict[tuple[str, str], list[int]] = {}
    for i in text_changed:
        text_groups.setdefault((before[i]["text_sha256"], after[i]["text_sha256"]), []).append(i)
    return {
        "input_paragraph_count": len(before), "submitted_paragraph_count": len(after),
        "changed_paragraph_count_by_same_index": len(changed), "changed_paragraphs": changed,
        "text_changed_paragraph_indices": text_changed,
        "same_text_replacement_groups": [{"paragraph_indices": indices, "before_text_sha256": pair[0], "after_text_sha256": pair[1]}
                                          for pair, indices in text_groups.items()],
        "input_heading1_count": len(top_before), "submitted_heading1_count": len(top_after),
        "submitted_heading1_paragraph_indices": [p["index"] for p in top_after],
        "submitted_heading1_direct_format_signatures": [
            {"paragraph_index": p["index"], "style_id": p["style_id"],
             "paragraph_properties": p["direct_paragraph_properties"], "run_properties": p["direct_run_properties"]}
            for p in top_after
        ],
        "submitted_heading1_direct_format_counts": dict(Counter(
            json.dumps({"paragraph": p["direct_paragraph_properties"], "run": p["direct_run_properties"]}, sort_keys=True)
            for p in top_after)),
        "submitted_numbered_paragraph_count": sum(p["numbered_prefix"] for p in after),
        "input_numbered_paragraph_count": sum(p["numbered_prefix"] for p in before),
        "interpretation": "paragraphs aligned by document order/index; numbering and styles are saved-state observations, not verifier execution",
    }


def _verifier_top_level_labels(source_path: Path, input_docx: Path) -> list[tuple[str, str]]:
    """Read literal top-level heading candidates from verifier source; never import it."""
    if not source_path.is_file():
        return []
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    section_values: list[str] = []
    top_expr = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "section_b" in names:
                section_values = [n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            if "top_level" in names:
                top_expr = node.value
    if not isinstance(top_expr, ast.List):
        return []
    with zipfile.ZipFile(input_docx) as archive:
        doc = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = [_paragraph_text(p).strip() for p in doc.findall(".//w:body/w:p", NS)]
    resolved = []
    ordinal = 0
    for element in top_expr.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            resolved.append((f"top_level_{ordinal + 1}", element.value))
        elif isinstance(element, ast.Name) and element.id == "section_b":
            # Match the verifier's exact `candidate in output_texts` membership,
            # not substring presence in a concatenated document string.
            match = next((s for s in section_values if s in paragraphs), None)
            if match:
                resolved.append((f"top_level_{ordinal + 1}", match))
        ordinal += 1
    return resolved


def _heading_state(path: Path, labels: list[tuple[str, str]]) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    result = {}
    for label, expected_text in labels:
        for index, paragraph in enumerate(root.findall(".//w:body/w:p", NS)):
            text = _paragraph_text(paragraph).strip()
            if text != expected_text:
                continue
            ppr = paragraph.find("w:pPr", NS)
            pstyle = ppr.find("w:pStyle", NS) if ppr is not None else None
            direct_para = {}
            if ppr is not None:
                for item in list(ppr):
                    name = item.tag.rsplit("}", 1)[-1]
                    if name != "pStyle":
                        direct_para[name] = {k.rsplit("}", 1)[-1]: v for k, v in item.attrib.items()}
            run_props = {}
            first_run = next((r for r in paragraph.findall("w:r", NS) if "".join(t.text or "" for t in r.findall(".//w:t", NS)).strip()), None)
            rpr = first_run.find("w:rPr", NS) if first_run is not None else None
            if rpr is not None:
                for item in list(rpr):
                    run_props[item.tag.rsplit("}", 1)[-1]] = {k.rsplit("}", 1)[-1]: v for k, v in item.attrib.items()}
            result[label] = {"paragraph_index": index,
                             "style_id": pstyle.get(f"{{{NS['w']}}}val") if pstyle is not None else None,
                             "direct_paragraph_properties": direct_para,
                             "first_nonempty_run_direct_properties": run_props}
            break
        else:
            result[label] = {"status": "heading_text_not_found_in_saved_document"}
    signatures = [json.dumps({k: v for k, v in item.items() if k != "paragraph_index"}, sort_keys=True)
                  for item in result.values() if "paragraph_index" in item]
    result["_evidence_summary"] = {"matched_heading_count": len(signatures),
                                   "distinct_direct_xml_signatures": len(set(signatures))}
    return result


def _label_counts(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    texts = [_paragraph_text(p).strip() for p in root.findall(".//w:body/w:p", NS)]
    return {
        "new_body_label_exact_paragraphs": sum(text == "a. Isolation logic" for text in texts),
        "new_toc_label_exact_paragraphs": sum(text == "a. Isolation logic\t4" for text in texts),
        "old_label_occurrences": sum(text.count("c. Isolation logic") for text in texts),
    }


def _paragraph_text(paragraph: ET.Element) -> str:
    parts = []
    for node in paragraph.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if local == "t":
            parts.append(node.text or "")
        elif local == "tab":
            parts.append("\t")
        elif local in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts)


def _resource_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    samples = summary.get("samples", [])
    events = summary.get("events", [])
    if not samples:
        return {"sample_count": 0, "sample_window_s": None, "container_cpu_core_s": None,
                "cpu_status": "no_samples", "memory_current_sampled_peak_bytes": None,
                "kernel_memory_peak_bytes": None, "host_agent_rss_sampled_peak_bytes": None}
    times = [s.get("t_monotonic_ns") for s in samples]
    valid_times = all(isinstance(t, int) and not isinstance(t, bool) for t in times) and all(b >= a for a, b in zip(times, times[1:]))
    window = (times[-1] - times[0]) / 1e9 if valid_times and len(times) > 1 else (0.0 if valid_times else None)
    intervals = [(b - a) / 1e9 for a, b in zip(times, times[1:]) if isinstance(a, int) and isinstance(b, int) and b >= a]
    cpu_values, cpu_statuses = [], []
    for sample in samples:
        c = sample.get("container", {})
        cpu_values.append(c.get("cpu_usage_usec"))
        cpu_statuses.append(c.get("read_status", {}).get("cpuacct.usage"))
    cpu_error = None
    if not valid_times:
        cpu_error = "sample_clock_missing_or_nonmonotonic"
    elif any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in cpu_values):
        cpu_error = "cpu_counter_missing_or_non_numeric"
    elif any(isinstance(v, (int, float)) and isinstance(p, (int, float)) and v < p for p, v in zip(cpu_values, cpu_values[1:])):
        cpu_error = "cpu_counter_decreased"
    elif any(s != "ok_ns_converted_to_usec" for s in cpu_statuses):
        cpu_error = "cpu_counter_read_status_not_all_ok"
    cpu_s = (cpu_values[-1] - cpu_values[0]) / 1e6 if cpu_error is None and len(cpu_values) > 1 else (0.0 if cpu_error is None else None)
    current = [s.get("container", {}).get("mem_current_bytes") for s in samples]
    kernel_peak = [s.get("container", {}).get("mem_peak_bytes") for s in samples]
    rss = [s.get("host_agent", {}).get("rss_bytes") for s in samples]
    events_by_name = {}
    for e in events:
        events_by_name.setdefault(e.get("phase"), []).append(e.get("t_monotonic_ns"))
    stage_specs = {"agent_setup": ("agent_setup_begin", "agent_setup_done"), "agent": ("agent_begin", "agent_end"),
                   "verifier": ("verifier_begin", "verifier_end")}
    stages = {}
    boundary_pairs = []
    boundaries = sorted({t for values in events_by_name.values() for t in values if isinstance(t, int)})
    for name, (start_name, end_name) in stage_specs.items():
        starts, ends = events_by_name.get(start_name, []), events_by_name.get(end_name, [])
        if not starts or not ends or not valid_times:
            stages[name] = {"duration_s": None, "sampled_cpu_core_s": None, "eligible_interval_count": 0, "status": "unavailable_missing_boundaries"}
            continue
        start, end = starts[0], ends[-1]
        ds = (end - start) / 1e9 if end >= start else None
        stage_diffs, n = 0, 0
        for i, (left, right) in enumerate(zip(samples, samples[1:])):
            t0, t1 = left["t_monotonic_ns"], right["t_monotonic_ns"]
            if t0 >= start and t1 <= end:
                x, y = left.get("container", {}).get("cpu_usage_usec"), right.get("container", {}).get("cpu_usage_usec")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)) and y >= x:
                    stage_diffs += y - x
                    n += 1
            elif t0 < end and t1 > start and any(t0 < b <= t1 for b in boundaries):
                boundary_pairs.append(i)
        stages[name] = {"duration_s": ds, "sampled_cpu_core_s": stage_diffs / 1e6 if n else None,
                        "eligible_interval_count": n, "status": "sampled_interval_differences_only" if n else "unavailable_insufficient_within_stage_samples"}
    def numeric_max(values: list[Any]) -> int | float | None:
        valid = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0]
        return max(valid) if valid else None
    boundary_cpu_usec = 0
    boundary_cpu_intervals = 0
    for i in set(boundary_pairs):
        left, right = samples[i], samples[i + 1]
        x, y = left.get("container", {}).get("cpu_usage_usec"), right.get("container", {}).get("cpu_usage_usec")
        if isinstance(x, (int, float)) and not isinstance(x, bool) and isinstance(y, (int, float)) and not isinstance(y, bool) and y >= x:
            boundary_cpu_usec += y - x
            boundary_cpu_intervals += 1
    missing_fields = {}
    for field, selector in {
        "container.cpu_usage_usec": lambda s: s.get("container", {}).get("cpu_usage_usec"),
        "container.mem_current_bytes": lambda s: s.get("container", {}).get("mem_current_bytes"),
        "container.mem_peak_bytes": lambda s: s.get("container", {}).get("mem_peak_bytes"),
        "host_agent.rss_bytes": lambda s: s.get("host_agent", {}).get("rss_bytes"),
    }.items():
        missing_fields[field] = sum(selector(s) is None for s in samples)
    return {
        "sample_count": len(samples), "sample_window_start_monotonic_ns": times[0] if valid_times else None,
        "sample_window_end_monotonic_ns": times[-1] if valid_times else None, "sample_window_s": window,
        "sample_interval_s_median": statistics.median(intervals) if intervals else None,
        "sample_interval_s_min": min(intervals) if intervals else None, "sample_interval_s_max": max(intervals) if intervals else None,
        "sample_field_missing_counts": missing_fields,
        "container_cpu_core_s": cpu_s, "cpu_status": cpu_error or "valid_counter_difference",
        "memory_current_sampled_peak_bytes": numeric_max(current), "kernel_memory_peak_bytes": numeric_max(kernel_peak),
        "host_agent_rss_sampled_peak_bytes": numeric_max(rss), "phase_metrics": stages,
        "sample_intervals_crossing_recorded_event_boundaries": len(set(boundary_pairs)),
        "boundary_mixed_cpu_core_s": boundary_cpu_usec / 1e6 if boundary_cpu_intervals else None,
        "boundary_mixed_cpu_interval_count": boundary_cpu_intervals,
        "io_fields_present": bool(samples and all("io_read_bytes" in s.get("container", {}) and "io_write_bytes" in s.get("container", {}) for s in samples)),
        "io_read_status_counts": dict(Counter(s.get("container", {}).get("read_status", {}).get("io", "missing") for s in samples)),
        "io_interpretation": "recorded counters/read status only; not complete document or filesystem I/O",
    }


def _analyze_run(root: Path, collection: str, run_id: str, plan_suffix: str) -> tuple[dict[str, Any], list[Path]]:
    run_dir = root / "data/raw/generated" / collection / run_id
    summary_path, manifest_path = run_dir / "summary.json", run_dir / "manifest.json"
    summary, manifest = load_json(summary_path), load_json(manifest_path)
    plan_path = root / f"env/docops-arm64-word001/plan-identity-{plan_suffix}.json"
    frozen_path = root / f"env/docops-arm64-word001/frozen-identity-{plan_suffix}.json"
    approval_path = root / f"reports/resource/{collection}/APPROVAL.json"
    plan, frozen, approval = load_json(plan_path), load_json(frozen_path), load_json(approval_path)
    started = load_json(run_dir / "ATTEMPT_STARTED.json") if (run_dir / "ATTEMPT_STARTED.json").is_file() else {}
    completed = load_json(run_dir / "ATTEMPT_COMPLETED.json") if (run_dir / "ATTEMPT_COMPLETED.json").is_file() else {}
    identity_values = {summary.get("identity_sha256"), manifest.get("identity_sha256"), plan.get("identity_sha256"),
                       frozen.get("identity_sha256"), approval.get("identity_sha256"), started.get("identity_sha256")}
    approval_invocation = approval.get("entry_invocation")
    invocation_ok = not isinstance(approval_invocation, dict) or (
        approval_invocation.get("run_id") == run_id and approval_invocation.get("attempt_completed") is True
        and approval_invocation.get("entry_exit_code") == 0)
    attempt_binding_ok = started.get("run_id") == run_id and completed.get("run_id") == run_id
    identity_ok = (len(identity_values) == 1 and plan.get("collection") == collection
                   and frozen.get("collection") == collection and approval.get("collection") == collection
                   and approval.get("schema") == "docops-single-run-approval-v1"
                   and approval.get("user_approval") == "approved"
                   and summary.get("collection") == collection and manifest.get("run_id") == run_id
                   and summary.get("run_id") == run_id and attempt_binding_ok and invocation_ok)
    archive = _manifest_check(root, run_dir, manifest)
    if not archive["passed"]:
        raise ValueError(f"{collection} {run_id}: raw manifest verification failed: {archive}")
    if not identity_ok:
        raise ValueError(f"{collection} {run_id}: identity disagreement among archive/plan/frozen/approval")

    llm_files = sorted((run_dir / "agent").glob("llm_call_*.json"), key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))
    calls, model_info = _action_history(run_dir, len(llm_files))
    tool_calls = [c for c in calls if c.get("action") == "call_tool"]
    phases = summary.get("outcome", {}).get("phases", {})
    independent_report_path = root / f"reports/resource/{collection}/run-report.json"
    independent_report = load_json(independent_report_path) if independent_report_path.is_file() else None
    report_crosscheck = None
    if independent_report is not None:
        report_counts = {k: v for k, v in independent_report.get("agent", {}).get("tool_actions", {}).get("counts", {}).items() if v}
        raw_counts = dict(Counter(c.get("tool_name", "unknown") for c in tool_calls))
        report_crosscheck = {
            "run_id_matches": independent_report.get("run_id") == run_id,
            "identity_matches": independent_report.get("identity_sha256") == summary.get("identity_sha256"),
            "request_count_matches": independent_report.get("agent", {}).get("model_call_count") == len(llm_files),
            "termination_matches": independent_report.get("agent", {}).get("termination") == phases.get("agent", {}).get("status"),
            "reward_matches": independent_report.get("task_result", {}).get("reward") == phases.get("verifier", {}).get("reward"),
            "wall_matches": independent_report.get("measurement_integrity", {}).get("attempt_wall_s") == summary.get("wall_s"),
            "tool_name_counts_match": report_counts == raw_counts,
        }
    reward_file = run_dir / "verifier/reward.txt"
    reward_text = reward_file.read_text(encoding="utf-8").strip() if reward_file.is_file() else None
    ctrf = load_json(run_dir / "verifier/ctrf.json") if (run_dir / "verifier/ctrf.json").is_file() else {}
    tests = ctrf.get("results", {}).get("tests", []) if isinstance(ctrf.get("results"), dict) else []
    failed_tests = [t.get("name") for t in tests if t.get("status") in {"failed", "failure"}]
    task_dir = root / TASK_REL
    input_docx = task_dir / "environment/word_001_engineering_report_toc_hierarchy_seed.docx"
    submitted_docx = run_dir / "verifier/submission/word_001_engineering_report_toc_hierarchy_seed.docx"
    docx_report = _docx_diff(input_docx, submitted_docx) if input_docx.is_file() and submitted_docx.is_file() else None
    replacement_pairs = {
        (item.get("old", {}).get("sha256"), item.get("new", {}).get("sha256"))
        for call in tool_calls for item in call.get("arguments", {}).get("replacement_summaries", [])
        if item.get("old", {}).get("sha256") and item.get("new", {}).get("sha256")
    }
    verifier_source = task_dir / "tests/test_outputs.py"
    top_labels = _verifier_top_level_labels(verifier_source, submitted_docx) if submitted_docx.is_file() else []
    if docx_report is not None:
        docx_report["verifier_top_level_heading_source"] = "static literals parsed from local test_outputs.py; not imported/executed"
        docx_report["verifier_top_level_saved_direct_signatures"] = _heading_state(submitted_docx, top_labels) if submitted_docx.is_file() else {}
        docx_report["task_label_counts_input"] = _label_counts(input_docx)
        docx_report["task_label_counts_submitted"] = _label_counts(submitted_docx)
        for group in docx_report["same_text_replacement_groups"]:
            group["matches_emitted_tool_replacement_hash_pair"] = (
                group["before_text_sha256"], group["after_text_sha256"]) in replacement_pairs
    events = summary.get("events", [])
    verifier_stdout = (run_dir / "verifier/test-stdout.txt").read_text(encoding="utf-8", errors="replace") if (run_dir / "verifier/test-stdout.txt").is_file() else ""
    assertion_match = re.search(r"AssertionError:\s*([^\r\n]+)", verifier_stdout)
    event_times = {e.get("phase"): e.get("t_monotonic_ns") for e in events if isinstance(e.get("t_monotonic_ns"), int)}
    bootstrap_events = [e.get("phase") for e in events if e.get("phase", "").startswith("agent_setup_")]
    bootstrap_tool_counts = _bootstrap_tool_counts(run_dir, len(llm_files))
    persisted = Counter(c.get("return_status") for c in tool_calls)
    output = {
        "collection": collection, "run_id": run_id, "max_steps": plan.get("identity", {}).get("budget", {}).get("max_steps"),
        "identity_sha256": next(iter(identity_values)), "identity_chain_verified": identity_ok,
        "attempt_record_binding_verified": attempt_binding_ok,
        "independent_report_crosscheck": report_crosscheck,
        "archive_verification": archive,
        "historical_source_readback": _source_readback(root, plan),
        "attempt_wall_s": summary.get("wall_s"), "within_total_budget": summary.get("within_total_budget"),
        "agent_termination": phases.get("agent", {}).get("status"), "agent_call_count": len(llm_files),
        "action_counts": dict(Counter(c.get("action", "unknown") for c in calls)),
        "tool_action_count": len(tool_calls), "tool_name_counts": dict(Counter(c.get("tool_name", "unknown") for c in tool_calls)),
        "tool_activity_category_counts": dict(Counter(c.get("activity_category", "unknown") for c in tool_calls)),
        "tool_calls": tool_calls, "tool_return_status_counts": dict(persisted),
        "bootstrap_setup_events": bootstrap_events, "bootstrap_separate_from_model_actions": True,
        "bootstrap_tool_counts_from_first_request_history": bootstrap_tool_counts,
        "request_model": model_info.get("logged_request_model"), "response_model_counts": model_info.get("response_model_counts"),
        "usage_recorded_by_phase": {k: phases.get("agent", {}).get(k) for k in ("n_input_tokens", "n_output_tokens", "n_cache_tokens")},
        "verifier_status": phases.get("verifier", {}).get("status"), "reward": phases.get("verifier", {}).get("reward"),
        "reward_file_value": reward_text, "failed_assertions_from_saved_ctrf": failed_tests,
        "first_failure_detail_from_saved_stdout": assertion_match.group(1) if assertion_match else None,
        "assertions_before_first_failure": "passed by sequential verifier control flow" if assertion_match else "unknown",
        "later_assertions_interpretation": "not executed/unknown after first failure; no re-evaluation performed",
        "container_removal": next((e.get("result") for e in events if e.get("phase") == "removal_verified"), "unknown"),
        "attempt_markers": {name: (run_dir / name).is_file() for name in ("ATTEMPT_STARTED.json", "ATTEMPT_COMPLETED.json")},
        "approval_evidence": {"user_approval": approval.get("user_approval"),
                              "entry_invocation_present": isinstance(approval.get("entry_invocation"), dict),
                              "entry_invocation_run_id": approval_invocation.get("run_id") if isinstance(approval_invocation, dict) else None,
                              "entry_invocation_is_execution_record_not_identity": True},
        "image_tag_after_cleanup": next((e.get("present") for e in events if e.get("phase") == "image_tag_after_stop"), None),
        "container_id": summary.get("container", {}).get("id"), "resources": _resource_metrics(summary),
        "phase_durations_s": _phase_durations(events), "submitted_document": file_record(root, submitted_docx) if submitted_docx.is_file() else None,
        "document_state_comparison": docx_report,
        "tool_results_note": "return statuses linked only when following saved request-history message explicitly says Tool result for <tool>; unpersisted terminal tool result remains unknown",
    }
    inputs = [summary_path, manifest_path, plan_path, frozen_path, approval_path, input_docx, submitted_docx,
              run_dir / "agent/document-tools-agent.txt", run_dir / "verifier/ctrf.json", reward_file,
              run_dir / "verifier/test-stdout.txt",
              root / "references/repos/DocOps/harnesses/document_tools_agent.py"]
    inputs.append(verifier_source)
    inputs.extend(llm_files)
    if independent_report_path.is_file():
        inputs.append(independent_report_path)
    # Add every file declared by the run manifest: each was hash-checked above.
    inputs.extend(run_dir / item["path"] for item in manifest.get("outputs", []))
    return output, list(dict.fromkeys(p for p in inputs if p.is_file()))


def _source_readback(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    expected = plan.get("identity", {}).get("files", {})
    checked, mismatched, missing = [], [], []
    for label, item in expected.items():
        path_str, expected_hash = item.get("path"), item.get("sha256")
        path = Path(path_str) if path_str else None
        if path is not None and not path.is_absolute():
            path = root / path
        if path is None or not path.is_file():
            missing.append(label)
        elif sha256(path) != expected_hash:
            mismatched.append(label)
        else:
            checked.append(label)
    return {"identity_files_checked": len(checked) + len(mismatched) + len(missing),
            "current_file_hash_matches": len(checked), "current_file_hash_mismatches": mismatched,
            "current_file_missing": missing,
            "limitation": "archived identity remains the run identity; current source mismatch limits historical source-byte replay only"}


def _phase_durations(events: list[dict[str, Any]]) -> dict[str, Any]:
    ts = {}
    for event in events:
        ts.setdefault(event.get("phase"), []).append(event.get("t_monotonic_ns"))
    pairs = {"harbor_start": ("harbor_start_begin", "harbor_start_done"),
             "agent_setup": ("agent_setup_begin", "agent_setup_done"), "agent": ("agent_begin", "agent_end"),
             "verifier": ("verifier_begin", "verifier_end"), "harbor_stop": ("harbor_stop_begin", "harbor_stop_done"),
             "archive": ("archive_begin", "archive_done")}
    out = {}
    for name, (a, b) in pairs.items():
        starts, ends = ts.get(a, []), ts.get(b, [])
        out[name] = (ends[-1] - starts[0]) / 1e9 if starts and ends and ends[-1] >= starts[0] else None
    return out


def _bootstrap_tool_counts(run_dir: Path, call_count: int) -> dict[str, int]:
    if call_count < 1:
        return {}
    first = load_json(run_dir / "agent" / "llm_call_1.json")
    counts = Counter()
    for message in first.get("messages", []):
        content = message.get("content")
        if not isinstance(content, str):
            continue
        for name in ("get_task_metadata", "inspect_document"):
            if content.startswith(f"Bootstrap tool result ({name}"):
                counts[name] += 1
    return dict(counts)


def analyze(root: Path, output_dir: Path | None = None, run_specs: tuple = RUNS) -> dict[str, Any]:
    root = root.resolve()
    output_dir = output_dir or (root / OUT_REL)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite analysis directory: {output_dir}")
    results, all_inputs = [], []
    for collection, run_id, suffix in run_specs:
        result, inputs = _analyze_run(root, collection, run_id, suffix)
        results.append(result)
        all_inputs.extend(inputs)
    # DOCX resource/behavior are two observations, not a controlled repeat estimate.
    summary = _summary(results)
    output_dir.mkdir(parents=True)
    (output_dir / "per_run.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.md").write_text(_markdown(summary), encoding="utf-8")
    inputs = sorted({p.resolve() for p in all_inputs})
    outputs = [output_dir / "per_run.json", output_dir / "summary.json", output_dir / "summary.md"]
    code_path = root / "scripts/docops_word_resource_analysis.py"
    manifest = {"schema": "docops-word-resource-analysis-manifest-v1",
                "inputs": [file_record(root, p) for p in inputs],
                "analysis_code": file_record(root, code_path),
                "outputs": [file_record(root, p) for p in outputs],
                "manifest_self_hash": "omitted_by_design"}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Read-after-write verification; the manifest intentionally does not hash itself.
    for item in manifest["outputs"]:
        path = root / item["path"]
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise IOError(f"output hash mismatch after write: {item['path']}")
    return {"summary": summary, "manifest": manifest}


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scope": "only the two explicitly named DOCOPS-WORD-RESOURCE-03/04 runs for one DocOps Word task",
        "runs": [{"collection": r["collection"], "run_id": r["run_id"], "max_steps": r["max_steps"],
                  "model_calls": r["agent_call_count"], "tool_actions": r["tool_action_count"],
                  "tool_categories": r["tool_activity_category_counts"], "termination": r["agent_termination"],
                  "reward": r["reward"], "wall_s": r["attempt_wall_s"],
                  "container_cpu_core_s": r["resources"]["container_cpu_core_s"],
                  "memory_current_sampled_peak_bytes": r["resources"]["memory_current_sampled_peak_bytes"],
                  "kernel_memory_peak_bytes": r["resources"]["kernel_memory_peak_bytes"],
                  "host_agent_rss_sampled_peak_bytes": r["resources"]["host_agent_rss_sampled_peak_bytes"],
                  "sample_count": r["resources"]["sample_count"], "sample_window_s": r["resources"]["sample_window_s"],
                  "identity_verified": r["identity_chain_verified"], "archive_verified": r["archive_verification"]["passed"],
                  "bootstrap_tool_counts": r["bootstrap_tool_counts_from_first_request_history"],
                  "tool_return_status_counts": r["tool_return_status_counts"],
                  "first_failure_detail": r["first_failure_detail_from_saved_stdout"],
                  "phase_durations_s": r["phase_durations_s"],
                  "document_text_changed_indices": (r["document_state_comparison"] or {}).get("text_changed_paragraph_indices"),
                  "heading1_count_in_saved_document": (r["document_state_comparison"] or {}).get("submitted_heading1_count"),
                  "heading1_indices_in_saved_document": (r["document_state_comparison"] or {}).get("submitted_heading1_paragraph_indices"),
                  "phase_durations_s": r["phase_durations_s"],
                  "phase_sampled_cpu_core_s": {k: v["sampled_cpu_core_s"] for k, v in r["resources"]["phase_metrics"].items()},
                  "historical_source_hash_mismatches": r["historical_source_readback"]["current_file_hash_mismatches"]}
                 for r in runs],
        "run_details": [{"collection": r["collection"], "request_model": r["request_model"],
                         "response_model_counts": r["response_model_counts"],
                         "bootstrap_tool_counts": r["bootstrap_tool_counts_from_first_request_history"],
                         "tool_return_status_counts": r["tool_return_status_counts"],
                         "independent_report_crosscheck": r["independent_report_crosscheck"],
                         "first_failure_detail": r["first_failure_detail_from_saved_stdout"],
                         "assertions_before_first_failure": r["assertions_before_first_failure"],
                         "phase_durations_s": r["phase_durations_s"],
                         "phase_sampled_cpu_core_s": {k: v["sampled_cpu_core_s"] for k, v in r["resources"]["phase_metrics"].items()},
                         "historical_source_hash_mismatches": r["historical_source_readback"]["current_file_hash_mismatches"],
                         "format_style_actions": [{"paragraph_index": c.get("arguments", {}).get("paragraph_index"),
                                                   "style_name": c.get("arguments", {}).get("style_name"),
                                                   "direct_format_fields_supplied": c.get("arguments", {}).get("format_fields", [])}
                                                  for c in r["tool_calls"] if c.get("tool_name") == "word_set_format"],
                         "format_edit_action_count": sum(c.get("tool_name") == "word_set_format" for c in r["tool_calls"]),
                         "direct_format_field_count": sum(len(c.get("arguments", {}).get("format_fields", []))
                                                           for c in r["tool_calls"] if c.get("tool_name") == "word_set_format"),
                         "submitted_label_counts": (r["document_state_comparison"] or {}).get("task_label_counts_submitted"),
                         "heading_signature_summary": ((r["document_state_comparison"] or {}).get("verifier_top_level_saved_direct_signatures", {}).get("_evidence_summary", {})),
                         "heading1_style_count": (r["document_state_comparison"] or {}).get("submitted_heading1_count"),
                         "document_state_comparison": r["document_state_comparison"]}
                        for r in runs],
        "comparability": "descriptive only; max_steps differs (12 vs 40), n=1 each; no causal effect or successful-completion cost inference",
        "resource_scope": "container CPU/memory are shared task-container measurements; host RSS includes Agent/orchestration/collection scope; not per-tool or model-inference-only",
        "time_scope": "attempt wall and event phase intervals are recorded monotonic-clock durations; request timestamps are not server inference time; no wall-minus-CPU waiting estimate",
        "missing_evidence": ["03 has no independent run-report.json", "terminal tool result after last request may be unpersisted", "no per-tool start/end resource timestamps", "I/O counters do not establish complete document/filesystem I/O"],
    }


def _markdown(summary: dict[str, Any]) -> str:
    rows = summary["runs"]
    lines = ["# DOCOPS Word 03/04 有限行为—资源联合分析", "",
             "## 证据范围与核验", "",
             "仅分析显式登记的 DOCOPS-03 与 DOCOPS-04 两个归档 run。两份 raw manifest 的输出 bytes/SHA、归档 identity、对应计划/冻结值/批准 identity 均由分析入口核验；提交 DOCX 与官方输入按保存哈希定位。历史身份按归档链判断，不要求当前源码回到历史字节。", "",
             "该分析描述一个 DocOps Word 任务的两次不同步数配置运行，不是受控重复，也不估计步数预算的因果效应。", "",
             "## 行为、终止与资源", "",
             "| Run | 步数上限 | 请求 | 工具动作/类别 | 终止 | Reward | Wall s | 容器 CPU core-s | memory.current 采样峰值 B | 内核 memory peak B | 宿主 Agent RSS 采样峰值 B | 采样点/窗口 s |",
             "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        cats = ", ".join(f"{k}:{v}" for k, v in r["tool_categories"].items())
        lines.append(f"| {r['collection']} | {r['max_steps']} | {r['model_calls']} | {r['tool_actions']} ({cats}) | {r['termination']} | {r['reward']} | {r['wall_s']} | {r['container_cpu_core_s']} | {r['memory_current_sampled_peak_bytes']} | {r['kernel_memory_peak_bytes']} | {r['host_agent_rss_sampled_peak_bytes']} | {r['sample_count']} / {r['sample_window_s']} |")
    lines += ["", "### 每次运行的行为与提交文档证据", ""]
    for detail in summary.get("run_details", []):
        lines.append(f"- {detail['collection']}：请求模型 `{detail['request_model']}`；响应模型计数 `{detail['response_model_counts']}`。bootstrap/setup 单列为 `{detail['bootstrap_tool_counts']}`，不计入模型自主工具动作。工具返回状态 `{detail['tool_return_status_counts']}`；verifier 首个失败为 `{detail['first_failure_detail']}`；此前顺序断言状态：{detail['assertions_before_first_failure']}。阶段 wall 为 `{detail['phase_durations_s']}` 秒；阶段内样本 CPU 差分为 `{detail['phase_sampled_cpu_core_s']}` core-s；当前源码回读与历史 identity 文件哈希不一致项 `{detail['historical_source_hash_mismatches']}`（不改变已核验归档身份）。可用独立 run-report 与 raw 的交叉核验 `{detail['independent_report_crosscheck']}`；无独立报告时为 null。")
        doc = detail.get("document_state_comparison") or {}
        heading_evidence = doc.get("verifier_top_level_saved_direct_signatures", {}).get("_evidence_summary", {})
        lines.append(f"  提交 DOCX 与输入按段落位置比较：文本改变段落索引 `{doc.get('text_changed_paragraph_indices')}`；正文新标签/TOC新标签/旧标签计数为 `{doc.get('task_label_counts_submitted')}`。格式编辑动作数 `{detail['format_edit_action_count']}`，其参数中的直接格式字段数 `{detail['direct_format_field_count']}`；动作参数为 `{detail['format_style_actions']}`。保存文档 Heading 1 样式段落数 `{doc.get('submitted_heading1_count')}`（索引 `{doc.get('submitted_heading1_paragraph_indices')}`）；静态定位到的 verifier 顶级标题中 `{heading_evidence.get('matched_heading_count')}` 个匹配、直接 XML 签名有 `{heading_evidence.get('distinct_direct_xml_signatures')}` 种。具体段落直接属性与签名见 per_run.json。该 XML 盘点不重跑 verifier，也不替代其实际结果。")
    termination = "；".join(f"{r['collection']}：{r['termination']}，reward={r['reward']}" for r in rows)
    failures = "；".join(f"{d['collection']}：{d['first_failure_detail']}" for d in summary.get("run_details", []))
    common_categories = set(rows[0]["tool_categories"]) if rows else set()
    for row in rows[1:]:
        common_categories.intersection_update(row["tool_categories"])
    lines += ["", f"终止与任务结果（独立维度）：{termination}。保存的 pytest 输出首个失败为：{failures}。失败前的顺序断言已执行且未触发失败；后续断言未执行或 unknown。reward=0 不抹去实际采样的描述价值，但这些开销不是成功完成成本。", "",
              "模型请求与 bootstrap/setup 分开计数。工具类别依据结构化 action 的 tool_name；返回只在保存的对话历史中出现紧随其后的 `Tool result for <tool>` 消息时关联。若终止前没有下一请求持久化该消息，返回状态保持 unknown。工具参数摘要和提交 DOCX 的段落/样式状态见 per_run.json；工具成功不等于 verifier 正确。", "",
              "资源按原采样字段重算：CPU 为首末有效 cgroup 累计计数差，memory.current 为采样最大值，kernel memory peak 单列，宿主 RSS 为采样最大值。采样窗口短于 attempt wall；阶段 CPU 仅累计阶段内两端样本均在边界内的相邻采样差，边界混合未均摊。容器资源不能归因到单个工具，宿主 RSS 不是模型推理 CPU。I/O 只盘点字段与读取状态，不解释为完整文件系统 I/O。", "",
              "## 有限结论与缺口", "",
              f"两条记录共同出现的结构化工具类别为 `{sorted(common_categories)}`；调用证明动作被发出，不代表结果正确。格式参数、工具返回和保存 DOCX 状态需交叉解读。出现 finish 也不等于任务通过；两点间 wall/CPU/内存差异不能单因归结为 max_steps。", "",
              "reward=0 仍可用于分析实际调用序列、终止路径和已观测资源；但不应称为成功完成成本、Office 类别规律或模型能力结论。当前没有逐工具资源时间戳，也不能把请求时间解释为服务端推理时间。", "",
              "下一步唯一建议：若研究问题要区分任务特异性与稳定行为，先评估是否在另一项固定 Office 任务上做固定配置重复；不要为了 reward=1 自动重跑本任务。", "",
              "G2/G3-R 裁定不变；CPU-02 与 Replay 继续暂停。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.root, args.output)
    print(json.dumps({"runs": len(result["summary"]["runs"]), "output": str(args.output or (args.root / OUT_REL))}, ensure_ascii=False))
