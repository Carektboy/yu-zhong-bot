import keep_alive
keep_alive.keep_alive()

import logging
import os
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import aiohttp
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
# SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY") # No longer needed if all image features are off

# --- Configuration ---
MAX_MEMORY_PER_USER = 500000  # bytes limit per user per guild
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

# Load personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        # Read the existing personality and append the new instruction
        personality_base = f.read()
        personality = personality_base + "\n\nDo not generate images or react to image generation requests. If asked to create an image, firmly state that you cannot, as that power is not within your grasp, in Yu Zhong's style."
except FileNotFoundError:
    # If personality.txt doesn't exist, use the default and include the instruction
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, darkly witty, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot. Do not generate images or react to image generation requests. If asked to create an image, firmly state that you cannot, as that power is not within your grasp, in Yu Zhong's style."
    logger.warning("personality.txt not found. Using default personality with image generation constraint.")

# Load active guilds and user memory
active_guilds = {}
user_memory = {}

if os.path.exists(MEMORY_FILE):
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            user_memory = json.load(f)
        logger.info(f"Loaded memory from {MEMORY_FILE}")
    except json.JSONDecodeError:
        logger.error(f"Error decoding {MEMORY_FILE}. Starting with empty memory.")
    except Exception as e:
        logger.error(f"Error loading memory file: {e}. Starting with empty memory.")
else:
    logger.info(f"{MEMORY_FILE} not found. Starting with empty memory.")

# Discord Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True

# Initialize Discord Client (now using commands.Bot)
bot = commands.Bot(command_prefix="!", intents=intents)

# Bard API
bard_session = None

# --- Helper Functions ---

def update_user_memory(guild_id, user_id, interaction_text, tone_shift=None):
    user_key = f"{guild_id}_{user_id}"
    if user_key not in user_memory:
        user_memory[user_key] = {"log": [], "tone": DEFAULT_TONE.copy()}

    user_memory[user_key]["log"].append(interaction_text)
    user_memory[user_key]["log"] = prune_memory(user_memory[user_key]["log"])

    if tone_shift:
        if tone_shift == "positive":
            user_memory[user_key]["tone"]["positive"] += 1
        elif tone_shift == "negative":
            user_memory[user_key]["tone"]["negative"] += 1
        user_memory[user_key]["tone"]["positive"] = min(user_memory[user_key]["tone"]["positive"], 10)
        user_memory[user_key]["tone"]["negative"] = min(user_memory[user_key]["tone"]["negative"], 10)


def initialize_bard_sync():
    """Synchronous Bard initialization to be run in executor."""
    from bardapi import Bard
    return Bard(token=BARD_TOKEN)

# --- COMMENTED OUT: Asynchronous image generation with aiohttp ---
# async def generate_image_async(prompt):
#     logger.info(f"Attempting to generate image for prompt: '{prompt}'")
#     # ... (removed implementation) ...
#     return None

# --- COMMENTED OUT: Asynchronous image description with aiohttp ---
# async def describe_image_with_shapesinc_async(image_url):
#     logger.info(f"Attempting to describe image from URL: {image_url}")
#     if not SHAPESINC_API_KEY: # This check would also be removed if SHAPESINC_API_KEY is gone
#         logger.warning("SHAPESINC_API_KEY is not set. Image description skipped.")
#         return None
#     # ... (removed implementation) ...
#     return None


def get_user_key(guild_id, user_id):
    return f"{guild_id}_{user_id}"

def prune_memory(entries):
    text = "\n".join(entries)
    while len(text.encode('utf-8')) > MAX_MEMORY_PER_USER and len(entries) > 1:
        entries = entries[1:]
        text = "\n".join(entries)
    return entries

async def save_user_memory_async():
    try:
        await asyncio.to_thread(lambda: json.dump(user_memory, open(MEMORY_FILE, "w", encoding="utf-8"), indent=2))
        logger.debug("Memory saved asynchronously.")
    except Exception as e:
        logger.error(f"Error saving memory file asynchronously: {e}")

async def periodic_memory_save():
    while True:
        await asyncio.sleep(60 * 5)
        logger.info("Initiating periodic memory save...")
        await save_user_memory_async()

