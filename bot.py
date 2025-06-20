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
from keep_alive import keep_alive
import random

from openai import OpenAI  # already imported here, no need to re-import inside block

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")
SHAPESINC_MODEL_USERNAME = os.getenv("SHAPESINC_MODEL_USERNAME")

SHAPESINC_SHAPE_MODEL = None
shapes_client = None

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

if SHAPESINC_API_KEY and SHAPESINC_MODEL_USERNAME:
    try:
        # Try to get the list of available models to find the correct model ID
        temp_client = OpenAI(api_key=SHAPESINC_API_KEY,
                             base_url="https://api.shapes.inc/v1/")

        # Get available models
        models_response = temp_client.models.list()
        available_models = [model.id for model in models_response.data]

        # Try to find a model that matches the username or contains it
        SHAPESINC_SHAPE_MODEL = None
        for model_id in available_models:
            if SHAPESINC_MODEL_USERNAME in model_id or model_id == SHAPESINC_MODEL_USERNAME:
                SHAPESINC_SHAPE_MODEL = model_id
                break

        if SHAPESINC_SHAPE_MODEL:
            shapes_client = temp_client
            logger.info(
                f"Shapes.inc API client initialized with model: {SHAPESINC_SHAPE_MODEL}"
            )
            logger.info(f"Available models: {available_models}")
        else:
            logger.critical(
                f"Model '{SHAPESINC_MODEL_USERNAME}' not found. Available models: {available_models}"
            )
            shapes_client = None

    except Exception as e:
        logger.critical(
            f"Failed to initialize Shapes.inc client or list models: {e}")
        shapes_client = None
else:
    logger.critical(
        "Missing SHAPESINC_API_KEY or SHAPESINC_MODEL_USERNAME. AI client will not be available."
    )

MAX_MEMORY_PER_USER = 500000
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('YuZhongBot')

patch_cache = {"data": "", "timestamp": 0}


def get_latest_patch_notes():
    global patch_cache
    now = time.time()
    # Cache for 1 hour (3600 seconds)
    if now - patch_cache["timestamp"] < 3600:
        return patch_cache["data"]
    try:
        # Try multiple URLs for better patch note coverage
        urls_to_try = [
            "https://m.mobilelegends.com/news/articleldetail?newsid=3062931",  # Specific article
            "https://www.mobilelegends.com/en/news",
            "https://mobile-legends.fandom.com/wiki/Patch_Notes",
            "https://m.mobilelegends.com/en/news"
        ]

        for url in urls_to_try:
            try:
                response = requests.get(
                    url,
                    timeout=10,
                    headers={
                        'User-Agent':
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    })
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                # Strategy 1: Look for any text containing patch/update keywords
                all_text = soup.get_text()
                patch_keywords = [
                    "patch", "update", "balance", "hero", "nerf", "buff",
                    "adjustment"
                ]

                # Find sentences containing patch keywords
                sentences = all_text.split('.')
                relevant_sentences = []

                for sentence in sentences:
                    sentence = sentence.strip()
                    if any(keyword in sentence.lower() for keyword in
                           patch_keywords) and len(sentence) > 20:
                        relevant_sentences.append(sentence[:200])
                        if len(relevant_sentences
                               ) >= 5:  # Limit to 5 relevant sentences
                            break

                if relevant_sentences:
                    summary = "Recent patch information:\n" + "\n• ".join(
                        relevant_sentences)
                    patch_cache["data"] = summary
                    patch_cache["timestamp"] = now
                    return summary

                # Strategy 2: Look for specific HTML structures
                news_selectors = [
                    "article", ".news-item", ".news", ".post", ".entry",
                    "[class*='news']", "[class*='patch']", "[class*='update']",
                    "h1, h2, h3, h4", ".title", ".headline"
                ]

                for selector in news_selectors:
                    elements = soup.select(selector)
                    if elements:
                        texts = []
                        for elem in elements[:10]:  # Check first 10 elements
                            text = elem.get_text(strip=True)
                            if text and len(text) > 10 and any(
                                    keyword in text.lower()
                                    for keyword in patch_keywords):
                                texts.append(text[:150])
                                if len(texts) >= 3:
                                    break

                        if texts:
                            summary = f"Latest from {url}:\n" + "\n• ".join(
                                texts)
                            patch_cache["data"] = summary
                            patch_cache["timestamp"] = now
                            return summary

            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch from {url}: {e}")
                continue

        # If all URLs fail, return a generic message
        patch_cache[
            "data"] = "Unable to fetch current patch notes. The Land of Dawn's secrets remain hidden for now."
        patch_cache["timestamp"] = now
        return patch_cache["data"]
    except requests.exceptions.RequestException as e:
        logger.warning(
            f"Patch notes fetch failed due to network/HTTP error: {e}")
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
        logger.error(
            f"Error decoding {MEMORY_FILE}. Starting with empty memory: {e}")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while loading {MEMORY_FILE}: {e}")
