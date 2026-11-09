# Enrich step for LeadForge.
# Reads a CSV of websites and saves one clean text note per site.
# Usage: python enrich.py <websites.csv> <output folder>
# One bad website never stops the others. The final ENRICH_SUMMARY line is
# read by the dashboard so it can report exact counts.

import asyncio
import csv
import re
import sys
from pathlib import Path

try:
    from dashboard.intelligence import extract_emails_from_text, extract_social_links, audit_website
except ImportError:
    try:
        from intelligence import extract_emails_from_text, extract_social_links, audit_website
    except ImportError:
        extract_emails_from_text = lambda t: []
        extract_social_links = lambda t: {"links": {}}
        audit_website = lambda u, h: {"score": 50, "recommendations": []}


def load_urls(input_file):
    urls = []
    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            if "website" in row and row["website"]:
                url = row["website"].strip()
            else:
                values = [value for value in row.values() if value]
                url = values[0].strip() if values else ""
            if not url:
                continue
            if not url.startswith("http"):
                url = "https://" + url
            urls.append(url)
    return urls


def file_name_for(url, index):
    host = re.sub(r"^https?://", "", url).split("/")[0]
    host = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
    return f"{index:02d}-{host}.md"


def clean_error(exc):
    return re.sub(r"\s+", " ", str(exc)).strip()[:500]


def fetch_basic_note(url):
    import urllib.request
    import ssl
    import json
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        raw_html = resp.read().decode("utf-8", errors="replace")

    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = title_m.group(1).strip() if title_m else ""
    desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', raw_html, re.IGNORECASE | re.DOTALL)
    if not desc_m:
        desc_m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', raw_html, re.IGNORECASE | re.DOTALL)
    desc = desc_m.group(1).strip() if desc_m else ""

    # Deep intelligence extraction
    emails = extract_emails_from_text(raw_html)
    social_res = extract_social_links(raw_html)
    social = social_res.get("links", {})
    audit = audit_website(url, raw_html)

    clean = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    text = f"# Website Notes & Intelligence for {url}\n\n"
    if title:
        text += f"**Title:** {title}\n\n"
    if desc:
        text += f"**Description:** {desc}\n\n"

    # Contact & Channels block
    text += "### Direct Contact & Social Channels\n"
    text += f"- **Emails Found:** {', '.join(emails) if emails else 'None detected on page'}\n"
    for s_name, s_url in social.items():
        if s_url:
            text += f"- **{s_name.title()}:** {s_url}\n"
    text += "\n"

    # Website Audit block
    text += f"### Website Conversion Audit (Score: {audit.get('score', 50)}/100)\n"
    text += f"- **Mobile Responsive:** {'Yes' if audit.get('has_viewport') else 'No'}\n"
    text += f"- **SSL Secured:** {'Yes' if audit.get('has_ssl') else 'No'}\n"
    text += f"- **Instant WhatsApp Widget:** {'Yes' if audit.get('has_whatsapp') else 'No'}\n"
    text += f"- **Online Booking Calendar:** {'Yes' if audit.get('has_booking') else 'No'}\n"
    text += f"- **Sticky Click-to-Call:** {'Yes' if audit.get('has_click_to_call') else 'No'}\n\n"

    recs = audit.get("recommendations", [])
    if recs:
        text += "### Recommended Changes for Higher Client Conversions:\n"
        for idx, rec in enumerate(recs, 1):
            text += f"{idx}. {rec}\n"
        text += "\n"

    if clean:
        text += f"### Website Content Extract:\n{clean[:2500]}\n"

    intel_payload = {
        "url": url,
        "title": title,
        "description": desc,
        "emails": emails,
        "social": social,
        "audit": audit,
    }

    return text, intel_payload


async def run_crawl(urls, output_dir):
    try:
        from crawl4ai import AsyncWebCrawler
    except Exception as exc:
        print(f"crawl4ai not found ({clean_error(exc)}). Using fast built-in HTTP website reader...", flush=True)
        succeeded = 0
        failed = 0
        for i, url in enumerate(urls, start=1):
            print(f"Reading {url} via built-in reader...", flush=True)
            try:
                res = fetch_basic_note(url)
                if isinstance(res, tuple):
                    text, intel_payload = res
                else:
                    text, intel_payload = res, {}
                if not text or len(text.strip()) < 20:
                    raise RuntimeError("Site returned an empty or unreadable page.")
                out_file = output_dir / file_name_for(url, i)
                out_file.write_text(text, encoding="utf-8")
                if intel_payload:
                    try:
                        import json
                        out_file.with_suffix(".json").write_text(json.dumps(intel_payload, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                succeeded += 1
                print(f"  Saved note {out_file.name} with deep intelligence", flush=True)
            except Exception as e:
                failed += 1
                print(f"ENRICH_FAILED {url} {clean_error(e)}", flush=True)
        print(f"ENRICH_SUMMARY attempted={len(urls)} succeeded={succeeded} failed={failed}", flush=True)
        return 0 if failed == 0 else (3 if succeeded > 0 else 4)

    succeeded = 0
    failed = 0
    try:
        async with AsyncWebCrawler() as crawler:
            for i, url in enumerate(urls, start=1):
                print(f"Reading {url} ...", flush=True)
                try:
                    result = await asyncio.wait_for(crawler.arun(url=url), timeout=45)
                    if not result.success:
                        raise RuntimeError(result.error_message or "The site did not return readable content.")
                    markdown = result.markdown
                    text = getattr(markdown, "raw_markdown", None) or str(markdown)
                    if not text.strip():
                        raise RuntimeError("The site returned an empty page.")
                    out_file = output_dir / file_name_for(url, i)
                    out_file.write_text(text, encoding="utf-8")
                    succeeded += 1
                    print(f"  Saved note {out_file.name}", flush=True)
                except Exception as exc:
                    failed += 1
                    print(f"ENRICH_FAILED {url} {clean_error(exc)}", flush=True)
                    print("  Could not read this one, skipping.", flush=True)
    except Exception as exc:
        remaining = len(urls) - succeeded - failed
        if remaining > 0:
            failed += remaining
            for url in urls[succeeded + failed - remaining:]:
                print(f"ENRICH_FAILED {url} Website reader stopped: {clean_error(exc)}", flush=True)
    print(f"ENRICH_SUMMARY attempted={len(urls)} succeeded={succeeded} failed={failed}", flush=True)
    if failed == 0:
        return 0
    if succeeded > 0:
        return 3
    return 4


async def main():
    if len(sys.argv) < 3:
        print("Usage: python enrich.py <websites.csv> <output folder>")
        print("ENRICH_SUMMARY attempted=0 succeeded=0 failed=0")
        return 2
    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    try:
        urls = load_urls(input_file)
    except Exception as exc:
        print(f"ENRICH_FAILED input {clean_error(exc)}", flush=True)
        print("ENRICH_SUMMARY attempted=0 succeeded=0 failed=1", flush=True)
        return 4
    if not urls:
        print("No websites found in the input file. Enrich step has nothing to do.")
        print("ENRICH_SUMMARY attempted=0 succeeded=0 failed=0", flush=True)
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)
    code = await run_crawl(urls, output_dir)
    print("Enrich done.", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
