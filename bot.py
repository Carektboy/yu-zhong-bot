from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import asyncio
import time
import requests
from bs4 import BeautifulSoup
import logging
import os
import json
import discord

from openai import OpenAI

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")
SHAPESINC_SHAPE_MODEL = os.getenv("SHAPESINC_SHAPE_MODEL")

MAX_MEMORY_PER_USER = 500000
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

patch_cache = {"data": "", "timestamp": 0}

def get_latest_patch_notes():
    global patch_cache
    now = time.time()
    if now - patch_cache["timestamp"] < 3600:
        return patch_cache["data"]
    try:
        url = "https://mobile-legends.fandom.com/wiki/Latest_Patch_Notes"
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        patch_section = soup.find("div", class_="mw-parser-output")
        if patch_section:
            paragraphs = patch_section.find_all("p", limit=5)
            summary = "\n".join([p.text.strip() for p in paragraphs if p.text.strip()])
            patch_cache["data"] = summary
            patch_cache["timestamp"] = now
            return summary
        return "Could not find recent patch notes."
    except Exception as e:
        logger.warning(f"Patch notes fetch failed: {e}")
        return "Unable to fetch patch notes at this time."

try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality_base = f.read()
        personality = personality_base + "\n\nDo not generate images or react to image generation requests. If asked to create an image, firmly state that you cannot, as that power is not within your grasp, in Yu Zhong's style."
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends..."
    logger.warning("personality.txt not found. Using default personality.")

active_guilds = {}
user_memory = {}
if os.path.exists(MEMORY_FILE):
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            user_memory = json.load(f)
        logger.info(f"Loaded memory from {MEMORY_FILE}")
    except:
        logger.error(f"Error decoding {MEMORY_FILE}. Starting empty.")
else:
    logger.info(f"{MEMORY_FILE} not found. Starting with empty memory.")

def update_user_memory(guild_id, user_id, user_input, reply, tone_change):
    user_key = f"{guild_id}_{user_id}"
    memory = user_memory.get(user_key, {"log": [], "tone": DEFAULT_TONE.copy()})
    memory["log"].append({"role": "user", "content": user_input})
    memory["log"].append({"role": "assistant", "content": reply})
    memory["tone"][tone_change] += 1
    while len(json.dumps(memory)) > MAX_MEMORY_PER_USER and len(memory["log"]) > 2:
        memory["log"] = memory["log"][2:]
    user_memory[user_key] = memory

def determine_tone(text):
    rude_keywords = ["stupid", "dumb", "trash", "hate"]
    kind_keywords = ["thank", "please", "good", "love"]
    text = text.lower()
    if any(word in text for word in rude_keywords):
        return "negative"
    elif any(word in text for word in kind_keywords):
        return "positive"
    return "neutral"

def save_enabled_guilds():
    filepath = os.path.join(os.path.dirname(__file__), 'enabled_guilds.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump([gid for gid, enabled in active_guilds.items() if enabled], f)

def load_enabled_guilds():
    filepath = os.path.join(os.path.dirname(__file__), 'enabled_guilds.json')
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        enabled_ids = json.load(f)
        return {str(gid): True for gid in enabled_ids}

active_guilds = load_enabled_guilds()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
shapes_client = None

@bot.event
async def on_ready():
    global shapes_client
    logger.info(f"Yu Zhong has awakened as {bot.user}!")
    for guild in bot.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False
    if SHAPESINC_API_KEY and SHAPESINC_SHAPE_MODEL:
        try:
            shapes_client = OpenAI(api_key=SHAPESINC_API_KEY, base_url="https://api.shapes.inc/v1/")
            logger.info("Shapes.inc API initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize Shapes.inc API: {e}")
            shapes_client = None
    else:
        logger.critical("Missing Shapes.inc API keys.")
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

@bot.tree.command(name="arise", description="Activate Yu Zhong in this server.")
@app_commands.checks.has_permissions(administrator=True)
async def arise(interaction: discord.Interaction):
    active_guilds[str(interaction.guild_id)] = True
    save_enabled_guilds()
    await interaction.response.send_message("Yu Zhong has risen from the abyss...", ephemeral=True)

@bot.tree.command(name="stop", description="Put Yu Zhong back to rest.")
@app_commands.checks.has_permissions(administrator=True)
async def stop(interaction: discord.Interaction):
    active_guilds[str(interaction.guild_id)] = False
    save_enabled_guilds()
    await interaction.response.send_message("Yu Zhong has returned to the abyss.", ephemeral=True)

@bot.tree.command(name="reset", description="Reset Yu Zhong's memory for this server.")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    removed = False
    for key in list(user_memory.keys()):
        if key.startswith(f"{guild_id}_"):
            del user_memory[key]
            removed = True
    if removed:
        await interaction.response.send_message("Yu Zhong’s memory has been purged for this server.", ephemeral=True)
    else:
        await interaction.response.send_message("No memory found to reset for this server.", ephemeral=True)

@bot.tree.command(name="patch", description="Shows the latest MLBB patch summary.")
async def patch(interaction: discord.Interaction):
    summary = get_latest_patch_notes()
    await interaction.response.send_message(f"\U0001F4DC **Latest Patch Notes Summary:**\n```{summary[:1900]}```")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    user_key = f"{guild_id}_{user_id}"
    if not active_guilds.get(guild_id, False):
        return
    user_input = message.content.strip()
    if not user_input or not shapes_client:
        return
    memory_data = user_memory.get(user_key, {"log": [], "tone": DEFAULT_TONE.copy()})
    messages = [{"role": "system", "content": personality}]
    pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
    tone_desc = "Neutral tone. Respond confidently and wittily, briefly."
    if pos > neg:
        tone_desc = "You like this mortal. Be forgiving, witty, and confident."
    elif neg > pos:
        tone_desc = "This mortal has been rude. Be cold, dismissive, brief."
    messages[0]["content"] += f"\n{tone_desc}"
    messages.extend(memory_data["log"])
    patch_notes = get_latest_patch_notes()
    enhanced_input = f"{user_input}\n\n[Context: Latest MLBB Patch Notes]\n{patch_notes}"
    messages.append({"role": "user", "content": enhanced_input})
    try:
        response_completion = await asyncio.to_thread(
            shapes_client.chat.completions.create,
            model=SHAPESINC_SHAPE_MODEL,
            messages=messages,
            max_tokens=250,
            temperature=0.7
        )
        reply = response_completion.choices[0].message.content.strip()
        if reply:
            await message.reply(reply)
            update_user_memory(guild_id, user_id, user_input, reply, determine_tone(user_input))
        else:
            await message.channel.send("The dragon is silent...")
    except Exception as e:
        logger.error(f"API error: {e}")
        await message.channel.send("My arcane powers falter...")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN missing.")
    if not SHAPESINC_API_KEY or not SHAPESINC_SHAPE_MODEL:
        logger.critical("Shapes.inc API key or model missing.")
    bot.run(DISCORD_TOKEN)
