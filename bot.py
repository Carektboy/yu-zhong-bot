import keep_alive
keep_alive.keep_alive()

import logging
import os
import json
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import asyncio
# import aiohttp # Not needed for Shapes.inc API call
# from io import BytesIO # Not needed for Shapes.inc API call

# NEW: Import OpenAI client
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# CHANGED: Replaced BARD_TOKEN with SHAPESINC_API_KEY
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")
# NEW: Environment variable for the specific Shapes.inc model (e.g., shapesinc/YOUR_SHAPE_USERNAME)
SHAPESINC_SHAPE_MODEL = os.getenv("SHAPESINC_SHAPE_MODEL")

# --- Configuration ---
MAX_MEMORY_PER_USER = 500000  # bytes limit per user per guild
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

# Load personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality_base = f.read()
        personality = personality_base + "\n\nDo not generate images or react to image generation requests. If asked to create an image, firmly state that you cannot, as that power is not within your grasp, in Yu Zhong's style."
except FileNotFoundError:
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

# Shapes.inc API Client (CHANGED from bard_session)
shapes_client = None

# --- Helper Functions ---

# CHANGED: The update_user_memory function now expects a more structured interaction to save
# to memory, specifically for the OpenAI-compatible API roles.
# It will save the user's input and the bot's reply separately for better context re-creation.
def update_user_memory(guild_id, user_id, user_message, bot_reply, tone_shift=None):
    user_key = f"{guild_id}_{user_id}"
    if user_key not in user_memory:
        # Memory log will now store pairs for user and assistant
        user_memory[user_key] = {"log": [], "tone": DEFAULT_TONE.copy()}

    # Store user and bot messages as separate entries or as a tuple/dict if more complex memory needed
    # For simplicity here, we'll store them as separate items in the log list
    # The parsing logic in on_message will then reconstruct the roles
    user_memory[user_key]["log"].append({"role": "user", "content": user_message})
    user_memory[user_key]["log"].append({"role": "assistant", "content": bot_reply})
    
    user_memory[user_key]["log"] = prune_memory(user_memory[user_key]["log"])

    if tone_shift:
        if tone_shift == "positive":
            user_memory[user_key]["tone"]["positive"] += 1
        elif tone_shift == "negative":
            user_memory[user_key]["tone"]["negative"] += 1
        user_memory[user_key]["tone"]["positive"] = min(user_memory[user_key]["tone"]["positive"], 10)
        user_memory[user_key]["tone"]["negative"] = min(user_memory[user_key]["tone"]["negative"], 10)

def get_user_key(guild_id, user_id):
    return f"{guild_id}_{user_id}"

# CHANGED: Prune memory function needs to understand the new log structure (list of dicts)
def prune_memory(entries):
    # Calculate approximate size of messages list
    # Sum of length of 'content' strings for a rough estimate
    current_size = sum(len(entry.get("content", "").encode('utf-8')) for entry in entries)
    
    # Keep removing oldest messages (pairs of user/assistant) until under limit
    while current_size > MAX_MEMORY_PER_USER and len(entries) > 2: # Keep at least system + 1 turn
        # Remove the oldest user and assistant message pair
        if entries[0].get("role") == "user" and entries[1].get("role") == "assistant":
            removed_user_msg = entries.pop(0)
            removed_assistant_msg = entries.pop(0)
            current_size -= (len(removed_user_msg.get("content", "").encode('utf-8')) + 
                             len(removed_assistant_msg.get("content", "").encode('utf-8')))
        else:
            # If history is malformed, just remove the oldest entry
            removed_entry = entries.pop(0)
            current_size -= len(removed_entry.get("content", "").encode('utf-8'))
        
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
    global shapes_client # CHANGED from bard_session
    logger.info(f"Yu Zhong has awakened as {bot.user}!")

    for guild in bot.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False
    logger.info(f"Bot active status initialized: {active_guilds}")

    bot.loop.create_task(periodic_memory_save())

    logger.info("Initializing Shapes.inc API...")
    if SHAPESINC_API_KEY and SHAPESINC_SHAPE_MODEL: # NEW: Check for model too
        try:
            # NEW: Initialize OpenAI client pointing to Shapes.inc API
            shapes_client = OpenAI(
                api_key=SHAPESINC_API_KEY,
                base_url="https://api.shapes.inc/v1/"
            )
            logger.info("Shapes.inc API initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize Shapes.inc API: {e}. Bot will not respond to general messages.")
            shapes_client = None
    else:
        logger.critical("SHAPESINC_API_KEY or SHAPESINC_SHAPE_MODEL is not set. Shapes.inc API will not function.")
        shapes_client = None

    # Sync slash commands
    try:
        await bot.tree.sync() # Sync global commands
        logger.info("Global slash commands synced successfully via bot.tree.sync().")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

# --- Application Commands (Slash Commands) ---
# (These remain largely unchanged as they don't interact with Bard/Shapes.inc API directly)

