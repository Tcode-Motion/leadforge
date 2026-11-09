cal.diy: your call booking page

What it does in the pipeline
It gives you one booking link to drop into your outreach messages. A lead taps it, picks a time, and the call lands on your calendar with no back and forth.

Before you start
For real bookings it must connect to your calendar, for example your Google Calendar, so the open slots and invites are real. Before starting, copy .env.example to a new file named .env and fill in the values. Honest note: if you only need one booking link, the free hosted cal.com does the same job with zero setup. Self hosting this one pays off when you want your own brand and domain on the page.

Start it
Easiest way: use the Start button on the LeadForge Apps page. LeadForge prepares safe port settings and shows the real address.
Manual way: open a terminal in this folder and run:
docker compose up -d
Stop it later with: docker compose down

Where it opens
Usual address: http://localhost:3002
LeadForge also checks the Redis, API, and Prisma Studio host ports and can switch them if busy. Use the Open button on the LeadForge card.

First setup step inside it
Open the address above, create your account, then connect your Google Calendar and set your working hours. Your booking link is shown on your event type page, ready to paste into listmonk emails.
