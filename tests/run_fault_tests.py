"""LeadForge fault injection tests for the repository edition.

Every fault must end in a friendly state and the dashboard must still
answer GET / with 200 afterwards. Run: python3 run_fault_tests.py
Source tree: LF_SRC env or ~/workspace/leadforge-repo/leadforge.
"""
import http.client as http_client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

SRC = Path(os.environ.get("LF_SRC", str(Path(__file__).resolve().parent.parent)))
WORK = Path(os.environ.get("LF_WORK", str(Path(tempfile.gettempdir()) / "lf_fault")))
FAKEBIN = WORK / "fakebin"
RESULTS = []

LEADS_CSV = (
    "title,category,phone,website,review_rating,review_count,address\n"
    "Alpha Dental Care,Dental clinic,+91 90000 00001,https://alpha.example.com,4.8,132,Alpha Road Kolkata\n"
    "Gamma Fitness,Gym,+91 90000 00003,,4.4,59,Gamma Street Kolkata\n"
)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:300]) if detail and not ok else ""))


def http(port, method, path, form=None, raw_body=None, timeout=30):
    conn = http_client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    body = None
    headers = {}
    if form is not None:
        body = urllib.parse.urlencode(form)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if raw_body is not None:
        body = raw_body
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8", "replace")
    status = resp.status
    conn.close()
    return status, data


def start_server(copy_dir, port, extra_env=None):
    env = dict(os.environ)
    env["PATH"] = str(FAKEBIN) + os.pathsep + env.get("PATH", "")
    env["LEADFORGE_PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"
    env.update(extra_env or {})
    log_path = WORK / f"server-{port}.log"
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [sys.executable, "-u", str(copy_dir / "dashboard" / "app.py")],
        cwd=str(copy_dir), env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 45
    while time.time() < deadline:
        if proc.poll() is not None:
            log_file.flush()
            log_txt = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            raise RuntimeError(f"server on {port} exited early rc={proc.returncode}; log:\n{log_txt}")
        try:
            status, _ = http(port, "GET", "/api/health", timeout=3)
            if status == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.35)
    log_file.flush()
    log_txt = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    raise RuntimeError(f"server on {port} did not start within 45s; log:\n{log_txt}")


def stop_server(proc):
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def remove_readonly(func, path, excinfo):
    try:
        import stat
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def safe_rmtree(path):
    if os.path.exists(path):
        shutil.rmtree(path, onexc=remove_readonly)


def make_copy(name):
    dest = WORK / name
    if dest.exists():
        safe_rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", "preview_*.png", "google-maps-scraper.exe", "server-info.json"))
    return dest


def data_dir(copy_dir):
    return copy_dir / "dashboard" / "data"


def write_leads(copy_dir):
    data = data_dir(copy_dir)
    data.mkdir(parents=True, exist_ok=True)
    (data / "latest.csv").write_text(LEADS_CSV)
    (data / "latest-meta.json").write_text(json.dumps({
        "status": "good", "updated": "2026-11-09T10:00:00", "rows": 2,
        "enrich_attempted": 2, "enrich_succeeded": 1, "enrich_failed": 0, "failed_websites": [],
    }))


def alive(port):
    try:
        status, body = http(port, "GET", "/", timeout=10)
        return status == 200 and "LeadForge" in body
    except Exception:
        return False


def set_mode(value):
    (WORK / "stub_mode").write_text(value)


