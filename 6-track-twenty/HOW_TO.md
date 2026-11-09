twenty: the CRM that remembers every lead

What it does in the pipeline
It is the memory of the whole pipeline. Every lead, reply, call and deal lives here, so you always know who was contacted, who replied, and what happens next.

Before you start
Before starting, copy .env.example to a new file named .env and change the password and secret values in it. Twenty is powerful but heavy. You can also skip it at first and track leads in the results.csv file, then import that file here later when the list grows.

Start it
Easiest way: use the Start button on the LeadForge Apps page. LeadForge prepares safe port settings and shows the real address.
Manual way: open a terminal in this folder and run:
docker compose up -d
Stop it later with: docker compose down

Where it opens
Usual address: http://localhost:3003
If port 3003 is busy, LeadForge can switch it. Use the Open button on the LeadForge card.

First setup step inside it
Open the address above and create your workspace and admin account. Then go to People or Companies and import your leads from results.csv (folder 1). Add a stage field like New, Contacted, Replied, Call booked, Closed, so every lead has a clear next step.
