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


async def run_crawl(urls, output_dir):
    try:
        from crawl4ai import AsyncWebCrawler
    except Exception as exc:
        for url in urls:
            print(f"ENRICH_FAILED {url} crawl4ai could not be imported: {clean_error(exc)}", flush=True)
        print(f"ENRICH_SUMMARY attempted={len(urls)} succeeded=0 failed={len(urls)}", flush=True)
        return 4

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