else:
    logger.info(f"{MEMORY_FILE} not found. Starting with empty memory.")


def update_user_memory(guild_id, user_id, user_input, reply, tone_change):
    user_key = f"{guild_id}_{user_id}"
    memory = user_memory.get(user_key, {
        "log": [],
        "tone": DEFAULT_TONE.copy()
    })
    memory["log"].append({"role": "user", "content": user_input})
    memory["log"].append({"role": "assistant", "content": reply})
    memory["tone"][tone_change] += 1
    # Ensure memory doesn't exceed MAX_MEMORY_PER_USER (approximate size by JSON dumping)
    while len(json.dumps(memory)) > MAX_MEMORY_PER_USER and len(
            memory["log"]) > 2:
        memory["log"] = memory["log"][2:]  # Remove oldest user/assistant pair
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
    rude_keywords = [
        "stupid", "dumb", "trash", "hate", "idiot", "suck", "cringe"
    ]
    kind_keywords = [
        "thank", "please", "good", "love", "awesome", "great", "cool"
    ]
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
            json.dump([
                int(gid) for gid, enabled in active_guilds.items() if enabled
            ], f)
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
intents.message_content = True  # Required for on_message to read content
intents.members = True  # Useful for getting member info, good to have
intents.guilds = True  # Required for guild-related events and fetching guilds

bot = commands.Bot(command_prefix="!", intents=intents)

# Shapes.inc client is initialized above with model username resolution


@bot.event
async def on_ready():
    logger.info(f"Yu Zhong has awakened as {bot.user}!")
    # Initialize active_guilds for all current guilds if they aren't loaded
    for guild in bot.guilds:
        if str(guild.id) not in active_guilds:
            active_guilds[str(guild.id)] = False  # Default to inactive
    try:
        # Sync slash commands globally or to specific guilds for faster testing
        await bot.tree.sync()
        logger.info("Slash commands synced.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")


async def safe_followup_send(interaction,
                             message,
                             ephemeral=False,
                             max_retries=3):
    """Safely send a followup message with retry logic"""
    for attempt in range(max_retries):
        try:
            await interaction.followup.send(message, ephemeral=ephemeral)
            return
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                wait_time = 2**attempt + random.uniform(0, 1)
                logger.warning(
                    f"Rate limited, waiting {wait_time:.2f}s before retry {attempt + 1}"
                )
                await asyncio.sleep(wait_time)
            else:
                raise e
    logger.error(f"Failed to send message after {max_retries} attempts")


@bot.tree.command(name="arise",
                  description="Activate Yu Zhong in this server.")
@app_commands.checks.has_permissions(administrator=True)
async def arise(interaction: discord.Interaction):
    # Defer the interaction immediately to acknowledge it
    await interaction.response.defer(ephemeral=True)

    guild_id_str = str(interaction.guild_id)
    if guild_id_str is None:
        await safe_followup_send(interaction,
                                 "This command can only be used in a server.",
                                 ephemeral=True)
        return

    active_guilds[guild_id_str] = True
    save_enabled_guilds()
    await safe_followup_send(interaction,
                             "Yu Zhong has risen from the abyss...",
                             ephemeral=True)


@bot.tree.command(name="stop", description="Put Yu Zhong back to rest.")
@app_commands.checks.has_permissions(administrator=True)
async def stop(interaction: discord.Interaction):
    # Defer the interaction immediately
    await interaction.response.defer(ephemeral=True)

    guild_id_str = str(interaction.guild_id)
    if guild_id_str is None:
        await safe_followup_send(interaction,
                                 "This command can only be used in a server.",
                                 ephemeral=True)
        return

    active_guilds[guild_id_str] = False
    save_enabled_guilds()
    await safe_followup_send(interaction,
                             "Yu Zhong has returned to the abyss.",
                             ephemeral=True)


