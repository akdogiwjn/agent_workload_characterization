"""Production acceptance: the REAL LocalASRNode.__call__ path with the
English adapter injected (same injection as register_tools.py overlay).

Checks: output structure, text/timestamp 1:1, units (ms), ordering,
duration bounds, VAD segment offsets, sentence assembly, spot checks at
start/middle/end and one VAD boundary.
"""
import asyncio
import json
import os
import subprocess
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/opt/openstoryline/src")
sys.path.insert(0, "/opt/openstoryline")

# the SAME injection the task entry uses
from open_storyline.nodes.core_nodes import asr_node


def _load_english_asr_model(self):
    if not hasattr(self, "asr_model"):
        from asr_adapter import ParaformerEnAsr
        self.asr_model = ParaformerEnAsr()
    return self.asr_model


asr_node.LocalASRNode._load_asr_model = _load_english_asr_model

from open_storyline.nodes.core_nodes.asr_node import LocalASRNode
from open_storyline.nodes.node_state import NodeState
from open_storyline.nodes.node_summary import NodeSummary

SOURCE = "/task/source.mp4"
OUT = Path("/task/out"); OUT.mkdir(exist_ok=True)

# measure the actual decoded audio-track duration (not "about 37 s")
def audio_duration_s(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())

async def main():
    duration_s = audio_duration_s(SOURCE)
    duration_ms = duration_s * 1000.0
    print(f"decoded audio duration: {duration_s:.3f} s ({duration_ms:.1f} ms)")

    node = LocalASRNode(SimpleNamespace(
        local_mcp_server=SimpleNamespace(server_cache_dir="cache")))
    # adapter raw output FIRST (keeps _vad_segments / metadata that the
    # production _combine_tool_outputs legitimately strips)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        raw_wav = os.path.join(td, "audio.wav")
        subprocess.run(["ffmpeg", "-y", "-i", SOURCE, "-vn",
                        "-af", "afftdn,agate=threshold=-40dB:ratio=10:attack=20:release=100",
                        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        raw_wav], capture_output=True)
        raw_full = node._load_asr_model().generate(
            input=raw_wav, sentence_timestamp=True)[0]
    json.dump(raw_full, open(OUT / "adapter_raw_output.json", "w"),
              ensure_ascii=False, indent=1, default=str)
    segs = raw_full.get("_vad_segments")
    state = NodeState(session_id="asr-adapter-01", artifact_id="verify-1",
                      lang="en", node_summary=NodeSummary(), llm=None,
                      mcp_ctx=None)
    result = await node(state, mode="auto", lang="en",
                        split_shots={"clips": [{
                            "clip_id": "c000", "path": SOURCE,
                            "kind": "video", "source_ref": {
                                "media_id": "m0", "start": 0,
                                "end": int(duration_ms),
                                "duration": int(duration_ms),
                                "width": 854, "height": 480},
                            "fps": 25}]})
    raw = result["tool_excute_result"]
    asr_infos = raw["asr_infos"]
    info = asr_infos[0]

    checks = {}
    def check(name, ok, detail=""):
        checks[name] = {"ok": bool(ok), "detail": detail}
        print(("PASS " if ok else "FAIL ") + name + (f" | {detail}" if detail else ""))

    # structure
    for field in ("asr_text", "asr_timestamps", "asr_sentence_info"):
        check(f"field:{field}", field in info)
    text = info["asr_text"]
    ts = info["asr_timestamps"]
    sentences = info["asr_sentence_info"]
    check("text_nonempty_english",
          len(text) > 50 and sum(c.isascii() for c in text) / max(len(text), 1) > 0.9,
          f"len={len(text)}")

    # 1:1 word/timestamp
    words = text.replace("，", " ").replace("。", " ").replace("？", " ") \
                .replace("、", " ").split()
    raw_words = info.get("_raw_word_count") or (result.get("_raw_word_count"))
    # adapter metadata was stripped by pack? fall back to sentence timestamps
    n_ts = len(ts)
    n_w = len(words)
    check("word_timestamp_1to1", n_ts == n_w or raw_words == n_ts,
          f"ts={n_ts} words={n_w} raw={raw_words}")

    # units & ordering & bounds
    import math
    finite = all(math.isfinite(a) and math.isfinite(b) for a, b in ts)
    check("timestamps_finite", finite)
    check("start_le_end", all(a <= b for a, b in ts))
    ordered = all(ts[i][1] <= ts[i+1][0] + 1e-9 or ts[i][0] <= ts[i+1][0]
                  for i in range(len(ts)-1))
    check("timestamps_ordered", ordered)
    tolerance_ms = 720.0  # 12 LFR frames * 60 ms (MAX_TOKEN_DURATION), pre-declared
    over = [t for t in ts if t[1] > duration_ms + tolerance_ms]
    check("within_duration_tolerance",
          not over,
          f"max_end={max((t[1] for t in ts), default=0):.0f}ms vs dur={duration_ms:.0f}ms "
          f"tol=+{tolerance_ms:.0f}ms; over={len(over)}")
    neg = [t for t in ts if t[0] < -1e-9]
    check("no_negative", not neg)

    # VAD segments: monotonic, non-overlapping (from the RAW adapter output)
    check("vad_segments_monotonic",
          segs and all(segs[i][1] <= segs[i+1][0] for i in range(len(segs)-1)),
          f"segments={segs}")
    # words not repeated across segments: count distinct start times
    starts = [round(t[0], 1) for t in ts]
    check("no_duplicate_word_starts", len(set(starts)) == len(starts))

    # sentences: text/timestamps consistent, acoustic basis
    ok_sent = bool(sentences)
    for s in sentences:
        if not (s.get("start") is not None and s.get("end") is not None
                and isinstance(s.get("timestamp"), list) and s["timestamp"]):
            ok_sent = False
            break
        if s["start"] != s["timestamp"][0][0] or s["end"] != s["timestamp"][-1][1]:
            ok_sent = False
            break
    check("sentence_structure_acoustic", ok_sent,
          f"sentences={len(sentences)}")
    sent_words = sum(len(str(s["text"]).split()) for s in sentences)
    # sentence text words may include punctuation attached; approximate
    check("sentence_word_coverage",
          abs(sent_words - n_w) <= len(sentences) * 2,
          f"sentence_words={sent_words} word_count={n_w}")

    json.dump({"result": result, "checks": checks,
               "duration_s_measured": duration_s},
              open(OUT / "verify_node_result.json", "w"),
              ensure_ascii=False, indent=1, default=str)

    # ---------- spot checks: re-run adapter on short slices ----------
    adapter = node.asr_model
    def slice_asr(start_s, end_s, tag):
        w = OUT / f"spot_{tag}.wav"
        subprocess.run(["ffmpeg", "-y", "-i", SOURCE, "-ss", str(start_s),
                        "-to", str(end_s), "-vn", "-acodec", "pcm_s16le",
                        "-ar", "16000", "-ac", "1", str(w)],
                       capture_output=True)
        r = adapter.generate(input=str(w), sentence_timestamp=True)[0]
        return r

    spots = {}
    # find a VAD boundary in the middle for the boundary spot
    mid_boundary = None
    if segs and len(segs) > 1:
        for i in range(len(segs) - 1):
            if 10000 < segs[i][1] < duration_ms - 5000:
                mid_boundary = segs[i][1]
                break
        if mid_boundary is None:
            mid_boundary = segs[0][1]
    plan = [("start", 0.0, min(3.5, duration_s)),
            ("middle", duration_s * 0.45, duration_s * 0.45 + 4.0),
            ("end", max(0.0, duration_s - 4.0), duration_s)]
    if mid_boundary:
        plan.append(("vad_boundary", max(0.0, mid_boundary / 1000.0 - 2.0),
                     mid_boundary / 1000.0 + 2.0))
    for tag, a, b in plan:
        r = slice_asr(a, b, tag)
        spots[tag] = {"window_s": [round(a, 2), round(b, 2)],
                      "text": r.get("text", "")[:250],
                      "n_words": len((r.get("text") or "").split()),
                      "first_ts": (r.get("timestamp") or [[None]])[0],
                      "last_ts": (r.get("timestamp") or [[None]])[-1]}
        print(f"SPOT {tag} [{a:.1f},{b:.1f}]s: {r.get('text','')[:120]}")

    json.dump(spots, open(OUT / "spot_checks.json", "w"),
              ensure_ascii=False, indent=1, default=str)

    failed = [k for k, v in checks.items() if not v["ok"]]
    print("\nOVERALL:", "PASS" if not failed else f"FAILED: {failed}")

asyncio.run(main())
