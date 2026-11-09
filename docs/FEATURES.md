# LeadForge feature map

Every feature in LeadForge, where it lives, and how to use it. Page names
are the dashboard pages. Code areas are functions in
`dashboard/app.py` unless another file is named. This map is checked
against the code; if a feature is not listed here, it is not in the app.

## Launcher and server

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| One double click start | `LeadForge.bat` at the pack root | Double click the bat file; keep the black window open while you work |
| Browser opens at the real address | `dashboard/wait_and_open.ps1`, server info written by `main()` | Automatic: the launcher reads `dashboard/data/server-info.json` and opens the recorded URL |
| Already running detection | `probe_existing_server()` in app.py | Start the bat again; it opens the running dashboard instead of a second copy |
| Automatic dashboard port switching, 8790 to 8899 | `server_candidate_ports()`, `main()` in app.py | Nothing to do; if 8790 is busy the next free port is used and opened |
| Friendly startup failure | `LeadForge.bat` startup_failed path | If startup fails, the window stays open and names the two log files |

## Run page and the pipeline

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Full pipeline in one Start | Run page, `run_pipeline()` and `_execute_pipeline()` | Leave mode on Full pipeline and click Run search |
| Find leads only mode | Run page mode select, `_execute_pipeline()` | Pick Find leads only when you want just the raw list |
| Five stage stepper with live console | Run page, job status at `GET /status` | Watch the console; stages print one line each with counts |
| Search form validation | `JOB_VALIDATION_FAILED` path in the run handler | Location and business type need 2 to 80 characters; max results 1 to 200 |
| One job at a time | `JOB_LOCK` and the already running notice | A second Start while a job runs is refused politely |
| Live job status feed | `GET /status`, job state read under `JOB_LOCK` | Polled by the Run page; no action needed |
| Max results mapped to scroll depth | `_execute_pipeline()` scraper call | Set max results; the count is approximate by design |
| Scraper subprocess with timeout | `_stream_process()`, `LEADFORGE_SCRAPER_TIMEOUT` (default 900s) | Automatic; a hung search is killed and reported as SCRAPER_TIMEOUT |
| Strict results CSV parsing | `_parse_results_strict()` | Automatic; a malformed file never replaces the last good `latest.csv` |
| Zero result runs labelled honestly | `_execute_pipeline()` result handling | A valid empty result ends as a zero result run, not an error |
| Website reading inside the run | `dashboard/enrich.py`, called from `_execute_pipeline()` | Automatic for up to 15 websites; needs the one time crawl4ai setup |
| Website failures isolated per site | `enrich.py` ENRICH_FAILED and ENRICH_SUMMARY lines | Automatic; counts show attempted, succeeded and failed |
| Stage 5 auto report | `_run_full_pipeline_tail()` and `generate_report()` | Automatic at the end of every full run; read it on the Reports page |
| Done or Partially done endings | `_run_full_pipeline_tail()` | A later stage failure never deletes earlier stage results |

## Finding and qualifying

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Google Maps business search | Folder `1-find-google-maps-scraper`, driven from `_execute_pipeline()` | Type location and business type on the Run page |
| Manual scraper runs | `queries.txt` and `run_scraper.bat` in folder 1 | Edit queries.txt and run the bat outside the dashboard |
| Four qualification classes | `compute_qualification()` | Automatic after reading; see the chip on the Leads page |
| Qualification method honesty | `compute_qualification()` and docs/04 | "No website confirmed" means the listing shows none and the reader found none |
| Qualification counts in summaries | `_run_full_pipeline_tail()`, `generate_report()` | Read the run summary or any report |

## Leads page and the lead store

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Lead store merged by phone | `dashboard/data/leads.json`, `load_lead_store()`, `sync_lead_store()` | Automatic after every run; fallback match is name plus city |
| First seen and last seen kept | `sync_lead_store()` | Visible in the store record for each lead |
| Leads table with all fields | Leads page, `leads_page()` using `lead_records()` | Open the Leads page |
| Text filter | Leads page filter input (browser side) | Type in the filter box to narrow the table |
| Qualification filter | Leads page, `qualFilter` select | Pick one class to show only those leads |
| Pitch chip per lead | Leads page, pitch files in `dashboard/data/pitches/` | A lead with a saved pitch shows the chip |
| Outcome marking | Leads page select, `POST /leads/outcome`, `set_lead_outcome()` | Pick New, Pitched, Replied, Call booked, Not interested or No reply |
| Download latest CSV | `GET /download/latest.csv` | Click Download CSV; with no results yet you get a friendly 404 page |
| Corrupt store protection | `load_lead_store()` logs STORE_CORRUPT | Automatic; the file is left untouched and the Health timeline shows the entry |

