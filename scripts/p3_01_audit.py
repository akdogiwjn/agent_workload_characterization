#!/usr/bin/env python3
"""Read-only P3-01 trace audit; never executes recorded commands."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "p3-01-audit-v2"


def _sha(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def _status(value: Any, source: str, note: str | None = None) -> dict:
    out = {"status": value, "source_field": source}
    if note:
        out["note"] = note
    return out


def _load_events(run_dir: Path) -> tuple[list[dict], dict[str, dict]]:
    events = [json.loads(line) for line in
              (run_dir / "mini_tool_events.jsonl").read_text().splitlines()
              if line.strip()]
    by_id: dict[str, dict] = {}
    for event in events:
        ident = event.get("tool_call_id")
        if ident is None:
            continue
        by_id.setdefault(ident, {}).setdefault(event.get("event"), []).append(event)
    return events, by_id


def _trajectory_calls(run_dir: Path) -> list[dict]:
    trajectory = json.loads((run_dir / "mini_trajectory.json").read_text())
    calls = []
    ordinal = 0
    for mi, message in enumerate(trajectory.get("messages") or []):
        if message.get("role") != "assistant":
            continue
        for ti, tool_call in enumerate(message.get("tool_calls") or []):
            ordinal += 1
            fn = tool_call.get("function") or {}
            args = fn.get("arguments")
            command = None
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    command = parsed.get("command") if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    pass
            calls.append({
                "ordinal": ordinal,
                "message_index": mi,
                "tool_index": ti,
                "tool_call_id": tool_call.get("id"),
                "function_name": fn.get("name"),
                "command": command if isinstance(command, str) else None,
            })
    return calls


def _tool_message_presence(run_dir: Path) -> list[bool]:
    trajectory = json.loads((run_dir / "mini_trajectory.json").read_text())
    result = []
    i = 0
    messages = trajectory.get("messages") or []
    while i < len(messages):
        message = messages[i]
        calls = message.get("tool_calls") or [] if message.get("role") == "assistant" else []
        if calls:
            for n in range(len(calls)):
                tool = messages[i + 1 + n] if i + 1 + n < len(messages) else None
                content = tool.get("content") if isinstance(tool, dict) else None
                result.append(isinstance(content, str) and bool(content))
            i += 1 + len(calls)
        else:
            i += 1
    return result


def _registration_context(project: Path, metadata: dict) -> dict:
    marker_path = project / "reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json"
    catalog_path = project / "workload_catalog/run_02.yaml"
    if not marker_path.is_file() or not catalog_path.is_file():
        return {"status": "missing", "source_fields": []}
    marker = json.loads(marker_path.read_text())
    identity = marker.get("identity") or {}
    result = marker.get("result") or {}
    run_match = result.get("run_id") == metadata.get("run_id")
    task_match = (identity.get("task") or {}).get("instance_id") == metadata.get("task_id")
    catalog_hash = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    catalog_match = catalog_hash == identity.get("catalog_sha256")
    return {
        "status": "recorded" if run_match and task_match and catalog_match else "unknown",
        "source_fields": [
            "reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json.identity",
            "reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json.result.run_id",
            "workload_catalog/run_02.yaml",
        ],
        "run_id_match": run_match,
        "task_match": task_match,
        "catalog_match": catalog_match,
        "identity": identity,
    }


def analyze_run(run_dir: Path, *, schema: str = SCHEMA) -> dict:
    project = Path(__file__).resolve().parents[1]
    manifest = json.loads((run_dir / "manifest.json").read_text())
    metadata = json.loads((run_dir / "metadata.json").read_text())
    trajectory = json.loads((run_dir / "mini_trajectory.json").read_text())
    registration = _registration_context(project, metadata)
    file_checks = []
    for rel, expected in manifest.get("files", {}).items():
        path = run_dir / rel
        if not path.is_file():
            file_checks.append({"path": rel, "status": "missing", "expected_sha256": expected})
            continue
        size, actual = _sha(path)
        file_checks.append({"path": rel, "status": "recorded" if actual == expected else "unknown",
                            "bytes": size, "expected_sha256": expected, "actual_sha256": actual})

    events, by_id = _load_events(run_dir)
    calls = _trajectory_calls(run_dir)
    output_presence = _tool_message_presence(run_dir)
    open_events = [x for x in events if x.get("event") == "open"]
    close_events = [x for x in events if x.get("event") == "closed"]
    open_ids = [x.get("tool_call_id") for x in open_events]
    close_ids = [x.get("tool_call_id") for x in close_events]
    duplicate_open_ids = sorted({x for x in open_ids if open_ids.count(x) > 1})
    duplicate_closed_ids = sorted({x for x in close_ids if close_ids.count(x) > 1})
    trajectory_ids = [x["tool_call_id"] for x in calls]
    event_order_ids = open_ids
    event_integrity = {
        "duplicate_open_ids": duplicate_open_ids,
        "duplicate_closed_ids": duplicate_closed_ids,
        "orphan_closed_ids": sorted(set(close_ids) - set(open_ids)),
        "unclosed_open_ids": sorted(set(open_ids) - set(close_ids)),
        "unexpected_events": sorted({x.get("event") for x in events} - {"open", "closed", "error"}),
        "trajectory_event_order_match": event_order_ids == trajectory_ids,
        "trajectory_event_count_match": len(event_order_ids) == len(trajectory_ids),
    }
    event_integrity["valid"] = not any((duplicate_open_ids, duplicate_closed_ids,
                                         event_integrity["orphan_closed_ids"],
                                         event_integrity["unclosed_open_ids"],
                                         event_integrity["unexpected_events"])) and \
        event_integrity["trajectory_event_order_match"] and event_integrity["trajectory_event_count_match"]
    registered = registration.get("status") == "recorded"
    registered_identity = registration.get("identity") or {}
    planned_image = registered_identity.get("image")
    planned_interpreters = registered_identity.get("interpreters") or {}
    records = []
    seen_ids: set[str] = set()
    for call in calls:
        ident = call["tool_call_id"]
        duplicate = ident in seen_ids or ident is None
        seen_ids.add(ident)
        group = by_id.get(ident, {}) if ident else {}
        opens = group.get("open", [])
        closes = group.get("closed", [])
        opening = opens[0] if len(opens) == 1 else None
        closing = closes[0] if len(closes) == 1 else None
        command = call["command"]
        command_hash = hashlib.sha256(command.encode()).hexdigest() if command is not None else None
        hook_view = opening.get("command_view") if opening else None
        hash_match = bool(command_hash and isinstance(hook_view, dict)
                          and command_hash == hook_view.get("sha256")
                          and len(command) == hook_view.get("length"))
        pairing = "recorded" if opening and closing and not duplicate and len(opens) == 1 and len(closes) == 1 else "unknown"
        duration = None
        if opening and closing and isinstance(opening.get("t_start_ns"), int) and isinstance(closing.get("t_end_ns"), int):
            duration = closing["t_end_ns"] - opening["t_start_ns"]
        records.append({
            "ordinal": call["ordinal"],
            "tool_call_id": ident,
            "source_fields": {
                "trajectory_command": f"mini_trajectory.json.messages[{call['message_index']}].tool_calls[{call['tool_index']}].function.arguments.command",
                "hook_open": f"mini_tool_events.jsonl[event=open,tool_call_id={ident}]",
                "hook_closed": f"mini_tool_events.jsonl[event=closed,tool_call_id={ident}]",
            },
            "command": {"status": "recorded" if command is not None else "missing",
                        "sha256": command_hash, "length": len(command) if command is not None else None,
                        "hook_projection_match": hash_match,
                        "projection": _status("recorded" if hook_view else "missing", "mini_tool_events.jsonl.command_view"),
                        "structured_argv": _status("unknown", "trajectory command string", "shell command is not structured argv")},
            "association": {"status": pairing, "duplicate_id": duplicate,
                             "open_count": len(opens), "closed_count": len(closes)},
            "timing": {"status": "recorded" if duration is not None else "missing",
                       "duration_ns": duration, "source": "mini_tool_events.jsonl t_start_ns/t_end_ns"},
            "returncode": {"status": "recorded" if closing and "returncode" in closing else "missing",
                           "value": closing.get("returncode") if closing else None},
            "output": {"content_present": _status("recorded" if call["ordinal"] <= len(output_presence) and output_presence[call["ordinal"] - 1] else "missing", "mini_trajectory.json tool message.content"),
                       "length": closing.get("output_length") if closing else None,
                       "truncation": _status("unknown", "mini_tool_events.jsonl", "no truncation marker")},
            "fields": {
                "cwd": _status("derived" if registered else "missing", "r2 marker + mini_agent_adapter.py AttachedDockerEnvironment.config.cwd", "/testbed is planned code/config behavior; actual per-call cwd is not recorded"),
                "stdin": _status("missing", "mini_trajectory.json/mini_tool_events.jsonl", "no per-call stdin field"),
                "environment": _status("unknown", "mini_trajectory.json.info.config", "config is not observed child environment"),
                "image": {"status": "derived" if planned_image else "missing", "source_field": "R2 ATTEMPT_STARTED.json.identity.image + workload_catalog/run_02.yaml", "planned_value": planned_image, "actual_observed": "unknown"},
                "software": _status("derived", "mini_trajectory.json.info.mini_version + R2 ATTEMPT_STARTED.json.identity.code_sha256", "version/code identity is registered; actual per-call executable path is not recorded"),
                "interpreter": _status("derived" if planned_interpreters else "missing", "R2 ATTEMPT_STARTED.json.identity.interpreters", "registered interpreter identity; per-call process observation is not recorded"),
                "file_initial_state": _status("missing", "candidate.patch and run files", "final patch is not per-call initial state"),
                "prior_edits": _status("unknown", "candidate.patch", "final patch does not establish per-call ordering"),
                "dependency": _status("unknown", "trajectory and command string", "no dependency graph recorded"),
                "remote_dependency": _status("unknown", "command projection and metadata", "no network/endpoint evidence"),
                "output_correctness": _status("unknown", "returncode/output evidence", "no per-call semantic verifier"),
            },
        })
    model_name = (((trajectory.get("info") or {}).get("config") or {}).get("model") or {}).get("model_name")
    return {
        "schema": schema, "source_run": metadata.get("run_id"), "attempt_id": metadata.get("attempt_id"),
        "source_manifest_verified": all(x["status"] == "recorded" for x in file_checks),
        "file_checks": file_checks,
        "counts": {"trajectory_calls": len(calls), "hook_events": len(events), "hook_pairs": sum(len(v.get("open", [])) == 1 and len(v.get("closed", [])) == 1 for v in by_id.values())},
        "event_integrity": event_integrity,
        "identity": {"task_id": metadata.get("task_id"), "source_type": metadata.get("source_type"), "registration": registration, "harness": "derived from mini_trajectory.info.mini_version", "mini_version": (trajectory.get("info") or {}).get("mini_version"), "model": {"status": "derived" if model_name else "missing", "value": model_name, "source_field": "mini_trajectory.json.info.config.model.model_name"}, "image": {"status": "derived" if planned_image else "missing", "planned_value": planned_image, "actual_observed": "unknown", "source_field": "R2 ATTEMPT_STARTED.json.identity.image + workload_catalog/run_02.yaml"}, "interpreters": {"status": "derived" if planned_interpreters else "missing", "planned_value": planned_interpreters, "actual_observed": "unknown", "source_field": "R2 ATTEMPT_STARTED.json.identity.interpreters"}},
        "calls": records,
        "assessment": {"command_hashes_all_match": bool(records) and all(x["command"]["hook_projection_match"] for x in records), "association_integrity": event_integrity["valid"], "safe_executable": False, "fidelity_ready": False, "reason": "command string and hook projection are recoverable, but structured argv, actual cwd/stdin/environment, initial state, dependencies and semantic correctness are incomplete"},
    }


def run_audit(run_dir: Path, output_dir: Path) -> dict:
    run_dir, output_dir = run_dir.resolve(), output_dir.resolve()
    project = Path(__file__).resolve().parents[1]
    expected_parent = (project / "reports" / "replay").resolve()
    if output_dir.parent != expected_parent or output_dir.exists():
        raise ValueError("output directory must be new and directly under reports/replay")
    output_dir.mkdir(parents=False)
    schema = "p3-01-audit-v3" if output_dir.name == "P3-01-audit-v3" else SCHEMA
    inventory = analyze_run(run_dir, schema=schema)
    (output_dir / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    (output_dir / "summary.md").write_text(_summary(inventory))
    (output_dir / "corrections.md").write_text(_corrections(inventory))
    outputs = []
    for name in ("inventory.json", "summary.md", "corrections.md"):
        size, digest = _sha(output_dir / name)
        outputs.append({"path": str((output_dir / name).relative_to(project)), "bytes": size, "sha256": digest})
    input_items = []
    input_paths: set[str] = set()
    source_manifest = json.loads((run_dir / "manifest.json").read_text())
    for rel in ["manifest.json", *source_manifest.get("files", {})]:
        size, digest = _sha(run_dir / rel)
        input_path = run_dir / rel
        try:
            display_path = str(input_path.relative_to(project))
        except ValueError:
            display_path = str(input_path)
        input_items.append({"path": display_path, "bytes": size, "sha256": digest})
        input_paths.add(display_path)
    related = [
        project / "reports/resource/RUN-02/retries/R2/APPROVAL.txt",
        project / "reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json",
        project / "workload_catalog/run_02.yaml",
        project / "src/agent_workload_characterization/runners/run_02_entry.py",
        project / "src/agent_workload_characterization/runners/mini_agent_adapter.py",
    ]
    for input_path in related:
        if not input_path.is_file():
            continue
        display_path = str(input_path.relative_to(project))
        if display_path in input_paths:
            continue
        size, digest = _sha(input_path)
        input_items.append({"path": display_path, "bytes": size, "sha256": digest})
    script_size, script_hash = _sha(Path(__file__))
    manifest = {"schema": schema + "-manifest", "inputs": input_items, "outputs": outputs, "analyzer": {"path": str(Path(__file__).relative_to(project)), "bytes": script_size, "sha256": script_hash}, "manifest_self_hash": None}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return inventory


def _summary(inv: dict) -> str:
    c = inv["counts"]
    return (f"# {inv['schema']}\n\n"
            f"Read-only audit of `{inv['source_run']}`; no recorded command was executed.\n\n"
            f"- trajectory calls: {c['trajectory_calls']}\n- hook events: {c['hook_events']}\n- paired hook calls: {c['hook_pairs']}\n"
            f"- all trajectory command hashes match hook projections: `{inv['assessment']['command_hashes_all_match']}`\n- event association/order integrity: `{inv['assessment']['association_integrity']}`\n\n"
            "The shell command string and its SHA-256/length are recorded, but this is not structured argv and is not an execution authorization. Per-call cwd/stdin, actual child environment, initial file state, dependency graph, remote dependency and semantic output correctness remain explicitly classified in `inventory.json`. Output content presence is recorded where available; truncation is unknown because no truncation marker is recorded.\n\n"
            "The trace supports a bounded local description of tool-call identity, ordering, pairing, command hashes, durations and return codes. It does not yet support safe or faithful replay. CPU-02 remains paused; P3-02 and G3-R are not authorized or passed.\n")


def _corrections(inv: dict) -> str:
    return ("# Corrections to P3-01 audit-v1/v2\n\n"
            "1. The prior claim that commands were not recoverable was too strong. v2 parses `function.arguments.command` and independently verifies every command hash and length against the hook projection.\n"
            "2. The v1 call-14 hash was manually incomplete. v2 generates it from source data and records the full digest; the source hash is not hand-entered.\n"
            "3. `metadata.json` does not establish an image identity. Model/harness fields are separated: model is derived from trajectory config, harness version from trajectory info, and image remains missing.\n"
            "4. Field coverage is now per call: recorded, derived, missing or unknown, including output presence/truncation, cwd, stdin, environment, initial state, dependencies and correctness.\n"
            "5. v2 incorrectly treated registered image/cwd/interpreter context as missing. v3 links the R2 marker, catalog and versioned code/config identity, while keeping actual runtime observation as unknown.\n"
            "6. v2 did not make orphan hook events and global event order part of the validity gate. v3 records those checks and refuses a clean association result on mismatch.\n"
            "7. This correction does not convert a shell command string into safe structured argv or authorize replay.\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    run_audit(args.run_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
