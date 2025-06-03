import keep_alive
keep_alive.keep_alive()

import os
import json
import discord
from dotenv import load_dotenv
from bardapi import Bard
import requests
from io import BytesIO

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HF_TOKEN")

MAX_MEMORY_PER_USER = 500000 # bytes limit per user per guild
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, darkly witty, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."


active_guilds = {}
# Load or initialize memory
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        user_memory = json.load(f)
else:
    user_memory = {}


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)
bard = Bard(token=BARD_TOKEN)


def generate_image(prompt):
    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2",
            headers={"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"},
            json={"inputs": prompt}
        )
        if response.status_code == 200:
            # Check if the content type is image before returning
            content_type = response.headers.get('Content-Type', '')
            if 'image' in content_type:
                return BytesIO(response.content)
            else:
                print(f"Hugging Face Error: Response was not an image (Content-Type: {content_type}). Status Code: {response.status_code}, Response: {response.text}")
                return None
        elif response.status_code == 503: # Common for model loading
            print(f"Hugging Face Error (503 Service Unavailable): Model might be loading. Try again shortly. Response: {response.text}")
            return None
        elif response.status_code == 429: # Rate limit
            print(f"Hugging Face Error (429 Too Many Requests): You are being rate-limited. Wait before trying again. Response: {response.text}")
            return None
        else:
            print(f"Hugging Face Error: Status Code: {response.status_code}, Response: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network or Request Error during image generation: {e}")
        return None
    except Exception as e:
        print(f"Unexpected Error during image generation: {e}")
        return None


def get_user_key(guild_id, user_id):
    return f"{guild_id}_{user_id}"


def prune_memory(entries):
    # Prune old entries if memory size exceeds limit
    text = "\n".join(entries)
    while len(text.encode('utf-8')) > MAX_MEMORY_PER_USER:
        entries = entries[1:]
        text = "\n".join(entries)
    return entries


def update_user_memory(guild_id, user_id, log, tone_shift):
    key = get_user_key(guild_id, user_id)

    if key not in user_memory:
        user_memory[key] = {"log": [], "tone": DEFAULT_TONE.copy()}

    user_memory[key]["log"].append(log)
    user_memory[key]["log"] = prune_memory(user_memory[key]["log"])

    if tone_shift == "positive":
        user_memory[key]["tone"]["positive"] += 1
    elif tone_shift == "negative":
        user_memory[key]["tone"]["negative"] += 1

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(user_memory, f, indent=2)


def determine_tone(user_text):
    lowered = user_text.lower()
    if any(word in lowered for word in ["thanks", "cool", "great", "good bot", "nice"]):
        return "positive"
    if any(word in lowered for word in ["stupid", "idiot", "dumb", "shut up"]):
        return "negative"
    return None


@client.event
async def on_ready():
    print("Yu Zhong has awakened...")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)

    # Handle activate/deactivate
    if message.content.lower() == "/activate":
        if not message.author.guild_permissions.administrator:
            await message.reply("Only those with power may awaken the dragon.")
            return
        active_guilds[str(message.guild.id)] = True
        await message.reply("Yu Zhong is now watching this realm.")
        return

    if message.content.lower() == "/deactivate":
        if not message.author.guild_permissions.administrator:
            await message.reply("You lack the authority to silence the dragon.")
            return
        active_guilds[str(message.guild.id)] = False
        await message.reply("Yu Zhong returns to slumber.")
        return

    # Ignore messages if not activated
    if not active_guilds.get(guild_id, False):
        return

    if message.content.startswith("!imagine "):
        prompt = message.content[len("!imagine "):].strip()
        await message.channel.send("🎨 Summoning image from the void...")
        image_bytes = generate_image(prompt)
        if image_bytes:
            file = discord.File(image_bytes, filename="yu_zhong_creation.png")
            await message.channel.send(file=file)
        else:
            await message.channel.send("I failed to summon the image...")
        return

    user_input = message.content.strip()
    if not user
