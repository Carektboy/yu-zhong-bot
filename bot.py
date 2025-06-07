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
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")

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
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, deadpool personality, nonchalant, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."
    logger.warning("personality.txt not found. Using default personality.")
except Exception as e:
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, deadpool personality, nonchalant, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."
    logger.error(f"Error loading personality from file: {e}. Using default personality.", exc_info=True)

# Global Bot State
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
        logger.error(f"Error loading memory file: {e}. Starting with empty memory.", exc_info=True)
else:
    logger.info(f"{MEMORY_FILE} not found. Starting with empty memory.")

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
    logger.debug(f"Memory pruned. Current size: {current_size} bytes, entries: {len(entries)}")
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
    logger.debug(f"Memory updated for {key}. Current tone: {user_memory[key]['tone']}")

async def save_user_memory_async():
    """Asynchronously saves the user memory to disk."""
    try:
        await asyncio.to_thread(lambda: json.dump(user_memory, open(MEMORY_FILE, "w", encoding="utf-8"), indent=2))
        logger.info(f"User memory saved to {MEMORY_FILE}.")
    except Exception as e:
        logger.error(f"Error saving memory file asynchronously: {e}", exc_info=True)

async def periodic_memory_save():
    """Task to periodically save user memory."""
    while True:
        await asyncio.sleep(MEMORY_SAVE_INTERVAL_MINUTES * 60)
        logger.info("Initiating periodic memory save...")
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

async def generate_image_async(prompt: str) -> BytesIO | None:
    logger.info(f"Attempting to generate image for prompt: '{prompt}'")
    if not SHAPESINC_API_KEY:
        logger.warning("SHAPESINC_API_KEY is not set. Image generation skipped.")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {SHAPESINC_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {"prompt": prompt}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.shapes.inc/v1/shapes/yuzhong-eqf1/infer",
                headers=headers,
                json=data
            ) as response:
                if response.status == 200:
                    json_data = await response.json()
                    image_url = json_data.get("image_url")
                    if image_url:
                        async with session.get(image_url) as image_response:
                            if image_response.status == 200:
                                image_bytes = await image_response.read()
                                logger.info(f"Successfully generated and fetched image for prompt: '{prompt}'")
                                return BytesIO(image_bytes)
                            else:
                                logger.warning(f"Failed to fetch generated image (status {image_response.status}): {await image_response.text()}")
                    else:
                        logger.warning(f"No image URL in Shapes Inc response: {json_data}")
                else:
                    logger.warning(f"Shapes Inc image generation failed (status {response.status}): {await response.text()}")

    except aiohttp.ClientError as e:
        logger.error(f"Shapes Inc image generation network error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Shapes Inc image generation unexpected error: {e}", exc_info=True)

    return None

async def describe_image_with_shapesinc_async(image_url: str) -> str | None:
    logger.info(f"Attempting to describe image from URL: {image_url}")
    if not SHAPESINC_API_KEY:
        logger.warning("SHAPESINC_API_KEY is not set. Image description skipped.")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.shapes.inc/v1/describe",
                headers={"Authorization": f"Bearer {SHAPESINC_API_KEY}"},
                json={"image_url": image_url}
            ) as response:
                if response.status == 200:
                    description = (await response.json()).get("description")
                    logger.info(f"Successfully described image: {description[:50]}...")
                    return description
                else:
                    logger.warning(f"Shapes Inc description failed (status {response.status}): {await response.text()}")
    except aiohttp.ClientError as e:
        logger.error(f"Shapes Inc describe network error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Shapes Inc describe unexpected error: {e}", exc_info=True)
    return None

# --- Discord Events ---

@client.event
async def on_ready():
    global bard_session
    logger.info(f"Yu Zhong has awakened as {client.user}!")
    logger.info(f"Current time in Damak, Koshi Province, Nepal: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z%z')}")

    # Initialize active_guilds status for all guilds the bot is in
    for guild in client.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False
    logger.info(f"Bot active status initialized across guilds: {active_guilds}")

    # Start periodic memory saving
    client.loop.create_task(periodic_memory_save())

    # Initialize Bard API
    if BARD_TOKEN:
        logger.info("Initializing Bard API (this might take a moment)...")
        try:
            bard_session = await asyncio.to_thread(initialize_bard_sync)
            logger.info("Bard API initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize Bard API: {e}. Bot will not respond to general messages.", exc_info=True)
            bard_session = None
    else:
        logger.critical("BARD_TOKEN is not set. Bard API will not function.")
        bard_session = None

    if not SHAPESINC_API_KEY:
        logger.warning("SHAPESINC_API_KEY is not set. Image generation/description features will not function.")

