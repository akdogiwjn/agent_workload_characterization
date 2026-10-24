"""Decisive test B2: patch m.kwargs['tokenizer'] with tokens.json lookup."""
import json, wave, time, os, subprocess
M = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"
from funasr import AutoModel
m = AutoModel(model=M, disable_update=True, disable_pbar=True)
tokens = json.load(open(M + "/tokens.json"))
tok = m.kwargs.get("tokenizer")
print("tokenizer:", type(tok).__name__, "| bpemodel:", getattr(tok, "bpemodel", None))
print("token_list len:", len(getattr(tok, "token_list", []) or []))

def ids2tokens(ids, **kw):
    return [tokens[int(i)] for i in ids]
def tokens2text(toks, **kw):
    return "".join(toks).replace("▁", " ").strip()
tok.ids2tokens = ids2tokens
tok.tokens2text = tokens2text

out = {}
res_a = m.generate(input=M + "/example/asr_example.wav")
out["a_official_table"] = res_a[0]
print("A official:", res_a[0].get("text", "")[:300])

subprocess.run(["mkdir", "-p", "/task/out"])
wav_out = "/task/out/interview_plain16k.wav"
subprocess.run(["ffmpeg", "-y", "-i", "/task/source.mp4", "-vn",
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_out],
               capture_output=True)
w = wave.open(wav_out); print("interview wav:", w.getnchannels(), "ch",
      w.getframerate(), "Hz", round(w.getnframes()/w.getframerate(), 2), "s"); w.close()
t0 = time.time()
res_b = m.generate(input=wav_out)
out["b_interview_table"] = res_b[0]
out["elapsed_s"] = round(time.time() - t0, 1)
print("B interview:", res_b[0].get("text", "")[:500])
print("keys:", sorted(res_b[0].keys()))
json.dump(out, open("/task/out/b2_table_decode.json", "w"), ensure_ascii=False, indent=1, default=str)
