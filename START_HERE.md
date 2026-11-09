Start here: your LeadForge pack

LeadForge is the name of this pack: 7 free tools that work as one pipeline to find leads, understand them, message them, book calls, track them and close the deal. One dashboard, also called LeadForge, runs the whole thing. Work through it in order. Do not try to do everything in one day.

Step 1: Open the dashboard and get leads. No Docker needed for this step.

1. Double click LeadForge.bat in this folder.
2. A black window opens. Keep it open. Your browser opens LeadForge by itself. The usual address is http://127.0.0.1:8790, but LeadForge switches to a free port if that one is busy, and the bat opens the real address. On a wide screen the pages are in the left sidebar. On a phone they are in the top navigation.
3. On the Run page, type a location (like Halishahar) and a business type (like dentists), set max results from 1 to 200. Leave the mode on Full pipeline and click Run search. Full pipeline does everything in one click: Stage 1 Find, Stage 2 Read websites, Stage 3 Qualify, Stage 4 Write pitches, Stage 5 Check and report. Pick Find leads only when you just want the raw list.
4. Watch the status and the activity console on the same page. When it finishes, open the Leads page to see your list, and the Reports page to read the run report.
5. One time only, for website notes: run folder 2's setup_crawl4ai.bat once. Without it you still get leads, just no notes on their websites. LeadForge tells you if this step is missing.

You need Python installed for LeadForge and folder 2. Get Python 3.12 free from python.org and tick "Add python.exe to PATH" during install. Read DASHBOARD.md for what each LeadForge page does.

The simple order for everything

1. Run a search on the Run page (Full pipeline does the most for you).
2. Open Settings to set up the server apps and the free AI writer. The Setup status panel at the top shows what is still missing, field by field. No more copying or editing setup files by hand.
3. Open Writer to write and edit pitches. If you have no AI key, use Manual mode there, or set up Local AI in Settings.
4. Open Leads to mark outcomes (Replied, Call booked, Not interested, No reply). LeadForge learns from these marks.
5. Open Reports to read run reports and check for chat replies.
6. Open Guide any time you are stuck. It explains every key and every app in simple steps.

Step 2: The server tools. Only when you are ready.

1. First install Docker Desktop for Windows, free, from the official site:
   https://www.docker.com/products/docker-desktop/
2. Restart your PC after installing it, and start Docker Desktop before using the server tools.
3. Set up each tool in LeadForge Settings first. The form writes the setup file for you, and random secrets are generated for you when you leave them blank.
4. Then start ONE tool at a time from the Apps page, in this order: twenty (your CRM, folder 6), listmonk (email, folder 3), chatwoot (inbox, folder 4), cal.diy (booking, folder 5), documenso (signing, folder 7).
5. Each folder has a HOW_TO.md. Read it before starting that tool the first time.
6. Do not run all 5 server tools at the same time. Your PC will slow down. Start one, use it, stop it if you do not need it running.
7. The usual tool addresses inside LeadForge are: listmonk http://localhost:9000, chatwoot http://localhost:3001, cal.diy http://localhost:3002, twenty http://localhost:3003, documenso http://localhost:3004. If a port is busy, LeadForge switches that tool and the Apps card shows the real address. Use the card Open button.
8. If anything fails, open the Health page in LeadForge. It shows checks and recent errors. The error log is dashboard\data\logs\errors.jsonl. Send that file to Muse if you need help.

What each tool is waiting on (nothing is broken if you skip these for now)

- listmonk (folder 3) waits on an SMTP email account, set inside listmonk after it starts (Settings, then SMTP). That is the account your campaign emails are sent from, for example a Gmail app password or a free SMTP service.
- documenso (folder 7) waits on the same SMTP email account, so signing invites reach your clients. It is also the one tool that is easier to run later on a small server, see its HOW_TO.md.
- chatwoot (folder 4) waits on a WhatsApp Business number, registered and approved with Meta, if you want WhatsApp inside the inbox. Email and website chat work without it.
- cal.diy (folder 5) waits on connecting your calendar, for example Google Calendar, so bookings are real.
- twenty (folder 6) waits on nothing but your time. It is ready when you are.

Safety first when you start sending

- WhatsApp: send first contact only through the official WhatsApp Business API inside chatwoot, with an approved template, an opt-out line, and small batches. Never from a personal number. The Guide page has the full card.
- Email: set SPF, DKIM and DMARC for your sending domain, and start with small daily numbers. Email replies land in your own mailbox, not in listmonk. The Guide explains this honestly.

Read PIPELINE_FLOW.md to see how one lead travels through all 7 tools, and DASHBOARD.md for the full manual.
