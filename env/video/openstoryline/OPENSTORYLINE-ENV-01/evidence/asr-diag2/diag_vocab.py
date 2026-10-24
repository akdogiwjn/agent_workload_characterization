"""Decisive test: decode argmax ids with tokens.json table vs bpe.model."""
import json, torch
M = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"

# 1) decoder embed dimension -> true vocab size of the model output space
ckpt = torch.load(M + "/model.pt", map_location="cpu", weights_only=False)
sd = ckpt if isinstance(ckpt, dict) and "model" not in ckpt else ckpt.get("model", ckpt)
for k, v in sd.items():
    if "decoder.embed" in k or "decoder_embed" in k:
        print("embed:", k, tuple(v.shape))
        break
for k, v in sd.items():
    if "predictor" in k and "weight" in k and v.dim() == 2:
        print("predictor proj:", k, tuple(v.shape))
        break
for k, v in sd.items():
    if "after_norm" in k or ("decoder" in k and "norm" in k and v.dim() == 1):
        print("decoder norm dim:", k, tuple(v.shape)); break

# 2) run inference, capture token_int before tokenizer decode
from funasr import AutoModel
m = AutoModel(model=M, disable_update=True, disable_pbar=True)
tokens = json.load(open(M + "/tokens.json"))

import numpy as np
orig_inference = m.model.inference
captured = {}
def patched(data_in, *a, **kw):
    # intercept at the point after argmax by re-running the pieces manually
    return orig_inference(data_in, *a, **kw)

# simpler: use funasr internals — decode with tokens.json directly
res = m.generate(input=M + "/example/asr_example.wav")
r = res[0]
print("default text:", r.get("text", "")[:200])

# 3) manual forward pass to get raw argmax ids
import torchaudio
wav, sr = torchaudio.load(M + "/example/asr_example.wav")
if sr != 16000:
    wav = torchaudio.functional.resample(wav, sr, 16000)
speech = wav.mean(dim=0) if wav.shape[0] > 1 else wav[0]
with torch.no_grad():
    out = m.model.inference(data_in=speech[None, :], data_lengths=torch.tensor([len(speech)]),
                            key=["ex"], tokenizer=None, frontend=m.frontend)
# this path may not work without frontend; fallback below
print("manual path done")
