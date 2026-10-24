#!/usr/bin/env python3
"""Minimal fake Responses upstream used ONLY to probe what the real Codex
exec_command shell actually resolves (python/pip) and to validate gateway SSE
terminal/usage capture in a small offline session."""
from __future__ import annotations
import json, os, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("FAKE_PORT", "8666"))
CMD = os.environ.get("VW_SHELLTEST_CMD",
                     "python -c 'import sys;print(sys.executable);import requests;print(\"REQOK\")'")

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
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        rid = "resp_" + uuid.uuid4().hex[:20]
        n = self.headers.get("X-Round", "1")
        # count rounds via ledger-less state: inspect body for a previous fco
        text = body.decode("utf-8", "replace")
        if "function_call_output" in text:
            item = {"id": "msg_" + uuid.uuid4().hex[:12], "type": "message",
                    "status": "completed", "role": "assistant",
                    "content": [{"type": "output_text", "text": "DONE", "annotations": []}]}
            resp = {"id": rid, "object": "response", "created_at": int(time.time()),
                    "status": "completed", "model": "qwen3.7-plus", "output": [item],
                    "usage": {"input_tokens": 50, "cached_input_tokens": 40,
                              "output_tokens": 20, "reasoning_output_tokens": 5,
                              "total_tokens": 70}}
            self._sse([("response.created", {"type": "response.created", "response": resp}),
                       ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": item}),
                       ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
                       ("response.completed", {"type": "response.completed", "response": resp})])
            return
        cid = "call_" + uuid.uuid4().hex[:12]
        item = {"id": cid, "type": "function_call", "status": "completed",
                "name": "exec_command", "arguments": json.dumps({"cmd": CMD, "workdir": "/tmp"}),
                "call_id": cid, "parallel_tool_calls": False}
        resp = {"id": rid, "object": "response", "created_at": int(time.time()),
                "status": "in_progress", "model": "qwen3.7-plus", "output": [item],
                "usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60}}
        self._sse([("response.created", {"type": "response.created", "response": resp}),
                   ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": item}),
                   ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
                   ("response.completed", {"type": "response.completed", "response": resp})])
    def do_POST(self):
        if self.path.rstrip("/").endswith("/compatible-mode/v1/responses"):
            self._responses()
        else:
            self.send_response(404); self.end_headers()
    def do_GET(self):
        self.send_response(404); self.end_headers()

if __name__ == "__main__":
    print(f"shelltest fake on {PORT} CMD={CMD!r}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
