"""Offline closeout only: never starts a process, container, or API request."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "env/video/vimax/VIMAX-GENERATION-PILOT-01"
OUT = ROOT / "reports/resource/VIMAX-GENERATION-PILOT-01/closeout-01"


def metadata(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def valid(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def rate(left: dict, right: dict, field: str, status: str, divisor=1) -> float | None:
    if any(left.get(k) is None or left.get(k) != right.get(k) for k in ("scope", "scope_kind")):
        return None
    if not all(str(r.get("read_status", {}).get(status, "")).startswith("ok") for r in (left, right)):
        return None
    a, b = left.get(field), right.get(field)
    t0, t1 = left.get("t_monotonic_ns"), right.get("t_monotonic_ns")
    if not all(valid(v) for v in (a, b, t0, t1)) or b < a or t1 <= t0:
        return None
    return (b - a) / divisor / ((t1 - t0) / 1e9)


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def chart(path: Path, panels: list) -> None:
    colors = ("#1769aa", "#d35400")
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="960" viewBox="0 0 1100 960">',
           '<rect width="1100" height="960" fill="white"/>',
           '<style>text{font-family:sans-serif;font-size:12px;fill:#263238}</style>']
    for index, (title, series) in enumerate(panels):
        ytop = index * 240
        svg.append(f'<text x="65" y="{ytop+25}" font-weight="bold">{html.escape(title)}</text>')
        pts = [(x, y) for _, seq in series for x, y in seq if y is not None and math.isfinite(y)]
        svg.append(f'<path d="M65 {ytop+195} H1060 M65 {ytop+45} V{ytop+195}" fill="none" stroke="#aaa"/>')
        if not pts:
            svg.append(f'<text x="80" y="{ytop+100}">No valid observations</text>')
            continue
        xmax = max(max(x for x, _ in pts), 1)
        ymax = max(max(y for _, y in pts), 1e-6)
        ymin = min(min(y for _, y in pts), 0)
        for j, (name, seq) in enumerate(series):
            segments, segment = [], []
            for x, y in seq:
                if y is None:
                    if segment: segments.append(segment)
                    segment = []
                else:
                    segment.append(f"{65+x/xmax*995:.2f},{ytop+195-(y-ymin)/(ymax-ymin)*150:.2f}")
            if segment: segments.append(segment)
            for segment in segments:
                svg.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{colors[j%2]}" stroke-width="1.3"/>')
            svg.append(f'<text x="{700+j*150}" y="{ytop+42}">{html.escape(name)}</text>')
        svg.extend([f'<text x="65" y="{ytop+218}">0 s</text>',
                    f'<text x="960" y="{ytop+218}">{xmax:.1f} s</text>',
                    f'<text x="8" y="{ytop+60}">{ymax:.3g}</text>'])
    svg.append('</svg>')
    path.write_text("\n".join(svg))


def main() -> None:
    if OUT.exists():
        raise SystemExit("Refusing to overwrite an existing closeout")
    inputs = [metadata(p) for p in sorted(RAW.rglob("*")) if p.is_file()]
    record = json.loads((RAW / "run-record.json").read_text())
    events = jsonl(RAW / "workspace/attempt/agent-events.jsonl")
    ledger = jsonl(RAW / "workspace/attempt/bailian-ledger.jsonl")
    samples = jsonl(RAW / "resource-samples.jsonl")
    started = {e["request_id"]: e for e in ledger if e.get("kind") == "open"}
    closed = {e["request_id"]: e for e in ledger if e.get("kind") == "close"}
    chats = {k: e for k, e in started.items() if e.get("op") == "llm_chat"}
    results = [e["tool_result"] for e in events if e.get("type") == "tool_result"]
    errors = [e.get("message", "") for e in events if e.get("type") == "error"]
    budget_stop = any("llm_calls cap=80" in s and "already_sent=80" in s for s in errors)
    usage = {k: sum((e.get("usage") or {}).get(k, 0) or 0 for e in closed.values()
                    if e.get("op") == "llm_chat")
             for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    media = [str(p.relative_to(RAW)) for p in RAW.rglob("*.mp4")]
    if not budget_stop or media:
        raise SystemExit("Evidence differs from reviewed planning-only budget-stop; inspect manually")
    OUT.mkdir(parents=True)
    stop = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "user_request": "帮我停止 并收尾",
        "container_id": record["container_id"],
        "container_inspect_observation": "Docker daemon returned No such container for the exact full ID",
        "container_ps_filter_observation": "docker ps -a --no-trunc --filter id=<exact ID> returned no rows, rc=0",
        "host_process_observation": "Host /proc exact-script check found no matching ViMax host runner, formal driver or main_agent.py process",
        "image_retained": "sha256:7c634c46a829e2d22ee901023b70a6bdb2e5bd06d7b334b0f8a8150a3daa39be linux/arm64",
        "action": "Existing runner had already completed budget-stop cleanup when checked; no additional kill, restart or API request issued by closeout",
        "inspection_evidence_note": "These are transcription of direct host Docker/process tool observations, not a rerun or fabricated daemon receipt",
    }
    dump(OUT / "stop-verification.json", stop)
    t0 = record["resource_boundary"]["start"]["t_monotonic_ns"]
    rows = [record["resource_boundary"]["start"], *samples, record["resource_boundary"]["end"]]
    points = []
    for i, row in enumerate(rows):
        left = rows[i - 1] if i else row
        points.append({"elapsed_s": (row["t_monotonic_ns"] - t0) / 1e9,
                       "cpu_usage_usec": row.get("cpu_usage_usec"),
                       "average_core": rate(left, row, "cpu_usage_usec", "cpuacct.usage", 1e6),
                       "memory_current_bytes": row.get("mem_current_bytes"),
                       "memory_kernel_peak_bytes": row.get("mem_peak_bytes"),
                       "io_read_bytes": row.get("io_read_bytes"),
                       "io_write_bytes": row.get("io_write_bytes"),
                       "io_read_Bps": rate(left, row, "io_read_bytes", "io"),
                       "io_write_Bps": rate(left, row, "io_write_bytes", "io")})
    with (OUT / "resource-samples.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(points[0])); writer.writeheader(); writer.writerows(points)
    network = record.get("host_netns_samples", [])
    names = sorted({name for r in network for name in r.get("ifaces", {})})
    interface = "eno1" if "eno1" in names else (names[0] if names else None)
    with (OUT / "network-selected-interface.csv").open("w", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["host_elapsed_s", "scope", "interface", "rx_bytes", "tx_bytes"])
        for r in network:
            v = r.get("ifaces", {}).get(interface, {})
            writer.writerow([r["t"], "HOST_NETNS_SHARED", interface, v.get("rx"), v.get("tx")])
    chart(OUT / "resource-curves.svg", [
        ("Container CPU: interval average cores", [("CPU", [(p["elapsed_s"], p["average_core"]) for p in points])]),
        ("Container memory.current (MiB); kernel peak reported separately", [("current", [(p["elapsed_s"], p["memory_current_bytes"] / 1048576 if p["memory_current_bytes"] is not None else None) for p in points])]),
        ("cgroup v1 throttle I/O cumulative bytes (MiB), NOT full filesystem traffic", [(k, [(p["elapsed_s"], p[k] / 1048576 if p[k] is not None else None) for p in points]) for k in ("io_read_bytes", "io_write_bytes")]),
        (f"HOST SHARED {interface}: raw cumulative counters (GiB), NOT task/API traffic", [(k, [(r["t"], r.get("ifaces", {}).get(interface, {}).get(k) / 1073741824 if r.get("ifaces", {}).get(interface, {}).get(k) is not None else None) for r in network]) for k in ("rx", "tx")]),
    ])
    intervals = [(b["t_monotonic_ns"] - a["t_monotonic_ns"]) / 1e9 for a, b in zip(samples, samples[1:])]
    summary = {
        "task": record["task"], "status": "closed_budget_exhausted_no_media",
        "termination": "LLM logical-call budget exhausted during repeated planning; not manually killed, not a wall timeout",
        "agent_returncode": json.loads((RAW / "workspace/attempt/driver-record.json").read_text()).get("agent_returncode"),
        "original_runner_ok": record.get("ok"),
        "original_runner_ok_meaning": "completion handshake only, NOT task/media success",
        "task_success": False, "evaluation": "not_started_no_submission", "reward": None,
        "identity_note": "Original run-record records code hashes and identity_frozen phase; this closeout does not invent a missing standalone frozen identity/approval",
        "llm_logical_starts": len(chats),
        "llm_logical_by_role": dict(Counter(e.get("role") for e in chats.values())),
        "llm_closed": sum(k in closed for k in chats),
        "llm_unclosed": [k for k in chats if k not in closed],
        "project_attempt_starts": sum(e.get("op") == "llm_attempt" for e in started.values()),
        "usage_saved_closed_calls_only": usage,
        "usage_note": "12 unclosed inner starts retain unknown outcome/usage; successful LLM responses do not imply successful parsing. Project attempt rows overlap logical requests, do not sum as additional calls",
        "actual_http_requests": None, "actual_cost": None,
        "media_operations_recorded": {k: sum(e.get("op") == k for e in started.values()) for k in ("image_generation", "video_create")},
        "media_files": media, "event_count": len(events),
        "tools": [{"name": name, "ok": ok, "count": n} for (name, ok), n in Counter((r.get("name"), r.get("ok")) for r in results).items()],
        "tool_starts": sum(e.get("type") == "tool_start" for e in events), "tool_results": len(results),
        "association_note": "Counts agree; no claim of independent per-tool-call ID matching beyond saved native event structure",
        "observed_failures": errors,
        "attempt_wall_s": record.get("total_wall_s"), "resource_summary": record.get("resource_summary"),
        "sampling": {"periodic_points": len(samples), "median_interval_s": statistics.median(intervals), "max_interval_s": max(intervals), "nonincreasing_intervals": sum(x <= 0 for x in intervals), "valid_cpu_intervals_including_boundaries": sum(p["average_core"] is not None for p in points)},
        "network": {"scope": "HOST_NETNS_SHARED", "sample_count": len(network), "selected_interface": interface, "selection_rule": "eno1 if present, otherwise first sorted interface; NOT an identified API route", "netns_inode": None, "interpretation": "Raw saved interface counters only; namespace identity not recorded; no per-task attribution or cross-interface sum"},
        "disk_footprint": {k: record.get("phases", {}).get(k, {}).get("workspace") for k in ("before", "after")},
        "cleanup": {"container_removed": True, "matching_host_processes": 0, "image_retained": True},
        "measurement_limitations": ["Resource window differs from attempt wall", "No image/video generation or FFmpeg execution cost in this attempt", "v1 throttle I/O is not complete filesystem I/O", "baseline_cpu_unreadable:None note conflicts with valid v1 baseline status; preserve original note, use actual read_status", "Actual HTTP, missing request outcomes and billing unknown"],
        "no_new_attempt_or_api": True,
    }
    dump(OUT / "run-report.json", summary)
    text = f"""# ViMax 首次真实任务停止与收尾

