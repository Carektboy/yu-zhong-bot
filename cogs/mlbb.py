import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import time
from bs4 import BeautifulSoup
import cloudscraper  # <-- 1. This fulfills the first instruction to import cloudscraper.

logger = logging.getLogger('YuZhongBot')

patch_cache = {"data": None, "timestamp": 0}

class MLBBCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.personality = bot.personality
        self.safe_send_response = bot.safe_send_response

        # Lazy init placeholders
        self.shapes_client = None
        self.SHAPESINC_SHAPE_MODEL = None
        self.shapes_initialized = False

        # Cloudscraper session
        # This part fulfills the "scraper = cloudscraper.create_scraper()" instruction.
        # It's done here for efficiency, so it's only created once.
        self.scraper = cloudscraper.create_scraper()

    async def lazy_init_shapes_client(self):
        if self.shapes_initialized:
            return
        self.shapes_initialized = True

        api_key = getattr(self.bot, "SHAPESINC_API_KEY", None)
        model_username = getattr(self.bot, "SHAPESINC_MODEL_USERNAME", None)

        if not api_key or not model_username:
            logger.warning("Shapes.inc API key or model username missing; AI features disabled.")
            return

        try:
            from openai import OpenAI

            self.shapes_client = OpenAI(
                base_url="https://api.shapes.inc/v1/",
                api_key=api_key,
                timeout=60.0
            )

            models_response = await asyncio.to_thread(self.shapes_client.models.list)
            available_models = [model.id for model in models_response.data]
            logger.info(f"Shapes.inc available models: {available_models}")

            matched_model = next(
                (m for m in available_models if model_username in m or m == model_username),
                None
            )

            if matched_model:
                self.SHAPESINC_SHAPE_MODEL = matched_model
                logger.info(f"Shapes.inc model resolved: {matched_model}")
            else:
                logger.critical(f"Shapes.inc model '{model_username}' not found. AI features disabled.")
                self.shapes_client = None
        except Exception as e:
            logger.critical(f"Failed to initialize Shapes.inc client or resolve model: {e}")
            self.shapes_client = None

    async def get_latest_patch_notes(self):
        global patch_cache
        now = time.time()
        if patch_cache["data"] and (now - patch_cache["timestamp"]) < 3600:
            return patch_cache["data"]

        await self.lazy_init_shapes_client()

        urls_to_try = [
            "https://m.mobilelegends.com/en/news",
            "https://www.mobilelegends.com/en/news",
            "https://www.google.com/search?q=mobile+legends+patch+notes&hl=en",
        ]
        news_selectors = [
            "div.news-content",
            "article.news-item",
            "div.news-detail-content",
            "div.article-content",
            "div.post-content",
            "p",
            "h2", "h3"
        ]
        patch_keywords = ["patch", "update", "balance", "hero", "nerf", "buff", "adjustment", "changelog"]

        final_summary_found = ""

        for url in urls_to_try:
            try:
                # 2. This line fulfills the second instruction, replacing the old
                # request with the cloudscraper one.
                response = await asyncio.to_thread(self.scraper.get, url, timeout=10)
                
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                for selector in news_selectors:
                    elements = soup.select(selector)
                    if elements:
                        texts = []
                        for elem in elements:
                            text = elem.get_text(strip=True)
                            if text and len(text) > 50 and any(keyword in text.lower() for keyword in patch_keywords):
                                texts.append(text[:500])
                                if len(texts) >= 3:
                                    break
                        if texts:
                            final_summary_found = f"Latest from {url}:\n" + "\n\n".join(texts)
                            break

                if final_summary_found:
                    break

                if not final_summary_found:
                    all_text = soup.get_text()
                    sentences = all_text.split('.')
                    relevant_sentences = []
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if any(keyword in sentence.lower() for keyword in patch_keywords) and len(sentence) > 30:
                            relevant_sentences.append(sentence[:200])
                            if len(relevant_sentences) >= 5:
                                break
                    if relevant_sentences:
                        final_summary_found = "Recent patch information:\n" + "\n• ".join(relevant_sentences)
                        break

            except Exception as e:
                logger.warning(f"Failed to fetch or parse from {url}: {e}")
                continue

        # If we have summary text and AI client ready, summarize with AI
        if final_summary_found and self.shapes_client and self.SHAPESINC_SHAPE_MODEL:
            try:
                summarization_prompt = (
                    f"Summarize the following Mobile Legends: Bang Bang patch notes concisely and in a tone suitable for Yu Zhong "
                    f"(authoritative, a bit dismissive, focusing on key changes like buffs/nerfs). Keep it under 300 words. "
                    f"Focus on important hero or item changes. If there are no clear changes, state that.\n\nRaw text:\n"
                    f"{final_summary_found[:8000]}"
                )
                summarize_messages = [
                    {"role": "system", "content": self.personality},
                    {"role": "user", "content": summarization_prompt}
                ]
                summarized_completion = await asyncio.to_thread(
                    self.shapes_client.chat.completions.create,
                    model=self.SHAPESINC_SHAPE_MODEL,
                    messages=summarize_messages,
                    max_tokens=250,
                    temperature=0.4
                )
                if summarized_completion and summarized_completion.choices and summarized_completion.choices[0].message:
                    summary = summarized_completion.choices[0].message.content.strip()
                    patch_cache["data"] = summary
                    patch_cache["timestamp"] = now
                    return summary
            except Exception as e:
                logger.warning(f"AI summarization failed: {e}. Using scraped text fallback.")

        if not final_summary_found:
            final_summary_found = "Unable to fetch current patch notes. The Land of Dawn's secrets remain hidden for now."

        patch_cache["data"] = final_summary_found
        patch_cache["timestamp"] = now
        return patch_cache["data"]

    @app_commands.command(name="patch", description="Shows the latest MLBB patch summary.")
    async def patch(self, interaction: discord.Interaction):
        await interaction.response.defer()
        summary = await self.get_latest_patch_notes()
        if len(summary) > 1900:
            summary = summary[:1897] + "..."
        await self.safe_send_response(interaction, f"\U0001F4DC **Latest Patch Notes Summary:**\n```{summary}```")

async def setup(bot):
    await bot.add_cog(MLBBCog(bot))
