# 09. Troubleshooting

Every failure in LeadForge ends with a code, a plain message and a fix.
The same codes appear in the UI, on the Health page timeline, and in
`dashboard/data/logs/errors.jsonl`. Find your code below.

## Dashboard and server

| Code | What it means | Fix |
| --- | --- | --- |
| HTTP_INTERNAL_ERROR | One request hit an unexpected problem. The server kept running and showed a friendly page. | Reload the page. If it repeats, note what you clicked and check the newest entry in errors.jsonl. |
| HTTP_SERVER_ERROR | The HTTP layer itself reported an error, usually a dropped connection. | Reload. It does not stop the dashboard. |
| Request too large (400 page) | A form post was bigger than the 1 MB safety cap. | Do not paste huge files into form fields. Split the text and retry. |
| Branded 404 page | The address or download does not exist yet. | Use the sidebar links. For the CSV download, run a search first so a results file exists. |
| STORE_CORRUPT | `dashboard/data/leads.json` exists but cannot be read. The dashboard started from an empty store view and left the file untouched. | Open the file in a text editor and repair the JSON, or restore a backup copy. Your leads are in that file, not lost by the dashboard. |

## Run and scraper

| Code | What it means | Fix |
| --- | --- | --- |
| JOB_VALIDATION_FAILED | The run form failed validation (empty or too short location or business type, or max results outside 1 to 200). | Fill both fields with at least 2 characters and a max results number in range. |
| JOB_ALREADY_RUNNING | A pipeline job is already running. One job at a time by design. | Wait for the current job to end, then start again. |
| SCRAPER_NOT_FOUND | The scraper program was not found where LeadForge expects it. | Keep the pack folders together. The binary belongs in `1-find-google-maps-scraper`. |
| SCRAPER_NOT_EXECUTABLE | The scraper file exists but cannot be run. | On Windows, unblock the file (right click, Properties, Unblock) and check your antivirus quarantine. |
| SCRAPER_START_FAILED | The scraper process could not start. | Read the detail line in the console; usually a blocked or missing helper file. Re-extract the pack if files are missing. |
| SCRAPER_TIMEOUT | The search ran past the time limit (default 900 seconds). | Lower max results, or search a smaller area. Slow networks need smaller runs. |
| SCRAPER_OUTPUT_MISSING | The scraper finished but produced no results file. | Run again. If it repeats, Google may be blocking the search; wait and retry later. |
| SCRAPER_CSV_MALFORMED | The results file was not valid. Your last good results were kept. | Run the search again. Do not hand edit results files. |
| SCRAPER_PARTIAL_OUTPUT | Some rows were usable, some were not. The good rows were saved. | Check the console counts. Re-run if the missing part matters. |
| SCRAPER_FAILED | The scraper exited with an error. | Read the scraper's own words in the console. Common causes: Google bot checks, no network, consent screens. Retry later. |
| PIPELINE_INTERNAL_ERROR | A pipeline stage hit an unexpected problem. Earlier stage results were kept. | Read the stage line in the console, fix that cause, and run again. |

## Apps and Docker