@bot.tree.command(name="arise", description="Awakens Yu Zhong in this realm.")
@app_commands.checks.has_permissions(administrator=True)
async def arise(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    active_guilds[guild_id] = True
    await interaction.response.send_message("Yu Zhong is now watching this realm. Beware.")
    logger.info(f"Bot activated in guild: {interaction.guild.name}")

@bot.tree.command(name="stop", description="Silences Yu Zhong in this realm.")
@app_commands.checks.has_permissions(administrator=True)
async def stop(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    active_guilds[guild_id] = False
    await interaction.response.send_message("Dragon falls asleep. For now.")
    logger.info(f"Bot deactivated in guild: {interaction.guild.name}")

@bot.tree.command(name="reset_memory", description="Resets a user's memory (admin only) or your own.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="The user whose memory to reset (defaults to yourself).")
async def reset_memory(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user_to_reset = interaction.user
        reset_message = "Your personal memories of Yu Zhong have been purged. Speak again, mortal, as if for the first time."
    else:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You lack the authority to manipulate other mortals' memories.", ephemeral=True)
            return
        user_to_reset = user
        reset_message = f"{user.mention}'s memories of Yu Zhong have been purged by command."

    user_key = get_user_key(str(interaction.guild.id), str(user_to_reset.id))
    if user_key in user_memory:
        del user_memory[user_key]
        await save_user_memory_async()
        logger.info(f"Memory for {user_to_reset.name} ({user_key}) reset by {interaction.user.name}.")
        await interaction.response.send_message(reset_message)
    else:
        await interaction.response.send_message(f"Mortal {user_to_reset.mention} had no memories to purge.", ephemeral=True)


# --- on_message handling (for general AI replies) ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    user_key = get_user_key(guild_id, user_id)

    if not active_guilds.get(guild_id, False):
        return

    user_input = message.content.strip()
    if not user_input:
        return

    # CHANGED: Check if Shapes.inc client is initialized
    if not shapes_client:
        await message.channel.send("My voice is currently silenced. Shapes.inc API failed to initialize.", reference=message)
        logger.error("Shapes.inc API client is not initialized. Cannot respond to general message.")
        return

    memory_data = user_memory.get(user_key, {"log": [], "tone": DEFAULT_TONE.copy()})
    
    # NEW: Construct messages array for OpenAI-compatible API
    messages = [
        {"role": "system", "content": personality} # System message for personality
    ]

    tone_desc = ""
    pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
    if pos > neg:
        tone_desc = "You like this mortal. Be a little more forgiving or playful, yet still confident and darkly witty. Respond briefly."
    elif neg > pos:
        tone_desc = "This mortal has been rude. Respond colder, more dismissively, perhaps with a hint of menace. Keep it concise."
    else:
        tone_desc = "Neutral tone. Respond confidently and wittily, briefly."
    
    # Add tone description to system message
    messages[0]["content"] += f"\n{tone_desc}"

    # NEW: Add historical messages from memory to the messages list
    # The 'log' now directly stores [{"role": "user", "content": "..."}] and [{"role": "assistant", "content": "..."}]
    messages.extend(memory_data["log"])

    # Add the current user input
    messages.append({"role": "user", "content": user_input})

    try:
        logger.info(f"Sending prompt to Shapes.inc API for {message.author.name} (tone: {tone_desc.split('.')[0]})...")
        
        # NEW: Call Shapes.inc API using the OpenAI client
        response_completion = await asyncio.to_thread(
            shapes_client.chat.completions.create,
            model=SHAPESINC_SHAPE_MODEL, # Use the model/shape you configured
            messages=messages,
            max_tokens=250, # Adjust as needed
            temperature=0.7 # Adjust as needed for creativity
        )

        # Access the content from the response
        reply = response_completion.choices[0].message.content.strip()

        if reply:
            await message.reply(reply)
            logger.info(f"Replied to {message.author.name}: {reply[:100]}...")

            tone_shift = determine_tone(user_input)
            # CHANGED: update_user_memory now takes user_message and bot_reply separately
            update_user_memory(guild_id, user_id, user_input, reply, tone_shift)
        else:
            await message.channel.send("The dragon is silent... my thoughts are not yet formed by Shapes.inc.", reference=message)
            logger.warning(f"Shapes.inc API returned empty response for {message.author.name}.")

    except Exception as e:
        logger.error(f"Shapes.inc API Error for {message.author.name}: {e}")
        await message.channel.send("My arcane powers falter... (Skills on cooldown). Try again later, if you dare.", reference=message)
        # CHANGED: update_user_memory now takes user_message and bot_reply (empty string for error) separately
        update_user_memory(guild_id, user_id, user_input, f"API Error - {e}", "negative") # Store error in memory for debugging

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    guild_id = str(member.guild.id)
    if not active_guilds.get(guild_id, False):
        logger.info(f"Bot inactive in {member.guild.name}. Skipping greeting for {member.name}.")
        return

    # CHANGED: Check shapes_client
    if not shapes_client:
        logger.warning(f"Shapes.inc API not initialized. Skipping greeting for {member.name}.")
        return

    logger.info(f"Greeting new member {member.name} in {member.guild.name}...")
    # NEW: Construct messages for greeting
    greeting_messages = [
        {"role": "system", "content": personality},
        {"role": "user", "content": f"Greet the mortal named {member.name} who has just stepped into your dominion. Keep the greeting short, mysterious, and charismatic, in the style of Yu Zhong."}
    ]
    
    try:
        # NEW: Call Shapes.inc API for greeting
        greeting_response_completion = await asyncio.to_thread(
            shapes_client.chat.completions.create,
            model=SHAPESINC_SHAPE_MODEL,
            messages=greeting_messages,
            max_tokens=100, # Shorter max_tokens for greetings
            temperature=0.8 # Slightly more creative for greetings
        )
        greeting = greeting_response_completion.choices[0].message.content.strip()

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
            logger.warning(f"Shapes.inc API returned empty greeting for {member.name}.")
    except Exception as e:
        logger.error(f"Error generating or sending greeting for {member.name}: {e}")


# --- Run the bot ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN is not set in .env. Please check your .env file.")
    # CHANGED: Check for Shapes.inc API key and model
    if not SHAPESINC_API_KEY:
        logger.critical("SHAPESINC_API_KEY is not set in .env. Shapes.inc API will not function.")
    if not SHAPESINC_SHAPE_MODEL:
        logger.critical("SHAPESINC_SHAPE_MODEL is not set in .env. Shapes.inc API will not function.")

    bot.run(DISCORD_TOKEN)