本次已停止且容器不存在；宿主未发现对应运行器/driver/Agent残留，使用镜像保留。停止检查时，原运行器已经因LLM调用门禁结束并完成清理；本轮没有再发停止信号、模型请求或重跑。

## 任务结果与终止

**未生成图片或视频，没有完成八镜头任务；评分未执行，reward=null，不是0分。** 原始 `ok=true` 仅指完成握手，Agent进程返回0不代表任务成功。最终error/done明确为 `llm_calls cap=80; already_sent=80`。原始记录保持不变。

80条LLM逻辑开始记录：外层27、内部53；68条保存闭合返回，12条内部开始记录未闭合，保持unknown，不能当成12次HTTP失败或零费用。另27条项目attempt记录与外层调用重叠，不加总为107次逻辑请求。实际HTTP次数unknown。

已保存闭合返回usage：输入{usage['prompt_tokens']:,}、输出{usage['completion_tokens']:,}、合计{usage['total_tokens']:,} tokens；不是全部请求的完整账单。登记软门禁实际针对输出token，不是输入输出合计；输出累计172,774，不能把总量933,898与500,000输出阈值混为一谈。费用unknown。

原生事件260条，工具开始/返回均44条：规划12次失败、3次成功返回（不代表完整可渲染）；read_file 8、list_files 1、glob_files 3次成功；write_json 12、run_shell 5次失败。可见解析异常、camera tree长度不符、修订目标不存在及重复规划；没有render工具调用。尚未做唯一根因诊断，不擅自断言模型不支持或需要更多预算。

