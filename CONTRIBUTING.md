# Contributing to LeadForge

LeadForge is a small local tool maintained by one person. Contributions are
welcome when they keep the tool simple, local and honest.

## Ground rules

1. The dashboard must stay dependency free. dashboard/app.py uses only the
   Python standard library. Do not add pip packages to the dashboard.
2. The dashboard binds to 127.0.0.1 only. Never change it to listen on the
   network.
3. Secrets never leave the PC. Never log, print or commit an API key, an
   app password or a token. Keys are shown in the UI only as a masked
   Saved note.
4. Never commit a real .env file or dashboard/data/ai-settings.json. The
   .gitignore already blocks them; do not force add them.
5. Friendly errors only. Any failure a user can hit must end in a plain
   language message with a fix, and a structured entry in
   dashboard/data/logs/errors.jsonl. A stack trace in the browser is a bug.
6. No fake claims in pitches, docs or UI text. Pitches may only use facts
   from the lead record itself.
7. Keep upstream tool folders untouched. LeadForge adapts to the seven
   bundled tools through generated files (for example
   docker-compose.leadforge.yml), never by editing their originals.

## How to work on it

1. Copy the repository to a scratch folder for risky experiments. The
   dashboard writes live state into dashboard/data, so test copies keep
   your real leads and keys safe.
2. Run the dashboard with `python dashboard/app.py` and open the address
   it prints (usually http://127.0.0.1:8790).
3. Before submitting a change, run the test suites in tests/:
   - The v6 regression suite (stub AI and stub chatwoot included).
   - The fault injection suite in tests/run_fault_tests.py, which covers
     corrupt data files, hanging AI endpoints, a missing scraper, a busy
     port, oversized forms and a deliberate handler crash.
   Every check must pass, and the app must still answer GET / with 200
   after each fault.
4. Update docs/FEATURES.md when you add, move or remove a feature, and add
   a CHANGELOG.md entry.

## Style

- Plain words in user facing text. Short sentences. No em dash or en dash
  characters in authored text.
- Small, surgical changes. Match the existing code layout before inventing
  a new one.
- Comments explain why, not what.
