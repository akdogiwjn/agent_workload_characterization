from __future__ import annotations

import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_runtime.session_index import SessionIndex
from agent_runtime.vimax_adapters import ViMaxAdapters


class FakeScriptPipeline:
    seen_script = None

    def __init__(self, **_kwargs):
        pass

    async def plan_text_artifacts(self, **kwargs):
        type(self).seen_script = kwargs["script"]


class FrozenScriptSessionTests(unittest.TestCase):
    def test_session_source_is_initialized_before_agent_and_tool_cannot_replace_it(self):
        frozen = (
            "Shot 1: photographer’s camera at sunrise.\n"
            "Shot 2: photographer’s camera at night."
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_file = root / "registered-script.txt"
            script_file.write_bytes(frozen)
            session_id = "planning-validation-02"
            index = SessionIndex(root)
            index.create(script=frozen.decode("utf-8"), planning_mode="script",
                         user_requirement="exactly two registered test shots",
                         style="documentary", session_id=session_id)
            with patch.dict("os.environ", {
                    "VIMAX_FIXED_SCRIPT_SESSION_ID": session_id,
                    "VIMAX_FIXED_SCRIPT_PATH": str(script_file)}), \
                    patch("agent_runtime.vimax_adapters._build_chat_model",
                          return_value=object()), \
                    patch("agent_runtime.vimax_adapters.Script2VideoPipeline",
                          FakeScriptPipeline):
                adapter = ViMaxAdapters(root, index)
                rejected = asyncio.run(adapter.vimax_narrative_planning({
                    "session_id": session_id,
                    "script": "different replacement script",
                }))
                missing_session = asyncio.run(adapter.vimax_narrative_planning({}))
                self.assertFalse(rejected.ok)
                self.assertEqual(rejected.metadata["error_type"],
                                 "fixed_script_mismatch")
                self.assertFalse(missing_session.ok)
                self.assertEqual(missing_session.metadata["error_type"],
                                 "fixed_session_mismatch")
                accepted = asyncio.run(adapter.vimax_narrative_planning({
                    "session_id": session_id,
                }))
            self.assertTrue(accepted.ok)
            self.assertEqual(FakeScriptPipeline.seen_script, frozen.decode("utf-8"))
            self.assertEqual(script_file.read_bytes(), frozen)
            session = index.get(session_id)
            self.assertEqual(session["planning_mode"], "script")
            self.assertEqual(session["script"].encode("utf-8"), frozen)
            self.assertEqual(hashlib.sha256(script_file.read_bytes()).hexdigest(),
                             hashlib.sha256(frozen).hexdigest())


if __name__ == "__main__":
    unittest.main(verbosity=2)
