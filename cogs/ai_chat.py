import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import logging
import asyncio

logger = logging.getLogger('YuZhongBot')

class AIChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.personality = bot.personality
        self.shapes_client = bot.shapes_client
        self.SHAPESINC_SHAPE_MODEL = bot.SHAPESINC_SHAPE_MODEL
        self.safe_send_response = bot.safe_send_response
        self.DEFAULT_TONE = bot.DEFAULT_TONE
        self.MAX_MEMORY_PER_USER_TOKENS = bot.MAX_MEMORY_PER_USER_TOKENS
        self.MEMORY_DIR = bot.MEMORY_DIR

    def get_user_memory_filepath(self, guild_id, user_id):
        return os.path.join(self.MEMORY_DIR, f"user_{guild_id}_{user_id}.json")

    def load_user_memory(self, guild_id, user_id):
        filepath = self.get_user_memory_filepath(guild_id, user_id)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    memory = json.load(f)
                if "tone" not in memory:
                    memory["tone"] = self.DEFAULT_TONE.copy()
                else:
                    for k, v in self.DEFAULT_TONE.items():
                        if k not in memory["tone"]:
                            memory["tone"][k] = v
                return memory
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding memory for user {user_id} in guild {guild_id}: {e}")
                return {"log": [], "tone": self.DEFAULT_TONE.copy()}
            except Exception as e:
                logger.error(f"Unexpected error loading memory for user {user_id} in guild {guild_id}: {e}")
                return {"log": [], "tone": self.DEFAULT_TONE.copy()}
        return {"log": [], "tone": self.DEFAULT_TONE.copy()}

    def save_user_memory(self, guild_id, user_id, memory_data):
        filepath = self.get_user_memory_filepath(guild_id, user_id)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, indent=4)
        except IOError as e:
            logger.error(f"Failed to save user memory for {user_id} in guild {guild_id}: {e}")

    def update_user_memory(self, guild_id, user_id, user_input, reply, tone_change):
        memory = self.load_user_memory(guild_id, user_id)

        memory["log"].append({"role": "user", "content": user_input})
        memory["log"].append({"role": "assistant", "content": reply})
        memory["tone"][tone_change] += 1

        current_memory_tokens = sum(len(m["content"].split()) for m in memory["log"] if isinstance(m["content"], str))
        while current_memory_tokens > self.MAX_MEMORY_PER_USER_TOKENS and len(memory["log"]) > 2:
            memory["log"] = memory["log"][2:]
            current_memory_tokens = sum(len(m["content"].split()) for m in memory["log"] if isinstance(m["content"], str))

        self.save_user_memory(guild_id, user_id, memory)

    def determine_tone(self, text):
        text_lower = text.lower()
        if any(word in text_lower for word in ["thank", "great", "awesome", "good", "love", "thanks", "nice", "cool", "helpful"]):
            return "positive"
        elif any(word in text_lower for word in ["hate", "bad", "stupid", "annoying", "idiot", "sucks", "dislike", "useless"]):
            return "negative"
        return "neutral"

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user or message.author.bot:
            return

        if not message.content:
            return

        if not message.guild:
            return  # Optional: ignore DMs

        channel_id_str = str(message.channel.id)
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        user_display_name = message.author.display_name

        bot_mentioned = self.bot.user.mentioned_in(message)

        if not self.bot.active_channels.get(channel_id_str) and not bot_mentioned:
            return

        async with message.channel.typing():
            if not self.shapes_client:
                logger.warning(f"Shapes.inc client not available for channel {channel_id_str}.")
                await message.reply("My arcane powers are dormant... (AI service unavailable.)")
                return

            memory_data = self.load_user_memory(guild_id, user_id)

            messages = [{"role": "system", "content": self.personality}]
            pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
            tone_desc = "Neutral. This person is neutral, speak normal tone, not rude nor friendly."
            if pos > neg:
                tone_desc = "You like this person. Be good to them, they are your friend."
            elif neg > pos:
                tone_desc = "This person has been rude. Be cold, dismissive, brief, but forgiving."
            messages[0]["content"] += f"\n{tone_desc}"

            messages.extend(memory_data["log"])
            user_input = message.content
            messages.append({"role": "user", "content": user_input})

            reply_text = "My power wanes... I cannot respond at this moment."
            tone_change = "neutral"

            try:
                completion = await asyncio.to_thread(
                    self.shapes_client.chat.completions.create,
                    model=self.SHAPESINC_SHAPE_MODEL,
                    messages=messages,
                    max_tokens=200,
                    temperature=0.8,
                )
                if completion and completion.choices and completion.choices[0].message:
                    reply_text = completion.choices[0].message.content.strip()
                    tone_change = self.determine_tone(user_input)
            except Exception as e:
                logger.error(f"Error calling Shapes.inc API: {e}")
                if "rate limit" in str(e).lower():
                    reply_text = "Even a dragon's power is not infinite. My voice is temporarily restricted."
                else:
                    reply_text = "A temporal distortion in the flow of power prevents my response."

            if len(reply_text) > 1900:
                reply_text = reply_text[:1897] + "..."

            await message.reply(reply_text)
            self.update_user_memory(guild_id, user_id, user_input, reply_text, tone_change)

    @app_commands.command(
        name="search",
        description="Search for information with Yu Zhong's knowledge."
    )
    async def search(self, interaction: discord.Interaction, query: str):
        channel_id_str = str(interaction.channel_id)

        if interaction.guild and not self.bot.active_channels.get(channel_id_str):
            await self.safe_send_response(interaction, "My power is not active in this channel. Use `/arise` to awaken me.", ephemeral=True)
            return

        await interaction.response.defer()

        if not self.shapes_client:
            await self.safe_send_response(interaction, "My arcane powers are dormant... (AI service unavailable.)")
            return

        try:
            guild_id = str(interaction.guild_id) if interaction.guild else "DM"
            user_id = str(interaction.user.id)
            memory_data = self.load_user_memory(guild_id, user_id)

            mlbb_cog = self.bot.get_cog("MLBBCog")
            patch_notes = ""
            if mlbb_cog:
                patch_notes = await mlbb_cog.get_latest_patch_notes()
            else:
                logger.warning("MLBBCog not loaded, cannot get patch notes for search.")

            user_display_name = interaction.user.display_name

            search_personality = f"{self.personality}\n\nYou are being asked to search for information about: '{query}'. Provide helpful, accurate information while maintaining your Yu Zhong personality. Be informative but keep your characteristic wit and confidence."
            pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
            tone_desc = "Neutral. This person is neutral, speak normal tone, not rude nor friendly."
            if pos > neg:
                tone_desc = "You like this person. Be good to them, they are your friend."
            elif neg > pos:
                tone_desc = "This person has been rude. Be cold, dismissive, brief, but forgiving."
            search_personality += f"\n{tone_desc}"

            messages = [{"role": "system", "content": search_personality}]
            messages.extend(memory_data["log"])

            full_query_content = f"Search for information about: {query}\n\n[User Info: Address the user as '{user_display_name}' in your response, not by any model or API names]"
            if patch_notes:
                full_query_content += f"\n\n[Context: Latest MLBB Patch Notes]\n{patch_notes}"

            messages.append({"role": "user", "content": full_query_content})

            reply_text = "My power wanes... I cannot fulfill this search at the moment."
            tone_change = "neutral"

            try:
                completion = await asyncio.to_thread(
                    self.shapes_client.chat.completions.create,
                    model=self.SHAPESINC_SHAPE_MODEL,
                    messages=messages,
                    max_tokens=400,
                    temperature=0.7,
                )
                if completion and completion.choices and completion.choices[0].message:
                    reply_text = completion.choices[0].message.content.strip()
                    tone_change = self.determine_tone(query)
            except Exception as e:
                logger.error(f"Error calling Shapes.inc API for search: {e}")
                if "rate limit" in str(e).lower():
                    reply_text = "Even a dragon's power is not infinite. My knowledge is temporarily restricted."
                else:
                    reply_text = "A temporal distortion in the flow of power prevents my search."

            if len(reply_text) > 1900:
                reply_text = reply_text[:1897] + "..."

            await self.safe_send_response(interaction, reply_text)
            self.update_user_memory(guild_id, user_id, query, reply_text, tone_change)

        except Exception as e:
            logger.error(f"Unexpected error in search command: {e}")
            await self.safe_send_response(interaction, "A distortion disrupted my response. Please try again later.")


async def setup(bot):
    await bot.add_cog(AIChatCog(bot))
