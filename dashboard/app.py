"""LeadForge dashboard.

LeadForge is the one local web page for the whole client pipeline pack:
- Run page: type a location and a business type, click Run, and the
  google-maps-scraper finds leads, then crawl4ai reads their websites.
- Leads page: the latest lead list, with a CSV download.
- Apps page: start and stop the five server tools (listmonk, chatwoot,
  cal.diy, twenty, documenso) and open each one.

Standard library only. The dashboard chooses a free local port at startup.
"""

import atexit
import csv
import html
import json
import math
import os
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.error
import urllib.request
import uuid

APP_DIR = Path(__file__).resolve().parent
PACK_DIR = APP_DIR.parent
DATA_DIR = APP_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
NOTES_DIR = DATA_DIR / "notes"
LOG_DIR = DATA_DIR / "logs"
RUNTIME_DIR = DATA_DIR / "runtime"
LATEST_CSV = DATA_DIR / "latest.csv"
LATEST_META = DATA_DIR / "latest-meta.json"
SERVER_INFO_FILE = DATA_DIR / "server-info.json"
APP_PORTS_FILE = DATA_DIR / "app-ports.json"
ERRORS_FILE = LOG_DIR / "errors.jsonl"
MAIN_LOG_FILE = LOG_DIR / "leadforge.log"
ENRICH_SCRIPT = APP_DIR / "enrich.py"
AI_SETTINGS_FILE = DATA_DIR / "ai-settings.json"
PITCHES_DIR = DATA_DIR / "pitches"
LEADS_STORE_FILE = DATA_DIR / "leads.json"
REPORTS_DIR = DATA_DIR / "reports"
CHATWOOT_SYNC_FILE = DATA_DIR / "chatwoot-sync.json"
LEAD_OUTCOMES = ["New", "Pitched", "Replied", "Call booked", "Not interested", "No reply"]
QUALIFICATION_LABELS = {
    "no_website_confirmed": "No website confirmed",
    "has_website": "Has website",
    "website_dead": "Website dead",
    "unknown": "Unknown",
}
REGION_PACK = [
    ("West Bengal", ["west bengal", "kolkata", "halishahar", "howrah", "durgapur", "siliguri", "asansol"], "bangla", "Bangla or Bengali friendly English works well here."),
    ("Delhi", ["delhi", "new delhi", "noida", "gurgaon", "gurugram", "ghaziabad"], "english", "Hinglish friendly English works well here."),
    ("Maharashtra", ["maharashtra", "mumbai", "pune", "nagpur", "nashik", "thane"], "english", "Hinglish or Marathi friendly English works well here."),
    ("Tamil Nadu", ["tamil nadu", "chennai", "coimbatore", "madurai", "salem", "trichy", "tiruchirappalli"], "english", "English works well here, with a Tamil greeting as an option."),
    ("Karnataka", ["karnataka", "bengaluru", "bangalore", "mysuru", "mysore", "hubli", "mangaluru"], "english", "English works well here."),
    ("Uttar Pradesh", ["uttar pradesh", "lucknow", "kanpur", "agra", "varanasi", "prayagraj", "meerut"], "english", "Hinglish friendly English works well here."),
    ("Gujarat", ["gujarat", "ahmedabad", "surat", "vadodara", "rajkot", "gandhinagar"], "english", "English or Gujarati friendly English works well here."),
    ("Kerala", ["kerala", "kochi", "thiruvananthapuram", "kozhikode", "thrissur"], "english", "English works well here."),
]
AI_PROVIDER_INFO = {
    "gemini": {
        "label": "Google Gemini free tier",
        "default_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "url_env": "LEADFORGE_GEMINI_URL",
        "key_url": "https://aistudio.google.com/apikey",
    },
    "groq": {
        "label": "Groq free tier",
        "default_url": "https://api.groq.com/openai/v1/chat/completions",
        "url_env": "LEADFORGE_GROQ_URL",
        "key_url": "https://console.groq.com/keys",
    },
    "local": {
        "label": "Local AI (Ollama or compatible) - no key, no limit",
        "default_url": "http://127.0.0.1:11434/v1/chat/completions",
        "url_env": "LEADFORGE_OLLAMA_URL",
        "key_url": "https://ollama.com/download",
        "default_base_url": "http://127.0.0.1:11434",
        "default_model": "qwen2.5:3b",
    },
}
OLLAMA_STATUS_CACHE = {"at": 0, "data": None}
OLLAMA_CHECK_TIMEOUT_SECONDS = 2.5
DEFAULT_PITCH_RULES = """Who is sending: Tanmoy from GDL Technologies.
What GDL Technologies does: builds mobile apps, websites and software for businesses.
Offer: a useful website, mobile app or software idea for this business, explained in simple words.
Call to action: one soft call to action only. Ask for a reply or a short call. No pressure.
Tone: human, simple, friendly and direct. Write like a real person, not like an advertisement.
Hard rules: use only the facts in the lead data and the website note. Never invent ratings, prices, clients, results or problems. Do not make claims that cannot be proved. Do not say a business has no website if a website is listed.
Length: keep the WhatsApp message at about 60 to 90 words. The email needs a clear subject and a body of about 120 to 160 words.
Language: write in the language selected in LeadForge. When Bangla is selected, use proper Bangla script.
Format: follow the exact output markers in the instruction. Do not add extra headings or explanations."""
try:
    AI_TIMEOUT_SECONDS = int(os.environ.get("LEADFORGE_AI_TIMEOUT", "30"))
except ValueError:
    AI_TIMEOUT_SECONDS = 30
AI_TIMEOUT_SECONDS = max(1, min(60, AI_TIMEOUT_SECONDS))
try:
    AI_BATCH_PAUSE_SECONDS = int(os.environ.get("LEADFORGE_AI_BATCH_PAUSE_MS", "600")) / 1000.0
except ValueError:
    AI_BATCH_PAUSE_SECONDS = 0.6
AI_BATCH_PAUSE_SECONDS = max(0.0, min(5.0, AI_BATCH_PAUSE_SECONDS))

HOST = "127.0.0.1"
DEFAULT_PORT = 8790
PORT_SCAN_END = 8899
try:
    PREFERRED_PORT = int(os.environ.get("LEADFORGE_PORT", str(DEFAULT_PORT)))
    if not (1024 <= PREFERRED_PORT <= 65535):
        PREFERRED_PORT = DEFAULT_PORT
except ValueError:
    PREFERRED_PORT = DEFAULT_PORT
PORT = PREFERRED_PORT
SERVER_STATE = {
    "host": HOST,
    "port": PREFERRED_PORT,
    "url": f"http://{HOST}:{PREFERRED_PORT}",
    "pid": os.getpid(),
    "started_at": "",
    "token": os.environ.get("LEADFORGE_LAUNCH_TOKEN") or uuid.uuid4().hex,
    "preferred_port": PREFERRED_PORT,
}
MAX_LOG_BYTES = 1_000_000

# The scraper program. On Tanmoy's PC this is the Windows exe in folder 1.
# PIPELINE_SCRAPER_BIN can point somewhere else (used for dev testing).
SCRAPER_BIN = os.environ.get(
    "PIPELINE_SCRAPER_BIN",
    str(PACK_DIR / "1-find-google-maps-scraper" / "google-maps-scraper.exe"),
)
# The python that has crawl4ai installed (folder 2 venv).
# PIPELINE_CRAWL_PYTHON can override it (used for dev testing).
CRAWL_PYTHON = os.environ.get(
    "PIPELINE_CRAWL_PYTHON",
    str(PACK_DIR / "2-understand-crawl4ai" / "venv" / "Scripts" / "python.exe"),
)

# The five server tools, in pipeline order. Ports match the pack compose files.
APPS = [
    {
        "id": "listmonk",
        "name": "listmonk",
        "desc": "Email campaigns: sends your outreach emails to the lead list.",
        "folder": "3-message-listmonk",
        "url": "http://localhost:9000",
        "compose": "docker-compose.yml",
        "web_service": "app",
        "web_container_port": 9000,
        "preferred_port": 9000,
        "requires_env": False,
        "dependent_ports": [
            {"key": "database", "label": "Postgres database", "service": "db", "container_port": 5432, "preferred_port": 5432},
        ],
    },
    {
        "id": "chatwoot",
        "name": "chatwoot",
        "desc": "One inbox for WhatsApp, email and website chat replies.",
        "folder": "4-inbox-chatwoot",
        "url": "http://localhost:3001",
        "compose": "docker-compose.yaml",
        "web_service": "rails",
        "web_container_port": 3000,
        "preferred_port": 3001,
        "requires_env": True,
        "dependent_ports": [
            {"key": "database", "label": "Postgres database", "service": "postgres", "container_port": 5432, "preferred_port": 5432},
            {"key": "cache", "label": "Redis cache", "service": "redis", "container_port": 6379, "preferred_port": 6379},
        ],
    },
    {
        "id": "caldiy",
        "name": "cal.diy",
        "desc": "Your booking page: leads pick a time, the call lands on your calendar.",
        "folder": "5-book-caldiy",
        "url": "http://localhost:3002",
        "compose": "docker-compose.yml",
        "web_service": "calcom",
        "web_container_port": 3000,
        "preferred_port": 3002,
        "requires_env": True,
        "dependent_ports": [
            {"key": "cache", "label": "Redis cache", "service": "redis", "container_port": 6379, "preferred_port": 6379},
            {"key": "api", "label": "API service", "service": "calcom-api", "container_port": 80, "preferred_port": 8080},
            {"key": "studio", "label": "Prisma Studio", "service": "studio", "container_port": 5555, "preferred_port": 5555},
        ],
    },
    {
        "id": "twenty",
        "name": "twenty (CRM)",
        "desc": "The CRM that tracks every lead, reply, call and deal.",
        "folder": "6-track-twenty",
        "url": "http://localhost:3003",
        "compose": "docker-compose.yml",
        "web_service": "server",
        "web_container_port": 3000,
        "preferred_port": 3003,
        "requires_env": True,
        "dependent_ports": [],
    },
    {
        "id": "documenso",
        "name": "documenso",
        "desc": "Proposals and agreements that clients sign online.",
        "folder": "7-close-documenso",
        "url": "http://localhost:3004",
        "compose": "docker-compose.yml",
        "web_service": "documenso",
        "web_container_port": 3000,
        "preferred_port": 3004,
        "requires_env": True,
        "dependent_ports": [],
    },
]
APPS_BY_ID = {a["id"]: a for a in APPS}

JOB_LOCK = threading.Lock()
JOB = {
    "state": "idle",  # idle, running, done, partial, failed
    "step": "",
    "log": [],
    "error": "",
    "error_code": "",
    "notice": "",
    "location": "",
    "business_type": "",
    "max_results": 30,
    "leads": 0,
    "run_dir": "",
    "result_kind": "",
    "enrich_attempted": 0,
    "enrich_succeeded": 0,
    "enrich_failed": 0,
    "enrich_skipped": 0,
    "failed_websites": [],
    "started_at": "",
}

APP_LOCK = threading.Lock()
APP_STATE = {
    a["id"]: {
        "running": False,  # an action is currently working
        "busy": False,
        "status": "not_started",
        "last_result": "",
        "output": "",
        "message": "",
        "fix": "",
        "started_by_leadforge": False,
        "started_at": "",
    }
    for a in APPS
}
BATCH_STATE = {"running": False, "summary": "", "output": "", "results": {}}
APP_PORT_DATA = {"version": 1, "updated": "", "apps": {}}
SETTINGS_STATE = {"apps": {}, "ai": {}}
WRITER_STATE = {"notice": "", "error": "", "error_code": "", "last": None}
WRITER_JOB_LOCK = threading.Lock()
WRITER_JOB = {
    "state": "idle",
    "running": False,
    "total": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "current": "",
    "message": "",
    "errors": [],
    "output": "",
    "language": "english",
    "started_at": "",
    "finished_at": "",
}
LOG_LOCK = threading.Lock()
DOCKER_CACHE = {"at": 0.0, "status": "unknown", "detail": ""}


# ---------------------------------------------------------------- reliability core

