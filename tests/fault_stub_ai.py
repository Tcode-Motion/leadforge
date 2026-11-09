"""Fault stub AI server for LeadForge fault injection tests.

Modes are read from the file named by LF_FAULT_MODE (default /tmp/lf_fault/stub_mode):
  ok       -> valid Gemini shaped JSON answer
  garbage  -> HTTP 200 with a non JSON body
  array    -> HTTP 200 with a JSON array at the root
  hang     -> sleeps far beyond the client timeout
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODE_FILE = Path(os.environ.get("LF_FAULT_MODE", "/tmp/lf_fault/stub_mode"))

TEXT = (
    "WHATSAPP_MESSAGE:\n"
    "Fault stub WhatsApp hello. I am Tanmoy from GDL Technologies, and I help local businesses with simple websites, mobile apps and software that make daily work easier for owners and customers. I saw your business details in my saved lead list and had one practical idea to discuss. Would you be open to a short call this week?\n\n"
    "EMAIL_SUBJECT: Fault stub subject line\n\n"
    "EMAIL_BODY:\n"
    "Hello, this fault stub email body was written for testing the LeadForge writer fault paths."
)


def mode():
    try:
        return MODE_FILE.read_text().strip()
    except OSError:
        return "ok"


class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)
        m = mode()
        if m == "hang":
            time.sleep(20)
            self._send(json.dumps({"candidates": [{"content": {"parts": [{"text": TEXT}]}}]}))
            return
        if m == "garbage":
            self._send("this is not json at all {{{", "text/plain")
            return
        if m == "array":
            self._send(json.dumps(["just", "an", "array"]))
            return
        self._send(json.dumps({"candidates": [{"content": {"parts": [{"text": TEXT}]}}]}))

    def do_GET(self):
        self._send(json.dumps({"models": [{"name": "qwen2.5:3b"}]}))


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8981), H).serve_forever()
