import keep_alive
keep_alive.keep_alive()

import logging
import os
import json
import discord
from discord.ext import commands # Recommended for future use if you move to commands.Bot
from dotenv import load_dotenv
import asyncio
import aiohttp # New import for asynchronous HTTP requests
from io import BytesIO
from datetime import datetime # Import datetime for current time logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")

# --- Configuration ---
MAX_MEMORY_PER_USER_BYTES = 500000 # bytes limit per user per guild (renamed for clarity)
MEMORY_FILE = "user_memory.json" # Using local file for UptimeRobot setup
DEFAULT_TONE_SCORE = {"positive": 0, "negative": 0} # Renamed for consistency
MEMORY_SAVE_INTERVAL_MINUTES = 5 # How often to save user memory to disk

# Load personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
    logger.info("Custom personality loaded from personality.txt")
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, darkly witty, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."
    logger.warning("personality.txt not found. Using default personality.")
except Exception as e: # Catch any other file reading errors
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, darkly witty, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."
    logger.error(f"Error loading personality from file: {e}. Using default personality.", exc_info=True)


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
        logger.error(f"Error loading memory file: {e}. Starting with empty memory.", exc_info=True)
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
bard_session = None # This will hold the Bard API instance

# --- Helper Functions ---

# Asynchronous function to initialize Bard (since bardapi uses requests internally,
# we wrap it in run_in_executor to prevent blocking, but it's still less ideal than a truly async LLM API)
def initialize_bard_sync():
    """Synchronous Bard initialization to be run in executor."""
    from bardapi import Bard
    return Bard(token=BARD_TOKEN)

# Asynchronous image generation with aiohttp
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

# Asynchronous image description with aiohttp
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

def get_user_key(guild_id: str, user_id: str) -> str:
    return f"{guild_id}_{user_id}"

def prune_memory(entries: list[str]) -> list[str]:
    """Prunes old memory entries if the total size exceeds MAX_MEMORY_PER_USER_BYTES."""
    current_size = len(json.dumps(entries).encode('utf-8')) # Approximate size of the list
    while current_size > MAX_MEMORY_PER_USER_BYTES and len(entries) > 1:
        entries.pop(0) # Remove the oldest entry
        current_size = len(json.dumps(entries).encode('utf-8'))
    logger.debug(f"Memory pruned. Current size: {current_size} bytes, entries: {len(entries)}")
    return entries


@client.event
async def on_ready():
    logger.info(f"Yu Zhong is online as {client.user} and ready to dominate.")

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)

# --- THIS