## Writer

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Single lead pitch generation | Writer page, `handle_writer_generate()`, `generate_pitch()` | Pick a lead, output and language, click Generate |
| Cloud AI: Gemini | `ai_request()` with the Gemini provider info, model gemini-2.0-flash | Save a free key from aistudio.google.com/apikey in Settings |
| Cloud AI: Groq | `ai_request()` with the Groq provider info, model llama-3.3-70b-versatile | Save a free key from console.groq.com/keys in Settings |
| Local AI (Ollama and compatible) | `ai_request_local()`, `local_ai_status()` | Choose Local AI in Settings, keep base http://127.0.0.1:11434, click Check local AI |
| Local AI bases for other servers | Settings local base field | LM Studio 1234, llama.cpp 8080, KoboldCpp 5001; any OpenAI compatible base works |
| One click model download | `run_model_pull()`, `handle_model_pull()`, status at `GET /settings/pull-status` | In Settings, when Ollama answers, click Download model |
| AI request timeout and error mapping | `ai_request()`, `ai_request_local()`, `AI_TIMEOUT_SECONDS` (30s default) | Automatic; failures show as AI_NO_KEY, AI_KEY_INVALID, AI_RATE_LIMIT, AI_TIMEOUT, AI_OFFLINE or AI_PROVIDER_ERROR |
| Editable pitch result with counts | Writer page result editor | Edit the text; word counts update as you type |
| Copy WhatsApp and Copy Email | Writer page copy buttons | Click to copy the exact text for pasting into chatwoot or listmonk |
| Regenerate | Writer page, `generate_pitch()` | Click Regenerate for a fresh draft of the same lead |
| Batch writing, first 10 qualified | `handle_writer_batch()`, `run_ai_batch()` | Click Batch on the Writer page; covers no website confirmed plus website dead |
| Include has website toggle | Writer page batch form, `run_ai_batch(include_has_website)` | Tick the labelled toggle to also pitch leads that have a website |
| Unknown leads always excluded | `run_ai_batch()` selection | Automatic; unknown data leads are never batched |
| Pitch file saved per lead | `save_pitch_file()`, `dashboard/data/pitches/` | Automatic on every successful generation; outcome becomes Pitched |
| Retry ladder | `pitch_attempts_for_lead()` | Automatic: full prompt, simpler prompt, other provider, then marked for manual |
| What is working learning card | Writer page, `learning_summary()` | Mark outcomes on the Leads page; needs at least 3 pitched leads with outcomes |
| Learning hint inside prompts | `build_ai_prompt()` | Automatic once the learning card has a pattern |

## Manual web mode and the web assistant

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Copy instruction (full form) | `build_manual_instruction()` | Writer page, Manual mode, click Copy instruction, paste into any web AI |
| Strict reply markers | `build_manual_instruction()`, paste parsing in `handle_writer_manual()` | The AI replies with WHATSAPP:, SUBJECT: and EMAIL: markers; paste the reply back and save |
| No markers fallback | `handle_writer_manual()` | A reply without markers is saved whole, with a plain notice |
| Quick open buttons | Writer page manual card | Buttons open ChatGPT, Gemini, Claude and the Groq playground |
| Batch manual instruction | `build_manual_batch_instruction()` | One copied text with a `=== LEAD n: name ===` section per lead |
| Batch manual paste back | `handle_writer_manual_batch()` | Paste the combined reply; each section is saved to its lead |
| Web assistant setup copy | `build_web_assistant_setup()` | Click Copy web assistant setup once; paste it into a Gemini Gem or ChatGPT GPT named LeadForge Pitch Writer |
| Saved assistant short form | `build_short_manual_instruction()` and the useSavedAssistant toggle | Tick "I use my saved web assistant"; copies shrink to lead blocks only |

