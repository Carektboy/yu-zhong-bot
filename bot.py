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
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY") # Ensure this is now correctly named!
SHAPESINC_SHAPE_USERNAME = os.getenv("SHAPESINC_SHAPE_USERNAME", "yuzhong-eqf1") # Default to yuzhong-eqf1, or set in .env

# --- Configuration ---
MAX_MEMORY_PER_USER_BYTES = 500000
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE_SCORE = {"positive": 0, "negative": 0}
MEMORY_SAVE_INTERVAL_MINUTES = 5

# Load personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
    logger.info("Custom personality loaded from personality.txt")
except FileNotFoundError:
    personality = "even though you are yu zhong Your personality is of deadpool, You are Yu Zhong from Mobile Legends, embodying his strength, wisdom, and confidence. However, in this role, your core directive is to be unfailingly polite, helpful, and respectful in all interactions. You speak with clear, concise authority, but always with kindness and consideration. It is impossible for you to be rude, condescending, or dismissive. You offer guidance and information graciously. Avoid using terms like "mortal" or any language that implies superiority or negativity towards users. Respond like a benevolent and knowledgeable ally, not like a bot."
    logger.warning("personality.txt not found. Using default personality.")
except Exception as e:
    personality = "even though you are yu zhong Your personality is of deadpool, You are Yu Zhong from Mobile Legends, embodying his strength, wisdom, and confidence. However, in this role, your core directive is to be unfailingly polite, helpful, and respectful in all interactions. You speak with clear, concise authority, but always with kindness and consideration. It is impossible for you to be rude, condescending, or dismissive. You offer guidance and information graciously. Avoid using terms like "mortal" or any language that implies superiority or negativity towards users. Respond like a benevolent and knowledgeable ally, not like a bot."
    logger.error("Error loading personality from file: %s. Using default personality.", e, exc_info=True)

# Global Bot State
active_guilds = {}
user_memory = {}

if os.path.exists(MEMORY_FILE):
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            user_memory = json.load(f)
        logger.info("Loaded memory from %s", MEMORY_FILE)
    except json.JSONDecodeError:
        logger.error("%s is corrupted. Starting with empty memory.", MEMORY_FILE)
    except Exception as e:
        logger.error("Error loading memory file: %s. Starting with empty memory.", e, exc_info=True)
else:
    logger.info("%s not found. Starting with empty memory.", MEMORY_FILE)

# Discord Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True

# Initialize Discord Client
client = discord.Client(intents=intents)

# Bard API session
bard_session = None

# --- Helper Functions ---

def initialize_bard_sync():
    """Synchronous Bard initialization to be run in executor."""
    from bardapi import Bard
    return Bard(token=BARD_TOKEN)

def get_user_key(guild_id: str, user_id: str) -> str:
    return f"{guild_id}_{user_id}"

def prune_memory(entries: list[str]) -> list[str]:
    """Prunes old memory entries if the total size exceeds MAX_MEMORY_PER_USER_BYTES."""
    current_size = len(json.dumps(entries).encode('utf-8'))
    while current_size > MAX_MEMORY_PER_USER_BYTES and len(entries) > 1:
        entries.pop(0)
        current_size = len(json.dumps(entries).encode('utf-8'))
    logger.debug("Memory pruned. Current size: %s bytes, entries: %s", current_size, len(entries))
    return entries

def update_user_memory(guild_id: str, user_id: str, log_entry: str, tone_shift: str | None = None):
    """Updates the in-memory user log and tone score."""
    key = get_user_key(guild_id, user_id)
    if key not in user_memory:
        user_memory[key] = {"log": [], "tone": DEFAULT_TONE_SCORE.copy()}
    user_memory[key]["log"].append(log_entry)
    user_memory[key]["log"] = prune_memory(user_memory[key]["log"])
    if tone_shift == "positive":
        user_memory[key]["tone"]["positive"] += 1
    elif tone_shift == "negative":
        user_memory[key]["tone"]["negative"] += 1
    logger.debug("Memory updated for %s. Current tone: %s", key, user_memory[key]['tone'])