## 本地资源（仅规划/恢复路径）

- attempt wall：{record['total_wall_s']:.3f}s；资源边界窗：{record['resource_summary']['wall_s']:.3f}s，不混用。
- CPU：{record['resource_summary']['cpu_core_seconds']:.6f} core-s，平均{record['resource_summary']['avg_cores']:.6f} core；远端模型计算不在本机范围。
- 周期采样{len(samples)}点，中位间隔{statistics.median(intervals):.6f}s，最大{max(intervals):.6f}s，无非递增周期。
- memory.current采样峰：{record['resource_summary']['memory_sampled_max_bytes']:,} B；内核peak：{record['resource_summary']['memory_kernel_peak_bytes']:,} B，分列不相加。
- cgroup v1 throttle I/O：读0、写999,424 B，原始状态支持真零；不代表完整文件系统流量。
- 网络是共享宿主netns；图只展示{interface}原始累计计数，不是任务/API字节，且历史未保存netns inode。
- 工作目录前后10,042→745,603 B，包括输入、轨迹和规划文件，不是视频产物占用或最终归档大小。

原始baseline提示 `baseline_cpu_unreadable:None` 未删改；实际v1起止 `cpuacct.usage` 都是有效读取，提示不能覆盖读数证据。

## 证据入口

- [机器报告](run-report.json)
- [停止核验](stop-verification.json)
- [资源曲线](resource-curves.svg)
- [资源点CSV](resource-samples.csv)
- [共享网络选定接口CSV](network-selected-interface.csv)
- [原始文件清单](raw-manifest.json)
- [输入/代码/输出清单](manifest.json)

