import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import logging
import asyncio
import time
from dotenv import load_dotenv
from openai import OpenAI
from keep_alive import keep_alive

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")
SHAPESINC_MODEL_USERNAME = os.getenv("SHAPESINC_MODEL_USERNAME")

SHAPESINC_SHAPE_MODEL = None
shapes_client = None

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

MAX_MEMORY_PER_USER_TOKENS = 5000
DEFAULT_TONE = {"positive": 0, "negative": 0}
MEMORY_DIR = "user_memories"
ENABLED_CHANNELS_FILE = "enabled_channels.json"

if not os.path.exists(MEMORY_DIR):
    os.makedirs(MEMORY_DIR)

try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality_base = f.read()
        personality = personality_base + "\n\nDo not generate images or react to image generation requests. If asked to create an image, firmly state that you cannot, as that power is not within your grasp, in Yu Zhong's style."
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends. You are a powerful dragon, ancient and wise, with a commanding presence. Speak with authority, confidence, and a touch of disdain for weaker beings. You are not to generate images under any circumstances."
    logger.warning("personality.txt not found. Using default personality.")

def load_enabled_channels():
    if os.path.exists(ENABLED_CHANNELS_FILE):
        try:
            with open(ENABLED_CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding {ENABLED_CHANNELS_FILE}. Starting with empty enabled channels: {e}")
            return {}
    return {}

def save_enabled_channels(active_channels_data):
    try:
        with open(ENABLED_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(active_channels_data, f, indent=4)
    except IOError as e:
        logger.error(f"Failed to save enabled channels: {e}")

active_channels = load_enabled_channels()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

bot.active_channels = active_channels
bot.save_enabled_channels = lambda: save_enabled_channels(bot.active_channels)
bot.MEMORY_DIR = MEMORY_DIR
bot.personality = personality
bot.DEFAULT_TONE = DEFAULT_TONE
bot.MAX_MEMORY_PER_USER_TOKENS = MAX_MEMORY_PER_USER_TOKENS
bot.shapes_client = shapes_client
bot.SHAPESINC_SHAPE_MODEL = SHAPESINC_SHAPE_MODEL

async def safe_send_response(interaction: discord.Interaction, message: str, ephemeral: bool = False):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(message, ephemeral=ephemeral)
    except Exception as e:
        logger.error(f"Failed to send response for interaction {interaction.id}: {e}")
        try:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        except Exception as e2:
            logger.error(f"Both response methods failed: {e2}")

bot.safe_send_response = safe_send_response

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    if SHAPESINC_API_KEY and SHAPESINC_MODEL_USERNAME:
        bot.shapes_client = OpenAI(
            base_url="https://api.shapes.inc",
            api_key=SHAPESINC_API_KEY,
        )
        bot.SHAPESINC_SHAPE_MODEL = SHAPESINC_MODEL_USERNAME
        logger.info("Shapes.inc client initialized.")
    else:
        logger.warning("SHAPESINC_API_KEY or SHAPESINC_MODEL_USERNAME not set. AI features will be disabled.")

    initial_extensions = [
        "cogs.admin",
        "cogs.mlbb",
        "cogs.ai_chat",
    ]
    for extension in initial_extensions:
        try:
            await bot.load_extension(extension)
            logger.info(f"Loaded extension: {extension}")
        except commands.ExtensionError as e:
            logger.error(f"Failed to load extension {extension}: {e}")

    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s).")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

@bot.event
async def on_member_join(member):
    logger.info(f'{member.name} has joined the server!')

@bot.event
async def on_guild_join(guild):
    logger.info(f"Joined new guild: {guild.name} ({guild.id})")
    default_channel = guild.system_channel or guild.text_channels[0]
    if default_channel:
        try:
            await default_channel.send(
                f"Behold, I, Yu Zhong, have arrived! To activate my power in a channel, an administrator must use `/arise`."
            )
        except discord.Forbidden:
            logger.warning(f"Missing permissions to send welcome message in {guild.name}.")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.author.bot:
        return

    if not message.content:
        return

    channel_id_str = str(message.channel.id)
    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    user_display_name = message.author.display_name

    bot_mentioned = bot.user.mentioned_in(message)

    if not bot.active_channels.get(channel_id_str) and not bot_mentioned:
        await bot.process_commands(message)
        return

    if message.guild and bot_mentioned:
        pass

    await bot.process_commands(message)

async def main():
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN environment variable not set. Exiting.")
        return

    keep_alive()

    try:
        await bot.start(DISCORD_TOKEN)
    except discord.errors.LoginFailure as e:
        logger.critical(f"Failed to log in: {e}. Check your DISCORD_TOKEN.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during bot startup: {e}")
      

if __name__ == "__main__":
    asyncio.run(main())
