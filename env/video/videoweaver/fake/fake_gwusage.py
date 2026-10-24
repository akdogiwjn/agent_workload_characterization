#!/usr/bin/env python3
"""Fake upstream for the gateway usage handler verification (offline, no creds).

Returns:
- Responses SSE with usage on a data line whose response has NO id (top-level
  response_id absent) -> the gateway must attribute it to the local request.
- chat/completions non-SSE usage (summary) -> must count toward the unified
  soft total.
Used to prove real-handler behavior (not just Ledger.record simulation)."""
from __future__ import annotations
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(__import__("os").environ.get("FAKE_PORT", "8666"))


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for name, data in events:
            self.wfile.write(f"event: {name}\n".encode())
            self.wfile.write(("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode())
        self.wfile.flush()

    def _responses(self):
        rid = "resp_" + uuid.uuid4().hex[:20]
        # first: an in_progress event WITHOUT usage and WITH a null response.id
        e1 = {"type": "response.output_item.added", "response": {"id": None, "status": "in_progress"}}
        # second: completed with usage but response.id is null and no top-level response_id
        e2 = {"type": "response.completed",
              "response": {"id": None, "status": "completed",
                           "usage": {"input_tokens": 5, "cached_input_tokens": 1,
                                     "output_tokens": 3, "reasoning_output_tokens": 1,
                                     "total_tokens": 8}}}
        resp = {"id": rid, "object": "response", "status": "completed", "output": [],
                "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}}
        self._sse([
            ("response.created", {"type": "response.created", "response": resp}),
            ("response.output_item.added", e1),
            ("response.completed", e2),
            ("message", {"type": "message", "data": "[DONE]"}),
        ])

    def _chat(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        body = {"choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 10, "cached_tokens": 4,
                          "completion_tokens": 4, "total_tokens": 14}}
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = self.path.rstrip("/")
        if path.endswith("/compatible-mode/v1/responses"):
            self._responses()
        elif path.endswith("/compatible-mode/v1/chat/completions"):
            self._chat()
        else:
            self.send_response(404); self.end_headers()

    def do_GET(self):
        self.send_response(404); self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
