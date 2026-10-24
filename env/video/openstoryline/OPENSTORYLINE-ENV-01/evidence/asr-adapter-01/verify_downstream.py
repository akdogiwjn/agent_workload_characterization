"""Downstream offline chain on SYNTHETIC media with a FIXED fake LLM.

Real nodes: SpeechRoughCutNode (LLM boundary faked), PlanTimelineProNode,
RenderVideoNode. The fake LLM returns a PRESET rough-cut plan (fixture, not
an Agent decision). Verifies: ASR-result consumption, keep-range grouping,
calibrated timestamps, timeline windows, rendered output specs, and a
cuts.json exported from the ACTUAL rendered keep-ranges.
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/opt/openstoryline/src")
sys.path.insert(0, "/opt/openstoryline")
os.environ.setdefault("OPENSTORYLINE_CONFIG", "/opt/openstoryline/config.toml")

from open_storyline.config import load_settings
from open_storyline.nodes.core_nodes.speech_rough_cut import SpeechRoughCutNode
from open_storyline.nodes.core_nodes.plan_timeline_pro import PlanTimelineProNode
from open_storyline.nodes.core_nodes.render_video import RenderVideoNode
from open_storyline.nodes.node_state import NodeState
from open_storyline.nodes.node_summary import NodeSummary

OUT = Path("/task/out"); OUT.mkdir(exist_ok=True)
SYNTH = "/task/synth.mp4"

# ---------- 1. synthetic media: 10 s, 854x480, 25 fps, sine audio ----------
subprocess.run(["ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc2=duration=10:size=854x480:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", SYNTH], capture_output=True, check=True)

# ---------- 2. ASR fixture (3 sentences, word timestamps within 10 s) ----------
def words_with_ts(pairs):
    return [{"t": w, "s": s, "e": e} for w, s, e in pairs]

sent1 = words_with_ts([("hello", 300, 600), ("there", 600, 900),
                        ("welcome", 950, 1400), ("to", 1400, 1550), ("the", 1550, 1700),
                        ("show", 1700, 2100)])
sent2 = words_with_ts([("this", 3200, 3550), ("middle", 3550, 4100),
                       ("part", 4100, 4500), ("gets", 4500, 4800), ("cut", 4800, 5100)])
sent3 = words_with_ts([("final", 7300, 7800), ("section", 7800, 8500),
                       ("stays", 8500, 9000), ("goodbye", 9000, 9600)])

def mk_sentence(ws):
    return {"text": " ".join(w["t"] for w in ws),
            "start": ws[0]["s"], "end": ws[-1]["e"],
            "timestamp": [[w["s"], w["e"]] for w in ws]}

sentences = [mk_sentence(s) for s in (sent1, sent2, sent3)]
all_ts = [t for s in (sent1, sent2, sent3) for t in
          [[w["s"], w["e"]] for w in s]]
asr_text = " ".join(s["text"] for s in sentences)

asr_infos = [{
    "clip_id": "c000", "kind": "video", "path": SYNTH,
    "asr_text": asr_text, "asr_timestamps": all_ts,
    "asr_sentence_info": sentences,
    "source_ref": {"media_id": "m0", "start": 0, "end": 10000,
                   "duration": 10000, "width": 854, "height": 480},
    "fps": 25}]

# ---------- fake LLM: preset plan = keep s1 & s3, drop s2 ----------
FAKE_PLAN = {"reason": "fixture: drop the middle sentence",
             "res": [{"text": sent["text"], "start": sent["start"],
                      "end": sent["end"]} for sent in (sentences[0], sentences[2])]}

class FakeLLM:
    """Per-sentence fake: keeps s1 and s3, DROPS s2 (the middle sentence).
    Mirrors the real contract where each LLM call handles ONE sentence."""
    calls = 0
    async def complete(self, *, system_prompt, user_prompt, media=None,
                       temperature=None, top_p=None, max_tokens=None,
                       model_preferences=None):
        FakeLLM.calls += 1
        # match ONLY the current sentence (the "Current:" line), not the
        # full-text context which appears in every call
        import re as _re
        m = _re.search(r"Current:\s*(\{.*?\})\s*Preceding", user_prompt, _re.S)
        curr = json.loads(m.group(1)) if m else {}
        KEEP = {id(sentences[0]), id(sentences[2])}  # drop the middle
        for sent in sentences:
            if curr.get("start") == sent["start"] and \
                    curr.get("end") == sent["end"] and \
                    curr.get("text") == sent["text"]:
                if id(sent) in KEEP:
                    return json.dumps({"reason": "fixture: keep",
                                       "res": [{"text": sent["text"],
                                                "start": sent["start"],
                                                "end": sent["end"]}]})
                return json.dumps({"reason": "fixture: drop", "res": []})
        return json.dumps({"reason": "fixture: no-match drop", "res": []})

async def main():
    settings = load_settings(os.environ.get("OPENSTORYLINE_CONFIG", "/opt/openstoryline/config.toml"))
    checks = {}
    def check(name, ok, detail=""):
        checks[name] = {"ok": bool(ok), "detail": detail}
        print(("PASS " if ok else "FAIL ") + name + (f" | {detail}" if detail else ""))

    class FakeMcpCtx:
        class request_context:
            request = None
        async def report_progress(self, *a, **kw):
            return None

    def mk_state():
        return NodeState(session_id="downstream", artifact_id="d1",
                         lang="zh", node_summary=NodeSummary(),
                         llm=FakeLLM(), mcp_ctx=FakeMcpCtx())

    # ---------- 3. SpeechRoughCutNode (real node, fake LLM boundary) ----------
    rc = SpeechRoughCutNode(settings)
    os.makedirs("/task/cache", exist_ok=True)
    rc_result = await rc(mk_state(), mode="auto", lang="zh",
                         asr={"asr_infos": asr_infos},
                         user_request="remove the middle sentence",
                         gap_threshold=400)
    if rc_result.get("isError") or "tool_excute_result" not in rc_result:
        json.dump(rc_result, open(OUT / "roughcut_error_dump.json", "w"),
                  ensure_ascii=False, indent=1, default=str)
        raise RuntimeError(f"roughcut node failed: {json.dumps(rc_result, default=str)[:600]}")
    rc_out = rc_result["tool_excute_result"]
    clips = rc_out["clips"]
    rc_jsons = rc_out["rough_cut_jsons"]
    check("roughcut_llm_called", FakeLLM.calls == len(sentences),
          f"calls={FakeLLM.calls}")
    check("roughcut_clips_produced", len(clips) >= 1, f"clips={len(clips)}")
    # keep ranges: s1 [300,2100] and s3 [7300,9600]; 400ms gap keeps them apart
    ranges = [(c["source_ref"]["start"], c["source_ref"]["end"]) for c in clips]
    check("roughcut_keep_ranges", ranges == [(300, 2100), (7300, 9600)],
          f"ranges={ranges}")
    # calibrated rough_cut_json: time of kept items shifted by deleted middle
    flat = [it for sub in rc_jsons for it in sub]
    cal = sorted((it["start"], it["end"]) for it in flat)
    # deleted [2100,7300] = 5200ms; second item shifts by -5200
    # native calibrate_asr_times behavior: boundary points map to the
    # deleted-segment start; the LAST item end (9300) reveals an upstream
    # remap quirk (t beyond all deleted ranges subtracts only prefix[-1][2],
    # not the full deleted total) — recorded as a finding, NOT modified
    # (rendering uses clip source_ref, not these calibrated values)
    expected_cal_native = [(0, 1800), (1800, 9300)]
    check("roughcut_calibrated_native_behavior",
          cal == expected_cal_native, f"cal={cal}")
    for c in clips:
        check(f"clip_exists:{c['clip_id']}",
              os.path.exists(c["path"]), c["path"])

    # ---------- 4. PlanTimelineProNode ----------
    pt = PlanTimelineProNode(settings)
    pt_result = await pt(mk_state(), mode="auto", lang="zh",
                         is_speech_rough_cut=True,
                         speech_rough_cut=rc_out,
                         load_media={"medias": [{"media_id": "m0",
                                                 "path": SYNTH}]})
    pt_out = pt_result["tool_excute_result"]
    tracks = (pt_out.get("plan_timeline") or pt_out).get("tracks", {}) \
        if isinstance(pt_out, dict) else {}
    video_track = tracks.get("video", [])
    check("timeline_video_track", len(video_track) == 2,
          f"segments={len(video_track)}")
    tl_windows = [(s["timeline_window"]["start"], s["timeline_window"]["end"])
                  for s in video_track]
    check("timeline_windows_concat",
          tl_windows == [(0, 1800), (1800, 4100)], f"{tl_windows}")
    src_windows = [(s["source_window"]["start"], s["source_window"]["end"])
                   for s in video_track]
    check("timeline_source_windows_relative_to_slices",
          src_windows == [(0, 1800), (0, 2300)], f"{src_windows}")
    check("timeline_source_paths_are_slices",
          all("speech_rough_cut_" in str(s.get("source_path", ""))
              for s in video_track))

    # ---------- 5. RenderVideoNode ----------
    rv = RenderVideoNode(settings)
    rv_result = await rv(mk_state(), mode="auto", lang="zh",
                         load_media={"medias": [{"media_id": "m0",
                                                 "path": SYNTH}]},
                         plan_timeline={"tracks": tracks},
                         transition_rec=[], text_rec=[],
                         aspect_ratio="16:9",
                         output_max_dimension_px=854,
                         include_video_audio=True)
    json.dump(rv_result, open(OUT / "render_raw_result.json", "w"),
              ensure_ascii=False, indent=1, default=str)
    rv_out = rv_result.get("tool_excute_result") or {}
    out_path = rv_out.get("output_path") or rv_out.get("path") \
        or rv_out.get("video_path")
    check("render_output_exists", out_path and os.path.exists(out_path),
          str(out_path))
    if out_path and os.path.exists(out_path):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_name,codec_type,width,height,avg_frame_rate",
             "-of", "json", out_path], capture_output=True, text=True)
        meta = json.loads(probe.stdout)
        dur = float(meta["format"]["duration"])
        vstream = next(s for s in meta["streams"]
                       if s["codec_type"] == "video")
        astreams = [s for s in meta["streams"] if s["codec_type"] == "audio"]
        check("render_duration_matches_keep",
              abs(dur - 4.1) < 0.3, f"dur={dur:.2f}s expected=4.10s")
        check("render_resolution", (vstream["width"], vstream["height"]) == (854, 480),
              f"{vstream['width']}x{vstream['height']}")
        check("render_fps", abs(float(vstream["avg_frame_rate"].split("/")[0]) /
              max(1, float(vstream["avg_frame_rate"].split("/")[1]) or 1) - 25) < 1,
              vstream["avg_frame_rate"])
        check("render_has_audio", bool(astreams))
        check("render_codecs",
              vstream["codec_name"] == "h264" and
              all(a["codec_name"] == "aac" for a in astreams))

        # ---------- 6. cuts.json from ACTUAL keep ranges ----------
        keep = sorted((c["source_ref"]["start"], c["source_ref"]["end"])
                      for c in clips)
        cuts, prev = [], 0
        for s, e in keep:
            if s > prev:
                cuts.append({"start_ms": prev, "end_ms": s,
                             "reason": "removed by rough-cut fixture"})
            prev = e
        if prev < 10000:
            cuts.append({"start_ms": prev, "end_ms": 10000,
                         "reason": "removed by rough-cut fixture"})
        cuts_doc = {"cuts": cuts}
        json.dump(cuts_doc, open(OUT / "cuts.json", "w"), indent=1)
        total_keep = sum(e - s for s, e in keep)
        check("cuts_json_consistent_with_render",
              abs(total_keep / 1000.0 - dur) < 0.3,
              f"keep={total_keep}ms render={dur*1000:.0f}ms cuts={len(cuts)}")

    json.dump({"checks": checks, "roughcut": rc_out, "timeline": pt_out,
               "render": rv_out, "asr_fixture": asr_infos,
               "fake_llm_calls": FakeLLM.calls},
              open(OUT / "downstream_result.json", "w"),
              ensure_ascii=False, indent=1, default=str)
    failed = [k for k, v in checks.items() if not v["ok"]]
    print("\nDOWNSTREAM OVERALL:", "PASS" if not failed else f"FAILED: {failed}")

asyncio.run(main())
