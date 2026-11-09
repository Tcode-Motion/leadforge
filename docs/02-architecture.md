# 02. Architecture

LeadForge is deliberately small: one Python file serves the dashboard,
runs the jobs, and talks to the seven bundled tools. This page is the map
a developer needs before changing anything.

## Components

| Part | Where | What it does |
| --- | --- | --- |
| Launcher | `LeadForge.bat`, `dashboard/wait_and_open.ps1` | Starts the server with a fresh launch token and opens the browser at the real address |
| Dashboard server | `dashboard/app.py` | HTTP server, pages, pipeline job, app control, writer, settings, reports, health |
| Website reader glue | `dashboard/enrich.py` | Runs crawl4ai for a list of websites, saves one note per site, prints summary lines the dashboard parses |
| Finder | `1-find-google-maps-scraper/` | gosom google-maps-scraper Windows binary, driven with queries and flags |
| Reader | `2-understand-crawl4ai/` | crawl4ai install plus `scrape.py` for ad hoc scraping |
| Server apps | folders 3 to 7 | listmonk, chatwoot, cal.diy, twenty, documenso, each with its upstream Docker Compose file |
| Tests | `tests/` | Regression suite helpers and the fault injection suite |

`dashboard/app.py` is about 6,400 lines and uses only the Python standard
library. There are no pip dependencies for the dashboard itself.

## Data flow, in text

```
Run page form
  -> POST /run
  -> run_pipeline() queues one background job (JOB_LOCK: one at a time)
  -> Stage 1 Find: scraper subprocess, strict CSV parse
       -> dashboard/data/latest.csv (replaced only after a valid parse)
       -> lead store sync (merge by phone)
  -> Stage 2 Read: enrich.py subprocess over up to 15 websites
       -> dashboard/data/notes/, ENRICH_SUMMARY parsed from stdout
  -> Stage 3 Qualify: compute_qualification() per lead
  -> Stage 4 Write (full mode): write_pitches_for_leads()
       -> AI route: cloud (ai_request), local (ai_request_local),
          or manual marking
       -> dashboard/data/pitches/*.md, store outcome becomes Pitched
  -> Stage 5 Check and report: generate_report()
       -> dashboard/data/reports/report-*.md
Browser polls GET /status for the live console.
```

App control flow:

```
Apps page -> POST /apps/action -> _do_app_action()
  -> allocate_app_ports() picks free host ports, persists them
  -> generate_runtime_compose() writes docker-compose.leadforge.yml
     (a copy of the upstream compose with host ports replaced)
  -> _compose_command() runs docker compose config, then up or down,
     with timeouts (config 120s, start 900s, stop 300s)
```

## Pages and routes

GET pages: `/` (Run), `/leads`, `/writer`, `/apps`, `/settings`,
`/guide`, `/reports`, `/health`. Each page is a `*_page()` function near
the end of app.py, wrapped by `shell()`.

JSON and helper GET routes: `/api/health`, `/api/errors`, `/status`,
`/apps/status`, `/writer/status`, `/settings/pull-status`,
`/download/latest.csv`, `/logo.svg`, `/favicon.ico`.

POST routes: `/run`, `/apps/action`, `/settings/save`, `/settings/ai`,
`/settings/check-ai`, `/settings/pull-model`, `/settings/chatwoot-sync`,
`/settings/check`, `/settings/playbook`, `/settings/playbook-reset`,
`/reports/generate`, `/reports/check-replies`, `/leads/outcome`,
`/writer/generate`, `/writer/batch`, `/writer/manual`,
`/writer/manual-batch`, `/health/clear-errors`.

Request handling lives in `class Handler` (`do_GET` / `do_POST` wrapping
`_get_impl` / `_post_impl` in a catch-all) on
`class LeadForgeHTTPServer`. POST bodies are capped at 1,000,000 bytes.

## The port system

- The dashboard prefers the port in `LEADFORGE_PORT`, default 8790, and
  scans upward to 8899 for the first port it can bind
  (`server_candidate_ports()`).
- Before binding, `probe_existing_server()` checks whether a LeadForge
  dashboard is already running (matching health payload and launch
  token), so a second launch opens the existing one.
- Each server app has a preferred web port (9000, 3001, 3002, 3003,
  3004) plus dependent database and cache ports.
  `allocate_app_ports()` moves any busy host port to the next free one
  and persists the result in `dashboard/data/app-ports.json`.
- Because Docker Compose merges port lists from multiple files,
  LeadForge does not use override files for ports. It generates a full
  runtime copy, `docker-compose.leadforge.yml`, with the chosen host
  ports written in, and injects matching app URLs (for example
  `NEXT_PUBLIC_WEBAPP_URL`) so each app knows its real address.

## The server-info handshake

On startup the server writes `dashboard/data/server-info.json` with the
host, the actual port, the full URL, the process id, the start time and
the launch token from the environment. `wait_and_open.ps1` polls that
file until the token matches this launch and the health endpoint
answers, then opens the browser at the recorded URL. That is why the
launcher always lands on the real port, even after a switch.

## Data files

All live state is under `dashboard/data/`:

| File or folder | Contents |
| --- | --- |
| `latest.csv`, `latest-meta.json` | Last good scraper results and run metadata |
| `leads.json` | The lead store: one record per lead, merged by phone |
| `ai-settings.json` | AI provider choice, masked key storage, playbook, chatwoot sync settings |
| `app-ports.json` | Persisted per app port assignments |
| `server-info.json` | This run's address and launch token |
| `chatwoot-sync.json` | Last reply check status |
| `runs/`, `notes/` | Per run working files and website notes |
| `pitches/` | One markdown pitch file per pitched lead |
| `reports/` | Generated markdown reports |
| `logs/leadforge.log`, `logs/errors.jsonl` | Structured event logs |

JSON state is written with `atomic_write_json()`. Reads go through
`read_json_file()` with defaults, and the lead store additionally logs
STORE_CORRUPT when the file exists but cannot be parsed, so a corrupt
file shows up in the error timeline instead of failing quietly.

## Logs and errors

`record_event()` writes structured JSON lines. Errors and warnings also
go to `errors.jsonl`. Both files rotate at about 1 MB
(`_rotate_if_needed()`, `MAX_LOG_BYTES = 1_000_000`, one `.1` backup).
Secrets are stripped by `sanitize_text()` before anything is logged.
The Health page reads the recent error entries and shows each code with
its plain language fix.

## Error handling design

- Every route handler runs inside a catch-all. An unexpected exception
  becomes the branded error page ("Something went wrong"), an
  HTTP_INTERNAL_ERROR entry in errors.jsonl, and the server keeps
  serving. A hidden test route, `GET /__test__/error`, raises on purpose
  and only exists when `LEADFORGE_TEST_ROUTES=1`.
- Background steps report failure codes, never tracebacks: scraper codes
  (SCRAPER_NOT_FOUND, SCRAPER_TIMEOUT, SCRAPER_CSV_MALFORMED and
  friends), app codes (APP_SETUP_NEEDED, DOCKER_MISSING and friends) and
  AI codes (AI_NO_KEY, AI_TIMEOUT, AI_RATE_LIMIT and friends). The full
  list with fixes is docs/09-troubleshooting.md.
- Timeouts are set on every external call: AI requests default to 30
  seconds (`LEADFORGE_AI_TIMEOUT`, clamped 1 to 60), the scraper to 900
  seconds (`LEADFORGE_SCRAPER_TIMEOUT`, clamped 10 to 3600), website
  reading to 60 seconds per site clamped between 60 and 900 total, and
  Docker commands to 120, 900 and 300 seconds as above.
