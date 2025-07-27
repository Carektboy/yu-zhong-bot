import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
import asyncio
import time
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

logger = logging.getLogger('YuZhongBot')

patch_cache = {"data": None, "timestamp": 0}

class MLBBCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.personality = bot.personality
        self.shapes_client = bot.shapes_client
        self.SHAPESINC_SHAPE_MODEL = bot.SHAPESINC_SHAPE_MODEL
        self.safe_send_response = bot.safe_send_response

    async def get_latest_patch_notes(self):
        global patch_cache
        now = time.time()
        if patch_cache["data"] and (now - patch_cache["timestamp"]) < 3600:
            return patch_cache["data"]

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
                response = await asyncio.to_thread(requests.get, url, timeout=10)
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

            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch from {url}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error parsing {url}: {e}")
                continue

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
                logger.warning(f"AI summarization of patch notes failed: {e}. Falling back to scraped text.")

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