## Playbook and the checkers

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Pitch Playbook editors | Settings page, `pitch_playbook()`, `handle_pitch_rules_save()` | Edit rules and examples in Settings, click Save playbook |
| Playbook reset | `handle_pitch_rules_reset()` | Click Reset on the playbook card to restore the default |
| One prompt path for all routes | `build_ai_prompt()` | Automatic; cloud, local and manual all use the same builder and playbook |
| Output checker | `validate_pitch_output()` | Automatic; markers, WhatsApp 30 to 140 words, no bracket placeholders, no banned fake claim words |
| One correction retry | `generate_pitch()` correction pass | Automatic and exactly once; then the lead is marked for manual |
| AI style checker | `style_check_pitch()` with `AI_STYLE_PHRASES` | Automatic; verdict is Looks human, Some AI signs or Looks AI-written, with reasons |
| One humanize rewrite | `generate_pitch()` humanize pass | Automatic when a pitch reads AI-written; the better version is saved and marked Humanized |
| Manual pastes checked with warnings only | `handle_writer_manual()` | Paste results show warnings; your text is never edited |
| Region language pack | `REGION_PACK`, read by `build_ai_prompt()` | Leave language on Auto (by region), the default |
| Language choices | Writer page language select | English, Bangla, or Auto (by region) per generation or batch |

## Settings and app setup

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Setup status panel | `setup_status_rows()`, `setup_status_panel()` | Top of Settings and Guide; names the missing field names per app |
| chatwoot setup form | Settings page, `handle_settings_save()` | Fill SECRET_KEY_BASE and POSTGRES_PASSWORD, or leave blank to auto generate |
| cal.diy setup form | Settings page, `handle_settings_save()` | DATABASE_URL, DATABASE_DIRECT_URL, NEXTAUTH_SECRET, CALENDSO_ENCRYPTION_KEY, JWT_SECRET |
| twenty setup form | Settings page, `handle_settings_save()` | PG_DATABASE_PASSWORD and ENCRYPTION_KEY, both auto generated when blank |
| documenso setup form | Settings page, `handle_settings_save()` | Postgres fields, encryption keys, web app URL and database URLs rebuilt from the saved values |
| Auto generated secrets | `RANDOM_GENERATORS`, `generate_random_value()` | Leave an auto marked secret blank and LeadForge generates it on save |
| Masked secrets after saving | Settings page rendering from `load_ai_settings()` and the env readers | Saved secrets show only as Saved; they are never printed again |
| Blank secret keeps the old value | `handle_settings_save()`, `handle_ai_settings_save()` | Re-save a form with secret fields blank to change only the rest |
| Required field validation | `APP_REQUIRED_FIELDS`, `APP_ENV_INCOMPLETE` | Saving with a required field missing names the field instead of failing later |
| Check setup per app | `handle_settings_check()`, compose config run | Click Check setup on the app form; it runs a real config validation |
| listmonk guidance card | Settings page | listmonk has no form; SMTP is set inside listmonk after it starts |
| AI settings form | `handle_ai_settings_save()`, `dashboard/data/ai-settings.json` | Pick the provider, paste the key, save; the key is stored masked |
| Check AI and Check local AI | `POST /settings/check-ai`, `local_ai_status()`, `handle_local_ai_check()` | Click after saving to test the route before writing |
| Chatwoot reply check settings | `chatwoot_sync_settings()`, `handle_chatwoot_sync_save()` | Base URL, account ID and API token (masked) in the Settings card |

## Apps page and Docker control

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| App cards with status pills | Apps page, `apps_page()`, `apps_status_data()`, `app_display_status()` | Open the Apps page; states include running, not started, setup needed and failed |
| Start, Stop and Open per app | `POST /apps/action`, `_do_app_action()` | Use the buttons on each card; Open uses the app's current address |
| Start all with per app isolation | Apps page, `start_all_thread()`, `_start_all_apps()` | One failure stays on its card and does not stop the rest |
| Automatic app port switching | `allocate_app_ports()` | Automatic when a web, database or cache host port is busy |
| Port assignments persist | `load_app_ports()`, `save_app_ports()`, `dashboard/data/app-ports.json` | Automatic; switched ports survive restarts |
| Runtime compose generation | `generate_runtime_compose()` writes `docker-compose.leadforge.yml` | Automatic; upstream compose files are never edited |
| App URLs follow switched ports | `runtime_env_for_app()` | Automatic; twenty, documenso, chatwoot and cal.diy receive their real URL |
| Compose timeouts | `_compose_command()` (config 120s, start 900s, stop 300s) | Automatic; slow first pulls end as a clear timeout, not a hang |
| Docker missing or stopped states | `docker_status()` | Apps and Health pages show the exact state and fix |
| Per app output terminal | Apps page, status at `GET /apps/status` | The card output updates live while an action runs |
| Writer job status feed | `GET /writer/status`, `writer_job_snapshot()` | Polled by the Writer page during generation |
| Model pull progress feed | `GET /settings/pull-status`, `pull_job_snapshot()` | Shown live in Settings during a model download |

