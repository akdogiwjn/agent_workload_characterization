"""Environment & loading identity capture (no inference)."""
import json, sys
result = {}
result["python"] = sys.version
import funasr, torch, torchaudio
result["funasr"] = funasr.__version__
result["torch"] = torch.__version__
result["torchaudio"] = torchaudio.__version__
result["torch_threads"] = torch.get_num_threads()
result["device"] = "cpu"
MODEL = "/root/.cache/modelscope/models/iic--speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020/snapshots/master"
import logging, io
buf = io.StringIO()
h = logging.StreamHandler(buf)
logging.getLogger().addHandler(h)
logging.getLogger().setLevel(logging.DEBUG)
from funasr import AutoModel
m = AutoModel(model=MODEL, disable_update=True, disable_pbar=True)
result["load_log_tail"] = buf.getvalue()[-3000:]
result["model_path"] = m.model_path
cfg = m.model.conf if hasattr(m.model, "conf") else {}
result["key_conf"] = {
    k: cfg.get(k) for k in ("model", "predictor", "predictor_conf",
                             "tokenizer", "tokenizer_conf", "frontend",
                             "frontend_conf")}
tok = getattr(m, "tokenizer", None)
result["tokenizer_type"] = type(tok).__name__ if tok else None
result["vocab_size"] = len(getattr(tok, "token_list", []) or []) if tok else None
result["bpemodel"] = str(getattr(tok, "bpemodel", None))
json.dump(result, open("/task/out/env_identity.json", "w"),
          ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: result[k] for k in
                  ("python", "funasr", "torch", "torchaudio",
                   "tokenizer_type", "vocab_size", "model_path")},
                 indent=1))
