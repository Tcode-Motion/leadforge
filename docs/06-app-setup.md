# 06. App setup

The five server apps run in Docker. Four of them need a setup file
(`.env`) before they can start. LeadForge gives each one a form on the
Settings page, so you never copy or edit setup files by hand. In every
form: secret fields are password inputs, a saved secret shows afterwards
only as a masked Saved note, leaving a secret blank on re-save keeps the
old value, and fields marked auto are generated for you when left blank.
After saving, the app leaves the Setup needed state. **Check setup** on
the form runs a real `docker compose config` validation.

## listmonk (email campaigns)

- Folder `3-message-listmonk`, address port 9000, database Postgres on
  host port 5432 (auto switched if busy).
- No pre-start setup form: listmonk starts without a `.env`. Its
  guidance card on Settings explains the one real setup: after starting
  listmonk, open it, sign in, and set your sending (SMTP) details inside
  listmonk itself under its Settings. You need an email sending account
  for this; listmonk only sends, it is not a mailbox.
- See docs/07-sending-safely.md for the domain records (SPF, DKIM,
  DMARC) a sending domain needs.

## chatwoot (inbox)

- Folder `4-inbox-chatwoot`, address port 3001, Postgres 5432 and Redis
  6379 (auto switched if busy).
- Required fields: **SECRET_KEY_BASE** (auto generated) and
  **POSTGRES_PASSWORD** (auto generated). Those two are all LeadForge
  needs to start it.
- WhatsApp note: chatwoot talks to WhatsApp through the official
  WhatsApp Business API. Connecting a number is done inside chatwoot
  with a WhatsApp Business account; LeadForge cannot do that part for
  you, and first contact messages need an approved template. Read
  docs/07-sending-safely.md before connecting a number.
- The reply check settings (base URL, account ID, API access token)
  live in their own Settings card; see docs/08-reports-and-outcomes.md.

## cal.diy (booking)

- Folder `5-book-caldiy`, address port 3002, Redis 6379, API 8080 and
  Prisma Studio 5555 (auto switched if busy).
- Required fields: **DATABASE_URL** and **DATABASE_DIRECT_URL** (the
  database connection strings), **NEXTAUTH_SECRET** (auto generated),
  **CALENDSO_ENCRYPTION_KEY** (auto generated) and **JWT_SECRET** (auto
  generated, listed from the Compose file).
- After it starts, connect your calendar inside cal.diy itself; that is
  where leads' bookings land.

## twenty (CRM)

- Folder `6-track-twenty`, address port 3003. Its database and cache run
  inside Docker without published host ports.
- Required fields: **PG_DATABASE_PASSWORD** (auto generated) and
  **ENCRYPTION_KEY** (auto generated).
- The compose file also receives its server URL from LeadForge, so the
  app knows its real address after a port switch.

## documenso (proposals and signing)

- Folder `7-close-documenso`, address port 3004. Its database runs
  inside Docker without a published host port.
- Required fields: **POSTGRES_USER** (default documenso),
  **POSTGRES_PASSWORD** (auto generated), **POSTGRES_DB** (default
  documenso), **NEXTAUTH_SECRET** (auto generated),
  **NEXT_PRIVATE_ENCRYPTION_KEY** and
  **NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY** (auto generated),
  **NEXT_PUBLIC_WEBAPP_URL** (LeadForge keeps it in step with the real
  port), the two database URLs (rebuilt from the saved Postgres
  values), and the SMTP from fields.
- Certificate note: documenso signs documents with a certificate file.
  The upstream production Compose mounts a signing certificate at a
  fixed path; on a Windows PC that path needs adjusting before signing
  works fully. The app itself starts and runs without it; treat signing
  as the last step, ideally on a small server later.

## General notes

- Start one server app at a time on an 8 GB PC. All five at once is
  heavy, and nothing in the pipeline needs all five together.
- Every app's address follows its real port. The Apps page always shows
  the current address, and Open uses it.
- If Docker Desktop is not installed or not running, the Apps and
  Health pages say exactly that, with the fix. Finding leads and
  writing pitches never need Docker.
