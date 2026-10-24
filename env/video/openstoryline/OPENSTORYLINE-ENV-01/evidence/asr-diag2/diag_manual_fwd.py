"""Manual forward pass: replicate model.inference internals, decode with
tokens.json lookup. Decisive test for the vocab-mismatch hypothesis."""
import json, wave
import numpy as np
import torch
M = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"
from funasr import AutoModel
m = AutoModel(model=M, disable_update=True, disable_pbar=True)
model, frontend = m.model, m.kwargs.get("frontend")

tokens = json.load(open(M + "/tokens.json"))
sos = eos = None
for i, t in enumerate(tokens):
    if t == "<s>": sos = i
    if t == "</s>": eos = i
blank = tokens.index("<blank>") if "<blank>" in tokens else 0
print(f"sos={sos} eos={eos} blank={blank} vocab={len(tokens)}")

def run(wav_path, tag):
    w = wave.open(wav_path)
    assert w.getframerate() == 16000 and w.getnchannels() == 1
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close()
    speech = torch.from_numpy(raw.astype(np.float32) / 32768.0)[None, :]
    speech_lens = torch.tensor([speech.shape[1]])
    with torch.no_grad():
        enc_outs = model.encoder(frontend(speech, speech_lens)[0], speech_lens) if False else None
        feats, feats_lens = frontend(speech, speech_lens)
        enc = model.encoder(feats, feats_lens)
        encoder_out, encoder_out_lens = enc[0], enc[1]
        predictor_outs = model.calc_predictor(encoder_out, encoder_out_lens)
        pre_acoustic_embeds, pre_token_length, alphas, pre_peak_index = (
            predictor_outs[0], predictor_outs[1], predictor_outs[2], predictor_outs[3])
        pre_token_length = pre_token_length.round().long()
        if torch.max(pre_token_length) < 1:
            print(tag, ": no tokens predicted"); return
        decoder_outs = model.cal_decoder_with_predictor(
            encoder_out, encoder_out_lens, pre_acoustic_embeds, pre_token_length)
        decoder_out, ys_pad_lens = decoder_outs[0], decoder_outs[1]
    i = 0
    am_scores = decoder_out[i, : pre_token_length[i], :]
    yseq = am_scores.argmax(dim=-1).tolist()
    token_int = [t for t in yseq if t not in (sos, eos, blank)]
    pieces = [tokens[t] for t in token_int]
    text_table = "".join(pieces).replace("▁", " ").strip()
    # bpe decode for contrast
    import sentencepiece as spm
    sp = spm.SentencePieceProcessor(); sp.load(M + "/bpe.model")
    text_bpe = sp.DecodeIds(token_int)
    print(f"--- {tag} ---")
    print("tokens.json decode:", text_table[:400])
    print("bpe.model decode :", text_bpe[:400])
    return {"token_int": token_int, "table_decode": text_table,
            "bpe_decode": text_bpe, "pre_peak_index": pre_peak_index[i].tolist(),
            "alphas_len": int(alphas[i].shape[0]) if hasattr(alphas[i], 'shape') else len(alphas[i])}

out = {}
out["official"] = run(M + "/example/asr_example.wav", "official example")
import subprocess
subprocess.run(["cp", "/task/out_ro/source.mp4", "/tmp/s.mp4"])
subprocess.run(["ffmpeg", "-y", "-i", "/tmp/s.mp4", "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1", "/tmp/i.wav"], capture_output=True)
out["interview"] = run("/tmp/i.wav", "interview 37s")
json.dump(out, open("/task/out_ro/c_manual_forward.json", "w"),
          ensure_ascii=False, indent=1)
