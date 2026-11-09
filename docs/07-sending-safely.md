# 07. Sending safely

LeadForge writes pitches. Sending them is where accounts get flagged,
so these rules are part of the tool, not fine print.

## WhatsApp

- First contact goes only through the **official WhatsApp Business
  API**, connected inside chatwoot with a WhatsApp Business account.
  Never send first contact pitches from a personal number, and never
  use unofficial bulk sender tools.
- The first message must be an **approved template** in the WhatsApp
  Business account. Free form chat is for replies, after the person
  answers.
- Every first message carries a **personalized first line** (the
  business name and locality from the lead record) and an **opt out
  line** (for example: "Reply STOP and I will not message again.").
  Honor every opt out at once.
- Send in **small batches with gaps** between them. Start with a few
  messages a day on a new number and grow slowly. Do not blast the
  whole lead list on day one.
- Honest limit: **no tool can promise zero flags.** WhatsApp judges the
  number's history, the template quality and how many people block or
  report. A flagged or banned number is a real risk even when every
  rule above is followed. Send like a person, not like a machine.

## Email

- Set up the domain records before sending: **SPF** (who may send for
  your domain), **DKIM** (messages are signed) and **DMARC** (what to
  do with unsigned mail). Without them, most first emails land in spam.
- listmonk sends the campaign and handles bounces and unsubscribes.
  Keep its lists clean; remove hard bounces instead of retrying them.
- Warm up slowly: small daily numbers first (tens, not hundreds), only
  to real business addresses you found publicly, one clear offer, one
  plain text style message, and an unsubscribe link in every campaign.
- Email replies land in your mailbox, or in chatwoot if you connect the
  mailbox there. LeadForge does not read your mailbox; mark email
  outcomes by hand on the Leads page.

## What LeadForge will not do

- It does not send anything by itself. You press send in chatwoot or
  listmonk.
- It does not write fake claims. The output checker rejects pitches
  with guarantee language, invented results or placeholders, and the
  writer may only use facts from the lead record.
- It does not scrape personal phone numbers for WhatsApp blasts. The
  leads are businesses with publicly listed numbers, contacted about
  their business.
