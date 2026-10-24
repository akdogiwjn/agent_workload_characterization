"""A: official example audio, base inference only."""
import json, wave, time
EX = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master/example/asr_example.wav"
# inspect audio
w = wave.open(EX)
info = {"channels": w.getnchannels(), "sampwidth": w.getsampwidth(),
        "framerate": w.getframerate(), "frames": w.getnframes(),
        "duration_s": w.getnframes() / w.getframerate()}
w.close()
import numpy as np
raw = np.frombuffer(open(EX, "rb").read()[44:], dtype=np.int16) \
    if info["sampwidth"] == 2 else None
info["abs_max"] = int(np.abs(raw).max()) if raw is not None else None
info["rms"] = float(np.sqrt((raw.astype(float) ** 2).mean())) if raw is not None else None
print("example audio:", json.dumps(info))

from funasr import AutoModel
m = AutoModel(model="/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master",
              disable_update=True, disable_pbar=True)
t0 = time.time()
res = m.generate(input=EX)
elapsed = time.time() - t0
r = res[0]
out = {"info": info, "elapsed_s": round(elapsed, 2),
       "keys": sorted(r.keys()), "text": r.get("text", ""),
       "call_count": 1, "components": "base ASR only"}
json.dump(out, open("/task/out/a_official_example.json", "w"),
          ensure_ascii=False, indent=1)
print("keys:", out["keys"])
print("text:", out["text"])
