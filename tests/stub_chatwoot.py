import json
from http.server import BaseHTTPRequestHandler, HTTPServer

CONVS = {
    "data": {
        "payload": [
            {
                "id": 1,
                "meta": {"sender": {"phone_number": "+919000000001", "name": "Alpha Dental Care"}},
                "messages": [{"message_type": 0, "content": "I am interested, please call me"}],
                "updated_at": "2026-11-08T10:00:00",
            },
            {
                "id": 2,
                "meta": {"sender": {"phone_number": "+919999999999", "name": "Unknown Person"}},
                "messages": [{"message_type": 0, "content": "Who is this?"}],
                "updated_at": "2026-11-08T10:05:00",
            },
        ]
    }
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        token = self.headers.get("api_access_token") or ""
        if token == "bad-token":
            body = json.dumps({"error": "unauthorized"}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if "/conversations" in self.path:
            body = json.dumps(CONVS).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8979), Handler).serve_forever()
