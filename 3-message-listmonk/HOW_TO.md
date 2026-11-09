listmonk: your email campaign sender

What it does in the pipeline
It holds your lead lists and sends the outreach emails. You write one campaign, it sends it to the whole list and tracks opens and clicks.

Before you start
You need an SMTP email account to send from, for example a Gmail app password, Amazon SES, or any mail server you already have. Without SMTP it can store lists but cannot send. Sending from a brand new domain with no warm up hurts delivery, so pick your sending identity with care. This folder has the docker compose file and a config.toml.sample for reference.

Start it
Easiest way: use the Start button on the LeadForge Apps page. LeadForge prepares safe port settings and shows the real address.
Manual way: open a terminal in this folder and run:
docker compose up -d
Stop it later with: docker compose down

Where it opens
Usual address: http://localhost:9000
If port 9000 or its Postgres host port 5432 is busy, LeadForge can switch them. Use the Open button on the LeadForge card.

First setup step inside it
Open the address above and log in or create your admin account. Then go to Settings, then SMTP, and add your email sending account. After that, import your lead list from the twenty CRM export (folder 6) or straight from results.csv (folder 1).
