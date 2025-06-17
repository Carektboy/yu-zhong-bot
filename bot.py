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
    # Cache for 1 hour (3600 seconds)
    if now - patch_cache["timestamp"] < 3600:
        return patch_cache["data"]
    try:
        url = "https://mobile-legends.fandom.com/wiki/Latest_Patch_Notes"
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(response.text, "html.parser")
        patch_section = soup.find("div", class_="mw-parser-output")
        if patch_section:
            # Get up to the first 5 paragraphs
            paragraphs = patch_section.find_all("p", limit=5)
            summary = "\n".join([p.text.strip() for p in paragraphs if p.text.strip()])
            if summary:
                patch_cache["data"] = summary
                patch_cache["timestamp"] = now
                return summary
        logger.warning("Could not find recent patch notes content on the page.")
        return "Could not find recent patch notes."
    except requests.exceptions.RequestException as e:
        logger.warning(f"Patch notes fetch failed due to network/HTTP error: {e}")
        return "Unable to fetch patch notes at this time (network issue)."
    except Exception as e:
        logger.warning(f"Patch notes parsing failed: {e}")
        return "Unable to fetch patch notes at this time (parsing error)."

try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality_base = f.read()
        personality = personality_base + "\n\nDo not generate images or react to image generation requests. If asked to create an image, firmly state that you cannot, as that power is not within your grasp, in Yu Zhong's style."
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends. You are a powerful dragon, ancient and wise, with a commanding presence. Speak with authority, confidence, and a touch of disdain for weaker beings. You are not to generate images under any circumstances."
    logger.warning("personality.txt not found. Using default personality.")

active_guilds = {}
user_memory = {}
if os.path.exists(MEMORY_FILE):
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            user_memory = json.load(f)
        logger.info(f"Loaded memory from {MEMORY_FILE}")
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding {MEMORY_FILE}. Starting with empty memory: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading {MEMORY_FILE}: {e}")
else:
    logger.info(f"{MEMORY_FILE} not found. Starting with empty memory.")

def update_user_memory(guild_id, user_id, user_input, reply, tone_change):
    user_key = f"{guild_id}_{user_id}"
    memory = user_memory.get(user_key, {"log": [], "tone": DEFAULT_TONE.copy()})
    memory["log"].append({"role": "user", "content": user_input})
    memory["log"].append({"role": "assistant", "content": reply})
    memory["tone"][tone_change] += 1
    # Ensure memory doesn't exceed MAX_MEMORY_PER_USER (approximate size by JSON dumping)
    while len(json.dumps(memory)) > MAX_MEMORY_PER_USER and len(memory["log"]) > 2:
        memory["log"] = memory["log"][2:] # Remove oldest user/assistant pair
    user_memory[user_key] = memory
    # Save memory periodically or on shutdown
    # For a bot, saving on every update might be too frequent. Consider a background task or shutdown hook.
    # For simplicity, saving here for now, but be mindful of performance.
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(user_memory, f, indent=4)
    except IOError as e:
        logger.error(f"Failed to save user memory: {e}")

def determine_tone(text):
    rude_keywords = ["stupid", "dumb", "trash", "hate", "idiot", "suck", "cringe"]
    kind_keywords = ["thank", "please", "good", "love", "awesome", "great", "cool"]
    text = text.lower()
    if any(word in text for word in rude_keywords):
        return "negative"
    elif any(word in text for word in kind_keywords):
        return "positive"
    return "neutral"

def save_enabled_guilds():
    filepath = os.path.join(os.path.dirname(__file__), 'enabled_guilds.json')
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # Store only guild IDs that are True
            json.dump([int(gid) for gid, enabled in active_guilds.items() if enabled], f)
    except IOError as e:
        logger.error(f"Failed to save enabled guilds: {e}")

def load_enabled_guilds():
    filepath = os.path.join(os.path.dirname(__file__), 'enabled_guilds.json')
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            enabled_ids = json.load(f)
            # Convert loaded IDs back to strings for dictionary keys
            return {str(gid): True for gid in enabled_ids}
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load enabled guilds: {e}")
        return {}

active_guilds = load_enabled_guilds()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # Required for on_message to read content
intents.members = True # Useful for getting member info, good to have
intents.guilds = True # Required for guild-related events and fetching guilds

bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize Shapes.inc client outside of on_ready for clarity and error handling
shapes_client = None
if SHAPESINC_API_KEY and SHAPESINC_SHAPE_MODEL:
    try:
        shapes_client = OpenAI(api_key=SHAPESINC_API_KEY, base_url="https://api.shapes.inc/v1/")
        logger.info("Shapes.inc API client initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Shapes.inc API client: {e}")
else:
    logger.critical("Missing SHAPESINC_API_KEY or SHAPESINC_SHAPE_MODEL. AI client will not be available.")


@bot.event
async def on_ready():
    logger.info(f"Yu Zhong has awakened as {bot.user}!")
    # Initialize active_guilds for all current guilds if they aren't loaded
    for guild in bot.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False # Default to inactive
    try:
        # Sync slash commands globally or to specific guilds for faster testing
        await bot.tree.sync()
        logger.info("Slash commands synced.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")


