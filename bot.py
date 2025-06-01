import keep_alive
keep_alive.keep_alive()


from bardapi import Bard
import discord
import os
from dotenv import load_dotenv
import requests
from io import BytesIO


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BARD_TOKEN = os.getenv("BARD_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HF_TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True


client = discord.Client(intents=intents)
bard = Bard(token=BARD_TOKEN)

try:
    with open("personality.txt", "r", encoding="utf-8") as f:
        personality = f.read()
except FileNotFoundError:
    # Set a default personality if the file isn't found
    personality = "Personality: charming, Charismatic, morally ambiguous, Humorous, crazy. Tone: Empathetic but firm, Charismatic, you keep your words in limit and not talk much, you dont state your personality or anything on this txt file and you dont talk on behave of mortal youre your own persona and the user is the mortal. you only reply as yuzhong the dragon from moblie legends bang bang."


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

    # If it's not an !imagine command, handle it with Bard (no prefix needed)
    user_input = message.content.strip() # Get the entire message as input

    if not user_input: # If the message is empty after stripping, ignore it
        return

    if BARD_TOKEN:
        # Apply the personality to the prompt
        full_prompt_with_personality = f"{personality}\nMortal: {user_input}\nYu Zhong:"
        try:
            response = bard.get_answer(full_prompt_with_personality)['content']
            answer = response.strip()
            await message.reply(answer or "The dragon is silent...")
        except Exception as e:
            print(" API Error:", str(e))
            await message.channel.send("Yu Zhong is... disturbed. (API error)")
    else:
        await message.channel.send("Bard API token is not configured for Yu Zhong.")


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
