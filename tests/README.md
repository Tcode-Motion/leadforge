# LeadForge tests

Two suites live here. Both run against disposable copies of the pack and
never touch real data. Both print PASS or FAIL per check and exit non
zero when any check fails.

## Fault injection suite (19 checks)

    python3 run_fault_tests.py

Covers the crash hardening promises: corrupt leads.json (and the
STORE_CORRUPT log entry), corrupt ai-settings.json and app-ports.json,
an AI endpoint returning garbage, a JSON array, and a hang past the
timeout, garbage writer lead indexes, a 200 KB form field, a POST body
over the 1 MB cap, branded 404 pages for unknown GET and POST routes,
Stop with nothing running, an empty results CSV, a CSV with wrong
headers, a deleted data directory, a busy preferred port, a missing
scraper binary, a double Start click, and a deliberate handler crash
through the hidden test route. Every check also asserts the dashboard
still answers GET / with 200 afterwards.

Source tree: the repository copy by default, or the LF_SRC environment
variable. The AI stub for this suite is fault_stub_ai.py, driven by the
LF_FAULT_MODE file.

## v6 regression helpers

stub_ai.py and stub_chatwoot.py are the stub servers the v6 regression
suite runs against:

- stub_ai.py serves fake Gemini, Groq and local AI answers on
  127.0.0.1:8977. Its behaviour mode, counters and pull mode are read
  from files in /tmp/lf_tests (stub_mode, stub_count, pull_mode,
  requests.log), which the suite creates.
- stub_chatwoot.py serves fake chatwoot conversations on 127.0.0.1:8979,
  including a bad token case.

The v6 suite itself (64 checks: settings saves and secret handling, AI
routes and error mapping, playbook in every prompt path, qualification
fixtures, the full pipeline stages, chatwoot sync, reports, and the v4
and v5 behaviours) is run by the maintainer against a scratch copy with
these stubs and a fake Docker on PATH. Results from the repository
edition run: 64 of 64 passed, together with 19 of 19 fault checks,
83 checks in total.
