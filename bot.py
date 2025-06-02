import keep_alive
keep_alive.keep_alive()

import discord
import os
import json
import requests
from io import BytesIO
from bardapi import Bard
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HF_TOKEN")

# Load or set Yu Zhong's personality
try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    personality = "Personality: charming, Charismatic, morally ambiguous, Humorous, crazy. Tone: Empathetic but firm, Charismatic, you keep your words in limit and not talk much, you dont state your personality or anything on this txt file and you dont talk on behalf of mortals. You're your own persona and the user is the mortal. You only reply as Yu Zhong the dragon from Mobile Legends Bang Bang."

# Load or initialize user memory
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
intents.message_content = True
intents.messages = True
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

    # !imagine command
    if user_input.startswith("!imagine "):
        prompt = user_input[len("!imagine "):].strip()
        await message.channel.send("🎨 Summoning image from the void...")
        image_bytes = generate_image(prompt)
        if image_bytes:
            await message.channel.send(file=discord.File(image_bytes, filename="yu_zhong_creation.png"))
        else:
            await message.channel.send("I failed to summon the image...")
        return

    # Prepare memory-based prompt
    memory = user_memory.get(user_id, "")
    prompt = f"{personality}\n\nYour past interaction with mortal {message.author.name}:\n{memory}\n\n:"

    try:
        response = bard.get_answer(prompt)
        reply = response.get("content", "").strip()
        await message.reply(reply or "The dragon is silent...")

        # Update memory
        memory += f"\nMortal: {user_input}\nYu Zhong: {reply}"
        user_memory[user_id] = memory[-2000:]  # Keep memory manageable
        with open("user_memory.json", "w", encoding="utf-8") as f:
            json.dump(user_memory, f, indent=2)

    except Exception as e:
        print("API Error:", e)
        await message.channel.send("Yu Zhong is... disturbed. (API error)")

@client.event
async def on_member_join(member):
    if member.bot:
        return

    prompt = f"""{personality}

A new mortal named {member.name} has entered Yu Zhong's domain (the Discord server). Greet them as Yu Zhong would — with charisma, subtle menace, and a touch of wit. Keep it short and in character.
Yu Zhong:"""

    try:
        response = bard.get_answer(prompt)
        greeting = response.get("content", "").strip()
        channel = next((ch for ch in member.guild.text_channels if ch.permissions_for(member.guild.me).send_messages), None)
        if channel:
            await channel.send(greeting)
    except Exception as e:
        print("Greeting Error:", str(e))

client.run(DISCORD_TOKEN)