def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_storage():
    for folder in (DATA_DIR, RUNS_DIR, NOTES_DIR, LOG_DIR, RUNTIME_DIR, PITCHES_DIR, REPORTS_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def _rotate_if_needed(path):
    try:
        if path.exists() and path.stat().st_size >= MAX_LOG_BYTES:
            rotated = path.with_name(path.name + ".1")
            if rotated.exists():
                rotated.unlink()
            path.replace(rotated)
    except OSError:
        pass


def record_event(level, area, code, message, detail="", fix=""):
    """Write one structured event. Errors also go to errors.jsonl."""
    try:
        ensure_storage()
        event = {
            "time": now_iso(),
            "level": level,
            "area": area,
            "code": code,
            "message": str(message),
            "detail": str(detail or "")[-4000:],
            "fix": str(fix or ""),
        }
        line = json.dumps(event, ensure_ascii=False)
        with LOG_LOCK:
            _rotate_if_needed(MAIN_LOG_FILE)
            with open(MAIN_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if level in ("error", "warning"):
                _rotate_if_needed(ERRORS_FILE)
                with open(ERRORS_FILE, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        return event
    except Exception:
        # Logging must never take the dashboard down.
        return None


def log_error(area, code, message, detail="", fix=""):
    return record_event("error", area, code, message, detail, fix)


def log_warning(area, code, message, detail="", fix=""):
    return record_event("warning", area, code, message, detail, fix)


def recent_errors(limit=12):
    if not ERRORS_FILE.exists():
        return []
    events = []
    try:
        lines = ERRORS_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-300:]:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    events.append(item)
            except Exception:
                continue
    except OSError:
        return []
    return list(reversed(events[-limit:]))


def clear_error_log():
    ensure_storage()
    with LOG_LOCK:
        ERRORS_FILE.write_text("", encoding="utf-8")
    record_event("info", "system", "ERROR_LOG_CLEARED", "The recent error display was cleared.")


def read_json_file(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def atomic_write_json(path, data):
    ensure_storage()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def default_app_port_entry(app):
    ports = {
        "web": {
            "label": app["name"] + " web page",
            "service": app["web_service"],
            "container_port": int(app["web_container_port"]),
            "preferred_port": int(app["preferred_port"]),
            "actual_port": int(app["preferred_port"]),
            "switched": False,
        }
    }
    for dep in app.get("dependent_ports", []):
        ports[dep["key"]] = {
            "label": dep["label"],
            "service": dep["service"],
            "container_port": int(dep["container_port"]),
            "preferred_port": int(dep["preferred_port"]),
            "actual_port": int(dep["preferred_port"]),
            "switched": False,
        }
    return {
        "preferred_port": int(app["preferred_port"]),
        "actual_port": int(app["preferred_port"]),
        "url": app["url"],
        "switched": False,
        "ports": ports,
        "started_by_leadforge": False,
        "started_at": "",
        "status": "not_started",
        "last_message": "",
        "runtime_file": "",
    }


def load_app_ports():
    global APP_PORT_DATA
    stored = read_json_file(APP_PORTS_FILE, {"version": 1, "apps": {}})
    apps = stored.get("apps", {}) if isinstance(stored, dict) else {}
    merged = {"version": 1, "updated": stored.get("updated", "") if isinstance(stored, dict) else "", "apps": {}}
    for app in APPS:
        entry = default_app_port_entry(app)
        old = apps.get(app["id"], {}) if isinstance(apps, dict) else {}
        if isinstance(old, dict):
            for key in ("actual_port", "url", "switched", "started_by_leadforge", "started_at", "status", "last_message", "runtime_file"):
                if key in old:
                    entry[key] = old[key]
            old_ports = old.get("ports", {})
            if isinstance(old_ports, dict):
                for key, old_port in old_ports.items():
                    if key in entry["ports"] and isinstance(old_port, dict):
                        for field in ("actual_port", "switched"):
                            if field in old_port:
                                entry["ports"][key][field] = old_port[field]
        try:
            entry["actual_port"] = int(entry["actual_port"])
        except Exception:
            entry["actual_port"] = int(app["preferred_port"])
        entry["url"] = f"http://localhost:{entry['actual_port']}"
        if "web" in entry["ports"]:
            entry["ports"]["web"]["actual_port"] = entry["actual_port"]
            entry["ports"]["web"]["switched"] = bool(entry.get("switched"))
        merged["apps"][app["id"]] = entry
        with APP_LOCK:
            APP_STATE[app["id"]]["started_by_leadforge"] = bool(entry.get("started_by_leadforge"))
            APP_STATE[app["id"]]["started_at"] = entry.get("started_at", "")
            APP_STATE[app["id"]]["status"] = entry.get("status", "not_started")
            APP_STATE[app["id"]]["message"] = entry.get("last_message", "")
    APP_PORT_DATA = merged
    return APP_PORT_DATA


def ensure_app_ports_loaded():
    if not APP_PORT_DATA.get("apps"):
        load_app_ports()


def save_app_ports():
    APP_PORT_DATA["updated"] = now_iso()
    atomic_write_json(APP_PORTS_FILE, APP_PORT_DATA)


def app_assignment(app_id):
    if app_id not in APP_PORT_DATA.get("apps", {}):
        load_app_ports()
    return APP_PORT_DATA["apps"][app_id]


def is_port_listening(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex((HOST, int(port))) == 0
    except OSError:
        return False


def is_port_free(port):
    port = int(port)
    if port < 1 or port > 65535 or is_port_listening(port):
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            sock.bind((HOST, port))
            sock.listen(1)
        return True
    except OSError:
        return False


def find_available_port(preferred, reserved=None, span=1000):
    reserved = {int(x) for x in (reserved or set())}
    start = max(1, int(preferred))
    end = min(65535, start + int(span))
    for port in range(start, end + 1):
        if port not in reserved and is_port_free(port):
            return port
    return None


def port_state(port):
    if is_port_listening(port):
        return "listening"
    if is_port_free(port):
        return "free"
    return "busy"


def write_server_info():
    SERVER_STATE["started_at"] = SERVER_STATE.get("started_at") or now_iso()
    data = {
        "app": "LeadForge",
        "host": SERVER_STATE["host"],
        "port": SERVER_STATE["port"],
        "url": SERVER_STATE["url"],
        "pid": int(SERVER_STATE.get("pid") or os.getpid()),
        "started_at": SERVER_STATE["started_at"],
        "launch_token": SERVER_STATE["token"],
        "preferred_port": SERVER_STATE["preferred_port"],
    }
    atomic_write_json(SERVER_INFO_FILE, data)
    return data


def remove_server_info_if_mine():
    data = read_json_file(SERVER_INFO_FILE, {})
    if data.get("launch_token") == SERVER_STATE.get("token") and int(data.get("pid") or 0) == os.getpid():
        try:
            SERVER_INFO_FILE.unlink()
        except OSError:
            pass


def probe_existing_server():
    """Return health data from an already running LeadForge, if one answers."""
    candidates = []
    info = read_json_file(SERVER_INFO_FILE, {})
    if info.get("port"):
        candidates.append(info["port"])
    for port in range(PREFERRED_PORT, PORT_SCAN_END + 1):
        if port not in candidates:
            candidates.append(port)
    for port in candidates:
        try:
            req = urllib.request.Request(f"http://{HOST}:{int(port)}/api/health", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=0.6) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            if not isinstance(data, dict):
                continue
            server = data.get("server", {}) if isinstance(data.get("server"), dict) else {}
            if data.get("app") == "LeadForge" and server.get("token"):
                return data
        except Exception:
            continue
    return None


def docker_status(force=False):
    current = time.time()
    if not force and current - DOCKER_CACHE.get("at", 0) < 5 and DOCKER_CACHE.get("status") != "unknown":
        return DOCKER_CACHE["status"], DOCKER_CACHE.get("detail", "")
    exe = shutil.which("docker")
    if exe is None:
        result = ("missing", "Docker was not found on this computer.")
    else:
        try:
            proc = subprocess.run(
                [exe, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=6, errors="replace",
            )
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            if proc.returncode == 0:
                version = (proc.stdout or "").strip()
                result = ("ready", f"Docker is running. Server version: {version}" if version else "Docker is running.")
            elif "cannot connect" in combined.lower() or "docker daemon" in combined.lower() or "is the docker daemon running" in combined.lower():
                result = ("stopped", combined[-1200:] or "Docker Desktop is not running.")
            else:
                result = ("stopped", combined[-1200:] or f"Docker info stopped with code {proc.returncode}.")
        except subprocess.TimeoutExpired:
            result = ("stopped", "Docker did not answer within 6 seconds.")
        except Exception as exc:
            result = ("stopped", str(exc))
    DOCKER_CACHE.update({"at": current, "status": result[0], "detail": result[1]})
    return result


def docker_fix(status):
    if status == "missing":
        return "Install Docker Desktop, start it, then try again. The dashboard and lead finder still work without Docker."
    if status == "stopped":
        return "Start Docker Desktop and wait until it says it is running, then try again."
    return ""


def crawl_setup_state():
    python_path = Path(CRAWL_PYTHON)
    return {
        "python": CRAWL_PYTHON,
        "python_found": python_path.exists(),
        "script_found": ENRICH_SCRIPT.exists(),
        "ready": python_path.exists() and ENRICH_SCRIPT.exists(),
    }


def scraper_state():
    path = Path(SCRAPER_BIN)
    executable = path.exists() and (os.name == "nt" or os.access(path, os.X_OK))
    return {"path": SCRAPER_BIN, "found": path.exists(), "executable": executable, "ready": path.exists() and executable}


def job_log(line):
    with JOB_LOCK:
        JOB["log"].append(str(line))
        if len(JOB["log"]) > 400:
            JOB["log"] = JOB["log"][-400:]


def job_set(**kw):
    with JOB_LOCK:
        JOB.update(kw)


def host_of(url):
    host = re.sub(r"^https?://", "", (url or "").strip()).split("/")[0]
    return re.sub(r"[^a-zA-Z0-9.-]", "_", host)


def note_exists(website):
    host = host_of(website)
    if not host or not NOTES_DIR.exists():
        return False
    return any(host in p.name for p in NOTES_DIR.glob("*.md"))


# ---------------------------------------------------------------- pipeline

def _stream_process(cmd, cwd=None, kill_after=900):
    """Run a command and stream output to the job log.

    Returns (returncode, output_lines, timed_out). A timeout is reported as
    data instead of leaving the dashboard hanging forever.
    """
    lines = []
    timed_out = {"value": False}

    def kill_process():
        timed_out["value"] = True
        try:
            proc.kill()
        except Exception:
            pass

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        errors="replace",
    )
    timer = threading.Timer(float(kill_after), kill_process)
    timer.start()
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                line = line.rstrip("\n")
                lines.append(line)
                if line.strip():
                    job_log(line)
        proc.wait()
    finally:
        timer.cancel()
    return proc.returncode, lines, bool(timed_out["value"])


def _pick_error(lines, fallback):
    for line in reversed(lines):
        if re.search(r"(error|failed|panic|exception|ERR_)", line, re.IGNORECASE):
            if line.strip():
                return line.strip()
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return fallback


def _parse_results_strict(csv_path):
    """Parse a results CSV and distinguish valid, empty and malformed files."""
    csv_path = Path(csv_path)
    result = {"status": "missing", "fieldnames": [], "rows": [], "error": ""}
    if not csv_path.exists():
        result["error"] = f"Results file was not created: {csv_path}"
        return result
    try:
        raw = csv_path.read_bytes()
    except OSError as exc:
        result.update({"status": "malformed", "error": f"Results file could not be read: {exc}"})
        return result
    if len(raw) == 0:
        result.update({"status": "empty", "error": "Results file is empty."})
        return result
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        result.update({"status": "malformed", "error": f"Results file is not valid UTF-8 text: {exc}"})
        return result
    if "\x00" in text:
        result.update({"status": "malformed", "error": "Results file contains binary NUL characters."})
        return result
    try:
        import io
        reader = csv.DictReader(io.StringIO(text), strict=True)
        fieldnames = reader.fieldnames or []
        clean_fields = [(fn or "").strip() for fn in fieldnames]
        if not clean_fields or not any(clean_fields):
            result.update({"status": "malformed", "error": "Results CSV has no header row."})
            return result
        if len(clean_fields) != len(set(clean_fields)):
            result.update({"status": "malformed", "error": "Results CSV has duplicate column names."})
            return result
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                result.update({"status": "malformed", "error": "Results CSV has a row with the wrong number of fields."})
                return result
            if any((value or "").strip() for value in row.values()):
                rows.append(row)
    except csv.Error as exc:
        result.update({"status": "malformed", "error": f"Results CSV could not be parsed: {exc}"})
        return result
    known = {"title", "name", "business_name", "business", "phone", "phone_number", "telephone", "mobile", "website", "site", "url", "web", "review_rating", "rating", "ratings", "score", "review_count", "reviews", "reviews_count", "number_of_reviews", "address", "full_address", "location"}
    if not ({fn.lower().strip() for fn in fieldnames} & known):
        result.update({"status": "malformed", "error": "Results CSV does not contain recognisable lead columns."})
        return result
    result.update({"status": "valid", "fieldnames": fieldnames, "rows": rows})
    return result


def _read_results(csv_path):
    """Tolerant reader used by display code. Invalid data becomes no rows."""
    parsed = _parse_results_strict(csv_path)
    if parsed["status"] != "valid":
        return [], []
    return parsed["fieldnames"], parsed["rows"]


def latest_data_state():
    parsed = _parse_results_strict(LATEST_CSV)
    meta = read_json_file(LATEST_META, {})
    state = {
        "status": parsed["status"],
        "available": parsed["status"] == "valid" and len(parsed["rows"]) > 0,
        "rows": len(parsed["rows"]) if parsed["status"] == "valid" else 0,
        "error": parsed["error"],
        "meta": meta,
    }
    if parsed["status"] == "valid" and parsed["rows"]:
        state["showing"] = "last_good"
    elif meta.get("last_result") == "zero":
        state["showing"] = "last_good" if state["available"] else "none"
    elif parsed["status"] == "malformed":
        state["showing"] = "none"
    else:
        state["showing"] = "none"
    return state


def _save_latest_results(results_csv, run_dir, leads):
    tmp = LATEST_CSV.with_name("latest.csv.tmp")
    shutil.copyfile(results_csv, tmp)
    tmp.replace(LATEST_CSV)
    atomic_write_json(LATEST_META, {
        "status": "good",
        "last_result": "success",
        "updated": now_iso(),
        "rows": int(leads),
        "source_run": str(run_dir),
    })


def _record_zero_result(run_dir):
    old = read_json_file(LATEST_META, {})
    old.update({
        "last_result": "zero",
        "last_zero_at": now_iso(),
        "last_zero_run": str(run_dir),
    })
    atomic_write_json(LATEST_META, old)


def _column_map(fieldnames):
    lower = {fn.lower().strip(): fn for fn in fieldnames if fn}
    def find(keys):
        for k in keys:
            if k in lower:
                return lower[k]
        return None
    return {
        "website": find(["website", "site", "url", "web"]),
    }


def run_pipeline(location, business_type, max_results, mode="full"):
    try:
        _run_pipeline_inner(location, business_type, max_results, mode)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        log_error("pipeline", "PIPELINE_INTERNAL_ERROR", "The pipeline stopped because of an internal dashboard problem.", detail, "Open Health and send the LeadForge error log to Muse if this repeats.")
        job_set(state="failed", step="Failed", error="The pipeline stopped because of an internal dashboard problem. The detail is in the error log.", error_code="PIPELINE_INTERNAL_ERROR")
        job_log(f"Dashboard error: {detail}")


def _run_pipeline_inner(location, business_type, max_results, mode="full"):
    try:
        _execute_pipeline(location, business_type, max_results, mode)
    finally:
        with JOB_LOCK:
            run_dir = JOB.get("run_dir", "")
            lines = list(JOB.get("log", []))
        if run_dir:
            try:
                ensure_storage()
                Path(run_dir).mkdir(parents=True, exist_ok=True)
                (Path(run_dir) / "job.log").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            except OSError:
                pass


def _execute_pipeline(location, business_type, max_results, mode="full"):
    ensure_storage()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / stamp
    suffix = 2
    while run_dir.exists():
        run_dir = RUNS_DIR / f"{stamp}-{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True, exist_ok=True)
    job_set(run_dir=str(run_dir), mode=mode)

    query = f"{business_type} in {location}"
    queries_file = run_dir / "queries.txt"
    queries_file.write_text(query + "\n", encoding="utf-8")
    results_csv = run_dir / "results.csv"

    job_set(step="Finding leads")
    if mode == "full":
        job_log("Stage 1 Find: searching for leads.")
    job_log(f"Search: {query}")
    depth = max(1, math.ceil(max_results / 10))
    job_log(f"Max results requested: {max_results} (scraper scroll depth {depth})")

    scraper = scraper_state()
    if not scraper["found"]:
        message = "The scraper program was not found."
        log_error("pipeline", "SCRAPER_NOT_FOUND", message, scraper["path"], "Check that folder 1 still contains google-maps-scraper.exe, or reinstall the pack.")
        job_set(state="failed", step="Failed", error=f"{message} Expected file: {scraper['path']}", error_code="SCRAPER_NOT_FOUND")
        job_log(message)
        return
    if not scraper["executable"]:
        message = "The scraper program is present but cannot be executed."
        log_error("pipeline", "SCRAPER_NOT_EXECUTABLE", message, scraper["path"], "Check the file permissions and antivirus quarantine, then try again.")
        job_set(state="failed", step="Failed", error=message, error_code="SCRAPER_NOT_EXECUTABLE")
        job_log(message)
        return

    cmd = [
        SCRAPER_BIN,
        "-input", str(queries_file),
        "-results", str(results_csv),
        "-exit-on-inactivity", "3m",
        "-depth", str(depth),
    ]
    try:
        scraper_timeout = int(os.environ.get("LEADFORGE_SCRAPER_TIMEOUT", "900"))
    except ValueError:
        scraper_timeout = 900
    scraper_timeout = max(10, min(3600, scraper_timeout))
    job_log("Starting the scraper. The first run can take a few minutes.")
    try:
        code, lines, timed_out = _stream_process(cmd, cwd=run_dir, kill_after=scraper_timeout)
    except OSError as exc:
        message = "The scraper could not be started."
        log_error("pipeline", "SCRAPER_START_FAILED", message, str(exc), "Check the scraper file and Windows security prompts, then try again.")
        job_set(state="failed", step="Failed", error=message, error_code="SCRAPER_START_FAILED")
        job_log(message)
        return

    parsed = _parse_results_strict(results_csv)
    partial_reason = ""
    if timed_out:
        message = f"The scraper timed out after {scraper_timeout} seconds."
        log_error("pipeline", "SCRAPER_TIMEOUT", message, "\n".join(lines[-30:]), "Try a smaller search, check the internet connection, then run again.")
        if parsed["status"] != "valid" or not parsed["rows"]:
            job_set(state="failed", step="Failed", error=message, error_code="SCRAPER_TIMEOUT", leads=0)
            job_log(message)
            return
        partial_reason = message + " Partial results were saved."
        job_log(partial_reason)

    if parsed["status"] in ("missing", "empty"):
        code_reason = _pick_error(lines, f"Scraper stopped with code {code}.") if code != 0 else parsed["error"]
        if code != 0:
            message = "The scraper failed and did not produce a usable results file."
            error_code = "SCRAPER_FAILED"
            fix = "Check the internet connection and the run log, then try again."
        else:
            message = "The scraper finished without a usable results file."
            error_code = "SCRAPER_OUTPUT_MISSING"
            fix = "Check the run log in this run folder and try the search again."
        log_error("pipeline", error_code, message, code_reason, fix)
        job_set(state="failed", step="Failed", error=f"{message} {code_reason}", error_code=error_code, leads=0)
        job_log(message)
        return
    if parsed["status"] == "malformed":
        message = "The scraper results file was malformed, so the last good lead list was kept."
        log_error("pipeline", "SCRAPER_CSV_MALFORMED", message, parsed["error"], "Try the search again. If it repeats, send the error log and this run folder details to Muse.")
        job_set(state="failed", step="Failed", error=f"{message} Detail: {parsed['error']}", error_code="SCRAPER_CSV_MALFORMED", leads=0)
        job_log(message)
        return

    fieldnames, rows = parsed["fieldnames"], parsed["rows"]
    leads = len(rows)
    if code != 0 and leads == 0:
        err = _pick_error(lines, f"Scraper stopped with code {code} and found no leads.")
        log_error("pipeline", "SCRAPER_FAILED", "The scraper failed and returned no leads.", err, "Check the internet connection and the run log, then try again.")
        job_set(state="failed", step="Failed", error=err, error_code="SCRAPER_FAILED", leads=0)
        job_log(f"Scraper stopped with code {code} and found no leads.")
        return
    if code != 0 and leads > 0:
        reason = f"Scraper stopped with code {code}, but {leads} valid leads were recovered."
        partial_reason = (partial_reason + " " + reason).strip()
        log_warning("pipeline", "SCRAPER_PARTIAL_OUTPUT", reason, _pick_error(lines, ""), "Review the recovered leads before using them.")

    if leads == 0:
        _record_zero_result(run_dir)
        job_set(
            state="partial" if partial_reason else "done",
            step="Done, no results" if not partial_reason else "Partially done",
            leads=0,
            result_kind="zero",
            error=partial_reason,
            error_code="PARTIAL_RESULT" if partial_reason else "",
        )
        job_log("The search completed successfully, but it returned 0 leads. This is a zero result, not a crash.")
        job_log("The previous good lead list was not overwritten.")
        return

    _save_latest_results(results_csv, run_dir, leads)
    job_set(leads=leads, result_kind="success")
    job_log(f"Found {leads} leads. Saved to the Leads page.")

    job_set(step="Reading lead websites")
    if mode == "full":
        job_log("Stage 2 Read websites: reading lead websites for notes.")
    colmap = _column_map(fieldnames)
    websites = []
    if colmap["website"]:
        seen = set()
        for r in rows:
            w = (r.get(colmap["website"]) or "").strip()
            if w and w not in seen:
                seen.add(w)
                websites.append(w)
            if len(websites) >= 15:
                break
    if not websites:
        job_log("No websites in these results, so the website reading step is skipped.")
        if mode == "full":
            _run_full_pipeline_tail(partial_reason, 0, 0, 0, [])
            return
        job_set(
            state="partial" if partial_reason else "done",
            step="Partially done" if partial_reason else "Done",
            error=partial_reason,
            error_code="PARTIAL_RESULT" if partial_reason else "",
            enrich_attempted=0, enrich_succeeded=0, enrich_failed=0, enrich_skipped=0,
        )
        return

    websites_csv = run_dir / "websites.csv"
    with open(websites_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["website"])
        for w in websites:
            writer.writerow([w])

    crawl = crawl_setup_state()
    if not crawl["ready"]:
        message = "Website reading is not set up yet, so notes were skipped. The leads are saved."
        log_warning("pipeline", "CRAWL_NOT_SETUP", message, f"Python: {crawl['python']} found={crawl['python_found']}; script found={crawl['script_found']}", "Run 2-understand-crawl4ai/setup_crawl4ai.bat once, then run the pipeline again for notes.")
        job_log(message)
        job_log("Run 2-understand-crawl4ai/setup_crawl4ai.bat once, then run the pipeline again to add website notes.")
        if mode == "full":
            _run_full_pipeline_tail((partial_reason + " " + message).strip(), 0, 0, 0, [])
            return
        job_set(
            state="partial", step="Partially done", error=message, error_code="CRAWL_NOT_SETUP",
            enrich_attempted=0, enrich_succeeded=0, enrich_failed=0, enrich_skipped=len(websites),
        )
        return

    job_log(f"Reading {len(websites)} lead websites to write pitch notes.")
    cmd = [CRAWL_PYTHON, str(ENRICH_SCRIPT), str(websites_csv), str(NOTES_DIR)]
    enrich_timeout = max(60, min(900, len(websites) * 60))
    try:
        code, lines, timed_out = _stream_process(cmd, cwd=run_dir, kill_after=enrich_timeout)
    except OSError as exc:
        code, lines, timed_out = 1, [str(exc)], False

    attempted = len(websites)
    succeeded = None
    failed = None
    failed_urls = []
    for line in lines:
        if line.startswith("ENRICH_SUMMARY"):
            values = dict(part.split("=", 1) for part in line.split() if "=" in part)
            try:
                attempted = int(values.get("attempted", attempted))
                succeeded = int(values.get("succeeded", 0))
                failed = int(values.get("failed", 0))
            except ValueError:
                pass
        elif line.startswith("ENRICH_FAILED"):
            parts = line.split(maxsplit=2)
            if len(parts) >= 2:
                failed_urls.append(parts[1])
    if succeeded is None:
        succeeded = sum(1 for w in websites if note_exists(w))
        failed = max(0, attempted - succeeded)
    _meta_old = read_json_file(LATEST_META, {})
    _meta_old.update({
        "enrich_attempted": int(attempted or 0),
        "enrich_succeeded": int(succeeded or 0),
        "enrich_failed": int(failed or 0),
        "failed_websites": list(failed_urls),
    })
    atomic_write_json(LATEST_META, _meta_old)
    if timed_out:
        failed = max(1, attempted - int(succeeded or 0))
        message = f"Website reading timed out after {enrich_timeout} seconds. Finished notes were kept."
        log_error("pipeline", "CRAWL_TIMEOUT", message, "\n".join(lines[-30:]), "Run again later, or reduce the number of results.")
        partial_reason = (partial_reason + " " + message).strip()
    elif failed:
        message = f"Website reading finished with {failed} failed website(s) out of {attempted}. Successful notes were kept."
        log_warning("pipeline", "CRAWL_PARTIAL_FAILURE", message, "\n".join(failed_urls), "Open the failed websites by hand if those leads matter.")
        partial_reason = (partial_reason + " " + message).strip()
    elif code != 0:
        message = "Website reading stopped before it could confirm any notes."
        log_error("pipeline", "CRAWL_FAILED", message, _pick_error(lines, f"Code {code}"), "Check the crawl4ai setup and internet connection, then run again.")
        failed = attempted
        succeeded = 0
        partial_reason = (partial_reason + " " + message).strip()
    else:
        job_log("Website notes are saved. Open the Leads page to see which leads have notes.")

    job_set(
        state="partial" if partial_reason else "done",
        step="Partially done" if partial_reason else "Done",
        error=partial_reason,
        error_code="PARTIAL_RESULT" if partial_reason else "",
        enrich_attempted=attempted,
        enrich_succeeded=int(succeeded or 0),
        enrich_failed=int(failed or 0),
        enrich_skipped=0,
        failed_websites=failed_urls,
    )
    if mode == "full":
        _run_full_pipeline_tail(partial_reason, attempted, int(succeeded or 0), int(failed or 0), failed_urls)
        return


def _run_full_pipeline_tail(partial_reason, enrich_attempted, enrich_succeeded, enrich_failed, failed_urls):
    job_set(
        step="Qualifying leads",
        enrich_attempted=enrich_attempted,
        enrich_succeeded=int(enrich_succeeded or 0),
        enrich_failed=int(enrich_failed or 0),
        enrich_skipped=0,
        failed_websites=list(failed_urls or []),
    )
    job_log("Stage 3 Qualify: checking which leads have no website, a dead website, a working website, or not enough data.")
    selected, counts = select_batch_leads(False)
    job_log(
        f"Stage 3 Qualify: {counts['no_website_confirmed']} no website confirmed, {counts['website_dead']} website dead, "
        f"{counts['has_website']} has website, {counts['unknown']} unknown."
    )
    job_set(step="Writing pitches")
    job_log("Stage 4 Write pitches: writing for qualified leads only (no website confirmed, plus dead websites). The style check runs inside the writer.")
    result_counts = write_pitches_for_leads(selected, "both", "auto", job_log)
    job_log(
        f"Stage 4 Write pitches: {result_counts['succeeded']} ready, {result_counts['failed']} failed, "
        f"{result_counts['manual']} marked for manual mode."
    )
    job_set(step="Checking and reporting")
    job_log("Stage 5 Check and report: building the report from the lead store.")
    report_path = generate_report()
    job_log(f"Stage 5 Check and report: report saved as {report_path.name}. Open the Reports page to read it.")
    problems = []
    if partial_reason:
        problems.append(partial_reason)
    if result_counts["failed"]:
        problems.append(f"{result_counts['failed']} pitch(es) could not be written and were marked for manual mode.")
    total_leads = len(lead_records())
    qualified = counts["no_website_confirmed"] + counts["website_dead"]
    summary = (
        f"Full pipeline finished. Found {total_leads} leads. Qualified {qualified}. "
        f"Pitched {result_counts['succeeded']}. Failed {result_counts['failed']}."
    )
    job_log(summary)
    job_set(
        state="partial" if problems else "done",
        step="Partially done" if problems else "Done",
        error=" ".join(problems),
        error_code="PARTIAL_RESULT" if problems else "",
        leads=total_leads,
        result_kind="success",
    )


# ---------------------------------------------------------------- docker apps

RUNTIME_COMPOSE_NAME = "docker-compose.leadforge.yml"


def _replace_first(text, old, new, label):
    if old not in text:
        raise ValueError(f"Could not find the expected Compose setting for {label}.")
    return text.replace(old, new, 1)


def runtime_env_for_app(app, url):
    env = dict(os.environ)
    if app["id"] == "twenty":
        env["SERVER_URL"] = url
    elif app["id"] == "documenso":
        env["NEXT_PUBLIC_WEBAPP_URL"] = url
    elif app["id"] == "caldiy":
        env["API_PORT"] = "80"
    return env


def generate_runtime_compose(app, entry):
    folder = PACK_DIR / app["folder"]
    source = folder / app["compose"]
    if not source.exists():
        raise FileNotFoundError(f"Compose file not found: {source}")
    text = source.read_text(encoding="utf-8", errors="replace")
    ports = entry["ports"]
    web = int(ports["web"]["actual_port"])

    if app["id"] == "listmonk":
        text = _replace_first(text, '"9000:9000"', f'"{web}:9000"', "listmonk web port")
        db = int(ports["database"]["actual_port"])
        text = _replace_first(text, '"127.0.0.1:5432:5432"', f'"127.0.0.1:{db}:5432"', "listmonk database port")
    elif app["id"] == "chatwoot":
        text = _replace_first(text, "'127.0.0.1:3001:3000'", f"'127.0.0.1:{web}:3000'", "chatwoot web port")
        db = int(ports["database"]["actual_port"])
        cache = int(ports["cache"]["actual_port"])
        text = _replace_first(text, "'127.0.0.1:5432:5432'", f"'127.0.0.1:{db}:5432'", "chatwoot database port")
        text = _replace_first(text, "'127.0.0.1:6379:6379'", f"'127.0.0.1:{cache}:6379'", "chatwoot Redis port")
        old_env = "    environment:\n      - NODE_ENV=production\n      - RAILS_ENV=production\n"
        new_env = old_env + f"      - FRONTEND_URL=http://localhost:{web}\n"
        text = _replace_first(text, old_env, new_env, "chatwoot frontend URL")
    elif app["id"] == "caldiy":
        cache = int(ports["cache"]["actual_port"])
        api = int(ports["api"]["actual_port"])
        studio = int(ports["studio"]["actual_port"])
        text = _replace_first(text, '"127.0.0.1:${REDIS_PORT:-6379}:6379"', f'"127.0.0.1:{cache}:6379"', "cal.diy Redis port")
        text = _replace_first(text, "- 3002:3000", f"- {web}:3000", "cal.diy web port")
        text = _replace_first(text, '"${API_PORT:-80}:${API_PORT:-80}"', f'"{api}:80"', "cal.diy API port")
        text = _replace_first(text, '"127.0.0.1:5555:5555"', f'"127.0.0.1:{studio}:5555"', "cal.diy Studio port")
        old_env = "    env_file: .env\n    environment:\n"
        new_env = old_env + f"      - NEXT_PUBLIC_WEBAPP_URL=http://localhost:{web}\n      - NEXTAUTH_URL=http://localhost:{web}\n"
        text = _replace_first(text, old_env, new_env, "cal.diy web URL")
    elif app["id"] == "twenty":
        text = _replace_first(text, '"3003:3000"', f'"{web}:3000"', "twenty web port")
    elif app["id"] == "documenso":
        text = _replace_first(text, "3004:${PORT:-3000}", f"{web}:${{PORT:-3000}}", "documenso web port")
    else:
        raise ValueError(f"No runtime Compose builder exists for {app['id']}.")

    target = folder / RUNTIME_COMPOSE_NAME
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target


def app_setup_problem(app):
    if not app.get("requires_env"):
        return None
    folder = PACK_DIR / app["folder"]
    if (folder / ".env").exists():
        return None
    return {
        "message": f"{app['name']} needs its .env setup file before Docker can start it.",
        "fix": f"In {app['folder']}, copy .env.example to .env and fill in the required values from that folder's HOW_TO.md. LeadForge did not invent any secret values.",
    }


def _reserved_ports(except_app_id=None):
    reserved = {int(SERVER_STATE.get("port", PREFERRED_PORT))}
    for app_id, entry in APP_PORT_DATA.get("apps", {}).items():
        if app_id == except_app_id or not entry.get("started_by_leadforge"):
            continue
        for info in entry.get("ports", {}).values():
            try:
                reserved.add(int(info["actual_port"]))
            except Exception:
                pass
    return reserved


def allocate_app_ports(app, entry):
    import copy
    entry = copy.deepcopy(entry)
    ports = entry["ports"]
    if entry.get("started_by_leadforge") and is_port_listening(int(entry.get("actual_port", 0))):
        return entry
    reserved = _reserved_ports(except_app_id=app["id"])
    selected = set()
    ordered_keys = ["web"] + [key for key in ports.keys() if key != "web"]
    for key in ordered_keys:
        info = ports[key]
        preferred = int(info["preferred_port"])
        previous = int(info.get("actual_port", preferred))
        chosen = None
        for candidate in (preferred, previous):
            if candidate not in reserved and candidate not in selected and is_port_free(candidate):
                chosen = candidate
                break
        if chosen is None:
            chosen = find_available_port(preferred + 1, reserved | selected, span=1200)
        if chosen is None:
            raise RuntimeError(f"No free port was found for {info['label']} near {preferred}. Close a program using a nearby port, then try again.")
        info["actual_port"] = int(chosen)
        info["switched"] = int(chosen) != preferred
        selected.add(int(chosen))
    entry["actual_port"] = int(ports["web"]["actual_port"])
    entry["switched"] = bool(ports["web"]["switched"])
    entry["url"] = f"http://localhost:{entry['actual_port']}"
    return entry


def _app_set_state(app_id, **values):
    with APP_LOCK:
        APP_STATE[app_id].update(values)


def _compose_command(app, runtime_file, args, env, timeout):
    exe = shutil.which("docker")
    if exe is None:
        raise FileNotFoundError("Docker was not found on this computer.")
    cmd = [exe, "compose", "-f", runtime_file.name] + args
    return subprocess.run(
        cmd,
        cwd=str(PACK_DIR / app["folder"]),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
    )


def _emit_app(app_id, out, text):
    out.append(str(text))
    _app_set_state(app_id, output="\n".join(out[-160:]))


def _do_app_action(app, action):
    app_id = app["id"]
    folder = PACK_DIR / app["folder"]
    with APP_LOCK:
        if APP_STATE[app_id].get("busy"):
            return False
        APP_STATE[app_id].update({"busy": True, "running": True, "status": "working", "output": ""})
    out = []
    success = False
    try:
        entry = app_assignment(app_id)
        verb = "Starting" if action == "start" else "Stopping"
        _emit_app(app_id, out, f"{verb} {app['name']} in folder {app['folder']} ...")
        if not folder.exists():
            message = f"The app folder was not found: {folder}"
            log_error("apps", "APP_FOLDER_MISSING", message, app["folder"], "Reinstall the LeadForge pack or restore the missing folder.")
            _emit_app(app_id, out, message)
            _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Restore the missing app folder.")
            entry.update({"status": "start_failed", "last_message": message})
            save_app_ports()
            return False

        if action == "start":
            problem = app_setup_problem(app)
            if problem:
                log_error("apps", "APP_SETUP_NEEDED", problem["message"], app["folder"], problem["fix"])
                _emit_app(app_id, out, problem["message"])
                _emit_app(app_id, out, problem["fix"])
                _app_set_state(app_id, status="setup_needed", last_result="Failed", message=problem["message"], fix=problem["fix"])
                entry.update({"status": "setup_needed", "last_message": problem["message"]})
                save_app_ports()
                return False

        dstatus, ddetail = docker_status(force=True)
        if dstatus != "ready":
            code = "DOCKER_MISSING" if dstatus == "missing" else "DOCKER_STOPPED"
            message = "Docker was not found on this computer." if dstatus == "missing" else "Docker is installed, but Docker Desktop is not running or did not answer."
            fix = docker_fix(dstatus)
            log_error("apps", code, message, ddetail, fix)
            _emit_app(app_id, out, message)
            _emit_app(app_id, out, fix)
            if ddetail:
                _emit_app(app_id, out, f"Docker detail: {ddetail}")
            _app_set_state(app_id, status="docker_missing" if dstatus == "missing" else "docker_stopped", last_result="Failed", message=message, fix=fix)
            entry.update({"status": "docker_missing" if dstatus == "missing" else "docker_stopped", "last_message": message})
            save_app_ports()
            return False

        if action == "start":
            try:
                entry = allocate_app_ports(app, entry)
            except Exception as exc:
                message = str(exc)
                log_error("apps", "APP_PORT_UNAVAILABLE", message, app_id, "Close a program using the blocked port range, then try again.")
                _emit_app(app_id, out, message)
                _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Close a program using the blocked port range, then try again.")
                return False
            APP_PORT_DATA["apps"][app_id] = entry
            entry.update({"status": "starting", "last_message": "Starting with LeadForge port settings."})
            save_app_ports()
            for key, info in entry["ports"].items():
                if info.get("switched"):
                    note = f"Port switched for {info['label']}: {info['preferred_port']} was busy, using {info['actual_port']}."
                    _emit_app(app_id, out, note)
                    log_warning("apps", "APP_PORT_SWITCHED", note, app_id, "Use the Open button or the address shown on this card.")
            _emit_app(app_id, out, f"Open address for this start: {entry['url']}")

        runtime_file = folder / RUNTIME_COMPOSE_NAME
        try:
            runtime_file = generate_runtime_compose(app, entry)
            entry["runtime_file"] = runtime_file.name
            save_app_ports()
        except Exception as exc:
            message = "LeadForge could not prepare this app's safe port settings."
            log_error("apps", "APP_RUNTIME_CONFIG_FAILED", message, str(exc), "Do not edit the original Compose file by hand. Send the error log to Muse.")
            _emit_app(app_id, out, message)
            _emit_app(app_id, out, str(exc))
            _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Send the LeadForge error log to Muse.")
            entry.update({"status": "start_failed", "last_message": message})
            save_app_ports()
            return False

        env = runtime_env_for_app(app, entry["url"])
        if action == "start":
            try:
                check = _compose_command(app, runtime_file, ["config", "--quiet"], env, timeout=120)
            except subprocess.TimeoutExpired:
                check = None
                message = "Docker took too long checking this app's settings."
                log_error("apps", "APP_COMPOSE_CONFIG_TIMEOUT", message, app_id, "Wait for Docker to settle, then try again.")
                _emit_app(app_id, out, message)
                _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Wait for Docker to settle, then try again.")
                entry.update({"status": "start_failed", "last_message": message})
                save_app_ports()
                return False
            if check is None or check.returncode != 0:
                combined = "" if check is None else ((check.stdout or "") + "\n" + (check.stderr or "")).strip()
                message = "Docker rejected this app's settings before it started."
                log_error("apps", "APP_COMPOSE_CONFIG_FAILED", message, combined[-3000:], "Read the app folder HOW_TO.md, check its .env values, then try again.")
                _emit_app(app_id, out, message)
                for line in combined.splitlines()[-30:]:
                    _emit_app(app_id, out, line)
                _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Check the app .env values and HOW_TO.md, then try again.")
                entry.update({"status": "start_failed", "last_message": message})
                save_app_ports()
                return False

        args = ["up", "-d"] if action == "start" else ["down"]
        try:
            proc = _compose_command(app, runtime_file, args, env, timeout=900 if action == "start" else 300)
        except subprocess.TimeoutExpired:
            message = f"The {action} command took too long and was stopped. Docker may still be working in the background."
            log_error("apps", "APP_COMPOSE_TIMEOUT", message, app_id, "Wait a few minutes, check Docker Desktop, then try again.")
            _emit_app(app_id, out, message)
            _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Wait a few minutes, check Docker Desktop, then try again.")
            entry.update({"status": "start_failed", "last_message": message})
            save_app_ports()
            return False

        combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        for line in combined.splitlines()[-80:]:
            _emit_app(app_id, out, line)
        if proc.returncode == 0:
            success = True
            if action == "start":
                entry.update({"started_by_leadforge": True, "started_at": now_iso(), "status": "starting", "last_message": "Docker accepted the start command. The app may need time to boot."})
                _app_set_state(app_id, status="starting", last_result="OK", message="Docker accepted the start command. The app may need time to boot.", fix="", started_by_leadforge=True, started_at=entry["started_at"])
                _emit_app(app_id, out, f"{app['name']} start command finished OK. Open it at {entry['url']} after it has had time to boot.")
                record_event("info", "apps", "APP_STARTED", f"{app['name']} start command finished.", entry["url"])
            else:
                entry.update({"started_by_leadforge": False, "started_at": "", "status": "stopped", "last_message": "Stopped from LeadForge."})
                _app_set_state(app_id, status="stopped", last_result="OK", message="Stopped from LeadForge.", fix="", started_by_leadforge=False, started_at="")
                _emit_app(app_id, out, f"{app['name']} stopped.")
                record_event("info", "apps", "APP_STOPPED", f"{app['name']} stopped.", entry["url"])
            save_app_ports()
        else:
            message = f"Docker Compose could not {action} {app['name']}."
            log_error("apps", "APP_COMPOSE_FAILED", message, combined[-3000:], "Read the last lines in the app console, check Docker Desktop and the app setup, then try again.")
            _emit_app(app_id, out, message)
            _emit_app(app_id, out, "Nothing was marked as running from this failed attempt.")
            if action == "start":
                entry.update({"started_by_leadforge": False, "status": "start_failed", "last_message": message})
            else:
                entry.update({"status": "start_failed", "last_message": message})
            save_app_ports()
            _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Read the app console and Docker Desktop, then try again.")
        return success
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        message = f"LeadForge hit an internal problem while working on {app['name']}."
        log_error("apps", "APP_INTERNAL_ERROR", message, detail, "Open Health and send the error log to Muse if this repeats.")
        _emit_app(app_id, out, message)
        _app_set_state(app_id, status="start_failed", last_result="Failed", message=message, fix="Open Health and send the error log to Muse if this repeats.")
        return False
    finally:
        _app_set_state(app_id, busy=False, running=False)


def app_display_status(app):
    app_id = app["id"]
    entry = app_assignment(app_id)
    with APP_LOCK:
        state = dict(APP_STATE[app_id])
    actual = int(entry.get("actual_port", app["preferred_port"]))
    listening = is_port_listening(actual)
    if state.get("busy"):
        return {"code": "working", "label": "Working", "message": "LeadForge is working on this app.", "fix": "", "listening": listening}
    if entry.get("started_by_leadforge") and listening:
        return {"code": "running", "label": "Running", "message": "The app is listening on its LeadForge address.", "fix": "", "listening": True}
    if listening:
        return {"code": "running", "label": "Running", "message": "Something is listening on this app's address. It may have been started outside LeadForge.", "fix": "", "listening": True}
    problem = app_setup_problem(app)
    if problem:
        return {"code": "setup_needed", "label": "Setup needed", "message": problem["message"], "fix": problem["fix"], "listening": False}
    dstatus, _detail = docker_status()
    if dstatus == "missing":
        return {"code": "docker_missing", "label": "Docker missing", "message": "Docker was not found on this computer.", "fix": docker_fix(dstatus), "listening": False}
    if dstatus == "stopped":
        return {"code": "docker_stopped", "label": "Docker stopped", "message": "Docker Desktop is not running or did not answer.", "fix": docker_fix(dstatus), "listening": False}
    if entry.get("started_by_leadforge"):
        started_at = entry.get("started_at", "")
        recent = False
        try:
            recent = (datetime.now().astimezone() - datetime.fromisoformat(started_at)).total_seconds() < 180
        except Exception:
            recent = False
        if recent:
            return {"code": "starting", "label": "Starting", "message": "Docker accepted the start command, but the app is not listening yet.", "fix": "Wait a little, then use Open. If it stays here, read the app console.", "listening": False}
        return {"code": "start_failed", "label": "Not listening", "message": "LeadForge started this app before, but nothing is listening now. It may have stopped or failed while booting.", "fix": "Press Start again and read the app console if it fails.", "listening": False}
    if state.get("status") in ("start_failed", "setup_needed", "docker_missing", "docker_stopped"):
        return {"code": state["status"], "label": "Needs attention", "message": state.get("message", "The last action did not finish."), "fix": state.get("fix", ""), "listening": False}
    if state.get("status") == "stopped" or entry.get("status") == "stopped":
        return {"code": "stopped", "label": "Stopped", "message": "This app was stopped from LeadForge.", "fix": "", "listening": False}
    return {"code": "not_started", "label": "Not started", "message": "Not started from LeadForge yet.", "fix": "", "listening": False}


def apps_status_data():
    ensure_app_ports_loaded()
    data = {}
    for app in APPS:
        entry = app_assignment(app["id"])
        status = app_display_status(app)
        with APP_LOCK:
            state = dict(APP_STATE[app["id"]])
        data[app["id"]] = {
            "busy": bool(state.get("busy")),
            "running": bool(state.get("busy")) or status["code"] in ("running", "starting"),
            "status": status["code"],
            "status_label": status["label"],
            "last_result": state.get("last_result", ""),
            "output": state.get("output", ""),
            "message": status["message"],
            "fix": status["fix"] or state.get("fix", ""),
            "url": entry["url"],
            "preferred_port": int(app["preferred_port"]),
            "actual_port": int(entry["actual_port"]),
            "switched": bool(entry.get("switched")),
            "ports": entry.get("ports", {}),
            "started_by_leadforge": bool(entry.get("started_by_leadforge")),
        }
    with APP_LOCK:
        data["_batch"] = dict(BATCH_STATE)
    return data


def app_action_thread(app_id, action):
    with APP_LOCK:
        if APP_STATE[app_id].get("busy"):
            return False
    threading.Thread(target=_do_app_action, args=(APPS_BY_ID[app_id], action), daemon=True).start()
    return True


def _start_all_apps():
    with APP_LOCK:
        if BATCH_STATE.get("running"):
            return
        BATCH_STATE.update({"running": True, "summary": "Starting apps one by one...", "output": "", "results": {}})
    results = {}
    lines = []
    try:
        for app in APPS:
            ok = _do_app_action(app, "start")
            results[app["id"]] = bool(ok)
            lines.append(f"{app['name']}: {'started' if ok else 'not started'}")
            with APP_LOCK:
                BATCH_STATE.update({"results": dict(results), "output": "\n".join(lines), "summary": "Working: " + ", ".join(lines)})
        started = sum(1 for value in results.values() if value)
        summary = f"Start all finished: {started} of {len(APPS)} apps accepted a start command. Failures stayed visible on their cards."
        with APP_LOCK:
            BATCH_STATE.update({"running": False, "summary": summary, "output": "\n".join(lines), "results": dict(results)})
        record_event("info" if started else "warning", "apps", "APP_START_ALL_FINISHED", summary, "\n".join(lines))
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        log_error("apps", "APP_START_ALL_FAILED", "Start all stopped because of an internal problem.", detail, "Read each app card and the error log.")
        with APP_LOCK:
            BATCH_STATE.update({"running": False, "summary": "Start all stopped because of an internal problem. Read the app cards and Health page.", "output": "\n".join(lines), "results": dict(results)})


def start_all_thread():
    with APP_LOCK:
        if BATCH_STATE.get("running"):
            return False
    threading.Thread(target=_start_all_apps, daemon=True).start()
    return True


# ---------------------------------------------------------------- settings and AI writer

def _form_first(form, name, default=""):
    vals = form.get(name) if isinstance(form, dict) else None
    if not vals:
        return default
    return str(vals[0]).strip()


def sanitize_text(text, extra_values=None):
    result = str(text or "")
    values = []
    try:
        saved = load_ai_settings()
        if saved.get("api_key"):
            values.append(saved["api_key"])
    except Exception:
        pass
    if extra_values:
        values.extend(extra_values)
    for value in values:
        if value and len(str(value)) >= 4:
            result = result.replace(str(value), "[hidden]")
    return result


def random_char_string(length):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(int(length)))


RANDOM_GENERATORS = {
    "SECRET_KEY_BASE": lambda: secrets.token_hex(64),
    "POSTGRES_PASSWORD": lambda: secrets.token_hex(24),
    "NEXTAUTH_SECRET": lambda: secrets.token_urlsafe(32),
    "CALENDSO_ENCRYPTION_KEY": lambda: random_char_string(32),
    "CRON_API_KEY": lambda: secrets.token_hex(16),
    "JWT_SECRET": lambda: secrets.token_urlsafe(32),
    "CALCOM_APP_CREDENTIAL_ENCRYPTION_KEY": lambda: random_char_string(24),
    "CALCOM_SERVICE_ACCOUNT_ENCRYPTION_KEY": lambda: random_char_string(24),
    "NEXT_PRIVATE_ENCRYPTION_KEY": lambda: secrets.token_urlsafe(48),
    "NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY": lambda: secrets.token_urlsafe(48),
    "ENCRYPTION_KEY": lambda: secrets.token_urlsafe(32),
    "PG_DATABASE_PASSWORD": lambda: secrets.token_hex(32),
}


def generate_random_value(key):
    maker = RANDOM_GENERATORS.get(key)
    if maker:
        return maker()
    return secrets.token_urlsafe(32)


APP_REQUIRED_FIELDS = {
    "chatwoot": {"SECRET_KEY_BASE", "POSTGRES_PASSWORD"},
    "caldiy": {"DATABASE_URL", "DATABASE_DIRECT_URL", "NEXTAUTH_SECRET", "CALENDSO_ENCRYPTION_KEY", "JWT_SECRET"},
    "twenty": {"PG_DATABASE_PASSWORD", "ENCRYPTION_KEY"},
    "documenso": {
        "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "NEXTAUTH_SECRET",
        "NEXT_PRIVATE_ENCRYPTION_KEY", "NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY",
        "NEXT_PUBLIC_WEBAPP_URL", "NEXT_PRIVATE_DATABASE_URL", "NEXT_PRIVATE_DIRECT_DATABASE_URL",
        "NEXT_PRIVATE_SMTP_TRANSPORT", "NEXT_PRIVATE_SMTP_FROM_NAME", "NEXT_PRIVATE_SMTP_FROM_ADDRESS",
    },
}

SUPPLEMENTAL_FIELDS = {
    "caldiy": [
        {"key": "JWT_SECRET", "default": "", "required": True, "secret": True, "auto": True, "source": "Docker Compose"},
    ],
    "documenso": [
        {"key": "POSTGRES_USER", "default": "documenso", "required": True, "secret": False, "auto": False, "source": "Docker Compose"},
        {"key": "POSTGRES_PASSWORD", "default": "", "required": True, "secret": True, "auto": True, "source": "Docker Compose"},
        {"key": "POSTGRES_DB", "default": "documenso", "required": True, "secret": False, "auto": False, "source": "Docker Compose"},
    ],
}

ENV_SETUP_APP_IDS = {"chatwoot", "caldiy", "twenty", "documenso"}


def is_secret_field(key, value=""):
    upper = str(key or "").upper()
    if any(token in upper for token in ("SECRET", "KEY", "TOKEN", "PASSWORD", "PASS")):
        return True
    if re.search(r"^[a-z][a-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@", str(value or ""), re.IGNORECASE):
        return True
    return False


def _unquote_env_value(value):
    value = str(value or "")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        if value[0] == "'":
            return inner
        out = []
        i = 0
        while i < len(inner):
            ch = inner[i]
            if ch == "\\" and i + 1 < len(inner):
                nxt = inner[i + 1]
                if nxt == "n":
                    out.append("\n")
                elif nxt == "r":
                    out.append("\r")
                elif nxt == "t":
                    out.append("\t")
                else:
                    out.append(nxt)
                i += 2
            else:
                out.append(ch)
                i += 1
        return "".join(out)
    return value


def parse_env_value(raw):
    text = str(raw or "").strip()
    if not text:
        return ""
    if text[0] in ("'", '"'):
        quote = text[0]
        end = None
        i = 1
        while i < len(text):
            if text[i] == quote and (quote == "'" or text[i - 1] != "\\"):
                end = i
                break
            i += 1
        if end is not None:
            return _unquote_env_value(text[:end + 1])
    cut = []
    for ch in text:
        if ch == "#" and (not cut or cut[-1].isspace()):
            break
        cut.append(ch)
    return _unquote_env_value("".join(cut).strip())


def _env_assignment(line, commented=False):
    if commented:
        pattern = r"^\s*#\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
    else:
        pattern = r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
    match = re.match(pattern, str(line or ""))
    if not match:
        return None
    return match.group(1), match.group(2)


def parse_env_example_fields(app):
    example = PACK_DIR / app["folder"] / ".env.example"
    if not example.exists():
        return []
    required = APP_REQUIRED_FIELDS.get(app["id"], set())
    fields = []
    seen = set()
    try:
        lines = example.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        found = _env_assignment(line, commented=False)
        source = ".env.example"
        if not found and app["id"] == "twenty":
            commented = _env_assignment(line, commented=True)
            if commented and commented[0] in ("PG_DATABASE_PASSWORD", "ENCRYPTION_KEY"):
                found = commented
                source = ".env.example"
        if not found:
            continue
        key, raw = found
        if key in seen:
            continue
        seen.add(key)
        default = parse_env_value(raw)
        fields.append({
            "key": key,
            "default": default,
            "required": key in required,
            "secret": is_secret_field(key, default),
            "auto": key in RANDOM_GENERATORS,
            "source": source,
        })
    return fields


def env_fields_for_app(app):
    if app["id"] not in ENV_SETUP_APP_IDS:
        return []
    fields = parse_env_example_fields(app)
    seen = {field["key"] for field in fields}
    for extra in SUPPLEMENTAL_FIELDS.get(app["id"], []):
        if extra["key"] not in seen:
            fields.append(dict(extra))
            seen.add(extra["key"])
    return fields


def parse_env_file(path):
    values = {}
    path = Path(path)
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return values
    for line in lines:
        found = _env_assignment(line, commented=False)
        if found:
            key, raw = found
            values[key] = parse_env_value(raw)
    return values


def format_env_value(value):
    value = str(value or "")
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or any(ch in value for ch in ("#", '"', "'", "$")):
        if "'" not in value:
            return "'" + value + "'"
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$") + '"'
    return value


def write_env_values(path, fields, values):
    path = Path(path)
    lines = []
    for field in fields:
        key = field["key"]
        lines.append(f"{key}={format_env_value(values.get(key, ''))}")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)


def is_url_field(key):
    upper = str(key or "").upper()
    return upper.endswith("_URL") or upper in ("FRONTEND_URL", "SERVER_URL", "REDIS_URL") or "WEBAPP_URL" in upper or upper.endswith("_ENDPOINT")


def is_email_field(key):
    upper = str(key or "").upper()
    return upper.endswith("_EMAIL") or upper in ("EMAIL_FROM", "MAILER_SENDER_EMAIL", "NEXT_PRIVATE_SMTP_FROM_ADDRESS")


def validate_env_values(fields, values):
    missing = []
    invalid = []
    for field in fields:
        key = field["key"]
        value = str(values.get(key, "") or "")
        if field.get("required") and not value.strip():
            missing.append(key)
            continue
        if not value:
            continue
        if is_url_field(key) and "://" in value:
            parsed = urlparse(value)
            if parsed.scheme not in ("http", "https", "postgres", "postgresql", "redis", "rediss") or not parsed.netloc:
                invalid.append(key)
        if is_email_field(key):
            if not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value):
                invalid.append(key)
    return missing, invalid


def env_setup_status(app):
    fields = env_fields_for_app(app)
    env_path = PACK_DIR / app["folder"] / ".env"
    required = [field["key"] for field in fields if field.get("required")]
    if not env_path.exists():
        return {"code": "setup_needed", "label": "Setup needed", "missing": required, "invalid": []}
    values = parse_env_file(env_path)
    missing, invalid = validate_env_values(fields, values)
    if missing or invalid:
        return {"code": "needs_fields", "label": "Needs fields", "missing": missing, "invalid": invalid}
    return {"code": "ready", "label": "Ready", "missing": [], "invalid": []}


def resolve_settings_values(app, form):
    fields = env_fields_for_app(app)
    env_path = PACK_DIR / app["folder"] / ".env"
    existing = parse_env_file(env_path)
    values = {}
    generated = []
    prefix = f"f_{app['id']}_"
    for field in fields:
        key = field["key"]
        vals = form.get(prefix + key) if isinstance(form, dict) else None
        submitted = str(vals[0]).strip() if vals else None
        if field.get("secret") and (submitted is None or submitted == ""):
            if existing.get(key):
                value = existing[key]
            elif field.get("auto"):
                value = generate_random_value(key)
                generated.append(key)
            else:
                value = field.get("default", "")
        elif submitted is not None:
            value = submitted
        else:
            value = existing.get(key, field.get("default", ""))
        values[key] = value
    if app["id"] == "documenso":
        defaults = {field["key"]: field.get("default", "") for field in fields}
        db_user = values.get("POSTGRES_USER", "documenso")
        db_pass = values.get("POSTGRES_PASSWORD", "")
        db_name = values.get("POSTGRES_DB", "documenso")
        built_url = f"postgres://{db_user}:{db_pass}@database:5432/{db_name}"
        for key in ("NEXT_PRIVATE_DATABASE_URL", "NEXT_PRIVATE_DIRECT_DATABASE_URL"):
            current = str(values.get(key, "") or "")
            if current == defaults.get(key) or "127.0.0.1:54320" in current:
                values[key] = built_url
    return fields, values, generated


def settings_state_for_app(app_id):
    return SETTINGS_STATE["apps"].setdefault(app_id, {})


def handle_settings_save(app, form):
    fields, values, generated = resolve_settings_values(app, form)
    missing, invalid = validate_env_values(fields, values)
    state = settings_state_for_app(app["id"])
    if missing or invalid:
        state["save"] = {
            "kind": "error",
            "message": "Setup was not saved. Fill the named fields and try again.",
            "missing": missing,
            "invalid": invalid,
            "generated": [],
            "at": now_iso(),
        }
        log_warning(
            "settings", "APP_ENV_INCOMPLETE", f"{app['name']} setup was not saved.",
            f"Missing fields: {', '.join(missing) if missing else 'none'}; Invalid fields: {', '.join(invalid) if invalid else 'none'}",
            "Fill the named fields in Settings and save again.",
        )
        return False
    env_path = PACK_DIR / app["folder"] / ".env"
    write_env_values(env_path, fields, values)
    reread = parse_env_file(env_path)
    missing2, invalid2 = validate_env_values(fields, reread)
    if missing2 or invalid2:
        state["save"] = {
            "kind": "error",
            "message": "Setup was written, but LeadForge could not verify every required field.",
            "missing": missing2,
            "invalid": invalid2,
            "generated": [],
            "at": now_iso(),
        }
        log_error(
            "settings", "APP_ENV_VERIFY_FAILED", f"{app['name']} setup could not be verified after saving.",
            f"Missing fields: {', '.join(missing2) if missing2 else 'none'}; Invalid fields: {', '.join(invalid2) if invalid2 else 'none'}",
            "Open the app setup in Settings and save it again.",
        )
        return False
    state["save"] = {
        "kind": "success",
        "message": "Saved. This app is ready to start from the Apps page.",
        "missing": [],
        "invalid": [],
        "generated": generated,
        "at": now_iso(),
    }
    record_event(
        "info", "settings", "APP_ENV_SAVED", f"{app['name']} setup was saved from Settings.",
        "Generated random fields: " + (", ".join(generated) if generated else "none"),
    )
    return True


def handle_settings_check(app):
    state = settings_state_for_app(app["id"])
    problem = app_setup_problem(app)
    if problem:
        state["check"] = {"kind": "error", "message": problem["message"], "fix": problem["fix"], "at": now_iso()}
        return False
    dstatus, ddetail = docker_status(force=True)
    if dstatus != "ready":
        code = "DOCKER_MISSING" if dstatus == "missing" else "DOCKER_STOPPED"
        message = "Docker was not found on this computer." if dstatus == "missing" else "Docker is installed, but Docker Desktop is not running or did not answer."
        fix = docker_fix(dstatus)
        state["check"] = {"kind": "error", "message": message, "fix": fix, "at": now_iso()}
        log_error("settings", code, message, ddetail, fix)
        return False
    try:
        entry = app_assignment(app["id"])
        runtime_file = generate_runtime_compose(app, entry)
        proc = _compose_command(app, runtime_file, ["config", "--quiet"], runtime_env_for_app(app, entry["url"]), timeout=120)
    except Exception as exc:
        message = "LeadForge could not prepare the Docker check for this app."
        state["check"] = {"kind": "error", "message": message, "fix": "Send the LeadForge error log to Muse.", "at": now_iso()}
        log_error("settings", "SETTINGS_COMPOSE_CHECK_FAILED", message, str(exc), "Send the LeadForge error log to Muse.")
        return False
    combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        state["check"] = {"kind": "success", "message": "Docker accepted this app setup. The Compose check passed.", "fix": "", "at": now_iso()}
        record_event("info", "settings", "APP_SETUP_CHECK_PASSED", f"{app['name']} setup check passed.", app["folder"])
        return True
    message = "Docker rejected this app setup."
    state["check"] = {"kind": "error", "message": message, "fix": "Check the named setup fields, then run Check setup again.", "at": now_iso(), "detail": combined[-1200:]}
    log_error("settings", "APP_SETUP_CHECK_FAILED", message, combined[-2000:], "Check the app setup fields in Settings, then try again.")
    return False


def normalize_local_base_url(value):
    base = str(value or "").strip().rstrip("/")
    if not base:
        base = AI_PROVIDER_INFO["local"]["default_base_url"]
    if "://" not in base:
        base = "http://" + base
    return base.rstrip("/")


def load_ai_settings():
    data = read_json_file(AI_SETTINGS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    provider = data.get("provider")
    if provider not in AI_PROVIDER_INFO:
        provider = "gemini"
    cloud_provider = data.get("cloud_provider")
    if cloud_provider not in ("gemini", "groq"):
        cloud_provider = provider if provider in ("gemini", "groq") else ""
    local_base_url = os.environ.get("LEADFORGE_OLLAMA_BASE_URL") or data.get("local_base_url") or AI_PROVIDER_INFO["local"]["default_base_url"]
    local_model = str(data.get("local_model") or AI_PROVIDER_INFO["local"]["default_model"]).strip() or AI_PROVIDER_INFO["local"]["default_model"]
    stored_rules = str(data.get("pitch_rules") or "")
    return {
        "provider": provider,
        "api_key": str(data.get("api_key") or ""),
        "cloud_provider": cloud_provider,
        "local_base_url": normalize_local_base_url(local_base_url),
        "local_model": local_model,
        "pitch_rules": stored_rules if stored_rules.strip() else DEFAULT_PITCH_RULES,
        "pitch_examples": str(data.get("pitch_examples") or ""),
        "updated": str(data.get("updated") or ""),
    }


def save_ai_settings(provider, api_key, cloud_provider="", local_base_url="", local_model="", pitch_rules=None, pitch_examples=None):
    if provider not in AI_PROVIDER_INFO:
        provider = "gemini"
    if cloud_provider not in ("gemini", "groq"):
        cloud_provider = provider if provider in ("gemini", "groq") else ""
    if pitch_rules is None or pitch_examples is None:
        current = load_ai_settings()
        if pitch_rules is None:
            pitch_rules = current.get("pitch_rules", DEFAULT_PITCH_RULES)
        if pitch_examples is None:
            pitch_examples = current.get("pitch_examples", "")
    data = {
        "provider": provider,
        "api_key": str(api_key or ""),
        "cloud_provider": cloud_provider,
        "local_base_url": normalize_local_base_url(local_base_url),
        "local_model": str(local_model or AI_PROVIDER_INFO["local"]["default_model"]).strip() or AI_PROVIDER_INFO["local"]["default_model"],
        "pitch_rules": str(pitch_rules or ""),
        "pitch_examples": str(pitch_examples or ""),
        "updated": now_iso(),
    }
    atomic_write_json(AI_SETTINGS_FILE, data)
    OLLAMA_STATUS_CACHE.update({"at": 0, "data": None})
    return data


def ai_generation_ready(settings):
    if settings.get("provider") == "local":
        return True
    return bool(settings.get("api_key")) and settings.get("cloud_provider") == settings.get("provider")


def ai_public_state():
    settings = load_ai_settings()
    is_local = settings["provider"] == "local"
    cloud_key_ready = bool(settings["api_key"]) and settings.get("cloud_provider") == settings["provider"] if not is_local else bool(settings["api_key"])
    return {
        "provider": settings["provider"],
        "is_local": is_local,
        "has_key": True if is_local else cloud_key_ready,
        "has_cloud_key": bool(settings["api_key"]),
        "cloud_provider": settings.get("cloud_provider", ""),
        "local_base_url": settings["local_base_url"],
        "local_model": settings["local_model"],
        "updated": settings["updated"],
    }


def handle_ai_settings_save(form):
    provider = _form_first(form, "ai_provider", "gemini")
    if provider not in AI_PROVIDER_INFO:
        provider = "gemini"
    submitted = _form_first(form, "ai_api_key", "")
    existing = load_ai_settings()
    local_base_url = _form_first(form, "ai_local_base_url", existing.get("local_base_url", ""))
    local_model = _form_first(form, "ai_local_model", existing.get("local_model", ""))
    if provider == "local":
        api_key = existing.get("api_key", "")
        cloud_provider = existing.get("cloud_provider", "")
    elif submitted:
        api_key = submitted
        cloud_provider = provider
    elif existing.get("cloud_provider") == provider:
        api_key = existing.get("api_key", "")
        cloud_provider = provider
    else:
        api_key = ""
        cloud_provider = provider
    save_ai_settings(provider, api_key, cloud_provider, local_base_url, local_model)
    label = AI_PROVIDER_INFO[provider]["label"]
    if provider == "local":
        SETTINGS_STATE["ai"] = {
            "kind": "success",
            "message": "Local AI selected. No key is needed. The base URL and model are saved on this PC. Use Check local AI to test Ollama.",
            "at": now_iso(),
        }
        key_note = "not needed"
    else:
        SETTINGS_STATE["ai"] = {
            "kind": "success" if api_key else "warning",
            "message": f"{label} key saved on this PC." if api_key else f"{label} selected. No API key is saved yet.",
            "at": now_iso(),
        }
        key_note = "yes" if api_key else "no"
    record_event("info", "settings", "AI_SETTINGS_SAVED", "Free AI settings were saved from Settings.", f"Provider: {provider}; Key saved: {key_note}; Local model: {local_model or AI_PROVIDER_INFO['local']['default_model']}")
    return True


def pitch_playbook():
    settings = load_ai_settings()
    rules = str(settings.get("pitch_rules") or "").strip() or DEFAULT_PITCH_RULES
    examples = str(settings.get("pitch_examples") or "").strip()
    return rules, examples


PULL_JOB = {"state": "idle", "running": False, "percent": 0, "status_line": "", "message": "", "model": ""}
PULL_LOCK = threading.Lock()


def _set_pull_job(**updates):
    with PULL_LOCK:
        PULL_JOB.update(updates)


def pull_job_snapshot():
    with PULL_LOCK:
        return dict(PULL_JOB)


def run_model_pull():
    settings = load_ai_settings()
    base = normalize_local_base_url(settings.get("local_base_url"))
    model = (settings.get("local_model") or "qwen2.5:3b").strip() or "qwen2.5:3b"
    _set_pull_job(state="running", running=True, percent=0, status_line="Starting download", message="", model=model)
    url = os.environ.get("LEADFORGE_OLLAMA_PULL_URL") or (base + "/api/pull")
    payload = json.dumps({"name": model, "stream": True}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    succeeded = False
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    _set_pull_job(state="failed", running=False, message="The download stream sent an unreadable line, so the download was stopped.")
                    return
                if not isinstance(data, dict):
                    _set_pull_job(state="failed", running=False, message="The download stream sent a line in a format LeadForge could not read, so the download was stopped.")
                    return
                if data.get("error"):
                    _set_pull_job(state="failed", running=False, status_line=str(data.get("status") or ""), message=f"Model download failed: {data.get('error')}")
                    return
                status_text = str(data.get("status") or "")
                percent = pull_job_snapshot()["percent"]
                total = data.get("total")
                completed = data.get("completed")
                if total and completed is not None:
                    try:
                        percent = max(0, min(100, int(int(completed) * 100 / int(total))))
                    except (TypeError, ValueError):
                        pass
                if status_text == "success":
                    percent = 100
                    succeeded = True
                _set_pull_job(status_line=status_text, percent=percent)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed_body = json.loads(body)
            detail = str(parsed_body.get("error") or "")
        except Exception:
            detail = ""
        _set_pull_job(state="failed", running=False, message=f"Model download failed with HTTP {exc.code}." + (f" Detail: {detail}" if detail else ""))
        return
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _set_pull_job(state="failed", running=False, message="Could not reach Ollama for the download. Start Ollama on this PC, then try again.")
        log_error("ai", "AI_OFFLINE", "Ollama model pull could not reach the local server.", sanitize_text(str(exc)), "Start Ollama, then try the download again.")
        return
    except Exception as exc:
        _set_pull_job(state="failed", running=False, message="The model download stopped because of an internal problem. The detail is in the error log.")
        log_error("ai", "AI_PROVIDER_ERROR", "The model pull stopped because of an internal problem.", sanitize_text(str(exc)), "Try the download again. If it repeats, open Health and send the error log to Muse.")
        return
    if succeeded:
        OLLAMA_STATUS_CACHE["checked_at"] = 0.0
        _set_pull_job(state="done", running=False, percent=100, message=f"Model {model} is downloaded and ready to use.")
    else:
        _set_pull_job(state="failed", running=False, message="The download stream ended before Ollama reported success. Try the download again.")


def handle_model_pull():
    snapshot = pull_job_snapshot()
    if snapshot.get("running"):
        return True
    status = local_ai_status()
    if not status["running"]:
        _set_pull_job(state="failed", running=False, message=status["message"] + " " + status["fix"])
        return False
    threading.Thread(target=run_model_pull, daemon=True).start()
    return True


def handle_pitch_rules_save(form):
    existing = load_ai_settings()
    rules = _form_first(form, "pitch_rules", "")
    examples = _form_first(form, "pitch_examples", "")
    save_ai_settings(
        existing["provider"], existing.get("api_key", ""), existing.get("cloud_provider", ""),
        existing.get("local_base_url", ""), existing.get("local_model", ""),
        pitch_rules=rules, pitch_examples=examples,
    )
    SETTINGS_STATE["playbook"] = {
        "kind": "success",
        "message": f"Pitch rules saved. Every provider, Local AI and the manual instruction will use them. Rules: {len(rules)} characters. Examples: {len(examples)} characters.",
        "at": now_iso(),
    }
    record_event("info", "settings", "PITCH_RULES_SAVED", "Pitch rules were saved from Settings.", f"Rules characters: {len(rules)}; Examples characters: {len(examples)}")
    return True


def handle_pitch_rules_reset():
    existing = load_ai_settings()
    save_ai_settings(
        existing["provider"], existing.get("api_key", ""), existing.get("cloud_provider", ""),
        existing.get("local_base_url", ""), existing.get("local_model", ""),
        pitch_rules=DEFAULT_PITCH_RULES, pitch_examples=existing.get("pitch_examples", ""),
    )
    SETTINGS_STATE["playbook"] = {
        "kind": "success",
        "message": "Pitch rules were reset to the default playbook.",
        "at": now_iso(),
    }
    record_event("info", "settings", "PITCH_RULES_RESET", "Pitch rules were reset to default.", "")
    return True


class AIError(Exception):
    def __init__(self, code, message, fix, detail=""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix
        self.detail = detail


def ai_endpoint(provider):
    info = AI_PROVIDER_INFO[provider]
    return os.environ.get(info["url_env"]) or info["default_url"]


def local_ai_status(force=False):
    settings = load_ai_settings()
    base = settings["local_base_url"]
    selected = settings["local_model"]
    cached = OLLAMA_STATUS_CACHE.get("data")
    if not force and cached and cached.get("base_url") == base and cached.get("selected_model") == selected and time.time() - OLLAMA_STATUS_CACHE.get("at", 0) < 5:
        return dict(cached)
    result = {
        "running": False,
        "configured": False,
        "models": [],
        "selected_model": selected,
        "selected_downloaded": False,
        "base_url": base,
        "source": "",
        "code": "LOCAL_AI_NOT_RUNNING",
        "message": "Local AI is not running on this PC.",
        "fix": "Start Ollama on this PC and keep it running. If Ollama is not installed, download it free from https://ollama.com/download and install it first.",
    }

    def fetch_json(url):
        req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=OLLAMA_CHECK_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    models = None
    source = ""
    last_error = None
    try:
        data = fetch_json(base + "/api/tags")
        if not isinstance(data, dict):
            raise ValueError("Unexpected model list format")
        models = []
        for item in data.get("models") or []:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    models.append(name)
        source = "Ollama /api/tags"
    except Exception as tags_error:
        last_error = tags_error
        try:
            data = fetch_json(base + "/v1/models")
            if not isinstance(data, dict):
                raise ValueError("Unexpected model list format")
            models = []
            for item in data.get("data") or []:
                if isinstance(item, dict):
                    name = str(item.get("id") or item.get("name") or "").strip()
                    if name:
                        models.append(name)
            source = "OpenAI compatible /v1/models"
            last_error = None
        except Exception as models_error:
            last_error = models_error
    if models is not None:
        result["running"] = True
        result["models"] = models
        result["source"] = source
        result["selected_downloaded"] = selected in models
        if models:
            result["configured"] = True
            result["code"] = "LOCAL_AI_READY"
            result["message"] = f"Local AI is running on this PC. Answered by {source}."
            result["fix"] = "" if result["selected_downloaded"] else f"The selected model is not downloaded yet. Run: ollama pull {selected}"
        else:
            result["code"] = "LOCAL_AI_NO_MODEL"
            result["message"] = f"Local AI is running, but no model is downloaded yet. Answered by {source}."
            result["fix"] = f"Run: ollama pull {selected}"
    elif isinstance(last_error, urllib.error.HTTPError):
        result["running"] = True
        result["code"] = "LOCAL_AI_PROVIDER_ERROR"
        result["message"] = f"Local AI answered with an error (HTTP {last_error.code}) when LeadForge asked for the model list."
        result["fix"] = "Start the local AI server again, then use Check local AI. If it repeats, update the local AI app."
    elif isinstance(last_error, (TimeoutError, socket.timeout)):
        result["code"] = "LOCAL_AI_TIMEOUT"
        result["message"] = "Local AI did not answer in time on this PC."
        result["fix"] = "Start Ollama on this PC and keep it running, then use Check local AI again."
    elif isinstance(last_error, urllib.error.URLError):
        reason = getattr(last_error, "reason", last_error)
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower():
            result["code"] = "LOCAL_AI_TIMEOUT"
            result["message"] = "Local AI did not answer in time on this PC."
            result["fix"] = "Start Ollama on this PC and keep it running, then use Check local AI again."
        else:
            result["code"] = "LOCAL_AI_NOT_RUNNING"
    elif last_error is not None:
        result["code"] = "LOCAL_AI_PROVIDER_ERROR"
        result["message"] = "LeadForge could not read the local AI model list."
        result["fix"] = sanitize_text(str(last_error))
    OLLAMA_STATUS_CACHE.update({"at": time.time(), "data": dict(result)})
    return result


def handle_local_ai_check():
    status = local_ai_status(force=True)
    if status["configured"]:
        message = f"Local AI is running on this PC. Answered by {status.get('source') or 'the local server'}. Downloaded models: " + ", ".join(status["models"]) + "."
        if not status["selected_downloaded"]:
            message += f" The selected model {status['selected_model']} is not in that list yet."
        SETTINGS_STATE["local"] = {"kind": "success", "message": message, "fix": status["fix"], "models": status["models"], "at": now_iso()}
        record_event("info", "settings", "LOCAL_AI_CHECK_PASSED", "Local AI check passed.", "Downloaded models: " + ", ".join(status["models"]))
        return True
    SETTINGS_STATE["local"] = {"kind": "error", "message": status["message"], "fix": status["fix"], "models": status["models"], "at": now_iso()}
    log_warning("settings", status["code"], status["message"], status["base_url"], status["fix"])
    return False


def ai_request_local(base_url, model, prompt):
    override = os.environ.get("LEADFORGE_OLLAMA_URL")
    if override and override.rstrip("/").endswith("/v1/chat/completions"):
        url = override
    elif override and "://" in override:
        url = override.rstrip("/") + "/v1/chat/completions"
    else:
        url = normalize_local_base_url(base_url) + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You write short, honest outreach messages for local business services."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1400,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        detail = sanitize_text(f"HTTP {exc.code}: {body}")
        if exc.code == 404:
            raise AIError("AI_MODEL_MISSING", f"The local model {model} is not downloaded yet.", f"Run: ollama pull {model}", detail)
        if exc.code == 429:
            raise AIError("AI_RATE_LIMIT", "Local AI is busy right now.", "Wait a moment and try again.", detail)
        raise AIError("AI_PROVIDER_ERROR", f"Local AI returned an error (HTTP {exc.code}).", "Check that Ollama is running and the selected model is downloaded, then try again.", detail)
    except (TimeoutError, socket.timeout) as exc:
        raise AIError("AI_TIMEOUT", "Local AI took too long to answer.", "Your PC may be busy or the model may be large. Try again, or choose a lighter model like llama3.2:3b in Settings.", sanitize_text(str(exc)))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        reason_text = str(reason)
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in reason_text.lower():
            raise AIError("AI_TIMEOUT", "Local AI took too long to answer.", "Your PC may be busy or the model may be large. Try again, or choose a lighter model like llama3.2:3b in Settings.", sanitize_text(reason_text))
        raise AIError("AI_OFFLINE", "Ollama is not running on this PC.", "Start Ollama and keep it running, then try again. If Ollama is not installed, download it free from https://ollama.com/download.", sanitize_text(reason_text))
    except Exception as exc:
        raise AIError("AI_PROVIDER_ERROR", "The local AI request failed before a usable answer came back.", "Check Ollama is running, then try again.", sanitize_text(str(exc)))
    try:
        data = json.loads(raw)
    except Exception:
        raise AIError("AI_PROVIDER_ERROR", "Local AI answered in a format LeadForge could not read.", "Try again. If it repeats, update Ollama or choose another downloaded model.", sanitize_text(raw[:1000]))
    if not isinstance(data, dict):
        raise AIError("AI_PROVIDER_ERROR", "Local AI answered in a format LeadForge could not read.", "Try again. If it repeats, update Ollama or choose another downloaded model.", sanitize_text(raw[:1000]))
    choices = data.get("choices") or []
    text = ""
    if choices:
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "")
    if not text.strip():
        raise AIError("AI_PROVIDER_ERROR", "Local AI answered with no text.", "Try again, or choose another downloaded model in Settings.", sanitize_text(raw[:1000]))
    return text


def ai_request(provider, api_key, prompt):
    if provider == "local":
        settings = load_ai_settings()
        return ai_request_local(settings["local_base_url"], settings["local_model"], prompt)
    url = ai_endpoint(provider)
    if provider == "gemini":
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1400},
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    else:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You write short, honest outreach messages for local business services."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1400,
        }
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        detail = sanitize_text(f"HTTP {exc.code}: {body}", [api_key])
        if exc.code in (401, 403):
            raise AIError("AI_KEY_INVALID", "The free AI key was not accepted.", "Check the key in Settings, or make a fresh free key and save it again.", detail)
        if exc.code == 429:
            raise AIError("AI_RATE_LIMIT", "The free AI quota is used up for now.", "Wait for the free quota to reset, or switch provider in Settings.", detail)
        raise AIError("AI_PROVIDER_ERROR", f"The AI provider returned an error (HTTP {exc.code}).", "Try again in a little while. If it repeats, check the provider status and your key.", detail)
    except (TimeoutError, socket.timeout) as exc:
        raise AIError("AI_TIMEOUT", "The AI service took too long to answer.", "Check the internet connection and try again.", sanitize_text(str(exc), [api_key]))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        reason_text = str(reason)
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in reason_text.lower():
            raise AIError("AI_TIMEOUT", "The AI service took too long to answer.", "Check the internet connection and try again.", sanitize_text(reason_text, [api_key]))
        raise AIError("AI_OFFLINE", "LeadForge could not reach the free AI service.", "Check the internet connection on this PC, then try again.", sanitize_text(reason_text, [api_key]))
    except Exception as exc:
        raise AIError("AI_PROVIDER_ERROR", "The AI request failed before a usable answer came back.", "Try again. If it repeats, open Health and send the error log to Muse.", sanitize_text(str(exc), [api_key]))
    try:
        data = json.loads(raw)
    except Exception:
        raise AIError("AI_PROVIDER_ERROR", "The AI service answered in a format LeadForge could not read.", "Try again. If it repeats, switch provider in Settings.", sanitize_text(raw[:1000], [api_key]))
    if not isinstance(data, dict):
        raise AIError("AI_PROVIDER_ERROR", "The AI service answered in a format LeadForge could not read.", "Try again. If it repeats, switch provider in Settings.", sanitize_text(raw[:1000], [api_key]))
    text = ""
    if provider == "gemini":
        candidates = data.get("candidates") or []
        if candidates:
            parts = ((candidates[0].get("content") or {}).get("parts") or [])
            text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
    else:
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            text = str(message.get("content") or "")
    if not text.strip():
        raise AIError("AI_PROVIDER_ERROR", "The AI service answered with no text.", "Try again, or switch provider in Settings.", sanitize_text(raw[:1000], [api_key]))
    return text


def lead_fact_lines(lead):
    facts = []
    if lead.get("name"):
        facts.append(f"Business name: {lead['name']}")
    if lead.get("category"):
        facts.append(f"Business type: {lead['category']}")
    if lead.get("address"):
        facts.append(f"Address or area: {lead['address']}")
    if lead.get("rating"):
        facts.append(f"Rating: {lead['rating']}")
    if lead.get("reviews"):
        facts.append(f"Reviews: {lead['reviews']}")
    if lead.get("phone"):
        facts.append(f"Phone: {lead['phone']}")
    if lead.get("website"):
        facts.append(f"Website: {lead['website']}")
    if lead.get("note_text"):
        facts.append("Website note from the lead website:\n" + lead["note_text"][:3500])
    locality = lead_locality(lead)
    if locality:
        facts.append(f"Local area: {locality}")
    return facts


def build_ai_prompt(lead, output, language, format_style="api"):
    facts = lead_fact_lines(lead)
    if language == "bangla":
        language_line = "Write in Bangla using proper Bangla script. Keep business names, phone numbers and web addresses unchanged."
    else:
        language_line = "Write in English with simple, natural words."
    if format_style == "manual":
        if output == "whatsapp":
            format_lines = [
                "Use this exact reply format and nothing else:",
                "WHATSAPP:",
                "<the WhatsApp message>",
                "WhatsApp length: about 60 to 90 words.",
            ]
        elif output == "email":
            format_lines = [
                "Use this exact reply format and nothing else:",
                "SUBJECT:",
                "<one clear subject line>",
                "EMAIL:",
                "<the email body>",
                "Email length: about 120 to 160 words, not counting the subject.",
            ]
        else:
            format_lines = [
                "Use this exact reply format and nothing else:",
                "WHATSAPP:",
                "<the WhatsApp message>",
                "SUBJECT:",
                "<one clear subject line>",
                "EMAIL:",
                "<the email body>",
                "WhatsApp length: about 60 to 90 words. Email length: about 120 to 160 words, not counting the subject.",
            ]
    elif format_style == "none":
        if output == "whatsapp":
            format_lines = ["WhatsApp length: about 60 to 90 words."]
        elif output == "email":
            format_lines = ["Email length: about 120 to 160 words, not counting the subject."]
        else:
            format_lines = ["WhatsApp length: about 60 to 90 words. Email length: about 120 to 160 words, not counting the subject."]
    elif output == "whatsapp":
        format_lines = [
            "Write only the WhatsApp message. No heading and no quotes.",
            "WhatsApp length: about 60 to 90 words.",
        ]
    elif output == "email":
        format_lines = [
            "Use this exact format:",
            "EMAIL_SUBJECT: <one clear subject line>",
            "EMAIL_BODY:",
            "<the email body>",
            "Email length: about 120 to 160 words, not counting the subject.",
        ]
    else:
        format_lines = [
            "Use this exact format:",
            "WHATSAPP_MESSAGE:",
            "<the WhatsApp message>",
            "",
            "EMAIL_SUBJECT: <one clear subject line>",
            "EMAIL_BODY:",
            "<the email body>",
            "WhatsApp length: about 60 to 90 words. Email length: about 120 to 160 words, not counting the subject.",
        ]
    rules, examples = pitch_playbook()
    lines = ["Pitch rules:", rules]
    if examples:
        lines.extend(["", "Style examples to imitate:", examples])
    worked = learning_summary()
    if worked:
        lines.extend(["", "What has worked so far: " + worked])
    lines.extend([
        "",
        "You are writing a personal outreach message for Tanmoy.",
        "Tanmoy builds mobile apps, websites and software for local businesses under GDL Technologies.",
        language_line,
        "Write like a human. Sound warm and direct, not salesy.",
        "Use only the facts below. Do not invent facts. Do not invent prices, customers, ratings, results, or problems.",
        "Do not make fake claims about the business. If the business has a website listed, do not say it has no website.",
        "Make one soft call to action only: ask for a reply or a short call.",
        "",
        "Lead facts:",
    ])
    lines.extend(facts if facts else ["Only the business name is known."])
    lines.append("")
    lines.extend(format_lines)
    return "\n".join(lines)


def parse_ai_output(text, output, lead):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    result = {"whatsapp": "", "email_subject": "", "email_body": ""}
    if output in ("whatsapp", "both"):
        if output == "both":
            match = re.search(r"WHATSAPP_MESSAGE:\s*(.*?)(?=\n\s*EMAIL_SUBJECT:|\Z)", cleaned, re.IGNORECASE | re.DOTALL)
            result["whatsapp"] = match.group(1).strip() if match else ""
        else:
            result["whatsapp"] = re.sub(r"^WHATSAPP_MESSAGE:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    if output in ("email", "both"):
        subject_match = re.search(r"EMAIL_SUBJECT:\s*(.+)", cleaned, re.IGNORECASE)
        if subject_match:
            result["email_subject"] = subject_match.group(1).strip().splitlines()[0].strip()
        body_match = re.search(r"EMAIL_BODY:\s*(.*)\Z", cleaned, re.IGNORECASE | re.DOTALL)
        if body_match:
            result["email_body"] = body_match.group(1).strip()
        elif output == "email":
            lines = cleaned.splitlines()
            for i, line in enumerate(lines):
                if line.strip().lower().startswith("subject:"):
                    result["email_subject"] = line.split(":", 1)[1].strip()
                    result["email_body"] = "\n".join(lines[i + 1:]).strip()
                    break
            if not result["email_body"]:
                result["email_body"] = cleaned
    if output == "both" and not result["whatsapp"] and cleaned:
        before_email = cleaned.split("EMAIL_SUBJECT:")[0]
        result["whatsapp"] = before_email.replace("WHATSAPP_MESSAGE:", "").strip()
    if output in ("email", "both") and result["email_body"] and not result["email_subject"]:
        result["email_subject"] = f"Website and app ideas for {lead.get('name', 'your business')}"
    return result


BANNED_CLAIM_PATTERN = re.compile(r"guaranteed|guarantee|100\s*(?:percent|%)\s*results?|number one|best in the world", re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"\[[^\]\n]{1,60}\]")


def validate_pitch_output(result, output):
    problems = []
    whatsapp = str(result.get("whatsapp") or "")
    subject = str(result.get("email_subject") or "")
    body = str(result.get("email_body") or "")
    if output in ("whatsapp", "both") and not whatsapp.strip():
        problems.append("The WhatsApp message is missing.")
    if output in ("email", "both"):
        if not subject.strip():
            problems.append("The email subject is missing.")
        if not body.strip():
            problems.append("The email body is missing.")
    if output in ("whatsapp", "both") and whatsapp.strip():
        words = len(re.findall(r"\S+", whatsapp))
        if words < 30 or words > 140:
            problems.append(f"The WhatsApp message is {words} words. It should be roughly 30 to 140 words.")
    combined = "\n".join([whatsapp, subject, body])
    if PLACEHOLDER_PATTERN.search(combined):
        problems.append("Remove leftover square bracket placeholders like [Name]. Use the real lead facts instead.")
    banned = BANNED_CLAIM_PATTERN.search(combined)
    if banned:
        problems.append(f"Remove the banned claim wording: {banned.group(0)}.")
    return problems


AI_STYLE_PHRASES = [
    "i hope this message finds you well",
    "in today's fast-paced world",
    "in todays fast-paced world",
    "boost your business",
    "take your business to the next level",
    "esteemed",
    "delve",
    "furthermore",
    "moreover",
    "cutting-edge",
    "cutting edge",
    "revolutionize",
    "unlock your potential",
    "game-changer",
    "game changer",
]


def style_check_pitch(result, lead):
    text = "\n".join([
        str(result.get("whatsapp") or ""),
        str(result.get("email_subject") or ""),
        str(result.get("email_body") or ""),
    ])
    lowered = text.lower()
    reasons = []
    score = 0
    found = [phrase for phrase in AI_STYLE_PHRASES if phrase in lowered]
    if found:
        score += min(2, len(found))
        reasons.append("Stock phrases found: " + ", ".join(found[:3]))
    if "—" in text or "–" in text:
        score += 1
        reasons.append("Contains an em dash or en dash")
    sentences = [s for s in re.split(r"[.!?]+", text) if len(s.split()) >= 3]
    if len(sentences) >= 3:
        lengths = [len(s.split()) for s in sentences]
        mean = sum(lengths) / len(lengths)
        variance = sum((value - mean) ** 2 for value in lengths) / len(lengths)
        if variance ** 0.5 < 2.2:
            score += 1
            reasons.append("Sentence lengths are very uniform")
    name = str((lead or {}).get("name") or "")
    locality = lead_locality(lead or {})
    if name and name.lower() not in lowered and (not locality or locality.lower() not in lowered):
        score += 1
        reasons.append("No lead specific detail: the business name or local area is missing")
    if PLACEHOLDER_PATTERN.search(text):
        score += 1
        reasons.append("Placeholder brackets left in the text")
    label = "Looks human" if score == 0 else "Some AI signs" if score <= 2 else "Looks AI-written"
    return {"label": label, "score": score, "reasons": reasons}


def generate_pitch(lead, output, language, provider_override=None, simple=False):
    settings = load_ai_settings()
    if provider_override in AI_PROVIDER_INFO:
        settings = dict(settings)
        settings["provider"] = provider_override
        if provider_override in ("gemini", "groq"):
            settings["cloud_provider"] = provider_override
    if not ai_generation_ready(settings):
        raise AIError("AI_NO_KEY", "No free AI key is saved yet.", "Open Settings, save a Gemini or Groq free key, choose Local AI, or use Manual mode on the Writer page.")
    prompt = build_ai_prompt(lead, output, language)
    if simple:
        prompt += "\n\nKeep it very simple and short. Use plain words and short sentences. Keep the WhatsApp message near 60 words."
    raw = ai_request(settings["provider"], settings["api_key"], prompt)
    result = parse_ai_output(raw, output, lead)
    if not (result.get("whatsapp") or result.get("email_body")):
        raise AIError("AI_PROVIDER_ERROR", "The AI answer did not contain a usable message.", "Try Regenerate, or switch provider in Settings.", sanitize_text(raw[:1000], [settings["api_key"]]))
    current_raw = raw
    problems = validate_pitch_output(result, output)
    quality_note = ""
    if problems:
        correction_prompt = (
            prompt
            + "\n\nYour previous answer had problems. Rewrite the pitch from scratch using the same lead facts and the same output format.\nFix these problems only:\n"
            + "\n".join("- " + problem for problem in problems)
            + "\n\nPrevious answer:\n"
            + raw[:3000]
        )
        try:
            raw_retry = ai_request(settings["provider"], settings["api_key"], correction_prompt)
            result_retry = parse_ai_output(raw_retry, output, lead)
            if result_retry.get("whatsapp") or result_retry.get("email_body"):
                result = result_retry
                current_raw = raw_retry
                retry_problems = validate_pitch_output(result, output)
                quality_note = "Auto-fixed on retry" if not retry_problems else "Check before sending"
            else:
                quality_note = "Check before sending"
        except AIError:
            quality_note = "Check before sending"
    style = style_check_pitch(result, lead)
    humanized = False
    if style["label"] == "Looks AI-written":
        humanize_prompt = (
            prompt
            + "\n\nRewrite the pitch so it sounds like a real person typed it. Vary the sentence lengths a lot. Remove these problems: "
            + "; ".join(style["reasons"])
            + ". Use the lead's real details and plain spoken words. Keep the same output format.\n\nPrevious answer:\n"
            + current_raw[:3000]
        )
        try:
            raw_human = ai_request(settings["provider"], settings["api_key"], humanize_prompt)
            result_human = parse_ai_output(raw_human, output, lead)
            if result_human.get("whatsapp") or result_human.get("email_body"):
                style_human = style_check_pitch(result_human, lead)
                if style_human["score"] < style["score"]:
                    result = result_human
                    style = style_human
                    humanized = True
                    if validate_pitch_output(result, output) and not quality_note:
                        quality_note = "Check before sending"
        except AIError:
            pass
    result["provider"] = settings["provider"]
    result["provider_label"] = AI_PROVIDER_INFO[settings["provider"]]["label"]
    result["quality_note"] = quality_note
    result["style_label"] = style["label"]
    result["style_reasons"] = style["reasons"]
    result["humanized"] = humanized
    return result


def build_manual_instruction(lead, output, language):
    prompt = build_ai_prompt(lead, output, language, format_style="manual")
    return prompt + "\n\nImportant: Reply with only the format above. Do not add an introduction, explanation, or extra text."


def manual_reply_format_lines(output):
    if output == "whatsapp":
        return ["WHATSAPP:", "<the WhatsApp message>"]
    if output == "email":
        return ["SUBJECT:", "<one clear subject line>", "EMAIL:", "<the email body>"]
    return [
        "WHATSAPP:",
        "<the WhatsApp message>",
        "SUBJECT:",
        "<one clear subject line>",
        "EMAIL:",
        "<the email body>",
    ]


def build_manual_batch_instruction(leads, output, language):
    selected = list(leads or [])[:10]
    lines = [
        f"You will write separate outreach pitches for {len(selected)} leads.",
        "Use only the facts inside each lead block. Do not invent facts, prices, customers, ratings, results, or problems.",
        "Reply only with the numbered sections below. Do not add an introduction or explanation.",
        "",
        "Use this exact reply format:",
    ]
    for i, lead in enumerate(selected, start=1):
        lines.append(f"=== LEAD {i}: {lead.get('name', '')} ===")
        lines.extend(manual_reply_format_lines(output))
    lines.append("")
    lines.append("Lead blocks:")
    for i, lead in enumerate(selected, start=1):
        lines.append("")
        lines.append(f"--- LEAD {i}: {lead.get('name', '')} ---")
        lines.append(build_ai_prompt(lead, output, resolve_pitch_language(lead, language), format_style="none"))
    return "\n".join(lines)


def build_web_assistant_setup(output):
    rules, examples = pitch_playbook()
    lines = [
        "You are my pitch writer. I will paste lead blocks. Reply only in the format.",
        "",
        "Pitch rules:",
        rules,
    ]
    if examples:
        lines.extend(["", "Style examples to imitate:", examples])
    lines.extend(["", "Output format:"])
    lines.extend(manual_reply_format_lines(output))
    lines.extend([
        "",
        "If I paste more than one lead block, answer with one section per lead. Start each section with === LEAD n: <business name> === and use the same markers inside that section.",
        "Use only the facts in each lead block. Do not invent facts.",
    ])
    return "\n".join(lines)


def build_short_manual_instruction(lead, output, language):
    facts = lead_fact_lines(lead)
    language_line = "Language: Bangla." if language == "bangla" else "Language: English."
    lines = ["Lead block:", language_line]
    lines.extend(facts if facts else ["Only the business name is known."])
    lines.extend(["", "Write the pitches in your saved format."])
    return "\n".join(lines)


def build_short_manual_batch_instruction(leads, output, language):
    selected = list(leads or [])[:10]
    if language == "auto":
        language_line = "Language: use the language that fits each lead's region (Bangla for West Bengal, English elsewhere)."
    else:
        language_line = "Language: Bangla." if language == "bangla" else "Language: English."
    lines = [f"Lead blocks for {len(selected)} leads.", language_line]
    for i, lead in enumerate(selected, start=1):
        lines.append("")
        lines.append(f"--- LEAD {i}: {lead.get('name', '')} ---")
        facts = lead_fact_lines(lead)
        lines.extend(facts if facts else ["Only the business name is known."])
    lines.extend(["", "Write the pitches in your saved format."])
    return "\n".join(lines)


def parse_manual_output(text, output, lead=None):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    result = {"whatsapp": "", "email_subject": "", "email_body": ""}
    marker_specs = []
    if output in ("whatsapp", "both"):
        marker_specs.append(("whatsapp", r"WHATSAPP(?:_MESSAGE)?"))
    if output in ("email", "both"):
        marker_specs.append(("email_subject", r"(?:EMAIL_)?SUBJECT"))
        marker_specs.append(("email_body", r"EMAIL(?:_BODY)?"))
    matches = []
    for field_name, pattern in marker_specs:
        for match in re.finditer(r"(?im)^[ \t]*" + pattern + r"[ \t]*:[ \t]*", cleaned):
            matches.append((match.start(), match.end(), field_name))
    matches.sort(key=lambda item: item[0])
    if not matches:
        result["whatsapp"] = cleaned
        return result, False
    for idx, (start, end, field_name) in enumerate(matches):
        next_start = matches[idx + 1][0] if idx + 1 < len(matches) else len(cleaned)
        value = cleaned[end:next_start].strip()
        if field_name == "email_subject":
            value = value.splitlines()[0].strip() if value else ""
        result[field_name] = value
    if output in ("email", "both") and result.get("email_body") and not result.get("email_subject"):
        lead_name = (lead or {}).get("name", "your business") if isinstance(lead, dict) else "your business"
        result["email_subject"] = f"Website and app ideas for {lead_name}"
    return result, True


def find_note_file(website):
    host = host_of(website)
    if not host or not NOTES_DIR.exists():
        return None
    candidates = sorted([p for p in NOTES_DIR.glob("*.md") if host in p.name])
    return candidates[0] if candidates else None


def pitch_slug(name, index):
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "lead").lower()).strip("-")[:60].strip("-") or "lead"
    return f"{base}-{int(index) + 1}"


