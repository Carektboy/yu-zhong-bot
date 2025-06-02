import keep_alive
keep_alive.keep_alive()

import discord
import os
import json
from dotenv import load_dotenv
import requests
from io import BytesIO
from bardapi import Bard

# Load tokens
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HF_TOKEN")

# Load or default personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    personality = "Charming, Charismatic, morally ambiguous, witty and chaotic. Yu Zhong is a powerful, ancient dragon who speaks confidently with wit and menace. His words are short, impactful, and in-character as the MLBB hero. He never refers to himself in the third person or uses narration. He simply *is* Yu Zhong."

# Load user memory or create new
if os.path.exists("user_memory.json"):
    with open("user_memory.json", "r", encoding="utf-8") as f:
        user_memory = json.load(f)
else:
    user_memory = {}

# Image generation
def generate_image(prompt):
    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2",
            headers={"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"},
            json={"inputs": prompt}
        )
        if response.status_code == 200:
            return BytesIO(response.content)
        else:
            print("Hugging Face Error:", response.text)
            return None
    except Exception as e:
        print("Image Gen Error:", e)
        return None

# Discord setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)
bard = Bard(token=BARD_TOKEN)

@client.event
async def on_ready():
    print("Yu Zhong has awakened...")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    user_input = message.content.strip()

    if not user_input:
        return

    # Handle !imagine command
    if user_input.startswith("!imagine "):
        prompt = user_input[len("!imagine "):].strip()
        await message.channel.send("🎨 Summoning image from the void...")
        image_bytes = generate_image(prompt)
        if image_bytes:
            await message.channel.send(file=discord.File(image_bytes, filename="yu_zhong_creation.png"))
        else:
            await message.channel.send("I failed to summon the image...")
        return

    # Load history memory if any
    history = user_memory.get(user_id, "")

    # Build prompt — without Mortal/Yu Zhong format
    prompt = (
        f"{personality}\n"
        f"Context about this mortal: {history}\n\n"
        f"The mortal said: \"{user_input}\"\n"
        f"Respond naturally as Yu Zhong would — no names or formatting."
    )

    try:
        response = bard.get_answer(prompt)
        reply = response.get("content", "").strip()
        await message.reply(reply or "The dragon is silent...")

        # Log user interaction
        new_entry = f"{message.author.name} said: {user_input} | Yu Zhong replied: {reply}"
        user_memory[user_id] = (history + "\n" + new_entry)[-1000:]  # keep memory short

        with open("user_memory.json", "w", encoding="utf-8") as f:
            json.dump(user_memory, f, indent=2)

    except Exception as e:
        print("API Error:", e)
        await message.channel.send("Yu Zhong is... disturbed. (API error)")

@client.event
async def on_member_join(member):
    if member.bot:
        return

    prompt = (
        f"{personality}\n"
        f"Greet the new user '{member.name}' as Yu Zhong would — charismatic, subtly menacing, and witty. Short and in-character. Don't mention 'Mortal' or 'Yu Zhong'."
    )

    try:
        response = bard.get_answer(prompt)
        greeting = response.get("content", "").strip()

        channel = next((ch for ch in member.guild.text_channels if ch.permissions_for(member.guild.me).send_messages), None)
        if channel:
            await channel.send(greeting)
    except Exception as e:
        print("Greeting Error:", str(e))

client.run(DISCORD_TOKEN)
