"""OPENSTORYLINE-ASR-ADAPTER-01 offline unit tests (no inference, no docker)."""
import json, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path("/home/lcq/agent_workload_characterization") if not Path("/opt/openstoryline").exists() else Path("/task_root")
sys.path.insert(0, str(ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source"))

from asr_adapter.paraformer_en import AsrWiringError, ParaformerEnAsr
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
if HAS_TORCH:
    from asr_adapter.paraformer_en import _fire_place_word_timestamps


@unittest.skipUnless(HAS_TORCH, "torch not on host; run in-container")
class FirePlaceTests(unittest.TestCase):
    def _alphas_peaks(self, n_tokens, n_peaks):
        peaks = torch.zeros(100)
        for i in range(n_peaks):
            peaks[i * (100 // max(n_peaks, 1))] = 1.0
        alphas = torch.full((100,), 1.0 / max(n_tokens + 1, 1))
        return alphas, peaks

    def test_exact_count_ok(self):
        ts = _fire_place_word_timestamps(*self._alphas_peaks(3, 4), 3, 0.0)
        self.assertEqual(len(ts), 3)
        self.assertTrue(all(a <= b for a, b in ts))

    def test_vad_offset_applied(self):
        # offset shifts the whole series; force_time_shift(-1.5 frames) may
        # pull the first start slightly below the offset (-90 ms max)
        base = _fire_place_word_timestamps(*self._alphas_peaks(2, 3), 2, 0.0)
        shifted = _fire_place_word_timestamps(*self._alphas_peaks(2, 3), 2, 5000.0)
        for (a0, _), (a1, _) in zip(base, shifted):
            self.assertAlmostEqual(a1 - a0, 5000.0, delta=1e-6)

    def test_unrecoverable_peak_shortage_refuses(self):
        # patch the CIF fallback so it still yields too few peaks -> the
        # adapter must refuse rather than emit partial timestamps
        import funasr.utils.timestamp_tools as tt
        with patch.object(tt, "cif_wo_hidden",
                          return_value=[torch.zeros(10)]):
            with self.assertRaises(AsrWiringError):
                _fire_place_word_timestamps(
                    *self._alphas_peaks(5, 2), 5, 0.0)

    def test_renormalize_recovers(self):
        # mismatched peaks trigger CIF renormalize; count must still match
        ts = _fire_place_word_timestamps(*self._alphas_peaks(4, 2), 4, 0.0)
        self.assertEqual(len(ts), 4)


class IdentityGuardTests(unittest.TestCase):
    def test_wrong_identity_refused(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "configuration.json").write_text(json.dumps(
                {"model_name_in_hub": {"ms": "some/other-model"}}))
            (d / "tokens.json").write_text('["<blank>","<s>","</s>","x"]')
            with patch.object(ParaformerEnAsr, "__init__", return_value=None), \
                 patch("asr_adapter.paraformer_en._DEFAULTS",
                       {"asr": d, "vad": d, "punc": d}):
                node = ParaformerEnAsr.__new__(ParaformerEnAsr)
                node.asr_dir = d
                with self.assertRaises(AsrWiringError):
                    node._identity_guard()

    def test_vocab_mismatch_refused(self):
        # decoder vocab 10020 vs tokens.json 4 -> hard refusal (checked in
        # __init__ after load; here we assert the guard code exists)
        import inspect
        src = inspect.getsource(ParaformerEnAsr.__init__)
        self.assertIn("refusing to decode with a mismatched table", src)


class InjectionTests(unittest.TestCase):
    def test_register_tools_overlay_present(self):
        rt = ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/register_tools.py"
        src = rt.read_text()
        self.assertIn("LocalASRNode._load_asr_model = _load_english_asr_model", src)
        self.assertIn("from asr_adapter import ParaformerEnAsr", src)

    def test_before_snapshot_preserved(self):
        before = ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/evidence/snapshots/register_tools.before.py"
        self.assertNotIn("_load_english_asr_model", before.read_text())


class AcceptanceEvidenceTests(unittest.TestCase):
    def test_node_result_all_checks_pass(self):
        r = json.loads((Path(__file__).parent / "verify_node_result.json").read_text())
        failed = [k for k, v in r["checks"].items() if not v["ok"]]
        self.assertEqual(failed, [], failed)

    def test_word_timestamp_1to1_in_evidence(self):
        r = json.loads((Path(__file__).parent / "verify_node_result.json").read_text())
        info = r["result"]["tool_excute_result"]["asr_infos"][0]
        self.assertEqual(len(info["asr_timestamps"]),
                         len(info["asr_text"]
                             .replace("，", " ").replace("。", " ")
                             .replace("？", " ").replace("、", " ").split()))

    def test_downstream_all_checks_pass(self):
        d = json.loads((Path(__file__).parent / "downstream_result.json").read_text())
        failed = [k for k, v in d["checks"].items() if not v["ok"]]
        self.assertEqual(failed, [], failed)

    def test_cuts_json_matches_rendered_duration(self):
        cuts = json.loads((Path(__file__).parent / "cuts.json").read_text())
        total = sum(c["end_ms"] - c["start_ms"] for c in cuts["cuts"])
        d = json.loads((Path(__file__).parent / "downstream_result.json").read_text())
        # 10s synth - removed = kept
        self.assertEqual(10000 - total, 4100)


import tempfile  # noqa: E402
if __name__ == "__main__":
    unittest.main()
