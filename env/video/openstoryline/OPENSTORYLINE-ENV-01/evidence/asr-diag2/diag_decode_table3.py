import json, wave, time, subprocess
M = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"
from funasr import AutoModel
m = AutoModel(model=M, disable_update=True, disable_pbar=True)
tokens = json.load(open(M + "/tokens.json"))
tok = m.kwargs.get("tokenizer")
CALLS = {"n": 0}
def ids2tokens(ids, **kw):
    CALLS["n"] += 1
    return [tokens[int(i)] for i in ids]
def tokens2text(toks, **kw):
    return "".join(toks).replace("▁", " ").strip()
tok.ids2tokens = ids2tokens
tok.tokens2text = tokens2text

res_a = m.generate(input=M + "/example/asr_example.wav")
print("patch called:", CALLS["n"], "times")
print("A official:", res_a[0].get("text", "")[:300])
