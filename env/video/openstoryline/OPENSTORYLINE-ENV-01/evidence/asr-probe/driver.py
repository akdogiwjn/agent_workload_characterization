"""Drive OpenStoryline's REAL LocalASRNode path with the English model.

Subclass overrides ONLY _load_asr_model (paraformer-en + fsmn-vad + ct-punc);
process / extract_audio_wav / _combine_tool_outputs are the untouched
upstream implementation from the isolated copy at commit c9e94521."""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/opt/openstoryline/src")
sys.path.insert(0, "/opt/openstoryline")

from open_storyline.nodes.core_nodes.asr_node import LocalASRNode
from open_storyline.nodes.node_state import NodeState
from open_storyline.nodes.node_summary import NodeSummary
from types import SimpleNamespace

STUB_SERVER_CFG = SimpleNamespace(local_mcp_server=SimpleNamespace(server_cache_dir='cache'))


class EnglishLocalASRNode(LocalASRNode):
    def _load_asr_model(self):
        if not hasattr(self, "asr_model"):
            from funasr import AutoModel
            self.asr_model = AutoModel(
                model="paraformer-en",
                vad_model="fsmn-vad",
                punc_model="ct-punc",
                vad_kwargs={"max_single_segment_time": 30000},
            )
        return self.asr_model


def main():
    import os
    os.makedirs("/task/out", exist_ok=True)
    node = EnglishLocalASRNode(server_cfg=STUB_SERVER_CFG)
    state = NodeState(session_id="os-asr-probe", artifact_id="probe-1",
                      lang="en", node_summary=NodeSummary(), llm=None,
                      mcp_ctx=None)
    inputs = {"split_shots": {"clips": [{
        "clip_id": "c000", "path": "/task/source.mp4",
        "kind": "video", "source_ref": {}, "fps": 25}]}}
    t0 = time.monotonic()
    raw = asyncio.run(node.process(state, inputs))
    regularized = node._combine_tool_outputs(state, raw)
    elapsed = time.monotonic() - t0

    with open("/task/out/asr_raw.json", "w") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1, default=str)
    with open("/task/out/asr_regularized.json", "w") as f:
        json.dump({"regularized": regularized, "elapsed_s": elapsed},
                  f, ensure_ascii=False, indent=1, default=str)
    asr = regularized["asr_infos"][0]
    print("elapsed_s:", round(elapsed, 1))
    print("text:", asr["asr_text"][:300])
    print("timestamp items:", len(asr["asr_timestamps"]))
    print("sentences:", len(asr["asr_sentence_info"]))
    if asr["asr_sentence_info"]:
        s0 = asr["asr_sentence_info"][0]
        print("sentence[0] keys:", sorted(s0.keys()))
        print("sentence[0]:", json.dumps(s0, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
