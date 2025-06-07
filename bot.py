import keep_alive
keep_alive.keep_alive()

import logging
import os
import json
import discord
from dotenv import load_dotenv
import asyncio
import aiohttp # New import for asynchronous HTTP requests
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")

# --- Configuration ---
MAX_MEMORY_PER_USER = 500000  # bytes limit per user per guild
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

# Load personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, darkly witty, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."
    logger.warning("personality.txt not found. Using default personality.")

# Load active guilds and user memory
active_guilds = {} # Stores {guild_id: True/False}
user_memory = {}   # Stores {user_key: {"log": [], "tone": {"positive": 0, "negative": 0}}}

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
intents.members = True # Required for on_member_join
intents.guilds = True  # Required for on_member_join and guild-specific commands

# Initialize Discord Client
client = discord.Client(intents=intents)

# Bard API - Using a session for better performance and to handle cookies
# We will initialize this in on_ready for proper async context
bard_session = None

# --- Helper Functions ---

# Asynchronous function to initialize Bard (since bardapi uses requests internally,
# we wrap it in run_in_executor to prevent blocking, but it's still less ideal than a truly async LLM API)
def initialize_bard_sync():
    """Synchronous Bard initialization to be run in executor."""
    from bardapi import Bard
    return Bard(token=BARD_TOKEN)

# Asynchronous image generation with aiohttp
async def generate_image_async(prompt):
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
        logger.error(f"Shapes Inc image generation network error: {e}")
    except Exception as e:
        logger.error(f"Shapes Inc image generation unexpected error: {e}")

    return None

# Asynchronous image description with aiohttp
async def describe_image_with_shapesinc_async(image_url):
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
        logger.error(f"Shapes Inc describe network error: {e}")
    except Exception as e:
        logger.error(f"Shapes Inc describe unexpected error: {e}")
    return None

def get_user_key(guild_id, user_id):
    return f"{guild_id}_{user_id}"

def prune_memory(entries):
    text = "\n".join(entries)
    while len(text.encode('utf-8')) > MAX_MEMORY_PER_USER and len(entries) > 1:
        entries = entries[1:] # Remove oldest entry
        text = "\n".join(entries)
    return entries

# Asynchronous memory saving to avoid blocking
async def save_user_memory_async():
    try:
        # Use asyncio.to_thread to run blocking I/O in a separate thread
        await asyncio.to_thread(lambda: json.dump(user_memory, open(MEMORY_FILE, "w", encoding="utf-8"), indent=2))
        logger.debug("Memory saved asynchronously.")
    except Exception as e:
        logger.error(f"Error saving memory file asynchronously: {e}")

# This will be called periodically to save memory
async def periodic_memory_save():
    while True:
        await asyncio.sleep(60 * 5) # Save every 5 minutes
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

@client.event
async def on_ready():
    global bard_session
    logger.info(f"Yu Zhong has awakened as {client.user}!")
    # Initialize active_guilds status for all guilds the bot is in
    for guild in client.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False # Default to inactive
    logger.info(f"Bot active status initialized: {active_guilds}")

    # Start periodic memory saving
    client.loop.create_task(periodic_memory_save())

    # Initialize Bard API by running it in a thread pool executor
    # This is a workaround since bardapi itself is synchronous
    logger.info("Initializing Bard API (this might take a moment)...")
    try:
        bard_session = await asyncio.to_thread(initialize_bard_sync)
        logger.info("Bard API initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Bard API: {e}. Bot will not respond to general messages.")
        bard_session = None # Ensure it's None if init fails

