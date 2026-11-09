# 08. Reports and outcomes

## The lead store

Every lead LeadForge has ever found lives in one store:
`dashboard/data/leads.json`. When a run finishes, its results are
merged into the store:

- Leads match by **phone number** (fallback: name plus city), so the
  same business found twice stays one record.
- Each record keeps first seen and last seen times, the listing facts,
  its qualification class, a link to its website note, a link to its
  pitch file, and its outcome.
- The Leads page reads the store, so it shows history, not just the
  last run. The store is a plain JSON file; keep a backup copy before
  big edits. If the file ever becomes unreadable, the dashboard logs
  STORE_CORRUPT, starts from an empty store view, and leaves the file
  itself untouched so you can repair it.

## Outcomes

Each lead carries one outcome, set on the Leads page:

| Outcome | Meaning |
| --- | --- |
| New | Found, nothing done yet |
| Pitched | A pitch was written (set automatically when a pitch is saved) |
| Replied | The business answered |
| Call booked | A call is scheduled |
| Not interested | They said no |
| No reply | Pitched, time passed, silence |

Mark outcomes honestly and promptly. Two features depend on them: the
reports below, and the learning card.

## The What is working card

On the Writer page, once at least 3 pitched leads have outcomes,
LeadForge summarises the pattern (for example, which style of pitch
earned replies or booked calls). That one line summary is added to new
prompts as a "What has worked so far" hint. Before 3 outcomes exist,
the card says it is still learning. It never invents a pattern from
thin data.

## Reports

- A report is generated **automatically at the end of every full
  pipeline run**, and any time with **Generate report now** on the
  Reports page.
- Reports are markdown files in `dashboard/data/reports/`. Sections:
  Found, Qualified (by class), Pitched, Failed (with reasons), Replies,
  Calls booked, Not replied, Not interested, Still new.
- The Reports page lists every report with its headline counts and
  renders the latest one on the page.

## Chatwoot reply check

Replies are how outcomes update themselves for WhatsApp conversations.

- Settings card: chatwoot base URL (default http://localhost:3001),
  account ID, and an API access token, stored masked like every secret.
- **Check replies now** (Reports page; also offered on Health, and run
  when the Reports page opens and a check is due) calls
  `{base}/api/v1/accounts/{id}/conversations?status=open`, at most 50
  conversations.
- A conversation matches a lead when the contact phone's last 10 digits
  match. A matched lead's outcome becomes **Replied**, unless it is
  already **Call booked**. The reply snippet and time are stored on the
  record.
- Tagging is **keyword only**, and the UI says so: words like
  interested, call me or price tag a reply positive; not interested or
  stop tag it negative; anything else is a question or other. It is a
  sorting aid, not a reading of intent.
- If chatwoot is unreachable or the token is wrong (401), the sync
  status records the problem with a plain fix and a will-recheck state.
  The check runs again when the page is opened; there is no background
  daemon, because the dashboard only runs while its window is open.

## Email reply honesty

listmonk sends email. It does not receive it. Email replies land in
your mailbox, or in chatwoot if you connect that mailbox as an inbox
there. Until one of those is true, mark email outcomes by hand on the
Leads page. LeadForge never pretends to sync email replies it cannot
see.