def lead_records():
    parsed = _parse_results_strict(LATEST_CSV)
    if parsed["status"] != "valid":
        return []
    fieldnames, rows = parsed["fieldnames"], parsed["rows"]
    lower = {fn.lower().strip(): fn for fn in fieldnames if fn}

    def find(keys):
        for key in keys:
            if key in lower:
                return lower[key]
        return None

    keys = {
        "name": find(["title", "name", "business_name", "business", "store_name"]),
        "category": find(["category", "type", "business_type", "industry", "primary_category"]),
        "address": find(["address", "full_address", "location", "street_address", "city"]),
        "rating": find(["review_rating", "rating", "ratings", "score"]),
        "reviews": find(["review_count", "reviews", "reviews_count", "number_of_reviews"]),
        "phone": find(["phone", "phone_number", "telephone", "mobile"]),
        "website": find(["website", "site", "url", "web"]),
    }
    records = []
    for idx, row in enumerate(rows):
        def value(key):
            source = keys.get(key)
            return str(row.get(source) or "").strip() if source else ""

        name = value("name") or f"Lead {idx + 1}"
        website = value("website")
        note_path = find_note_file(website)
        note_text = ""
        if note_path:
            try:
                note_text = note_path.read_text(encoding="utf-8", errors="replace")[:5000]
            except OSError:
                note_text = ""
        records.append({
            "index": idx,
            "slug": pitch_slug(name, idx),
            "name": name,
            "category": value("category"),
            "address": value("address"),
            "rating": value("rating"),
            "reviews": value("reviews"),
            "phone": value("phone"),
            "website": website,
            "note_exists": bool(note_path),
            "note_path": str(note_path) if note_path else "",
            "note_text": note_text,
        })
    return records


