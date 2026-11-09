"""LeadForge Automated HTTP Endpoint & Routing Integration Test Suite.
Validates all routes, status payloads, JSON endpoints, and error handlers.
"""

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_endpoints():
    test_port = find_free_port()
    print(f"Starting LeadForge test instance on port {test_port}...")

    env = os.environ.copy()
    env["LEADFORGE_PORT"] = str(test_port)
    env["LEADFORGE_MANAGED_LAUNCH"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-u", str(SRC / "dashboard" / "app.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Wait for server to bind
    ready = False
    start_time = time.time()
    while time.time() - start_time < 15:
        try:
            with socket.create_connection(("127.0.0.1", test_port), timeout=1):
                ready = True
                break
        except OSError:
            time.sleep(0.3)

    if not ready:
        proc.kill()
        out, _ = proc.communicate(timeout=5)
        print(f"Server output:\n{out}")
        raise RuntimeError(f"Server failed to start on port {test_port} within 15s")

    print(f"[OK] Server bound to port {test_port} successfully.")

    routes_to_test = [
        ("/", 200, "text/html"),
        ("/leads", 200, "text/html"),
        ("/whatsapp-bot", 200, "text/html"),
        ("/whatsapp/status", 200, "application/json"),
        ("/apps", 200, "text/html"),
        ("/setup", 200, "text/html"),
        ("/settings", 200, "text/html"),
        ("/guide", 200, "text/html"),
        ("/reports", 200, "text/html"),
        ("/health", 200, "text/html"),
        ("/troubleshooting", 200, "text/html"),
        ("/api/health", 200, "application/json"),
        ("/api/errors", 200, "application/json"),
        ("/apps/status", 200, "application/json"),
        ("/logo.svg", 200, "image/svg+xml"),
        ("/non-existent-route", 404, "text/html"),
    ]

    passed = 0
    failed = 0

    conn = http.client.HTTPConnection("127.0.0.1", test_port, timeout=10)
    for path, expected_status, content_type in routes_to_test:
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read()

            status_ok = resp.status == expected_status
            ctype = resp.getheader("Content-Type", "")
            type_ok = content_type in ctype

            if status_ok and type_ok:
                passed += 1
                print(f"  PASS: GET {path:<20} -> {resp.status} ({ctype.split(';')[0]})")
            else:
                failed += 1
                print(f"  FAIL: GET {path:<20} -> got {resp.status} (expected {expected_status}), ctype={ctype}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL: GET {path} error: {exc}")

    # Test POST /troubleshooting/clear-errors
    try:
        conn.request("POST", "/troubleshooting/clear-errors", headers={"X-Requested-With": "XMLHttpRequest"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        if resp.status == 200 and data.get("ok"):
            passed += 1
            print("  PASS: POST /troubleshooting/clear-errors -> 200 JSON OK")
        else:
            failed += 1
            print(f"  FAIL: POST /troubleshooting/clear-errors -> status {resp.status}, body {body}")
    except Exception as exc:
        failed += 1
        print(f"  FAIL: POST /troubleshooting/clear-errors error: {exc}")

    conn.close()

    # Clean shutdown
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    print(f"\nEndpoint test results: {passed} PASSED, {failed} FAILED")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    test_endpoints()
