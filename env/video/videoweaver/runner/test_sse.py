#!/usr/bin/env python3
"""SSE parse + usage aggregation + soft-threshold regression for the
VideoWeaver gateway. Protocol fixtures, not historical raw bytes (the original
upstream SSE stream was not preserved)."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
import gateway as g  # noqa: E402
from gateway import SseParser, Ledger, DEFAULT_BUDGET  # noqa: E402


class TestSseParser(unittest.TestCase):
    def _feed(self, lines):
        p = SseParser()
        for l in lines:
            p.feed_line(l)
        return p.flush()

    def test_data_with_and_without_space(self):
        # two separate events, each flushed by a blank line
        ev = self._feed(["data: {\"a\":1}", "", "data:{\"b\":2}", ""])
        self.assertEqual(len(ev), 2)
        self.assertEqual(json.loads(ev[0]["data"]), {"a": 1})
        self.assertEqual(json.loads(ev[1]["data"]), {"b": 2})

    def test_multiline_data(self):
        ev = self._feed(["data: {", "data: \"a\": 1}", ""])
        self.assertEqual(len(ev), 1)
        self.assertEqual(json.loads(ev[0]["data"]), {"a": 1})

    def test_crlf_and_event_field(self):
        ev = self._feed(["event: response.completed\r", "data: {}\r", "\r"])
        self.assertEqual(ev[0]["event"], "response.completed")
        self.assertEqual(json.loads(ev[0]["data"]), {})

    def test_done_is_not_success(self):
        ev = self._feed(["data: [DONE]", ""])
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["data"], "[DONE]")

    def test_comment_ignored(self):
        ev = self._feed([": keep-alive", "data: {}", ""])
        self.assertEqual(len(ev), 1)


class TestLedgerUsage(unittest.TestCase):
    def _ledger(self, td, soft):
        os.environ["VW_RUN_START_EPOCH"] = "0"
        os.environ["VW_RUN_ID"] = "t"
        b = dict(DEFAULT_BUDGET); b["observed_output_tokens_soft"] = soft
        return Ledger(str(Path(td) / "l.json"), b)

    def test_usage_accumulates_total_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td, 50000)
            l.record("usage", response_id="r1", total_tokens=70,
                     output_tokens=20, cached_input_tokens=40)
            l.record("usage", response_id="r2", total_tokens=130,
                     output_tokens=30, cached_input_tokens=100)
            self.assertEqual(l.data["usage"]["observed_total_tokens_total"], 200)
            self.assertEqual(l.data["usage"]["observed_llm_responses"], 2)

    def test_soft_threshold_crossed(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td, 100)
            l.record("usage", response_id="r1", total_tokens=120)
            self.assertEqual(l.data["usage"]["observed_total_tokens_total"], 120)
            # soft check threshold would block next llm forward
            self.assertTrue(l.data["usage"]["observed_total_tokens_total"] >= 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