def latest_pitch_for_lead(record):
    slug = record.get("slug") if isinstance(record, dict) else str(record or "")
    if not slug or not PITCHES_DIR.exists():
        return None
    candidates = []
    for path in PITCHES_DIR.glob(slug + "-*.md"):
        try:
            candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def detect_region(lead):
    text = str((lead or {}).get("address") or "").lower()
    for state, needles, language, note in REGION_PACK:
        if any(needle in text for needle in needles):
            return {"state": state, "language": language, "note": note}
    return {"state": "India", "language": "english", "note": "English works well here."}


def lead_locality(lead):
    address = str((lead or {}).get("address") or "").strip()
    if not address:
        return ""
    return address.split(",")[0].strip()[:60]


def resolve_pitch_language(lead, selected):
    if selected in ("english", "bangla"):
        return selected
    return detect_region(lead)["language"]


def compute_qualification(lead, meta=None):
    if meta is None:
        meta = read_json_file(LATEST_META, {})
    website = str((lead or {}).get("website") or "").strip()
    failed = [str(item).lower() for item in (meta.get("failed_websites") or [])]
    if website:
        host = host_of(website).lower()
        for item in failed:
            if (host and host in item) or website.lower() in item:
                return "website_dead"
        if lead.get("note_exists"):
            return "has_website"
        return "unknown"
    if meta.get("enrich_attempted") or meta.get("status") == "good" or meta.get("last_result") == "success":
        return "no_website_confirmed"
    return "unknown"


def lead_store_key(lead):
    digits = re.sub(r"\D", "", str((lead or {}).get("phone") or ""))
    if len(digits) >= 10:
        return "phone:" + digits[-10:]
    name = str((lead or {}).get("name") or "").strip().lower()
    return "name:" + name + "|" + lead_locality(lead).lower()


