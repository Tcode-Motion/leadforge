# Security Policy

## How LeadForge handles secrets

- API keys, app passwords and tokens stay on the local PC. They are stored
  in plain local files that only the dashboard reads:
  - AI keys and pitch settings in dashboard/data/ai-settings.json
  - Per app setup values in each app folder's .env file
  - The chatwoot reply check token inside ai-settings.json
- The UI never shows a saved secret again. After saving, a secret field
  shows only a masked Saved note. Leaving a secret field blank on re-save
  keeps the old value.
- Secrets are redacted from logs, error entries, HTML pages and pitch
  files by the dashboard's sanitize step. If you ever find a secret in a
  log or a report, treat it as a bug and report it.
- Never commit a .env file or dashboard/data/ai-settings.json to git. The
  shipped .gitignore blocks them. Check `git status` before every commit.

## Network exposure

- The dashboard binds to 127.0.0.1 only. It is a local control page, not a
  server. Do not expose it to a LAN or the internet, and do not put it
  behind a tunnel or a reverse proxy.
- The only outbound calls LeadForge makes are the ones you configure: the
  AI provider you pick (Gemini, Groq or your local AI server), the Google
  Maps scraper run, website reading, the chatwoot reply check against your
  own chatwoot, and Docker pulling the bundled apps' images.
- Manual web mode makes no API call at all. You carry the text to a web AI
  yourself.

## Reporting a problem

This is a solo maintained local tool. If you find a security problem, open
an issue in the repository with the smallest reproduction you can share,
and do not paste real keys, real lead phone numbers or customer data into
the report. Redact first, then send.