# Define the memory directory
MEMORY_DIR = "user_memories"


@bot.tree.command(name="reset",
                  description="Reset Yu Zhong's memory for this server.")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    # Defer the interaction immediately
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild_id)
    if guild_id is None:
        await interaction.followup.send(
            "This command can only be used in a server.", ephemeral=True)
        return

    removed = False

    # Remove files for users in this guild
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
    if os.path.exists(MEMORY_DIR):
        for filename in os.listdir(MEMORY_DIR):
            if filename.startswith(f"user_{guild_id}_") and filename.endswith(
                    ".json"):
                try:
                    os.remove(os.path.join(MEMORY_DIR, filename))
                    removed = True
                except OSError as e:
                    logger.error(
                        f"Failed to remove memory file {filename}: {e}")

    # Also clear from memory cache
    for key in list(user_memory.keys()):
        if key.startswith(f"{guild_id}_"):
            del user_memory[key]
            removed = True

    if removed:
        await safe_followup_send(
            interaction,
            "Yu Zhong's memory has been purged for this server.",
            ephemeral=True)
    else:
        await safe_followup_send(interaction,
                                 "No memory found to reset for this server.",
                                 ephemeral=True)


@bot.tree.command(name="patch",
                  description="Shows the latest MLBB patch summary.")
async def patch(interaction: discord.Interaction):
    # Defer the interaction because fetching patch notes can take time
    await interaction.response.defer(
    )  # False by default, so visible to everyone

    summary = get_latest_patch_notes()
    # Discord message limit is 2000 characters. Truncate if necessary.
    if len(summary) > 1900:  # Leave some room for the prefix
        summary = summary[:1897] + "..."

    await safe_followup_send(
        interaction,
        f"\U0001F4DC **Latest Patch Notes Summary:**\n```{summary}```")


@bot.tree.command(
    name="search",
    description="Search for information with Yu Zhong's knowledge.")
async def search(interaction: discord.Interaction, query: str):
    # Defer the interaction because AI processing can take time
    await interaction.response.defer()

    # Check if Shapes.inc client is initialized
    if not shapes_client:
        await interaction.followup.send(
            "My arcane powers are dormant... (AI service unavailable.)")
        return

    try:
        # Get patch notes for context
        patch_notes = get_latest_patch_notes()
        user_display_name = interaction.user.display_name

        # Create search-specific system message
        search_personality = f"{personality}\n\nYou are being asked to search for information about: '{query}'. Provide helpful, accurate information while maintaining your Yu Zhong personality. Be informative but keep your characteristic wit and confidence."

        messages = [{
            "role": "system",
            "content": search_personality
        }, {
            "role":
            "user",
            "content":
            f"Search for information about: {query}\n\n[Context: Latest MLBB Patch Notes]\n{patch_notes}\n\n[User Info: Address the user as '{user_display_name}' in your response, not by any model or API names]"
        }]

        # Use asyncio.to_thread for blocking API calls
        response_completion = await asyncio.to_thread(
            shapes_client.chat.completions.create,
            model=SHAPESINC_SHAPE_MODEL,
            messages=messages,
            max_tokens=400,  # Slightly more tokens for search results
            temperature=0.7)

        reply = ""
        if response_completion and response_completion.choices and response_completion.choices[
                0].message:
            reply = response_completion.choices[0].message.content.strip()

        if reply:
            # Discord message limit handling
            if len(reply) > 1900:
                reply = reply[:1897] + "..."
            await safe_followup_send(
                interaction, f"🔍 **Search Results for '{query}':**\n\n{reply}")
        else:
            await safe_followup_send(
                interaction,
                "My search through the arcane knowledge yields nothing... (No response generated.)"
            )

    except Exception as e:
        logger.error(
            f"Search command error for query '{query}' by {interaction.user.display_name}: {e}"
        )
        await safe_followup_send(
            interaction,
            "The search spell backfired... (An error occurred while processing your search.)"
        )