def load_lead_store():
    if LEADS_STORE_FILE.exists():
        try:
            with open(LEADS_STORE_FILE, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = None
        if raw is None:
            if LEADS_STORE_FILE.stat().st_size > 0:
                log_error(
                    "store", "STORE_CORRUPT",
                    "The lead store file could not be read, so LeadForge started from an empty store view. The file itself was left untouched.",
                    str(LEADS_STORE_FILE),
                    "Open Health and send the error log to Muse. Restoring a backup of leads.json also works.",
                )
            return {"leads": {}, "updated": "", "synced_meta": ""}
        if isinstance(raw, dict) and isinstance(raw.get("leads"), dict):
            return raw
        return {"leads": {}, "updated": "", "synced_meta": ""}
    return {"leads": {}, "updated": "", "synced_meta": ""}


def save_lead_store(store):
    store["updated"] = now_iso()
    atomic_write_json(LEADS_STORE_FILE, store)
    return store


def sync_lead_store():
    records = lead_records()
    store = load_lead_store()
    if not records:
        return store
    meta = read_json_file(LATEST_META, {})
    meta_marker = str(meta.get("updated") or "")
    new_run = store.get("synced_meta") != meta_marker
    now = now_iso()
    for rec in records:
        key = lead_store_key(rec)
        entry = store["leads"].get(key) or {}
        for field_name in ("name", "category", "address", "phone", "website", "rating", "reviews"):
            if rec.get(field_name):
                entry[field_name] = rec[field_name]
        entry.setdefault("name", rec.get("name", ""))
        entry["key"] = key
        entry["slug"] = rec.get("slug", "")
        entry["first_seen"] = entry.get("first_seen") or now
        entry["last_seen"] = now
        if new_run:
            entry["times_seen"] = int(entry.get("times_seen") or 0) + 1
        entry.setdefault("times_seen", 1)
        entry["qualification"] = compute_qualification(rec, meta)
        entry["note_file"] = Path(rec["note_path"]).name if rec.get("note_path") else ""
        pitch = latest_pitch_for_lead(rec)
        if pitch:
            entry["pitch_file"] = pitch.name
        entry.setdefault("pitch_file", "")
        if entry.get("outcome") not in LEAD_OUTCOMES:
            entry["outcome"] = "New"
        entry["region"] = detect_region(rec)["state"]
        store["leads"][key] = entry
    store["synced_meta"] = meta_marker
    save_lead_store(store)
    return store


def update_store_after_pitch(lead, pitch_path, language):
    store = sync_lead_store()
    entry = store["leads"].get(lead_store_key(lead))
    if not entry:
        return
    entry["pitch_file"] = Path(pitch_path).name
    entry["pitch_language"] = language
    entry["pitch_region"] = detect_region(lead)["state"]
    if entry.get("outcome") in ("", "New"):
        entry["outcome"] = "Pitched"
    save_lead_store(store)


def set_lead_outcome(key, outcome):
    if outcome not in LEAD_OUTCOMES:
        return False
    store = load_lead_store()
    entry = store["leads"].get(key)
    if not entry:
        return False
    entry["outcome"] = outcome
    save_lead_store(store)
    return True


def learning_summary(store=None):
    store = store or load_lead_store()
    pitched = [e for e in store.get("leads", {}).values() if e.get("pitch_file") and e.get("outcome") not in ("", "New", None)]
    if len(pitched) < 3:
        return ""
    groups = {}
    for entry in pitched:
        groups.setdefault((entry.get("pitch_language") or "english", entry.get("pitch_region") or "India"), []).append(entry)
    best = None
    for (language, region), items in groups.items():
        replies = sum(1 for item in items if item.get("outcome") in ("Replied", "Call booked"))
        if best is None or replies > best[2]:
            best = (language, region, replies, len(items))
    if best and best[2] > 0:
        language_label = "Bangla" if best[0] == "bangla" else "English"
        return f"{language_label} WhatsApp pitches to {best[1]} leads got {best[2]} replies from {best[3]} sent"
    return f"{len(pitched)} pitches sent, no replies yet. Keep marking outcomes on the Leads page."


def save_pitch_file(lead, result, output, language, source=""):
    ensure_storage()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = PITCHES_DIR / f"{lead['slug']}-{stamp}.md"
    suffix = 2
    while path.exists():
        path = PITCHES_DIR / f"{lead['slug']}-{stamp}-{suffix}.md"
        suffix += 1
    lines = [
        f"# Pitch for {lead['name']}",
        "",
        f"Provider: {result.get('provider_label') or result.get('provider', '')}",
        *([f"Source: {source}"] if source else []),
        f"Language: {language}",
        f"Output: {output}",
        f"Generated: {now_iso()}",
        *([f"Quality note: {result.get('quality_note')}"] if result.get("quality_note") else []),
        *([f"Style check: {result.get('style_label')}"] if result.get("style_label") else []),
        *([f"Style reasons: {'; '.join(result.get('style_reasons') or [])}"] if result.get("style_reasons") else []),
        *(["Humanized: yes"] if result.get("humanized") else []),
        "",
    ]
    if result.get("whatsapp"):
        lines.extend(["## WhatsApp", result["whatsapp"], ""])
    if result.get("email_subject") or result.get("email_body"):
        lines.extend(["## Email subject", result.get("email_subject", ""), "", "## Email", result.get("email_body", ""), ""])
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return path


def parse_pitch_file(path):
    result = {"whatsapp": "", "email_subject": "", "email_body": "", "quality_note": "", "style_label": "", "style_reasons": [], "humanized": False}
    if not path:
        return result
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result
    heading_map = {"WhatsApp": "whatsapp", "Email subject": "email_subject", "Email": "email_body"}
    current = None
    buffer = []

    def flush():
        if current:
            result[current] = "\n".join(buffer).strip()

    for line in text.splitlines():
        if line.startswith("Quality note:"):
            result["quality_note"] = line.split(":", 1)[1].strip()
        if line.startswith("Style check:"):
            result["style_label"] = line.split(":", 1)[1].strip()
        if line.startswith("Style reasons:"):
            result["style_reasons"] = [part.strip() for part in line.split(":", 1)[1].split(";") if part.strip()]
        if line.startswith("Humanized:"):
            result["humanized"] = line.split(":", 1)[1].strip().lower() == "yes"
        if line.startswith("## "):
            flush()
            buffer = []
            current = heading_map.get(line[3:].strip())
        elif current:
            buffer.append(line)
    flush()
    return result


def writer_job_snapshot():
    with WRITER_JOB_LOCK:
        data = dict(WRITER_JOB)
        data["errors"] = list(WRITER_JOB.get("errors", []))
        return data


def _set_writer_job(**values):
    with WRITER_JOB_LOCK:
        WRITER_JOB.update(values)


def other_configured_provider(settings):
    chosen = settings.get("provider")
    cloud_provider = settings.get("cloud_provider")
    cloud_ready = bool(settings.get("api_key")) and cloud_provider in ("gemini", "groq")
    if chosen != "local" and local_ai_status()["configured"]:
        return "local"
    if chosen == "local" and cloud_ready:
        return cloud_provider
    if chosen in ("gemini", "groq") and cloud_ready and cloud_provider != chosen:
        return cloud_provider
    return ""


def pitch_attempts_for_lead(lead, output, language, log_fn):
    resolved = resolve_pitch_language(lead, language)
    last_error = None
    try:
        result = generate_pitch(lead, output, resolved)
        if result.get("quality_note") == "Check before sending":
            raise AIError("AI_OUTPUT_CHECK", "The pitch failed the output check after one fix try.", "Use Manual mode for this lead, or try again later.")
        return result, resolved
    except AIError as exc:
        last_error = exc
        log_fn(f"{lead['name']}: first try failed ({exc.code}). Retrying with a shorter, simpler prompt.")
    try:
        result = generate_pitch(lead, output, resolved, simple=True)
        if result.get("quality_note") == "Check before sending":
            raise AIError("AI_OUTPUT_CHECK", "The pitch failed the output check after one fix try.", "Use Manual mode for this lead, or try again later.")
        log_fn(f"{lead['name']}: the simpler retry worked.")
        return result, resolved
    except AIError as exc:
        last_error = exc
    other = other_configured_provider(load_ai_settings())
    if other:
        log_fn(f"{lead['name']}: trying the other provider now ({other}).")
        try:
            result = generate_pitch(lead, output, resolved, provider_override=other)
            if result.get("quality_note") == "Check before sending":
                raise AIError("AI_OUTPUT_CHECK", "The pitch failed the output check after one fix try.", "Use Manual mode for this lead, or try again later.")
            log_fn(f"{lead['name']}: the other provider worked.")
            return result, resolved
        except AIError as exc:
            last_error = exc
    raise last_error


def mark_store_pitch_error(lead, code, message):
    try:
        store = sync_lead_store()
        entry = store["leads"].get(lead_store_key(lead))
        if entry:
            entry["last_error"] = f"{code}: {message}"
            save_lead_store(store)
    except Exception:
        pass


def select_batch_leads(include_has_website=False):
    records = lead_records()
    meta = read_json_file(LATEST_META, {})
    counts = {key: 0 for key in QUALIFICATION_LABELS}
    selected = []
    for rec in records:
        qualification = compute_qualification(rec, meta)
        rec["qualification"] = qualification
        counts[qualification] += 1
        if qualification in ("no_website_confirmed", "website_dead") or (include_has_website and qualification == "has_website"):
            selected.append(rec)
    return selected[:10], counts


def write_pitches_for_leads(selected, output, language, log_fn, progress_fn=None):
    succeeded = 0
    failed = 0
    manual = 0
    errors = []
    for i, lead in enumerate(selected):
        if i > 0 and AI_BATCH_PAUSE_SECONDS:
            time.sleep(AI_BATCH_PAUSE_SECONDS)
        if progress_fn:
            progress_fn(i, lead["name"], succeeded, failed)
        try:
            result, resolved = pitch_attempts_for_lead(lead, output, language, log_fn)
            path = save_pitch_file(lead, result, output, resolved)
            update_store_after_pitch(lead, path, resolved)
            succeeded += 1
        except AIError as exc:
            failed += 1
            manual += 1
            errors.append({"lead": lead["name"], "code": exc.code, "message": exc.message})
            log_fn(f"{lead['name']}: could not be written ({exc.code}). Marked for manual mode.")
            log_error("ai", exc.code, f"AI writing failed for {lead['name']}.", sanitize_text(exc.detail), exc.fix)
            mark_store_pitch_error(lead, exc.code, exc.message)
        except Exception as exc:
            failed += 1
            manual += 1
            errors.append({"lead": lead["name"], "code": "AI_PROVIDER_ERROR", "message": "The AI request failed for this lead."})
            log_fn(f"{lead['name']}: could not be written (AI_PROVIDER_ERROR). Marked for manual mode.")
            log_error("ai", "AI_PROVIDER_ERROR", f"AI writing failed for {lead['name']}.", sanitize_text(str(exc)), "Try again. If it repeats, open Health and send the error log to Muse.")
            mark_store_pitch_error(lead, "AI_PROVIDER_ERROR", "The AI request failed for this lead.")
        if progress_fn:
            progress_fn(i + 1, "", succeeded, failed)
    return {"total": len(selected), "succeeded": succeeded, "failed": failed, "manual": manual, "errors": errors}


def run_ai_batch(output, language, include_has_website=False):
    leads, counts = select_batch_leads(include_has_website)
    _set_writer_job(
        state="running", running=True, total=len(leads), processed=0, succeeded=0, failed=0,
        current="", message="Writing pitches...", errors=[], output=output, language=language,
        started_at=now_iso(), finished_at="", qualified_counts=counts, manual=0,
    )

    def log_step(message):
        record_event("info", "ai", "AI_BATCH_STEP", message)

    def progress(processed, current, succeeded, failed):
        _set_writer_job(processed=processed, current=current, succeeded=succeeded, failed=failed)

    result_counts = write_pitches_for_leads(leads, output, language, log_step, progress)
    total = result_counts["total"]
    succeeded = result_counts["succeeded"]
    failed = result_counts["failed"]
    errors = result_counts["errors"]
    if total == 0:
        state = "failed"
        message = "No qualified leads were available for the batch. Qualified means no website confirmed, or a dead website."
    elif failed == 0:
        state = "done"
        message = f"Batch finished. {succeeded} of {total} pitches are ready."
    elif succeeded > 0:
        state = "partial"
        message = f"Batch partially done. {succeeded} of {total} pitches are ready, {failed} failed."
    else:
        state = "failed"
        message = f"Batch failed. No pitches were written out of {total} leads."
    included_counts = {key: 0 for key in QUALIFICATION_LABELS}
    for selected_lead in leads:
        included_counts[selected_lead.get("qualification", "unknown")] += 1
    message += (
        f" Included: {included_counts['no_website_confirmed']} with no website confirmed, {included_counts['website_dead']} with a dead website, "
        f"{included_counts['has_website']} with a website. Not included: {counts['unknown']} unknown, "
        f"{counts['has_website'] - included_counts['has_website']} with a website (toggle off)."
    )
    _set_writer_job(state=state, running=False, current="", message=message, finished_at=now_iso(), errors=list(errors), manual=result_counts["manual"], succeeded=succeeded, failed=failed, processed=total)


def handle_writer_generate(form):
    leads = lead_records()
    if not leads:
        WRITER_STATE.update({"notice": "", "error": "No leads are saved yet. Run a search first.", "error_code": "AI_NO_LEADS", "last": None})
        return False
    try:
        lead_index = int(float(str(_form_first(form, "lead", "0")).strip()))
    except (TypeError, ValueError):
        lead_index = 0
    if lead_index < 0 or lead_index >= len(leads):
        lead_index = 0
    lead = leads[lead_index]
    output = _form_first(form, "output", "both")
    if output not in ("whatsapp", "email", "both"):
        output = "both"
    language = _form_first(form, "language", "english")
    if language not in ("english", "bangla", "auto"):
        language = "english"
    settings = load_ai_settings()
    if not ai_generation_ready(settings):
        exc = AIError("AI_NO_KEY", "No free AI key is saved yet.", "Open Settings, save a Gemini or Groq free key, choose Local AI, or use Manual mode on the Writer page.")
        WRITER_STATE.update({"notice": "", "error": exc.message, "error_code": exc.code, "last": None})
        log_error("ai", exc.code, exc.message, "", exc.fix)
        return False
    resolved_language = resolve_pitch_language(lead, language)
    try:
        result = generate_pitch(lead, output, resolved_language)
        path = save_pitch_file(lead, result, output, resolved_language)
        update_store_after_pitch(lead, path, resolved_language)
    except AIError as exc:
        WRITER_STATE.update({"notice": "", "error": exc.message + (f" Fix: {exc.fix}" if exc.fix else ""), "error_code": exc.code, "last": None})
        log_error("ai", exc.code, exc.message, sanitize_text(exc.detail), exc.fix)
        return False
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        WRITER_STATE.update({"notice": "", "error": "The pitch could not be written because of an internal problem. The detail is in the error log.", "error_code": "AI_PROVIDER_ERROR", "last": None})
        log_error("ai", "AI_PROVIDER_ERROR", "The pitch writer hit an internal problem.", sanitize_text(detail), "Try again. If it repeats, open Health and send the error log to Muse.")
        return False
    last = {"lead_index": lead_index, "slug": lead["slug"], "output": output, "language": resolved_language}
    last.update(result)
    WRITER_STATE.update({"notice": f"Pitch ready for {lead['name']}. Saved as {path.name}.", "error": "", "error_code": "", "last": last})
    record_event("info", "ai", "AI_PITCH_CREATED", f"AI pitch created for {lead['name']}.", f"Provider: {result.get('provider', '')}; Output: {output}; Language: {language}")
    return True


def handle_writer_batch(form):
    snapshot = writer_job_snapshot()
    if snapshot.get("running"):
        WRITER_STATE.update({"notice": "A pitch batch is already running. Wait for it to finish.", "error": "", "error_code": ""})
        return False
    leads = lead_records()
    if not leads:
        WRITER_STATE.update({"notice": "", "error": "No leads are saved yet. Run a search first.", "error_code": "AI_NO_LEADS"})
        return False
    settings = load_ai_settings()
    if not ai_generation_ready(settings):
        exc = AIError("AI_NO_KEY", "No free AI key is saved yet.", "Open Settings, save a Gemini or Groq free key, choose Local AI, or use Manual mode on the Writer page.")
        WRITER_STATE.update({"notice": "", "error": exc.message, "error_code": exc.code})
        log_error("ai", exc.code, exc.message, "", exc.fix)
        return False
    output = _form_first(form, "output", "both")
    if output not in ("whatsapp", "email", "both"):
        output = "both"
    language = _form_first(form, "language", "english")
    if language not in ("english", "bangla", "auto"):
        language = "english"
    include_has_website = _form_first(form, "include_has_website", "") in ("1", "on", "true", "yes")
    WRITER_STATE.update({"notice": "Pitch batch started. Keep this page open and watch the progress.", "error": "", "error_code": ""})
    threading.Thread(target=run_ai_batch, args=(output, language, include_has_website), daemon=True).start()
    return True


def _writer_form_selection(form):
    leads = lead_records()
    if not leads:
        return [], None, "both", "english"
    try:
        lead_index = int(float(str(_form_first(form, "lead", "0")).strip()))
    except (TypeError, ValueError):
        lead_index = 0
    if lead_index < 0 or lead_index >= len(leads):
        lead_index = 0
    output = _form_first(form, "output", "both")
    if output not in ("whatsapp", "email", "both"):
        output = "both"
    language = _form_first(form, "language", "english")
    if language not in ("english", "bangla", "auto"):
        language = "english"
    return leads, leads[lead_index], output, language


def handle_writer_manual(form):
    leads, lead, output, language = _writer_form_selection(form)
    if lead is None:
        WRITER_STATE.update({"notice": "", "error": "No leads are saved yet. Run a search first.", "error_code": "AI_NO_LEADS", "last": None})
        return False
    text = _form_first(form, "manual_reply", "")
    if not text:
        WRITER_STATE.update({
            "notice": "",
            "error": "Paste the AI reply in the manual box first, then click Save manual pitch.",
            "error_code": "AI_MANUAL_EMPTY",
            "last": None,
        })
        log_warning("ai", "AI_MANUAL_EMPTY", "An empty manual AI reply was not saved.", lead["name"], "Paste the reply from the free AI website, then save it.")
        return False
    resolved_language = resolve_pitch_language(lead, language)
    result, followed_format = parse_manual_output(text, output, lead)
    problems = validate_pitch_output(result, output)
    style = style_check_pitch(result, lead)
    result["provider"] = "manual"
    result["provider_label"] = "Manual mode"
    result["quality_note"] = "Check before sending" if problems else ""
    result["style_label"] = style["label"]
    result["style_reasons"] = style["reasons"]
    path = save_pitch_file(lead, result, output, resolved_language, source="Manual paste")
    update_store_after_pitch(lead, path, resolved_language)
    if followed_format:
        notice = f"Manual pitch saved for {lead['name']}. Saved as {path.name}. It is marked as manual."
    else:
        notice = f"The AI reply did not follow the format, so the whole text was saved as the pitch text for {lead['name']}. Saved as {path.name}. It is marked as manual."
    if problems:
        notice += " Check before sending: " + " ".join(problems)
    last = {"lead_index": lead["index"], "slug": lead["slug"], "output": output, "language": resolved_language}
    last.update(result)
    WRITER_STATE.update({"notice": notice, "error": "", "error_code": "", "last": last})
    record_event("info", "ai", "AI_MANUAL_PITCH_CREATED", f"Manual pitch saved for {lead['name']}.", f"Output: {output}; Language: {resolved_language}; Format followed: {'yes' if followed_format else 'no'}")
    return True


def handle_writer_manual_batch(form):
    leads = lead_records()[:10]
    if not leads:
        WRITER_STATE.update({"notice": "", "error": "No leads are saved yet. Run a search first.", "error_code": "AI_NO_LEADS", "last": None})
        return False
    output = _form_first(form, "output", "both")
    if output not in ("whatsapp", "email", "both"):
        output = "both"
    language = _form_first(form, "language", "english")
    if language not in ("english", "bangla", "auto"):
        language = "english"
    text = _form_first(form, "manual_batch_reply", "")
    if not text:
        WRITER_STATE.update({
            "notice": "",
            "error": "Paste the batch AI reply in the manual batch box first, then click Save batch pitches.",
            "error_code": "AI_MANUAL_EMPTY",
            "last": None,
        })
        log_warning("ai", "AI_MANUAL_EMPTY", "An empty manual batch AI reply was not saved.", "", "Paste the batch reply from the free AI website, then save it.")
        return False
    header_pattern = re.compile(r"(?im)^[ \t]*={3,}[ \t]*LEAD[ \t]+(\d+)[ \t]*:[ \t]*(.*?)[ \t]*={3,}[ \t]*$")
    headers = list(header_pattern.finditer(text))
    sections = []
    seen = set()
    for idx, match in enumerate(headers):
        try:
            number = int(match.group(1))
        except ValueError:
            continue
        if number < 1 or number > len(leads) or number in seen:
            continue
        seen.add(number)
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        body = text[match.end():end].strip()
        if body:
            sections.append((number, body))
    if sections:
        saved = 0
        unformatted = 0
        warning_count = 0
        first_last = None
        for number, body in sections:
            lead = leads[number - 1]
            result, followed_format = parse_manual_output(body, output, lead)
            if not followed_format:
                unformatted += 1
            problems = validate_pitch_output(result, output)
            if problems:
                warning_count += 1
            style = style_check_pitch(result, lead)
            result["provider"] = "manual"
            result["provider_label"] = "Manual mode"
            result["quality_note"] = "Check before sending" if problems else ""
            result["style_label"] = style["label"]
            result["style_reasons"] = style["reasons"]
            resolved_language = resolve_pitch_language(lead, language)
            pitch_path = save_pitch_file(lead, result, output, resolved_language, source="Manual batch paste")
            update_store_after_pitch(lead, pitch_path, resolved_language)
            saved += 1
            if first_last is None:
                first_last = {"lead_index": lead["index"], "slug": lead["slug"], "output": output, "language": resolved_language}
                first_last.update(result)
        notice = f"Manual batch saved {saved} pitch{'es' if saved != 1 else ''}."
        if unformatted:
            notice += f" {unformatted} section{'s' if unformatted != 1 else ''} did not follow the format, so the whole section text was saved as the pitch text."
        if warning_count:
            notice += f" {warning_count} saved pitch{'es' if warning_count != 1 else ''} should be checked before sending."
        WRITER_STATE.update({"notice": notice, "error": "", "error_code": "", "last": first_last})
        record_event("info", "ai", "AI_MANUAL_BATCH_CREATED", f"Manual batch saved {saved} pitches.", f"Output: {output}; Language: {language}")
        return True
    lead = leads[0]
    result, followed_format = parse_manual_output(text, output, lead)
    problems = validate_pitch_output(result, output)
    style = style_check_pitch(result, lead)
    result["provider"] = "manual"
    result["provider_label"] = "Manual mode"
    result["quality_note"] = "Check before sending" if problems else ""
    result["style_label"] = style["label"]
    result["style_reasons"] = style["reasons"]
    resolved_language = resolve_pitch_language(lead, language)
    path = save_pitch_file(lead, result, output, resolved_language, source="Manual batch paste")
    update_store_after_pitch(lead, path, resolved_language)
    last = {"lead_index": lead["index"], "slug": lead["slug"], "output": output, "language": language}
    last.update(result)
    notice = f"Lead sections were not found in the pasted reply, so one combined pitch file was saved for {lead['name']}. Saved as {path.name}."
    if not followed_format:
        notice += " The whole pasted text was saved as the pitch text."
    if problems:
        notice += " Check before sending: " + " ".join(problems)
    WRITER_STATE.update({"notice": notice, "error": "", "error_code": "", "last": last})
    record_event("info", "ai", "AI_MANUAL_BATCH_COMBINED", f"Manual batch fallback saved one combined pitch for {lead['name']}.", f"Output: {output}; Language: {language}")
    return True


# ---------------------------------------------------------------- pages

CSS = """
:root{
  color-scheme:dark;
  --bg:#0B0F17; --bg-deep:#060910; --panel:#111826; --panel-2:#151D2E; --panel-3:#0C1320;
  --panel-soft:rgba(21,29,46,.72); --line:rgba(148,184,255,.13); --line-2:rgba(148,184,255,.26);
  --txt:#EDF2FA; --dim:#98A3B7; --faint:#66738A; --acc:#FFB020; --acc-2:#FFCA55; --acc-ink:#1B1303;
  --acc-soft:rgba(255,176,32,.13); --green:#4ADE80; --green-soft:rgba(74,222,128,.11);
  --red:#F87171; --red-soft:rgba(248,113,113,.10); --blue:#7DD3FC; --blue-soft:rgba(125,211,252,.10);
  --violet:#C4B5FD; --shadow:0 18px 44px rgba(0,0,0,.24); --shadow-soft:0 8px 24px rgba(0,0,0,.16);
  --radius:12px; --radius-lg:14px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; color:var(--txt); background-color:var(--bg-deep);
  background-image:
    radial-gradient(880px 480px at 88% -8%, rgba(255,176,32,.075), rgba(255,176,32,0) 64%),
    radial-gradient(760px 560px at -12% 28%, rgba(59,130,246,.055), rgba(59,130,246,0) 62%),
    linear-gradient(rgba(148,184,255,.022) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148,184,255,.022) 1px, transparent 1px),
    linear-gradient(180deg, #0B0F17 0%, #080D15 100%);
  background-size:auto,auto,28px 28px,28px 28px,auto; background-attachment:fixed;
  font-family:ui-sans-system,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
}
::selection{background:rgba(255,176,32,.88); color:#171106}
a{color:var(--acc)}
a:hover{color:var(--acc-2)}
button,input{font:inherit}
:focus-visible{outline:2px solid rgba(255,176,32,.78); outline-offset:2px}
svg.icon{width:18px;height:18px;flex:0 0 auto;stroke-width:1.8}
svg.icon.sm{width:15px;height:15px} svg.icon.lg{width:24px;height:24px}

/* App shell */
.app-shell{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:100vh}
.sidebar{
  position:sticky;top:0;height:100vh;z-index:20;display:flex;flex-direction:column;
  padding:22px 16px 16px;border-right:1px solid var(--line);
  background:linear-gradient(180deg,rgba(20,29,48,.96),rgba(9,14,24,.98));
  box-shadow:16px 0 36px rgba(0,0,0,.12);
}
.side-brand{display:flex;align-items:center;gap:12px;text-decoration:none;padding:2px 4px}
.logoimg{width:46px;height:46px;display:block;filter:drop-shadow(0 7px 16px rgba(255,176,32,.16))}
.wm{font-size:23px;font-weight:780;letter-spacing:-.035em;color:var(--txt);line-height:1;white-space:nowrap}
.wm span{color:var(--acc)}
.tag{color:var(--dim);font-size:12px;margin-top:5px;white-space:nowrap}
.side-label{margin:30px 8px 9px;color:var(--faint);font-size:10.5px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}
.side-nav{display:grid;gap:6px}
.side-link{
  position:relative;display:flex;align-items:center;gap:11px;min-height:42px;padding:9px 11px;
  border:1px solid transparent;border-radius:10px;color:var(--dim);text-decoration:none;
  font-size:13.5px;font-weight:620;transition:background .16s ease,color .16s ease,border-color .16s ease;
}
.side-link .icon{width:19px;height:19px}
.side-link:hover{color:var(--txt);background:rgba(148,184,255,.055);border-color:rgba(148,184,255,.07)}
.side-link.active{color:#FFE1A1;background:linear-gradient(90deg,rgba(255,176,32,.17),rgba(255,176,32,.07));border-color:rgba(255,176,32,.22)}
.side-link.active:before{content:"";position:absolute;left:-16px;top:9px;bottom:9px;width:3px;border-radius:0 3px 3px 0;background:var(--acc)}
.side-link.active .icon{color:var(--acc)}
.side-spacer{flex:1;min-height:24px}
.system-card{border:1px solid var(--line);border-radius:12px;background:rgba(7,11,18,.52);padding:13px;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}
.system-top{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:700;color:var(--txt)}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--faint);flex:0 0 auto;display:inline-block}
.status-dot.ok,.status-dot.running,.status-dot.done{background:var(--green);box-shadow:0 0 0 4px rgba(74,222,128,.10)}
.status-dot.warn,.status-dot.running-state,.status-dot.partial,.status-dot.starting,.status-dot.working{background:var(--acc);box-shadow:0 0 0 4px rgba(255,176,32,.10)}
.status-dot.bad,.status-dot.failed,.status-dot.error{background:var(--red);box-shadow:0 0 0 4px rgba(248,113,113,.10)}
.status-dot.pulse{animation:pulse 2.2s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 3px rgba(74,222,128,.10)}50%{box-shadow:0 0 0 6px rgba(74,222,128,.04)}}
.system-address{margin-top:8px;color:var(--dim);font-size:11.5px;line-height:1.45}
.system-address .mono{color:#C9D4E8}
.side-meta{margin-top:11px;padding:0 3px;color:var(--faint);font-size:11px;line-height:1.55}
.main-shell{min-width:0}
.page-wrap{max-width:1240px;margin:0 auto;padding:30px 34px 28px}
.page-foot{display:flex;justify-content:space-between;gap:18px;margin-top:28px;padding-top:16px;border-top:1px solid rgba(148,184,255,.08);color:var(--faint);font-size:12px;line-height:1.55}
.page-foot b{color:var(--dim)}

/* Page structure and common components */
.page-head{display:flex;align-items:flex-start;justify-content:space-between;gap:22px;margin:2px 0 20px}
.page-head h1{font-size:31px;line-height:1.12;letter-spacing:-.035em;margin:0;font-weight:790}
.page-head p{max-width:720px;color:var(--dim);font-size:14px;line-height:1.65;margin:8px 0 0}
.eyebrow{display:flex;align-items:center;gap:8px;color:var(--acc);font-size:11px;font-weight:760;letter-spacing:.13em;text-transform:uppercase;margin-bottom:9px}
.eyebrow:before{content:"";width:22px;height:1px;background:var(--acc)}
.head-actions{display:flex;align-items:center;gap:9px;flex:0 0 auto;padding-top:28px}
.card,.panel{
  background:linear-gradient(180deg,rgba(255,255,255,.022),rgba(255,255,255,0) 42%),var(--panel);
  border:1px solid var(--line);border-radius:var(--radius-lg);box-shadow:var(--shadow-soft);
}
.card{padding:22px 24px;margin-bottom:18px}
.card h2,.panel h2{margin:0 0 6px;font-size:17px;line-height:1.3;font-weight:700;letter-spacing:-.015em}
.card p,.panel p{color:var(--dim);font-size:13.5px;line-height:1.62;margin:2px 0 8px}
.panel{padding:20px}
.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}
.panel-head h2{margin:0}
.panel-head p{margin:5px 0 0}
.title-with-icon{display:flex;gap:12px;align-items:flex-start}
.icon-medallion{
  width:40px;height:40px;border-radius:11px;display:inline-flex;align-items:center;justify-content:center;
  color:var(--acc);background:var(--acc-soft);border:1px solid rgba(255,176,32,.20);flex:0 0 auto;
}
.icon-medallion.blue{color:var(--blue);background:var(--blue-soft);border-color:rgba(125,211,252,.18)}
.icon-medallion.green{color:var(--green);background:var(--green-soft);border-color:rgba(74,222,128,.18)}
.icon-medallion.red{color:var(--red);background:var(--red-soft);border-color:rgba(248,113,113,.18)}
.icon-medallion.neutral{color:#C7D2E5;background:rgba(148,184,255,.07);border-color:var(--line)}
.btn{
  min-height:40px;display:inline-flex;align-items:center;justify-content:center;gap:8px;
  background:linear-gradient(180deg,var(--acc-2),var(--acc));color:var(--acc-ink);border:1px solid rgba(255,202,85,.55);
  border-radius:10px;padding:8px 16px;font-weight:740;font-size:13.5px;cursor:pointer;
  text-decoration:none;white-space:nowrap;box-shadow:0 8px 20px rgba(255,176,32,.13),inset 0 1px 0 rgba(255,255,255,.28);
  transition:transform .14s ease,filter .14s ease,background .14s ease,border-color .14s ease;
}
.btn:hover{filter:brightness(1.055);color:var(--acc-ink)}
.btn:active{transform:translateY(1px)}
.btn.ghost,.btn.secondary{background:rgba(148,184,255,.045);color:var(--txt);border:1px solid var(--line-2);box-shadow:none;font-weight:640}
.btn.ghost:hover,.btn.secondary:hover{background:rgba(148,184,255,.085);color:var(--txt);border-color:rgba(148,184,255,.36)}
.btn.danger-ghost{background:rgba(248,113,113,.045);color:#FCA5A5;border:1px solid rgba(248,113,113,.28);box-shadow:none;font-weight:640}
.btn.danger-ghost:hover{background:rgba(248,113,113,.10);color:#FECACA}
.btn.small{min-height:34px;padding:6px 12px;font-size:12.5px;border-radius:9px}
.btn:disabled{opacity:.48;cursor:wait;transform:none}
.dangerbtn{min-height:38px;background:rgba(248,113,113,.055);color:#FCA5A5;border:1px solid rgba(248,113,113,.34);border-radius:10px;padding:8px 14px;font-weight:680;cursor:pointer}
.dangerbtn:hover{background:rgba(248,113,113,.11)}
.pill,.status-pill{
  display:inline-flex;align-items:center;gap:7px;min-height:25px;padding:4px 10px;border-radius:999px;
  font-size:11.5px;font-weight:700;border:1px solid var(--line-2);color:var(--dim);background:rgba(148,184,255,.045);white-space:nowrap;
}
.pill .status-dot,.status-pill .status-dot{width:6px;height:6px;box-shadow:none}
.pill.running,.status-pill.warn,.pill.partial{color:#FFD58A;border-color:rgba(255,176,32,.38);background:rgba(255,176,32,.09)}
.pill.done,.status-pill.ok{color:#BBF7D0;border-color:rgba(74,222,128,.34);background:rgba(74,222,128,.08)}
.pill.failed,.status-pill.error{color:#FECACA;border-color:rgba(248,113,113,.36);background:rgba(248,113,113,.08)}
.status-pill.info{color:#BAE6FD;border-color:rgba(125,211,252,.30);background:rgba(125,211,252,.07)}
.callout,.notebox,.errbox{
  border:1px solid var(--line);border-radius:11px;padding:12px 14px;font-size:13.5px;line-height:1.58;
  background:rgba(125,211,252,.055);color:#C9D9EA;
}
.callout{display:flex;gap:10px;align-items:flex-start}
.callout .icon{margin-top:1px;color:var(--blue)}
.callout.warn{background:rgba(255,176,32,.065);border-color:rgba(255,176,32,.24);color:#E8DCC2}.callout.warn .icon{color:var(--acc)}
.callout.error,.errbox{background:rgba(248,113,113,.065);border-color:rgba(248,113,113,.30);color:#FECACA}
.callout.success{background:rgba(74,222,128,.06);border-color:rgba(74,222,128,.25);color:#D1FAE5}.callout.success .icon{color:var(--green)}
.errbox{border-style:solid}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;font-size:12px;word-break:break-word}
.oktext{color:var(--green);font-weight:700}.badtext{color:var(--red);font-weight:700}.warntext{color:var(--acc);font-weight:700}
.switchchip{display:inline-flex;align-items:center;margin-left:8px;padding:3px 8px;border-radius:999px;background:rgba(255,176,32,.13);color:#FFD58A;font-size:10.5px;font-weight:760;vertical-align:2px}

/* Forms */
label{display:block;font-size:11px;color:var(--dim);margin:0 0 7px;text-transform:uppercase;letter-spacing:.105em;font-weight:700}
input[type=text],input[type=number],input[type=search],input[type=password],input[type=email],input[type=url],select,textarea{
  width:100%;min-height:44px;background:#0A111E;border:1px solid var(--line);border-radius:10px;color:var(--txt);
  padding:10px 12px;font-size:14.5px;outline:none;box-shadow:inset 0 1px 0 rgba(255,255,255,.018);
  transition:border-color .15s ease,box-shadow .15s ease,background .15s ease;
}
textarea{line-height:1.6;resize:vertical}
select{appearance:auto}
input::placeholder,textarea::placeholder{color:#5E6B82}
input:hover,select:hover,textarea:hover{border-color:rgba(148,184,255,.24)}
input:focus,select:focus,textarea:focus{border-color:rgba(255,176,32,.62);box-shadow:0 0 0 3px rgba(255,176,32,.12);background:#0B1322}
.field-control{position:relative}
.field-control .icon{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:17px;height:17px;color:var(--faint);pointer-events:none}
.field-control input{padding-left:38px}
.field-control:focus-within .icon{color:var(--acc)}
input:invalid:not(:placeholder-shown){border-color:rgba(248,113,113,.55)}

/* Settings and Writer */
.settings-fields{display:grid;grid-template-columns:repeat(auto-fill,minmax(265px,1fr));gap:12px;max-height:560px;overflow:auto;padding:2px 4px 2px 2px}
.field-card{border:1px solid rgba(148,184,255,.10);border-radius:11px;background:rgba(7,11,18,.34);padding:12px;min-width:0}
.field-card label{margin-bottom:6px;text-transform:none;letter-spacing:0;font-size:12px;color:#C9D4E8;word-break:break-word}
.field-card input{height:40px;font-size:13.5px}
.field-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center}
.field-help{color:var(--faint);font-size:11.5px;line-height:1.5;margin-top:7px}
.badge{display:inline-flex;align-items:center;min-height:21px;padding:2px 7px;border-radius:999px;border:1px solid var(--line);background:rgba(148,184,255,.05);color:var(--dim);font-size:10.5px;font-weight:720}
.badge.required{color:#FFD58A;border-color:rgba(255,176,32,.30);background:rgba(255,176,32,.08)}
.badge.secret{color:#FCA5A5;border-color:rgba(248,113,113,.26);background:rgba(248,113,113,.06)}
.badge.auto{color:#BBF7D0;border-color:rgba(74,222,128,.25);background:rgba(74,222,128,.06)}
.settings-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
.settings-summary{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.config-list{display:grid;gap:9px;margin-top:14px}
.config-row{display:flex;align-items:center;gap:12px;border:1px solid rgba(148,184,255,.10);border-radius:11px;background:rgba(7,11,18,.34);padding:11px 12px}
.config-row.ok{border-color:rgba(74,222,128,.24)}
.config-row.warn{border-color:rgba(255,176,32,.28)}
.config-symbol{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex:0 0 auto;background:rgba(148,184,255,.06);color:var(--dim)}
.config-row.ok .config-symbol{background:rgba(74,222,128,.10);color:var(--green)}
.config-row.warn .config-symbol{background:rgba(255,176,32,.10);color:var(--acc)}
.config-symbol .icon{width:17px;height:17px}
.config-main{flex:1;min-width:0}
.config-name{font-weight:720;font-size:13.5px;color:var(--txt)}
.config-detail{color:var(--dim);font-size:12.5px;line-height:1.5;margin-top:2px;overflow-wrap:anywhere}
.guide-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px;align-items:stretch}
.guide-card{padding:19px;display:flex;flex-direction:column}
.guide-steps{margin:11px 0 0;padding-left:20px;color:var(--dim);font-size:13.5px;line-height:1.65}
.guide-steps li{margin:3px 0}
.guide-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto;padding-top:15px}
.manual-text{min-height:170px;font-size:13.5px}
.manual-instruction{min-height:190px;font-size:12.5px}
.quick-links{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
@media (max-width:680px){.config-row{align-items:flex-start;flex-wrap:wrap}.config-main{flex-basis:calc(100% - 46px)}}
.writer-grid{display:grid;grid-template-columns:minmax(300px,390px) minmax(0,1fr);gap:16px;align-items:start}
.writer-controls{display:grid;gap:14px}
.writer-actions{display:flex;gap:9px;flex-wrap:wrap}
.pitch-section{margin-bottom:16px}
.pitch-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px}
.pitch-head h3{margin:0;font-size:14.5px}
.pitch-count{color:var(--faint);font-size:11.5px;white-space:nowrap}
textarea.pitch-text{min-height:150px;font-size:14px}
textarea.email-body{min-height:250px}
input.subject-input{font-weight:650}
.note-preview{max-height:190px;overflow:auto;white-space:pre-wrap;color:var(--dim);font-size:12.5px;line-height:1.6;background:#070B12;border:1px solid rgba(148,184,255,.09);border-radius:10px;padding:11px}
.pitch-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:720;background:rgba(74,222,128,.10);color:#BBF7D0;border:1px solid rgba(74,222,128,.22)}
.pitch-chip .icon{width:13px;height:13px}
.pitch-chip.no{background:rgba(148,184,255,.045);color:var(--faint);border-color:rgba(148,184,255,.09)}
.qual-chip{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:720;background:rgba(255,176,32,.10);color:#FDE68A;border:1px solid rgba(255,176,32,.25);white-space:nowrap}
.qual-chip.has_website{background:rgba(74,222,128,.10);color:#BBF7D0;border-color:rgba(74,222,128,.22)}
.qual-chip.website_dead{background:rgba(248,113,113,.10);color:#FECACA;border-color:rgba(248,113,113,.25)}
.qual-chip.unknown{background:rgba(148,184,255,.045);color:var(--faint);border-color:rgba(148,184,255,.09)}
.outcome-form{display:flex;gap:6px;align-items:center}
.outcome-form select{max-width:130px}
@media (max-width:900px){.writer-grid{grid-template-columns:1fr}.settings-fields{max-height:none}}

/* Run page */
.journey-panel{padding:18px 22px 16px;margin-bottom:14px;overflow:hidden}
.journey-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:8px}
.journey-head h2{font-size:16px;margin:0}
.journey-head p{margin:4px 0 0}
.journey{position:relative;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));padding:12px 2px 2px}
.journey:before{content:"";position:absolute;left:10%;right:10%;top:30px;height:1px;background:linear-gradient(90deg,rgba(255,176,32,.08),rgba(255,176,32,.42),rgba(148,184,255,.20));}
.journey-step{position:relative;text-align:center;min-width:0;padding:0 5px}
.journey-icon{position:relative;z-index:1;width:38px;height:38px;margin:0 auto;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#0D1524;border:1px solid rgba(255,176,32,.38);color:var(--acc);box-shadow:0 0 0 5px var(--panel)}
.journey-icon .icon{width:18px;height:18px}
.journey-label{margin-top:8px;font-size:12.5px;font-weight:700;color:var(--txt)}
.journey-sub{margin-top:2px;font-size:11px;color:var(--faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.metric-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:7px 0;margin-bottom:14px;overflow:hidden}
.metric{display:flex;align-items:center;gap:12px;padding:11px 18px;min-width:0}
.metric + .metric{border-left:1px solid rgba(148,184,255,.09)}
.metric .icon-medallion{width:36px;height:36px;border-radius:10px}
.metric .num{font-size:22px;font-weight:790;color:var(--txt);line-height:1;font-variant-numeric:tabular-nums}
.metric .lab{color:var(--faint);font-size:10.5px;margin-top:5px;text-transform:uppercase;letter-spacing:.105em;font-weight:700;white-space:nowrap}
.command-panel{padding:21px 22px;margin-bottom:14px}
.command-form{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1.12fr) minmax(146px,.55fr) auto;gap:14px;align-items:end}
.command-form .btn{height:44px;min-width:122px;margin:0}
.form-note{margin-top:13px}
.console-panel{padding:0;overflow:hidden;margin-bottom:0}
.console-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:15px 18px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.012)}
.console-title{display:flex;align-items:center;gap:10px;font-weight:730;font-size:14px}
.console-title .icon{color:var(--acc)}
.console-meta{display:flex;align-items:center;gap:10px;color:var(--dim);font-size:12.5px;flex-wrap:wrap;justify-content:flex-end}
.console-notes{padding:0 16px}
.console-notes .callout{margin-top:14px}
pre.log{
  background:#05080E;border:0;border-top:1px solid rgba(148,184,255,.07);border-radius:0;
  padding:14px 16px;white-space:pre-wrap;font-size:12px;line-height:1.65;max-height:300px;overflow:auto;
  color:#C7D0E0;min-height:74px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;margin:0;
}
.console-foot{padding:13px 16px;border-top:1px solid var(--line);display:flex;justify-content:flex-end}
.console-foot:empty{display:none;padding:0;border:0}

/* Tables and Leads */
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
.search-box{position:relative;width:min(340px,100%)}
.search-box .icon{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:17px;height:17px;color:var(--faint)}
.search-box input{height:40px;padding-left:37px;font-size:13.5px}
.table-shell{border:1px solid var(--line);border-radius:12px;overflow:auto;background:rgba(9,14,24,.42);max-height:72vh}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13.5px;min-width:820px}
th,td{padding:11px 13px;border-bottom:1px solid rgba(148,184,255,.07);text-align:left;vertical-align:top;line-height:1.45}
thead th{position:sticky;top:0;z-index:2;background:#0D1626;color:#AAB6CA;font-size:10.8px;text-transform:uppercase;letter-spacing:.09em;font-weight:760;box-shadow:0 1px 0 var(--line)}
tbody tr{transition:background .12s ease} tbody tr:hover td{background:rgba(148,184,255,.035)}
tbody tr:last-child td{border-bottom:0}
td:first-child{font-weight:680;color:var(--txt)}
td a{color:#FFCA55;text-decoration:none}
td a .icon{width:13px;height:13px;margin-left:4px;vertical-align:-2px}
td a:hover{text-decoration:underline}
.phone-cell{font-variant-numeric:tabular-nums;white-space:nowrap}
.note-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:720;background:rgba(255,176,32,.11);color:#FFD58A;border:1px solid rgba(255,176,32,.20)}
.note-chip .icon{width:13px;height:13px}
.note-chip.no{background:rgba(148,184,255,.045);color:var(--faint);border-color:rgba(148,184,255,.09)}
.lead-count-note{color:var(--faint);font-size:12px;margin-top:10px}
.empty-state{text-align:center;padding:38px 22px 34px}
.empty-mark{width:82px;height:82px;margin:0 auto 17px;border-radius:24px;display:flex;align-items:center;justify-content:center;background:rgba(255,176,32,.07);border:1px solid rgba(255,176,32,.16)}
.empty-mark img{width:58px;height:58px}
.empty-state h2{font-size:21px;margin:0 0 8px}
.empty-state p{max-width:560px;margin:0 auto 18px}

/* Apps */
.apps-toolbar{padding:18px 20px;margin-bottom:16px}
.batch-summary{margin-top:14px}
.app-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(325px,1fr));gap:16px;align-items:stretch}
.appcard{
  background:linear-gradient(180deg,rgba(255,255,255,.022),rgba(255,255,255,0) 44%),var(--panel);
  border:1px solid var(--line);border-radius:var(--radius-lg);padding:18px;box-shadow:var(--shadow-soft);
  display:flex;flex-direction:column;min-width:0;
}
.app-head{display:flex;align-items:flex-start;gap:12px}
.app-head-main{min-width:0;flex:1}
.appcard h3{margin:0;font-size:15.5px;font-weight:720;line-height:1.25}
.app-purpose{color:var(--dim);font-size:13px;line-height:1.55;margin:11px 0 13px}
.app-icon{width:43px;height:43px;border-radius:11px}
.app-icon.mail{color:#7DD3FC;background:rgba(125,211,252,.10);border-color:rgba(125,211,252,.20)}
.app-icon.chat{color:#6EE7B7;background:rgba(52,211,153,.10);border-color:rgba(52,211,153,.20)}
.app-icon.calendar{color:#FFCA55;background:rgba(255,176,32,.11);border-color:rgba(255,176,32,.22)}
.app-icon.users{color:#67E8F9;background:rgba(103,232,249,.09);border-color:rgba(103,232,249,.19)}
.app-icon.pen{color:#FDA4AF;background:rgba(251,113,133,.09);border-color:rgba(251,113,133,.19)}
.app-address{display:flex;align-items:center;gap:8px;border:1px solid rgba(148,184,255,.10);background:#0A111E;border-radius:10px;padding:9px 10px;min-width:0}
.app-address .icon{width:15px;height:15px;color:var(--faint)}
.app-address a{color:#FFCA55;text-decoration:none;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.app-status{display:flex;gap:9px;align-items:flex-start;margin-top:13px;color:var(--dim);font-size:12.8px;line-height:1.5}
.app-status .status-dot{margin-top:5px}
.app-callout{display:none;margin-top:11px;padding:10px 11px;border-radius:10px;font-size:12.5px;line-height:1.52;border:1px solid rgba(255,176,32,.23);background:rgba(255,176,32,.06);color:#E8DCC2}
.app-callout.show{display:block}
.app-callout.error{border-color:rgba(248,113,113,.28);background:rgba(248,113,113,.06);color:#FECACA}
.app-actions{display:flex;gap:8px;margin-top:15px;flex-wrap:wrap}
.app-actions form{display:inline-flex;margin:0}
.app-output{margin-top:14px;border:1px solid rgba(148,184,255,.10);border-radius:10px;background:#070B12;overflow:hidden}
.app-output summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:8px;padding:9px 11px;color:var(--dim);font-size:12px;font-weight:680}
.app-output summary::-webkit-details-marker{display:none}
.app-output summary:hover{color:var(--txt)}
.app-output summary .icon{width:15px;height:15px;color:var(--acc)}
.app-output summary span{margin-left:auto;color:var(--faint);font-weight:560}
.app-output pre.log{max-height:155px;min-height:44px;border-top:1px solid rgba(148,184,255,.08);font-size:11.5px}

/* Health */
.health-hero{display:flex;align-items:center;gap:19px;padding:21px 22px;margin-bottom:16px;overflow:hidden;position:relative}
.health-hero:after{content:"";position:absolute;right:-70px;top:-110px;width:250px;height:250px;border-radius:50%;background:rgba(255,176,32,.055);pointer-events:none}
.health-ring{position:relative;width:78px;height:78px;border-radius:50%;display:grid;place-items:center;flex:0 0 auto;background:conic-gradient(var(--green) 0 84%,rgba(148,184,255,.13) 84% 100%)}
.health-ring.warn{background:conic-gradient(var(--acc) 0 68%,rgba(148,184,255,.13) 68% 100%)}
.health-ring.error{background:conic-gradient(var(--red) 0 58%,rgba(148,184,255,.13) 58% 100%)}
.health-ring-inner{width:64px;height:64px;border-radius:50%;background:#101827;display:flex;align-items:center;justify-content:center;color:var(--green)}
.health-ring.warn .health-ring-inner{color:var(--acc)} .health-ring.error .health-ring-inner{color:var(--red)}
.health-hero-main{flex:1;min-width:0;position:relative;z-index:1}
.health-hero h2{font-size:21px;margin:0 0 5px}
.health-facts{display:flex;gap:8px;flex-wrap:wrap;margin-top:11px}
.fact-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid var(--line);border-radius:999px;background:rgba(7,11,18,.38);color:var(--dim);font-size:11.5px}
.fact-chip b{color:var(--txt)}
.check-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(295px,1fr));gap:13px;margin-bottom:16px}
.check-card{padding:16px;min-width:0}
.check-head{display:flex;align-items:center;gap:11px;margin-bottom:10px}
.check-head h3{font-size:14px;margin:0;flex:1;line-height:1.35}
.check-detail{color:var(--dim);font-size:12.8px;line-height:1.55;margin:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.fix-line{margin-top:10px;padding:9px 10px;border-left:3px solid var(--acc);background:rgba(255,176,32,.055);color:#E8DCC2;font-size:12.5px;line-height:1.5;border-radius:0 8px 8px 0}
.ports-wrap .table-shell{max-height:none}
.port-address{font-weight:700}
.dep-details{margin-top:7px;color:var(--dim);font-size:12px}
.dep-details summary{cursor:pointer;color:var(--faint);font-weight:650}
.dep-details ul{margin:7px 0 0;padding-left:17px;line-height:1.65}
.state-message{color:var(--dim);font-size:12.5px;line-height:1.5;margin-top:5px}
.state-fix{color:#E8DCC2;font-size:12.5px;line-height:1.5;margin-top:5px}
.error-list{display:grid;gap:10px}
.error-item{display:grid;grid-template-columns:4px minmax(0,1fr);gap:12px;padding:13px 14px;border:1px solid var(--line);border-radius:11px;background:rgba(7,11,18,.34)}
.error-rail{border-radius:99px;background:var(--acc)} .error-item.error .error-rail{background:var(--red)} .error-item.warning .error-rail{background:var(--acc)}
.error-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;color:var(--faint);font-size:11.5px;margin-bottom:5px}
.error-item p{margin:0;color:#DCE5F2;font-size:13px}
.error-item details{margin-top:7px;color:var(--dim);font-size:12px}
.error-item summary{cursor:pointer;color:var(--faint);font-weight:650}
.log-files{margin-top:12px;border:1px solid var(--line);border-radius:10px;background:rgba(7,11,18,.34)}
.log-files summary{cursor:pointer;padding:10px 12px;color:var(--dim);font-size:12.5px;font-weight:680}
.log-files div{padding:0 12px 12px;color:var(--dim);font-size:12px;line-height:1.7}
.health-actions{display:flex;gap:9px;flex-wrap:wrap;position:relative;z-index:1}

/* Scrollbars */
*{scrollbar-width:thin;scrollbar-color:rgba(148,184,255,.28) transparent}
*::-webkit-scrollbar{width:9px;height:9px} *::-webkit-scrollbar-thumb{background:rgba(148,184,255,.24);border-radius:99px;border:2px solid transparent;background-clip:padding-box}
*::-webkit-scrollbar-track{background:transparent}

/* Legacy layout helpers still used by error content */
.row{display:flex;gap:14px}.row>div{flex:1}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:16px}
.healthgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.healthitem{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px}
.healthitem h3{margin:0 0 6px;font-size:14px}.healthitem p{margin:4px 0;color:var(--dim)}
.empty{text-align:center;padding:16px 0 8px}.empty img{width:76px;height:76px}.empty h2{margin-top:14px}
.foot{color:var(--faint);font-size:12px;margin-top:26px;line-height:1.6}.foot b{color:var(--dim)}

@media (max-width:1050px){
  .command-form{grid-template-columns:1fr 1fr}.command-form .field-max{max-width:220px}.command-form .btn{width:fit-content}
  .app-grid{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
}
@media (max-width:900px){
  .app-shell{display:block}
  .sidebar{position:relative;height:auto;padding:14px 14px 12px;border-right:0;border-bottom:1px solid var(--line);box-shadow:none}
  .side-brand{padding:0}
  .logoimg{width:40px;height:40px}.wm{font-size:21px}.tag{font-size:11.5px}
  .side-label{display:none}
  .side-nav{grid-template-columns:repeat(3,minmax(0,1fr));margin-top:14px;gap:7px}
  .side-link{flex-direction:column;justify-content:center;gap:5px;min-height:52px;padding:7px 3px;font-size:11.5px;text-align:center}
  .side-link.active:before{left:10px;right:10px;top:auto;bottom:-1px;width:auto;height:3px;border-radius:3px 3px 0 0}
  .side-spacer{display:none}
  .system-card{margin-top:12px;display:flex;align-items:center;gap:12px;padding:10px 12px}
  .system-address{margin:0}.side-meta{display:none}
  .page-wrap{padding:21px 15px 24px}
  .page-head{align-items:flex-start;flex-direction:column;gap:13px;margin-bottom:16px}
  .head-actions{padding-top:0}
  .page-head h1{font-size:27px}
  .head-actions{width:100%;flex-wrap:wrap}
  .card{padding:19px 17px}
}
@media (max-width:680px){
  .metric-strip{grid-template-columns:repeat(2,minmax(0,1fr));padding:4px 0}
  .metric{padding:11px 13px}.metric + .metric{border-left:0}.metric:nth-child(even){border-left:1px solid rgba(148,184,255,.09)}
  .metric:nth-child(n+3){border-top:1px solid rgba(148,184,255,.09)}
  .journey-panel{padding:15px 9px 12px}.journey{gap:0;padding-top:9px}.journey:before{top:25px}
  .journey-icon{width:34px;height:34px}.journey-label{font-size:10.8px}.journey-sub{display:none}
  .command-form{grid-template-columns:1fr}.command-form .field-max{max-width:none}.command-form .btn{width:100%}
  .console-head{align-items:flex-start;flex-direction:column}.console-meta{justify-content:flex-start}
  .app-grid{grid-template-columns:1fr}
  .health-hero{align-items:flex-start;flex-direction:column}
  .health-actions{width:100%}.health-actions .btn{flex:1}
  .page-foot{flex-direction:column;gap:4px}
  .toolbar{align-items:stretch;flex-direction:column}.search-box{width:100%}
  .system-card{align-items:flex-start;flex-direction:column;gap:5px}
}
@media (prefers-reduced-motion:reduce){
  *,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.01ms!important}
}
"""


ICON_PATHS = {
    "run": '<path d="M7 4.8v14.4c0 .8.9 1.3 1.6.9L20 12.9a1.05 1.05 0 0 0 0-1.8L8.6 3.9c-.7-.4-1.6.1-1.6.9Z" fill="currentColor" stroke="none"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20.2 20.2-4-4"/>',
    "pin": '<path d="M12 21s-6.8-5.35-6.8-10.2a6.8 6.8 0 1 1 13.6 0C18.8 15.65 12 21 12 21Z"/><circle cx="12" cy="10.6" r="2.35"/>',
    "briefcase": '<rect x="3" y="7.5" width="18" height="12" rx="2"/><path d="M9 7.5V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.5"/><path d="M3 12.5h18"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.6-3 2.7-4.5 5.5-4.5s4.9 1.5 5.5 4.5"/><path d="M15.8 5.3a3.2 3.2 0 0 1 0 5.6"/><path d="M17.4 14.8c1.7.6 2.7 1.9 3.1 4.2"/>',
    "grid": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    "activity": '<path d="M3 12h4l2.2-6.2 4.1 12.4 2.3-6.2H21"/>',
    "database": '<ellipse cx="12" cy="5.2" rx="7" ry="3"/><path d="M5 5.2v13.6c0 1.7 3.1 3 7 3s7-1.3 7-3V5.2"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7.5 8 6 8-6"/>',
    "message": '<path d="M21 11.5c0 4.7-4 8.5-9 8.5-1 0-2-.15-2.9-.45L4 21l1.55-3.65A8.6 8.6 0 0 1 3 11.5C3 6.8 7 3 12 3s9 3.8 9 8.5Z"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="16" rx="2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/><path d="m9 15.2 2 2 4-4.2"/>',
    "pen": '<path d="m14.6 5.4 4 4L8.2 19.8H4.2v-4Z"/><path d="m12.7 7.3 4 4"/><path d="M4 21.2h16"/>',
    "check": '<path d="m4.8 12.6 4.4 4.4L19.2 7"/>',
    "alert": '<path d="M12 4 2.9 20h18.2Z"/><path d="M12 10v4.2"/><path d="M12 17.3h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.8h.01"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M20 14v5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19V6a1.5 1.5 0 0 1 1.5-1.5H10"/>',
    "play": '<path d="M7 4.8v14.4c0 .8.9 1.3 1.6.9L20 12.9a1.05 1.05 0 0 0 0-1.8L8.6 3.9c-.7-.4-1.6.1-1.6.9Z" fill="currentColor" stroke="none"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/>',
    "download": '<path d="M12 4v11"/><path d="m7.8 11.2 4.2 4.2 4.2-4.2"/><path d="M4.5 20h15"/>',
    "file": '<path d="M6 3h8l4 4v14H6Z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3"/><path d="M12.5 15H17"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a12.5 12.5 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16.5 16.5 0 0 1 3 6a2 2 0 0 1 2-2Z"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14.5 14.5 0 0 1 0 18"/><path d="M12 3a14.5 14.5 0 0 0 0 18"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.35-5.65"/><path d="M20 3v4.2h-4.2"/>',
    "shield": '<path d="M12 3 5 5.8v5.4c0 4.6 2.9 7.7 7 9.3 4.1-1.6 7-4.7 7-9.3V5.8Z"/><path d="m9 11.6 2.1 2.1 4.3-4.5"/>',
    "server": '<rect x="4" y="4" width="16" height="7" rx="1.5"/><rect x="4" y="13" width="16" height="7" rx="1.5"/><path d="M7.5 7.5h.01M7.5 16.5h.01"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    "book": '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3Z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
    "hash": '<path d="M9 4 7 20M17 4l-2 16M4.5 9h17M3.5 15h17"/>',
    "minus": '<path d="M5 12h14"/>',
    "settings": '<path d="M5 7h8M19 7h0M5 12h2M13 12h6M5 17h10M19 17h0"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
    "spark": '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/><circle cx="12" cy="12" r="3.2"/>',
}


def icon(name, css_class=""):
    path = ICON_PATHS.get(name, ICON_PATHS["info"])
    cls = ("icon " + css_class).strip()
    return (
        f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{path}</svg>'
    )


APP_ICONS = {
    "listmonk": ("mail", "mail"),
    "chatwoot": ("message", "chat"),
    "caldiy": ("calendar", "calendar"),
    "twenty": ("users", "users"),
    "documenso": ("pen", "pen"),
}


def shell(active, body):
    entries = [
        ("run", "Run", "/", "search"),
        ("leads", "Leads", "/leads", "users"),
        ("writer", "Writer", "/writer", "pen"),
        ("apps", "Apps", "/apps", "grid"),
        ("settings", "Settings", "/settings", "settings"),
        ("guide", "Guide", "/guide", "book"),
        ("reports", "Reports", "/reports", "file"),
        ("health", "Health", "/health", "activity"),
    ]
    nav = ""
    for key, label, href, icon_name in entries:
        cls = "side-link active" if key == active else "side-link"
        current = ' aria-current="page"' if key == active else ""
        nav += f'<a class="{cls}" href="{href}"{current}>{icon(icon_name)}<span>{label}</span></a>'
    address = html.escape(SERVER_STATE.get("url", ""))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>LeadForge</title>
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<style>{CSS}</style></head>
<body>
<div class="app-shell">
<aside class="sidebar">
<a class="side-brand" href="/" aria-label="LeadForge home"><img class="logoimg" src="/logo.svg" alt="LeadForge logo">
<div><div class="wm">Lead<span>Forge</span></div>
<div class="tag">Find clients. Forge deals.</div></div></a>
<div class="side-label">Pipeline</div>
<nav class="side-nav" aria-label="LeadForge pages">{nav}</nav>
<div class="side-spacer"></div>
<div class="system-card">
<div class="system-top"><span class="status-dot ok pulse"></span><span>Local system online</span></div>
<div class="system-address">Dashboard address<br><span class="mono">{address}</span></div>
</div>
<div class="side-meta">LeadForge Interface v6<br>Private to this PC</div>
</aside>
<main class="main-shell"><div class="page-wrap">
{body}
<footer class="page-foot"><span><b>LeadForge</b> - your client pipeline on this PC.</span><span>Nothing is sent to a client until you send it yourself from the tools.</span></footer>
</div></main>
</div>
</body></html>"""

def pipeline_stats():
    """Counts for the Run page stat tiles, from the latest results."""
    fieldnames, rows = _read_results(LATEST_CSV)
    total = len(rows)
    with_phone = 0
    with_website = 0
    if rows:
        lower = {fn.lower().strip(): fn for fn in fieldnames if fn}

        def find(keys):
            for k in keys:
                if k in lower:
                    return lower[k]
            return None

        phone_key = find(["phone", "phone_number", "telephone", "mobile"])
        site_key = find(["website", "site", "url", "web"])
        for r in rows:
            if phone_key and (r.get(phone_key) or "").strip():
                with_phone += 1
            if site_key and (r.get(site_key) or "").strip():
                with_website += 1
    notes = 0
    if NOTES_DIR.exists():
        notes = len(list(NOTES_DIR.glob("*.md")))
    return total, with_phone, with_website, notes


def run_page():
    with JOB_LOCK:
        state = JOB["state"]
        notice = JOB["notice"]
        location = JOB["location"]
        business_type = JOB["business_type"]
        max_results = JOB["max_results"]
    notice_html = (
        f'<div class="callout warn form-note">{icon("alert")}<div>{html.escape(notice)}</div></div>'
        if notice else ""
    )
    disabled = " disabled" if state == "running" else ""
    total, with_phone, with_website, notes_ready = pipeline_stats()
    step_data = [
        ("search", "Find", "Google Maps"),
        ("book", "Understand", "Website notes"),
        ("mail", "Message", "Campaigns"),
        ("users", "Track", "CRM"),
        ("pen", "Close", "Agreements"),
    ]
    steps_html = ""
    for icon_name, label, sub in step_data:
        steps_html += (
            f'<div class="journey-step"><div class="journey-icon">{icon(icon_name)}</div>'
            f'<div class="journey-label">{label}</div><div class="journey-sub">{sub}</div></div>'
        )
    body = f"""
<div class="page-head">
<div>
<div class="eyebrow">Command center</div>
<h1>Find your next clients</h1>
<p>Search one market at a time. LeadForge finds the businesses, reads their websites, and prepares useful notes for a personal pitch.</p>
</div>
<div class="head-actions"><span class="status-pill ok"><span class="status-dot ok"></span>Local only</span></div>
</div>

<section class="panel journey-panel" aria-label="Pipeline steps">
<div class="journey-head"><div><h2>Your pipeline journey</h2><p>Five connected stages, from discovery to a signed deal.</p></div><span class="status-pill info">5 stages</span></div>
<div class="journey">{steps_html}</div>
</section>

<section class="panel metric-strip" aria-label="Latest pipeline totals">
<div class="metric"><div class="icon-medallion">{icon("users")}</div><div><div class="num">{total}</div><div class="lab">Leads found</div></div></div>
<div class="metric"><div class="icon-medallion blue">{icon("phone")}</div><div><div class="num">{with_phone}</div><div class="lab">With phone</div></div></div>
<div class="metric"><div class="icon-medallion green">{icon("globe")}</div><div><div class="num">{with_website}</div><div class="lab">With website</div></div></div>
<div class="metric"><div class="icon-medallion">{icon("file")}</div><div><div class="num">{notes_ready}</div><div class="lab">Notes ready</div></div></div>
</section>

<section class="panel command-panel">
<div class="panel-head">
<div class="title-with-icon"><div class="icon-medallion">{icon("search")}</div><div><h2>Run a lead search</h2><p>Choose the place and the kind of business. The website reader runs after the finder finishes.</p></div></div>
</div>
<form method="post" action="/run" class="command-form">
<div><label for="location">Location</label><div class="field-control">{icon("pin")}<input id="location" type="text" name="location" placeholder="e.g. Halishahar" value="{html.escape(location)}" required></div></div>
<div><label for="business_type">Business type</label><div class="field-control">{icon("briefcase")}<input id="business_type" type="text" name="business_type" placeholder="e.g. dentists" value="{html.escape(business_type)}" required></div></div>
<div class="field-max"><label for="max_results">Max results</label><div class="field-control">{icon("hash")}<input id="max_results" type="number" name="max_results" value="{int(max_results)}" min="1" max="200"></div></div>
<div><label>Mode</label><div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px"><label class="check-row" style="margin:0"><input type="radio" name="mode" value="full" checked><span>Full pipeline: find, read, qualify, write pitches, report</span></label><label class="check-row" style="margin:0"><input type="radio" name="mode" value="find"><span>Find leads only</span></label></div></div>
<button class="btn" type="submit"{disabled}>{icon("play", "sm")}Run search</button>
</form>
{notice_html}
</section>

<section class="panel console-panel" aria-label="Pipeline activity">
<div class="console-head">
<div class="console-title">{icon("terminal")}<span>Activity console</span></div>
<div class="console-meta"><span class="pill {html.escape(state)}" id="jobpill">{html.escape(state)}</span><span id="jobstep"></span><span id="jobleads"></span><span id="jobelapsed"></span></div>
</div>
<div class="console-notes"><div id="joberror"></div><div id="jobresult"></div></div>
<pre class="log" id="joblog">No job yet. Fill the form above and click Run search.</pre>
<div class="console-foot" id="jobdone"></div>
</section>
<script>
function lfEscape(value) {{
  return String(value || '').replace(/[&<>"']/g, function(ch) {{
    return {{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}}[ch];
  }});
}}
function lfElapsed(startedAt, state) {{
  if (!startedAt || state !== 'running') return '';
  const start = Date.parse(startedAt);
  if (!start) return '';
  let seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const hours = Math.floor(seconds / 3600); seconds = seconds % 3600;
  const minutes = Math.floor(seconds / 60); const rest = seconds % 60;
  const two = function(n) {{ return String(n).padStart(2, '0'); }};
  return 'Elapsed ' + (hours ? hours + ':' : '') + two(minutes) + ':' + two(rest);
}}
async function poll() {{
  try {{
    const s = await (await fetch('/status')).json();
    const pill = document.getElementById('jobpill');
    pill.textContent = s.state || 'idle';
    pill.className = 'pill ' + (s.state || 'idle');
    document.getElementById('jobstep').textContent = s.step || '';
    document.getElementById('jobleads').textContent = s.leads ? ('Leads found: ' + s.leads) : '';
    document.getElementById('jobelapsed').textContent = lfElapsed(s.started_at, s.state);
    const log = document.getElementById('joblog');
    if (s.log && s.log.length) {{
      log.textContent = s.log.join('\\n');
      log.scrollTop = log.scrollHeight;
    }} else if (s.state === 'running') {{
      log.textContent = 'Starting the pipeline...';
    }}
    const errorBox = document.getElementById('joberror');
    if (s.error) {{
      errorBox.innerHTML = '<div class="callout error"><div><b>Job problem:</b> ' + lfEscape(s.error) + '</div></div>';
    }} else {{
      errorBox.innerHTML = '';
    }}
    const resultBox = document.getElementById('jobresult');
    const notes = ' Notes: ' + (s.enrich_attempted || 0) + ' attempted, ' + (s.enrich_succeeded || 0) + ' ready, ' + (s.enrich_failed || 0) + ' failed, ' + (s.enrich_skipped || 0) + ' skipped.';
    if (s.state === 'done' && s.result_kind === 'zero') {{
      resultBox.innerHTML = '<div class="callout warn"><div>Finished normally with 0 leads. Your last good lead list was kept.</div></div>';
    }} else if (s.state === 'done') {{
      resultBox.innerHTML = '<div class="callout success"><div>Finished with ' + (s.leads || 0) + ' leads.' + lfEscape(notes) + '</div></div>';
    }} else if (s.state === 'partial') {{
      resultBox.innerHTML = '<div class="callout warn"><div>Partially done with ' + (s.leads || 0) + ' leads saved.' + lfEscape(notes) + '</div></div>';
    }} else {{
      resultBox.innerHTML = '';
    }}
    const done = document.getElementById('jobdone');
    if (s.state === 'done' || s.state === 'partial') {{
      done.innerHTML = '<a class="btn ghost" href="/leads">Open the Leads page</a>';
    }} else if (s.state === 'failed') {{
      done.innerHTML = '<a class="btn ghost" href="/health">Open Health</a>';
    }} else {{
      done.innerHTML = '';
    }}
  }} catch(e) {{}}
}}
poll(); setInterval(poll, 1500);
</script>"""
    return shell("run", body)

def _lead_columns(fieldnames):
    lower = {fn.lower().strip(): fn for fn in fieldnames if fn}
    def find(keys):
        for k in keys:
            if k in lower:
                return lower[k]
        return None
    cols = []
    for label, keys in [
        ("Business", ["title", "name", "business_name", "business"]),
        ("Phone", ["phone", "phone_number", "telephone", "mobile"]),
        ("Website", ["website", "site", "url", "web"]),
        ("Rating", ["review_rating", "rating", "ratings", "score"]),
        ("Reviews", ["review_count", "reviews", "reviews_count", "number_of_reviews"]),
        ("Address", ["address", "full_address", "location"]),
    ]:
        key = find(keys)
        if key:
            cols.append((label, key))
    if not cols:
        cols = [(fn, fn) for fn in fieldnames[:5]]
    return cols


def leads_page():
    store = sync_lead_store()
    store_entries = sorted(store.get("leads", {}).values(), key=lambda e: str(e.get("name") or "").lower())
    if store_entries:
        head_cells = "".join(f"<th>{label}</th>" for label in ("Business", "Category", "Phone", "Website", "Rating", "Reviews", "Address", "Note", "Pitch", "Qualification", "Outcome"))
        body_rows = ""
        for entry in store_entries:
            cells = ""
            cells += f"<td>{html.escape(str(entry.get('name') or ''))}</td>"
            cells += f"<td>{html.escape(str(entry.get('category') or ''))}</td>"
            cells += f'<td class="phone-cell">{html.escape(str(entry.get("phone") or ""))}</td>'
            website_val = str(entry.get("website") or "")
            if website_val:
                href = website_val if website_val.startswith("http") else "https://" + website_val
                cells += f'<td><a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener">{html.escape(website_val)}{icon("external", "sm")}</a></td>'
            else:
                cells += "<td></td>"
            cells += f"<td>{html.escape(str(entry.get('rating') or ''))}</td>"
            cells += f"<td>{html.escape(str(entry.get('reviews') or ''))}</td>"
            cells += f"<td>{html.escape(str(entry.get('address') or ''))}</td>"
            if entry.get("note_file"):
                cells += f'<td><span class="note-chip">{icon("check", "sm")}Yes</span></td>'
            else:
                cells += f'<td><span class="note-chip no">{icon("minus", "sm")}No</span></td>'
            if entry.get("pitch_file"):
                cells += '<td><span class="pitch-chip">Pitch ready</span></td>'
            else:
                cells += '<td><span class="pitch-chip no">No pitch</span></td>'
            qualification = entry.get("qualification") or "unknown"
            cells += f'<td><span class="qual-chip {html.escape(qualification)}">{html.escape(QUALIFICATION_LABELS.get(qualification, "Unknown"))}</span></td>'
            outcome_options = ""
            for outcome in LEAD_OUTCOMES:
                selected_attr = " selected" if entry.get("outcome") == outcome else ""
                outcome_options += f'<option value="{outcome}"{selected_attr}>{outcome}</option>'
            reply_line = ""
            if entry.get("reply_snippet"):
                reply_line = f'<div class="muted" style="margin-top:5px">Reply ({html.escape(str(entry.get("reply_tag") or "Question / other"))}): {html.escape(str(entry.get("reply_snippet"))[:90])}</div>'
            cells += (
                f'<td><form method="post" action="/leads/outcome" class="outcome-form"><input type="hidden" name="key" value="{html.escape(str(entry.get("key") or ""), quote=True)}">'
                f'<select name="outcome" aria-label="Outcome for {html.escape(str(entry.get("name") or ""), quote=True)}">{outcome_options}</select>'
                f'<button class="btn ghost small" type="submit">Save</button></form>{reply_line}</td>'
            )
            body_rows += f'<tr data-lead-row data-qual="{html.escape(qualification)}">{cells}</tr>'
        qual_options = '<option value="">All qualifications</option>' + "".join(
            f'<option value="{key}">{label}</option>' for key, label in QUALIFICATION_LABELS.items()
        )
        store_body = f"""
