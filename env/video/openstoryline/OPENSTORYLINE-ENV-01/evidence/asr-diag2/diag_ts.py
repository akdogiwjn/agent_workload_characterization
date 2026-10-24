"""Timestamp diagnosis: pred_timestamp=True behavior on this checkpoint."""
import json, traceback
M = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"
from funasr import AutoModel
m = AutoModel(model=M, disable_update=True, disable_pbar=True)

out = {}
# test 1: pred_timestamp=True
try:
    res = m.generate(input=M + "/example/asr_example.wav", pred_timestamp=True)
    r = res[0]
    out["pred_timestamp"] = {"keys": sorted(r.keys()),
                             "has_timestamp": "timestamp" in r,
                             "timestamp_sample": (r.get("timestamp") or [])[:5],
                             "text": r.get("text", "")[:100]}
    print("pred_timestamp=True keys:", sorted(r.keys()))
    if r.get("timestamp"):
        print("timestamp[:5]:", r["timestamp"][:5])
except Exception as e:
    out["pred_timestamp"] = {"error": f"{type(e).__name__}: {e}",
                             "tb": traceback.format_exc()[-800:]}
    print("pred_timestamp=True ERROR:", type(e).__name__, str(e)[:150])

# test 2: sentence_timestamp=True without VAD (exact KeyError repro)
try:
    res = m.generate(input=M + "/example/asr_example.wav", sentence_timestamp=True)
    r = res[0]
    out["sentence_timestamp"] = {"keys": sorted(r.keys()),
                                 "has_sentence_info": "sentence_info" in r}
    print("sentence_timestamp=True keys:", sorted(r.keys()))
except Exception as e:
    out["sentence_timestamp"] = {"error": f"{type(e).__name__}: {e}",
                                 "tb": traceback.format_exc()[-600:]}
    print("sentence_timestamp=True ERROR:", type(e).__name__, str(e)[:150])

json.dump(out, open("/task/out_ro/d_ts_probe.json", "w"), ensure_ascii=False, indent=1)