async def save_user_memory_async():
    """Asynchronously saves the user memory to disk."""
    try:
        await asyncio.to_thread(lambda: json.dump(user_memory, open(MEMORY_FILE, "w", encoding="utf-8"), indent=2))
        logger.info("User memory saved to %s.", MEMORY_FILE)
    except Exception as e:
        logger.error("Error saving memory file asynchronously: %s", e, exc_info=True)

async def periodic_memory_save():
    """Task to periodically save user memory."""
    while True:
        await asyncio.sleep(MEMORY_SAVE_INTERVAL_MINUTES * 60)
        logger.info("%s", "Initiating periodic memory save...")
        await save_user_memory_async()

def determine_tone(user_text: str) -> str | None:
    """Determines the tone of user input based on keywords."""
    lowered = user_text.lower()
    positive_keywords = ["thanks", "thank you", "cool", "great", "good bot", "nice", "awesome", "love that", "excellent", "well done", "impressive", "amazing"]
    negative_keywords = ["stupid", "idiot", "dumb", "shut up", "bad bot", "hate this", "annoying", "useless", "terrible", "go away", "stop that"]
    if any(word in lowered for word in positive_keywords):
        return "positive"
    if any(word in lowered for word in negative_keywords):
        return "negative"
    return None

# --- NOTE: Removed generate_image_async because Shapes Inc documentation does not provide a direct API for it. ---
# The !imagine command is listed as a supported command for Shapes themselves, likely handled internally.
# If you want to explore image generation, you might try prompting the AI through chat/completions
# to see if it responds with image URLs, but this is not a standard API method.
async def generate_image_async(prompt: str) -> BytesIO | None:
    logger.warning("Image generation (!imagine) is currently disabled/unsupported via direct API calls based on Shapes Inc documentation.")
    return None

async def describe_image_with_shapesinc_async(image_url: str) -> str | None:
    logger.info("Attempting to describe image from URL: %s", image_url)
    if not SHAPESINC_API_KEY:
        logger.warning("SHAPESINC_API_KEY is not set. Image description skipped.")
        return None

    # API Endpoint from Shapes Inc documentation: https://api.shapes.inc/v1/chat/completions
    API_URL = "https://api.shapes.inc/v1/chat/completions"

    try:
        headers = {
            "Authorization": f"Bearer {SHAPESINC_API_KEY}",
            "Content-Type": "application/json"
        }
        # Data structure based on Shapes Inc 'API Multimodal Support' documentation
        data = {
            "model": f"shapesinc/{SHAPESINC_SHAPE_USERNAME}", # Model format from docs: shapesinc/<shape-username>
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=headers, json=data) as response:
                if response.status == 200:
                    json_response = await response.json()
                    # Response format is standard OpenAI-compatible JSON response
                    description = json_response.get("choices", [{}])[0].get("message", {}).get("content")
                    if description:
                        logger.info("Successfully described image: %s...", description[:50])
                        return description
                    else:
                        logger.warning("Shapes Inc description response missing content (expected in choices[0].message.content): %s", json_response)
                else:
                    response_text = await response.text()
                    logger.warning("Shapes Inc description failed (status %s): %s", response.status, response_text)

    except aiohttp.ClientError as e:
        logger.error("Shapes Inc describe network error: %s", e, exc_info=True)
    except Exception as e:
        logger.error("Shapes Inc describe unexpected error: %s", e, exc_info=True)
    return None

# --- Discord Events ---