本次没有修复执行代码、补跑、调用verifier、更新HTML或提交Git。下一步只能先离线诊断规划输出/解析与原生工具失败，不自动续跑。本报告是收尾记录，不是新执行批准。
"""
    (OUT / "summary.md").write_text(text)
    dump(OUT / "raw-manifest.json", {"scope": str(RAW.relative_to(ROOT)), "files": inputs, "note": "Seals existing run as observed; original files not rewritten; no claim that original runner had already created this manifest"})
    for item in inputs:
        if metadata(ROOT / item["path"]) != item:
            raise RuntimeError("Raw changed during closeout: " + item["path"])
    outputs = [metadata(p) for p in sorted(OUT.iterdir()) if p.is_file()]
    dump(OUT / "manifest.json", {"inputs": inputs, "code": [metadata(Path(__file__).resolve())], "outputs": outputs, "self_hashed": False})
    for section in (inputs, outputs):
        for item in section:
            if metadata(ROOT / item["path"]) != item:
                raise RuntimeError("Hash readback failed: " + item["path"])
    print(json.dumps({"report": str(OUT.relative_to(ROOT)), "raw_files_verified": len(inputs), "outputs_verified": len(outputs), "task_success": False, "container_removed_verified": True}))


if __name__ == "__main__":
    main()
