# 04. Finding and qualifying

Two of the seven tools do the finding work, and the dashboard turns their
output into one honest qualification per lead.

## Finding: the Google Maps scraper

- Tool: gosom/google-maps-scraper (MIT), folder
  `1-find-google-maps-scraper`, run by the dashboard as a subprocess.
- Input: one query built from your Location and Business type, for
  example "dentists in Halishahar". The folder also keeps `queries.txt`
  and `run_scraper.bat` for manual runs outside the dashboard.
- Max results: the scraper has no exact result limit flag. LeadForge
  maps your number (1 to 200) to a scroll depth, so the count you get
  is close to what you asked, not exact. The Run page says this openly.
- Output: a results CSV with the business name, phone, website, address
  and rating fields the scraper found.
- Safety checks: the file is parsed strictly before anything is saved
  (header check, duplicate header check, NUL byte check). A malformed
  file fails with SCRAPER_CSV_MALFORMED and the previous good
  `latest.csv` is kept untouched. A valid run with zero rows is labelled
  as a zero result run, not an error.
- Timeouts and failures: default timeout 900 seconds. Missing binary,
  non executable binary, start failure, timeout, missing output and a
  partial output each have their own code and fix in
  docs/09-troubleshooting.md.
- Reality note: Google can show bot checks, ask for consent, or change
  Maps at any time. A search can return fewer leads than asked, or none.
  That is a Google limit, not a LeadForge crash, and the console says so
  in plain words.

## Reading: crawl4ai

- Tool: unclecode/crawl4ai (Apache 2.0), folder
  `2-understand-crawl4ai`. One time setup: `setup_crawl4ai.bat`.
- In a pipeline run, `dashboard/enrich.py` takes the websites from the
  fresh results (up to 15), fetches each one, and saves one markdown
  note per site under `dashboard/data/notes/`.
- Each site is isolated: a dead or slow site prints an ENRICH_FAILED
  line and the run continues. The step ends with attempted, succeeded
  and failed counts, and a Done or Partially done state.
- The notes give the writer real facts to mention. A lead with no note
  is pitched from its listing facts only.

## Qualifying: the four classes

`compute_qualification()` in `dashboard/app.py` assigns exactly one
class per lead, from two facts: what the Google listing shows, and what
the reader found.

| Class | Meaning, exactly |
| --- | --- |
| `no_website_confirmed` | The listing shows no website AND the reader found none either |
| `website_dead` | A website is listed, but fetching it fails |
| `has_website` | A website is listed and it loads, or a note was prepared for it |
| `unknown` | Not enough data to say (no listing website field and no reader result) |

Honesty note: "confirmed" means only what the table says. LeadForge
never claims a business has no website in any wider sense; it reports
that the Google listing shows none and the reader found none. The dead
website class is its own pitch angle: their listed site is broken.

## Who gets pitched

- The default batch covers `no_website_confirmed` plus `website_dead`
  only, first 10 leads, one at a time.
- `has_website` leads join a batch only through the labelled toggle on
  the Writer page.
- `unknown` leads are always excluded from batches. You can still write
  for one by hand from the lead picker, knowing the data is thin.
- Every run summary and every report counts the classes separately, so
  you can see exactly what was found.
