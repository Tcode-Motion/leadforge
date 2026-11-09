# 10. Hosting later (optional, for later)

Status: optional reading for later. Nothing in LeadForge needs this
today, and this page makes no recommendation. It exists so the facts
are written down in one place.

## What actually needs an always on host

Only the inbox style apps benefit from running all day: chatwoot (so
WhatsApp and email replies arrive in one inbox at any hour), and with
it listmonk, twenty and documenso if you want them reachable at any
time. They need Docker, storage that persists, and a public address so
WhatsApp can deliver webhooks.

Finding leads, reading websites, qualifying, writing pitches and making
reports are batch jobs. They run fine on the laptop, on demand, in
minutes. They never need a server.

## What the dashboard computer cannot do

The LeadForge dashboard is a local control page bound to 127.0.0.1. It
is not a public server and should not be turned into one.

## Options, stated neutrally

- Keep everything on the laptop. Works today; the inbox is only live
  while the laptop is on.
- A home server: an old laptop or small PC left plugged in at home,
  running the Docker apps. No monthly cost beyond power; reachable from
  outside only with extra setup.
- A small cloud server (VPS): runs Docker all day with a public
  address. Costs a small monthly amount; needs basic server care.
- Free tiers of hosting platforms: they exist, but free tiers commonly
  sleep when idle and can lose stored data, which makes them a poor
  fit for an inbox or a CRM.
- Git based automation (for example scheduled runs in a git hosting
  service): suitable for batch jobs like scheduled lead finds or
  reports. It is not a host: runs are temporary, with no permanent
  storage or public address, so it cannot run chatwoot or a CRM.

## When this page matters

Only if replies start arriving at hours when the laptop is off, and
only after the tool itself is in daily use. Until then, the laptop
setup in docs/01-getting-started.md is the whole story.
