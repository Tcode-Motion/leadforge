LeadForge: your one control page for the whole pipeline

What it is
LeadForge is a small web page that runs on your own PC. It puts the whole pack behind one screen, so you do not have to open folders and run files one by one. Its tagline says what it does: Find clients. Forge deals.

On a wide screen, the pages sit in the left sidebar with the live local address below them. On a phone, the same navigation moves into a compact top bar. The pages are: Run, Leads, Writer, Apps, Settings, Guide, Reports, and Health.

Start it
1. Double click LeadForge.bat in this pack folder.
2. A black window opens. That window is the LeadForge server. Keep it open while you work. Close it to stop LeadForge.
3. LeadForge picks a free local port and your browser opens at the real address. The usual port is 8790, but the address can be different if 8790 is busy. LeadForge checks ports from the preferred one upward and uses the first free one.
4. If LeadForge is already running, the bat opens the running dashboard instead of starting a second copy.
5. If startup fails, the black window stays open with the log paths. It does not vanish silently.

Run page and the Full pipeline
Type a location, a business type, and a max results number from 1 to 200, pick a mode, then click Run search.

- Find leads only: the scraper finds the leads, then the website reader reads up to 15 lead websites and saves a pitch note for each one it can read. This is the original behavior.
- Full pipeline (the default): after Find and Read, the same one click continues automatically. Stage 3 Qualify sorts every lead (see Qualification below). Stage 4 Write pitches writes pitches for qualified leads only, using your chosen AI provider, with the style check inside. Stage 5 Check and report builds a report on the Reports page. The activity console shows one line per stage. If a later stage fails, the earlier results are kept, and the job ends Done or Partially done with a plain summary and counts.

LeadForge will not start a second pipeline job while one is already running. Bad form values are shown on the page. A failed website does not kill the whole job.

One honest detail: the scraper tool has no exact result limit setting. LeadForge turns your max results number into the scraper scroll depth, so the count you get is close to what you asked, not exact.

Qualification: website truth first
Every lead in the store gets one qualification, computed from real data only:

- No website confirmed: the Google listing shows no website and the website reader found none either. LeadForge never claims more than the data shows.
- Has website: a website is listed and it loads, or a website note was prepared for it.
- Website dead: a website is listed but the reader could not load it. This is its own pitch angle: their site is broken.
- Unknown: not enough data to say. Unknown leads are never pitched by the batch or the Full pipeline.

Pitch batches (Writer page and Full pipeline) include No website confirmed plus Website dead leads by default. A clearly labelled toggle, "Also include leads that already have a website", adds Has website leads. The batch cap is 10 leads per run, which protects the free AI quota.

The lead store
Leads are kept in dashboard\data\leads.json, merged across runs. The phone number is the unique key (if there is no phone, name plus city is used). The store keeps first seen, last seen, how many runs saw the lead, qualification, website note link, pitch link, outcome, and the last error if a pitch failed. The Leads page reads the store, so past leads stay after new runs. The latest run list is still dashboard\data\latest.csv, with the Download CSV button on the Leads page.

On the Leads page you can filter by qualification and mark one outcome per lead: New, Pitched, Replied, Call booked, Not interested, No reply. Marking outcomes is how LeadForge learns (see Learning below).

A malformed results file never replaces the last good list. A completed search with 0 leads is labelled as a zero result, not a crash, and the last good list is still shown and labelled.

Apps page
One card for each server tool: listmonk, chatwoot, cal.diy, twenty, and documenso. Each card has the real Open address, Start, Stop, a live state, the app console, and a plain fix when something is wrong.

Start them one at a time where you can. There is also a Start all apps button. It works through the apps one by one, keeps going after one fails, and reports how many accepted a start command.

You do not need Docker to open LeadForge or use the lead finder. Docker problems affect only the Apps page.

Automatic app ports
The usual web ports are:
- listmonk: 9000
- chatwoot: 3001
- cal.diy: 3002
- twenty: 3003
- documenso: 3004

Before an app starts, LeadForge checks its web port. If it is busy, LeadForge picks the next free port, saves it in dashboard\data\app-ports.json, and shows the real Open address on the card. The card also says when a port was switched.

