import keep_alive
keep_alive.run()


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

with open("personality.txt", "r", encoding="utf-8") as f:
    personality = f.read()

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
    
    
    if message.author.bot or not message.content.startswith(""):
        return

    user_input = message.content[4:]
    prompt = f"{personality}\nMortal: {user_input}\nYu Zhong:"

    try:
        response = bard.get_answer(prompt)
        answer = response.get("content", "").strip()
        await message.reply(answer or "The dragon is silent...")
    except Exception as e:
        print(" API Error:", str(e))
        await message.reply("Yu Zhong is... disturbed. (API error)")

    
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

#@client.event
#async def on_message(message):
   # if message.author.bot:
  #      return

    # Image generation command
   #    prompt = message.content[9:].strip()
      #  image_url = generate_image(prompt)
      #  if image_url:
      #      await message.reply(f"Behold what I envisioned, mortal:\n{image_url}")
      #  else:
       #     await message.reply("I failed to summon the image...")

    # Bard reply
    #elif message.content.startswith("!yz "):
     #   user_input = message.content[4:]
      ## try:
        #  await message.reply(answer or "The dragon is silent...")
        #except Exception as e:
         #   print("API Error:", str(e))
          #  await message.reply("Yu Zhong is... disturbed. (API error)")

client.run(DISCORD_TOKEN)

import threading
from server import app

threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 8080}).start()
