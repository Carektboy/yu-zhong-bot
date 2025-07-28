import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import logging
import asyncio
from openai import OpenAI

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
            except Exception as e:
                logger.error(f"Unexpected error loading memory for user {user_id} in guild {guild_id}: {e}")

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

        # IMPORTANT: When updating memory, include the display name for clarity
        # This helps the AI understand who said what in past interactions
        # user_input already contains the display name if on_message or search command adds it.
        # So, we just use the user_input passed to this function.
        memory["log"].append({"role": "user", "content": user_input})
        memory["log"].append({"role": "assistant", "content": reply})
        memory["tone"][tone_change] += 1

        current_memory_tokens = sum(
            len(m["content"].split()) for m in memory["log"] if isinstance(m["content"], str)
        )

        while current_memory_tokens > self.MAX_MEMORY_PER_USER_TOKENS and len(memory["log"]) > 2:
            memory["log"] = memory["log"][2:]
            current_memory_tokens = sum(
                len(m["content"].split()) for m in memory["log"] if isinstance(m["content"], str)
            )

        self.save_user_memory(guild_id, user_id, memory)

    def determine_tone(self, text):
        text_lower = text.lower()
        if any(word in text_lower for word in [
            "thank", "great", "awesome", "good", "love", "thanks", "nice", "cool", "helpful"
        ]):
            return "positive"
        elif any(word in text_lower for word in [
            "hate", "bad", "stupid", "annoying", "idiot", "sucks", "dislike", "useless"
        ]):
            return "negative"
        return "neutral"

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.author == self.bot.user:
            return

        channel_id_str = str(message.channel.id)
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        user_display_name = message.author.display_name
        bot_mentioned = self.bot.user.mentioned_in(message)

        # Only proceed if bot is active in channel OR bot is mentioned
        if not self.bot.active_channels.get(channel_id_str) and not bot_mentioned:
            return

        # --- REVISED LOGIC FOR HANDLING IMAGES ---
        # If there are ANY attachments, send the predefined refusal and stop.
        if message.attachments:
            await message.channel.typing() # Show typing indicator
            # Yu Zhong's refusal for images, as per personality.txt
            await message.reply("Hmph! Such trivial images hold no sway over my ancient power. My grasp extends beyond mere visual conjurations.")
            logger.info(f"Replied to message with attachment from {user_display_name} in {message.channel.name}")
            return # Stop further processing for messages with attachments
        # --- END REVISED LOGIC ---

        # If there's no content (after checking for attachments), return (e.g., sticker, but no attachment).
        if not message.content:
            return

        async with message.channel.typing():
            if not self.shapes_client:
                logger.warning(f"Shapes.inc client not available for channel {channel_id_str}.")
                await message.reply("My arcane powers are dormant... (AI service unavailable.)")
                return

            memory_data = self.load_user_memory(guild_id, user_id)

            messages = [{"role": "system", "content": self.personality}]
            pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]

            if pos > neg:
                messages[0]["content"] += "\nYou like this person. Be good to them, they are your friend."
            elif neg > pos:
                messages[0]["content"] += "\nThis person has been rude. Be cold, dismissive, brief, but forgiving."
            else:
                messages[0]["content"] += "\nNeutral. This person is neutral, speak normal tone, not rude nor friendly."

            messages.extend(memory_data["log"])

            # CRITICAL CHANGE: Include user_display_name in the content for API calls
            user_input_for_api = f"{user_display_name}: {message.content}"
            messages.append({"role": "user", "content": user_input_for_api})

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
                    tone_change = self.determine_tone(message.content) # Use original message.content for tone detection
            except Exception as e:
                logger.error(f"Error calling Shapes.inc API: {e}")
                if "rate limit" in str(e).lower():
                    reply_text = "Even a dragon's power is not infinite. My voice is temporarily restricted."
                else:
                    reply_text = "A temporal distortion in the flow of power prevents my response."

            if len(reply_text) > 1900:
                reply_text = reply_text[:1897] + "..."

            await message.reply(reply_text)
            # IMPORTANT: Store the user_input_for_api in memory so the AI sees it structured correctly in future turns
            self.update_user_memory(guild_id, user_id, user_input_for_api, reply_text, tone_change)

    @app_commands.command(
        name="search",
        description="Search for information with Yu Zhong's knowledge."
    )
    async def search(self, interaction: discord.Interaction, query: str):
        channel_id_str = str(interaction.channel_id)

        if interaction.guild and not self.bot.active_channels.get(channel_id_str):
            await self.safe_send_response(interaction,
                "My power is not active in this channel. Use `/arise` to awaken me.", ephemeral=True)
            return

        await interaction.response.defer()

        if not self.shapes_client:
            await self.safe_send_response(interaction,
                "My arcane powers are dormant... (AI service unavailable.)")
            return

        try:
            guild_id = str(interaction.guild_id) if interaction.guild else "DM"
            user_id = str(interaction.user.id)
            memory_data = self.load_user_memory(guild_id, user_id)

            mlbb_cog = self.bot.get_cog("MLBBCog")
            patch_notes = await mlbb_cog.get_latest_patch_notes() if mlbb_cog else ""
            if not mlbb_cog:
                logger.warning("MLBBCog not loaded, cannot get patch notes for search.")

            user_display_name = interaction.user.display_name

            # Add explicit instruction about usernames in the system prompt for search as well
            search_personality = f"{self.personality}\n\nYou are being asked to search for information about: '{query}'. Provide helpful, accurate information while maintaining your Yu Zhong personality. Do not confuse other users with '{user_display_name}'."

            pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
            if pos > neg:
                search_personality += "\nYou like this person. Be good to them, they are your friend."
            elif neg > pos:
                search_personality += "\nThis person has been rude. Be cold, dismissive, brief, but forgiving."
            else:
                search_personality += "\nNeutral. This person is neutral, speak normal tone, not rude nor friendly."

            messages = [{"role": "system", "content": search_personality}]
            messages.extend(memory_data["log"])

            # CRITICAL CHANGE: Include user_display_name in the content for API calls in search command
            full_query_content = (
                f"{user_display_name}: Search for information about: {query}\n\n"
                f"[User Info: Address the user as '{user_display_name}' in your response]"
            )
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
            # IMPORTANT: Store the full_query_content in memory so the AI sees it structured correctly in future turns
            self.update_user_memory(guild_id, user_id, full_query_content, reply_text, tone_change)

        except Exception as e:
            logger.error(f"Unexpected error in search command: {e}")
            await self.safe_send_response(interaction, "A ripple in the void has interrupted my search.")


async def setup(bot):
    await bot.add_cog(AIChatCog(bot))
