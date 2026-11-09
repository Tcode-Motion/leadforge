# Reads websites.csv and saves each website as a clean text (markdown) file.
# Use the text to understand a lead before writing your pitch to them.

import asyncio
import csv
import re
from pathlib import Path

from crawl4ai import AsyncWebCrawler

BASE = Path(__file__).parent
INPUT_FILE = BASE / "websites.csv"
OUTPUT_DIR = BASE / "output"


def load_urls():
    # Read the CSV. Use the "website" column if it exists, else the first column.
    urls = []
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "website" in row and row["website"]:
                url = row["website"].strip()
            else:
                url = list(row.values())[0].strip()
            if not url:
                continue
            if not url.startswith("http"):
                url = "https://" + url
            urls.append(url)
    return urls


def file_name_for(url, index):
    # Turn a URL into a safe file name, like 01-example.com.md
    host = re.sub(r"^https?://", "", url).split("/")[0]
    host = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
    return f"{index:02d}-{host}.md"


async def main():
    urls = load_urls()
    if not urls:
        print("No websites found in websites.csv. Add some rows first.")
        return
    OUTPUT_DIR.mkdir(exist_ok=True)
    async with AsyncWebCrawler() as crawler:
        for i, url in enumerate(urls, start=1):
            print(f"Reading {url} ...")
            result = await crawler.arun(url=url)
            if not result.success:
                print(f"  Could not read this one, skipping. {result.error_message}")
                continue
            markdown = result.markdown
            # Newer versions wrap the text, so take the raw text if present.
            text = getattr(markdown, "raw_markdown", None) or str(markdown)
            out_file = OUTPUT_DIR / file_name_for(url, i)
            out_file.write_text(text, encoding="utf-8")
            print(f"  Saved {out_file.name}")
    print("Done. Read the files in the output folder.")


if __name__ == "__main__":
    asyncio.run(main())