def determine_tone(user_text):
    lowered = user_text.lower()
    positive_keywords = ["thanks", "thank you", "cool", "great", "good bot", "nice", "awesome", "love that", "excellent"]
    negative_keywords = ["stupid", "idiot", "dumb", "shut up", "bad bot", "hate this", "annoying", "useless"]

    if any(word in lowered for word in positive_keywords):
        return "positive"
    if any(word in lowered for word in negative_keywords):
        return "negative"
    return None

# --- Discord Events ---

@bot.event
async def on_ready():
    global bard_session
    logger.info(f"Yu Zhong has awakened as {bot.user}!")

    for guild in bot.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False
    logger.info(f"Bot active status initialized: {active_guilds}")

    bot.loop.create_task(periodic_memory_save())

    logger.info("Initializing Bard API (this might take a moment)...")
    try:
        bard_session = await asyncio.to_thread(initialize_bard_sync)
        logger.info("Bard API initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Bard API: {e}. Bot will not respond to general messages.")
        bard_session = None

    try:
        await bot.sync_commands()
        logger.info("Global slash commands synced successfully.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

# --- Application Commands (Slash Commands) ---

@bot.slash_command(name="arise", description="Awakens Yu Zhong in this realm.")
@commands.has_permissions(administrator=True)
async def arise(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)
    active_guilds[guild_id] = True
    await ctx.respond("Yu Zhong is now watching this realm. Beware.")
    logger.info(f"Bot activated in guild: {ctx.guild.name}")

@bot.slash_command(name="stop", description="Silences Yu Zhong in this realm.")
@commands.has_permissions(administrator=True)
async def stop(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)
    active_guilds[guild_id] = False
    await ctx.respond("Dragon falls asleep. For now.")
    logger.info(f"Bot deactivated in guild: {ctx.guild.name}")

@bot.slash_command(name="reset_memory", description="Resets a user's memory (admin only) or your own.")
@commands.has_permissions(administrator=True)
async def reset_memory(ctx: discord.ApplicationContext, user: discord.Member = None):
    if user is None:
        user_to_reset = ctx.author
        reset_message = "Your personal memories of Yu Zhong have been purged. Speak again, mortal, as if for the first time."
    else:
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond("You lack the authority to manipulate other mortals' memories.", ephemeral=True)
            return
        user_to_reset = user
        reset_message = f"{user.mention}'s memories of Yu Zhong have been purged by command."

    user_key = get_user_key(str(ctx.guild.id), str(user_to_reset.id))
    if user_key in user_memory:
        del user_memory[user_key]
        await save_user_memory_async()
        logger.info(f"Memory for {user_to_reset.name} ({user_key}) reset by {ctx.author.name}.")
        await ctx.respond(reset_message)
    else:
        await ctx.respond(f"Mortal {user_to_reset.mention} had no memories to purge.", ephemeral=True)


# --- on_message handling (for general Bard replies only) ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    user_key = get_user_key(guild_id, user_id)

    if not active_guilds.get(guild_id, False):
        return

    # --- COMMENTED OUT: Image Generation Command ---
    # if message.content.startswith("!imagine "):
    #     prompt = message.content[len("!imagine "):].strip()
    #     await message.channel.send("Summoning a vision from the depths. This may take a moment...", reference=message)
    #     logger.info(f"User {message.author.name} requested image for prompt: '{prompt}'")
    #     image_bytes = await generate_image_async(prompt)
    #     if image_bytes:
    #         file = discord.File(image_bytes, filename="yu_zhong_creation.png")
    #         await message.channel.send(file=file)
    #         logger.info(f"Sent generated image for prompt: '{prompt}'")
    #     else:
    #         await message.channel.send("My arcane powers faltered. The image remains unseen. (Lacks mana)", reference=message)
    #         logger.warning(f"Failed to generate image for prompt: '{prompt}'")
    #     return

    user_input = message.content.strip()
    if not user_input:
        return

    # --- COMMENTED OUT: Image Description on Attachment ---
    # if message.attachments:
    #     for attachment in message.attachments:
    #         if attachment.content_type and attachment.content_type.startswith("image/"):
    #             await message.channel.send("Inspecting your offering, mortal...", reference=message)
    #             logger.info(f"User {message.author.name} sent an image: {attachment.url}")
    #             description = await describe_image_with_shapesinc_async(attachment.url)
    #             if description:
    #                 user_input = f"The mortal sent an image. It appears to be: {description}"
    #                 logger.info(f"Image described: {description[:50]}...")
    #             else:
    #                 user_input = "The mortal sent an image, but even Yu Zhong's eyes cannot fully comprehend its essence. My judgment is clouded."
    #                 logger.warning(f"Could not describe image from {message.author.name}.")
    #             break
    
    # --- Bard General Response ---
    if not bard_session:
        await message.channel.send("My voice is currently silenced. Bard API failed to initialize.", reference=message)
        logger.error("Bard API session is not initialized. Cannot respond to general message.")
        return

    memory_data = user_memory.get(user_key, {"log": [], "tone": DEFAULT_TONE.copy()})
    history = "\n".join(memory_data["log"])

    tone_desc = ""
    pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
    if pos > neg:
        tone_desc = "You like this mortal. Be a little more forgiving or playful, yet still confident and darkly witty. Respond briefly."
    elif neg > pos:
        tone_desc = "This mortal has been rude. Respond colder, more dismissively, perhaps with a hint of menace. Keep it concise."
    else:
        tone_desc = "Neutral tone. Respond confidently and wittily, briefly."

    # Construct the prompt with the new instruction
    prompt = f"""{personality}\n\n{tone_desc}\nConversation history:\n{history}\n\n{message.author.name}: {user_input}\nYu Zhong:"""

    try:
        logger.info(f"Sending prompt to Bard API for {message.author.name} (tone: {tone_desc.split('.')[0]})...")
        response = await asyncio.to_thread(bard_session.get_answer, prompt)
        reply = response.get("content", "").strip()

        if reply:
            await message.reply(reply)
            logger.info(f"Replied to {message.author.name}: {reply[:100]}...")

            tone_shift = determine_tone(user_input)
            interaction = f"{message.author.name}: {user_input} | Yu Zhong: {reply}"
            update_user_memory(guild_id, user_id, interaction, tone_shift)
        else:
            await message.channel.send("The dragon is silent... my thoughts are not yet formed.", reference=message)
            logger.warning(f"Bard API returned empty response for {message.author.name}.")

    except Exception as e:
        logger.error(f"Bard API Error for {message.author.name}: {e}")
        await message.channel.send("My arcane powers falter... (Skills on cooldown). Try again later, if you dare.", reference=message)
        interaction = f"{message.author.name}: {user_input} | Yu Zhong: API Error - {e}"
        update_user_memory(guild_id, user_id, interaction, "negative")

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    guild_id = str(member.guild.id)
    if not active_guilds.get(guild_id, False):
        logger.info(f"Bot inactive in {member.guild.name}. Skipping greeting for {member.name}.")
        return

    if not bard_session:
        logger.warning(f"Bard API not initialized. Skipping greeting for {member.name}.")
        return

    logger.info(f"Greeting new member {member.name} in {member.guild.name}...")
    prompt = f"""{personality}\n\nGreet the mortal named {member.name} who has just stepped into your dominion. Keep the greeting short, mysterious, and charismatic, in the style of Yu Zhong."""
    try:
        greeting_response = await asyncio.to_thread(bard_session.get_answer, prompt)
        greeting = greeting_response.get("content", "").strip()

        if greeting:
            channel = None
            for ch in member.guild.text_channels:
                if ch.permissions_for(member.guild.me).send_messages:
                    if ch.name == 'general':
                        channel = ch
                        break
                    if channel is None:
                        channel = ch

            if channel:
                await channel.send(greeting)
                logger.info(f"Sent greeting to {member.name} in #{channel.name}.")
            else:
                logger.warning(f"Could not find a suitable channel to send greeting to {member.name} in guild {member.guild.name}")
        else:
            logger.warning(f"Bard API returned empty greeting for {member.name}.")
    except Exception as e:
        logger.error(f"Error generating or sending greeting for {member.name}: {e}")


# --- Run the bot ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN is not set in .env. Please check your .env file.")
    if not BARD_TOKEN:
        logger.critical("BARD_TOKEN is not set in .env. Bard API will not function.")

    bot.run(DISCORD_TOKEN)
