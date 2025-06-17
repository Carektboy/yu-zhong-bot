import aiohttp
import asyncio
import json
from bs4 import BeautifulSoup

PATCH_NOTES_URL = "https://mobile-legends.fandom.com/wiki/Patch_Notes"
OUTPUT_FILE = "patch_notes.json"

async def fetch_page(session, url):
    async with session.get(url) as resp:
        return await resp.text()

async def get_latest_patch_url():
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, PATCH_NOTES_URL)
        soup = BeautifulSoup(html, "html.parser")

        # Find the first patch version link in the list
        patch_list = soup.select("div#mw-content-text ul > li > a")
        for link in patch_list:
            href = link.get("href")
            title = link.get("title", "").lower()
            if "patch" in title:
                return "https://mobile-legends.fandom.com" + href
        return None

def extract_patch_info(html):
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("div.mw-parser-output")
    version_header = soup.select_one("h1.page-header__title")
    version = version_header.get_text(strip=True) if version_header else "Unknown"

    # Naive extraction of major sections (can be improved with full logic)
    summary = ""
    new_heroes, buffs, nerfs = [], [], []

    if content:
        for tag in content.find_all(["h2", "h3", "ul", "p"]):
            text = tag.get_text(separator="\n").lower()
            if "new hero" in text:
                ul = tag.find_next("ul")
                if ul:
                    new_heroes = [li.get_text(strip=True) for li in ul.find_all("li")]
            elif "buff" in text:
                ul = tag.find_next("ul")
                if ul:
                    buffs = [li.get_text(strip=True) for li in ul.find_all("li")]
            elif "nerf" in text:
                ul = tag.find_next("ul")
                if ul:
                    nerfs = [li.get_text(strip=True) for li in ul.find_all("li")]
            elif tag.name == "p" and not summary:
                summary = tag.get_text(strip=True)

    return {
        "version": version,
        "summary": summary,
        "new_heroes": new_heroes,
        "buffs": buffs,
        "nerfs": nerfs,
        "notes_url": PATCH_NOTES_URL
    }

async def main():
    async with aiohttp.ClientSession() as session:
        latest_url = await get_latest_patch_url()
        if not latest_url:
            print("Failed to find latest patch URL.")
            return

        print(f"Fetching latest patch from: {latest_url}")
        html = await fetch_page(session, latest_url)
        patch_data = extract_patch_info(html)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(patch_data, f, indent=4, ensure_ascii=False)

        print(f"✅ Patch notes saved to {OUTPUT_FILE} - Version: {patch_data['version']}")

if __name__ == "__main__":
    asyncio.run(main())