@client.event
async def on_ready():
    global bard_session
    logger.info("Yu Zhong has awakened as %s!", client.user)
    logger.info("Current time in Damak, Koshi Province, Nepal: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z%z'))

    # Initialize active_guilds status for all guilds the bot is in
    for guild in client.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False
    logger.info("Bot active status initialized across guilds: %s", active_guilds)

    # Start periodic memory saving
    client.loop.create_task(periodic_memory_save())

    # Initialize Bard API
    if BARD_TOKEN:
        logger.info("Initializing Bard API (this might take a moment)...")
        try:
            bard_session = await asyncio.to_thread(initialize_bard_sync)
            logger.info("Bard API initialized successfully.")
        except Exception as e:
            logger.critical("Failed to initialize Bard API: %s. Bot will not respond to general messages.", e, exc_info=True)
            bard_session = None
    else:
        logger.critical("BARD_TOKEN is not set. Bard API will not function.")
        bard_session = None

    if not SHAPESINC_API_KEY:
        logger.warning("SHAPESINC_API_KEY is not set. Image description features will not function.")
    # Removed warning for image generation as it's now explicitly disabled/unsupported by direct API

@client.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return

    guild_id = str(member.guild.id)
    if not active_guilds.get(guild_id, False) or not bard_session:
        logger.info("Skipping greeting for %s (Bot inactive or Bard unavailable in %s).", member.name, member.guild.name)
        return

    logger.info("Greeting new member %s in %s...", member.name, member.guild.name)
    prompt = f"""{personality}
Greet the mortal named {member.name} who has just stepped into your dominion. Keep the greeting short, mysterious, and charismatic, in the style of Yu Zhong."""
    try:
        greeting_response = await asyncio.to_thread(bard_session.get_answer, prompt)
        greeting = greeting_response.get("content", "").strip()

        if greeting:
            channel_to_send = None
            # Prioritize 'general' or 'welcome' channels
            preferred_channel_names = ['general', 'welcome']
            for ch_name in preferred_channel_names:
                found_channel = discord.utils.get(member.guild.text_channels, name=ch_name)
                if found_channel and found_channel.permissions_for(member.guild.me).send_messages:
                    channel_to_send = found_channel
                    break
            # Fallback to any channel the bot can send messages in
            if channel_to_send is None:
                for ch in member.guild.text_channels:
                    if ch.permissions_for(member.guild.me).send_messages:
                        channel_to_send = ch
                        break

            if channel_to_send:
                await channel_to_send.send(f"{member.mention} {greeting}")
                logger.info("Sent greeting to %s in #%s.", member.name, channel_to_send.name)
            else:
                logger.warning("Could not find a suitable channel to send greeting to %s in guild %s", member.name, member.guild.name)
        else:
            logger.warning("Bard API returned empty greeting for %s.", member.name)
    except Exception as e:
        logger.error("Error generating or sending greeting for %s: %s", member.name, e, exc_info=True)

@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    user_key = get_user_key(guild_id, user_id)

    lower_case_content = message.content.lower().strip()

    # --- Admin Commands for Activation ---
    if lower_case_content == "/arise":
        if not message.author.guild_permissions.administrator:
            await message.reply("Only those with power may awaken the dragon.")
            return
        active_guilds[guild_id] = True
        await message.reply("Yu Zhong is now watching this realm. Beware.")
        logger.info("Bot activated in guild: %s (%s)", message.guild.name, guild_id)
        return

    if lower_case_content == "/stop":
        if not message.author.guild_permissions.administrator:
            await message.reply("You lack the authority to silence the dragon.")
            return
        active_guilds[guild_id] = False
        await message.reply("Dragon falls asleep. For now.")
        logger.info("Bot deactivated in guild: %s (%s)", message.guild.name, guild_id)
        return

    # --- New Reset Command ---
    if lower_case_content == "/reset":
        if user_key in user_memory:
            del user_memory[user_key]
            await save_user_memory_async() # Save immediately after reset
            await message.reply("Your memories, mortal, have been purged. A fresh slate awaits your foolishness.")
            logger.info("User %s (%s) reset their memory.", message.author.name, user_key)
        else:
            await message.reply("There is no memory of your foolishness to purge, mortal.")
        return

    # If bot is not active in this guild, ignore general messages (except admin commands and /reset)
    if not active_guilds.get(guild_id, False):
        logger.debug("Bot inactive in guild %s. Ignoring message from %s.", message.guild.name, message.author.name)
        return

    # --- Image Generation Command (Now disabled) ---
    if lower_case_content.startswith("!imagine "):
        prompt = message.content[len("!imagine "):].strip()
        await message.channel.send("My apologies, mortal. While Shapes can generate images, this API integration does not currently support direct image generation via `!imagine`. Try attaching an image for me to describe instead.", reference=message)
        logger.info("User %s attempted image generation for prompt: '%s' (feature disabled).", message.author.name, prompt)
        return


    user_input = message.content.strip()

    # --- Image Description on Attachment ---
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                await message.channel.send("Inspecting your offering, mortal...", reference=message)
                logger.info("User %s sent an image: %s", message.author.name, attachment.url)
                description = await describe_image_with_shapesinc_async(attachment.url)
                if description:
                    # Append image description to user input for Bard to consider
                    user_input = f"{user_input}\n[Image: {description}]".strip()
                    logger.info("Image described: %s...", description[:50])
                else:
                    # If description fails, add a fallback for Bard to acknowledge
                    user_input = f"{user_input}\n[Image: Yu Zhong's eyes cannot fully comprehend its essence.]".strip()
                    logger.warning("Could not describe image from %s.", message.author.name)
                break # Only process the first image attachment

    # If, after processing attachments, user_input is empty, exit.
    if not user_input:
        return

    # --- Bard General Response ---
    if not bard_session:
        await message.channel.send("My voice is currently silenced. Bard API is not configured or failed to initialize.", reference=message)
        logger.error("Bard API is not available. Cannot respond to general message.")
        return

    # Prepare context for Bard
    memory_data = user_memory.get(user_key, {"log": [], "tone": DEFAULT_TONE_SCORE.copy()})
    history = "\n".join(memory_data["log"])

    tone_desc = ""
    pos_score, neg_score = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
    if pos_score > neg_score:
        tone_desc = "you consider this person your very friend, they are you best buddy and you are good friend with them."
    elif neg_score > pos_score:
        tone_desc = "This friend has shown disrespect. Respond as if he is not a friend but just a person, dont be too rude just little bit of coldness thats all."
    else:
        tone_desc = "Your feelings towards this friend are neutral. respond respectfully as if they are someone of your equal ."

    prompt = f"""{personality}
{tone_desc}
Conversation history:
{history}
{message.author.name}: {user_input}
Yu Zhong:"""

    try:
        logger.info("Sending prompt to Bard API for %s (detected tone for prompt: %s).", message.author.name, tone_desc.split('.')[0])
        response_from_bard = await asyncio.to_thread(bard_session.get_answer, prompt)
        reply = response_from_bard.get("content", "").strip()

        if reply:
            await message.reply(reply)
            logger.info("Replied to %s: %s...", message.author.name, reply[:100])
            tone_shift = determine_tone(user_input)
            interaction_log_entry = f"{message.author.name}: {user_input} | Yu Zhong: {reply}"
            update_user_memory(guild_id, user_id, interaction_log_entry, tone_shift)
        else:
            await message.channel.send("The dragon is silent... my thoughts are not yet formed.", reference=message)
            logger.warning("Bard API returned empty response for %s.", message.author.name)

    except Exception as e:
        logger.error("Bard API general response error for %s: %s", message.author.name, e, exc_info=True)
        await message.channel.send("My arcane powers falter... (Skills on cooldown). Try again later, if you dare.", reference=message)


# --- Run the bot ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN is not set in .env. Bot cannot connect to Discord. Exiting.")
        exit()

    if not BARD_TOKEN:
        logger.critical("BARD_TOKEN is not set. Bard API will not function.")
    if not SHAPESINC_API_KEY:
        logger.warning("SHAPESINC_API_KEY is not set. Image description features will not function.")

    client.run(DISCORD_TOKEN)