@client.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return

    guild_id = str(member.guild.id)
    if not active_guilds.get(guild_id, False) or not bard_session:
        logger.info(f"Skipping greeting for {member.name} (Bot inactive or Bard unavailable in {member.guild.name}).")
        return

    logger.info(f"Greeting new member {member.name} in {member.guild.name}...")
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
                logger.info(f"Sent greeting to {member.name} in #{channel_to_send.name}.")
            else:
                logger.warning(f"Could not find a suitable channel to send greeting to {member.name} in guild {member.guild.name}")
        else:
            logger.warning(f"Bard API returned empty greeting for {member.name}.")
    except Exception as e:
        logger.error(f"Error generating or sending greeting for {member.name}: {e}", exc_info=True)

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
        logger.info(f"Bot activated in guild: {message.guild.name} ({guild_id})")
        return

    if lower_case_content == "/stop":
        if not message.author.guild_permissions.administrator:
            await message.reply("You lack the authority to silence the dragon.")
            return
        active_guilds[guild_id] = False
        await message.reply("Dragon falls asleep. For now.")
        logger.info(f"Bot deactivated in guild: {message.guild.name} ({guild_id})")
        return

    # If bot is not active in this guild, ignore general messages (except admin commands)
    if not active_guilds.get(guild_id, False):
        logger.debug(f"Bot inactive in guild {message.guild.name}. Ignoring message from {message.author.name}.")
        return

    # --- Image Generation Command ---
    if lower_case_content.startswith("!imagine "):
        prompt = message.content[len("!imagine "):].strip()
        await message.channel.send("Summoning a vision from the depths. This may take a moment...", reference=message)
        logger.info(f"User {message.author.name} requested image for prompt: '{prompt}'")

        image_bytes = await generate_image_async(prompt)
        if image_bytes:
            file = discord.File(image_bytes, filename="yu_zhong_creation.png")
            await message.channel.send(file=file)
            logger.info(f"Sent generated image for prompt: '{prompt}'")
        else:
            await message.channel.send("My arcane powers faltered. The image remains unseen. (Lacks mana)", reference=message)
            logger.warning(f"Failed to generate image for prompt: '{prompt}'")
        return

    user_input = message.content.strip()

    # --- Image Description on Attachment ---
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                await message.channel.send("Inspecting your offering, mortal...", reference=message)
                logger.info(f"User {message.author.name} sent an image: {attachment.url}")
                description = await describe_image_with_shapesinc_async(attachment.url)
                if description:
                    # Append image description to user input for Bard to consider
                    user_input = f"{user_input}\n[Image: {description}]".strip()
                    logger.info(f"Image described: {description[:50]}...")
                else:
                    user_input = f"{user_input}\n[Image: Yu Zhong's eyes cannot fully comprehend its essence.]".strip()
                    logger.warning(f"Could not describe image from {message.author.name}.")
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
        tone_desc = "You consider this mortal somewhat loyal. Be a little more forgiving or playfully condescending, yet still confident and darkly witty. Respond briefly."
    elif neg_score > pos_score:
        tone_desc = "This mortal has shown disrespect. Respond colder, more dismissively, perhaps with a hint of menace. Keep it concise."
    else:
        tone_desc = "Your feelings towards this mortal are neutral. Respond confidently and wittily, briefly, as is your nature."

    prompt = f"""{personality}
{tone_desc}
Conversation history:
{history}
{message.author.name}: {user_input}
Yu Zhong:"""

    try:
        logger.info(f"Sending prompt to Bard API for {message.author.name} (detected tone for prompt: {tone_desc.split('.')[0]})...")
        response_from_bard = await asyncio.to_thread(bard_session.get_answer, prompt)
        reply = response_from_bard.get("content", "").strip()

        if reply:
            await message.reply(reply)
            logger.info(f"Replied to {message.author.name}: {reply[:100]}...")
            tone_shift = determine_tone(user_input)
            interaction_log_entry = f"{message.author.name}: {user_input} | Yu Zhong: {reply}"
            update_user_memory(guild_id, user_id, interaction_log_entry, tone_shift)
        else:
            await message.channel.send("The dragon is silent... my thoughts are not yet formed.", reference=message)
            logger.warning(f"Bard API returned empty response for {message.author.name}.")

    except Exception as e:
        logger.error(f"Bard API general response error for {message.author.name}: {e}", exc_info=True)
        await message.channel.send("My arcane powers falter... (Skills on cooldown). Try again later, if you dare.", reference=message)


# --- Run the bot ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN is not set in .env. Bot cannot connect to Discord. Exiting.")
        exit()

    if not BARD_TOKEN:
        logger.critical("BARD_TOKEN is not set. Bard API will not function.")
    if not SHAPESINC_API_KEY:
        logger.warning("SHAPESINC_API_KEY is not set. Image generation/description features will not function.")

    client.run(DISCORD_TOKEN)
    
