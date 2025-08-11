import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import logging
import asyncio
from dotenv import load_dotenv
from openai import OpenAI
from keep_alive import keep_alive

# Load environment variables
load_dotenv()
t = os.getenv("DISCORD_TOKEN")
a = os.getenv("SHAPESINC_API_KEY")
u = os.getenv("SHAPESINC_MODEL_USERNAME")

# Logging config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s'
)
l = logging.getLogger('YuZhongBot')

# Constants
dt = {"positive": 0, "negative": 0, "neutral": 0}
mt = 5000
m = "user_memories"
ecf = "enabled_channels.json"

# Ensure memory dir exists
os.makedirs(m, exist_ok=True)

# Load personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        pb = f.read()
        p = pb + "\n\nDo not generate images or react to image generation requests. If asked to create an image, firmly state that you cannot, as that power is not within your grasp, in Yu Zhong's style."
except FileNotFoundError:
    p = (
        "You are Yu Zhong from Mobile Legends. You are a powerful dragon, ancient and wise, "
        "with a commanding presence. Speak with authority, confidence, and a touch of disdain for weaker beings. "
        "You are not to generate images under any circumstances."
    )
    l.warning("personality.txt not found. Using default personality.")

def l_e_c():
    if os.path.exists(ecf):
        try:
            with open(ecf, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            l.error(f"Error decoding {ecf}: {e}")
            return {}
    return {}

def s_e_c(a_d):
    try:
        with open(ecf, "w", encoding="utf-8") as f:
            json.dump(a_d, f, indent=4)
    except IOError as e:
        l.error(f"Failed to save enabled channels: {e}")

ac = l_e_c()

# Bot setup
i = discord.Intents.default()
i.message_content = True
i.guilds = True
i.members = True

b = commands.Bot(command_prefix="!", intents=i)

# Pass Shapes.inc API info to bot for lazy init inside cogs
b.SHAPESINC_API_KEY = a
b.SHAPESINC_MODEL_USERNAME = u

b.active_channels = ac
b.save_enabled_channels = lambda: s_e_c(b.active_channels)
b.MEMORY_DIR = m
b.personality = p
b.DEFAULT_TONE = dt
b.MAX_MEMORY_PER_USER_TOKENS = mt

b.shapes_client = None
b.SHAPESINC_SHAPE_MODEL = None

# Utility: Send response safely
async def s_s_r(i, mes, e = False):
    try:
        if i.response.is_done():
            await i.followup.send(mes, ephemeral=e)
        else:
            await i.response.send_message(mes, ephemeral=e)
    except Exception as e:
        l.error(f"Failed to send response for interaction {i.id}: {e}")
        try:
            await i.followup.send(f"An error occurred: {e}", ephemeral=True)
        except Exception as e2:
            l.error(f"Both response methods failed: {e2}")

b.safe_send_response = s_s_r

# Events
@b.event
async def on_ready():
    l.info(f'Logged in as {b.user.name} ({b.user.id})')

    # Load cogs
    ie = [
        "cogs.admin",
        "cogs.mlbb",
        "cogs.ai_chat",
    ]
    for ext in ie:
        try:
            await b.load_extension(ext)
            l.info(f"Loaded extension: {ext}")
        except commands.ExtensionError as e:
            l.error(f"Failed to load extension {ext}: {e}")

    try:
        synced = await b.tree.sync()
        l.info(f"Synced {len(synced)} command(s).")
    except Exception as e:
        l.error(f"Failed to sync commands: {e}")

@b.event
async def on_member_join(mem):
    l.info(f'{mem.name} has joined the server!')

@b.event
async def on_guild_join(g):
    l.info(f"Joined new guild: {g.name} ({g.id})")
    dc = g.system_channel or (g.text_channels[0] if g.text_channels else None)
    if dc:
        try:
            await dc.send(
                f"Behold, I, Yu Zhong, have arrived! To activate my power in a channel, an administrator must use `/arise`."
            )
        except discord.Forbidden:
            l.warning(f"Missing permissions to send welcome message in {g.name}.")

@b.event
async def on_message(mes):
    if mes.author.bot or not mes.content or mes.author == b.user:
        return

    c = str(mes.channel.id)
    bm = b.user.mentioned_in(mes)

    if not b.active_channels.get(c) and not bm:
        await b.process_commands(mes)
        return

    await b.process_commands(mes)

# Main async runner
async def main():
    if not t:
        l.critical("DISCORD_TOKEN not set. Exiting.")
        return

    keep_alive()
    l.info("Keep-alive web server started.")

    try:
        await b.start(t)
    except discord.errors.LoginFailure as e:
        l.critical(f"Failed to log in: {e}")
    except Exception as e:
        l.critical(f"Unexpected startup error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        l.info("Bot shutting down...")
        asyncio.run(b.close())
    except Exception as e:
        l.error(f"Unhandled error: {e}")
