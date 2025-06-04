# bot.py

from keep_alive import keep_alive
keep_alive()

import logging
import os
import json
import discord
from dotenv import load_dotenv
from bardapi import Bard
import requests
from io import BytesIO
import asyncio
import time
from collections import defaultdict

# === Logging ===
logging.basicConfig(level=logging.INFO)

# === Environment Variables ===
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")

# === Constants ===
MAX_MEMORY_PER_USER = 500000  # bytes
MEMORY_FILE = "user_memory.json"
ACTIVE_GUILDS_FILE = "active_guilds.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

# === Load Personality ===
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, darkly witty, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."

# === Load Memory ===
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        user_memory = json.load(f)
else:
    user_memory = {}

if os.path.exists(ACTIVE_GUILDS_FILE):
    with open(ACTIVE_GUILDS_FILE, "r", encoding="utf-8") as f:
        active_guilds = json.load(f)
else:
    active_guilds = {}

last_image_time = defaultdict(float)

# === Discord Setup ===
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)
bard = Bard(token=BARD_TOKEN)


# === Shapes Inc ===

def generate_image(prompt):
    try:
        headers = {"Authorization": f"Bearer {SHAPESINC_API_KEY}"}
        response = requests.post(
            "https://api.shapes.inc/v1/generate",
            headers=headers,
            json={"prompt": prompt}
        )
        if response.status_code == 200:
            data = response.json()
            image_url = data.get("image_url")
            if image_url:
                image_bytes = requests.get(image_url).content
                return BytesIO(image_bytes)
        logging.info(f"Shapes Inc image generation failed: {response.text}")
    except Exception as e:
        logging.info(f"Shapes Inc image error: {e}")
    return None


def describe_image_with_shapesinc(image_url):
    try:
        response = requests.post(
            "https://api.shapes.inc/v1/describe",
            headers={"Authorization": f"Bearer {SHAPESINC_API_KEY}"},
            json={"image_url": image_url}
        )
        if response.status_code == 200:
            return response.json().get("description")
        logging.info(f"Shapes Inc description failed: {response.text}")
    except Exception as e:
        logging.info(f"Shapes Inc describe error: {e}")
    return None


# === Helpers ===

def get_user_key(guild_id, user_id):
    return f"{guild_id}_{user_id}"


def prune_memory(entries):
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


def save_active_guilds():
    with open(ACTIVE_GUILDS_FILE, "w", encoding="utf-8") as f:
        json.dump(active_guilds, f)


# === Events ===

@client.event
async def on_ready():
    logging.info("Yu Zhong has awakened...")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)

    # === Activation Commands ===
    if message.content.lower() == "/arise":
        if not message.author.guild_permissions.administrator:
            await message.reply("Only those with power may awaken the dragon.")
            return
        active_guilds[guild_id] = True
        save_active_guilds()
        await message.reply("Yu Zhong is now watching this realm.")
        return

    if message.content.lower() == "/stop":
        if not message.author.guild_permissions.administrator:
            await message.reply("You lack the authority to silence the dragon.")
            return
        active_guilds[guild_id] = False
        save_active_guilds()
        await message.reply("Dragon falls asleep.")
        return

    if not active_guilds.get(guild_id, False):
        return

    # === Image Command with Cooldown ===
    if message.content.startswith("!imagine "):
        now = time.time()
        if now - last_image_time[message.author.id] < 10:
            await message.channel.send("Your mana needs time to recover.")
            return
        last_image_time[message.author.id] = now

        prompt = message.content[len("!imagine "):].strip()
        await message.channel.send("Summoning image...")
        image_bytes = generate_image(prompt)
        if image_bytes:
            file = discord.File(image_bytes, filename="yu_zhong_creation.png")
            await message.channel.send(file=file)
        else:
            await message.channel.send("I failed to summon the image (lacks mana).")
        return

    user_input = message.content.strip()
    if not user_input:
        return

    # === Handle Attachments ===
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                await message.channel.send("Inspecting your offering...")
                description = describe_image_with_shapesinc(attachment.url)
                if description:
                    user_input = f"The mortal sent an image. It appears to be: {description}"
                else:
                    user_input = "The mortal sent an image, but even dragons cannot comprehend it."
                break

    # === Memory and Prompt Construction ===
    key = get_user_key(guild_id, user_id)
    memory_data = user_memory.get(key, {"log": [], "tone": DEFAULT_TONE.copy()})
    history = "\n".join(memory_data["log"])

    tone_desc = ""
    pos, neg = memory_data["tone"]["positive"], memory_data["tone"]["negative"]
    if pos > neg:
        tone_desc = "You like this mortal. Be a little more forgiving or playful."
    elif neg > pos:
        tone_desc = "This mortal has been rude. Respond colder, more dismissively."
    else:
        tone_desc = "Neutral tone."

    prompt = f"""{personality}

{tone_desc}
Conversation history:
{history}

{message.author.name}: {user_input}
Yu Zhong:"""

    # === Generate Response ===
    try:
        response = bard.get_answer(prompt)
        reply = response.get("content", "").strip() or "The dragon growls... but says nothing."
        await message.reply(reply)

        tone_shift = determine_tone(user_input)
        interaction = f"{message.author.name}: {user_input} | Yu Zhong: {reply}"
        update_user_memory(guild_id, user_id, interaction, tone_shift)

    except Exception as e:
        logging.info(f"API Error: {e}")
        await message.channel.send("Slow down. (Skills On Cooldown)")


@client.event
async def on_member_join(member):
    if member.bot:
        return
    asyncio.create_task(greet_new_member(member))


async def greet_new_member(member):
    prompt = f"""{personality}
Greet the mortal named {member.name} who has entered your domain. Keep it short, mysterious, and charismatic."""
    try:
        response = bard.get_answer(prompt)
        greeting = response.get("content", "").strip()
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
        else:
            logging.info(f"Could not find a channel to greet {member.name} in {member.guild.name}")
    except Exception as e:
        logging.info(f"Greeting Error for {member.name}: {e}")


# === Run Bot ===
client.run(DISCORD_TOKEN)