@client.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    user_key = get_user_key(guild_id, user_id)

    # --- Admin Commands for Activation ---
    if message.content.lower() == "/arise":
        if not message.author.guild_permissions.administrator:
            await message.reply("Only those with power may awaken the dragon.")
            return
        active_guilds[guild_id] = True
        await message.reply("Yu Zhong is now watching this realm. Beware.")
        logger.info(f"Bot activated in guild: {message.guild.name}")
        return

    if message.content.lower() == "/stop":
        if not message.author.guild_permissions.administrator:
            await message.reply("You lack the authority to silence the dragon.")
            return
        active_guilds[guild_id] = False
        await message.reply("Dragon falls asleep. For now.")
        logger.info(f"Bot deactivated in guild: {message.guild.name}")
        return

    # If bot is not active in this guild, ignore general messages
    if not active_guilds.get(guild_id, False):
        return

    # --- Image Generation Command ---
    if message.content.startswith("!imagine "):
        prompt = message.content[len("!imagine "):].strip()
        await message.channel.send("Summoning a vision from the depths. This may take a moment...", reference=message) # Reference original message
        logger.info(f"User {message.author.name} requested image for prompt: '{prompt}'")

        image_bytes = await generate_image_async(prompt) # Await the async function
        if image_bytes:
            file = discord.File(image_bytes, filename="yu_zhong_creation.png")
            await message.channel.send(file=file)
            logger.info(f"Sent generated image for prompt: '{prompt}'")
        else:
            await message.channel.send("My arcane powers faltered. The image remains unseen. (Lacks mana)", reference=message)
            logger.warning(f"Failed to generate image for prompt: '{prompt}'")
        return # Important to return after handling a command

    user_input = message.content.strip()
    if not user_input:
        return

    # --- Image Description on Attachment ---
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                await message.channel.send("Inspecting your offering, mortal...", reference=message)
                logger.info(f"User {message.author.name} sent an image: {attachment.url}")
                description = await describe_image_with_shapesinc_async(attachment.url) # Await the async function
                if description:
                    user_input = f"The mortal sent an image. It appears to be: {description}"
                    logger.info(f"Image described: {description[:50]}...")
                else:
                    user_input = "The mortal sent an image, but even Yu Zhong's eyes cannot fully comprehend its essence. My judgment is clouded."
                    logger.warning(f"Could not describe image from {message.author.name}.")
                break # Only process the first image attachment

    # --- Bard General Response ---
    if not bard_session:
        await message.channel.send("My voice is currently silenced. Bard API failed to initialize.", reference=message)
        logger.error("Bard API session is not initialized. Cannot respond to general message.")
        return

    # Prepare context for Bard
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

    prompt = f"""{personality}

{tone_desc}
Conversation history:
{history}

{message.author.name}: {user_input}
Yu Zhong:"""

    try:
        # Run Bard API call in a separate thread to avoid blocking the event loop
        # This is a key change for speed
        logger.info(f"Sending prompt to Bard API for {message.author.name} (tone: {tone_desc.split('.')[0]})...")
        response = await asyncio.to_thread(bard_session.get_answer, prompt)
        reply = response.get("content", "").strip()

        if reply:
            await message.reply(reply)
            logger.info(f"Replied to {message.author.name}: {reply[:100]}...")

            # Update memory after successful response
            tone_shift = determine_tone(user_input)
            interaction = f"{message.author.name}: {user_input} | Yu Zhong: {reply}"
            update_user_memory(guild_id, user_id, interaction, tone_shift) # This will trigger save_user_memory_async
        else:
            await message.channel.send("The dragon is silent... my thoughts are not yet formed.", reference=message)
            logger.warning(f"Bard API returned empty response for {message.author.name}.")

    except Exception as e:
        logger.error(f"Bard API Error for {message.author.name}: {e}")
        await message.channel.send("My arcane powers falter... (Skills on cooldown). Try again later, if you dare.", reference=message)
        # Still log interaction for memory, even if error
        interaction = f"{message.author.name}: {user_input} | Yu Zhong: API Error - {e}"
        update_user_memory(guild_id, user_id, interaction, "negative") # Indicate negative interaction

@client.event
async def on_member_join(member):
    if member.bot:
        return

    guild_id = str(member.guild.id)
    if not active_guilds.get(guild_id, False):
        logger.info(f"Bot inactive in {member.guild.name}. Skipping greeting for {member.name}.")
        return # Only greet if bot is active in guild

    if not bard_session:
        logger.warning(f"Bard API not initialized. Skipping greeting for {member.name}.")
        return

    logger.info(f"Greeting new member {member.name} in {member.guild.name}...")
    prompt = f"""{personality}
Greet the mortal named {member.name} who has just stepped into your dominion. Keep the greeting short, mysterious, and charismatic, in the style of Yu Zhong."""
    try:
        greeting_response = await asyncio.to_thread(bard_session.get_answer, prompt)
        greeting = greeting_response.get("content", "").strip()

        if greeting:
            channel = None
            # Prioritize 'general' channel, then any channel the bot can send messages in
            for ch in member.guild.text_channels:
                if ch.permissions_for(member.guild.me).send_messages:
                    if ch.name == 'general':
                        channel = ch
                        break
                    if channel is None: # Set to first available if 'general' not found yet
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
    if not SHAPESINC_API_KEY:
        logger.critical("SHAPESINC_API_KEY is not set in .env. Image features will not function.")

    client.run(DISCORD_TOKEN)
