"""Final: prove the contract CAN be met with minimal fixes.
Manual forward + tokens.json decode + ts_prediction_lfr6_standard
word timestamps + sentence assembly -> {text, timestamp, sentence_info}."""
import json, wave
import numpy as np
import torch
M = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"
from funasr import AutoModel
m = AutoModel(model=M, disable_update=True, disable_pbar=True)
model, frontend = m.model, m.kwargs["frontend"]
tokens = json.load(open(M + "/tokens.json"))
sos, eos, blank = 1, 2, 0

from funasr.utils.timestamp_tools import ts_prediction_lfr6_standard

def full_asr(wav_path):
    w = wave.open(wav_path)
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    sr = w.getframerate(); w.close()
    assert sr == 16000
    speech = torch.from_numpy(raw.astype(np.float32) / 32768.0)[None, :]
    speech_lens = torch.tensor([speech.shape[1]])
    with torch.no_grad():
        feats, feats_lens = frontend(speech, speech_lens)
        enc = model.encoder(feats, feats_lens)
        encoder_out, encoder_out_lens = enc[0], enc[1]
        po = model.calc_predictor(encoder_out, encoder_out_lens)
        pre_acoustic_embeds, pre_token_length, alphas, pre_peak_index = po[0], po[1], po[2], po[3]
        pre_token_length = pre_token_length.round().long()
        do = model.cal_decoder_with_predictor(encoder_out, encoder_out_lens,
                                              pre_acoustic_embeds, pre_token_length)
        decoder_out = do[0]
    i = 0
    am_scores = decoder_out[i, : pre_token_length[i], :]
    yseq = am_scores.argmax(dim=-1).tolist()
    token_int = [t for t in yseq if t not in (sos, eos, blank)]
    pieces = [tokens[t] for t in token_int]
    text = "".join(pieces).replace("▁", " ").strip()
    # word-level timestamps exactly as funasr model.py does for pred_timestamp
    ts_str, ts = ts_prediction_lfr6_standard(
        pre_peak_index[i], alphas[i], list(pieces),
        vad_offset=0, upsample_rate=1)
    # simple sentence assembly on punctuation (mirrors timestamp_sentence intent)
    sentences, cur_words, cur_ts = [], [], []
    for piece, t in zip(pieces, ts):
        cur_words.append(piece); cur_ts.append(t)
        word = piece.lstrip("▁")
        if word and word[-1] in ".?!":
            seg_text = "".join(cur_words).replace("▁", " ").strip()
            sentences.append({"text": seg_text,
                              "start": cur_ts[0][0], "end": cur_ts[-1][1],
                              "timestamp": [list(x) for x in cur_ts]})
            cur_words, cur_ts = [], []
    if cur_words:
        seg_text = "".join(cur_words).replace("▁", " ").strip()
        sentences.append({"text": seg_text, "start": cur_ts[0][0],
                          "end": cur_ts[-1][1],
                          "timestamp": [list(x) for x in cur_ts]})
    return {"text": text, "timestamp": [list(x) for x in ts],
            "sentence_info": sentences}

import subprocess
out = {}
# official example
res = full_asr(M + "/example/asr_example.wav")
out["official"] = res
print("== official ==")
print("text:", res["text"][:200])
print("timestamp[:4]:", res["timestamp"][:4])
print("sentences:", len(res["sentence_info"]))
# interview
subprocess.run(["cp", "/task/out_ro/source.mp4", "/tmp/s.mp4"])
subprocess.run(["ffmpeg", "-y", "-i", "/tmp/s.mp4", "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1", "/tmp/i.wav"], capture_output=True)
res2 = full_asr("/tmp/i.wav")
out["interview"] = res2
print("== interview 37s ==")
print("text:", res2["text"][:300])
ts = res2["timestamp"]
print("timestamp items:", len(ts), "| first:", ts[0] if ts else None,
      "| last:", ts[-1] if ts else None)
print("units ms? last_end <= 37056:", ts[-1][1] if ts else None)
mono = all(ts[k][0] <= ts[k][1] for k in range(len(ts)))
ordered = all(ts[k][1] <= ts[k+1][0] or ts[k][0] <= ts[k+1][0] for k in range(len(ts)-1))
print("start<=end all:", mono, "| roughly ordered:", ordered)
print("sentences:", len(res2["sentence_info"]))
for s in res2["sentence_info"][:3]:
    print("  ", s["start"], "-", s["end"], "ms:", s["text"][:60])
json.dump(out, open("/task/out_ro/d_full_chain.json", "w"), ensure_ascii=False, indent=1)
