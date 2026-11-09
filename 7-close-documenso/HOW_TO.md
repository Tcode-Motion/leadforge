documenso: proposals the client signs online

What it does in the pipeline
When a lead says yes, you send the proposal or agreement from here and the client signs it online. No printing, no scanning, no chasing paper.

Before you start
You need an SMTP email account so the signing invites reach clients by email. It can be the same account you use for listmonk (folder 3). Before starting, copy .env.example to a new file named .env and fill in your values. One warning: this compose file was written for a Linux server. It expects a signing certificate file at the path /opt/documenso/cert.p12 on the host. On a Windows PC that path needs adjusting, so this is the one tool that is easier to run later on a small server. Nothing is broken if you skip it for now.

Start it
Easiest way: use the Start button on the LeadForge Apps page. LeadForge prepares safe port settings and shows the real address.
Manual way: open a terminal in this folder and run:
docker compose up -d
Stop it later with: docker compose down

Where it opens
Usual address: http://localhost:3004
If port 3004 is busy, LeadForge can switch it. Use the Open button on the LeadForge card.

First setup step inside it
Open the address above and create your account. Add your SMTP settings, then upload your standard proposal or agreement as a template, ready to send to the next client who says yes.
