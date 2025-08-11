import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import time
from bs4 import BeautifulSoup
import cloudscraper

l = logging.getLogger('YuZhongBot')

pc = {"data": None, "timestamp": 0}

class MLBBCog(commands.Cog):
    def __init__(self, b):
        self.b = b
        self.p = b.personality
        self.r = b.safe_send_response

        # Lazy init placeholders
        self.sc = None
        self.sm = None
        self.si = False

        # Cloudscraper session
        self.cs = cloudscraper.create_scraper()

    async def lazy_init_shapes_client(self):
        if self.si:
            return
        self.si = True

        a = getattr(self.b, "SHAPESINC_API_KEY", None)
        u = getattr(self.b, "SHAPESINC_MODEL_USERNAME", None)

        if not a or not u:
            l.warning("Shapes.inc API key or model username missing; AI features disabled.")
            return

        try:
            from openai import OpenAI

            self.sc = OpenAI(
                base_url="https://api.shapes.inc/v1/",
                api_key=a,
                timeout=60.0
            )

            res = await asyncio.to_thread(self.sc.models.list)
            am = [m.id for m in res.data]
            l.info(f"Shapes.inc available models: {am}")

            mm = next(
                (m for m in am if u in m or m == u),
                None
            )

            if mm:
                self.sm = mm
                l.info(f"Shapes.inc model resolved: {mm}")
            else:
                l.critical(f"Shapes.inc model '{u}' not found. AI features disabled.")
                self.sc = None
        except Exception as e:
            l.critical(f"Failed to initialize Shapes.inc client or resolve model: {e}")
            self.sc = None

    async def get_latest_patch_notes(self):
        global pc
        n = time.time()
        if pc["data"] and (n - pc["timestamp"]) < 3600:
            return pc["data"]

        await self.lazy_init_shapes_client()

        urls = [
            "https://m.mobilelegends.com/en/news",
            "https://www.mobilelegends.com/en/news",
            "https://www.google.com/search?q=mobile+legends+patch+notes&hl=en",
        ]
        sel = [
            "div.news-content",
            "article.news-item",
            "div.news-detail-content",
            "div.article-content",
            "div.post-content",
            "p",
            "h2", "h3"
        ]
        k = ["patch", "update", "balance", "hero", "nerf", "buff", "adjustment", "changelog"]

        s = ""

        for u in urls:
            try:
                res = await asyncio.to_thread(self.cs.get, u, timeout=10)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, 'html.parser')

                for p in sel:
                    e = soup.select(p)
                    if e:
                        t = []
                        for elem in e:
                            text = elem.get_text(strip=True)
                            if text and len(text) > 50 and any(kwd in text.lower() for kwd in k):
                                t.append(text[:500])
                                if len(t) >= 3:
                                    break
                        if t:
                            s = f"Latest from {u}:\n" + "\n\n".join(t)
                            break

                if s:
                    break

                if not s:
                    at = soup.get_text()
                    sen = at.split('.')
                    rel = []
                    for sentence in sen:
                        sentence = sentence.strip()
                        if any(kwd in sentence.lower() for kwd in k) and len(sentence) > 30:
                            rel.append(sentence[:200])
                            if len(rel) >= 5:
                                break
                    if rel:
                        s = "Recent patch information:\n" + "\n• ".join(rel)
                        break

            except Exception as e:
                l.warning(f"Failed to fetch or parse from {u}: {e}")
                continue

        # If we have summary text and AI client ready, summarize with AI
        if s and self.sc and self.sm:
            try:
                prompt = (
                    f"Summarize the following Mobile Legends: Bang Bang patch notes concisely and in a tone suitable for Yu Zhong "
                    f"(authoritative, a bit dismissive, focusing on key changes like buffs/nerfs). Keep it under 300 words. "
                    f"Focus on important hero or item changes. If there are no clear changes, state that.\n\nRaw text:\n"
                    f"{s[:8000]}"
                )
                m = [
                    {"role": "system", "content": self.p},
                    {"role": "user", "content": prompt}
                ]
                comp = await asyncio.to_thread(
                    self.sc.chat.completions.create,
                    model=self.sm,
                    messages=m,
                    max_tokens=250,
                    temperature=0.4
                )
                if comp and comp.choices and comp.choices[0].message:
                    summary = comp.choices[0].message.content.strip()
                    pc["data"] = summary
                    pc["timestamp"] = n
                    return summary
            except Exception as e:
                l.warning(f"AI summarization failed: {e}. Using scraped text fallback.")

        if not s:
            s = "Unable to fetch current patch notes. The Land of Dawn's secrets remain hidden for now."

        pc["data"] = s
        pc["timestamp"] = n
        return pc["data"]

    @app_commands.command(name="patch", description="Shows the latest MLBB patch summary.")
    async def patch(self, i: discord.Interaction):
        await i.response.defer()
        s = await self.get_latest_patch_notes()
        if len(s) > 1900:
            s = s[:1897] + "..."
        await self.r(i, f"\U0001F4DC **Latest Patch Notes Summary:**\n```{s}```")

async def setup(b):
    await b.add_cog(MLBBCog(b))
