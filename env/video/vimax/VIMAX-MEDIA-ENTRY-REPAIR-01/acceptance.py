#!/usr/bin/env python3
"""Offline acceptance for the network-gated cold-start run.

Reads the run's workspace + fake-stats.json and verifies:
  - the entry completed the REAL path (COMPLETE, render ok, phases ordered)
  - fake send counts: 19 image creates (3 portraits + 8x2 candidates),
    15 video creates (8 major + 7 transition), downloads bounded
  - the 8 MAJOR shot videos map by SHA-256 to distinct major clips and the
    final video's per-segment digits follow that mapping in order
  - the 7 transition videos map to transition clips and are NOT part of the
    final concat (final duration ~= 8 x 5 s, not 15 x 5 s)
  - technical checks: h264 / 1280x720 / 30fps / ~40 s / no audio / decodes
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

RUN = Path(sys.argv[1]).resolve()
WORK = RUN / "workspace/attempt"
SESSION_GLOB = "workspace/.working_dir/*/script2video"

failures: list[str] = []
checks: dict[str, dict] = {}


def check(name: str, ok: bool, detail="") -> bool:
    checks[name] = {"ok": bool(ok), "detail": str(detail)[:400]}
    if not ok:
        failures.append(name)
    return bool(ok)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


def _digits(png: Path) -> int | None:
    from PIL import Image
    img = Image.open(png).convert("RGB")
    w, h = img.size
    xs = [int(w * 0.24 + i * (w * 0.52) / 3 + (w * 0.52) / 6) for i in range(3)]
    ys = [int(h * 0.31 + j * (h * 0.38) / 2 + (h * 0.38) / 4) for j in range(2)]
    px = img.load()
    bits = []
    for j in range(2):
        for i in range(3):
            r, g, b = px[xs[i], ys[j]]
            bits.append(1 if (r > 180 and g > 150 and b < 120) else 0)
    return sum(bit << pos for pos, bit in enumerate(bits))


def main() -> int:
    # ---- entry completed the real path ------------------------------------
    complete = WORK / "COMPLETE"
    ok_complete = False
    if complete.exists():
        try:
            c = json.loads(complete.read_text())
            ok_complete = (c.get("render_tool_ok") is True
                           and c.get("main_agent_returncode") == 0)
        except ValueError:
            pass
    check("entry_complete_render_ok", ok_complete,
          complete.read_text()[:200] if complete.exists() else "missing")
    check("entry_no_failure_marker", not (WORK / "ENTRY-FAILED.json").exists(),
          "ENTRY-FAILED present")
    phases = []
    pfile = WORK / "ENTRY-PHASES.jsonl"
    if pfile.exists():
        phases = [json.loads(l)["phase"] for l in pfile.read_text().splitlines()
                  if l.strip()]
    order = [p for p in ("entry.start", "startup_gate.released",
                         "seed_session.start", "seed_session.created",
                         "seed_session.done", "complete.written")
             if p in phases]
    check("entry_phase_order", len(order) == 6, phases)

    # ---- fake stats: send counts and kinds --------------------------------
    stats_path = WORK / "fake-stats.json"
    if not stats_path.exists():
        check("fake_stats_available", False, "missing fake-stats.json")
        print(json.dumps({"ok": False, "failures": failures}, ensure_ascii=False))
        return 7
    stats = json.loads(stats_path.read_text())
    img_creates = stats.get("image_creates", [])
    video_creates = stats.get("video_creates", [])
    majors = [c for c in video_creates if c["kind"] == "major"]
    transitions = [c for c in video_creates if c["kind"] == "transition"]
    check("fake_image_creates_19", len(img_creates) == 19,
          f"got {len(img_creates)}")
    check("fake_video_creates_15", len(video_creates) == 15,
          f"got {len(video_creates)}")
    check("fake_major_8", len(majors) == 8, f"got {len(majors)}")
    check("fake_transition_7", len(transitions) == 7, f"got {len(transitions)}")

    # ---- ledger agrees with the fake boundary ------------------------------
    ledger = WORK / "model-events.jsonl"
    if ledger.exists():
        rows = [json.loads(l) for l in ledger.read_text().splitlines()
                if l.strip()]
        creates = [r for r in rows if r.get("op") == "video_create"
                   and r.get("kind") == "close" and r.get("status") == "ok"]
        img_rows = [r for r in rows if r.get("op") == "image_generation"
                    and r.get("kind") == "close" and r.get("status") == "ok"]
        check("ledger_video_creates_15", len(creates) == 15,
              f"got {len(creates)}")
        check("ledger_image_generations_19", len(img_rows) == 19,
              f"got {len(img_rows)}")

    # ---- artifacts on disk --------------------------------------------------
    sdirs = sorted(RUN.glob(SESSION_GLOB))
    if not sdirs:
        check("session_script2video_dir", False, "no script2video dir")
        print(json.dumps({"ok": False, "failures": failures}, ensure_ascii=False))
        return 7
    sd = sdirs[0]
    portraits = sorted((sd / "character_portraits").rglob("*.png"))
    check("portraits_3", len(portraits) == 3, f"got {len(portraits)}")
    transition_files = sorted(sd.glob("shots/*/transition_video_from_shot_*.mp4"))
    check("transition_videos_7", len(transition_files) == 7,
          f"got {len(transition_files)}")
    new_cameras = sorted(sd.rglob("new_camera_*.png"))
    check("new_camera_frames", len(new_cameras) >= 1,
          f"got {len(new_cameras)}")
    candidates = sorted(sd.glob("shots/*/first_frame_candidates/candidate_*.png"))
    check("keyframe_candidates_16", len(candidates) == 16,
          f"got {len(candidates)}")

    # ---- 8 major shots map to distinct major clips -------------------------
    clip_sha = stats.get("clip_sha256", {})
    major_sha = {v: k for k, v in clip_sha.items()
                 if k.startswith("major-")}
    trans_sha = {v: k for k, v in clip_sha.items()
                 if k.startswith("transition-")}
    shot_clip: dict[int, int] = {}
    for i in range(8):
        v = sd / "shots" / str(i) / "video.mp4"
        if not v.exists():
            check(f"shot_{i}_video", False, "missing")
            continue
        name = major_sha.get(sha(v))
        if name is None:
            check(f"shot_{i}_maps_major_clip", False, "sha not in major set")
        else:
            shot_clip[i] = int(name.split("-")[1].split(".")[0])
    check("all_shots_map_to_distinct_major_clips",
          len(shot_clip) == 8 and len(set(shot_clip.values())) == 8,
          shot_clip)
    for tf in transition_files:
        check("transition_maps_transition_clip",
              sha(tf) in trans_sha, tf.name)

    # ---- final video --------------------------------------------------------
    finals = sorted(sd.rglob("final_video.mp4"))
    if not finals:
        check("final_video_exists", False, "missing")
    else:
        fv = finals[-1]
        r = run(["ffprobe", "-v", "error", "-print_format", "json",
                 "-show_format", "-show_streams", str(fv)])
        j = json.loads(r.stdout)
        streams = j.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        info = {"codec": video.get("codec_name"),
                "w": video.get("width"), "h": video.get("height"),
                "fps": video.get("r_frame_rate"),
                "dur": float((j.get("format") or {}).get("duration", 0)),
                "audio": any(s.get("codec_type") == "audio" for s in streams)}
        check("final_codec_h264", info["codec"] == "h264", info["codec"])
        check("final_720p_16_9", info["w"] == 1280 and info["h"] == 720,
              f"{info['w']}x{info['h']}")
        check("final_fps_30", info["fps"] == "30/1", info["fps"])
        check("final_duration_40s", abs(info["dur"] - 40) <= 1.5, info["dur"])
        check("final_no_audio", info["audio"] is False, info["audio"])
        r = run(["ffmpeg", "-v", "error", "-i", str(fv), "-f", "null", "-"])
        check("final_full_decode", r.returncode == 0 and not r.stderr.strip(),
              r.stderr[:200])
        # per-segment digits must equal the shot->major mapping IN ORDER
        frames = RUN / "acceptance-frames"
        frames.mkdir(exist_ok=True)
        seg_digits = []
        for k in range(8):
            t = k * 5 + 2.5
            png = frames / f"seg-{k}.png"
            rr = run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i",
                      str(fv), "-frames:v", "1", str(png)])
            seg_digits.append(_digits(png) if rr.returncode == 0
                              and png.exists() else None)
        order_ok = (len(shot_clip) == 8
                    and all(d is not None for d in seg_digits)
                    and all(shot_clip.get(i) == d for i, d in
                            enumerate(seg_digits)))
        check("final_segments_follow_shot_order", order_ok,
              f"shot_clip={shot_clip} seg_digits={seg_digits}")

    result = {"ok": not failures, "failures": failures,
              "checks": len(checks),
              "shot_clip_map": shot_clip,
              "send_counts": {"image": len(img_creates),
                              "video_major": len(majors),
                              "video_transition": len(transitions)}}
    (RUN / "acceptance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 7


if __name__ == "__main__":
    raise SystemExit(main())
