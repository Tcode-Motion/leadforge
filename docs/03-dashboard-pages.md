# 03. Dashboard pages

The dashboard has eight pages in the sidebar (on a phone, in the top
bar). This page says what each one shows and what each button does.

## Run

The command page. Shows the five stage stepper (Find, Read, Qualify,
Write, Check and report), counters for the latest results, the search
form, and the activity console.

- **Location** and **Business type**: both required, 2 to 80 characters.
- **Max results**: 1 to 200. Approximate; it sets the scraper scroll
  depth.
- **Mode**: Full pipeline (default) or Find leads only.
- **Run search**: starts the one background job. While a job runs, the
  button state and the console update live from `GET /status`. A second
  start is refused with a note.
- The console prints one line per stage with counts, and the job ends as
  Done, Partially done or Failed, always with a plain summary.

## Leads

The CRM style library of every lead in the store.

- Table columns come from the lead store: business details, phone,
  website, the qualification chip, pitch state and the outcome control.
- **Filter box** narrows the table by text, in the browser only.
- **Qualification filter** shows one class at a time.
- **Outcome select** per lead saves through `POST /leads/outcome`
  (New, Pitched, Replied, Call booked, Not interested, No reply).
- **Download CSV** saves the latest results file
  (`/download/latest.csv`). If there are no results yet, it answers with
  a friendly 404 page instead of an empty file.

## Writer

Where pitches are written, checked and copied.

- **Lead picker**: choose one lead from the store. Leads that already
  have a pitch show a pitch chip.
- **Output**: WhatsApp, Email or Both.
- **Language**: English, Bangla, or Auto (by region), the default.
- **Generate**: writes one pitch with the configured provider, runs the
  output checker and the style checker, and saves the markdown file to
  `dashboard/data/pitches/`. Results are editable; word counts update as
  you type.
- **Copy buttons** copy the WhatsApp text or the email (subject plus
  body) to the clipboard.
- **Regenerate** runs the writer again for the same lead.
- **Batch**: writes for the first 10 qualified leads (no website
  confirmed plus website dead). A labelled toggle can include has
  website leads. Unknown leads are never batched.
- **Manual mode**: *Copy instruction* builds the full instruction text
  (Pitch Playbook plus the strict reply markers). Quick open buttons
  link to ChatGPT, Gemini, Claude and the Groq playground. Paste the
  reply into the paste box and save; LeadForge parses the markers, and
  if there are no markers it saves the whole text with a plain notice.
  The batch manual form works the same way with one section per lead.
- **Web assistant**: *Copy web assistant setup* gives a one time setup
  text for a Gemini Gem or a ChatGPT GPT named "LeadForge Pitch Writer".
  The "I use my saved web assistant" toggle then shortens every manual
  copy to lead blocks only.
- **What is working** card: once at least 3 pitched leads have outcomes,
  it summarises which pitches earned replies or calls, and that summary
  is added to new prompts. Before that it says it is still learning.

## Apps

The control room for the five server apps (listmonk, chatwoot, cal.diy,
twenty, documenso). Each card shows an icon, what the app is for, a
status pill, its current address, and an output terminal.

- **Start** and **Stop**: run Docker Compose for that app through the
  generated runtime compose file. Busy ports switch automatically and
  the card shows the new address.
- **Open**: opens the app at its current address.
- **Start all**: starts the apps one by one. A failure stays visible on
  its own card and does not stop the rest.
- **Setup needed** state: the card names the fix. Fill the app's form on
  the Settings page; LeadForge does not invent setup values on its own
  except the secrets marked as auto generated there.
- **Check setup** (from Settings) runs a real compose config validation
  for the app.

## Settings

Four groups of forms, plus the live Setup status panel at the top.

- **Setup status panel**: one row per app naming the fields still
  missing, and the AI writer state. The same panel heads the Guide page.
- **App setup forms**: one form per app that needs a `.env` before it can
  start (chatwoot, cal.diy, twenty, documenso). Secret fields are
  password inputs; after saving they show only as a masked Saved note,
  and leaving one blank on re-save keeps the old value. Fields marked
  auto are generated for you when left blank. **Save setup** writes the
  app's `.env`; **Check setup** validates it. listmonk has a guidance
  card instead, because its sending setup happens inside listmonk.
- **Free AI form**: provider choice (Gemini, Groq or Local AI), the API
  key (masked after saving), local base URL and model name. **Save**,
  then **Check AI** or **Check local AI** to test the route.
- **Download model (one click)**: appears when a local AI server
  answers. It pulls the chosen model with live progress. If no local
  server answers, the official Ollama download link and steps show
  instead.
- **Pitch Playbook**: two editors, rules and examples, with **Save
  playbook** and **Reset to default**.
- **Chatwoot reply check card**: base URL, account ID and API access
  token (masked). Used by the reply check on the Reports page.

## Guide

Beginner cards, in the order to do them: the two free AI keys with the
exact signup links, local AI, per app setup, the listmonk SMTP path,
chatwoot WhatsApp Business, how finding and reading work, the "No API
key at all?" card (manual mode, plus an honest note about web to API
bridge tools), and the safe sending rules. The Setup status panel at
the top always shows what is still missing.

## Reports

- Lists every saved report with its headline counts, and renders the
  latest report on the page.
- **Generate report now** builds a fresh report from the lead store.
- **Check replies now** runs the chatwoot reply check (it also runs when
  the page opens and a sync is due): open conversations are matched to
  leads by phone and outcomes are updated. The sync state (done,
  unreachable, unauthorized) is shown with a plain fix.

## Health

The control room for the dashboard itself.

- **Status summary** and diagnostic cards: server, Docker, disk space,
  data folder and logs, each with a state and a fix when something is
  wrong.
- **Ports table**: the dashboard port and every app port, preferred and
  actual, with switched ports marked.
- **Recent errors**: the error timeline from
  `dashboard/data/logs/errors.jsonl`, newest first, each with its code,
  message and fix. **Clear errors** empties the display.
- The same data is available as JSON at `/api/health` and `/api/errors`.