LeadForge also checks published helper ports that can clash:
- listmonk Postgres: usual host port 5432
- chatwoot Postgres: usual host port 5432
- chatwoot Redis: usual host port 6379
- cal.diy Redis: usual host port 6379
- cal.diy API: usual host port 8080 in LeadForge, changed from the Compose default 80 to avoid a common and privileged port
- cal.diy Prisma Studio: usual host port 5555

These apps talk to their database and cache through Docker service names and container ports, so changing only the host side is safe for those connections. Twenty and documenso do not publish database or cache ports in their Compose files, so there is no helper host port for LeadForge to switch.

How the port switch works in Docker
LeadForge does not stack a second port on top of the first one. For each start, it creates docker-compose.leadforge.yml inside that app folder. This is a full runtime copy of the app Compose file with the chosen host ports replacing the original host ports. The original Compose file is not edited. Stop uses the same runtime file, so it stops the same project.

Some apps also receive their real local web address while starting:
- twenty receives SERVER_URL
- documenso receives NEXT_PUBLIC_WEBAPP_URL
- chatwoot receives FRONTEND_URL in its runtime copy
- cal.diy receives NEXT_PUBLIC_WEBAPP_URL and NEXTAUTH_URL in its runtime copy

Settings page: app setup and keys inside the UI
No more copying .env.example files or editing setup text by hand.

Setup status panel
At the top of Settings, and again at the top of the Guide page, a live panel shows one row per item: lead finder program, website reader, free AI key (with the provider name), Local AI, and every server app. Green means Configured or Ready. Amber means Missing, and the row names the exact fields still needed (names only, never values) with a button that jumps to the right form. Grey means Not needed. For Writer AI, either the cloud key row or the Local AI row needs to be green.

App setup forms
Four apps need a setup file before Docker can start them, verified from their shipped files: chatwoot, cal.diy, twenty, and documenso. Each gets a form in Settings, built from that app's own .env.example, in the example's original order:

- chatwoot: SECRET_KEY_BASE and POSTGRES_PASSWORD are required and are auto-generated when left blank.
- cal.diy: DATABASE_URL, DATABASE_DIRECT_URL, NEXTAUTH_SECRET, CALENDSO_ENCRYPTION_KEY, plus JWT_SECRET (used by its API service in the Compose file) are required. The secrets are auto-generated when left blank.
- twenty: PG_DATABASE_PASSWORD and ENCRYPTION_KEY are required. In twenty's .env.example they exist only as commented placeholders, and the form includes them for that reason. Both are auto-generated when left blank.
- documenso: POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB (required by its Compose file, not present in its .env.example) plus NEXTAUTH_SECRET, NEXT_PRIVATE_ENCRYPTION_KEY, NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY, NEXT_PUBLIC_WEBAPP_URL, NEXT_PRIVATE_DATABASE_URL, NEXT_PRIVATE_DIRECT_DATABASE_URL, NEXT_PRIVATE_SMTP_TRANSPORT, NEXT_PRIVATE_SMTP_FROM_NAME and NEXT_PRIVATE_SMTP_FROM_ADDRESS are required. The secrets are auto-generated when left blank, and the database URLs are rebuilt from the Postgres values you save, so the app and its database always match.

Saving writes the app's real .env in its pack folder, in the example's order, quoting values only when they contain spaces or special characters. The .env.example file is never touched. After saving, LeadForge reads the file back and validates it: every required key present and non-empty, and URL and email shaped fields checked. The result is shown per app: Ready, or the exact fields still missing. When the .env is valid, the app flips from Setup needed to Not started on the Apps page and in Health, by itself.

Secrets that only need to be random are generated with strong randomness on save when you leave them blank, and Settings tells you their names only. On a later visit, secret fields show only a Saved state, never the value. Leaving a secret blank on a later save keeps the existing value. Non-secret fields show their saved values so you can review them.

Each app also has a Check setup action. It builds the same runtime Compose file a start would use and runs docker compose config to validate it when Docker is available. If Docker is missing or stopped, it says so honestly.

listmonk is different: it needs no setup file before it starts, so Settings shows a guidance card instead of a form. Its email sending (SMTP) is set inside listmonk after it starts: open listmonk, create or log in to the admin account, then go to Settings, then SMTP, and add the sending account. A free route is a Gmail app password or a free SMTP service. Without SMTP, listmonk can store lists but cannot send.

