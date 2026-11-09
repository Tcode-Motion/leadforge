# 01. Getting started

LeadForge runs on your own Windows PC. This page takes you from the zip
file to your first list of leads.

## What you need

- Windows 10 or 11
- Python 3.12 from https://www.python.org/downloads/ (tick the box
  "Add python.exe to PATH" during install)
- Docker Desktop from https://www.docker.com/products/docker-desktop
  (only for the five server apps; skip it for now if you only want to
  find leads and write pitches)
- About 8 GB RAM is workable if you run one server app at a time

## Install

1. Unzip the repository. You get one folder named `leadforge`. Keep its
   inside layout as it is; the dashboard finds the tool folders by their
   numbered names.
2. Inside it you will see `LeadForge.bat`, the `dashboard` folder, and
   seven numbered tool folders.

## First run

1. Double click `LeadForge.bat`.
2. A black window opens. That window is the LeadForge server. Keep it
   open while you work; close it to stop LeadForge.
3. Your browser opens by itself at the real dashboard address. The usual
   address is http://127.0.0.1:8790. If that port is busy, LeadForge
   picks the next free port and the launcher opens that address instead.
   You never need to guess the port.
4. If LeadForge is already running, the launcher opens the running
   dashboard instead of starting a second copy.
5. If startup fails, the black window stays open and names the log files.
   Nothing fails silently.

## Your first lead search

1. Open the **Run** page.
2. Type a **Location** (for example `Halishahar`) and a **Business type**
   (for example `dentists`). Both need at least 2 characters.
3. Set **Max results** between 1 and 200. Start with 30. The number is
   approximate: the scraper has no exact limit, so LeadForge turns it
   into a scroll depth.
4. Leave the mode on **Full pipeline**. It runs all five stages in one
   click: Find, Read websites, Qualify, Write pitches, Check and report.
   Pick **Find leads only** when you just want the raw list.
5. Click **Run search**. Watch the activity console on the same page. One
   job runs at a time; a second click while a job runs is refused with a
   polite note.
6. When it ends, open the **Leads** page to see the list, and the
   **Reports** page to read the run report.

One time only, for website notes: open folder `2-understand-crawl4ai` and
run `setup_crawl4ai.bat` once. Without it you still get leads, just no
website notes. LeadForge tells you on the Run page if this step is
missing.

## What to do next

- Open the **Guide** page in the dashboard. It has short cards for the
  free AI keys, per app setup, and safe sending rules.
- Open **Settings** when you are ready to write pitches or start the
  server apps. The Setup status panel at the top names exactly what is
  still missing. See docs/06-app-setup.md.
- Read docs/07-sending-safely.md before sending any message to anyone.