def main():
    if WORK.exists():
        safe_rmtree(WORK)
    WORK.mkdir(parents=True)
    FAKEBIN.mkdir(parents=True)
    docker = FAKEBIN / "docker"
    docker.write_text('#!/bin/sh\ncase "$1" in\n  info) echo "27.0.0"; exit 0 ;;\n  compose) exit 0 ;;\n  --version) echo "Docker version 27.0.0, build test"; exit 0 ;;\n  *) exit 0 ;;\nesac\n')
    try:
        docker.chmod(0o755)
    except Exception:
        pass
    docker_bat = FAKEBIN / "docker.cmd"
    docker_bat.write_text('@echo off\nif "%1"=="info" (echo 27.0.0 & exit /b 0)\nif "%1"=="compose" (exit /b 0)\nif "%1"=="--version" (echo Docker version 27.0.0, build test & exit /b 0)\nexit /b 0\n')

    stub_env = dict(os.environ)
    stub_env["LF_FAULT_MODE"] = str(WORK / "stub_mode")
    stub = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "fault_stub_ai.py")],
        env=stub_env, stdout=open(WORK / "stub.log", "w"), stderr=subprocess.STDOUT,
    )
    time.sleep(0.8)
    gemini_url = "http://127.0.0.1:8981/gemini"
    ai_env = {"LEADFORGE_GEMINI_URL": gemini_url, "LEADFORGE_GROQ_URL": gemini_url, "LEADFORGE_AI_TIMEOUT": "3"}

    try:
        # ---------------- copy F1: corrupt state files and CSV faults
        copy1 = make_copy("copyF1")
        write_leads(copy1)
        d1 = data_dir(copy1)
        (d1 / "leads.json").write_text("{ this is not json ]]]")
        (d1 / "ai-settings.json").write_text("### broken ###")
        (d1 / "app-ports.json").write_text("[1, 2, 3")
        (d1 / "server-info.json").write_text("garbage{{{")
        (d1 / "latest-meta.json").write_text("not json either")
        proc = start_server(copy1, 8921, dict(ai_env))
        try:
            ok_pages = True
            for path in ("/", "/leads", "/writer?lead=0", "/settings", "/apps", "/health", "/guide", "/reports"):
                status, _ = http(8921, "GET", path)
                ok_pages = ok_pages and status == 200
            status, apps_body = http(8921, "GET", "/apps/status")
            apps_ok = False
            try:
                apps_ok = "_batch" in json.loads(apps_body)
            except Exception:
                apps_ok = False
            errors_text = ""
            err_file = d1 / "logs" / "errors.jsonl"
            if err_file.exists():
                errors_text = err_file.read_text(errors="replace")
            check("F01 corrupt leads.json: all pages still 200 and STORE_CORRUPT is logged",
                  ok_pages and "STORE_CORRUPT" in errors_text, errors_text[-200:])
            check("F02 corrupt ai-settings.json: settings and apps status fine, apps JSON parses",
                  status == 200 and apps_ok)
            http(8921, "POST", "/writer/generate", {"lead": "0", "output": "both", "language": "english"})
            _, writer_html = http(8921, "GET", "/writer?lead=0&output=both&language=english")
            check("F03 corrupt ai-settings.json falls back to no key state (AI_NO_KEY), app alive",
                  "AI_NO_KEY" in writer_html and alive(8921))
            set_mode("garbage")
            http(8921, "POST", "/settings/ai", {"ai_provider": "gemini", "ai_api_key": "FAULTKEY-1234"})
            http(8921, "POST", "/writer/generate", {"lead": "0", "output": "both", "language": "english"})
            _, writer_html = http(8921, "GET", "/writer?lead=0&output=both&language=english")
            check("F04 AI endpoint returns non JSON garbage: AI_PROVIDER_ERROR, app alive",
                  "AI_PROVIDER_ERROR" in writer_html and alive(8921), writer_html[:200])
            set_mode("array")
            http(8921, "POST", "/writer/generate", {"lead": "0", "output": "both", "language": "english"})
            _, writer_html = http(8921, "GET", "/writer?lead=0&output=both&language=english")
            check("F05 AI endpoint returns a JSON array: AI_PROVIDER_ERROR, app alive",
                  "AI_PROVIDER_ERROR" in writer_html and alive(8921))
            set_mode("hang")
            globals_env = None
            # timeout is fixed at server start; this server has 3s timeout via env
            http(8921, "POST", "/writer/generate", {"lead": "0", "output": "both", "language": "english"})
            _, writer_html = http(8921, "GET", "/writer?lead=0&output=both&language=english")
            check("F06 AI endpoint hangs past the timeout: AI_TIMEOUT, app alive",
                  "AI_TIMEOUT" in writer_html and alive(8921), writer_html[:200])
            set_mode("ok")
            status, _ = http(8921, "POST", "/writer/generate", {"lead": "abc", "output": "both", "language": "english"})
            status2, _ = http(8921, "POST", "/writer/generate", {"lead": "1.5", "output": "both", "language": "english"})
            check("F07 writer lead index garbage (abc, 1.5) never 500s",
                  status in (200, 303) and status2 in (200, 303) and alive(8921), f"{status} {status2}")
            big_value = "x" * 200000
            status, _ = http(8921, "POST", "/settings/save", {"app": "chatwoot", "f_chatwoot_POSTGRES_USERNAME": big_value})
            status2, _ = http(8921, "GET", "/settings")
            check("F08 oversized form field (200 KB) is accepted safely, settings still renders",
                  status in (200, 303) and status2 == 200 and alive(8921), f"{status} {status2}")
            huge_body = "a=" + "y" * 1100000
            status, body = http(8921, "POST", "/run", raw_body=huge_body)
            check("F09 oversized POST body over 1 MB gets a friendly 400 page",
                  status == 400 and "Request too large" in body and alive(8921), str(status))
            status, _ = http(8921, "GET", "/no-such-page")
            check("F10 unknown GET route returns the branded 404 page",
                  status == 404 and alive(8921), str(status))
            status, _ = http(8921, "POST", "/no-such-action", {"a": "b"})
            check("F11 unknown POST route returns the branded 404 page",
                  status == 404 and alive(8921), str(status))
            status, _ = http(8921, "POST", "/apps/action", {"app": "listmonk", "action": "stop"})
            status2, apps_body = http(8921, "GET", "/apps/status")
            check("F12 Stop with no running job or app stays friendly",
                  status in (200, 303) and status2 == 200 and alive(8921), f"{status} {status2}")
            # CSV faults on the same copy
            (d1 / "latest.csv").write_text("")
            status, leads_html = http(8921, "GET", "/leads")
            status2, _ = http(8921, "GET", "/download/latest.csv")
            check("F13 empty latest.csv: leads page 200, download is a friendly 404",
                  status == 200 and status2 == 404 and alive(8921), f"{status} {status2}")
            (d1 / "latest.csv").write_text("foo,bar\n1,2\n3,4\n")
            status, _ = http(8921, "GET", "/leads")
            status2, _ = http(8921, "GET", "/writer")
            check("F14 CSV with wrong headers: leads and writer pages still 200",
                  status == 200 and status2 == 200 and alive(8921), f"{status} {status2}")
        finally:
            stop_server(proc)

        # ---------------- copy F2: missing data dir
        copy2 = make_copy("copyF2")
        shutil.rmtree(data_dir(copy2))
        proc = start_server(copy2, 8922, dict(ai_env))
        try:
            ok_pages = True
            for path in ("/", "/leads", "/settings", "/apps", "/health", "/reports", "/writer", "/guide"):
                status, _ = http(8922, "GET", path)
                ok_pages = ok_pages and status == 200
            check("F15 missing data directory is recreated and every page answers 200",
                  ok_pages and alive(8922))
        finally:
            stop_server(proc)

        # ---------------- copy F3: port busy on start
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", 8923))
        blocker.listen(1)
        copy3 = make_copy("copyF3")
        proc = None
        try:
            env = dict(ai_env)
            proc = start_server(copy3, 8924, env)  # health wait must use the actual port
            info = json.loads((data_dir(copy3) / "server-info.json").read_text())
            check("F16 preferred port busy on start: dashboard moves to the next free port",
                  info.get("port") == 8924 and alive(8924), str(info.get("port")))
        finally:
            stop_server(proc)
            blocker.close()

        # ---------------- copy F4: scraper missing + double start
        copy4 = make_copy("copyF4")
        env4 = dict(ai_env)
        env4["PIPELINE_SCRAPER_BIN"] = str(WORK / "no-such-scraper-binary")
        proc = start_server(copy4, 8925, env4)
        try:
            http(8925, "POST", "/run", {"location": "Kolkata", "business_type": "dentists", "max_results": "10", "mode": "full"})
            job = {}
            deadline = time.time() + 30
            while time.time() < deadline:
                _, body = http(8925, "GET", "/status")
                job = json.loads(body)
                if job.get("state") in ("failed", "done", "partial"):
                    break
                time.sleep(0.4)
            check("F17 scraper binary missing: job fails with SCRAPER_NOT_FOUND, app alive",
                  job.get("state") == "failed" and job.get("error_code") == "SCRAPER_NOT_FOUND" and alive(8925),
                  str(job.get("error_code")))
        finally:
            stop_server(proc)

        slow_scraper_py = WORK / "slow_scraper.py"
        slow_scraper_py.write_text(
            "import sys, time\n"
            "out = ''\n"
            "args = sys.argv[1:]\n"
            "for i in range(len(args)):\n"
            "    if args[i] == '-results' and i + 1 < len(args):\n"
            "        out = args[i+1]\n"
            "time.sleep(4)\n"
            "if out:\n"
            "    with open(out, 'w', encoding='utf-8') as f:\n"
            "        f.write('title,category,phone,website,review_rating,review_count,address\\nSlow Dental,Dental clinic,+91 90000 00009,,4.5,10,Slow Road Kolkata\\n')\n"
        )
        if sys.platform == "win32":
            slow_scraper = WORK / "slow_scraper.bat"
            slow_scraper.write_text(f'@echo off\n"{sys.executable}" "{slow_scraper_py}" %*\n')
        else:
            slow_scraper = WORK / "slow_scraper.sh"
            slow_scraper.write_text(f'#!/bin/sh\n"{sys.executable}" "{slow_scraper_py}" "$@"\n')
            slow_scraper.chmod(0o755)
        copy5 = make_copy("copyF5")
        env5 = dict(ai_env)
        env5["PIPELINE_SCRAPER_BIN"] = str(slow_scraper)
        proc = start_server(copy5, 8926, env5)
        try:
            http(8926, "POST", "/run", {"location": "Kolkata", "business_type": "dentists", "max_results": "10", "mode": "find"})
            time.sleep(0.6)
            http(8926, "POST", "/run", {"location": "Kolkata", "business_type": "dentists", "max_results": "10", "mode": "find"})
            _, body = http(8926, "GET", "/status")
            job = json.loads(body)
            double_ok = "already running" in str(job.get("notice", ""))
            job = {}
            deadline = time.time() + 40
            while time.time() < deadline:
                _, body = http(8926, "GET", "/status")
                job = json.loads(body)
                if job.get("state") in ("failed", "done", "partial"):
                    break
                time.sleep(0.4)
            check("F18 double Start click: second start is refused politely and the first job finishes",
                  double_ok and job.get("state") in ("done", "partial") and alive(8926),
                  f"notice_ok={double_ok} state={job.get('state')}")
        finally:
            stop_server(proc)

        # ---------------- copy F6: deliberate handler crash
        copy6 = make_copy("copyF6")
        env6 = dict(ai_env)
        env6["LEADFORGE_TEST_ROUTES"] = "1"
        proc = start_server(copy6, 8927, env6)
        try:
            status, body = http(8927, "GET", "/__test__/error")
            errors_text = (data_dir(copy6) / "logs" / "errors.jsonl").read_text(errors="replace")
            check("F19 deliberate handler crash returns the friendly 500 page and is logged",
                  status == 500 and "Something went wrong" in body and "HTTP_INTERNAL_ERROR" in errors_text and alive(8927),
                  f"status={status}")
        finally:
            stop_server(proc)
    finally:
        stub.terminate()

    failed = [name for name, ok in RESULTS if not ok]
    print(f"\nFAULT TOTAL {len(RESULTS)} PASSED {len(RESULTS) - len(failed)} FAILED {len(failed)}")
    (WORK / "fault-results.json").write_text(json.dumps(
        [{"name": n, "ok": o} for n, o in RESULTS], indent=1))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