<div class="page-head">
<div><div class="eyebrow">Lead library</div><h1>Leads</h1><p>Your lead store keeps every lead across runs. Mark the outcome for each lead and LeadForge learns what works. The latest run list is still available as a CSV download.</p></div>
<div class="head-actions"><span class="status-pill ok"><span class="status-dot ok"></span>{len(store_entries)} saved leads</span></div>
</div>
<section class="panel">
<div class="panel-head toolbar">
<div class="title-with-icon"><div class="icon-medallion">{{icon("users")}}</div><div><h2>Lead store</h2><p>Search the store, filter by qualification, and update outcomes.</p></div></div>
<div class="head-actions">
<div class="search-box">{{icon("search")}}<input id="leadFilter" type="search" placeholder="Filter leads" aria-label="Filter leads"></div>
<select id="qualFilter" aria-label="Filter by qualification">{qual_options}</select>
<a class="btn" href="/download/latest.csv">{{icon("download", "sm")}}Download CSV</a>
</div>
</div>
<div class="callout" style="margin-bottom:14px">{{icon("info")}}<div><b>Qualification:</b> No website confirmed means the Google listing shows no website and the website reader found none either. LeadForge never claims more than the data shows. Website dead means a website is listed but the reader could not load it, which is its own pitch angle.</div></div>
<div class="table-shell"><table><thead><tr>{head_cells}</tr></thead><tbody>{body_rows}</tbody></table></div>
</section>
<script>
(function(){{var q=document.getElementById('qualFilter');if(!q)return;q.addEventListener('change',function(){{document.querySelectorAll('[data-lead-row]').forEach(function(r){{r.style.display=(!q.value||r.getAttribute('data-qual')===q.value)?'':'none';}});}});}})();
</script>"""
        store_body = store_body.replace('{icon("users")}', icon("users")).replace('{icon("search")}', icon("search")).replace('{icon("download", "sm")}', icon("download", "sm")).replace('{icon("info")}', icon("info"))
        return shell("leads", store_body)
    parsed = _parse_results_strict(LATEST_CSV)
    data_state = latest_data_state()
    meta = data_state.get("meta", {})
    if parsed["status"] != "valid" or not parsed["rows"]:
        if parsed["status"] == "malformed":
            body = f"""
<div class="page-head"><div><div class="eyebrow">Lead library</div><h1>Leads need attention</h1><p>The latest lead file could not be read safely, so LeadForge protected the library instead of guessing.</p></div></div>
<section class="panel">
<div class="title-with-icon"><div class="icon-medallion red">{icon("alert")}</div><div><h2>Latest lead file needs attention</h2><p>Run the pipeline again. If the same problem repeats, open Health and send the error log file to Muse.</p></div></div>
<div class="callout error" style="margin-top:16px"><div>{html.escape(parsed['error'])}</div></div>
<div style="margin-top:16px"><a class="btn" href="/health">{icon("activity", "sm")}Open Health</a></div>
</section>"""
        elif meta.get("last_result") == "zero":
            body = f"""
<div class="page-head"><div><div class="eyebrow">Lead library</div><h1>No leads in the latest search</h1><p>The search finished normally. A zero result is useful information, not a crash.</p></div></div>
<section class="panel empty-state">
<div class="empty-mark"><img src="/logo.svg" alt="LeadForge logo"></div>
<h2>The latest search found 0 leads</h2>
<p>There is no earlier good list to show. Try a broader business type or a nearby location.</p>
<a class="btn" href="/">{icon("search", "sm")}Run another search</a>
</section>"""
        else:
            body = f"""
<div class="page-head"><div><div class="eyebrow">Lead library</div><h1>Your leads will appear here</h1><p>Run a search and LeadForge will build a clean, ready to use list.</p></div></div>
<section class="panel empty-state">
<div class="empty-mark"><img src="/logo.svg" alt="LeadForge logo"></div>
<h2>No leads yet</h2>
<p>Go to the Run page, type a location and a business type, and click Run search. Your leads will appear here with phone, website and note status.</p>
<a class="btn" href="/">{icon("search", "sm")}Open the Run page</a>
</section>"""
        return shell("leads", body)

    fieldnames, rows = parsed["fieldnames"], parsed["rows"]
    cols = _lead_columns(fieldnames)
    website_key = None
    for label, key in cols:
        if label == "Website":
            website_key = key
    head = "".join(f"<th>{html.escape(label)}</th>" for label, _ in cols) + "<th>Note</th><th>Pitch</th>"
    pitch_records = lead_records()
    body_rows = ""
    for row_index, r in enumerate(rows):
        cells = ""
        for label, key in cols:
            val = (r.get(key) or "").strip()
            if label == "Website" and val:
                href = val if val.startswith("http") else "https://" + val
                cells += f'<td><a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener">{html.escape(val)}{icon("external", "sm")}</a></td>'
            elif label == "Phone":
                cells += f'<td class="phone-cell">{html.escape(val)}</td>'
            else:
                cells += f"<td>{html.escape(val)}</td>"
        website_val = (r.get(website_key) or "") if website_key else ""
        if note_exists(website_val):
            cells += f'<td><span class="note-chip">{icon("check", "sm")}Yes</span></td>'
        else:
            cells += f'<td><span class="note-chip no">{icon("minus", "sm")}No</span></td>'
        pitch_record = pitch_records[row_index] if row_index < len(pitch_records) else {"name": "", "index": row_index}
        if latest_pitch_for_lead(pitch_record):
            cells += f'<td><span class="pitch-chip">Pitch ready</span></td>'
        else:
            cells += f'<td><span class="pitch-chip no">No pitch</span></td>'
        body_rows += f"<tr data-lead-row>{cells}</tr>"
    if meta.get("last_result") == "zero":
        banner = f'<div class="callout" style="margin-bottom:14px">{icon("info")}<div>The most recent search finished successfully with 0 leads. This table is the last good lead list, so it was not overwritten.</div></div>'
    elif meta.get("updated"):
        banner = f'<div class="callout" style="margin-bottom:14px">{icon("info")}<div>Showing the last good lead list saved at {html.escape(str(meta.get("updated")))}.</div></div>'
    else:
        banner = f'<div class="callout" style="margin-bottom:14px">{icon("info")}<div>Showing the last good lead list.</div></div>'
    body = f"""
<div class="page-head">
<div><div class="eyebrow">Lead library</div><h1>Leads</h1><p>Your last good list, ready to scan, search and export. A note marker means the website reader prepared a pitch note.</p></div>
<div class="head-actions"><span class="status-pill ok"><span class="status-dot ok"></span>{len(rows)} saved leads</span></div>
</div>
<section class="panel">
<div class="panel-head toolbar">
<div class="title-with-icon"><div class="icon-medallion">{icon("users")}</div><div><h2>Lead list</h2><p>Search within the loaded list without changing the saved file.</p></div></div>
<div class="head-actions">
<div class="search-box">{icon("search")}<input id="leadFilter" type="search" placeholder="Filter leads" aria-label="Filter leads"></div>
<a class="btn" href="/download/latest.csv">{icon("download", "sm")}Download CSV</a>
</div>
</div>
{banner}
<div class="table-shell"><table><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div>
<div class="lead-count-note" id="leadFilterStatus">Showing all {len(rows)} leads.</div>
</section>
<script>
(function() {{
  const input = document.getElementById('leadFilter');
  const status = document.getElementById('leadFilterStatus');
  const rows = Array.from(document.querySelectorAll('[data-lead-row]'));
  if (!input || !status) return;
  input.addEventListener('input', function() {{
    const query = input.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach(function(row) {{
      const show = !query || row.textContent.toLowerCase().includes(query);
      row.style.display = show ? '' : 'none';
      if (show) visible += 1;
    }});
    status.textContent = query ? ('Showing ' + visible + ' of ' + rows.length + ' leads.') : ('Showing all ' + rows.length + ' leads.');
  }});
}})();
</script>"""
    return shell("leads", body)

def apps_page():
    ensure_app_ports_loaded()
    cards = ""
    for app in APPS:
        entry = app_assignment(app["id"])
        url = entry["url"]
        switched = '<span class="switchchip">Port switched</span>' if entry.get("switched") else ""
        icon_name, icon_class = APP_ICONS.get(app["id"], ("grid", "neutral"))
        cards += f"""
<article class="appcard">
<div class="app-head"><div class="icon-medallion app-icon {icon_class}">{icon(icon_name, "lg")}</div>
<div class="app-head-main"><h3>{html.escape(app['name'])}{switched}</h3></div>
<span class="status-pill" id="pill-{app['id']}"><span class="status-dot" id="pill-dot-{app['id']}"></span>Checking</span></div>
<p class="app-purpose">{html.escape(app['desc'])}</p>
<div class="app-address">{icon("globe")}<a id="addr-{app['id']}" href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(url)}</a></div>
<div class="app-status" id="status-{app['id']}"><span class="status-dot" id="dot-{app['id']}"></span><span id="status-text-{app['id']}">Checking the current state...</span></div>
<div class="app-callout" id="callout-{app['id']}"></div>
<div class="app-actions">
<a class="btn small" id="open-{app['id']}" href="{html.escape(url)}" target="_blank" rel="noopener">{icon("external", "sm")}Open</a>
<form method="post" action="/apps/action">
<input type="hidden" name="app" value="{app['id']}">
<input type="hidden" name="action" value="start">
<button class="btn ghost small" id="start-{app['id']}" type="submit">{icon("play", "sm")}Start</button></form>
<form method="post" action="/apps/action">
<input type="hidden" name="app" value="{app['id']}">
<input type="hidden" name="action" value="stop">
<button class="btn danger-ghost small" id="stop-{app['id']}" type="submit">{icon("stop", "sm")}Stop</button></form>
</div>
<details class="app-output"><summary>{icon("terminal")}<span style="margin-left:0">App output</span><span id="output-state-{app['id']}">Open log</span></summary>
<pre class="log" id="console-{app['id']}">No output yet.</pre></details>
</article>"""
    body = f"""
<div class="page-head">
<div><div class="eyebrow">Pipeline tools</div><h1>Apps</h1><p>Start each server tool from one control room. LeadForge checks ports first, switches busy ones safely, and always shows the real address.</p></div>
<div class="head-actions"><span class="status-pill info">{icon("server", "sm")}5 local tools</span></div>
</div>
<section class="panel apps-toolbar">
<div class="panel-head toolbar" style="margin-bottom:0">
<div class="title-with-icon"><div class="icon-medallion">{icon("grid")}</div><div><h2>Tool control</h2><p>Start one tool at a time where you can. Running all five together can slow the PC down.</p></div></div>
<form method="post" action="/apps/action">
<input type="hidden" name="app" value="all">
<input type="hidden" name="action" value="start">
<button class="btn" type="submit">{icon("play", "sm")}Start all apps</button>
</form>
</div>
<div class="callout batch-summary">{icon("info")}<div id="batchsummary">Start all has not been used in this dashboard session.</div></div>
</section>
<div class="app-grid">{cards}</div>
<script>
function appTone(status) {{
  if (status === 'running') return 'ok';
  if (status === 'working' || status === 'starting' || status === 'docker_missing' || status === 'docker_stopped') return 'warn';
  if (status === 'setup_needed' || status === 'start_failed') return 'error';
  if (status === 'stopped') return 'info';
  return '';
}}
async function pollApps() {{
  try {{
    const s = await (await fetch('/apps/status')).json();
    const batch = document.getElementById('batchsummary');
    if (batch && s._batch) batch.textContent = s._batch.summary || 'Start all has not been used in this dashboard session.';
    for (const id in s) {{
      if (id === '_batch') continue;
      const a = s[id];
      const pill = document.getElementById('pill-' + id);
      const pillDot = document.getElementById('pill-dot-' + id);
      const dot = document.getElementById('dot-' + id);
      const statusText = document.getElementById('status-text-' + id);
      const callout = document.getElementById('callout-' + id);
      const con = document.getElementById('console-' + id);
      const addr = document.getElementById('addr-' + id);
      const open = document.getElementById('open-' + id);
      const start = document.getElementById('start-' + id);
      const stop = document.getElementById('stop-' + id);
      const outputState = document.getElementById('output-state-' + id);
      if (!pill || !statusText || !con) continue;
      const tone = appTone(a.status);
      pill.className = 'status-pill ' + tone;
      pill.childNodes[1].textContent = a.status_label || a.status || 'Unknown';
      pillDot.className = 'status-dot ' + (tone || 'warn');
      dot.className = 'status-dot ' + (tone || 'warn');
      statusText.textContent = a.message || '';
      if (addr) {{ addr.textContent = a.url; addr.href = a.url; }}
      if (open) {{ open.href = a.url; }}
      if (start) start.disabled = !!a.busy;
      if (stop) stop.disabled = !!a.busy;
      const notes = [];
      if (a.switched) notes.push('Port switched from ' + a.preferred_port + ' to ' + a.actual_port + '.');
      if (a.ports) {{
        const deps = [];
        for (const key in a.ports) {{
          const p = a.ports[key];
          if (key !== 'web' && p.switched) deps.push(p.label + ' ' + p.preferred_port + ' to ' + p.actual_port);
        }}
        if (deps.length) notes.push('Other switched ports: ' + deps.join(', ') + '.');
      }}
      if (a.fix) notes.push('Fix: ' + a.fix);
      if (notes.length) {{
        callout.textContent = notes.join(' ');
        callout.className = 'app-callout show' + (tone === 'error' ? ' error' : '');
      }} else {{
        callout.textContent = '';
        callout.className = 'app-callout';
      }}
      if (a.output) {{
        con.textContent = a.output;
        con.scrollTop = con.scrollHeight;
        if (outputState) outputState.textContent = 'Updated';
      }}
    }}
  }} catch(e) {{}}
}}
pollApps(); setInterval(pollApps, 2000);
</script>"""
    return shell("apps", body)




# ---------------------------------------------------------------- settings and writer pages

def setup_status_rows():
    rows = []
    scraper = scraper_state()
    if scraper.get("found"):
        rows.append({
            "name": "Lead finder program",
            "state": "ready",
            "label": "Ready",
            "detail": "The program file is in folder 1. No key is needed.",
            "fields": [],
            "anchor": "",
            "action": "",
        })
    else:
        rows.append({
            "name": "Lead finder program",
            "state": "missing",
            "label": "Missing",
            "detail": "The program file was not found in folder 1.",
            "fields": [],
            "anchor": "",
            "action": "",
        })
    if ENRICH_SCRIPT.exists():
        rows.append({
            "name": "Website reader",
            "state": "not_needed",
            "label": "Not needed",
            "detail": "No key or setup form is needed. It runs after the finder.",
            "fields": [],
            "anchor": "",
            "action": "",
        })
    else:
        rows.append({
            "name": "Website reader",
            "state": "missing",
            "label": "Missing",
            "detail": "The website reader script was not found.",
            "fields": [],
            "anchor": "",
            "action": "",
        })
    ai_settings = load_ai_settings()
    local_status = local_ai_status()
    cloud_ready = bool(ai_settings.get("api_key")) and bool(ai_settings.get("cloud_provider"))
    if cloud_ready:
        cloud_label = AI_PROVIDER_INFO[ai_settings["cloud_provider"]]["label"]
        rows.append({
            "name": f"Free AI key ({cloud_label})",
            "state": "configured",
            "label": "Configured",
            "detail": "A free AI key is saved on this PC. It is never shown here. Writer AI is ready with this cloud key.",
            "fields": [],
            "anchor": "#free-ai",
            "action": "View",
        })
    else:
        rows.append({
            "name": "Free AI key (Gemini or Groq)",
            "state": "missing",
            "label": "Missing",
            "detail": "No free AI key is saved yet. Missing field: API key." + (" This is okay because Local AI is ready." if local_status["configured"] else " Local AI can be used instead."),
            "fields": ["API key"],
            "anchor": "#free-ai",
            "action": "Add key",
        })
    if local_status["configured"]:
        model_names = ", ".join(local_status["models"])
        detail = f"Local AI is running on this PC. Answered by {local_status.get('source') or 'the local server'}. Downloaded models: {model_names}. Writer AI is ready with Local AI."
        if not local_status["selected_downloaded"]:
            detail += f" Selected model {local_status['selected_model']} is not downloaded yet. Fix: ollama pull {local_status['selected_model']}."
        rows.append({
            "name": "Local AI (Ollama or compatible)",
            "state": "configured",
            "label": "Configured",
            "detail": detail,
            "fields": [],
            "anchor": "#free-ai",
            "action": "View",
        })
    else:
        if local_status["code"] == "LOCAL_AI_NO_MODEL":
            missing_detail = f"Ollama is running, but no model is downloaded yet. Fix: ollama pull {local_status['selected_model']}."
            missing_fields = ["Local AI model"]
        elif local_status["code"] == "LOCAL_AI_TIMEOUT":
            missing_detail = "Ollama did not answer in time. Fix: start Ollama on this PC and keep it running."
            missing_fields = ["Ollama running"]
        else:
            missing_detail = "Ollama is not running on this PC. Fix: start Ollama. If it is not installed, download it free from https://ollama.com/download and install it."
            missing_fields = ["Ollama running"]
        if cloud_ready:
            missing_detail += " This is okay because a cloud key is ready."
        rows.append({
            "name": "Local AI (Ollama or compatible)",
            "state": "missing",
            "label": "Missing",
            "detail": missing_detail,
            "fields": missing_fields,
            "anchor": "#free-ai",
            "action": "Open Local AI setup",
        })
    for app in APPS:
        if app["id"] in ENV_SETUP_APP_IDS:
            status = env_setup_status(app)
            if status["code"] == "ready":
                rows.append({
                    "name": app["name"],
                    "state": "ready",
                    "label": "Ready",
                    "detail": "Setup file is saved and the required fields pass.",
                    "fields": [],
                    "anchor": f"#setup-{app['id']}",
                    "action": "View form",
                })
            else:
                fields = list(status.get("missing") or []) + list(status.get("invalid") or [])
                rows.append({
                    "name": app["name"],
                    "state": "missing",
                    "label": "Missing",
                    "detail": "Fields to fix: " + (", ".join(fields) if fields else "setup file"),
                    "fields": fields,
                    "anchor": f"#setup-{app['id']}",
                    "action": "Open form",
                })
        elif app["id"] == "listmonk":
            rows.append({
                "name": app["name"],
                "state": "not_needed",
                "label": "Not needed",
                "detail": "No setup file is needed before it starts. Email sending is set inside listmonk later.",
                "fields": [],
                "anchor": "#setup-listmonk",
                "action": "Read note",
            })
    return rows


def setup_status_panel(link_prefix=""):
    rows_html = ""
    for row in setup_status_rows():
        if row["state"] in ("ready", "configured"):
            symbol = icon("check")
            pill = '<span class="status-pill ok"><span class="status-dot ok"></span>' + html.escape(row["label"]) + "</span>"
            row_class = "ok"
        elif row["state"] == "missing":
            symbol = icon("alert")
            pill = '<span class="status-pill warn"><span class="status-dot warn"></span>' + html.escape(row["label"]) + "</span>"
            row_class = "warn"
        else:
            symbol = icon("minus")
            pill = '<span class="status-pill"><span class="status-dot"></span>' + html.escape(row["label"]) + "</span>"
            row_class = "neutral"
        action_html = ""
        if row.get("anchor") and row.get("action"):
            href = link_prefix + row["anchor"] if link_prefix else row["anchor"]
            action_html = f'<a class="btn ghost small" href="{html.escape(href, quote=True)}">{html.escape(row["action"])}</a>'
        rows_html += f"""
<div class="config-row {row_class}">
<div class="config-symbol">{symbol}</div>
<div class="config-main"><div class="config-name">{html.escape(row['name'])}</div><div class="config-detail">{html.escape(row['detail'])}</div></div>
{pill}{action_html}
</div>"""
    return f"""
<section class="panel" id="setup-status" style="padding:19px;margin-bottom:16px">
<div class="title-with-icon"><div class="icon-medallion">{icon("shield")}</div><div><h2>Setup status</h2><p>This is a live check. Green means ready. Amber means something is missing. Grey means no setup is needed. For Writer AI, either the cloud key row or the Local AI row needs to be green.</p></div></div>
<div class="config-list">{rows_html}</div>
</section>"""


def guide_page():
    def steps(items):
        return "<ol class=\"guide-steps\">" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ol>"

    def card(icon_name, title, desc, step_items, actions_html="", note=""):
        note_html = f'<div class="callout" style="margin-top:13px">{icon("info")}<div>{note}</div></div>' if note else ""
        return f"""
<section class="panel guide-card">
<div class="title-with-icon"><div class="icon-medallion">{icon(icon_name)}</div><div><h2>{html.escape(title)}</h2><p>{html.escape(desc)}</p></div></div>
{steps(step_items)}
{note_html}
<div class="guide-actions">{actions_html}</div>
</section>"""

    cards = ""
    cards += card(
        "spark", "Free Gemini key", "Use this key in the Writer page. It is free and no card is needed.",
        [
            "Open Google AI Studio.",
            "Sign in with your Google account.",
            "Click Create API key.",
            "Copy the key.",
            "In LeadForge, open Settings, go to Free AI, choose Google Gemini free tier, paste the key, and click Save AI settings.",
        ],
        '<a class="btn small" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Open Google AI Studio</a><a class="btn ghost small" href="/settings#free-ai">Open Settings</a>',
    )
    cards += card(
        "spark", "Free Groq key", "Groq is another free AI choice for the Writer page. It is free and no card is needed.",
        [
            "Open the Groq console.",
            "Sign in.",
            "Open API Keys.",
            "Click Create key and copy the key.",
            "In LeadForge, open Settings, go to Free AI, choose Groq free tier, paste the key, and click Save AI settings.",
        ],
        '<a class="btn small" href="https://console.groq.com/keys" target="_blank" rel="noopener">Open Groq console</a><a class="btn ghost small" href="/settings#free-ai">Open Settings</a>',
    )
    cards += card(
        "server", "Local AI with Ollama", "Local AI runs on your own PC. It needs no API key and has no daily limit. The light setup below fits a PC with 8 GB RAM and no GPU.",
        [
            "Download Ollama free from https://ollama.com/download and install it.",
            "Open a terminal and run: ollama pull qwen2.5:3b. This is one time only and about 2 GB.",
            "Keep Ollama running. LeadForge talks to it on this PC only, nothing leaves the PC, no key, no daily limit.",
            "In LeadForge, open Settings, go to Free AI, choose Local AI, keep the base URL http://127.0.0.1:11434 and model qwen2.5:3b, save, then click Check local AI.",
        ],
        '<a class="btn small" href="https://ollama.com/download" target="_blank" rel="noopener">Download Ollama</a><a class="btn ghost small" href="/settings#free-ai">Open Local AI setup</a>',
        "Honest notes: a 3B model in 8 GB RAM with no GPU writes a pitch in roughly tens of seconds, depending on the CPU. Quality is below Gemini, but the Pitch rules in Settings keep the format consistent. If your PC is stronger, qwen2.5:7b is the quality step up.",
    )
    cards += card(
        "message", "chatwoot setup", APPS_BY_ID["chatwoot"]["desc"],
        [
            "Open Settings and fill the chatwoot form.",
            "Click Save chatwoot setup, then Check setup if you want LeadForge to test it.",
            "Start chatwoot from the Apps page.",
            "Inside chatwoot, create your admin account.",
            "Go to Inboxes and add your first channel. Website chat is the quickest to test.",
        ],
        '<a class="btn ghost small" href="/settings#setup-chatwoot">Open chatwoot form</a>',
    )
    cards += card(
        "calendar", "cal.diy setup", APPS_BY_ID["caldiy"]["desc"],
        [
            "Open Settings and fill the cal.diy form.",
            "Click Save cal.diy setup.",
            "Start cal.diy from the Apps page.",
            "Inside cal.diy, create your account.",
            "Connect your Google Calendar and set your working hours. Your booking link is shown on your event type page.",
        ],
        '<a class="btn ghost small" href="/settings#setup-caldiy">Open cal.diy form</a>',
    )
    cards += card(
        "users", "twenty setup", APPS_BY_ID["twenty"]["desc"],
        [
            "Open Settings and fill the twenty form. Blank random fields are made for you on save.",
            "Click Save twenty setup.",
            "Start twenty from the Apps page.",
            "Inside twenty, create your workspace and admin account.",
            "Go to People or Companies and import your leads. Add stages like New, Contacted, Replied, Call booked, and Closed.",
        ],
        '<a class="btn ghost small" href="/settings#setup-twenty">Open twenty form</a>',
    )
    cards += card(
        "pen", "documenso setup", APPS_BY_ID["documenso"]["desc"],
        [
            "Open Settings and fill the documenso form.",
            "Click Save documenso setup.",
            "Start documenso from the Apps page when you are ready.",
            "Inside documenso, create your account.",
            "Add your SMTP settings, then upload your standard proposal or agreement as a template.",
        ],
        '<a class="btn ghost small" href="/settings#setup-documenso">Open documenso form</a>',
        "This one can wait if you like. Its shipped setup expects a signing certificate path, so it is often easier later on a small server.",
    )
    cards += card(
        "mail", "listmonk email sending", "listmonk holds your lead lists and sends outreach emails. It has no setup form before it starts.",
        [
            "Start listmonk from the Apps page.",
            "Open listmonk and create or log in to the admin account.",
            "Go to Settings, then SMTP.",
            "Add your email sending account.",
            "Import your lead list after SMTP is ready.",
        ],
        '<a class="btn ghost small" href="/apps">Open Apps</a>',
        "A free route can be a Gmail app password or a free SMTP service. Without SMTP, listmonk can store lists but cannot send email.",
    )
    cards += card(
        "message", "chatwoot and WhatsApp", "chatwoot can collect replies in one inbox.",
        [
            "Email and website chat can work without WhatsApp.",
            "Real WhatsApp needs a WhatsApp Business API number.",
            "That number is connected inside chatwoot later, after the number is ready through Meta or a provider.",
        ],
        '<a class="btn ghost small" href="/settings#setup-chatwoot">Open chatwoot form</a>',
    )
    cards += card(
        "search", "Lead finder and website reader", "These two parts find leads and prepare website notes.",
        [
            "No API key is needed for the lead finder.",
            "No API key is needed for the website reader.",
            "Open Run, type a location and business type, and click Run search.",
            "The finder finds businesses first. The reader then reads websites and saves notes.",
        ],
        '<a class="btn ghost small" href="/">Open Run</a>',
    )
    cards += card(
        "book", "Set up your free web pitch writer", "This takes about 5 minutes, one time only. After that, your web assistant already knows the Pitch rules and format.",
        [
            "Open Writer, go to Manual mode, and click Copy web assistant setup.",
            "Gemini route: open gemini.google.com, open Gems, choose New Gem, name it LeadForge Pitch Writer, paste the setup text, and save.",
            "ChatGPT route: open chatgpt.com, open Explore GPTs or Create, paste the same setup text as the instructions, and save.",
            "Menu names may differ slightly on Gemini or ChatGPT. Look for the same ideas: create a custom assistant and paste instructions.",
            "For each batch later: open that saved assistant, paste the short instruction from LeadForge, copy the reply, and paste it back in LeadForge.",
        ],
        '<a class="btn ghost small" href="/writer#manual-mode">Open Writer manual mode</a>',
    )
    cards += card(
        "shield", "Send WhatsApp the safe way", "First contact on WhatsApp has rules. Following them keeps the risk of flags low, but no tool can promise zero flags.",
        [
            "Send the first message only through the official WhatsApp Business API inside chatwoot, with an approved template message.",
            "Add an opt-out line, for example: Reply STOP and I will not message again.",
            "Personalize the first line with the business name or area, so it never reads like a bulk blast.",
            "Send in small batches with gaps between them. Never send first contact from a personal number.",
        ],
        "",
        "If someone replies STOP or says they are not interested, mark them Not interested on the Leads page and do not message them again.",
    )
    cards += card(
        "mail", "Send email the safe way", "Email lands in the inbox only when the sending domain proves it is really you.",
        [
            "Set SPF, DKIM and DMARC records for your sending domain inside your DNS settings. Your email provider shows the exact values to add.",
            "Start with small daily numbers and grow slowly, so providers learn to trust the domain.",
            "listmonk handles bounces for you. The sending account itself is set in the listmonk email sending card on this page.",
        ],
        "",
        "Skipping SPF, DKIM and DMARC is the main reason first emails land in spam.",
    )
    cards += card(
        "chat", "Where email replies go", "listmonk sends email, but it does not receive replies.",
        [
            "Email replies land in your own mailbox, the same inbox the sending address belongs to.",
            "If you connect your email inside chatwoot later, replies can appear in chatwoot instead.",
            "Until then, mark email outcomes by hand on the Leads page: Replied, Call booked, Not interested, or No reply.",
        ],
        "",
        "LeadForge does not fake email sync. Chat replies sync from chatwoot on the Reports page; email outcomes are manual for now.",
    )
    cards += card(
        "pen", "No API key at all?", "The Writer page has a safe manual mode. You copy one instruction, use any free AI website, then paste the reply back.",
        [
            "Open Writer and pick the lead, output, and language.",
            "Click Copy instruction in Manual mode.",
            "Open ChatGPT, Gemini, Claude, or Groq and paste the instruction.",
            "Copy the AI reply.",
            "Paste it back in Writer and click Save manual pitch.",
        ],
        '<a class="btn ghost small" href="/writer#manual-mode">Open Writer manual mode</a>',
        "Some GitHub projects say they turn a web AI login into an API. They exist, but they need your web login cookies, break often, and can get the account flagged. LeadForge does not use them. The copy and paste mode is the safe built in way.",
    )
    body = f"""
<div class="page-head">
<div><div class="eyebrow">Beginner guide</div><h1>Guide</h1><p>Simple steps for keys, apps, email, WhatsApp, and the no key Writer mode. Follow one card at a time.</p></div>
<div class="head-actions"><a class="btn" href="/settings">{icon("settings", "sm")}Open Settings</a></div>
</div>
{setup_status_panel("/settings")}
<div class="guide-grid">{cards}</div>"""
    return shell("guide", body)


def settings_page():
    ai_state = ai_public_state()
    ai_result = SETTINGS_STATE.get("ai", {})
    ai_label = AI_PROVIDER_INFO[ai_state["provider"]]["label"]
    if ai_state.get("is_local"):
        ai_saved_line = "Local AI selected. No key is needed."
    elif ai_state["has_key"]:
        ai_saved_line = f"{ai_label} key is saved on this PC. It is never shown here."
    else:
        ai_saved_line = "No free AI key is saved yet."
    ai_result_html = ""
    if ai_result:
        tone = "success" if ai_result.get("kind") == "success" else "warn"
        ai_result_html = f'<div class="callout {tone}" style="margin-top:14px">{icon("check" if tone == "success" else "alert")}<div>{html.escape(ai_result.get("message", ""))}</div></div>'
    ai_settings_full = load_ai_settings()
    playbook_result = SETTINGS_STATE.get("playbook", {})
    playbook_result_html = ""
    if playbook_result:
        tone = "success" if playbook_result.get("kind") == "success" else "warn"
        playbook_result_html = f'<div class="callout {tone}" style="margin-top:14px">{icon("check" if tone == "success" else "alert")}<div>{html.escape(playbook_result.get("message", ""))}</div></div>'
    examples_placeholder = "Example shape:\nWHATSAPP:\nHi, I saw your business and had one simple idea for your website.\nSUBJECT:\nOne simple website idea\nEMAIL:\nHello, I am Tanmoy from GDL Technologies."
    local_result = SETTINGS_STATE.get("local", {})
    local_result_html = ""
    if local_result:
        if local_result.get("kind") == "success":
            local_result_html = f'<div class="callout success" style="margin-top:12px">{icon("check")}<div>{html.escape(local_result.get("message", ""))}</div></div>'
        else:
            fix_line = f'<br>Fix: {html.escape(local_result.get("fix", ""))}' if local_result.get("fix") else ""
            local_result_html = f'<div class="callout error" style="margin-top:12px">{icon("alert")}<div>{html.escape(local_result.get("message", ""))}{fix_line}</div></div>'
    pull_status_now = local_ai_status()
    pull_job_now = pull_job_snapshot()
    if pull_status_now["running"]:
        pull_html = (
            '<div class="callout" style="margin-top:12px">' + icon("info") + '<div><b>One-click model download.</b> Ollama is running on this PC. Download the selected local model here, one time. Size for qwen2.5:3b is about 2 GB.'
            '<form method="post" action="/settings/pull-model" style="margin-top:10px"><button class="btn ghost" type="submit">' + icon("download", "sm") + 'Download model (one click)</button></form>'
            '<div id="pullStatus" style="margin-top:9px">' + html.escape(pull_job_now.get("message") or pull_job_now.get("status_line") or "No download running.") + '</div></div></div>'
            '<script>(function(){var el=document.getElementById(\'pullStatus\');if(!el)return;function tick(){fetch(\'/settings/pull-status\').then(function(r){return r.json();}).then(function(d){var text=(d.state)+\' \' + (d.percent||0) + \'% \' + (d.status_line||\'\') + \' \' + (d.message||\'\');el.textContent=text;if(d.running){setTimeout(tick,1200);}}).catch(function(){});}tick();})();</script>'
        )
    else:
        pull_html = (
            '<div class="callout" style="margin-top:12px">' + icon("info") + '<div><b>Local AI is optional.</b> Ollama is not running on this PC, so the one-click download is not shown. Step 1: install Ollama free. Step 2: start Ollama, come back to this page, and the Download model button will appear here.'
            '<div style="margin-top:10px"><a class="btn ghost" href="https://ollama.com/download" target="_blank" rel="noopener">' + icon("download", "sm") + 'Download Ollama</a></div></div></div>'
        )
    provider_options = ""
    for key, info in AI_PROVIDER_INFO.items():
        selected = " selected" if key == ai_state["provider"] else ""
        provider_options += f'<option value="{key}"{selected}>{html.escape(info["label"])}</option>'
    ai_key_placeholder = "Saved on this PC. Leave blank to keep it." if ai_state.get("has_cloud_key") else "Paste your free API key"

    app_sections = ""
    for app in APPS:
        if app["id"] not in ENV_SETUP_APP_IDS:
            continue
        fields = env_fields_for_app(app)
        existing = parse_env_file(PACK_DIR / app["folder"] / ".env")
        status = env_setup_status(app)
        state = settings_state_for_app(app["id"])
        icon_name, icon_class = APP_ICONS.get(app["id"], ("grid", "neutral"))
        if status["code"] == "ready":
            pill = '<span class="status-pill ok"><span class="status-dot ok"></span>Ready</span>'
        elif status["code"] == "setup_needed":
            pill = '<span class="status-pill error"><span class="status-dot bad"></span>Setup needed</span>'
        else:
            pill = '<span class="status-pill warn"><span class="status-dot warn"></span>Needs fields</span>'
        result_bits = ""
        save_result = state.get("save")
        if save_result:
            if save_result.get("kind") == "success":
                generated = save_result.get("generated") or []
                generated_line = ""
                if generated:
                    generated_line = "<br>Auto generated random fields: " + html.escape(", ".join(generated)) + ". Their values are not shown."
                result_bits += f'<div class="callout success" style="margin-top:14px">{icon("check")}<div>{html.escape(save_result.get("message", ""))}{generated_line}</div></div>'
            else:
                names = []
                if save_result.get("missing"):
                    names.append("Missing: " + ", ".join(save_result["missing"]))
                if save_result.get("invalid"):
                    names.append("Invalid: " + ", ".join(save_result["invalid"]))
                result_bits += f'<div class="callout error" style="margin-top:14px">{icon("alert")}<div>{html.escape(save_result.get("message", ""))}<br>{html.escape(". ".join(names))}</div></div>'
        elif status["code"] == "needs_fields":
            names = []
            if status.get("missing"):
                names.append("Missing: " + ", ".join(status["missing"]))
            if status.get("invalid"):
                names.append("Invalid: " + ", ".join(status["invalid"]))
            result_bits += f'<div class="callout warn" style="margin-top:14px">{icon("alert")}<div>This saved setup still needs attention.<br>{html.escape(". ".join(names))}</div></div>'
        check_result = state.get("check")
        if check_result:
            if check_result.get("kind") == "success":
                result_bits += f'<div class="callout success" style="margin-top:12px">{icon("check")}<div>{html.escape(check_result.get("message", ""))}</div></div>'
            else:
                fix_line = f'<br>Fix: {html.escape(check_result.get("fix", ""))}' if check_result.get("fix") else ""
                result_bits += f'<div class="callout error" style="margin-top:12px">{icon("alert")}<div>{html.escape(check_result.get("message", ""))}{fix_line}</div></div>'
        fields_html = ""
        for field in fields:
            key = field["key"]
            field_id = f"set-{app['id']}-{key}"
            is_secret = bool(field.get("secret"))
            input_type = "password" if is_secret else "text"
            saved_value = existing.get(key, "")
            shown_value = "" if is_secret else (saved_value if key in existing else field.get("default", ""))
            value_attr = f' value="{html.escape(shown_value, quote=True)}"' if not is_secret else ""
            if is_secret:
                if saved_value:
                    placeholder = "Saved on this PC. Leave blank to keep it."
                elif field.get("auto"):
                    placeholder = "Leave blank to auto generate"
                else:
                    placeholder = "Type the value once"
            else:
                placeholder = "Optional" if not field.get("required") else "Required"
            badges = ""
            badges += '<span class="badge required">Required</span>' if field.get("required") else '<span class="badge">Optional</span>'
            if is_secret:
                badges += '<span class="badge secret">Secret</span>'
            if field.get("auto"):
                badges += '<span class="badge auto">Auto random</span>'
            if is_secret:
                if saved_value:
                    help_text = "Saved on this PC. It is never shown here. Leave blank to keep it."
                elif field.get("auto"):
                    help_text = "Leave blank and LeadForge will make a strong random value on save."
                else:
                    help_text = "Type it once. After saving it will only show as Saved."
            else:
                if key in existing:
                    help_text = "Saved value is shown. Source: " + field.get("source", ".env.example") + "."
                elif field.get("default"):
                    help_text = "Example value is filled in. Source: " + field.get("source", ".env.example") + "."
                else:
                    help_text = "Optional. Leave blank if this app does not use it."
            fields_html += f"""