## Reports and reply check

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Automatic report per full run | `generate_report()` from `_run_full_pipeline_tail()` | Read it on the Reports page after any full pipeline run |
| Generate report now | `POST /reports/generate`, `handle_report_generate()` | Click on the Reports page for a fresh report from the store |
| Report sections and counts | `generate_report()`, files in `dashboard/data/reports/` | Found, Qualified, Pitched, Failed with reasons, Replies, Calls booked, Not replied, Not interested, Still new |
| Chatwoot reply check | `check_chatwoot_replies()`, `POST /reports/check-replies`, `handle_report_check_replies()` | Click Check replies now; it also runs when the Reports page opens and a check is due |
| Phone matching by last 10 digits | `check_chatwoot_replies()` | Automatic; open conversations (max 50) are matched to leads |
| Outcome flips to Replied | `check_chatwoot_replies()` with `set_lead_outcome()` | Automatic on a match, unless the lead is already Call booked |
| Keyword reply tags | `classify_reply()` | interested, call me, price style words tag positive; not interested, stop tag negative; else question or other |
| Sync status with will-recheck | `dashboard/data/chatwoot-sync.json`, Reports page | Unreachable or 401 states show a plain fix; opening the page rechecks, no background daemon |
| Email reply honesty | docs/08 | Email replies land in your mailbox; mark email outcomes by hand until the mailbox is connected to chatwoot |

## Guide and Health

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Guide cards for keys and setup | Guide page, `guide_page()` | Follow the cards in order; free key links are on the cards |
| Safe sending rules in the Guide | Guide page, text from docs/07 | Read before sending anything: Business API, templates, opt out, small batches |
| Web to API bridge honesty note | Guide page "No API key at all?" card | States that cookie based bridge tools break often and can flag accounts, so LeadForge does not use them |
| Health summary and diagnostic cards | Health page, `health_page()`, `health_data()` | Open Health for server, Docker, disk, data and log checks |
| Live ports table | Health page, `health_data()` | Shows preferred and actual ports for the dashboard and every app |
| Recent error timeline | Health page, `recent_errors()` | Newest errors with code, message and fix |
| Clear errors | `POST /health/clear-errors`, `clear_error_log()` | Click Clear errors on the Health page |
| Page shell and navigation | `shell()` wraps every `*_page()` in app.py | Automatic; sidebar on desktop, top bar on phones |
| Health as JSON | `GET /api/health`, `GET /api/errors` | For scripts or support; same data as the Health page |
| Rotating logs | `record_event()`, `_rotate_if_needed()`, `dashboard/data/logs/` | leadforge.log and errors.jsonl rotate at about 1 MB |

## Safety and crash protection

| Feature | Where it lives | How to use it |
| --- | --- | --- |
| Local only binding | `HOST` in app.py, server start in `main()` | The dashboard listens on 127.0.0.1 only; there is no setting to expose it |
| Catch all error handler | `class Handler` do_GET and do_POST, `_error_response()` | Automatic; a bad request gets the branded friendly page and the server keeps serving |
| POST size cap | `Handler._post_impl()` (1,000,000 bytes) | Automatic; an oversized post gets a friendly 400 page |
| Secret redaction in logs and pages | `sanitize_text()` | Automatic; saved keys are stripped from logs, errors and HTML |
| Atomic JSON writes | `atomic_write_json()` | Automatic; a crash mid save cannot leave a half written settings file |
| Settings in plain local files | `dashboard/data/ai-settings.json` and per app `.env` files | Your files on your PC; never commit them (see SECURITY.md) |
| Fault injection test suite | `tests/run_fault_tests.py` | Run it after changes: 19 checks covering corrupt files, hanging AI, missing scraper, busy port, oversized forms, double start and a deliberate crash |
