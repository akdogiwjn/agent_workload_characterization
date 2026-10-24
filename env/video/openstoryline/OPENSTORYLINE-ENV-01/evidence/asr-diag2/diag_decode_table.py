"""Decisive test B: decode with tokens.json table -> text should be readable."""
import json, wave, time
import numpy as np
import torch
M = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"

from funasr import AutoModel
m = AutoModel(model=M, disable_update=True, disable_pbar=True)

# locate the tokenizer object used at generate time
tok = None
for attr in ("tokenizer",):
    if hasattr(m, attr):
        tok = getattr(m, attr)
print("m.tokenizer:", type(tok).__name__ if tok else None)

tokens = json.load(open(M + "/tokens.json"))

# patch ids2tokens/tokens2text to use tokens.json lookup
class TableTokenizer:
    def __init__(self, table):
        self.table = table
    def ids2tokens(self, ids, **kw):
        return [self.table[int(i)] for i in ids]
    def tokens2text(self, toks, **kw):
        return "".join(toks).replace("▁", " ").strip()
    def decode(self, ids, **kw):
        return self.tokens2text(self.ids2tokens(ids))

table_tok = TableTokenizer(tokens)
if tok is not None:
    tok.ids2tokens = table_tok.ids2tokens
    tok.tokens2text = table_tok.tokens2text
    tok.decode = table_tok.decode
    print("patched tokenizer:", type(tok).__name__)

# official example
res_a = m.generate(input=M + "/example/asr_example.wav")
print("A official example:", res_a[0].get("text", "")[:300])
json.dump({"a_official_table_decode": res_a[0]},
          open("/task/out/b_official_table.json", "w"), ensure_ascii=False, indent=1)

# interview: plain ffmpeg extract, NO afftdn/agate
import subprocess, tempfile, os
with tempfile.TemporaryDirectory() as td:
    wav_out = os.path.join(td, "a.wav")
    subprocess.run(["ffmpeg", "-y", "-i", "/task/source.mp4", "-vn",
                    "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_out],
                   capture_output=True)
    w = wave.open(wav_out)
    print("interview wav:", w.getnchannels(), "ch", w.getframerate(), "Hz",
          round(w.getnframes()/w.getframerate(), 2), "s")
    w.close()
    t0 = time.time()
    res_b = m.generate(input=wav_out)
    print("B interview (plain extract):", res_b[0].get("text", "")[:500])
    out = {"b_interview_table_decode": res_b[0], "elapsed_s": round(time.time()-t0,1),
           "keys": sorted(res_b[0].keys())}
    json.dump(out, open("/task/out/b_interview_table.json", "w"),
              ensure_ascii=False, indent=1)
    print("keys:", out["keys"])
