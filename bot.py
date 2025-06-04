import keep_alive
keep_alive.keep_alive()

import logging
logging.basicConfig(level=logging.INFO)

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
SHAPESINC_API_KEY = os.getenv("SHAPESINC_API_KEY")

MAX_MEMORY_PER_USER = 500000  # bytes limit per user per guild
MEMORY_FILE = "user_memory.json"
DEFAULT_TONE = {"positive": 0, "negative": 0}

try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    personality = "You are Yu Zhong from Mobile Legends. You're charismatic, darkly witty, slightly unhinged, and speak confidently in short phrases. You respond like a user, not like a bot."

active_guilds = {}
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
        headers = {
            "Authorization": f"Bearer {SHAPESINC_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {"prompt": prompt}

        response = requests.post(
            "https://api.shapes.inc/v1/shapes/yuzhong-eqf1/infer",
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            json_data = response.json()
            image_url = json_data.get("image_url")
            if image_url:
                image_bytes = requests.get(image_url).content
                return BytesIO(image_bytes)
            else:
                logging.info("No image URL in response: %s", json_data)
        else:
            logging.info("Shapes Inc image generation failed: %s", response.text)

    except Exception as e:
        logging.info("Shapes Inc image generation error: %s", str(e))

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
        logging.info("Shapes Inc description failed: %s", response.text)
    except Exception as e:
        logging.info("Shapes Inc describe error: %s", e)
    return None

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

@client.event
async def on_ready():
    logging.info("Yu Zhong has awakened...")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)

    if message.content.lower() == "/arise":
        if not message.author.guild_permissions.administrator:
            await message.reply("Only those with power may awaken the dragon.")
            return
        active_guilds[guild_id] = True
        await message.reply("Yu Zhong is now watching this realm.")
        return

    if message.content.lower() == "/stop":
        if not message.author.guild_permissions.administrator:
            await message.reply("You lack the authority to silence the dragon.")
            return
        active_guilds[guild_id] = False
        await message.reply("Dragon falls asleep")
        return

    if not active_guilds.get(guild_id, False):
        return

    if message.content.startswith("!imagine "):
        prompt = message.content[len("!imagine "):].strip()
        await message.channel.send("Summoning image.")
        image_bytes = generate_image(prompt)
        if image_bytes:
            file = discord.File(image_bytes, filename="yu_zhong_creation.png")
            await message.channel.send(file=file)
        else:
            await message.channel.send("I failed to summon the image (lacks mana)")
        return

    user_input = message.content.strip()
    if not user_input:
        return

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

    try:
        response = bard.get_answer(prompt)
        reply = response.get("content", "").strip()
        await message.reply(reply or "The dragon is silent...")

        tone_shift = determine_tone(user_input)
        interaction = f"{message.author.name}: {user_input} | Yu Zhong: {reply}"
        update_user_memory(guild_id, user_id, interaction, tone_shift)

    except Exception as e:
        logging.info("API Error: %s", e)
        await message.channel.send("Slow down. (Skills On Cooldown)")

@client.event
async def on_member_join(member):
    if member.bot:
        return

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
            logging.info(f"Could not find a channel to send greeting to {member.name} in guild {member.guild.name}")
    except Exception as e:
        logging.info(f"Greeting Error for {member.name}: {e}")

client.run(DISCORD_TOKEN)
