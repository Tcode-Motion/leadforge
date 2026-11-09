chatwoot: one inbox for all replies

What it does in the pipeline
It collects replies from WhatsApp, email, Instagram and your website chat into one shared inbox, so no lead reply gets lost and you can answer from one place.

Before you start
This is the heaviest tool in the pack. It normally lives on a server with a domain name and HTTPS. WhatsApp needs a WhatsApp Business number connected through Meta (free Cloud API with a registered business number, or a paid provider). Before starting, copy .env.example to a new file named .env and fill in your domain and secret values. Without the WhatsApp number it still works for email and website chat.

Start it
Easiest way: use the Start button on the LeadForge Apps page. LeadForge prepares safe port settings and shows the real address.
Manual way: open a terminal in this folder and run:
docker compose up -d
Stop it later with: docker compose down

Where it opens
Usual address: http://localhost:3001
If the web, Postgres, or Redis host port is busy, LeadForge can switch it. Use the Open button on the LeadForge card.

First setup step inside it
Open the address above and create your admin account. Then go to Inboxes and add your first channel (website chat is the quickest to test). Add the WhatsApp channel when your business number is approved by Meta.
