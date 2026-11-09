# 05. The AI writer

The Writer turns a lead record into a WhatsApp message and an email.
There are three routes to the same writer: a free cloud key, a local AI
on your own PC, or manual mode with any web AI. All three share one
prompt builder (`build_ai_prompt()`), one Pitch Playbook, one output
checker and one style checker.

## Route 1: cloud AI with a free key

| Provider | Model | Get a free key |
| --- | --- | --- |
| Google Gemini | gemini-2.0-flash | https://aistudio.google.com/apikey |
| Groq | llama-3.3-70b-versatile | https://console.groq.com/keys |

Steps: create the key on the provider site, paste it in Settings under
Free AI, save, then click Check AI. The key is stored in
`dashboard/data/ai-settings.json` on your PC only, is shown afterwards
only as a masked Saved note, and is redacted from every log and page.
Free tiers give hundreds to roughly a thousand requests a day, which is
far more than the batch size of 10 needs. Requests time out after 30
seconds. Failures map to plain codes: AI_KEY_INVALID, AI_RATE_LIMIT,
AI_TIMEOUT, AI_OFFLINE, AI_PROVIDER_ERROR.

## Route 2: local AI (no key, no limit)

Any OpenAI compatible local server works through `{base}/v1/chat/completions`.

| Server | Default base |
| --- | --- |
| Ollama | http://127.0.0.1:11434 |
| LM Studio | http://127.0.0.1:1234 |
| llama.cpp server | http://127.0.0.1:8080 |
| KoboldCpp | http://127.0.0.1:5001 |

Settings checks the server by asking for its model list (`/api/tags`,
then `/v1/models`). Model guidance for a normal PC:

- **qwen2.5:3b (recommended)**: about 2 GB at Q4. Fits 8 GB RAM with no
  GPU, writes a pitch in tens of seconds.
- llama3.2:3b: fast English option, similar size.
- qwen2.5:7b: better writing, but borderline in 8 GB and slow on a low
  CPU.

**Download model (one click)**: when Ollama answers, Settings offers a
one click pull of the chosen model with live progress. When Ollama is
absent, you get the official download link (https://ollama.com/download)
and the steps instead. Local AI is optional; nothing requires it.

## Route 3: manual web mode (no key, no install)

1. On the Writer page, pick a lead, an output and a language, then click
   **Copy instruction**. The instruction contains the Pitch Playbook and
   the strict reply format.
2. Paste it into any web AI. Quick open buttons: ChatGPT
   (https://chatgpt.com), Gemini (https://gemini.google.com), Claude
   (https://claude.ai), Groq playground (https://console.groq.com/playground).
3. The AI must reply with markers:

```
WHATSAPP:
<the WhatsApp message>
SUBJECT:
<the email subject, only when email output was asked>
EMAIL:
<the email body>
```

4. Paste the whole reply back and save. LeadForge parses the markers.
   With no markers, it saves the whole text as the pitch and tells you
   plainly. Manual pastes get checker warnings only, never edits.
5. Batch manual mode uses one instruction with a section per lead,
   headed `=== LEAD n: <name> ===`, and parses the reply the same way.

**Web assistant setup**: the *Copy web assistant setup* button copies
the playbook plus the reply format as a one time setup for a Gemini Gem
or a ChatGPT GPT named "LeadForge Pitch Writer". After that, tick "I use
my saved web assistant" and manual copies shrink to lead blocks only:
about two pastes per 10 leads instead of ten.

## The Pitch Playbook

Settings holds two editors: rules and examples. The saved playbook is
prepended to every prompt on every route by the single prompt builder,
so cloud, local and manual pitches follow the same house style. Reset
restores the default playbook. Keep it concrete: who is sending, what
you offer, what a good pitch looks like, and one or two real examples.

## The checkers

**Output checker** (`validate_pitch_output()`): markers present,
WhatsApp length roughly 30 to 140 words, no leftover bracket
placeholders, and no banned fake claim words: guaranteed, guarantee,
100 percent result, number one, best in the world. On failure the writer
makes exactly one automatic correction retry with the problem named.

**AI style checker** (`style_check_pitch()`): looks for stock phrases
("I hope this message finds you well", "in today's fast-paced world",
"boost your business", "take your business to the next level",
"esteemed", "delve" and friends), em or en dash characters, uniform
sentence lengths, a missing business name or locality, and bracket
placeholders. The verdict is Looks human, Some AI signs or Looks
AI-written, with the top reasons. If a generated pitch reads AI-written,
the writer makes one rewrite pass through the same provider, rechecks,
and saves the better version, marked Humanized. This is a local
estimate, not a guarantee about any external detector.

## The retry ladder

For each lead, `pitch_attempts_for_lead()` tries, in order:

1. The chosen provider with the full prompt.
2. The same provider with a simpler, shorter prompt.
3. The other configured provider, if one exists.
4. Mark the lead for manual mode and continue with the next lead.

Every step is logged in the batch console with its error code, so a
failed lead is visible, never silent.

## The region pack

Language Auto (by region), the default, reads the lead's address and
picks a language style:

| Region | Style |
| --- | --- |
| West Bengal | Bangla or Bengali friendly English |
| Delhi | Hinglish friendly English |
| Maharashtra | Hinglish or Marathi friendly English |
| Tamil Nadu | English, with a Tamil greeting as an option |
| Karnataka | English |
| Uttar Pradesh | Hinglish friendly English |
| Gujarat | English or Gujarati friendly English |
| Kerala | English |
| Anywhere else in India | English |

The locality from the address is also used as the local touch in the
pitch ("I saw your clinic in Halishahar"), because a pitch may only use
facts from the lead record itself. Nothing is invented: no ratings, no
prices, no claims about the business that the data does not show.