Free AI writer
The Writer page writes personal outreach from real lead data only: business name, category, city and address, rating and reviews when present, phone, website, and the saved website note. It never invents facts about the business.

Settings has a Free AI card with three ways to write, and the choice is yours. LeadForge never switches providers silently.

1. Google Gemini free tier: get a free key at https://aistudio.google.com/apikey (sign in, Create API key, no card needed). LeadForge calls the gemini-2.0-flash model.
2. Groq free tier: get a free key at https://console.groq.com/keys (sign in, API Keys, Create key, no card needed). LeadForge calls the llama-3.3-70b-versatile model.
3. Local AI (Ollama or compatible): no key, no daily limit, nothing leaves the PC. See the Local AI section below. Local AI is fully optional; the cloud key and Manual mode work without it.

The API key is stored in dashboard\data\ai-settings.json on this PC only. It is shown masked after saving, a blank field keeps the existing key, and the key is redacted from every log and error message. Free quotas are real: free tiers can run out for the day, and LeadForge shows a plain AI_RATE_LIMIT message when that happens instead of pretending.

On the Writer page: pick a lead, pick Output (WhatsApp message, Email, or Both), pick a Language (Auto by region, English, or Bangla), and click Generate. Results appear in editable text areas with character counts, Copy buttons, and Regenerate. Every generation is saved as one markdown file per lead in dashboard\data\pitches, and the Leads page shows a Pitch ready chip for that lead.

Batch: the "Write for first 10 leads" button writes for qualified leads (see Qualification), one by one with a short pause, and one lead failing never stops the others. It ends Done or Partially done with counts, including how many leads were marked for Manual mode.

Errors are plain and coded: AI_NO_KEY (no provider ready), AI_KEY_INVALID (the provider rejected the key, with the fix), AI_RATE_LIMIT (free quota), AI_TIMEOUT, AI_PROVIDER_ERROR, AI_OFFLINE (no internet, DNS, or the local server is not running), and AI_MODEL_MISSING for a local model that is not downloaded yet.

Retry ladder: if a pitch fails its checks or the provider errors, LeadForge retries once with a shorter, simpler prompt. If it still fails and you have both a cloud key and Local AI configured, it tries the other provider once. If it still fails, the lead is marked for Manual mode and the batch continues. Each step is written to the job log with the lead name.

Style check and humanize
Every generated pitch passes a small built-in checker before it is saved: stock phrases (like "I hope this message finds you well"), em dash or en dash characters, very uniform sentence lengths, missing lead specific detail, placeholder brackets, plus the output checker for word counts and banned claim words. The result is a label: Looks human, Some AI signs, or Looks AI-written, shown with the top reasons. If the label is Looks AI-written, LeadForge does one rewrite pass with humanize instructions and saves the better version, marked Humanized on the pitch. Manual pastes get the same checker as warnings only; saving is never blocked.

Local AI (Ollama or compatible)
Local AI talks to any OpenAI compatible server on your own PC through its /v1/chat/completions address. Typical base URLs: Ollama http://127.0.0.1:11434, LM Studio http://127.0.0.1:1234, llama.cpp server http://127.0.0.1:8080, KoboldCpp http://127.0.0.1:5001. LeadForge checks it through Ollama's /api/tags first and falls back to /v1/models, and reports whichever answered, with model names only.

