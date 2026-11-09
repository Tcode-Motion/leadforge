# Changelog

All notable changes to LeadForge, newest first. Versions v1 to v5 were the
PC pack evolution. Version v6 added the writer, the settings forms and the
full pipeline. The repository edition keeps the v6 app and adds the
repository structure, the documentation set, fresh screenshots and a crash
hardening pass.

## Repository edition (2026-11-09)

- The pack is now a proper git repository: README, LICENSE, CHANGELOG,
  CONTRIBUTING, SECURITY, CODE OF CONDUCT, .gitignore and .gitattributes.
- Full documentation set under docs/, including docs/FEATURES.md, the
  complete feature map with the page and code area for every feature.
- Fresh screenshots for all eight dashboard pages under screenshots/,
  captured from a disposable copy with clearly fake demo leads.
- Crash hardening in dashboard/app.py:
  - A corrupt or unreadable leads.json now logs STORE_CORRUPT and the
    dashboard starts from an empty store view instead of failing quietly.
  - Bad lead index values in writer forms (text, decimals) are parsed
    safely and can no longer produce a 500 page.
  - Writer generation failures that are not AI errors now show a friendly
    writer message instead of the generic error page.
  - JSON answers with the wrong shape (from the local AI, the cloud AI,
    the model pull stream, an existing dashboard, or chatwoot) are treated
    as provider errors instead of crashing the request.
  - Chatwoot reply check failures are recorded with a friendly fix on the
    sync status instead of raising.
- Test suites moved into tests/: the v6 regression suite helpers and the
  new fault injection suite (19 checks: corrupt files, hanging AI, missing
  scraper, busy port, oversized forms, double start, deliberate crash).

## v6 (2026-11-08)

- Settings page with in-UI setup forms for chatwoot, cal.diy, twenty and
  documenso. Secrets can be auto generated, are shown only as a masked
  Saved note afterwards, and a blank field on re-save keeps the old value.
  listmonk gets a guidance card because its SMTP is set inside listmonk.
- Live Setup status panel on Settings and Guide, naming the missing field
  names per app. Saving a complete setup flips the app state out of
  Setup needed. Per app Check setup runs a real compose config validation.
- Free AI Writer with three routes:
  - Cloud: Google Gemini (gemini-2.0-flash) or Groq
    (llama-3.3-70b-versatile) with a free API key stored locally and masked.
  - Local AI: any OpenAI compatible local server (Ollama by default),
    with a status check and a one click model download with progress.
  - Manual web mode: copy an instruction, paste it into any web AI, paste
    the answer back. Strict reply markers, a batch form, and a saved web
    assistant setup that shortens later copies to lead blocks only.
- Pitch Playbook in Settings: editable rules and examples prepended to
  every prompt on every route. Output checker with exactly one automatic
  correction retry. AI style checker with one humanize rewrite pass.
- Full pipeline mode on the Run page: one Start runs Find, Read websites,
  Qualify, Write pitches, then Check and report, as five stages in one job.
  Find leads only mode keeps the older behaviour.
- Lead qualification classes: no_website_confirmed, website_dead,
  has_website, unknown, with the honest method note. Default pitch batch
  covers only the two no website classes.
- Retry ladder for pitch writing, region language pack with Auto (by
  region) as the default, and a lead store (dashboard/data/leads.json)
  merged by phone with outcomes.
- What is working learning card on the Writer page, fed by marked outcomes.
- Reports page with an automatic report after every full pipeline run.
- Chatwoot reply check: matches open chatwoot conversations to leads by
  phone, flips outcomes to Replied, tags replies by simple keywords.

## v5 (2026-11-08)

- Professional command center redesign of the dashboard: left sidebar app
  shell with icon navigation, local system status card, command header on
  the Run page, CRM style Leads library, Apps control room with per tool
  icons and status pills, and a Health control room with a status ring,
  diagnostic cards, ports table and error timeline.
- Browser runtime errors cleaned to zero; desktop and true phone widths
  checked with no page level horizontal overflow.

## v4 (2026-11-08)

- Error management system. The dashboard scans for a free port from 8790
  upward and writes server-info.json; LeadForge.bat opens the real address
  through wait_and_open.ps1 and detects an already running dashboard.
- Per app port switching: busy web and dependent database or cache ports
  move to the next free port, persist in app-ports.json, and are applied
  through a generated docker-compose.leadforge.yml so upstream files stay
  untouched. App URLs follow the switched ports.
- Health page and /api/health, rotating logs in dashboard/data/logs/,
  friendly errors only in the UI, and job hardening: input validation,
  no duplicate concurrent jobs, scraper timeout, strict CSV parsing with
  the last good file preserved, and fault isolated website reading.

## v3 (2026-11-08)

- Rebrand to LeadForge, tagline "Find clients. Forge deals." New amber
  magnet logo, deep navy and amber interface, header bar, five step
  stepper, stat tiles and richer app cards. RUN_PIPELINE.bat replaced by
  LeadForge.bat.

## v2 (2026-11-08)

- One dashboard app (dashboard/app.py, Python standard library only) and
  one launcher that runs everything and opens a web GUI: Run page with
  location, business type and max results, Leads page with the results
  table and CSV download, Apps page with Start, Stop and Open per tool.

## v1 (2026-11-08)

- First PC pack: the seven free tools downloaded and staged in numbered
  folders with HOW_TO notes, starter queries, the Windows scraper binary,
  crawl4ai setup scripts, and compose files for the five server apps.