@bot.event
async def on_message(message):
    # Ignore messages from bots and messages outside of a guild (e.g., DMs)
    if message.author.bot or not message.guild:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)

    # Check if bot is mentioned
    bot_mentioned = bot.user in message.mentions

    # Check if the bot is active in this guild OR if the bot is mentioned
    if not active_guilds.get(guild_id, False) and not bot_mentioned:
        # Still process commands even if bot is not active
        await bot.process_commands(message)
        return

    user_input = message.content.strip()

    # Check for images in the message
    has_images = len(message.attachments) > 0 and any(
        attachment.content_type
        and attachment.content_type.startswith('image/')
        for attachment in message.attachments)

    # Ignore empty messages unless there are images
    if not user_input and not has_images:
        await bot.process_commands(message)
        return

    # Check if Shapes.inc client is initialized
    if not shapes_client:
        logger.warning(
            f"Shapes.inc client not available for guild {guild_id}. Cannot process message."
        )
        # Optionally, inform the user if the AI service isn't working
        # await message.channel.send("My inner dragon slumbers; the API is not ready.")
        return

    user_key = f"{guild_id}_{user_id}"
    memory_data = user_memory.get(user_key, {
        "log": [],
        "tone": DEFAULT_TONE.copy()
    })

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

    # Enhance input with latest patch notes and user context
    patch_notes = get_latest_patch_notes()
    user_display_name = message.author.display_name

    # Prepare the user message content
    if has_images:
        # For images, create a message with both text and image content
        image_urls = [
            attachment.url for attachment in message.attachments
            if attachment.content_type
            and attachment.content_type.startswith('image/')
        ]

        # Create content array for vision model
        content = []

        # Add text if present
        if user_input:
            enhanced_input = f"{user_input}\n\n[Context: Latest MLBB Patch Notes]\n{patch_notes}\n\n[User Info: Address the user as '{user_display_name}' in your response, not by any model or API names]"
            content.append({"type": "text", "text": enhanced_input})
        else:
            # Default text for image-only messages
            enhanced_input = f"Describe what you see in this image with your characteristic Yu Zhong personality.\n\n[Context: Latest MLBB Patch Notes]\n{patch_notes}\n\n[User Info: Address the user as '{user_display_name}' in your response, not by any model or API names]"
            content.append({"type": "text", "text": enhanced_input})

        # Add images
        for image_url in image_urls:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            })

        messages.append({"role": "user", "content": content})
    else:
        # Text-only message (original behavior)
        enhanced_input = f"{user_input}\n\n[Context: Latest MLBB Patch Notes]\n{patch_notes}\n\n[User Info: Address the user as '{user_display_name}' in your response, not by any model or API names]"
        messages.append({"role": "user", "content": enhanced_input})

    try:
        # Use asyncio.to_thread for blocking API calls to avoid freezing the bot
        response_completion = await asyncio.to_thread(
            shapes_client.chat.completions.create,
            model=SHAPESINC_SHAPE_MODEL,
            messages=messages,
            max_tokens=250,
            temperature=0.7)

        reply = ""
        # Safely get the content from the response
        if response_completion and response_completion.choices and response_completion.choices[
                0].message:
            reply = response_completion.choices[0].message.content.strip()

        if reply:
            await message.reply(reply)
            tone_change = determine_tone(user_input)
            if tone_change == "neutral":
                tone_change = "positive"  # Default neutral to positive for memory
            update_user_memory(guild_id, user_id, user_input, reply,
                               tone_change)
        else:
            await message.channel.send(
                "The dragon is silent... (No response generated by AI.)")

    except Exception as e:
        logger.error(
            f"API error when processing message from {message.author.display_name} in guild {message.guild.name}: {e}"
        )
        await message.channel.send(
            "My arcane powers falter... (An error occurred while processing your request.)"
        )

    # This is crucial: allows other commands (e.g., prefix commands) to still be processed
    await bot.process_commands(message)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical(
            "DISCORD_TOKEN environment variable is missing. Bot cannot start.")
    else:
        # Start the keep-alive web server
        keep_alive()
        logger.info("Keep-alive web server started on port 5000")

        if not SHAPESINC_API_KEY or not SHAPESINC_SHAPE_MODEL:
            logger.critical(
                "Shapes.inc API key or model is missing. AI functionality will be severely limited or non-functional."
            )

        bot.run(DISCORD_TOKEN)
