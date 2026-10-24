#!/opt/video-use-venv/bin/python3
"""Real offline render/timeline checks against the image's production helpers."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

HELPERS = Path("/opt/video-use/helpers")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
               "-of", "json", str(path)])
    return json.loads(out.stdout)


def render_case(temp: Path, label: str, size: str, rate: str) -> dict:
    source = temp / f"{label}-source.mp4"
    output = temp / f"{label}-output.mp4"
    edl = temp / f"{label}-edl.json"
    source_info = run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration=4.2",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4.2",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
    ])
    edl.write_text(json.dumps({
        "sources": {"source": str(source)},
        "ranges": [
            {"source": "source", "start": 0.25, "end": 1.35},
            {"source": "source", "start": 1.65, "end": 3.75},
        ],
    }))
    run([
        "/opt/video-use-venv/bin/python3", str(HELPERS / "render.py"), str(edl),
        "-o", str(output), "--preserve-source-spec", "--no-grade",
        "--no-audio-fades", "--no-loudnorm", "--no-subtitles",
    ])
    source_probe, output_probe = probe(source), probe(output)
    video = next(s for s in output_probe["streams"] if s["codec_type"] == "video")
    audio = next((s for s in output_probe["streams"] if s["codec_type"] == "audio"), None)
    source_video = next(s for s in source_probe["streams"] if s["codec_type"] == "video")
    source_rate = source_video["avg_frame_rate"]
    duration = float(output_probe["format"]["duration"])
    expected_duration = (1.35 - 0.25) + (3.75 - 1.65)
    if (video["width"], video["height"]) != (source_video["width"], source_video["height"]):
        raise AssertionError(f"dimensions changed for {label}")
    if video["avg_frame_rate"] != source_rate:
        raise AssertionError(f"frame rate changed for {label}: {video['avg_frame_rate']} != {source_rate}")
    if audio is None:
        raise AssertionError(f"audio missing for {label}")
    if abs(duration - expected_duration) > max(0.15, 2 / float(rate.split('/')[0]) if '/' not in rate else 0.15):
        raise AssertionError(f"duration outside codec tolerance for {label}: {duration}")
    run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(output), "-f", "null", "-"])

    timeline = load_module("pilot03_timeline_view", HELPERS / "timeline_view.py")
    requested_start = max(0.0, duration - 0.8)
    requested_end = duration + 1.0
    image = temp / f"{label}-near-end.png"
    actual_run = subprocess.run
    seeks: list[float] = []
    fps = float(__import__("fractions").Fraction(source_rate))
    source_duration = float(source_probe["format"]["duration"])
    safe_max = source_duration - 2.0 / fps - 0.001
    media_safe_max = source_duration - 1.0 / fps

    def checked_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "ffmpeg" and "-ss" in cmd:
            seek = float(cmd[cmd.index("-ss") + 1])
            seeks.append(seek)
            # timeline_view formats its seek argument to milliseconds; allow
            # at most the resulting 0.5ms rounding while keeping a half-frame
            # margin before the container duration.
            if seek > safe_max + 0.0011 or seek >= media_safe_max:
                raise AssertionError(
                    f"timeline screenshot requested outside safe frame range: {seek} > {safe_max}")
        return actual_run(cmd, *args, **kwargs)

    with patch.object(timeline.subprocess, "run", side_effect=checked_run):
        timeline.render_timeline(source, requested_start, requested_end, image, 5, None)
    if not image.is_file() or not seeks:
        raise AssertionError("near-end screenshot was not produced")
    return {
        "case": label,
        "input_size": [source_video["width"], source_video["height"]],
        "output_size": [video["width"], video["height"]],
        "input_fps": source_rate,
        "output_fps": video["avg_frame_rate"],
        "audio_stream": audio["codec_name"],
        "duration_s": duration,
        "expected_duration_s": expected_duration,
        "ffprobe_and_decode": "pass",
        "near_end_screenshot": "pass",
        "requested_screenshot_end_s": requested_end,
        "max_frame_seek_s": max(seeks),
        "last_safe_frame_s": safe_max,
        "source_generation": "lavfi test pattern and sine; no network",
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pilot03-render-") as td:
        root = Path(td)
        result = {
            "schema": "video-use-pilot03-synthetic-render-v1",
            "network": "container network=none",
            "production_helpers": [str(HELPERS / "render.py"), str(HELPERS / "timeline_view.py")],
            "cases": [
                render_case(root, "source-854x480-25", "854x480", "25"),
                render_case(root, "other-640x360-30000-1001", "640x360", "30000/1001"),
            ],
        }
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
