How one lead travels through LeadForge

Follow one example lead, a dental clinic in Halishahar, from first search to signed proposal.

1. Found by the scraper (folder 1-find-google-maps-scraper)
You run run_scraper.bat. The query "dentists in Halishahar" from queries.txt finds the clinic. It lands as one row in results.csv with its name, phone, website and address.

2. Understood by crawl4ai (folder 2-understand-crawl4ai)
You copy the clinic website from results.csv into websites.csv and run scrape.py. The clinic page text is saved as a file in the output folder. You read it and learn the clinic offers implants and braces but has no online booking. That one fact is your pitch angle.

3. Tracked in twenty (folder 6-track-twenty)
You import results.csv into twenty. The clinic is now a company in your CRM with a stage: New. Every later step updates this same record, so nothing is lost.

4. Messaged by listmonk (folder 3-message-listmonk)
You export the New leads from twenty (or use results.csv directly) and import them into listmonk as a list. Your campaign email is personal: it names the clinic, mentions implants, and points out the missing online booking. It ends with your booking link from step 5.

5. Replies land in chatwoot (folder 4-inbox-chatwoot)
The clinic replies, and later sends a WhatsApp message. Both show up in one chatwoot inbox. You answer from one place and mark the lead stage in twenty as Replied.

6. Call booked on cal.diy (folder 5-book-caldiy)
The clinic taps your booking link and picks a time. Because cal.diy is connected to your calendar, the call appears there automatically. You update the stage in twenty: Call booked.

7. Deal closed on documenso (folder 7-close-documenso)
After the call, the clinic says yes to a booking page build. You send your standard proposal from documenso. The clinic signs it online. You update the stage in twenty: Closed. The pipeline has done its full round.

Quick file map
- Leads are born in: 1-find-google-maps-scraper/results.csv
- Lead research is saved in: 2-understand-crawl4ai/output/
- The CRM import file is the same results.csv, imported into twenty (folder 6)
- Campaign lists in listmonk (folder 3) come from a twenty export or from results.csv
- The booking link pasted into emails is created in cal.diy (folder 5)
- The signed proposal is sent from documenso (folder 7)
