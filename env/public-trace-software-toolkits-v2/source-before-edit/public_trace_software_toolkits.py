#!/usr/bin/env python3
"""Evidence-layered software/toolkit summary from accepted local analyses.

This report reuses validated operation/behavior packages; it never executes a
trace or infers a product from a file extension. Coding program counts are
saved command-head components, not successful executions.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import csv
import hashlib
import importlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[1]
OUT_REL = "reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v1"

PACKAGES = {
    "public_operations_v3": ("reports/analysis/PUBLIC-TRACE-OPERATIONS-v3", ("summary.json", "toolkits.json", "per_trajectory.jsonl", "coverage.json")),
    "osworld_behavior_v3": ("reports/analysis/OSWORLD-task-behavior-v3", ("summary.json", "task_semantics.jsonl", "per_trajectory.jsonl")),
    "hepm_behavior_v2": ("reports/analysis/TOOLSANDBOX-HEPM-behavior-v2", ("summary.json", "per_trajectory.jsonl")),
    "docops_repeat02": ("reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1", ("summary.json", "per_run.jsonl")),
    "toolsandbox_assistant_repeat01": ("reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1", ("summary.json", "per_run.jsonl")),
    "agentx_applied_macro": ("reports/analysis/AGENTX-APPLIED-MACRO-v1", ("summary.json",)),
}

# These names are accepted only as command heads already extracted by the
# PUBLIC-TRACE-OPERATIONS-v3 parser. Shell control words and terminal API names
# are deliberately absent.
PROGRAMS = {
    "grep": ("grep", "内容检索"), "egrep": ("grep", "内容检索"), "fgrep": ("grep", "内容检索"),
    "rg": ("ripgrep", "内容检索"), "ripgrep": ("ripgrep", "内容检索"), "ag": ("The Silver Searcher", "内容检索"), "ack": ("ack", "内容检索"),
    "find": ("find", "文件定位"), "locate": ("locate", "文件定位"), "tree": ("tree", "目录浏览"), "ls": ("ls", "目录浏览"),
    "cat": ("cat", "文本查看/输出"), "head": ("head", "文本查看/输出截取"), "tail": ("tail", "文本查看/输出截取"), "less": ("less", "文本查看"), "more": ("more", "文本查看"), "nl": ("nl", "文本编号/查看"), "wc": ("wc", "文本计数"),
    "sed": ("sed", "文本流处理；具体读写用途未保留"), "awk": ("awk", "文本处理"), "sort": ("sort", "文本处理"), "uniq": ("uniq", "文本处理"), "cut": ("cut", "文本处理"), "tr": ("tr", "文本处理"), "xargs": ("xargs", "参数/命令组合；目标依赖上下文"), "tee": ("tee", "输出分流/写入；具体目标未保留"),
    "git": ("Git", "版本控制/差异检查；具体子命令在聚合计数中未保留"), "diff": ("diff", "差异检查"), "patch": ("patch", "补丁应用"), "apply_patch": ("apply_patch", "补丁应用"), "applypatch": ("apply_patch", "补丁应用"),
    "python": ("Python", "解释器/脚本入口；脚本用途不由名称决定"), "python3": ("Python", "解释器/脚本入口；脚本用途不由名称决定"), "python3.6": ("Python", "解释器/脚本入口；版本不作为软件版本结论"), "python3.7": ("Python", "解释器/脚本入口；版本不作为软件版本结论"),
    "pytest": ("pytest", "测试运行器"), "py.test": ("pytest", "测试运行器"), "vitest": ("Vitest", "测试运行器"), "tox": ("tox", "测试/环境自动化；具体子命令未保留"),
    "node": ("Node.js", "JavaScript运行时"), "npm": ("npm", "Node包管理/脚本入口；具体脚本未绑定"), "npx": ("npx", "Node包/命令执行入口；具体包未绑定"), "pnpm": ("pnpm", "Node包管理/脚本入口；具体脚本未绑定"), "yarn": ("Yarn", "Node包管理/脚本入口；具体脚本未绑定"),
    "go": ("Go toolchain", "Go命令；build/test子命令在聚合组件中不可区分"), "gofmt": ("gofmt", "Go源码格式化"), "cargo": ("Cargo", "Rust构建/测试/依赖工具；子命令未保留"), "rustc": ("rustc", "Rust编译器"), "rustup": ("rustup", "Rust工具链管理"),
    "mvn": ("Maven", "构建/测试/依赖；具体子命令未保留"), "mvnw": ("Maven Wrapper", "Maven构建入口；具体子命令未保留"), "gradle": ("Gradle", "构建/测试/依赖；具体子命令未保留"), "gradlew": ("Gradle Wrapper", "Gradle构建入口；具体子命令未保留"), "make": ("make", "构建/任务入口；目标名未保留"), "cmake": ("CMake", "构建配置/生成；具体参数未保留"), "ninja": ("Ninja", "构建工具"), "bazel": ("Bazel", "构建/测试；具体子命令未保留"), "gcc": ("GCC", "C编译器"), "g++": ("G++", "C++编译器"), "clang": ("Clang", "编译器"), "javac": ("javac", "Java编译器"), "java": ("Java", "运行时/命令入口；目标用途未细分"), "tsc": ("TypeScript Compiler", "TypeScript编译/检查"),
    "pip": ("pip", "Python包管理"), "pip3": ("pip", "Python包管理"), "uv": ("uv", "Python项目/依赖管理"), "uvx": ("uvx", "Python工具运行入口"), "conda": ("conda", "环境/依赖管理"), "mamba": ("mamba", "环境/依赖管理"), "poetry": ("Poetry", "Python项目/依赖管理"), "apt": ("APT", "系统包管理命令"), "apt-get": ("APT", "系统包管理命令"),
    "ruff": ("Ruff", "Python lint/格式工具"), "pylint": ("Pylint", "Python静态检查"), "mypy": ("mypy", "Python静态类型检查"), "curl": ("curl", "HTTP/URL命令行客户端；执行结果不由调用名证明"), "wget": ("Wget", "URL获取命令行工具；执行结果不由调用名证明"), "docker": ("Docker CLI", "容器命令接口；命令结果不由调用名证明"),
    "bash": ("Bash", "命令解释器/入口，不是命令内软件本身"), "sh": ("POSIX shell", "命令解释器/入口，不是命令内软件本身"), "ruby": ("Ruby", "解释器/运行时"), "perl": ("Perl", "解释器/文本处理"), "sphinx-build": ("Sphinx", "文档构建"), "django-admin": ("Django admin", "Django管理命令"), "sqlite3": ("SQLite CLI", "数据库命令行接口"),
}

APP_PRODUCTS = {
    "chrome": ("Chrome", "浏览器"), "google-chrome": ("Google Chrome", "浏览器"),
    "firefox": ("Firefox", "浏览器"), "thunderbird": ("Thunderbird", "邮件客户端"),
    "libreoffice_writer": ("LibreOffice Writer", "LibreOffice"),
    "libreoffice_calc": ("LibreOffice Calc", "LibreOffice"),
    "libreoffice_impress": ("LibreOffice Impress", "LibreOffice"),
    "libreoffice": ("LibreOffice（组件未指定）", "LibreOffice"),
    "wps": ("WPS（组件未指定）", "WPS"), "gimp": ("GIMP", "图像编辑"),
    "blender": ("Blender", "3D创作"), "evince": ("Evince", "PDF阅读器"),
    "nautilus": ("Nautilus", "文件管理器"), "freecad": ("FreeCAD", "CAD"),
    "geogebra": ("GeoGebra", "数学软件"), "kicad": ("KiCad", "电子设计"),
    "shotcut": ("Shotcut", "视频编辑"), "reaper": ("REAPER", "音频工作站"),
    "musescore": ("MuseScore", "乐谱编辑"), "obsidian": ("Obsidian", "笔记软件"),
    "mpv": ("mpv", "媒体播放器"), "3d-slicer": ("3D Slicer", "医学影像"),
    "vscode": ("Visual Studio Code", "Visual Studio Code"), "vs_code": ("Visual Studio Code", "Visual Studio Code"),
}
GENERIC_APP_IDS = {"browser", "writer", "calc", "office", "pdf_viewer", "pdfviewer", "file_manager", "file-manager", "image_viewer", "calendar", "mailhub", "terminal", "ubuntu", "desktop", "default", "base_setup", "init_state", "chrome_thunderbird", "chrome_vscode"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Reader:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.inputs: dict[str, dict] = {}

    def read(self, rel: str, expected: dict | None = None, role: str = "analysis_input") -> bytes:
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError(f"input outside project: {rel}")
        b = p.read_bytes()
        info = {"path": p.relative_to(self.root).as_posix(), "bytes": len(b), "sha256": sha(b), "role": role}
        if expected and (expected.get("bytes") != len(b) or expected.get("sha256") != info["sha256"]):
            raise ValueError(f"input hash mismatch: {rel}")
        old = self.inputs.get(info["path"])
        if old and (old["bytes"], old["sha256"]) != (info["bytes"], info["sha256"]):
            raise ValueError(f"input changed while reading: {rel}")
        self.inputs[info["path"]] = info
        return b

    def json(self, rel: str, expected: dict | None = None, role: str = "analysis_input"):
        return json.loads(self.read(rel, expected, role))

    def jsonl(self, rel: str, expected: dict | None = None, role: str = "analysis_input"):
        raw = self.read(rel, expected, role)
        rows = []
        for number, line in enumerate(raw.splitlines(), 1):
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise ValueError(f"invalid JSONL at {rel}:{number}: {exc}") from exc
        return rows


def load_package(reader: Reader, package_key: str):
    directory, filenames = PACKAGES[package_key]
    manifest_path = f"{directory}/manifest.json"
    manifest = reader.json(manifest_path, role="reused_source_manifest")
    items = manifest.get("outputs", [])
    by_name = {}
    for item in items:
        path = item.get("path", "")
        candidate = path if path.startswith("reports/") else f"{directory}/{path}"
        by_name[Path(path).name] = (candidate, item)
    loaded = {}
    for filename in filenames:
        if filename not in by_name:
            raise ValueError(f"{package_key} manifest does not register {filename}")
        path, expected = by_name[filename]
        data = reader.read(path, expected, role=f"reused_{package_key}_output")
        loaded[filename] = json.loads(data) if filename.endswith(".json") else [json.loads(x) for x in data.splitlines()]
    return loaded, manifest


def _command_value(unit):
    arg = unit.get("arguments")
    command = arg.get("command", arg.get("cmd")) if isinstance(arg, dict) else arg
    if unit.get("protocol") == "lingxi_heading_action" and isinstance(arg, dict):
        positional = arg.get("_positional", [])
        if positional and isinstance(positional[0], dict):
            command = positional[0].get("command")
    if str(unit.get("tool", "")).lower() == "sendshellinput" and isinstance(arg, dict):
        command = arg.get("input")
    return command


def _command_programs(unit, parser_module, operations_module):
    """Return statically identified command heads and explicit module runners."""
    command = _command_value(unit)
    if not isinstance(command, (str, list)):
        return [], None
    if str(unit.get("tool", "")).lower() == "bash" and isinstance(command, str):
        classified = operations_module.classify_command(command)
    else:
        classified = parser_module.classify_unit(unit)
    heads = classified.get("executables", [])
    programs = [{"raw_name": name, "count": 1, "entry_kind": "command_head"}
                for name in heads if name in PROGRAMS]
    segments = None
    if isinstance(command, list) and all(isinstance(x, str) for x in command):
        segments = [command]
    elif isinstance(command, str):
        stripped, _, _ = operations_module.strip_redirections(command)
        if stripped is not None:
            segments, _ = operations_module.shell_segments(stripped)
    operation = classified.get("operation", "unknown")
    if segments:
        for argv in segments:
            names = [PurePosixPath(x).name for x in argv]
            # An explicit Python module is a software identity, unlike a word in
            # a script argument or a search pattern.
            for i, token in enumerate(names):
                if token in {"python", "python3", "python3.6", "python3.7"}:
                    tail = names[i + 1:]
                    if "-m" in tail:
                        mi = tail.index("-m")
                        module_name = tail[mi + 1] if mi + 1 < len(tail) else ""
                        if module_name in {"pytest", "unittest"}:
                            programs.append({"raw_name": module_name, "count": 1, "entry_kind": "explicit_python_module"})
                    break
            # npx names the package executable explicitly only in this form.
            if names and names[0] == "npx":
                candidates = [x for x in names[1:] if not x.startswith("-")]
                if candidates and candidates[0] in {"jest", "vitest"}:
                    programs.append({"raw_name": candidates[0], "count": 1, "entry_kind": "explicit_npx_package"})
    # One command record contributes at most one incidence per software; exact
    # repeated command heads remain represented by the component count.
    compact = {}
    for item in programs:
        key = (item["raw_name"], item["entry_kind"])
        compact[key] = compact.get(key, 0) + item["count"]
    return [{"raw_name": name, "count": count, "entry_kind": kind} for (name, kind), count in compact.items()], operation


def _observe_call(call, parser_module, operations_module, group, task, path, trace_id, position, calls_by_id):
    programs, operation = _command_programs(call, parser_module, operations_module)
    if not programs:
        return []
    call_id = call.get("call_id")
    touched = []
    for item in programs:
        key = (group[0], group[1], item["raw_name"], item["entry_kind"])
        b = calls_by_id.setdefault(key, {"component_occurrences": 0, "call_keys": set(), "traces": set(), "tasks": set(),
                                          "operations": Counter(), "ids": Counter(), "examples": [], "paired": 0,
                                          "paired_errors": 0, "paired_exit_zero": 0, "paired_exit_nonzero": 0,
                                          "paired_exit_unknown": 0, "call_id_missing": 0})
        touched.append(key)
        position_key = json.dumps(position, sort_keys=True, ensure_ascii=False)
        call_key = (path, trace_id, position_key)
        b["component_occurrences"] += item["count"]
        b["call_keys"].add(call_key)
        b["traces"].add((group, trace_id if trace_id is not None else path))
        b["tasks"].add(task)
        b["operations"][operation] += 1
        if call_id:
            b["ids"][call_key] = str(call_id)
        else:
            b["call_id_missing"] += 1
        if len(b["examples"]) < 3:
            b["examples"].append({"path": path, "task": task, "trajectory_id": trace_id,
                                  "position": position, "entry_kind": item["entry_kind"]})
    return touched


def _recompute_coding_software(reader, rows, coverage, public_manifest, root, toolkit):
    """Reparse only registered saved-command-bearing files with the accepted parser."""
    sys.path.insert(0, str(root / "scripts"))
    parser_module = importlib.import_module("public_trace_operations")
    sys.path.insert(0, str(root / "src"))
    operations_module = importlib.import_module("agent_workload_characterization.analyzers.public_operations")
    analyzer_path = "src/agent_workload_characterization/analyzers/public_operations.py"
    analyzer_expected = next((x for x in public_manifest.get("inputs", []) if x.get("path") == analyzer_path), None)
    script_expected = next((x for x in public_manifest.get("inputs", []) if x.get("path") == "scripts/public_trace_operations.py"), None)
    for rel, expected in ((analyzer_path, analyzer_expected), ("scripts/public_trace_operations.py", script_expected)):
        if not expected:
            raise ValueError(f"PUBLIC-TRACE-OPERATIONS-v3 does not bind analysis source {rel}")
        reader.read(rel, expected, role="reused_public_operation_parser")

    coverage_by_path = {x["path"]: x for x in coverage["objects"]}
    wanted_swe = {r["location"]["path"] for r in rows
                  if r.get("source") == "SWE-bench" and r.get("saved_command_available_count", 0)}
    v3_inputs = {x["path"]: x for x in public_manifest.get("inputs", [])}
    aggregates = {}
    returns_summary = Counter()
    for path in sorted(wanted_swe):
        registered = coverage_by_path.get(path)
        if not registered:
            raise ValueError(f"command-bearing SWE-bench path is absent from v3 coverage: {path}")
        data = reader.read(path, {"bytes": registered["expected_bytes"], "sha256": registered["expected_sha256"]}, role="reparsed_registered_coding_command_source")
        group = registered["group"]
        parsed = parser_module._analyze_swebench_bytes(path, group, data)
        units_by_kind = parsed.get("units_by_kind", [])
        calls = [u for _, units in units_by_kind for u in units]
        id_calls = Counter(str(u.get("call_id")) for u in calls if u.get("call_id"))
        id_returns = Counter(str(r.get("call_id")) for r in parsed.get("returns", []) if r.get("call_id"))
        returns_by_id = defaultdict(list)
        for ret in parsed.get("returns", []):
            if ret.get("call_id"):
                returns_by_id[str(ret["call_id"])].append(ret)
        for call in calls:
            if not isinstance(_command_value(call), (str, list)):
                continue
            task = registered["task"]
            call_group = ("SWE-bench", group)
            touched = _observe_call(call, parser_module, operations_module, call_group, task, path, None,
                          call.get("position"), aggregates)
            cid = str(call.get("call_id")) if call.get("call_id") else None
            if cid and id_calls[cid] == id_returns[cid] == 1:
                ret = returns_by_id[cid][0]
                for key in touched:
                    bucket = aggregates[key]
                    bucket["paired"] += 1
                    bucket["paired_errors"] += int(ret.get("error_present") is True or ret.get("status") == "error")
                    exit_code = ret.get("exit_code")
                    if exit_code == 0: bucket["paired_exit_zero"] += 1
                    elif isinstance(exit_code, int) and not isinstance(exit_code, bool): bucket["paired_exit_nonzero"] += 1
                    else: bucket["paired_exit_unknown"] += 1
        returns_summary["SWE-bench_returns_saved"] += len(parsed.get("returns", []))

    wanted_re = defaultdict(set)
    for row in rows:
        if row.get("source") == "SWE-rebench" and row.get("saved_command_available_count", 0):
            wanted_re[row["location"]["path"]].add(row["location"].get("trajectory_id"))
    for path, trajectory_ids in sorted(wanted_re.items()):
        expected = v3_inputs.get(path)
        if not expected:
            raise ValueError(f"command-bearing SWE-rebench shard is absent from v3 manifest: {path}")
        compressed = reader.read(path, expected, role="reparsed_registered_coding_command_source")
        try:
            content = gzip.decompress(compressed).decode("utf-8")
        except Exception as exc:
            raise ValueError(f"cannot parse registered SWE-rebench shard {path}: {exc}") from exc
        for line_no, line in enumerate(content.split("\n"), 1):
            if not line.strip():
                continue
            trajectory = json.loads(line)
            trace_id = trajectory.get("trajectory_id")
            if trace_id not in trajectory_ids:
                continue
            participant = (trajectory.get("participant") or {}).get("key", "unknown")
            task = trajectory.get("instance_id", "unknown")
            events = trajectory.get("events", [])
            calls = [e for e in events if e.get("type") == "tool_call"]
            returns = [e for e in events if e.get("type") == "tool_result"]
            call_ids = Counter(str(e.get("tool_call_id")) for e in calls if e.get("tool_call_id"))
            return_ids = Counter(str(e.get("tool_call_id")) for e in returns if e.get("tool_call_id"))
            by_id = defaultdict(list)
            for ret in returns:
                if ret.get("tool_call_id"):
                    by_id[str(ret["tool_call_id"])].append(ret)
            for event_index, event in enumerate(events):
                if event.get("type") != "tool_call":
                    continue
                unit = {"tool": event.get("tool"), "arguments": event.get("input"),
                        "position": event_index, "call_id": event.get("tool_call_id")}
                if not isinstance(_command_value(unit), (str, list)):
                    continue
                group = ("SWE-rebench", participant)
                touched = _observe_call(unit, parser_module, operations_module, group, task, path, trace_id,
                              {"line": line_no, "event_index": event_index}, aggregates)
                cid = str(unit.get("call_id")) if unit.get("call_id") else None
                if cid and call_ids[cid] == return_ids[cid] == 1:
                    ret = by_id[cid][0]
                    for key in touched:
                        bucket = aggregates[key]
                        bucket["paired"] += 1
                        bucket["paired_errors"] += int(ret.get("error") is not None or ret.get("status") == "error")
                        bucket["paired_exit_unknown"] += 1
            returns_summary["SWE-rebench_returns_saved"] += len(returns)

    group_meta = {(g["source"], g["group"]): g for g in toolkit["coding"]["groups"]}
    group_task_denominator = defaultdict(set)
    for row in rows:
        if row.get("task") is not None:
            group_task_denominator[(row.get("source"), row.get("group"))].add(row["task"])
    out = []
    for (source, group, raw, entry_kind), b in sorted(aggregates.items()):
        meta = group_meta.get((source, group), {})
        program, purpose = PROGRAMS.get(raw, (raw, "explicit module/package in saved command"))
        if raw in {"pytest", "unittest", "jest", "vitest"} and entry_kind != "command_head":
            purpose = "explicit test-runner module/package in command arguments"
        out.append({"scene": "Coding/public", "source": source, "group": group, "raw_name": raw,
                    "software": program, "family": program, "purpose": purpose,
                    "evidence_type": "reparsed saved command argument; static only",
                    "task_count": len(b["tasks"]), "task_denominator": len(group_task_denominator[(source, group)]),
                    "trajectory_count": len(b["traces"]), "trajectory_denominator": meta.get("trajectory_count"),
                    "record_count": len(b["call_keys"]), "record_denominator": (meta.get("operations") or {}).get("denominator"),
                    "frequency": b["component_occurrences"], "frequency_unit": "static command component occurrences; not executions",
                    "component_calls": len(b["call_keys"]), "paired_return_ids": b["paired"],
                    "paired_return_error": b["paired_errors"], "paired_exit_zero": b["paired_exit_zero"],
                    "paired_exit_nonzero": b["paired_exit_nonzero"], "paired_exit_unknown": b["paired_exit_unknown"],
                    "call_id_missing": b["call_id_missing"], "operation_counts": dict(b["operations"]),
                    "entry_kind": entry_kind, "evidence_locations": b["examples"]})
    return out, dict(returns_summary)


def _local_coding_software(reader: Reader, root: Path, parser_module, operations_module):
    """Read only the nine accepted P1 run trajectories; parse calls, never execute."""
    base = "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3"
    manifest = reader.json(f"{base}/manifest.json", role="reused_local_coding_manifest")
    summary_info = manifest.get("outputs", {}).get("summary.json")
    if not summary_info:
        raise ValueError("accepted local Coding manifest does not bind summary.json")
    summary = reader.json(summary_info["path"], summary_info, role="reused_local_coding_summary")
    runs = summary.get("runs", [])
    selected_ids = summary.get("selected_run_ids", [])
    if len(runs) != 9 or len(selected_ids) != 9 or len(set(selected_ids)) != 9:
        raise ValueError("accepted local Coding summary does not identify nine unique selected runs")
    if {r.get("run_id") for r in runs} != set(selected_ids):
        raise ValueError("local Coding selected_run_ids do not match summary run records")
    expected_inputs = manifest.get("inputs", {})
    bins = {}
    run_tasks = {}
    task_runs = defaultdict(set)
    task_call_denominators = Counter()
    return_counts = Counter()
    for run in runs:
        run_id, task = run["run_id"], run["task"]
        run_dir = run["run_dir"].rstrip("/")
        rel = f"{run_dir}/mini_trajectory.json"
        expected = expected_inputs.get(rel)
        if not expected:
            raise ValueError(f"local Coding manifest does not bind selected trajectory {rel}")
        obj = reader.json(rel, expected, role="reparsed_local_coding_trajectory")
        messages = obj.get("messages") if isinstance(obj, dict) else None
        if not isinstance(messages, list):
            raise ValueError(f"local Coding trajectory has no messages list: {rel}")
        calls = []
        returns = []
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            if message.get("role") == "assistant":
                for call_index, call in enumerate(message.get("tool_calls") or []):
                    fn = call.get("function") if isinstance(call, dict) else None
                    if not isinstance(fn, dict) or fn.get("name") != "bash":
                        continue
                    raw_arguments = fn.get("arguments")
                    try:
                        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else None
                    except json.JSONDecodeError:
                        arguments = None
                    calls.append({"tool": "bash", "arguments": arguments, "argument_error": "missing_or_unparseable_function_arguments" if arguments is None else None, "call_id": call.get("id"),
                                  "position": {"message_index": message_index, "call_index": call_index}})
            if message.get("role") == "tool" and message.get("tool_call_id"):
                extra = message.get("extra") or {}
                returns.append({"call_id": message["tool_call_id"], "returncode": extra.get("returncode"),
                                "exception_present": bool(extra.get("exception_info"))})
        run_tasks[run_id] = task
        task_runs[task].add(run_id)
        task_call_denominators[task] += len(calls)
        call_counts = Counter(str(c["call_id"]) for c in calls if c.get("call_id"))
        return_by_id = defaultdict(list)
        for ret in returns:
            return_by_id[str(ret["call_id"])].append(ret)
        for call in calls:
            group = ("Coding/local", task)
            touched = _observe_call(call, parser_module, operations_module, group, task, rel, run_id,
                                    call["position"], bins)
            cid = str(call["call_id"]) if call.get("call_id") else None
            if cid and call_counts[cid] == 1 and len(return_by_id[cid]) == 1:
                ret = return_by_id[cid][0]
                for key in touched:
                    bucket = bins[key]
                    bucket["paired"] += 1
                    bucket["paired_errors"] += int(ret["exception_present"] or (isinstance(ret["returncode"], int) and ret["returncode"] != 0))
                    if isinstance(ret["returncode"], int) and not isinstance(ret["returncode"], bool) and ret["returncode"] == 0:
                        bucket["paired_exit_zero"] += 1
                    elif isinstance(ret["returncode"], int) and not isinstance(ret["returncode"], bool):
                        bucket["paired_exit_nonzero"] += 1
                    else:
                        bucket["paired_exit_unknown"] += 1
        call_ids = Counter(str(c["call_id"]) for c in calls if c.get("call_id"))
        result_ids = Counter(str(r["call_id"]) for r in returns if r.get("call_id"))
        return_counts["calls"] += len(calls)
        return_counts["calls_with_unparsed_arguments"] += sum(1 for c in calls if c.get("argument_error"))
        return_counts["returns"] += len(returns)
        return_counts["unique_id_pairs"] += sum(1 for cid, n in call_ids.items() if n == 1 and result_ids[cid] == 1)
        return_counts["call_ids_missing"] += sum(1 for c in calls if not c.get("call_id"))
        return_counts["return_ids_missing"] += sum(1 for r in returns if not r.get("call_id"))
        return_counts["duplicate_call_ids"] += sum(n - 1 for n in call_ids.values() if n > 1)
        return_counts["duplicate_return_ids"] += sum(n - 1 for n in result_ids.values() if n > 1)
        return_counts["orphan_return_records"] += sum(n for cid, n in result_ids.items() if cid not in call_ids)
        return_counts["calls_without_unique_return"] += len(calls) - sum(1 for cid, n in call_ids.items() if n == 1 and result_ids[cid] == 1)
        return_counts["returns_without_unique_call"] += len(returns) - sum(1 for cid, n in result_ids.items() if n == 1 and call_ids[cid] == 1)
    out = []
    for (source, task, raw, entry_kind), b in sorted(bins.items()):
        software, purpose = PROGRAMS.get(raw, (raw, "explicit command component in saved bash argument"))
        if raw in {"pytest", "unittest", "jest", "vitest"} and entry_kind != "command_head":
            purpose = "explicit test-runner module/package in command arguments"
        n_tasks = len({r["task"] for r in runs})
        n_runs = len(task_runs[task])
        out.append({"scene": "Coding/local", "source": "P1-12-CODING-REPEAT-01", "group": task,
                    "raw_name": raw, "software": software, "family": software, "purpose": purpose,
                    "evidence_type": "saved structured bash tool_call; static command component",
                    "task_count": 1, "task_denominator": n_tasks, "trajectory_count": len(b["traces"]),
                    "trajectory_denominator": n_runs, "record_count": len(b["call_keys"]),
                    "record_denominator": task_call_denominators[task], "frequency": b["component_occurrences"],
                    "frequency_unit": "static command component occurrences; not process executions",
                    "component_calls": len(b["call_keys"]), "paired_return_ids": b["paired"],
                    "paired_return_error": b["paired_errors"], "paired_exit_zero": b["paired_exit_zero"],
                    "paired_exit_nonzero": b["paired_exit_nonzero"], "paired_exit_unknown": b["paired_exit_unknown"],
                    "call_id_missing": b["call_id_missing"], "entry_kind": entry_kind,
                    "evidence_locations": b["examples"]})
    return out, dict(return_counts), {task: {"runs": len(task_runs[task]), "bash_tool_calls": task_call_denominators[task]}
                                      for task in sorted(task_runs)}


def _coding_software(rows, toolkit):
    meta = {(g["source"], g["group"]): g for g in toolkit["coding"]["groups"]}
    buckets = {}
    group_tasks = defaultdict(set)
    for row in rows:
        if row.get("unit_kind") in {"saved_retrieval_event", "saved_process_node"}:
            continue
        group = (row.get("source", "unknown"), row.get("group", "unknown"))
        loc = row.get("location") or {}
        trace_id = loc.get("trajectory_id")
        trace_key = (group, trace_id if trace_id is not None else (loc.get("path"), row.get("task")))
        task_key = row.get("task")
        if task_key is not None:
            group_tasks[group].add(task_key)
        for raw_name, value in (row.get("executable_counts") or {}).items():
            if raw_name not in PROGRAMS:
                continue
            key = (group, raw_name)
            b = buckets.setdefault(key, {"occurrences": 0, "traces": set(), "tasks": set(), "evidence": []})
            count = int(value)
            b["occurrences"] += count
            b["traces"].add(trace_key)
            if task_key is not None:
                b["tasks"].add(task_key)
            if len(b["evidence"]) < 3:
                b["evidence"].append({"path": loc.get("path"), "line": loc.get("line"), "trajectory_id": trace_id, "unit_kind": row.get("unit_kind")})
    output = []
    for (group, raw), b in sorted(buckets.items()):
        source, submission = group
        descriptor = meta.get(group, {})
        denom = int(descriptor.get("trajectory_count") or len(group_tasks[group]))
        canonical, purpose = PROGRAMS[raw]
        output.append({"scene": "Coding/public", "source": source, "group": submission,
                       "raw_name": raw, "software": canonical, "family": canonical,
                       "purpose": purpose, "evidence_type": "saved command head from static parser",
                       "entry_kind": "shell_entry" if raw in {"bash", "sh"} else "command_head",
                       "task_count": len(b["tasks"]), "task_denominator": len(group_tasks[group]),
                       "trajectory_count": len(b["traces"]), "trajectory_denominator": denom,
                       "record_count": None, "record_denominator": None,
                       "frequency": b["occurrences"], "frequency_unit": "static command-head component occurrences; not executions",
                       "return_linkage": "per-component return/success is not inferable from grouped counts",
                       "evidence_locations": b["evidence"]})
    return output


def _model_task_key(row):
    p = PurePosixPath(row.get("source_file", ""))
    parts = p.parts
    if "tasks" in parts:
        i = parts.index("tasks")
        model = parts[i - 1] if i else "unknown"
        task = parts[i + 1] if i + 1 < len(parts) else row.get("task_key")
        return model, str(task)
    return "unknown", str(row.get("task_key", "unknown"))


def _osworld_apps(task_rows, trajectory_rows):
    pairs = {_model_task_key(r) for r in trajectory_rows}
    if len(pairs) != 755:
        raise ValueError(f"expected 755 unique model×task records in accepted OSWorld analysis, got {len(pairs)}")
    apps = defaultdict(lambda: {"tasks": set(), "records": set(), "fields": set(), "evidence": []})
    task_to_apps = {}
    for task in task_rows:
        tid = str(task.get("task_key", task.get("task_id")))
        entries = defaultdict(set)
        for name in task.get("related_apps") or []:
            if isinstance(name, str) and name.strip():
                entries[name.strip()].add("related_apps")
        snap = task.get("snapshot")
        if isinstance(snap, str) and snap.strip():
            entries[snap.strip()].add("snapshot")
        task_to_apps[tid] = set(entries)
        evidence = task.get("evidence") or {}
        for raw, fields in entries.items():
            a = apps[raw]
            a["tasks"].add(tid)
            a["fields"].update(fields)
            if len(a["evidence"]) < 3:
                refs = [evidence.get(f) for f in sorted(fields)]
                a["evidence"].append({"task_key": tid, "references": refs})
    for model, task in pairs:
        for raw in task_to_apps.get(task, set()):
            apps[raw]["records"].add((model, task))
    rows = []
    family_tasks = defaultdict(set)
    for raw, a in sorted(apps.items(), key=lambda z: (-len(z[1]["tasks"]), z[0])):
        known = APP_PRODUCTS.get(raw)
        status = "named_application_identifier" if known else ("generic_or_ambiguous_label" if raw in GENERIC_APP_IDS else "unmapped_task_label")
        if known:
            family_tasks[known[1]].update(a["tasks"])
        rows.append({"scene": "Computer/Office", "source": "OSWorld task definitions", "group": "declared app labels",
                     "raw_name": raw, "software": known[0] if known else None,
                     "family": known[1] if known else None, "purpose": "task-declared application/snapshot; not proof of launch",
                     "evidence_type": "task declaration", "task_count": len(a["tasks"]), "task_denominator": len(task_rows),
                     "trajectory_count": len(a["records"]), "trajectory_denominator": len(pairs),
                     "record_count": None, "record_denominator": None, "frequency": None,
                     "frequency_unit": "not a call frequency", "identity_status": status,
                     "declaration_fields": sorted(a["fields"]), "runtime_use_status": "unknown; declarations are not runtime evidence",
                     "evidence_locations": a["evidence"]})
    families = []
    for family, tasks in sorted(family_tasks.items(), key=lambda z: (-len(z[1]), z[0])):
        records = {(model, task) for model, task in pairs if task in tasks}
        families.append({"scene": "Computer/Office", "source": "OSWorld task definitions", "group": "deduplicated declared application family",
                         "raw_name": family, "software": family, "family": family,
                         "purpose": "family-level declaration coverage; not runtime use", "evidence_type": "deduplicated task declaration family",
                         "task_count": len(tasks), "task_denominator": len(task_rows), "trajectory_count": len(records),
                         "trajectory_denominator": len(pairs), "record_count": None, "record_denominator": None,
                         "frequency": None, "frequency_unit": "not a call frequency", "identity_status": "family coverage; raw aliases remain separately listed"})
    return rows, pairs, families


def _hepm_tools(rows):
    buckets = {}
    denominators = defaultdict(set)
    for row in rows:
        group = row["group"]
        scenario = row.get("scenario")
        if scenario is not None:
            denominators[group].add(scenario)
        for name, count in (row.get("native_identity_counts") or {}).items():
            key = (group, name)
            b = buckets.setdefault(key, {"calls": 0, "trajectories": set(), "examples": []})
            b["calls"] += int(count)
            if scenario is not None:
                b["trajectories"].add(scenario)
            if len(b["examples"]) < 3:
                b["examples"].append({"scenario": scenario, "group_directory": row.get("group_directory")})
    out = []
    for (group, name), b in sorted(buckets.items()):
        n = len(denominators[group])
        helper = name == "summarize_the_task"
        out.append({"scene": "Assistant/public H-EPM", "source": "H-EPM adapted ToolSandbox", "group": group,
                    "raw_name": name, "software": "ToolSandbox simulated interface", "family": "simulation tool namespace",
                    "purpose": "framework summary helper" if helper else "simulated business/API operation; external product unknown",
                    "evidence_type": "saved structured tool call identity", "task_count": len(b["trajectories"]), "task_denominator": n,
                    "trajectory_count": len(b["trajectories"]), "trajectory_denominator": n,
                    "record_count": b["calls"], "record_denominator": None, "frequency": b["calls"],
                    "frequency_unit": "saved calls", "external_software_status": "not evidenced",
                    "evidence_locations": b["examples"]})
    return out


def _local_assistant(rows):
    buckets = {}
    all_runs = {row.get("run_id") for row in rows}
    all_tasks = {row.get("task") for row in rows}
    for row in rows:
        behavior = row.get("behavior") or {}
        for call in ((behavior.get("tool_calls") or {}).get("details") or []):
            name = call.get("tool_name") or "unknown"
            role = call.get("role") or "unknown"
            key = (name, role)
            b = buckets.setdefault(key, {"runs": set(), "tasks": set(), "calls": 0, "ok": 0, "examples": []})
            b["runs"].add(row["run_id"]); b["tasks"].add(row["task"]); b["calls"] += 1
            b["ok"] += int(call.get("ok") is True)
            if len(b["examples"]) < 3:
                b["examples"].append({"run_id": row["run_id"], "event_id": call.get("event_id")})
    out = []
    for (name, role), b in sorted(buckets.items()):
        out.append({"scene": "Assistant/local", "source": "ToolSandbox Assistant Repeat-01", "group": role,
                    "raw_name": name, "software": "ToolSandbox simulated interface", "family": "simulation tool namespace",
                    "purpose": "simulated business tool" if name != "end_conversation" else "simulated conversation control",
                    "evidence_type": "saved local run event", "task_count": len(b["tasks"]), "task_denominator": len(all_tasks),
                    "trajectory_count": len(b["runs"]), "trajectory_denominator": len(all_runs),
                    "record_count": b["calls"], "record_denominator": None, "frequency": b["calls"],
                    "frequency_unit": "saved logical tool calls", "ok_count": b["ok"],
                    "evidence_locations": b["examples"]})
    return out


DOCOPS_LIBS = {
    "xlsx_read_sheet": ("openpyxl", "表格读取"), "xlsx_write_cells": ("openpyxl", "单元格写入"),
    "xlsx_set_formula": ("openpyxl", "公式写入"), "xlsx_highlight_cells": ("openpyxl", "单元格格式"),
    "ppt_list_slides": ("python-pptx", "幻灯片读取"), "ppt_replace_text": ("python-pptx", "幻灯片文本编辑"),
    "ppt_reorder_slides": ("python-pptx", "幻灯片排序"), "ppt_delete_slides": ("python-pptx", "幻灯片删除"),
    "ppt_set_bullets": ("python-pptx", "项目符号编辑"),
    "pdf_extract_text": ("pdfplumber", "PDF文本抽取"), "pdf_reorder_pages": ("pypdf", "PDF页面重排"),
    "pdf_delete_pages": ("pypdf", "PDF页面删除"),
}

DOCOPS_FUNCTIONS = {
    "xlsx_read_sheet": ("tool_xlsx_read_sheet", "openpyxl", "load_workbook"),
    "xlsx_write_cells": ("tool_xlsx_write_cells", "openpyxl", "load_workbook"),
    "xlsx_set_formula": ("tool_xlsx_set_formula", "openpyxl", "load_workbook"),
    "xlsx_highlight_cells": ("tool_xlsx_highlight_cells", "openpyxl", "PatternFill"),
    "ppt_list_slides": ("tool_ppt_list_slides", "pptx", "Presentation"),
    "ppt_replace_text": ("tool_ppt_replace_text", "pptx", "Presentation"),
    "ppt_reorder_slides": ("tool_ppt_reorder_slides", "pptx", "Presentation"),
    "ppt_delete_slides": ("tool_ppt_delete_slides", "pptx", "Presentation"),
    "ppt_set_bullets": ("tool_ppt_set_bullets", "pptx", "Presentation"),
    "pdf_extract_text": ("tool_pdf_extract_text", "pdfplumber", "pdfplumber"),
    "pdf_reorder_pages": ("tool_pdf_reorder_pages", "pypdf", "PdfWriter"),
    "pdf_delete_pages": ("tool_pdf_delete_pages", "pypdf", "PdfWriter"),
}


def validate_docops_runtime(source: str):
    """Statically bind called interface names to TOOLS handlers and library use."""
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    imports = set()
    tool_map = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in node.targets) and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and isinstance(v, ast.Name):
                    tool_map[k.value] = v.id
    lines = {}
    for tool, (func, module, symbol) in DOCOPS_FUNCTIONS.items():
        if tool_map.get(tool) != func or func not in functions:
            raise ValueError(f"DocOps interface-to-handler mapping is not statically confirmed: {tool}")
        if module not in imports:
            raise ValueError(f"DocOps runtime does not import mapped library {module} for {tool}")
        function_text = ast.get_source_segment(source, functions[func]) or ""
        if symbol not in function_text:
            raise ValueError(f"DocOps handler does not reference mapped symbol {symbol}: {tool}")
        lines[tool] = {"function": func, "function_line": functions[func].lineno, "module": module, "symbol": symbol}
    docx_functions = {}
    docx_handlers = {"inspect_document": "tool_inspect_document", "word_replace_text": "tool_word_replace_text",
                     "word_insert_table_column": "tool_word_insert_table_column"}
    for tool, func in docx_handlers.items():
        node = functions.get(func)
        if tool_map.get(tool) != func or not node:
            raise ValueError(f"DocOps python-docx interface mapping is not statically confirmed: {tool}")
        if "Document" in (ast.get_source_segment(source, node) or ""):
            docx_functions[func] = node.lineno
    if "docx" not in imports or not docx_functions:
        raise ValueError("DocOps python-docx implementation reference is not statically confirmed")
    lines["__python_docx_reference__"] = {"module": "docx", "functions": docx_functions}
    return lines


def _docops(rows, runtime_source: str, runtime_sha: str, implementation_map):
    buckets = {}
    all_runs = {row.get("run_id") for row in rows}
    all_tasks = {row.get("task_key") for row in rows}
    for row in rows:
        for call in row.get("tools", []):
            name = call.get("name", "unknown")
            role = call.get("role") or "unknown"
            key = (row["task_key"], name, role)
            b = buckets.setdefault(key, {"runs": set(), "calls": 0, "ok": 0, "examples": []})
            b["runs"].add(row["run_id"]); b["calls"] += 1; b["ok"] += int(call.get("ok") is True)
            if len(b["examples"]) < 3:
                b["examples"].append({"run_id": row["run_id"], "event_id": call.get("event_id"), "role": call.get("role")})
    out = []
    for (task, tool, role), b in sorted(buckets.items()):
        lib, purpose = DOCOPS_LIBS.get(tool, (None, "用途由工具接口名/保存活动字段限定"))
        mapped = tool in implementation_map
        if lib and not mapped:
            lib, purpose = None, "已记录项目工具接口；实现库未绑定到可核验运行源码"
        out.append({"scene": "Computer/Office", "source": "DocOps local Repeat-02", "group": task,
                    "raw_name": tool, "software": lib or "项目自有工具接口", "family": "document processing library" if lib else "project tool API",
                    "purpose": purpose, "evidence_type": "saved tool call and terminal result status" if lib else ("saved tool interface; implementation mapping unavailable" if DOCOPS_LIBS.get(tool) else "saved tool interface"),
                    "task_count": 1, "task_denominator": len(all_tasks), "trajectory_count": len(b["runs"]), "trajectory_denominator": len(all_runs),
                    "record_count": b["calls"], "record_denominator": None, "frequency": b["calls"],
                    "frequency_unit": "saved tool calls", "ok_count": b["ok"], "role": role,
                    "runtime_source": runtime_source if lib else None, "runtime_source_sha256": runtime_sha if lib else None,
                    "runtime_handler": implementation_map.get(tool, {}).get("function"),
                    "runtime_handler_line": implementation_map.get(tool, {}).get("function_line"),
                    "library_module": implementation_map.get(tool, {}).get("module"),
                    "library_symbol": implementation_map.get(tool, {}).get("symbol"),
                    "library_version": "unknown; no runtime package-version evidence in selected report",
                    "runtime_source_location": {"path": runtime_source, "line": implementation_map.get(tool, {}).get("function_line")} if lib else None,
                    "evidence_locations": b["examples"]})
    # The implementation supports Word, but Repeat-02 made no Word-specific call.
    out.append({"scene": "Computer/Office", "source": "DocOps implementation reference", "group": "not invoked in Repeat-02",
                "raw_name": "python-docx", "software": "python-docx", "family": "DOCX processing library",
                "purpose": "document_tools_runtime.py DOCX inspection/edit functions exist; not observed in selected 9 runs",
                "evidence_type": "implementation reference only", "task_count": 0, "task_denominator": len(all_tasks),
                "trajectory_count": 0, "trajectory_denominator": len(all_runs), "record_count": 0, "record_denominator": None,
                "frequency": None, "frequency_unit": "not a runtime-use count", "library_version": "unknown",
                "runtime_source": runtime_source, "runtime_source_sha256": runtime_sha,
                "runtime_source_location": {"path": runtime_source, "functions": implementation_map.get("__python_docx_reference__", {}).get("functions", {})},
                "evidence_locations": []})
    return out


def build(root: Path):
    root = root.resolve()
    reader = Reader(root)
    package_results = {k: load_package(reader, k) for k in PACKAGES}
    packages = {k: v[0] for k, v in package_results.items()}
    package_manifests = {k: v[1] for k, v in package_results.items()}
    public = packages["public_operations_v3"]
    osw = packages["osworld_behavior_v3"]
    hepm = packages["hepm_behavior_v2"]
    docops = packages["docops_repeat02"]
    tsb = packages["toolsandbox_assistant_repeat01"]
    macro = packages["agentx_applied_macro"]["summary.json"]

    reparsed_coding, coding_returns = _recompute_coding_software(reader, public["per_trajectory.jsonl"],
                    public["coverage.json"], package_manifests["public_operations_v3"], root,
                    public["toolkits.json"])
    # SWE-bench's accepted aggregate is authoritative for mixed text/structured
    # interfaces; raw argv rereads supplement explicit module/package names.
    # SWE-rebench is reparsed from registered JSONL events, retaining native IDs
    # and separately counted return records.
    accepted_coding = _coding_software(public["per_trajectory.jsonl"], public["toolkits.json"])
    coding = [row for row in accepted_coding if row["source"] == "SWE-bench"]
    coding.extend(row for row in reparsed_coding if row["source"] == "SWE-rebench")
    coding.extend(row for row in reparsed_coding if row["source"] == "SWE-bench" and row.get("entry_kind") != "command_head")
    sys.path.insert(0, str(root / "scripts"))
    sys.path.insert(0, str(root / "src"))
    local_parser = importlib.import_module("public_trace_operations")
    local_operations = importlib.import_module("agent_workload_characterization.analyzers.public_operations")
    local_coding, local_coding_calls, local_coding_task_counts = _local_coding_software(reader, root, local_parser, local_operations)
    coding.extend(local_coding)
    os_apps, os_pairs, os_families = _osworld_apps(osw["task_semantics.jsonl"], osw["per_trajectory.jsonl"])

    runtime_path = "references/repos/DocOps/harnesses/document_tools_runtime.py"
    runtime_bytes = reader.read(runtime_path, role="runtime_implementation_mapping")
    runtime_text = runtime_bytes.decode("utf-8")
    docops_input = next((x for x in package_manifests["docops_repeat02"].get("inputs", []) if x.get("path") == runtime_path), None)
    if not docops_input or docops_input.get("sha256") != sha(runtime_bytes):
        raise ValueError("DocOps runtime source is not identical to the accepted analysis manifest")
    source_sha = sha(runtime_bytes)
    docops_map = validate_docops_runtime(runtime_text)
    docops_rows = _docops(docops["per_run.jsonl"], runtime_path, source_sha, docops_map)
    hepm_rows = _hepm_tools(hepm["per_trajectory.jsonl"])
    tsb_rows = _local_assistant(tsb["per_run.jsonl"])

    software_rows = coding + os_apps + os_families + hepm_rows + tsb_rows + docops_rows
    evidence = []
    for row in coding + os_apps + hepm_rows + tsb_rows + docops_rows:
        if row.get("evidence_locations"):
            evidence.append({"scene": row["scene"], "source": row["source"], "group": row["group"],
                             "raw_name": row["raw_name"], "evidence_type": row["evidence_type"],
                             "count": row.get("frequency") if row.get("frequency") is not None else row.get("trajectory_count"),
                             "location_samples": row["evidence_locations"]})
    for row in docops_rows:
        if row.get("runtime_source_location"):
            evidence.append({"scene": row["scene"], "source": row["source"], "group": row["group"],
                             "raw_name": row["raw_name"], "evidence_type": "runtime implementation mapping",
                             "count": row.get("frequency"), "location_samples": [row["runtime_source_location"]]})

    coding_groups = defaultdict(list)
    source_group_tasks = defaultdict(set)
    for source_row in public["per_trajectory.jsonl"]:
        source_group_tasks[(source_row.get("source"), source_row.get("group"))].add(source_row.get("task"))
    for row in coding:
        coding_groups[row["source"], row["group"]].append(row)
    group_rows = []
    all_coding_groups = {(x["source"], x["group"]): x for x in public["toolkits.json"]["coding"]["groups"]}
    for task, task_data in local_coding_task_counts.items():
        all_coding_groups[("Coding/local", task)] = {"trajectory_count": task_data["runs"], "operations": {"denominator": task_data["bash_tool_calls"]}}
        source_group_tasks[("Coding/local", task)].add(task)
    for (source, group), meta in sorted(all_coding_groups.items()):
        items = coding_groups[(source, group)]
        top = sorted(items, key=lambda x: (-x["frequency"], x["raw_name"]))[:8]
        group_rows.append({"source": source, "group": group, "trajectory_denominator": meta.get("trajectory_count"),
                           "task_denominator": len(source_group_tasks[(source, group)]),
                           "record_denominator": (meta.get("operations") or {}).get("denominator"),
                           "software_component_occurrences": sum(x["frequency"] for x in items),
                           "top_programs": [{"raw_name": x["raw_name"], "entry_kind": x.get("entry_kind"), "frequency": x["frequency"], "trajectory_count": x["trajectory_count"]} for x in top]})

    counts = {
        "coding_analysis_rows": len(public["per_trajectory.jsonl"]),
        "coding_group_count": len({(r["source"], r["group"]) for r in public["per_trajectory.jsonl"]}),
        "coding_public_groups_with_identified_software": sum(bool(coding_groups[(x["source"], x["group"])]) for x in public["toolkits.json"]["coding"]["groups"]),
        "local_coding_run_count": sum(item["runs"] for item in local_coding_task_counts.values()),
        "local_coding_task_count": len(local_coding_task_counts),
        "local_coding_bash_call_count": sum(item["bash_tool_calls"] for item in local_coding_task_counts.values()),
        "osworld_task_definitions": len(osw["task_semantics.jsonl"]),
        "osworld_model_task_records": len(os_pairs),
        "osworld_runtime_app_records_checked": len(os_pairs),
        "osworld_runtime_specific_product_records": "unknown; saved actions identify generic desktop interfaces, not the foreground application",
        "docops_runs": len(docops["per_run.jsonl"]),
        "docops_run_tasks": len({r["task_key"] for r in docops["per_run.jsonl"]}),
        "toolsandbox_assistant_runs": len(tsb["per_run.jsonl"]),
        "hepm_groups": len({r["group"] for r in hepm["per_trajectory.jsonl"]}),
        "hepm_trajectories_per_group": sorted({sum(1 for r in hepm["per_trajectory.jsonl"] if r["group"] == g) for g in {x["group"] for x in hepm["per_trajectory.jsonl"]}}),
        "agentx_trace_count_reused": macro["sources"]["AgentX"]["summary"]["trace_count"],
        "applied_compute_template_counts_reused": {name: item["template_count"] for name, item in macro["sources"]["Applied Compute"]["summary"].items() if isinstance(item, dict) and "template_count" in item},
        "agentx_concrete_tool_names": "not available from this filtered request-flow release",
        "applied_compute_concrete_tool_names": "not available from workload template fields",
        "video_concrete_software_names": "not available in selected accepted public-trace summaries",
    }
    toolkit = {
        "schema": "public-trace-software-toolkits-v1",
        "evidence_layers": {
            "saved_command": "Coding software heads are statically parsed saved command components from PUBLIC-TRACE-OPERATIONS-v3; command occurrence != successful execution.",
            "execution_return": "Return evidence is kept separate; grouped program-component counts cannot be joined to a particular return unless a direct ID-level record is retained.",
        "task_declaration": "OSWorld applications come from related_apps/snapshot declarations, deduplicated per task; the same labels are projected onto the accepted model×task records.",
            "implementation": "DocOps libraries are counted only for specifically named interfaces mapped to the frozen/readback-verified runtime implementation; generic inspect_document is not attributed to one library.",
            "unknown": "No product/software is inferred from file extensions, generic computer actions, package requirements, or workload-template placeholders.",
        },
        "counting": {"coding_frequency_unit": "static command-head component occurrences", "coding_presence_unit": "unique saved trajectory IDs within source/group", "coding_task_denominator": "unique task identifiers within each source/group", "osworld_task_denominator": len(osw["task_semantics.jsonl"]), "osworld_model_task_denominator": len(os_pairs), "hepm_denominator_by_group": {group: len({r.get("scenario") for r in hepm["per_trajectory.jsonl"] if r.get("group") == group and r.get("scenario") is not None}) for group in sorted({r["group"] for r in hepm["per_trajectory.jsonl"]})}, "local_docops_run_denominator": len({r.get("run_id") for r in docops["per_run.jsonl"]}), "local_docops_task_denominator": len({r.get("task_key") for r in docops["per_run.jsonl"]}), "local_assistant_run_denominator": len({r.get("run_id") for r in tsb["per_run.jsonl"]}), "local_assistant_task_denominator": len({r.get("task") for r in tsb["per_run.jsonl"]}), "aliases": "raw identifiers preserved; only explicitly listed OSWorld exact product IDs receive a display/family mapping; ambiguous labels remain unmapped"},
        "counts": counts,
        "coding_reparse": {"saved_return_records_in_reparsed_command_files": coding_returns,
                           "local_coding_calls_and_returns": local_coding_calls,
                           "local_coding_source": "nine explicit mini_trajectory.json files SHA-256-bound by accepted P1-12 characterization manifest",
                           "command_head_source": "reused from accepted PUBLIC-TRACE-OPERATIONS-v3 grouped static parser output",
                           "raw_reparse_use": "SWE-rebench native call events and command-bearing SWE-bench files; returns paired only by unique native ID"},
        "coding_groups": group_rows,
        "local_coding_task_counts": local_coding_task_counts,
        "osworld_runtime_app_identity": {"status": "unknown", "records_checked": len(os_pairs), "reason": "the accepted trajectory behavior output records generic desktop action/interface and static GUI code, but does not identify the foreground application per action"},
        "docops_interface_implementation_map": docops_map,
        "osworld_application_family_coverage": os_families,
        "toolkits": software_rows,
        "limitations": [
            "Coding package exposes grouped static executable heads, not per-component result association or proof of process launch; command conditionals and pipelines remain syntactic.",
            "PUBLIC-TRACE-OPERATIONS-v3 rows from different submissions/formats and participants are not pooled into a shared call denominator.",
            "OSWorld application counts are task declarations; the historical task revision binding is unknown and no declared app is treated as launched.",
            "H-EPM and local ToolSandbox names refer to simulated business/tool APIs, not real external products or services.",
            "DocOps library package versions are unknown; imported libraries are not counted as used unless a mapped interface was invoked in the selected run.",
            "Word/python-docx is an implementation reference but has no Word-specific invocation in the selected Office Repeat-02 nine-run batch.",
            "AgentX is a filtered request-flow corpus, Applied Compute contains production-derived templates, and the selected Video summaries contain no reliable concrete software identities.",
            "Local P1 Coding command names are re-read only from nine manifest-bound mini_trajectory files; command component counts are static and do not prove process launches. The local batch is reported separately from public Coding submissions.",
        ],
    }
    return {"software_toolkits": toolkit, "rows": software_rows, "evidence": evidence,
            "inputs": sorted(reader.inputs.values(), key=lambda x: x["path"]), "source_code_path": "scripts/public_trace_software_toolkits.py", "_root": root}


def _csv_rows(rows):
    fields = ["scene", "source", "group", "raw_name", "software", "family", "purpose", "evidence_type", "identity_status", "entry_kind", "role", "task_count", "task_denominator", "trajectory_count", "trajectory_denominator", "record_count", "record_denominator", "frequency", "frequency_unit", "component_calls", "call_id_missing", "paired_return_ids", "paired_return_error", "paired_exit_zero", "paired_exit_nonzero", "paired_exit_unknown", "ok_count", "runtime_use_status", "external_software_status", "library_version", "runtime_source", "runtime_source_sha256", "runtime_handler", "runtime_handler_line", "library_module", "library_symbol", "declaration_fields", "return_linkage"]
    return fields


def write_outputs(report: dict, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    (output / "software_toolkits.json").write_text(json.dumps(report["software_toolkits"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "software_toolkits.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_csv_rows(report["rows"]), extrasaction="ignore")
        writer.writeheader(); writer.writerows(report["rows"])
    with (output / "evidence.jsonl").open("w", encoding="utf-8") as f:
        for row in report["evidence"]:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (output / "summary.md").write_text(render_summary(report["software_toolkits"]), encoding="utf-8")
    manifest = {"schema": "public-trace-software-toolkits-manifest-v1", "input_scope": "accepted analysis outputs, registered command-bearing public Coding files, and nine manifest-selected local Coding mini_trajectory files; all command analysis is static", "inputs": report["inputs"], "analysis_code": [], "outputs": [], "manifest_self_hash": "excluded"}
    for rel in ["scripts/public_trace_software_toolkits.py"]:
        b = (PROJECT / rel).read_bytes(); manifest["analysis_code"].append({"path": rel, "bytes": len(b), "sha256": sha(b)})
    for name in ("summary.md", "software_toolkits.csv", "software_toolkits.json", "evidence.jsonl"):
        b = (output / name).read_bytes(); manifest["outputs"].append({"path": name, "bytes": len(b), "sha256": sha(b)})
    for item in manifest["inputs"]:
        b = (report["_root"] / item["path"]).read_bytes()
        if len(b) != item["bytes"] or sha(b) != item["sha256"]:
            raise ValueError(f"input changed before output manifest write: {item['path']}")
    for item in manifest["analysis_code"]:
        b = (PROJECT / item["path"]).read_bytes()
        if len(b) != item["bytes"] or sha(b) != item["sha256"]:
            raise ValueError(f"analysis code changed while writing: {item['path']}")
    for item in manifest["outputs"]:
        b = (output / item["path"]).read_bytes()
        if len(b) != item["bytes"] or sha(b) != item["sha256"]:
            raise ValueError(f"output readback mismatch: {item['path']}")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_summary(data):
    rows = data["toolkits"]
    coding_groups = data["coding_groups"]
    lines = ["# 场景—软件与工具栈（公开轨迹及本地实验）", "",
             "本报告按证据层分表，不把接口名、软件名、声明应用和实现库混合成一个排行榜。静态命令组件只证明文本记录中出现了命令头；OSWorld任务应用是任务声明；DocOps库只有在具体接口被调用且运行源码绑定后才记为本批实现使用。", "",
             "## 范围与口径", "",
             f"- Coding公开语料：复用 PUBLIC-TRACE-OPERATIONS-v3 的 {data['counts']['coding_analysis_rows']:,} 条逐轨迹分析行和 {data['counts']['coding_group_count']} 个来源/提交组；其中 {data['counts']['coding_public_groups_with_identified_software']} 组出现本轮识别名单内的程序名，其余不等于无工具。另对本地P1-12批 {data['counts']['local_coding_run_count']} 个run、{data['counts']['local_coding_task_count']}个任务重读已登记trajectory，独立分表。程序频数是静态命令头/组件出现次数，另列调用覆盖。", 
             f"- Computer/Office：OSWorld {data['counts']['osworld_task_definitions']} 个任务定义投影到 {data['counts']['osworld_model_task_records']} 条 model×task 记录（不是独立任务数）；声明应用不等于运行应用。", 
             f"- Assistant：H-EPM {data['counts']['hepm_groups']} 个来源版本组分别报告；本地 ToolSandbox Assistant Repeat-01 为 {data['counts']['toolsandbox_assistant_runs']} 次固定任务运行、{data['counting']['local_assistant_task_denominator']}个任务设计。模拟API不映射为真实产品。", 
             f"- DocOps：仅使用已验收 Repeat-02 的{data['counts']['docops_runs']}次运行、{data['counts']['docops_run_tasks']}个固定任务。库版本未由所选报告确认。", "",
             "## Coding：保存命令组件", "",
             "表中以组为单位保留原始程序名、静态组件频数和轨迹出现数。轨迹出现数按同一轨迹去重；组件频数可能在一个调用中重复。返回/成功无法从聚合命令头表逐项关联，以下不称实际成功执行。", "",
             "| 来源/提交（participant） | task覆盖分母 | 轨迹分母 | 保存记录分母 | 已识别组件数 | 常见程序组件（频数；轨迹数） |", "|---|---:|---:|---:|---:|---|"]
    for g in coding_groups:
        if g["source"] == "Coding/local":
            continue
        comps = "; ".join(f"`{x['raw_name']}` [{x.get('entry_kind') or 'static head'}] {x['frequency']:,}（{x['trajectory_count']}/{g['trajectory_denominator']}轨迹）" for x in g["top_programs"])
        lines.append(f"| {g['source']} / `{g['group']}` | {g['task_denominator']} | {g['trajectory_denominator']} | {g['record_denominator']} | {g['software_component_occurrences']} | {comps or '无已识别软件名'} |")
    lines += ["", "软件组件的用途按程序身份/保存的操作分类保守解释：grep/rg为检索；find/ls/tree为定位或目录浏览；cat/head/tail等为查看/截取；Git为版本控制；pytest/Vitest等是明确测试运行器；Python/Node/Java通常仅能确认解释器入口；Maven/Gradle/Cargo/Go等聚合计数没有保留子命令时，不细分 build 与 test。`npm test`只有脚本内容被绑定时才能归到具体测试框架。本表不把Shell内建、参数碎片、`python`目标脚本名或 grep 参数中的词汇当软件。", "",
             "## Local Coding：固定本地重复批次", "",
             f"对P1-12-CODING-REPEAT-01已验收manifest显式选择的{data['counts']['local_coding_run_count']}个run、{data['counts']['local_coding_task_count']}个任务做静态命令身份提取；按task分开，三个run是同任务重复。调用ID与tool返回仅按唯一原生ID配对。总bash逻辑调用及返回核验：{json.dumps(data['coding_reparse']['local_coding_calls_and_returns'], ensure_ascii=False, sort_keys=True)}。下表组件数是命令文本静态拆分，不等同进程启动次数；每项另列组件出现数和保存调用涉及数。", "",
             "| 固定任务 | task数/3 | run数/3 | Bash调用分母 | 常见软件组件（静态出现；涉及调用/run） |", "|---|---:|---:|---:|---|"]
    for g in coding_groups:
        if g["source"] != "Coding/local":
            continue
        comps = "; ".join(f"`{x['raw_name']}` {x['frequency']}组件 / {x.get('component_calls', 0)}调用 / {x['trajectory_count']}run" for x in g["top_programs"])
        lines.append(f"| `{g['group']}` | {g['task_denominator']} | {g['trajectory_denominator']} | {g['record_denominator']} | {comps or '无已识别软件名'} |")
    lines += ["", "## Computer/Office：OSWorld任务声明应用", "",
             "以下由 `related_apps` 与 `snapshot` 的原始标识按任务去重；model×task数是同一声明投影到保存轨迹记录后的覆盖，不是启动次数。原始ID未丢弃；泛化/组合/环境标记在机器表中保留为未映射或歧义，不能据此声称产品启动。", "",
             f"| 原始任务应用标识 | 规范显示/家族（仅可确认者） | 任务数/{data['counts']['osworld_task_definitions']} | model×task记录数/{data['counts']['osworld_model_task_records']} | 证据层 |", "|---|---|---:|---:|---|"]
    for r in sorted((x for x in rows if x["source"] == "OSWorld task definitions" and x.get("evidence_type") == "task declaration"), key=lambda x: (-x["task_count"], x["raw_name"])):
        lines.append(f"| `{r['raw_name']}` | {r.get('software') or 'unknown（保留原始标签）'} / {r.get('family') or 'unknown'} | {r['task_count']} | {r['trajectory_count']} | task declaration ({', '.join(r['declaration_fields'])}) |")
    lines += ["", f"OSWorld行为报告检查了 {data['counts']['osworld_runtime_app_records_checked']} 条 model×task 记录；保存动作没有可靠的前台应用身份，因此运行时具体应用为 unknown。computer/pyautogui属于动作接口/实现代码，不等于Chrome、Writer或其他应用被实际启动。历史任务revision与轨迹绑定仍unknown。", "",
             "家族覆盖按任务去重，不把同一任务里多个别名/组件重复计数：", "",
             "| 应用家族 | 任务覆盖 | model×task覆盖 |", "|---|---:|---:|"]
    for r in data.get("osworld_application_family_coverage", []):
        lines.append(f"| {r['family']} | {r['task_count']}/{r['task_denominator']} | {r['trajectory_count']}/{r['trajectory_denominator']} |")
    lines += ["", "## Assistant：模拟工具环境，不是外部软件名", "",
             "H-EPM是第三方公开的适配ToolSandbox轨迹；各保存来源版本组独立按该组trajectory/scenario记录数作分母。`summarize_the_task`是框架辅助；其余解析出的联系人、消息、提醒、设置、位置、时间、天气等名称是模拟业务/API接口，没有可确认的外部服务品牌。", "",
             "| 来源/版本组 | 接口名 | 用途/命名空间 | 调用数 | 轨迹覆盖/组内分母 |", "|---|---|---|---:|---:|"]
    for r in rows:
        if r["scene"] == "Assistant/public H-EPM":
            lines.append(f"| H-EPM `{r['group']}` | `{r['raw_name']}` | {r['purpose']} | {r['frequency']} | {r['trajectory_count']}/{r['trajectory_denominator']} |")
    lines += ["", f"本地 ToolSandbox Assistant Repeat-01 的工具名同样是模拟业务接口。所选批次共{data['counts']['toolsandbox_assistant_runs']}次运行；调用总数从已验收逐run事件汇总。按本地事件分别统计，不映射为微信、Outlook、Google Calendar等真实软件。", "",
             f"| 本地角色 | 模拟接口 | 任务数/{data['counting']['local_assistant_task_denominator']} | 运行数/{data['counting']['local_assistant_run_denominator']} | 保存调用数 | ok数 |", "|---|---|---:|---:|---:|---:|"]
    for r in rows:
        if r["scene"] == "Assistant/local":
            lines.append(f"| {r['group']} | `{r['raw_name']}` | {r['task_count']} | {r['trajectory_count']} | {r['frequency']} | {r['ok_count']} |")
    lines += ["", "## 本地 DocOps：接口到处理库", "",
             "库映射来自被Repeat-02身份/分析manifest绑定的 `document_tools_runtime.py`，并与每次保存工具调用关联。调用数是接口调用数；ok单列。这里只把具体格式接口映射到实现函数直接使用的库。`inspect_document`按实际路径扩展名分支，分析产物没有保留可验证的每次分支，因此不把它的调用摊给库。", "",
             f"| 固定任务 | 调用接口 | 角色 | 实现库 | 用途 | 调用数 | ok数 | 运行数/{data['counting']['local_docops_run_denominator']} |", "|---|---|---|---|---|---:|---:|---:|"]
    for r in rows:
        if r["source"] == "DocOps local Repeat-02" and r.get("runtime_source"):
            lines.append(f"| `{r['group']}` | `{r['raw_name']}` | {r.get('role') or 'unknown'} | {r['software']} | {r['purpose']} | {r['frequency']} | {r['ok_count']} | {r['trajectory_count']} |")
    lines += ["", "源码映射中，`openpyxl`对应明确的`xlsx_*`接口，`python-pptx`对应`ppt_*`，`pdfplumber`对应`pdf_extract_text`，`pypdf`对应`pdf_reorder_pages/delete_pages`。Repeat-02未调用Word专用接口；`python-docx`仅作为实现参考，未计作本批使用。`soffice`/LibreOffice桌面进程没有被这些事件证明。文档格式可被Python库处理，不等于Microsoft Office/LibreOffice应用启动。", "",
             "## 无法从这些来源统计的具体软件", "",
             "- AgentX发布的是筛选后的请求流，不是完整工具执行日志；无法据其请求/子代理字段列真实命令或业务软件。", 
             f"- Applied Compute是生产轨迹派生workload模板，不是Agent消息或真实工具操作记录；本轮复用模板数 {json.dumps(data['counts']['applied_compute_template_counts_reused'], ensure_ascii=False, sort_keys=True)}，模板字段不提供可确认程序名。", 
             "- Video按PUBLIC-TRACE-OPERATIONS-v3的既有限制保留为工具证据不完整；本轮没有从该来源得到可靠的具体软件/命令身份，保持unknown，不补推FFmpeg等常见工具。", 
             "- OSWorld有任务声明应用但无逐动作前台应用身份；本地P1 Coding以命令参数可读取的软件名为静态证据，不能证明进程成功启动。", "",
             "## 解释边界", "",
             "来源之间不共用分母；重复run不等于独立任务。静态命令头不证明进程成功启动，任务声明不证明应用被打开，API工具名不是真实服务名，源码导入不证明每个分支都运行。缺少运行版本时库版本unknown。操作类别比例也不等于软件使用时间、CPU或内存占比。", ""]
    return "\n".join(lines)


def generate(root: Path = PROJECT, output: Path | None = None):
    root = root.resolve()
    report = build(root)
    output = output or root / OUT_REL
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty report directory: {output}")
    write_outputs(report, output)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT / OUT_REL)
    args = parser.parse_args()
    report = generate(PROJECT, args.output)
    print(json.dumps({"output": str(args.output), "coding_rows": len([x for x in report["rows"] if x["scene"] == "Coding/public"]),
                      "toolkit_rows": len(report["rows"]), "evidence_rows": len(report["evidence"]), "inputs": len(report["inputs"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
