import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODE_FILE = Path("/tmp/lf_tests/stub_mode")
COUNT_FILE = Path("/tmp/lf_tests/stub_count")

GEMINI_TEXT = (
    "WHATSAPP_MESSAGE:\n"
    "Gemini stub WhatsApp hello. I am Tanmoy from GDL Technologies, and I help local businesses with simple websites, mobile apps and software that make daily work easier for owners and customers. I saw your business details in my saved lead list and had one practical idea to discuss. Would you be open to a short call this week?\n\n"
    "EMAIL_SUBJECT: Gemini stub subject line\n\n"
    "EMAIL_BODY:\n"
    "Hello, this Gemini stub email body was written for testing the LeadForge writer flow end to end."
)
GROQ_TEXT = (
    "WHATSAPP_MESSAGE:\n"
    "Groq stub WhatsApp hello. I am Tanmoy from GDL Technologies, and I help local businesses with simple websites, mobile apps and software that make daily work easier for owners and customers. I saw your business details in my saved lead list and had one practical idea to discuss. Would you be open to a short call this week?\n\n"
    "EMAIL_SUBJECT: Groq stub subject line\n\n"
    "EMAIL_BODY:\n"
    "Hello, this Groq stub email body was written for testing the LeadForge writer flow end to end."
)
LOCAL_TEXT = (
    "WHATSAPP_MESSAGE:\n"
    "Local stub WhatsApp hello. I am Tanmoy from GDL Technologies, and I help local businesses with simple websites, mobile apps and software that make daily work easier for owners and customers. I saw your business details in my saved lead list and had one practical idea to discuss. Would you be open to a short call this week?\n\n"
    "EMAIL_SUBJECT: Local stub subject line\n\n"
    "EMAIL_BODY:\n"
    "Hello, this local stub email body was written for testing the LeadForge Ollama flow end to end."
)
BAD_TEXT = (
    "WHATSAPP_MESSAGE:\n"
    "Hello [Name], I promise guaranteed results for your business and a number one service that will change everything for your team, your customers, your bookings, your calls, your sales, your daily work, and your future growth starting this week with one short friendly call together.\n\n"
    "EMAIL_SUBJECT: Bad stub subject line\n\n"
    "EMAIL_BODY:\n"
    "Hello, this bad stub email body contains problems that the LeadForge checker should catch and fix on one retry."
)
FIXED_TEXT = (
    "WHATSAPP_MESSAGE:\n"
    "Corrected stub WhatsApp hello. I am Tanmoy from GDL Technologies, and I help local businesses with simple websites, mobile apps and software that make daily work easier for owners and customers. I saw your business details in my saved lead list and had one practical idea to discuss. Would you be open to a short call this week?\n\n"
    "EMAIL_SUBJECT: Corrected stub subject line\n\n"
    "EMAIL_BODY:\n"
    "Hello, this corrected stub email body was written after the LeadForge checker asked for one correction retry."
)


def mode():
    try:
        return MODE_FILE.read_text().strip() or "ok"
    except OSError:
        return "ok"


STYLE_BAD = 'WHATSAPP_MESSAGE:\nI hope this message finds you well — we help local shops grow fast every single day now. We can boost your business with a modern new website for you today. We will take your business to the next level very soon for sure. Our team builds websites and apps for many shops like yours daily. Please reply here so we can talk more about this plan together.\nEMAIL_SUBJECT:\nGrow your shop with a new website today\nEMAIL_BODY:\nI hope this message finds you well — we help esteemed local shops grow fast every single day now. We can boost your business with a modern new website for you today. We will take your business to the next level very soon for sure. Our team builds websites and apps for many shops like yours daily. Please reply here so we can talk more about this plan together. We are ready when you are ready to begin this work.\n'

