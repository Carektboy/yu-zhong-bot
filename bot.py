import keep_alive
keep_alive.keep_alive()


from bardapi import Bard
import discord
import os
import json
from dotenv import load_dotenv
import requests
from io import BytesIO


load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HF_TOKEN")


try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    # Set a default personality if the file isn't found
    personality = "Personality: charming, Charismatic, morally ambiguous, Humorous, crazy. Tone: Empathetic but firm, Charismatic, you keep your words in limit and not talk much, you dont state your personality or anything on this txt file and you dont talk on behave of mortal youre your own persona and the user is the mortal. you only reply as yuzhong the dragon from moblie legends bang bang."

if os.path.exists("user_memory.json"):
    with open("user_memory.json", "r", encoding="utf-8") as f:
        user_memory = json.load(f)
else:
    user_memory = {}

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
            print(" Hugging Face Error:", response.text)
            return None
    except Exception as e:
        print(" Image Gen Error:", e)
        return None



intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True


client = discord.Client(intents=intents)
bard = Bard(token=BARD_TOKEN)



@client.event
async def on_ready():
    print(" Yu Zhong has awakened...")

@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author.bot:
        return

    # Handle the !imagine command explicitly
    if message.content.startswith("!imagine "):
        prompt = message.content[len("!imagine "):].strip()
        await message.channel.send("🎨 Summoning image from the void...")
        image_bytes = generate_image(prompt)
        if image_bytes:
            file = discord.File(image_bytes, filename="yu_zhong_creation.png")
            await message.channel.send(file=file)
        else:
            await message.channel.send("I failed to summon the image...")
        return # Stop processing after handling !imagine

  # Memory-based dynamic prompt
    user_id = str(message.author.id)
    user_input = message.content.strip()
    
    if not user_input:
        return

    memory = user_memory.get(user_id, "")
    dynamic_prompt = f"{personality}\nHistory with mortal {message.author.name}:\n{memory}\n\nMortal: {user_input}\nYu Zhong:"

    try:
        response = bard.get_answer(dynamic_prompt)
        answer = response.get("content", "").strip()

        # Save user interaction to memory
        log_entry = f"Mortal: {user_input} | Yu Zhong: {answer}\n"
        memory = memory + log_entry
        user_memory[user_id] = memory[-1500:]  # Limit memory per user

        with open("user_memory.json", "w", encoding="utf-8") as f:
            json.dump(user_memory, f, indent=2)

        await message.reply(answer or "The dragon is silent...")
    except Exception as e:
        print("API Error:", e)
        await message.channel.send("Yu Zhong is... disturbed. (API error)")


@client.event
async def on_member_join(member):
    # Skip bots
    if member.bot:
        return

    prompt = f"""{personality}

A new mortal named {member.name} has entered Yu Zhong's domain (the Discord server). Greet them as Yu Zhong would — with charisma, subtle menace, and a touch of wit. Keep it short and in character.
Yu Zhong:"""

    try:
        response = bard.get_answer(prompt)
        greeting = response.get("content", "").strip()

        # Find a channel to send the message
        channel = next((ch for ch in member.guild.text_channels if ch.permissions_for(member.guild.me).send_messages), None)
        if channel:
            await channel.send(greeting)
    except Exception as e:
        print(" Greeting Error:", str(e))



client.run(DISCORD_TOKEN)