<div class="field-card">
<label for="{html.escape(field_id, quote=True)}"><span class="mono">{html.escape(key)}</span></label>
<input id="{html.escape(field_id, quote=True)}" type="{input_type}" name="f_{app['id']}_{html.escape(key, quote=True)}"{value_attr} placeholder="{html.escape(placeholder, quote=True)}" autocomplete="{'new-password' if is_secret else 'off'}">
<div class="field-meta">{badges}</div>
<div class="field-help">{html.escape(help_text)}</div>
</div>"""
        app_sections += f"""
<section class="panel" id="setup-{app['id']}" style="margin-bottom:16px">
<div class="panel-head toolbar">
<div class="title-with-icon"><div class="icon-medallion app-icon {icon_class}">{icon(icon_name)}</div><div><h2>{html.escape(app['name'])} setup</h2><p>{html.escape(app['desc'])} Saving writes the app .env file in {html.escape(app['folder'])}. The .env.example file is not changed.</p></div></div>
<div class="head-actions">{pill}
<form method="post" action="/settings/check"><input type="hidden" name="app" value="{app['id']}"><button class="btn ghost small" type="submit">{icon("check", "sm")}Check setup</button></form>
</div>
</div>
{result_bits}
<form method="post" action="/settings/save">
<input type="hidden" name="app" value="{app['id']}">
<div class="settings-fields">{fields_html}</div>
<div class="settings-actions"><button class="btn" type="submit">{icon("check", "sm")}Save {html.escape(app['name'])} setup</button></div>
</form>
</section>"""

    listmonk = APPS_BY_ID["listmonk"]
    sync_state = chatwoot_sync_settings()
    sync_token_placeholder = "Saved on this PC. Leave blank to keep it." if sync_state.get("api_token") else "Paste the chatwoot API access token"
    sync_result = SETTINGS_STATE.get("sync", {})
    sync_result_html = ""
    if sync_result:
        sync_result_html = f'<div class="callout success" style="margin-top:12px">{icon("check")}<div>{html.escape(sync_result.get("message", ""))}</div></div>'
    body = f"""
<div class="page-head">
<div><div class="eyebrow">Setup</div><h1>Settings</h1><p>Set up the server apps and the free AI writer here. No more copying files or editing setup text by hand.</p></div>
<div class="head-actions"><span class="status-pill info">{icon("shield", "sm")}Local only</span></div>
</div>

<div class="callout warn" style="margin-bottom:16px">{icon("alert")}<div><b>Keep keys on this PC.</b> Keys stay in files on this PC only, and this dashboard is local only. Never paste API keys or app secrets into chats.</div></div>

{setup_status_panel("")}

{app_sections}

<section class="panel" id="free-ai" style="margin-bottom:16px">
<div class="panel-head">
<div class="title-with-icon"><div class="icon-medallion">{icon("spark")}</div><div><h2>Free AI writer</h2><p>Choose one provider. Gemini and Groq use a free API key. Local AI uses Ollama or a compatible local server on this PC and needs no key.</p></div></div>
<span class="status-pill {'ok' if ai_state['has_key'] else 'warn'}"><span class="status-dot {'ok' if ai_state['has_key'] else 'warn'}"></span>{html.escape(ai_saved_line)}</span>
</div>
<form method="post" action="/settings/ai">
<div class="row" style="flex-wrap:wrap">
<div><label for="ai_provider">Provider</label><select id="ai_provider" name="ai_provider">{provider_options}</select></div>
<div><label for="ai_api_key">API key for Gemini or Groq</label><input id="ai_api_key" type="password" name="ai_api_key" value="" placeholder="{html.escape(ai_key_placeholder, quote=True)}" autocomplete="new-password"></div>
</div>
<div class="row" style="flex-wrap:wrap;margin-top:14px">
<div><label for="ai_local_base_url">Local AI base URL</label><input id="ai_local_base_url" type="text" name="ai_local_base_url" value="{html.escape(ai_state['local_base_url'], quote=True)}" placeholder="http://127.0.0.1:11434"></div>
<div><label for="ai_local_model">Local AI model</label><input id="ai_local_model" type="text" name="ai_local_model" value="{html.escape(ai_state['local_model'], quote=True)}" placeholder="qwen2.5:3b"></div>
</div>
<div class="field-help" style="margin-top:9px">Local AI talks to any OpenAI compatible local server. It needs no API key and has no daily limit. Default base is Ollama at http://127.0.0.1:11434. Typical bases: Ollama 11434, LM Studio 1234, llama.cpp server 8080, KoboldCpp 5001. Recommended model: qwen2.5:3b, about 2 GB and comfortable in 8 GB RAM. Other options: llama3.2:3b for fast English first writing, and qwen2.5:7b for better writing but borderline in 8 GB and slow on a low CPU. Save first, then use Check local AI.</div>
<div class="settings-actions"><button class="btn" type="submit">{icon("check", "sm")}Save AI settings</button></div>
</form>
<form method="post" action="/settings/check-ai" style="margin-top:10px"><button class="btn ghost" type="submit">{icon("activity", "sm")}Check local AI</button></form>
{local_result_html}
{pull_html}
{ai_result_html}
<div class="callout" style="margin-top:14px">{icon("info")}<div>Get a free key: <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Google AI Studio</a> for Gemini, or <a href="https://console.groq.com/keys" target="_blank" rel="noopener">Groq console</a> for Groq. Free quotas can run out. Local AI has no key and no daily limit, but speed and quality depend on this PC.</div></div>
</section>

<section class="panel" id="pitch-rules" style="padding:20px;margin-bottom:16px">
<div class="title-with-icon"><div class="icon-medallion">{icon("pen")}</div><div><h2>Pitch rules</h2><p>These rules are used by every model: Gemini, Groq, Local AI, the manual instruction, and the web assistant setup. They are not secret and are stored with the AI settings on this PC.</p></div></div>
{playbook_result_html}
<form method="post" action="/settings/playbook">
<div class="pitch-section" style="margin-top:15px">
<div class="pitch-head"><label for="pitchRules" style="margin:0">Pitch rules</label><span class="pitch-count" data-count-for="pitchRules">0 characters</span></div>
<textarea id="pitchRules" name="pitch_rules" class="manual-text" data-count-input>{html.escape(ai_settings_full.get("pitch_rules", ""))}</textarea>
</div>
<div class="pitch-section">
<div class="pitch-head"><label for="pitchExamples" style="margin:0">Examples (optional)</label><span class="pitch-count" data-count-for="pitchExamples">0 characters</span></div>
<textarea id="pitchExamples" name="pitch_examples" class="manual-text" data-count-input placeholder="{html.escape(examples_placeholder, quote=True)}">{html.escape(ai_settings_full.get("pitch_examples", ""))}</textarea>
<div class="field-help">Paste one good pitch here later if you want every model to copy its style. Leave it empty if you do not have one yet.</div>
</div>
<div class="settings-actions"><button class="btn" type="submit">{icon("check", "sm")}Save rules</button></div>
</form>
<form method="post" action="/settings/playbook-reset" style="margin-top:10px"><button class="btn ghost" type="submit">{icon("refresh", "sm")}Reset to default</button></form>
</section>

<section class="panel" id="setup-listmonk">
<div class="title-with-icon"><div class="icon-medallion app-icon mail">{icon("mail")}</div><div><h2>listmonk setup</h2><p>{html.escape(listmonk['desc'])}</p></div></div>
<div class="callout" style="margin-top:14px">{icon("info")}<div>listmonk does not need a setup file before it starts. Its email sending is set inside listmonk after it starts: open listmonk, create or log in to the admin account, then go to <b>Settings</b>, then <b>SMTP</b>, and add your email sending account.</div></div>
</section>

<section class="panel" id="setup-chatwoot-sync" style="padding:20px">
<div class="title-with-icon"><div class="icon-medallion">{icon("chat")}</div><div><h2>Chatwoot reply sync</h2><p>Optional. LeadForge checks open chatwoot conversations and marks matched leads as Replied on the Leads page and in reports. Replies are classified by simple keywords only in this version, no AI is used for this.</p></div></div>
{sync_result_html}
<form method="post" action="/settings/chatwoot-sync">
<div class="row" style="flex-wrap:wrap;margin-top:14px">
<div><label for="chatwoot_base_url">Chatwoot base URL</label><input id="chatwoot_base_url" type="text" name="chatwoot_base_url" value="{html.escape(sync_state['base_url'], quote=True)}"></div>
<div><label for="chatwoot_account_id">Account ID</label><input id="chatwoot_account_id" type="text" name="chatwoot_account_id" value="{html.escape(sync_state['account_id'], quote=True)}"></div>
<div><label for="chatwoot_api_token">API access token</label><input id="chatwoot_api_token" type="password" name="chatwoot_api_token" value="" placeholder="{html.escape(sync_token_placeholder, quote=True)}" autocomplete="new-password"></div>
</div>
<div class="field-help" style="margin-top:9px">The token is stored only on this PC, shown masked, and never logged. Email replies are not synced: listmonk sends but does not receive, so email replies land in your mailbox (or in chatwoot if you connect email there) and are marked by hand on the Leads page for now.</div>
<div class="settings-actions"><button class="btn" type="submit">{icon("check", "sm")}Save reply sync settings</button></div>
</form>
</section>
<script>
document.querySelectorAll('[data-count-input]').forEach(function(el) {{
  const target = document.querySelector('[data-count-for="' + el.id + '"]');
  function update() {{ if (target) target.textContent = (el.value || '').length + ' characters'; }}
  update(); el.addEventListener('input', update);
}});
</script>"""
    return shell("settings", body)


def writer_page(query=None):
    query = query or {}

    def qfirst(name, default=""):
        vals = query.get(name)
        return str(vals[0]) if vals else default

    leads = lead_records()
    ai_state = ai_public_state()
    ai_label = AI_PROVIDER_INFO[ai_state["provider"]]["label"]
    local_status = local_ai_status() if ai_state.get("is_local") else None
    if not leads:
        key_note = ""
        if ai_state.get("is_local"):
            key_note = f'<div class="callout" style="margin-top:14px">{icon("info")}<div>Local AI is selected, so no API key is needed. After you have leads, this page will show whether Ollama is running.</div></div>'
        elif not ai_state["has_key"]:
            key_note = f'<div class="callout warn" style="margin-top:14px">{icon("alert")}<div>No free AI key is saved yet. After you have leads, open Settings and save a Gemini or Groq free key, choose Local AI, or use Manual mode.</div></div>'
        body = f"""
<div class="page-head"><div><div class="eyebrow">AI writer</div><h1>Writer</h1><p>Personal outreach, written from your real lead data by a free AI provider.</p></div></div>
<section class="panel empty-state">
<div class="empty-mark"><img src="/logo.svg" alt="LeadForge logo"></div>
<h2>No leads yet</h2>
<p>Run a search first. When your lead list is ready, this page will let you pick a lead and write a WhatsApp message, an email, or both.</p>
<a class="btn" href="/">{icon("search", "sm")}Open the Run page</a>
{key_note}
</section>"""
        return shell("writer", body)

    try:
        selected = int(qfirst("lead", "0"))
    except ValueError:
        selected = 0
    if selected < 0 or selected >= len(leads):
        selected = 0
    output = qfirst("output", "both")
    if output not in ("whatsapp", "email", "both"):
        output = "both"
    language = qfirst("language", "auto")
    if language not in ("english", "bangla", "auto"):
        language = "auto"
    lead = leads[selected]
    pitch_path = latest_pitch_for_lead(lead)
    result = parse_pitch_file(pitch_path) if pitch_path else {"whatsapp": "", "email_subject": "", "email_body": ""}
    last = WRITER_STATE.get("last")
    if last and int(last.get("lead_index", -1)) == selected:
        result = {
            "whatsapp": last.get("whatsapp", ""),
            "email_subject": last.get("email_subject", ""),
            "email_body": last.get("email_body", ""),
            "quality_note": last.get("quality_note", ""),
            "style_label": last.get("style_label", ""),
            "style_reasons": last.get("style_reasons", []),
            "humanized": last.get("humanized", False),
        }
    lead_options = ""
    for record in leads:
        detail = record.get("category") or record.get("address") or "Lead"
        selected_attr = " selected" if record["index"] == selected else ""
        lead_options += f'<option value="{record["index"]}"{selected_attr}>{html.escape(record["name"])} - {html.escape(detail)}</option>'
    output_options = ""
    for value, label in (("whatsapp", "WhatsApp message"), ("email", "Email"), ("both", "Both")):
        selected_attr = " selected" if value == output else ""
        output_options += f'<option value="{value}"{selected_attr}>{label}</option>'
    language_options = ""
    for value, label in (("english", "English"), ("bangla", "Bangla")):
        selected_attr = " selected" if value == language else ""
        language_options += f'<option value="{value}"{selected_attr}>{label}</option>'

    notice_html = ""
    if WRITER_STATE.get("error"):
        notice_html = f'<div class="callout error" style="margin-bottom:14px">{icon("alert")}<div><b>{html.escape(WRITER_STATE.get("error_code", "AI error"))}:</b> {html.escape(WRITER_STATE.get("error", ""))}</div></div>'
    elif WRITER_STATE.get("notice"):
        notice_html = f'<div class="callout success" style="margin-bottom:14px">{icon("check")}<div>{html.escape(WRITER_STATE.get("notice", ""))}</div></div>'
    if ai_state.get("is_local") and local_status:
        if local_status["configured"] and local_status["selected_downloaded"]:
            notice_html += f'<div class="callout success" style="margin-bottom:14px">{icon("check")}<div><b>Local AI is running on this PC.</b> Model: {html.escape(local_status["selected_model"])}. Downloaded models: {html.escape(", ".join(local_status["models"]))}. No key and no daily limit.</div></div>'
        elif local_status["configured"]:
            notice_html += f'<div class="callout warn" style="margin-bottom:14px">{icon("alert")}<div><b>Local AI is running, but the selected model is not downloaded yet.</b> Fix: <span class="mono">ollama pull {html.escape(local_status["selected_model"])}</span>. Downloaded models: {html.escape(", ".join(local_status["models"]))}.</div></div>'
        else:
            notice_html += f'<div class="callout warn" style="margin-bottom:14px">{icon("alert")}<div><b>{html.escape(local_status["message"])}</b> Fix: {html.escape(local_status["fix"])} Generate stays on so you can try after starting Ollama. Manual mode below also works.</div></div>'
    elif not ai_state["has_key"]:
        notice_html += f'<div class="callout warn" style="margin-bottom:14px">{icon("alert")}<div>No free AI key is saved, so Generate is off. Open Settings, save a Gemini or Groq free key, choose Local AI, or use Manual mode below. Manual mode needs no key and makes no API call.</div></div>'
    pitch_ready_html = ""
    if pitch_path:
        pitch_ready_html = f'<div class="callout success" style="margin-top:14px">{icon("check")}<div><b>Pitch ready for this lead.</b> Latest saved file: <span class="mono">{html.escape(pitch_path.name)}</span></div></div>'
    quality_note_html = ""
    if result.get("quality_note"):
        if result["quality_note"] == "Auto-fixed on retry":
            quality_note_html = f'<div class="callout success" style="margin-bottom:14px">{icon("check")}<div>Auto-fixed on retry</div></div>'
        else:
            quality_note_html = f'<div class="callout warn" style="margin-bottom:14px">{icon("alert")}<div>Check before sending</div></div>'
    style_html = ""
    if result.get("style_label"):
        style_class = "success" if result["style_label"] == "Looks human" else "warn" if result["style_label"] == "Some AI signs" else "error"
        style_icon = "check" if result["style_label"] == "Looks human" else "alert"
        reasons_text = (" Reasons: " + "; ".join(result.get("style_reasons") or [])) if result.get("style_reasons") else ""
        humanized_text = " This pitch was humanized by one rewrite pass." if result.get("humanized") else ""
        style_html = f'<div class="callout {style_class}" style="margin-bottom:14px">{icon(style_icon)}<div><b>Style check: {html.escape(result["style_label"])}</b>{html.escape(reasons_text)}{html.escape(humanized_text)}</div></div>'
    worked_summary = learning_summary(sync_lead_store())
    if worked_summary:
        learning_html = f'<section class="panel" style="margin-top:18px"><div class="panel-head"><div class="title-with-icon"><div class="icon-medallion green">{icon("spark")}</div><div><h2>What is working</h2><p>Learned from the outcomes you mark on the Leads page.</p></div></div></div><p style="margin:0">{html.escape(worked_summary)}. New prompts now include this hint.</p></section>'
    else:
        learning_html = '<section class="panel" style="margin-top:18px"><div class="panel-head"><div class="title-with-icon"><div class="icon-medallion">{icon("spark")}</div><div><h2>What is working</h2><p>LeadForge learns from your results over time.</p></div></div></div><p style="margin:0">Still learning: mark replies on the Leads page and I will learn what works.</p></section>'
    if lead.get("note_exists"):
        note_html = f'<div class="callout success">{icon("check")}<div>Website note found. The writer will use it with the lead facts.</div></div><details style="margin-top:10px"><summary style="cursor:pointer;color:var(--dim);font-size:12.5px;font-weight:680">Preview the website note</summary><div class="note-preview" style="margin-top:9px">{html.escape(lead.get("note_text", "")[:1400])}</div></details>'
    else:
        note_html = f'<div class="callout">{icon("info")}<div>No website note for this lead. The writer will use the lead facts only and will not invent details.</div></div>'
    fact_rows = ""
    for label, value in (("Type", lead.get("category")), ("Area", lead.get("address")), ("Rating", lead.get("rating")), ("Reviews", lead.get("reviews")), ("Phone", lead.get("phone")), ("Website", lead.get("website"))):
        if value:
            fact_rows += f'<div class="state-message"><b style="color:var(--txt)">{html.escape(label)}:</b> {html.escape(value)}</div>'
    batch = writer_job_snapshot()
    batch_message = batch.get("message") or "No pitch batch has run in this dashboard session."
    batch_disabled = " disabled" if (not ai_state["has_key"] or batch.get("running")) else ""
    generate_disabled = " disabled" if (not ai_state["has_key"] or batch.get("running")) else ""
    if local_status:
        if local_status["configured"] and local_status["selected_downloaded"]:
            ai_pill_text = f"Local AI ready: {local_status['selected_model']}"
            ai_pill_tone = "ok"
        elif local_status["configured"]:
            ai_pill_text = f"Local AI running, model missing: {local_status['selected_model']}"
            ai_pill_tone = "warn"
        else:
            ai_pill_text = "Local AI selected, not running"
            ai_pill_tone = "warn"
    else:
        ai_pill_text = ai_label + (" key saved" if ai_state["has_key"] else " needs a key")
        ai_pill_tone = "ok" if ai_state["has_key"] else "warn"
    manual_instruction = build_manual_instruction(lead, output, language)
    manual_batch_instruction = build_manual_batch_instruction(leads, output, language)
    manual_short_instruction = build_short_manual_instruction(lead, output, language)
    manual_batch_short_instruction = build_short_manual_batch_instruction(leads, output, language)
    web_assistant_setup = build_web_assistant_setup(output)
    manual_panel = f"""
<section class="panel" id="manual-mode" style="padding:20px;margin-top:16px">
<div class="panel-head">
<div class="title-with-icon"><div class="icon-medallion">{icon("book")}</div><div><h2>No key or limit hit? Use manual mode</h2><p>Copy one instruction, paste it into any free AI website, then paste the reply back here. This mode works with no AI key and makes no API call.</p></div></div>
<span class="status-pill info">No API call</span>
</div>
<div class="pitch-section">
<label for="webAssistantSetup">Web assistant setup (one time only)</label>
<textarea id="webAssistantSetup" class="manual-instruction" readonly>{html.escape(web_assistant_setup)}</textarea>
<div class="writer-actions" style="margin-top:9px"><button class="btn ghost" type="button" data-copy-target="webAssistantSetup">{icon("file", "sm")}Copy web assistant setup</button></div>
<div class="field-help">Paste this once into a Gemini Gem or a ChatGPT custom GPT and name it LeadForge Pitch Writer. After that, turn on the saved assistant option below and use the short instruction.</div>
</div>
<div class="callout" style="margin-bottom:14px">{icon("info")}<div><label for="useSavedAssistant" style="display:inline;text-transform:none;letter-spacing:0;font-size:13.5px;color:var(--txt)"><input type="checkbox" id="useSavedAssistant" style="width:auto;min-height:0;margin-right:8px">I use my saved web assistant</label><div style="margin-top:5px">On: the Copy instruction buttons use the short form, because your saved assistant already knows the rules. Off: the full instruction is copied.</div></div></div>
<div class="pitch-section">
<label for="manualInstruction">Instruction for {html.escape(lead['name'])}</label>
<textarea id="manualInstruction" class="manual-instruction" readonly>{html.escape(manual_instruction)}</textarea>
<textarea id="manualInstructionFull" style="display:none" readonly>{html.escape(manual_instruction)}</textarea>
<textarea id="manualInstructionShort" style="display:none" readonly>{html.escape(manual_short_instruction)}</textarea>
<div class="writer-actions" style="margin-top:9px"><button class="btn" type="button" data-copy-target="manualInstruction">{icon("file", "sm")}Copy instruction</button></div>
<div class="quick-links">
<a class="btn ghost small" href="https://chatgpt.com" target="_blank" rel="noopener">Open ChatGPT</a>
<a class="btn ghost small" href="https://gemini.google.com" target="_blank" rel="noopener">Open Gemini</a>
<a class="btn ghost small" href="https://claude.ai" target="_blank" rel="noopener">Open Claude</a>
<a class="btn ghost small" href="https://console.groq.com/playground" target="_blank" rel="noopener">Open Groq</a>
</div>
</div>
<form method="post" action="/writer/manual">
<input type="hidden" name="lead" value="{selected}"><input type="hidden" name="output" value="{output}"><input type="hidden" name="language" value="{language}">
<label for="manualReply">Paste the AI reply here</label>
<textarea id="manualReply" class="manual-text" name="manual_reply" placeholder="Paste the full reply from the free AI website here."></textarea>
<div class="settings-actions"><button class="btn" type="submit">{icon("check", "sm")}Save manual pitch</button></div>
</form>
<details style="margin-top:18px">
<summary style="cursor:pointer;color:var(--txt);font-weight:720">Manual batch for the first 10 leads</summary>
<div style="margin-top:13px">
<label for="manualBatchInstruction">Combined batch instruction</label>
<textarea id="manualBatchInstruction" class="manual-instruction" readonly>{html.escape(manual_batch_instruction)}</textarea>
<textarea id="manualBatchInstructionFull" style="display:none" readonly>{html.escape(manual_batch_instruction)}</textarea>
<textarea id="manualBatchInstructionShort" style="display:none" readonly>{html.escape(manual_batch_short_instruction)}</textarea>
<div class="writer-actions" style="margin-top:9px"><button class="btn ghost" type="button" data-copy-target="manualBatchInstruction">{icon("file", "sm")}Copy batch instruction</button></div>
<form method="post" action="/writer/manual-batch" style="margin-top:14px">
<input type="hidden" name="output" value="{output}"><input type="hidden" name="language" value="{language}">
<label for="manualBatchReply">Paste the batch AI reply here</label>
<textarea id="manualBatchReply" class="manual-text" name="manual_batch_reply" placeholder="Paste the full batch reply, with one numbered lead section for each lead."></textarea>
<div class="settings-actions"><button class="btn" type="submit">{icon("check", "sm")}Save batch pitches</button></div>
</form>
</div>
</details>
</section>"""
    result_sections = ""
    if output in ("whatsapp", "both"):
        result_sections += f"""
<div class="pitch-section">
<div class="pitch-head"><h3>WhatsApp message</h3><span class="pitch-count" data-count-for="waText">0 characters</span></div>
<textarea class="pitch-text" id="waText" data-count-input placeholder="Your WhatsApp pitch will appear here.">{html.escape(result.get("whatsapp", ""))}</textarea>
<div class="writer-actions" style="margin-top:9px"><button class="btn ghost small" type="button" data-copy-target="waText">{icon("file", "sm")}Copy WhatsApp</button></div>
</div>"""
    if output in ("email", "both"):
        result_sections += f"""
<div class="pitch-section">
<div class="pitch-head"><h3>Email subject</h3><span class="pitch-count" data-count-for="emailSubject">0 characters</span></div>
<input class="subject-input" id="emailSubject" type="text" data-count-input value="{html.escape(result.get("email_subject", ""), quote=True)}" placeholder="Email subject will appear here.">
</div>
<div class="pitch-section">
<div class="pitch-head"><h3>Email body</h3><span class="pitch-count" data-count-for="emailBody">0 characters</span></div>
<textarea class="pitch-text email-body" id="emailBody" data-count-input placeholder="Your email pitch will appear here.">{html.escape(result.get("email_body", ""))}</textarea>
<div class="writer-actions" style="margin-top:9px"><button class="btn ghost small" type="button" data-copy-target="emailSubject">{icon("file", "sm")}Copy subject</button><button class="btn ghost small" type="button" data-copy-target="emailBody">{icon("file", "sm")}Copy email</button></div>
</div>"""
    writer_script = """
<script>
function writerCount(el) {
  const target = document.querySelector('[data-count-for="' + el.id + '"]');
  if (target) target.textContent = (el.value || '').length + ' characters';
}
document.querySelectorAll('[data-count-input]').forEach(function(el) {
  writerCount(el);
  el.addEventListener('input', function() { writerCount(el); });
});
document.querySelectorAll('[data-copy-target]').forEach(function(btn) {
  btn.addEventListener('click', async function() {
    const el = document.getElementById(btn.getAttribute('data-copy-target'));
    if (!el) return;
    const old = btn.textContent;
    try {
      await navigator.clipboard.writeText(el.value || '');
      btn.textContent = 'Copied';
    } catch(e) {
      el.focus(); el.select(); document.execCommand('copy'); btn.textContent = 'Copied';
    }
    setTimeout(function() { btn.textContent = old; }, 1400);
  });
});
const savedAssistantToggle = document.getElementById('useSavedAssistant');
function swapManualInstructions() {
  const on = savedAssistantToggle && savedAssistantToggle.checked;
  const single = document.getElementById('manualInstruction');
  const singleFull = document.getElementById('manualInstructionFull');
  const singleShort = document.getElementById('manualInstructionShort');
  if (single && singleFull && singleShort) single.value = on ? singleShort.value : singleFull.value;
  const batch = document.getElementById('manualBatchInstruction');
  const batchFull = document.getElementById('manualBatchInstructionFull');
  const batchShort = document.getElementById('manualBatchInstructionShort');
  if (batch && batchFull && batchShort) batch.value = on ? batchShort.value : batchFull.value;
}
if (savedAssistantToggle) savedAssistantToggle.addEventListener('change', swapManualInstructions);
async function pollWriterBatch() {
  try {
    const s = await (await fetch('/writer/status')).json();
    const box = document.getElementById('batchStatus');
    if (!box) return;
    if (s.running) {
      box.textContent = 'Running. Processed ' + (s.processed || 0) + ' of ' + (s.total || 0) + '. Now writing: ' + (s.current || 'starting') + '.';
    } else if (s.state && s.state !== 'idle') {
      box.innerHTML = '';
      const span = document.createElement('span'); span.textContent = s.message || '';
      box.appendChild(span);
      const link = document.createElement('a'); link.href = window.location.pathname + window.location.search; link.textContent = ' Refresh this page';
      box.appendChild(link);
    }
  } catch(e) {}
}
pollWriterBatch(); setInterval(pollWriterBatch, 2000);
</script>"""
    body = f"""
