#!/usr/bin/env python3
"""Seal a report from the already captured offline production-entry evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/home/lcq/agent_workload_characterization")
REPAIR = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01"
OUT = REPAIR / "validation-03"
OUTPUT = OUT / "output"
SESSION = json.loads((OUTPUT / "agent-context.json").read_text())["session_id"]
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
import openstoryline_pilot_entry as entry  # noqa: E402


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def main() -> None:
    final = OUTPUT / "continuation-06"
    run = json.loads((OUT / "continuation-run-06.json").read_text())
    phase = json.loads((final / "phase-times.json").read_text())
    result = json.loads((final / "agent-result.json").read_text())
    assert result["status"] == "completed"
    assert phase["mcp_cleanup_status"] == "stopped"
    assert run["container_removal"] == "removed"
    assert run["network"] == "none" and run["asr_reexecuted"] is False

    store_dir = OUTPUT / SESSION
    metas = json.loads((store_dir / "meta.json").read_text())
    artifacts: dict[str, list[dict]] = {}
    for meta in metas:
        path = store_dir / meta["node_id"] / f"{meta['artifact_id']}.json"
        if path.is_file():
            artifacts.setdefault(meta["node_id"], []).append(json.loads(path.read_text()))
    latest = {node: rows[-1] for node, rows in artifacts.items()}
    for node in ("load_media", "split_shots", "local_asr", "speech_rough_cut",
                 "plan_timeline_pro", "render_video"):
        assert node in artifacts and artifacts[node], node
    asr = next(row for row in artifacts["local_asr"]
               if row.get("payload", {}).get("asr_infos"))
    assert asr["payload"]["asr_infos"][0].get("asr_sentence_info")
    rough = latest["speech_rough_cut"]
    timeline = latest["plan_timeline_pro"]
    render = latest["render_video"]
    assert rough["payload"].get("clips")
    assert timeline["payload"].get("tracks", {}).get("video")
    assert render["payload"].get("output_path")

    requests = jsonl(final / "model-requests.jsonl")
    fake = jsonl(final / "fake-model-requests.jsonl")
    starts = [event for event in requests if event.get("event") == "request_started"]
    assert len(starts) == len(fake) == 15, (len(starts), len(fake))
    intervals = {}
    for event in requests:
        if event.get("request_id"):
            intervals.setdefault(event["request_id"], {})[event["event"]] = event
    matched = []
    for exchange in fake:
        stamp = exchange["observed_monotonic_ns"]
        candidates = [rid for rid, pair in intervals.items()
                      if pair.get("request_started", {}).get("started_monotonic_ns", 0) <= stamp
                      <= pair.get("request_finished", {}).get("finished_monotonic_ns", 0)]
        assert len(candidates) == 1, (exchange.get("action"), candidates)
        matched.extend(candidates)
    sampling = [event for event in requests if event.get("event") == "request_finished"
                and event.get("phase") == "mcp_sampling"]
    assert len(sampling) == 6
    assert all(event.get("association", {}).get("node_id") == "speech_rough_cut"
               and event.get("association", {}).get("session_id") == SESSION for event in sampling)

    output_path = OUTPUT / "output.mp4"
    render_path = Path(render["payload"]["output_path"])
    # Container paths are translated by the checked host export helper.
    relative = Path(*Path(render["payload"]["output_path"]).parts[3:])
    render_host_path = OUTPUT / relative
    assert render_host_path.is_file() and sha(render_host_path) == sha(output_path)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(output_path)], capture_output=True,
                           text=True, check=True, timeout=60)
    streams = json.loads(probe.stdout)["streams"]
    video = next(row for row in streams if row.get("codec_type") == "video")
    audio = next(row for row in streams if row.get("codec_type") == "audio")
    assert (video["codec_name"], video["pix_fmt"], video["width"], video["height"]) == (
        "h264", "yuv420p", 320, 240)
    assert (audio["codec_name"], video["r_frame_rate"]) == ("aac", "25/1")
    audio_start = float(audio.get("start_time", 0))
    video_start = float(video.get("start_time", 0))
    audio_duration = float(audio.get("duration", 0))
    video_duration = float(video.get("duration", 0))
    assert abs(audio_start - video_start) <= 0.1
    assert abs(audio_duration - video_duration) <= 0.1
    volume = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(output_path), "-vn",
                             "-af", "volumedetect", "-f", "null", "/dev/null"],
                            capture_output=True, text=True, timeout=60)
    assert volume.returncode == 0
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", volume.stderr)
    assert match and float(match.group(1)) > -90.0
    cuts = json.loads((OUTPUT / "cuts.json").read_text())
    assert cuts["cuts"] == [{"start_ms": 0, "end_ms": 90,
                             "reason": "outside_final_rendered_source_intervals"},
                            {"start_ms": 5910, "end_ms": 6000,
                             "reason": "outside_final_rendered_source_intervals"}]

    report = {
        "status": "PASS_fake_model_real_mcp_local_compute",
        "model_boundary": "container-loopback fake Chat Completions only; no credentials or real model API",
        "image": json.loads((REPAIR / "image-identity-07.json").read_text()),
        "session_id": SESSION,
        "continuation": "continuation-06 reused saved local_asr artifact; ASR was not rerun",
        "final_continuation_requests": {"logical": len(starts), "fake_http_exchanges": len(fake),
                                         "uniquely_time_matched": len(matched),
                                         "mcp_sampling": len(sampling)},
        "prior_evidence_note": "Earlier continuation raw logs remain intact; those made before the callback scope fix include duplicate overlapping Agent/MCP sampling rows.",
        "mcp_tool_event_count": sum(len(jsonl(folder / "mcp-tool-events.jsonl"))
                                     for folder in [OUTPUT, *sorted(OUTPUT.glob("continuation-*"))]
                                     if (folder / "mcp-tool-events.jsonl").is_file()),
        "artifacts": {node: rows[-1]["artifact_id"] for node, rows in artifacts.items()
                      if node in {"load_media", "split_shots", "local_asr", "speech_rough_cut",
                                  "plan_timeline_pro", "render_video"}},
        "render": {"artifact_id": render["artifact_id"], "source": sha(render_host_path),
                   "submission": sha(output_path), "video": {"codec": video["codec_name"],
                   "pixel_format": video["pix_fmt"], "width": video["width"],
                   "height": video["height"], "fps": video["r_frame_rate"]},
                   "audio": {"codec": audio["codec_name"],
                             "sample_rate": audio.get("sample_rate"),
                             "start_time": audio.get("start_time"),
                             "duration": audio.get("duration"),
                             "non_silent_mean_volume_db": float(match.group(1)),
                             "audio_video_start_delta_s": abs(audio_start - video_start),
                             "audio_video_duration_delta_s": abs(audio_duration - video_duration)}},
        "cuts": cuts,
        "cleanup": {"mcp": phase["mcp_cleanup_status"],
                    "container": run["container_removal"],
                    "mismatch_probe_returncode": run["session_mismatch_probe"]["returncode"]},
    }
    target = OUT / "validation-report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