| Code | What it means | Fix |
| --- | --- | --- |
| DOCKER_MISSING | Docker was not found on this PC. | Install Docker Desktop, then try again. Finding and writing work without Docker. |
| DOCKER_STOPPED | Docker is installed but its engine is not running. | Start Docker Desktop and wait until it reports running. |
| APP_FOLDER_MISSING | An app folder is missing from the pack. | Keep the numbered folders together; re-extract the pack if one was deleted. |
| APP_SETUP_NEEDED | The app needs its setup form filled before it can start. | Open Settings, fill that app's form (the panel names the missing fields), save, then start again. |
| APP_ENV_INCOMPLETE | A saved setup is missing required values. | Open the app's Settings form; required fields are marked. Blank secrets keep their old value, so type only what is missing. |
| APP_ENV_VERIFY_FAILED | The saved setup failed verification. | Use Check setup on the form to see the exact failing part, fix it, save again. |
| APP_SETUP_CHECK_FAILED | `docker compose config` rejected the app setup. | Read the output on the card; usually one bad value in the form. Fix and re-check. |
| APP_SETUP_CHECK_PASSED | The setup validated. (Info, not an error.) | Start the app. |
| APP_COMPOSE_CONFIG_FAILED | Docker Compose could not build a valid config for the app. | Run Check setup from Settings; if the upstream compose file was edited, restore it. LeadForge never edits upstream files. |
| APP_COMPOSE_CONFIG_TIMEOUT | The config check ran past 120 seconds. | Docker Desktop may be starting or the PC is busy. Wait and retry. |
| APP_COMPOSE_FAILED | A start or stop command failed. | Read the app card output. Check Docker Desktop is running and the PC has free disk and memory. |
| APP_COMPOSE_TIMEOUT | A start ran past 900 seconds or a stop past 300 seconds. | First starts pull large images and can be slow on weak networks. Retry; progress is kept by Docker. |
| APP_RUNTIME_CONFIG_FAILED | LeadForge could not generate the runtime compose file. | Check the app folder is writable and complete, then retry. |
| APP_PORT_SWITCHED | A busy port was moved automatically. (Info.) | Use the new address shown on the card. Nothing to fix. |
| APP_PORT_UNAVAILABLE | No free port was found in the allowed range. | Close whatever is using large blocks of local ports, then retry. |
| APP_INTERNAL_ERROR | An app action hit an unexpected problem. | Retry the action. If it repeats, check errors.jsonl for the detail. |
| APP_START_ALL_FINISHED / APP_START_ALL_FAILED | Start all ended; per app results are on the cards. | Fix the failed cards one by one; the started apps keep running. |

## AI writer

| Code | What it means | Fix |
| --- | --- | --- |
| AI_NO_KEY | No cloud key is saved and the chosen route needs one. | Save a free Gemini or Groq key in Settings, or switch to Local AI or manual mode. |
| AI_KEY_INVALID | The provider rejected the key (401 style). | Re-copy the key from the provider site and save it again. Keys are masked after saving, so a typo is invisible; paste fresh. |
| AI_RATE_LIMIT | The free tier rate limit was hit (429 style). | Wait a few minutes. Batches stop per lead and continue later; nothing is lost. |
| AI_TIMEOUT | The AI did not answer within the time limit (30 seconds default). | Check the network, or for local AI pick a smaller model (qwen2.5:3b). Retry. |
| AI_OFFLINE | The provider could not be reached at all. | Check the internet connection. For local AI, check the server is running. |
| AI_PROVIDER_ERROR | The provider answered with an error or with something unreadable. | Retry. If it repeats, try the other provider; the retry ladder already falls back when it can. |
| AI_MODEL_MISSING | The chosen local model is not downloaded. | Use Download model (one click) in Settings, or pull it in Ollama. |
| LOCAL_AI_NOT_RUNNING | No local AI server answered at the base URL. | Start Ollama (or your server), then Check local AI. Default base is http://127.0.0.1:11434. |
| LOCAL_AI_NO_MODEL | The local server answered but lists no usable model. | Download a model first (one click in Settings). |
| LOCAL_AI_TIMEOUT / LOCAL_AI_PROVIDER_ERROR | The local server was too slow or answered badly. | Free memory, pick a 3B model, retry. |
| AI_OUTPUT_CHECK | A pitch failed the format or banned claim check; one automatic correction retry follows. | If it still fails, the lead is marked for manual mode. Edit the playbook examples if it happens often. |
| AI_NO_LEADS | A batch was started with no qualified leads. | Run a search first, or include the has website class with the toggle. |
| AI_MANUAL_EMPTY | A manual paste box was empty. | Paste the AI reply, then save. |

## Chatwoot reply check

| Code | What it means | Fix |
| --- | --- | --- |
| CHATWOOT_UNREACHABLE | Chatwoot did not answer at the saved base URL. | Start chatwoot from the Apps page, and check the base URL in Settings (default http://localhost:3001). The check retries when you open the page again. |
| CHATWOOT_SYNC_FAILED | The reply check failed, most often a wrong account ID or token (401). | Re-copy the account ID and API access token into the Settings card and run Check replies now. |
| CHATWOOT_SYNC_DONE | The check finished. (Info.) | Nothing to fix. Outcomes were updated on matched leads. |

## Still stuck

Open the Health page. It shows the dashboard, Docker, disk and data
checks, the live ports table, and the newest errors with their fixes.
The raw logs are `dashboard/data/logs/leadforge.log` and
`dashboard/data/logs/errors.jsonl`. Secrets are redacted in both, so
they are safe to share when asking for help.