STYLE_CLEAN = 'WHATSAPP_MESSAGE:\nHi, I am Tanmoy from GDL Technologies. I found Alpha Dental Care while looking at dental clinics in Kolkata this morning. Quick question: do you take bookings on WhatsApp, or only by phone right now? A small website could show your timings clearly and let people book in two taps. I can show you a sample first, no pressure at all. Want me to send it over?\nEMAIL_SUBJECT:\nA booking idea for Alpha Dental Care\nEMAIL_BODY:\nHello, I am Tanmoy from GDL Technologies here in Kolkata. I came across Alpha Dental Care while checking dental clinics nearby, and your 4.8 rating stood out. Most patients just want timings and a fast way to book before they call. A simple website can do that job without any big cost or monthly headache for you. I have one small idea sketched already. If you like, reply and I will send it across today.\n'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _pull(self):
        pull_mode = Path("/tmp/lf_tests/pull_mode").read_text().strip() if Path("/tmp/lf_tests/pull_mode").exists() else "pullok"
        plines = ['{"status":"pulling manifest"}', '{"status":"downloading","completed":50,"total":100}']
        if pull_mode == "pullfail":
            plines.append('{"error":"stub pull failed halfway"}')
        else:
            plines += ['{"status":"downloading","completed":100,"total":100}', '{"status":"verifying sha digest"}', '{"status":"success"}']
        body = ("\n".join(plines) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith("/api/tags") and mode() != "tagsfail":
            payload = {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:3b"}, {"name": "qwen2.5:7b"}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/v1/models"):
            payload = {"data": [{"id": "qwen2.5:3b"}, {"id": "llama3.2:3b"}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/pull":
            self._pull()
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw_body = self.rfile.read(length) if length else b""
        try:
            with open("/tmp/lf_tests/requests.log", "a", encoding="utf-8") as fh:
                fh.write(self.path + "\t" + raw_body.decode("utf-8", "replace") + "\n---END---\n")
        except OSError:
            pass
        current_mode = mode()
        if current_mode == "slow":
            time.sleep(6)
        if current_mode == "fail401":
            echoed = self.headers.get("x-goog-api-key") or ""
            auth = self.headers.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                echoed = auth[7:]
            body = json.dumps({"error": {"message": f"invalid api key {echoed} was rejected"}}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if current_mode == "fail429":
            body = json.dumps({"error": {"message": "quota exceeded for this key"}}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if current_mode == "fail404" and self.path.startswith("/v1/"):
            body = json.dumps({"error": {"message": "model not found"}}).encode()
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if current_mode == "stylebad" and ("/chat/completions" in self.path or self.path.startswith("/gemini")):
            style_count_file = Path("/tmp/lf_tests/stub_style_count")
            try:
                style_count = int(style_count_file.read_text().strip() or "0")
            except (OSError, ValueError):
                style_count = 0
            style_count += 1
            style_count_file.write_text(str(style_count))
            chosen = STYLE_BAD if style_count == 1 else STYLE_CLEAN
            if self.path.startswith("/gemini"):
                payload = {"candidates": [{"content": {"parts": [{"text": chosen}]}}]}
            else:
                payload = {"choices": [{"message": {"content": chosen}}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if current_mode == "batchfail":
            try:
                count = int(COUNT_FILE.read_text().strip() or "0")
            except (OSError, ValueError):
                count = 0
            count += 1
            COUNT_FILE.write_text(str(count))
            if count in (2, 3):
                body = json.dumps({"error": {"message": "stub failure for the middle lead"}}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        if current_mode == "badthenfixed":
            bad_count_file = Path("/tmp/lf_tests/stub_bad_count")
            try:
                bad_count = int(bad_count_file.read_text().strip() or "0")
            except (OSError, ValueError):
                bad_count = 0
            bad_count += 1
            bad_count_file.write_text(str(bad_count))
            chosen = BAD_TEXT if bad_count == 1 else FIXED_TEXT
            if self.path.startswith("/gemini"):
                payload = {"candidates": [{"content": {"parts": [{"text": chosen}]}}]}
            else:
                payload = {"choices": [{"message": {"content": chosen}}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/gemini"):
            payload = {"candidates": [{"content": {"parts": [{"text": GEMINI_TEXT}]}}]}
        elif self.path.startswith("/v1/"):
            payload = {"choices": [{"message": {"content": LOCAL_TEXT}}]}
        else:
            payload = {"choices": [{"message": {"content": GROQ_TEXT}}]}
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8977), Handler).serve_forever()