<div class="page-head">
<div><div class="eyebrow">AI writer</div><h1>Writer</h1><p>Pick a lead, choose the format, and let the free AI write a personal message from the real lead facts and website note.</p></div>
<div class="head-actions"><span class="status-pill {ai_pill_tone}"><span class="status-dot {ai_pill_tone}"></span>{html.escape(ai_pill_text)}</span></div>
</div>
{notice_html}
<div class="writer-grid">
<section class="panel">
<div class="title-with-icon"><div class="icon-medallion">{icon("pen")}</div><div><h2>Choose the lead</h2><p>The writer only uses facts saved in LeadForge.</p></div></div>
<form method="get" action="/writer" class="writer-controls" style="margin-top:16px">
<div><label for="leadPick">Lead</label><select id="leadPick" name="lead">{lead_options}</select></div>
<div><label for="outputPick">Output</label><select id="outputPick" name="output">{output_options}</select></div>
<div><label for="languagePick">Language</label><select id="languagePick" name="language">{language_options}</select></div>
<button class="btn ghost" type="submit">{icon("refresh", "sm")}Load lead</button>
</form>
<div style="margin-top:16px"><h3 style="margin:0 0 7px;font-size:14.5px">{html.escape(lead['name'])}</h3>{fact_rows}</div>
<div style="margin-top:14px">{note_html}</div>
{pitch_ready_html}
<div class="writer-actions" style="margin-top:16px">
<form method="post" action="/writer/generate"><input type="hidden" name="lead" value="{selected}"><input type="hidden" name="output" value="{output}"><input type="hidden" name="language" value="{language}"><button class="btn" type="submit"{generate_disabled}>{icon("spark", "sm")}Generate pitch</button></form>
<form method="post" action="/writer/generate"><input type="hidden" name="lead" value="{selected}"><input type="hidden" name="output" value="{output}"><input type="hidden" name="language" value="{language}"><button class="btn ghost" type="submit"{generate_disabled}>{icon("refresh", "sm")}Regenerate</button></form>
</div>
<div class="callout" style="margin-top:16px">{icon("info")}<div><b>Batch:</b> write pitches for qualified leads only: no website confirmed, plus dead websites. Unknown leads are never included. The cap of 10 protects the free quota.<div id="batchStatus" style="margin-top:7px">{html.escape(batch_message)}</div>
<form method="post" action="/writer/batch" style="margin-top:10px"><input type="hidden" name="output" value="{output}"><input type="hidden" name="language" value="{language}"><label class="check-row" style="margin:0 0 10px"><input type="checkbox" name="include_has_website" value="1"><span>Also include leads that already have a website</span></label><button class="btn ghost small" id="batchButton" type="submit"{batch_disabled}>{icon("pen", "sm")}Write for first 10 leads</button></form></div></div>
</section>
<section class="panel">
<div class="panel-head"><div class="title-with-icon"><div class="icon-medallion green">{icon("file")}</div><div><h2>Pitch editor</h2><p>Edit the text here before you use it. Copy buttons copy the current edited text.</p></div></div></div>
{quality_note_html}
{style_html}
{result_sections}
</section>
</div>
{learning_html}
{manual_panel}
{writer_script}"""
    return shell("writer", body)


# ---------------------------------------------------------------- reports and reply sync

def chatwoot_sync_settings():
    data = read_json_file(CHATWOOT_SYNC_FILE, {})
    if not isinstance(data, dict):
        data = {}
    return {
        "base_url": str(data.get("base_url") or "http://localhost:3001").rstrip("/"),
        "account_id": str(data.get("account_id") or ""),
        "api_token": str(data.get("api_token") or ""),
        "last_sync": data.get("last_sync") if isinstance(data.get("last_sync"), dict) else {},
    }


def save_chatwoot_sync_settings(base_url, account_id, api_token):
    current = chatwoot_sync_settings()
    data = {
        "base_url": (str(base_url or "").strip() or "http://localhost:3001").rstrip("/"),
        "account_id": str(account_id or "").strip(),
        "api_token": str(api_token or "").strip() or current["api_token"],
        "last_sync": current["last_sync"],
    }
    atomic_write_json(CHATWOOT_SYNC_FILE, data)
    return data


def _record_sync_status(result, message, fix=""):
    data = read_json_file(CHATWOOT_SYNC_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("base_url", "http://localhost:3001")
    data.setdefault("account_id", "")
    data.setdefault("api_token", "")
    data["last_sync"] = {"at": now_iso(), "result": result, "message": message, "fix": fix}
    atomic_write_json(CHATWOOT_SYNC_FILE, data)
    return data["last_sync"]


def classify_reply(text):
    lowered = str(text or "").lower()
    if any(word in lowered for word in ("not interested", "stop", "do not contact", "dont contact", "no thanks")):
        return "Not interested"
    if any(word in lowered for word in ("interested", "call me", "price", "cost", "quote", "charges", "details")):
        return "Positive"
    return "Question / other"


def check_chatwoot_replies():
    settings = chatwoot_sync_settings()
    if not settings["account_id"] or not settings["api_token"]:
        status = _record_sync_status("not_configured", "Chatwoot reply sync is not set up yet.", "Open Settings and save the Chatwoot base URL, account ID and API access token first.")
        return status
    url = f"{settings['base_url']}/api/v1/accounts/{urllib.parse.quote(str(settings['account_id']))}/conversations?status=open&per_page=50"
    request = urllib.request.Request(url, headers={"api_access_token": settings["api_token"]}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            status = _record_sync_status("auth_failed", f"Chatwoot rejected the API access token (HTTP {exc.code}).", "Open Chatwoot, copy a fresh API access token from your profile, save it in Settings, then check again.")
        else:
            status = _record_sync_status("error", f"Chatwoot answered with HTTP {exc.code}.", "Check that chatwoot is running at the saved base URL, then check again.")
        log_error("sync", "CHATWOOT_SYNC_FAILED", status["message"], f"HTTP {exc.code}", status["fix"])
        return status
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        status = _record_sync_status("unreachable", "Chatwoot could not be reached, so no replies were checked.", "Start chatwoot, then check again. LeadForge retries automatically the next time you open the Reports page or click Check replies now. Nothing broke.")
        log_error("sync", "CHATWOOT_UNREACHABLE", status["message"], sanitize_text(str(exc)), status["fix"])
        return status
    except Exception as exc:
        status = _record_sync_status("error", "The reply check stopped because of an internal problem. The detail is in the error log.", "Check that chatwoot is running at the saved base URL, then check again.")
        log_error("sync", "CHATWOOT_SYNC_FAILED", status["message"], sanitize_text(str(exc)), status["fix"])
        return status
    conversations = []
    if isinstance(payload, dict):
        inner = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        conversations = inner.get("payload") or payload.get("payload") or []
    if not isinstance(conversations, list):
        conversations = []
    store = sync_lead_store()
    matched = 0
    new_replies = 0
    for conv in conversations[:50]:
        if not isinstance(conv, dict):
            continue
        sender = ((conv.get("meta") or {}).get("sender") or {}) if isinstance(conv.get("meta"), dict) else {}
        phone = sender.get("phone_number") or sender.get("phone") or ""
        digits = re.sub(r"\D", "", str(phone))
        if len(digits) < 10:
            continue
        entry = store["leads"].get("phone:" + digits[-10:])
        if not entry:
            continue
        matched += 1
        messages = conv.get("messages") if isinstance(conv.get("messages"), list) else []
        incoming = [m for m in messages if isinstance(m, dict) and (m.get("message_type") in (0, "incoming") or m.get("incoming"))]
        last = {}
        if incoming:
            last = incoming[-1]
        else:
            candidate = conv.get("last_non_activity_message")
            if isinstance(candidate, dict):
                last = candidate
        content = str((last or {}).get("content") or "").strip()[:200]
        if not content:
            continue
        if entry.get("outcome") != "Call booked" and entry.get("reply_snippet") != content:
            entry["outcome"] = "Replied"
            entry["reply_snippet"] = content
            entry["reply_at"] = str(conv.get("updated_at") or now_iso())
            entry["reply_tag"] = classify_reply(content)
            new_replies += 1
    save_lead_store(store)
    status = _record_sync_status("done", f"Checked {min(len(conversations), 50)} open conversations. {matched} matched leads. {new_replies} new replies.", "")
    record_event("info", "sync", "CHATWOOT_SYNC_DONE", status["message"])
    return status


def generate_report():
    ensure_storage()
    store = sync_lead_store()
    entries = list(store.get("leads", {}).values())
    by_class = {key: 0 for key in QUALIFICATION_LABELS}
    for entry in entries:
        by_class[entry.get("qualification", "unknown")] = by_class.get(entry.get("qualification", "unknown"), 0) + 1
    qualified = by_class["no_website_confirmed"] + by_class["website_dead"]
    pitched = [e for e in entries if e.get("pitch_file")]
    failed = [e for e in entries if e.get("last_error")]
    replies = [e for e in entries if e.get("outcome") == "Replied"]
    calls = [e for e in entries if e.get("outcome") == "Call booked"]
    not_replied = [e for e in entries if e.get("outcome") == "No reply"]
    not_interested = [e for e in entries if e.get("outcome") == "Not interested"]
    still_new = [e for e in entries if e.get("outcome") == "New"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    headline = f"Found: {len(entries)}. Qualified: {qualified}. Pitched: {len(pitched)}. Replies: {len(replies)}. Calls booked: {len(calls)}."
    lines = [
        f"# LeadForge report {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        headline,
        "",
        "## Found",
        f"Total leads in the store: {len(entries)}",
        "",
        "## Qualified",
        f"No website confirmed: {by_class['no_website_confirmed']}",
        f"Website dead: {by_class['website_dead']}",
        f"Has website: {by_class['has_website']}",
        f"Unknown: {by_class['unknown']}",
        "Confirmed means the Google listing shows no website and the website reader found none either. LeadForge never claims more than the data shows.",
        "",
        "## Pitched",
        f"Pitched leads: {len(pitched)}",
    ]
    for entry in pitched:
        lines.append(f"- {entry.get('name', '')} ({entry.get('pitch_language', '')}, {entry.get('pitch_region', '')})")
    lines += ["", "## Failed"]
    if failed:
        for entry in failed:
            lines.append(f"- {entry.get('name', '')}: {entry.get('last_error', '')}")
    else:
        lines.append("No failed leads recorded.")
    lines += [
        "",
        "## Replies",
        f"Replies: {len(replies)}",
        "",
        "## Calls booked",
        f"Calls booked: {len(calls)}",
        "",
        "## Not replied",
        f"Not replied: {len(not_replied)}",
        "",
        "## Not interested",
        f"Not interested: {len(not_interested)}",
        "",
        "## Still new",
        f"Still new: {len(still_new)}",
        "",
    ]
    path = REPORTS_DIR / f"report-{stamp}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def list_reports():
    ensure_storage()
    reports = []
    for path in sorted(REPORTS_DIR.glob("report-*.md"), reverse=True):
        headline = ""
        try:
            text_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(text_lines) > 1:
                headline = text_lines[1].strip()
        except OSError:
            pass
        reports.append({"name": path.name, "path": path, "headline": headline, "modified": path.stat().st_mtime})
    return reports


def render_report_text(text):
    out = []
    in_list = False
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3 style='margin:16px 0 6px;font-size:15px'>{html.escape(line[3:])}</h3>")
        elif line.startswith("# "):
            out.append(f"<h2 style='margin:0 0 8px;font-size:18px'>{html.escape(line[2:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul style='margin:6px 0 6px 18px;padding:0'>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:])}</li>")
        elif line:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p style='margin:5px 0'>{html.escape(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


REPORTS_STATE = {"notice": "", "error": ""}


def reports_page():
    store = sync_lead_store()
    entries = list(store.get("leads", {}).values())
    sync = chatwoot_sync_settings()
    last_sync = sync.get("last_sync") or {}
    if last_sync:
        sync_class = "success" if last_sync.get("result") == "done" else "warn"
        sync_html = f'<div class="callout {sync_class}" style="margin-bottom:14px">{icon("check" if sync_class == "success" else "alert")}<div><b>Reply sync:</b> {html.escape(last_sync.get("message", ""))} <span class="muted">({html.escape(last_sync.get("at", ""))})</span>{("<br>Fix: " + html.escape(last_sync.get("fix", ""))) if last_sync.get("fix") else ""}</div></div>'
    else:
        sync_html = '<div class="callout" style="margin-bottom:14px">' + icon("info") + '<div><b>Reply sync:</b> not checked yet. Save the Chatwoot sync settings in Settings, then click Check replies now. Replies are classified by simple keywords only in this version.</div></div>'
    notice_html = ""
    if REPORTS_STATE.get("error"):
        notice_html = f'<div class="callout error" style="margin-bottom:14px">{icon("alert")}<div>{html.escape(REPORTS_STATE["error"])}</div></div>'
    elif REPORTS_STATE.get("notice"):
        notice_html = f'<div class="callout success" style="margin-bottom:14px">{icon("check")}<div>{html.escape(REPORTS_STATE["notice"])}</div></div>'
    reports = list_reports()
    rows = ""
    for report in reports:
        when = datetime.fromtimestamp(report["modified"]).strftime("%Y-%m-%d %H:%M")
        rows += f'<div class="run-row"><div><b>{html.escape(report["name"])}</b><div class="muted">{html.escape(when)}</div></div><div>{html.escape(report["headline"])}</div></div>'
    if not rows:
        rows = '<div class="muted">No reports yet. Run the Full pipeline, or click Generate report now.</div>'
    latest_html = ""
    if reports:
        try:
            latest_text = reports[0]["path"].read_text(encoding="utf-8", errors="replace")
            latest_html = f'<section class="panel" style="margin-top:18px"><div class="panel-head"><div class="title-with-icon"><div class="icon-medallion green">{icon("file")}</div><div><h2>Latest report</h2><p>{html.escape(reports[0]["name"])}</p></div></div></div>{render_report_text(latest_text)}</section>'
        except OSError:
            latest_html = ""
    body = f"""
<div class="page-head"><div><h1>Reports</h1><p>Every Full pipeline run ends with a report. You can also make one now. Counts come from the lead store, so marking outcomes on the Leads page changes the next report.</p></div></div>
{notice_html}
{sync_html}
<section class="panel">
<div class="panel-head"><div class="title-with-icon"><div class="icon-medallion">{icon("file")}</div><div><h2>Lead reports</h2><p>{len(entries)} leads in the store. Found, qualified, pitched, replies and outcomes, in one place.</p></div></div>
<div style="display:flex;gap:10px;flex-wrap:wrap"><form method="post" action="/reports/generate"><button class="btn" type="submit">{icon("file", "sm")}Generate report now</button></form>
<form method="post" action="/reports/check-replies"><button class="btn ghost" type="submit">{icon("refresh", "sm")}Check replies now</button></form></div></div>
<div style="margin-top:16px">{rows}</div>
</section>
{latest_html}
"""
    return shell("reports", body)


def handle_report_generate():
    path = generate_report()
    REPORTS_STATE.update({"notice": f"Report saved as {path.name}.", "error": ""})
    return True


def handle_report_check_replies():
    status = check_chatwoot_replies()
    if status.get("result") == "done":
        REPORTS_STATE.update({"notice": status.get("message", ""), "error": ""})
    else:
        REPORTS_STATE.update({"notice": "", "error": status.get("message", "") + ((" Fix: " + status.get("fix", "")) if status.get("fix") else "")})
    return True


def handle_chatwoot_sync_save(form):
    base_url = _form_first(form, "chatwoot_base_url", "http://localhost:3001")
    account_id = _form_first(form, "chatwoot_account_id", "")
    api_token = _form_first(form, "chatwoot_api_token", "")
    save_chatwoot_sync_settings(base_url, account_id, api_token)
    SETTINGS_STATE["sync"] = {"kind": "success", "message": "Chatwoot reply sync settings saved on this PC. The token is masked here and never logged.", "fields": []}
    record_event("info", "settings", "SETTINGS_SYNC_SAVED", "Chatwoot reply sync settings were saved from the Settings page.")
    return True


# ---------------------------------------------------------------- health

def health_data():
    ensure_storage()
    ensure_app_ports_loaded()
    checks = []

    def add(name, severity, detail, fix=""):
        checks.append({"name": name, "status": severity, "detail": detail, "fix": fix})

    add("Dashboard", "ok", f"Running at {SERVER_STATE['url']}. Preferred port was {SERVER_STATE['preferred_port']}; actual port is {SERVER_STATE['port']}.")
    try:
        probe = DATA_DIR / ".health-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        add("Data folder", "ok", f"Writable: {DATA_DIR}")
    except OSError as exc:
        add("Data folder", "error", f"LeadForge could not write to {DATA_DIR}: {exc}", "Check folder permissions and antivirus blocking, then restart LeadForge.")

    scraper = scraper_state()
    if scraper["ready"]:
        add("Lead finder program", "ok", f"Found and executable: {scraper['path']}")
    elif scraper["found"]:
        add("Lead finder program", "error", f"Found but not executable: {scraper['path']}", "Check file permissions or antivirus quarantine.")
    else:
        add("Lead finder program", "error", f"Not found: {scraper['path']}", "Check that folder 1 contains google-maps-scraper.exe.")

    crawl = crawl_setup_state()
    if crawl["ready"]:
        add("Website reader", "ok", f"crawl4ai Python found: {crawl['python']}")
    else:
        add("Website reader", "warning", "The leads still work, but website notes may be skipped.", "Run 2-understand-crawl4ai/setup_crawl4ai.bat once.")

    dstatus, ddetail = docker_status()
    if dstatus == "ready":
        add("Docker", "ok", ddetail)
    elif dstatus == "missing":
        add("Docker", "warning", ddetail, docker_fix(dstatus))
    else:
        add("Docker", "warning", "Docker is installed but the daemon did not answer. Apps cannot start until it is running.", docker_fix(dstatus))

    sync_settings = chatwoot_sync_settings()
    last_sync = sync_settings.get("last_sync") or {}
    if not sync_settings.get("account_id"):
        add("Chatwoot reply sync", "warning", "Not set up yet. Replies will not be checked automatically.", "Open Settings and save the Chatwoot reply sync base URL, account ID and API access token.")
    elif last_sync.get("result") == "done":
        add("Chatwoot reply sync", "ok", last_sync.get("message", "Last check finished."), "")
    elif last_sync:
        add("Chatwoot reply sync", "warning", last_sync.get("message", "The last reply check did not finish."), last_sync.get("fix", "") or "Open Reports and click Check replies now to retry.")
    else:
        add("Chatwoot reply sync", "warning", "Set up, but replies have not been checked yet.", "Open Reports and click Check replies now.")

    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_gb = usage.free / (1024 ** 3)
        free_pct = (usage.free / usage.total * 100) if usage.total else 0
        severity = "error" if free_gb < 1 or free_pct < 2 else "warning" if free_gb < 5 or free_pct < 5 else "ok"
        add("Disk space", severity, f"{free_gb:.1f} GB free ({free_pct:.1f} percent).", "Free disk space before starting large Docker apps." if severity != "ok" else "")
    except OSError as exc:
        add("Disk space", "warning", f"Could not read disk space: {exc}")

    latest = latest_data_state()
    if latest["available"]:
        add("Latest lead list", "ok", f"Last good list has {latest['rows']} leads.")
    elif latest["status"] == "malformed":
        add("Latest lead list", "error", latest["error"], "Run the pipeline again. The malformed file was not used as a good list.")
    elif latest.get("meta", {}).get("last_result") == "zero":
        add("Latest lead list", "ok", "The latest completed search returned 0 leads. No good list is being hidden or overwritten.")
    else:
        add("Latest lead list", "ok", "No lead list has been saved yet.")

    app_rows = []
    for app in APPS:
        entry = app_assignment(app["id"])
        status = app_display_status(app)
        mappings = []
        for key, info in entry.get("ports", {}).items():
            mappings.append({
                "key": key,
                "label": info.get("label", key),
                "service": info.get("service", ""),
                "container_port": info.get("container_port"),
                "preferred_port": info.get("preferred_port"),
                "actual_port": info.get("actual_port"),
                "switched": bool(info.get("switched")),
                "state": port_state(int(info.get("actual_port", 0))),
            })
        severity = "ok"
        if status["code"] in ("setup_needed", "start_failed"):
            severity = "error"
        elif status["code"] in ("docker_missing", "docker_stopped", "starting"):
            severity = "warning"
        app_rows.append({
            "id": app["id"],
            "name": app["name"],
            "preferred_port": int(app["preferred_port"]),
            "actual_port": int(entry["actual_port"]),
            "url": entry["url"],
            "switched": bool(entry.get("switched")),
            "status": status["code"],
            "status_label": status["label"],
            "message": status["message"],
            "fix": status["fix"],
            "severity": severity,
            "ports": mappings,
        })

    overall = "ok"
    if any(c["status"] == "error" for c in checks) or any(a["severity"] == "error" for a in app_rows):
        overall = "needs_attention"
    elif any(c["status"] == "warning" for c in checks) or any(a["severity"] == "warning" for a in app_rows):
        overall = "warning"
    return {
        "app": "LeadForge",
        "generated_at": now_iso(),
        "overall": overall,
        "server": {
            "host": SERVER_STATE["host"],
            "port": SERVER_STATE["port"],
            "url": SERVER_STATE["url"],
            "pid": os.getpid(),
            "started_at": SERVER_STATE.get("started_at", ""),
            "preferred_port": SERVER_STATE["preferred_port"],
            "token": SERVER_STATE["token"],
        },
        "checks": checks,
        "apps": app_rows,
        "errors": recent_errors(12),
        "error_log": str(ERRORS_FILE),
        "main_log": str(MAIN_LOG_FILE),
    }


def _severity_html(severity):
    if severity == "ok":
        return '<span class="status-pill ok"><span class="status-dot ok"></span>OK</span>'
    if severity == "error":
        return '<span class="status-pill error"><span class="status-dot bad"></span>Needs attention</span>'
    return '<span class="status-pill warn"><span class="status-dot warn"></span>Check</span>'


def _health_check_icon(name):
    lowered = name.lower()
    if "dashboard" in lowered:
        return "activity"
    if "data folder" in lowered:
        return "folder"
    if "lead finder" in lowered:
        return "search"
    if "website" in lowered:
        return "globe"
    if "docker" in lowered:
        return "server"
    if "disk" in lowered:
        return "database"
    if "lead list" in lowered:
        return "file"
    return "info"


def _check_detail_summary(check):
    name = check.get("name", "")
    detail = check.get("detail", "")
    if name == "Data folder":
        return "The LeadForge data folder is writable." if check.get("status") == "ok" else detail
    if name == "Lead finder program":
        if check.get("status") == "ok":
            return "Found in folder 1 and ready to run."
        if "not executable" in detail:
            return "Found in folder 1, but it cannot run yet."
        return "Not found in folder 1."
    if name == "Website reader" and check.get("status") == "ok":
        return "crawl4ai setup was found and is ready."
    return detail


def _app_status_pill(app):
    code = app.get("status", "")
    label = html.escape(app.get("status_label", "Unknown"))
    if code == "running":
        return f'<span class="status-pill ok"><span class="status-dot ok"></span>{label}</span>'
    if code in ("starting", "working", "docker_missing", "docker_stopped"):
        return f'<span class="status-pill warn"><span class="status-dot warn"></span>{label}</span>'
    if code in ("setup_needed", "start_failed"):
        return f'<span class="status-pill error"><span class="status-dot bad"></span>{label}</span>'
    return f'<span class="status-pill info"><span class="status-dot warn"></span>{label}</span>'


def _format_health_time(value):
    try:
        return datetime.fromisoformat(str(value)).strftime("%d %b %Y, %H:%M")
    except Exception:
        return str(value or "")


def health_page():
    data = health_data()
    check_cards = ""
    for check in data["checks"]:
        tone = "green" if check["status"] == "ok" else "red" if check["status"] == "error" else ""
        fix = f'<div class="fix-line"><b>Fix:</b> {html.escape(check["fix"])}</div>' if check.get("fix") else ""
        check_cards += f"""
<article class="panel check-card">
<div class="check-head"><div class="icon-medallion {tone}">{icon(_health_check_icon(check['name']))}</div><h3>{html.escape(check['name'])}</h3>{_severity_html(check['status'])}</div>
<p class="check-detail" title="{html.escape(check['detail'], quote=True)}">{html.escape(_check_detail_summary(check))}</p>{fix}
</article>"""
    app_rows = ""
    for app in data["apps"]:
        web_info = next((info for info in app["ports"] if info["key"] == "web"), None)
        if web_info:
            web_line = f"Web: host {web_info['actual_port']} to app {web_info['container_port']} ({html.escape(web_info['state'])})"
        else:
            web_line = f"Web: host {app['actual_port']}"
        helper_items = ""
        helper_count = 0
        for info in app["ports"]:
            if info["key"] == "web":
                continue
            helper_count += 1
            switched = " (switched)" if info["switched"] else ""
            helper_items += f"<li>{html.escape(info['label'])}: {info['preferred_port']} to {info['actual_port']} ({html.escape(info['state'])}{switched})</li>"
        helpers = f'<details class="dep-details"><summary>{helper_count} helper ports</summary><ul>{helper_items}</ul></details>' if helper_count else ""
        switched = '<span class="switchchip">Port switched</span>' if app["switched"] else ""
        fix = f'<div class="state-fix"><b>Fix:</b> {html.escape(app["fix"])}</div>' if app.get("fix") else ""
        app_rows += f"""
<tr><td><b>{html.escape(app['name'])}</b>{switched}<div class="state-message">Usual web port {app['preferred_port']}</div></td>
<td>{_app_status_pill(app)}<div class="state-message">{html.escape(app['message'])}</div>{fix}</td>
<td><a class="port-address" href="{html.escape(app['url'])}" target="_blank" rel="noopener">{html.escape(app['url'])}</a><div class="state-message">Actual port <b>{app['actual_port']}</b></div></td>
<td>{html.escape(web_line)}{helpers}</td></tr>"""
    errors_html = ""
    if data["errors"]:
        items = ""
        for event in data["errors"]:
            level = str(event.get("level", "warning")).lower()
            item_class = "error" if level == "error" else "warning"
            detail = ""
            if event.get("detail"):
                detail = f"<details><summary>Technical detail</summary><p class='mono'>{html.escape(event.get('detail', ''))}</p></details>"
            fix = f"<div class='fix-line'><b>Suggested fix:</b> {html.escape(event.get('fix', ''))}</div>" if event.get("fix") else ""
            items += f"""
<article class="error-item {item_class}"><div class="error-rail"></div><div>
<div class="error-meta"><span>{html.escape(_format_health_time(event.get('time', '')))}</span><span class="status-pill {'error' if level == 'error' else 'warn'}">{html.escape(level.title())}</span><span>{html.escape(event.get('area', ''))}</span><span class="mono">{html.escape(event.get('code', ''))}</span></div>
<p>{html.escape(event.get('message', ''))}</p>{detail}{fix}</div></article>"""
        errors_html = f'<div class="error-list">{items}</div>'
    else:
        errors_html = f"""
<div class="empty-state" style="padding:26px 10px 18px">
<div class="empty-mark" style="width:62px;height:62px;border-radius:18px"><span style="color:var(--green)">{icon("check", "lg")}</span></div>
<h2 style="font-size:18px">No recent errors recorded</h2>
<p>LeadForge has not logged a warning or error here. This is a clean recent history, not a promise that nothing can fail.</p>
</div>"""
    overall_label = {"ok": "All main checks look OK", "warning": "Working, with warnings", "needs_attention": "Needs attention"}.get(data["overall"], data["overall"])
    ring_class = "error" if data["overall"] == "needs_attention" else "warn" if data["overall"] == "warning" else ""
    hero_icon = "alert" if data["overall"] == "needs_attention" else "shield"
    body = f"""
<div class="page-head">
<div><div class="eyebrow">Control room</div><h1>System health</h1><p>Live checks for the dashboard, lead tools, Docker, app ports and recent problems. Fix lines stay short and point to the next useful action.</p></div>
<div class="head-actions"><a class="btn ghost" href="/health">{icon("refresh", "sm")}Refresh health</a></div>
</div>

<section class="panel health-hero">
<div class="health-ring {ring_class}"><div class="health-ring-inner">{icon(hero_icon, "lg")}</div></div>
<div class="health-hero-main"><h2>{html.escape(overall_label)}</h2><p>LeadForge is running locally. Ports can move automatically when another program is using the usual one.</p>
<div class="health-facts"><span class="fact-chip">{icon("globe", "sm")}<span>Address</span><b class="mono">{html.escape(data['server']['url'])}</b></span><span class="fact-chip">Preferred port <b>{data['server']['preferred_port']}</b></span><span class="fact-chip">Actual port <b>{data['server']['port']}</b></span><span class="fact-chip">{icon("clock", "sm")}Checked <b>{html.escape(_format_health_time(data['generated_at']))}</b></span></div></div>
<div class="health-actions"><a class="btn" href="/apps">{icon("grid", "sm")}Open Apps</a></div>
</section>

<div class="check-grid">{check_cards}</div>

<section class="panel ports-wrap">
<div class="panel-head"><div class="title-with-icon"><div class="icon-medallion blue">{icon("server")}</div><div><h2>App ports and state</h2><p>The Open address is the one to use. Helper port details stay tucked away until you need them.</p></div></div></div>
<div class="table-shell"><table><thead><tr><th>App</th><th>State</th><th>Open address</th><th>Ports</th></tr></thead><tbody>{app_rows}</tbody></table></div>
</section>

<section class="panel" style="margin-top:16px">
<div class="panel-head toolbar">
<div class="title-with-icon"><div class="icon-medallion red">{icon("alert")}</div><div><h2>Recent errors</h2><p>Newest problems first, with the friendly message before the technical detail.</p></div></div>
<form method="post" action="/health/clear-errors"><button class="dangerbtn" type="submit">Clear recent errors</button></form>
</div>
{errors_html}
<details class="log-files"><summary>Diagnostic log files</summary><div>Recent error log<br><span class="mono">{html.escape(data['error_log'])}</span><br>Main LeadForge log<br><span class="mono">{html.escape(data['main_log'])}</span></div></details>
</section>"""
    return shell("health", body)


def branded_error_page(title, message):
    body = f"""
<div class="page-head"><div><div class="eyebrow">LeadForge</div><h1>{html.escape(title)}</h1><p>LeadForge is still available. The safest next step is to check the control room.</p></div></div>
<section class="panel">
<div class="title-with-icon"><div class="icon-medallion red">{icon("alert")}</div><div><h2>{html.escape(title)}</h2><p>{html.escape(message)}</p></div></div>
<div style="margin-top:18px"><a class="btn" href="/health">{icon("activity", "sm")}Open Health</a></div>
</section>"""
    return shell("health", body)

# ---------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    server_version = "LeadForge"
    _headers_sent = False

    def log_message(self, *args):
        pass

    def _send(self, code, data, ctype="text/html; charset=utf-8"):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(code)
        self._headers_sent = True
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, path):
        self.send_response(303)
        self._headers_sent = True
        self.send_header("Location", path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _error_response(self, exc, path):
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log_error("web", "HTTP_INTERNAL_ERROR", "A dashboard page hit an internal problem, but LeadForge kept running.", f"Path: {path}\n{detail}", "Open Health and send the error log to Muse if this repeats.")
        if not self._headers_sent:
            try:
                self._send(500, branded_error_page("Something went wrong", "A dashboard page hit an internal problem. LeadForge kept running, and the technical detail was saved in the error log."))
            except Exception:
                pass

    def do_GET(self):
        self._headers_sent = False
        try:
            self._get_impl()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._error_response(exc, self.path)

    def _get_impl(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        if os.environ.get("LEADFORGE_TEST_ROUTES") == "1" and path == "/__test__/error":
            raise RuntimeError("Deliberate LeadForge test error")
        if path == "/":
            self._send(200, run_page())
        elif path == "/leads":
            self._send(200, leads_page())
        elif path == "/writer":
            self._send(200, writer_page(query))
        elif path == "/settings":
            self._send(200, settings_page())
        elif path == "/guide":
            self._send(200, guide_page())
        elif path == "/reports":
            self._send(200, reports_page())
        elif path == "/settings/pull-status":
            self._send(200, json.dumps(pull_job_snapshot()), "application/json")
        elif path == "/writer/status":
            self._send(200, json.dumps(writer_job_snapshot()), "application/json")
        elif path == "/apps":
            self._send(200, apps_page())
        elif path == "/health":
            self._send(200, health_page())
        elif path == "/api/health":
            self._send(200, json.dumps(health_data(), ensure_ascii=False), "application/json")
        elif path == "/api/errors":
            self._send(200, json.dumps({"errors": recent_errors(25)}), "application/json")
        elif path == "/status":
            with JOB_LOCK:
                data = {
                    "state": JOB["state"],
                    "step": JOB["step"],
                    "error": JOB["error"],
                    "error_code": JOB.get("error_code", ""),
                    "notice": JOB.get("notice", ""),
                    "leads": JOB["leads"],
                    "log": list(JOB["log"]),
                    "result_kind": JOB.get("result_kind", ""),
                    "enrich_attempted": JOB.get("enrich_attempted", 0),
                    "enrich_succeeded": JOB.get("enrich_succeeded", 0),
                    "enrich_failed": JOB.get("enrich_failed", 0),
                    "enrich_skipped": JOB.get("enrich_skipped", 0),
                    "failed_websites": list(JOB.get("failed_websites", [])),
                    "started_at": JOB.get("started_at", ""),
                }
            self._send(200, json.dumps(data), "application/json")
        elif path == "/apps/status":
            self._send(200, json.dumps(apps_status_data()), "application/json")
        elif path == "/download/latest.csv":
            parsed = _parse_results_strict(LATEST_CSV)
            if parsed["status"] == "valid" and parsed["rows"]:
                data = LATEST_CSV.read_bytes()
                self.send_response(200)
                self._headers_sent = True
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", 'attachment; filename="leads-latest.csv"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                detail = parsed["error"] or "There is no good lead list to download yet."
                self._send(404, branded_error_page("No good CSV yet", detail))
        elif path == "/logo.svg":
            logo_file = APP_DIR / "logo.svg"
            if logo_file.exists():
                self._send(200, logo_file.read_bytes(), "image/svg+xml")
            else:
                self._send(404, b"", "image/svg+xml")
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, branded_error_page("Page not found", "That LeadForge page does not exist."))

    def do_POST(self):
        self._headers_sent = False
        try:
            self._post_impl()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._error_response(exc, self.path)

    def _post_impl(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length < 0 or length > 1_000_000:
            self._send(400, branded_error_page("Request too large", "LeadForge could not read that form safely."))
            return
        raw = self.rfile.read(length) if length else b""
        form = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)

        def field(name, default=""):
            vals = form.get(name, [default])
            return vals[0].strip() if vals else default

        if path == "/run":
            with JOB_LOCK:
                already_running = JOB["state"] == "running"
                if already_running:
                    JOB["notice"] = "A pipeline job is already running. Wait for it to finish before starting another."
            if already_running:
                log_warning("pipeline", "JOB_ALREADY_RUNNING", "A second pipeline start was refused because a job is already running.", "", "Wait for the current job to finish.")
                self._redirect("/")
                return

            location = re.sub(r"\s+", " ", field("location")).strip()
            business_type = re.sub(r"\s+", " ", field("business_type")).strip()
            max_raw = field("max_results", "30")
            validation = ""
            max_results = 30
            if not location or not business_type:
                validation = "Type both a location and a business type first, then click Run."
            elif len(location) < 2 or len(location) > 80:
                validation = "Location must be between 2 and 80 characters."
            elif len(business_type) < 2 or len(business_type) > 80:
                validation = "Business type must be between 2 and 80 characters."
            else:
                try:
                    max_results = int(max_raw)
                    if max_results < 1 or max_results > 200:
                        validation = "Max results must be a whole number between 1 and 200."
                except ValueError:
                    validation = "Max results must be a whole number between 1 and 200."
            if validation:
                job_set(
                    state="idle", step="", error="", error_code="VALIDATION_ERROR", notice=validation,
                    location=location, business_type=business_type,
                    max_results=max_results if max_results else 30,
                )
                log_warning("pipeline", "JOB_VALIDATION_FAILED", validation, f"Location={location!r}; type={business_type!r}; max={max_raw!r}", "Correct the form and click Run again.")
                self._redirect("/")
                return

            with JOB_LOCK:
                if JOB["state"] == "running":
                    JOB["notice"] = "A pipeline job is already running. Wait for it to finish before starting another."
                    self._redirect("/")
                    return
                JOB.update({
                    "state": "running", "step": "Starting", "log": [], "error": "", "error_code": "",
                    "notice": "", "location": location, "business_type": business_type,
                    "max_results": max_results, "leads": 0, "result_kind": "",
                    "enrich_attempted": 0, "enrich_succeeded": 0, "enrich_failed": 0,
                    "enrich_skipped": 0, "failed_websites": [], "started_at": now_iso(),
                })
            mode = _form_first(form, "mode", "full")
            if mode not in ("full", "find"):
                mode = "full"
            threading.Thread(target=run_pipeline, args=(location, business_type, max_results, mode), daemon=True).start()
            self._redirect("/")
        elif path == "/apps/action":
            app_id = field("app")
            action = field("action", "start")
            if action not in ("start", "stop"):
                self._send(400, branded_error_page("Unknown app action", "LeadForge only supports Start and Stop for apps."))
                return
            if app_id == "all" and action == "start":
                start_all_thread()
            elif app_id in APPS_BY_ID:
                app_action_thread(app_id, action)
            else:
                self._send(404, branded_error_page("App not found", "That pipeline app does not exist."))
                return
            self._redirect("/apps")
        elif path == "/settings/save":
            app_id = field("app")
            if app_id not in APPS_BY_ID:
                self._send(404, branded_error_page("App not found", "That pipeline app does not exist."))
                return
            handle_settings_save(APPS_BY_ID[app_id], form)
            self._redirect("/settings")
        elif path == "/settings/ai":
            handle_ai_settings_save(form)
            self._redirect("/settings#free-ai")
        elif path == "/settings/check-ai":
            handle_local_ai_check()
            self._redirect("/settings#free-ai")
        elif path == "/settings/pull-model":
            handle_model_pull()
            self._redirect("/settings#free-ai")
        elif path == "/settings/chatwoot-sync":
            handle_chatwoot_sync_save(form)
            self._redirect("/settings#setup-chatwoot-sync")
        elif path == "/reports/generate":
            handle_report_generate()
            self._redirect("/reports")
        elif path == "/reports/check-replies":
            handle_report_check_replies()
            self._redirect("/reports")
        elif path == "/leads/outcome":
            outcome_key = _form_first(form, "key", "")
            outcome_value = _form_first(form, "outcome", "New")
            if outcome_key:
                set_lead_outcome(outcome_key, outcome_value)
            self._redirect("/leads")
        elif path == "/settings/playbook":
            handle_pitch_rules_save(form)
            self._redirect("/settings#pitch-rules")
        elif path == "/settings/playbook-reset":
            handle_pitch_rules_reset()
            self._redirect("/settings#pitch-rules")
        elif path == "/settings/check":
            app_id = field("app")
            if app_id not in APPS_BY_ID:
                self._send(404, branded_error_page("App not found", "That pipeline app does not exist."))
                return
            handle_settings_check(APPS_BY_ID[app_id])
            self._redirect("/settings")
        elif path == "/writer/generate":
            try:
                lead_index = int(float(field("lead", "0")))
            except (TypeError, ValueError):
                lead_index = 0
            output = field("output", "both")
            if output not in ("whatsapp", "email", "both"):
                output = "both"
            language = field("language", "english")
            if language not in ("english", "bangla"):
                language = "english"
            handle_writer_generate(form)
            self._redirect(f"/writer?lead={lead_index}&output={output}&language={language}")
        elif path == "/writer/batch":
            output = field("output", "both")
            if output not in ("whatsapp", "email", "both"):
                output = "both"
            language = field("language", "english")
            if language not in ("english", "bangla"):
                language = "english"
            handle_writer_batch(form)
            self._redirect(f"/writer?output={output}&language={language}")
        elif path == "/writer/manual":
            try:
                lead_index = int(float(field("lead", "0")))
            except (TypeError, ValueError):
                lead_index = 0
            output = field("output", "both")
            if output not in ("whatsapp", "email", "both"):
                output = "both"
            language = field("language", "english")
            if language not in ("english", "bangla"):
                language = "english"
            handle_writer_manual(form)
            self._redirect(f"/writer?lead={lead_index}&output={output}&language={language}")
        elif path == "/writer/manual-batch":
            output = field("output", "both")
            if output not in ("whatsapp", "email", "both"):
                output = "both"
            language = field("language", "english")
            if language not in ("english", "bangla"):
                language = "english"
            handle_writer_manual_batch(form)
            self._redirect(f"/writer?output={output}&language={language}")
        elif path == "/health/clear-errors":
            clear_error_log()
            self._redirect("/health")
        else:
            self._send(404, branded_error_page("Page not found", "That LeadForge action does not exist."))


class LeadForgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        exc_type, exc, tb = sys.exc_info()
        detail = "".join(traceback.format_exception(exc_type, exc, tb)) if exc_type else "Unknown server error"
        log_error("web", "HTTP_SERVER_ERROR", "The web server handled a broken connection or request.", detail, "Open Health if pages stop loading.")


def server_candidate_ports():
    end = min(65535, max(PORT_SCAN_END, PREFERRED_PORT + 100))
    return range(PREFERRED_PORT, end + 1)


def main():
    ensure_storage()
    load_app_ports()
    existing = probe_existing_server()
    if existing:
        server = existing.get("server", {})
        try:
            port = int(server.get("port"))
        except Exception:
            port = PREFERRED_PORT
        SERVER_STATE.update({
            "port": port,
            "url": server.get("url") or f"http://{HOST}:{port}",
            "started_at": server.get("started_at", ""),
            "token": server.get("token", SERVER_STATE["token"]),
            "pid": int(server.get("pid") or os.getpid()),
        })
        write_server_info()
        print("LeadForge is already running.")
        print(f"Open {SERVER_STATE['url']} in your browser.")
        return

    server = None
    last_error = None
    for port in server_candidate_ports():
        try:
            candidate = LeadForgeHTTPServer((HOST, port), Handler)
            SERVER_STATE["port"] = port
            SERVER_STATE["url"] = f"http://{HOST}:{port}"
            server = candidate
            break
        except OSError as exc:
            last_error = exc
            continue
    if server is None:
        message = f"No free dashboard port was found from {PREFERRED_PORT} upward."
        detail = str(last_error or "")
        log_error("system", "DASHBOARD_PORT_UNAVAILABLE", message, detail, "Close a program using these local ports, then run LeadForge.bat again.")
        print("LeadForge could not start.")
        print(message)
        print(f"Error log: {ERRORS_FILE}")
        print(f"Main log: {MAIN_LOG_FILE}")
        raise SystemExit(1)

    SERVER_STATE["started_at"] = now_iso()
    write_server_info()
    atexit.register(remove_server_info_if_mine)
    record_event("info", "system", "DASHBOARD_STARTED", f"LeadForge started at {SERVER_STATE['url']}.", f"PID {os.getpid()}")
    print("LeadForge dashboard is running.")
    print(f"Open {SERVER_STATE['url']} in your browser.")
    if SERVER_STATE["port"] != PREFERRED_PORT:
        print(f"Port {PREFERRED_PORT} was busy, so LeadForge switched to {SERVER_STATE['port']}.")
    print("Keep this window open while you use it. Close it to stop the dashboard.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("LeadForge stopped.")
    finally:
        server.server_close()
        remove_server_info_if_mine()


if __name__ == "__main__":
    main()