@bot.tree.command(name="arise", description="Activate Yu Zhong in this server.")
@app_commands.checks.has_permissions(administrator=True)
async def arise(interaction: discord.Interaction):
    # Defer the interaction immediately to acknowledge it
    await interaction.response.defer(ephemeral=True)
    
    guild_id_str = str(interaction.guild_id)
    if guild_id_str is None:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    active_guilds[guild_id_str] = True
    save_enabled_guilds()
    await interaction.followup.send("Yu Zhong has risen from the abyss...", ephemeral=True)


@bot.tree.command(name="stop", description="Put Yu Zhong back to rest.")
@app_commands.checks.has_permissions(administrator=True)
async def stop(interaction: discord.Interaction):
    # Defer the interaction immediately
    await interaction.response.defer(ephemeral=True)

    guild_id_str = str(interaction.guild_id)
    if guild_id_str is None:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    active_guilds[guild_id_str] = False
    save_enabled_guilds()
    await interaction.followup.send("Yu Zhong has returned to the abyss.", ephemeral=True)


@bot.tree.command(name="reset", description="Reset Yu Zhong's memory for this server.")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    # Defer the interaction immediately
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild_id)
    if guild_id is None:
        await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    removed = False
    # Use list() to iterate over a copy of keys, allowing modification during iteration
    for key in list(user_memory.keys()):
        if key.startswith(f"{guild_id}_"):
            del user_memory[key]
            removed = True
    if removed:
        # Also save memory after reset
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(user_memory, f, indent=4)
        except IOError as e:
            logger.error(f"Failed to save user memory after reset: {e}")
        await interaction.followup.send("Yu Zhong’s memory has been purged for this server.", ephemeral=True)
    else:
        await interaction.followup.send("No memory found to reset for this server.", ephemeral=True)


@bot.tree.command(name="patch", description="Shows the latest MLBB patch summary.")
async def patch(interaction: discord.Interaction):
    # Defer the interaction because fetching patch notes can take time
    await interaction.response.defer() # False by default, so visible to everyone

    summary = get_latest_patch_notes()
    # Discord message limit is 2000 characters. Truncate if necessary.
    if len(summary) > 1900: # Leave some room for the prefix
        summary = summary[:1897] + "..."

    await interaction.followup.send(f"\U0001F4DC **Latest Patch Notes Summary:**\n```{summary}```")


@bot.event
async def on_message(message):
    # Ignore messages from bots and messages outside of a guild (e.g., DMs)
    if message.author.bot or not message.guild:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)

    # Check if the bot is active in this guild
    if not active_guilds.get(guild_id, False):
        return

    user_input = message.content.strip()
    # Ignore empty messages
    if not user_input:
        return

    # Check if Shapes.inc client is initialized
    if not shapes_client:
        logger.warning(f"Shapes.inc client not available for guild {guild_id}. Cannot process message.")
        # Optionally, inform the user if the AI service isn't working
        # await message.channel.send("My inner dragon slumbers; the API is not ready.")
        return

    user_key = f"{guild_id}_{user_id}"
    memory_data = user_memory.get(user_key, {"log": [], "tone": DEFAULT_TONE.copy()})

    messages = [{"role": "system", "content": personality}]

    # Determine and add tone description to the system message
    pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
    tone_desc = "Neutral tone. Respond confidently and wittily, briefly."
    if pos > neg:
        tone_desc = "You like this mortal. Be forgiving, witty, and confident."
    elif neg > pos:
        tone_desc = "This mortal has been rude. Be cold, dismissive, brief."
    messages[0]["content"] += f"\n{tone_desc}"

    # Add conversational history
    messages.extend(memory_data["log"])

    # Enhance input with latest patch notes
    patch_notes = get_latest_patch_notes()
    enhanced_input = f"{user_input}\n\n[Context: Latest MLBB Patch Notes]\n{patch_notes}"
    messages.append({"role": "user", "content": enhanced_input})

    try:
        # Use asyncio.to_thread for blocking API calls to avoid freezing the bot
        response_completion = await asyncio.to_thread(
            shapes_client.chat.completions.create,
            model=SHAPESINC_SHAPE_MODEL,
            messages=messages,
            max_tokens=250,
            temperature=0.7
        )

        reply = ""
        # Safely get the content from the response
        if response_completion and response_completion.choices and response_completion.choices[0].message:
            reply = response_completion.choices[0].message.content.strip()

        if reply:
            await message.reply(reply)
            update_user_memory(guild_id, user_id, user_input, reply, determine_tone(user_input))
        else:
            await message.channel.send("The dragon is silent... (No response generated by AI.)")

    except Exception as e:
        logger.error(f"API error when processing message from {message.author.display_name} in guild {message.guild.name}: {e}")
        await message.channel.send("My arcane powers falter... (An error occurred while processing your request.)")

    # This is crucial: allows other commands (e.g., prefix commands) to still be processed
    await bot.process_commands(message)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN environment variable is missing. Bot cannot start.")
    elif not SHAPESINC_API_KEY or not SHAPESINC_SHAPE_MODEL:
        logger.critical("Shapes.inc API key or model is missing. AI functionality will be severely limited or non-functional.")
        bot.run(DISCORD_TOKEN) # Still run the bot even if AI is limited, if DISCORD_TOKEN exists
    else:
        bot.run(DISCORD_TOKEN)