One click download: when Ollama is running, Settings shows a Download model button. It downloads the selected model through Ollama for you, with live progress, and ends Done or Failed with the real reason. When Ollama is not running, the button is replaced by a Download Ollama link (https://ollama.com/download) and two simple steps.

Light local models for an 8 GB RAM PC with no graphics card:

| Model | Download size | Fit for 8 GB RAM, no GPU |
| qwen2.5:3b (recommended default) | about 2 GB | Comfortable. Best format following and Bangla for its size. A pitch takes roughly tens of seconds, depending on the CPU. |
| llama3.2:3b | about 2 GB | Comfortable and fast. English first; weaker Bangla. |
| qwen2.5:7b | about 4.7 GB | Borderline in 8 GB and slow on a low CPU. Better writing. Use only if you accept the wait, or on a stronger PC. |

Honest notes: a local 3B model writes below Gemini quality, and speed depends on your PC. The Pitch rules below keep its format consistent. Nothing you write with Local AI leaves the PC, and there is no key and no daily limit.

Pitch rules (the playbook for every model)
Settings has a Pitch rules editor: a Rules box and an Examples box, with Save rules and Reset to default buttons and a character count. The default rules say who Tanmoy and GDL Technologies are (mobile apps, websites and software for businesses), the offer and one soft call to action, the tone (human, simple, friendly, no pressure), and the hard rules: only facts from the lead data and the website note, never invent ratings, prices, clients or results, no guaranteed claims, WhatsApp about 60 to 90 words, email subject plus about 120 to 160 words, the selected language, and the exact output format.

Every writing path uses the same rules, through one code path: Gemini, Groq, Local AI, the Manual mode instruction, and the web assistant setup all start with the playbook, then your examples (under the heading "Style examples to imitate:") when the Examples box is not empty, then the lead facts and the output format. Edit the rules once and every model follows them.

After generation, an output checker validates the result: the required parts exist, the WhatsApp length is roughly 30 to 140 words, no square bracket placeholders are left, and none of the banned claim words appear (guaranteed, guarantee, 100 percent result, number one, best in the world). If it fails, LeadForge does exactly one correction retry that lists the problems, and uses the retry when it parses. The result area shows "Auto-fixed on retry" or "Check before sending".

Region awareness and learning
The Language choice "Auto (by region)" is the default. LeadForge reads the lead's address and applies a small built-in region table: West Bengal gets Bangla (or Bengali friendly English), Delhi gets Hinglish friendly English, Maharashtra gets Hinglish or Marathi friendly English, Tamil Nadu gets English with a Tamil greeting option, Karnataka, Uttar Pradesh, Gujarat and Kerala get English or locally friendly English, and anywhere else gets English. The prompt also includes the local area from the address, as the local touch. You can always override with English or Bangla by hand.

What is working: the Writer page shows a small learning card. When at least 3 pitched leads have outcomes marked on the Leads page, the card sums up replies by language and region, for example "Bangla WhatsApp pitches to West Bengal leads got 2 replies from 3 sent", and that one line is added to new prompts as a "What has worked so far" hint. With too little data, the card honestly says "Still learning: mark replies on the Leads page and I will learn what works."

Manual mode and the web assistant
On the Writer page, Manual mode needs no key and makes no API call:

- Copy instruction builds the same prompt the API would get (playbook included), plus a strict reply format: WHATSAPP:, SUBJECT:, EMAIL: markers (adapted to the output you picked).
- Quick open buttons take you to ChatGPT, Gemini, Claude, and the Groq playground.
- Paste the AI reply back and Save: the markers are parsed into the same result areas and the same pitch files, marked as manual. If the markers are missing, the whole text is saved as the pitch text and the page says plainly that the format was not followed. An empty paste is rejected with a friendly message.
- Batch manual works the same way for up to 10 leads: one combined instruction with numbered lead blocks, and the reply is split by "=== LEAD n: name ===" sections. If splitting fails, one combined pitch file is saved and the page says so.

Web assistant setup: Manual mode also has a "Copy web assistant setup" button. It copies a self-contained text (the current playbook, the output format, and "You are my pitch writer. I will paste lead blocks. Reply only in the format.") that you paste once into a Gemini Gem or a ChatGPT custom GPT named LeadForge Pitch Writer. After that, turn on "I use my saved web assistant" in Manual mode, and the per-run Copy instruction becomes the short form (lead blocks plus "Write the pitches in your saved format."), because the rules already live in your web assistant. The Guide page has the 5 minute setup card for both Gemini and ChatGPT.

Reports page and reply sync
Every Full pipeline run ends by writing a report, and the Reports page also has a Generate report now button. Reports are markdown files in dashboard\data\reports, named by date and time, with sections: Found, Qualified (by class, with the method note), Pitched, Failed (with reasons), Replies, Calls booked, Not replied, Not interested, Still new. The Reports page lists every report with its headline counts and renders the latest one.

Chatwoot reply sync (optional): Settings has a Chatwoot reply sync card (base URL, account ID, API access token). The token is a secret: stored on this PC only, shown masked, never logged. The Check replies now button on Reports (the same status is shown on Health) reads open chatwoot conversations, at most 50, matches contacts to the lead store by phone number, and marks matched leads Replied (unless already Call booked). It saves the reply snippet and time, and tags the reply by simple keywords only: interested, call me or price means Positive; not interested or stop means Not interested; anything else is Question / other. No AI is used for this classification in this version. If chatwoot is unreachable or the token is rejected, the status is recorded with the plain fix and shown on Reports and Health, and the next check simply retries. There is no background daemon: the dashboard only runs while it is open, so sync happens when you click the button or open the pages.

Email replies, honestly: listmonk sends email but does not receive it. Email replies land in your own mailbox, or inside chatwoot if you connect your email there. Until then, email outcomes are marked by hand on the Leads page. LeadForge does not fake email sync.

Safe sending rules
The Guide page has the full cards. The short version:

- WhatsApp: first contact only through the official WhatsApp Business API inside chatwoot, with an approved template message. Include an opt-out line. Personalize the first line. Send in small batches with gaps. Never send first contact from a personal number. No tool can promise zero flags; these rules keep the risk low.
- Email: set SPF, DKIM and DMARC for the sending domain inside your DNS. Start with small daily numbers. listmonk handles bounces.

Guide page
The Guide explains, in beginner language with numbered steps and real links: the free Gemini key, the free Groq key, Local AI, every server app setup, listmonk SMTP, chatwoot and WhatsApp, the lead finder and website reader (no key needed), the web pitch writer setup, safe sending, where email replies go, and the "No API key at all?" card. That card also says honestly that GitHub web to API bridge projects exist, but they need your web login cookies, break often, and can get the account flagged, so LeadForge does not use them. Copy and paste is the safe built in way.

Health page
Open Health from the sidebar on a wide screen, or from the top navigation on a phone. It checks:
- the actual dashboard address and port
- whether the data folder is writable
- whether the scraper program is found and can run
- whether the website reader setup is found
- whether Docker is installed and running
- disk space
- the latest lead list state
- every app assigned port, actual port, port state, and app state
- the Chatwoot reply sync state
- the latest errors

The same checks are available as JSON at /api/health on the dashboard address.

Error logs
LeadForge keeps two simple log files:
- dashboard\data\logs\errors.jsonl: recent warnings and errors, with time, area, code, friendly message, technical detail, and suggested fix
- dashboard\data\logs\leadforge.log: the main LeadForge event log

Both logs are capped by rotation at about 1 MB, so they cannot grow forever. Health has a Clear recent errors button. Clearing changes only the recent error display log. Secret values and API keys are never written to these logs; error messages are sanitized first.

If something fails and you ask Muse for help, send the errors.jsonl file, or copy the newest error from Health. Also say which page and button you used.

Security note
Keys stay in files on this PC only, and this dashboard is local only. Never paste API keys or app secrets into chats. Secret values are never shown after saving (only a Saved state), never written to the logs, and never included in screenshots or reports. The shipped pack contains no saved keys and no app .env files, only .env.example files, so a first run starts clean.

Where the files land
- Every pipeline run is saved in dashboard\data\runs with the date and time in the folder name.
- The last good lead list is dashboard\data\latest.csv.
- The lead store is dashboard\data\leads.json.
- Website notes are in dashboard\data\notes.
- Pitch files are in dashboard\data\pitches, one markdown file per lead.
- Reports are in dashboard\data\reports.
- The AI settings (including the key) are in dashboard\data\ai-settings.json on this PC only.
- The Chatwoot reply sync settings (including the token) are in dashboard\data\chatwoot-sync.json on this PC only.
- App setup files are the .env file inside each app folder, written from Settings.
- Dashboard startup details are in dashboard\data\server-info.json.
- App port choices are in dashboard\data\app-ports.json.
- Generated app runtime Compose files are named docker-compose.leadforge.yml inside each app folder.

Honest limits
- LeadForge itself never sends anything to any client. It finds leads, writes pitches, tracks outcomes, and starts tools. Sending happens inside the tools, by you.
- chatwoot needs a WhatsApp Business number approved by Meta before WhatsApp works in it. Email and website chat work without that.
- documenso is the one tool that is easier to run later on a small server, because its setup expects a Linux style certificate path. It is fine to leave it for later.
- LeadForge only works on this PC. It is not on the internet, and nobody else can open it.
- Reply sync runs only while the dashboard is open. There is no background service checking replies overnight.
- Error handling cannot make failures impossible. LeadForge is built to detect them, switch ports when that is safe, keep good data, log the detail, and explain the next fix in plain words.

Testing and limits
Tested on the Muse Linux computer before this pack was made (v6 test run, 64 automated checks against disposable copies of the pack, all passing):
- Settings: saving an app form writes the .env in the right folder with required keys filled; blank secrets are auto-generated and are different in two separate pack copies; the .env.example file is unchanged; a later visit shows secrets only as Saved; a blank secret on re-save keeps the existing value; a save with a required field cleared is rejected with the field names; the app state flips from Setup needed to Not started in /apps/status and /api/health; the Setup status panel flips rows from Missing to Ready. Test secret values were grepped for and are absent from errors.jsonl, leadforge.log, server-info, app-ports, and every page HTML.
- AI writer with a local stub server standing in for the providers: Gemini shape and Groq shape answers both parse into WhatsApp, subject, and email body; invalid key, rate limit, timeout, connection refused, and local model missing map to the right friendly errors; the no key state disables Generate; a qualified batch with one failing lead ends Partially done with the other pitch saved and the failed lead marked for Manual mode; pitch file content matches what the UI returned; the Leads page shows the pitch chip.
- Pitch rules: a custom rule line saved in Settings appears in the next request body for a cloud provider and for Local AI, and in the Manual mode instruction. A stub reply with a placeholder and a banned claim word triggered exactly one correction retry, and the corrected text was shown.
- Style check: a stub reply full of stock phrases was flagged Looks AI-written, rewritten once, and the saved pitch is the clean version, marked Humanized.
- Local AI with a stub Ollama: /api/tags with models passes the check and the status row turns Configured; the /v1/models fallback works when /api/tags fails; generation through /v1/chat/completions saves a pitch; connection refused shows the not running fix; a 404 shows the model missing fix with the pull command. The one click model download was tested against a stub /api/pull stream: a clean stream ends Done at 100 percent, and a stream that errors halfway ends Failed with the real error line, never hanging.
- Manual mode: the copied instruction contains the lead data, the playbook, and the reply markers; a well formed paste parses and saves as manual; a paste without markers saves the whole text with the plain notice; an empty paste is rejected; a batch paste with 2 lead sections saves 2 pitches. The web assistant setup text contains the playbook and format; the saved assistant toggle produces the short instruction without the full playbook, and the full instruction when off.
- Qualification and the lead store: fixture leads in each class classify correctly (no website confirmed, has website, website dead, unknown), and the default batch excludes has website and unknown leads.
- Full pipeline end to end with a stub scraper and a stub website reader: all five stage lines appear in the console, the summary counts are right, pitches are written only for qualified leads, and the auto report file has the right counts. Find leads only mode stops after the reader, as before.
- Chatwoot reply sync with a stub chatwoot: a matching conversation flips its lead to Replied with the snippet and a Positive tag; a 401 records the auth fix; an unreachable chatwoot records the will-recheck status and breaks nothing.
- Reports: after the stub full pipeline run, a report exists with the right counts; after outcomes are marked in the store, a regenerated report reflects them.
- Regression: the v4 and v5 core behavior (auto ports, app port manager, health, logs, run validation, malformed CSV safety, all pages) is covered by the same 64 check run.
- Browser QA: Settings, Writer (empty state, with a stub generated result, and Manual mode), Guide, Reports, Run (including a completed Full pipeline console in a disposable copy), Apps and Health, at desktop 1440x950 and at a true phone size 390x844, with zero runtime errors and no page level horizontal scroll. Screenshots were read back and checked.

Not proven on the Muse Linux computer:
- Live Gemini and Groq calls are NOT tested: no real API keys exist there. Both providers were tested only against a local stub server that returns the real response shapes. The first real call happens on your PC with your key.
- No real Ollama runs on the Muse computer. Local AI, its check, generation, and the model download were stub tested only.
- Chatwoot reply sync was tested against a stub chatwoot server, not a live chatwoot with real conversations.
- Docker is not installed there, so the five real apps were not really started there. Their Compose commands, port files, and the Settings Check setup validation were stub tested with a fake Docker, not live Docker tested.
- LeadForge.bat and the PowerShell browser opener can only be fully proven on Tanmoy Windows 11 PC.
- On the first Windows run, verify the browser opens at the address in server-info.json, Docker Desktop starts one app from its card, the Open button lands on that app, and Stop works. If any one fails, Health and errors.jsonl will show the exact area and detail to send back.
