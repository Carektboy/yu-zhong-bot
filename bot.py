import keep_alive
keep_alive.run()

from bardapi import Bard
import discord
import os
from dotenv import load_dotenv # Still useful for local testing

import requests
from io import BytesIO

load_dotenv() # Loads .env locally, ignored on Render if env vars are set

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
    print(" Yu Zhong has awakened...") # We need to see this!

@client.event
async def on_message(message):
    # ... (your on_message code) ...
    # (Make sure the if message.author.bot or not message.content.startswith(""): is not too restrictive if you use prefixes)
    # You have: if message.author.bot or not message.content.startswith(""): return
    # This will block messages not starting with anything (i.e. all messages). This line should probably be
    # if message.author.bot: return
    # and then your specific command checks should follow.
    # However, this won't stop the bot from coming online.
    pass # Placeholder for brevity, your code is here.


@client.event
async def on_member_join(member):
    # ... (your on_member_join code) ...
    pass # Placeholder for brevity, your code is here.

# -----------------------------------------------------------
# CRITICAL NEW DEBUGGING BLOCK
# -----------------------------------------------------------
print("Attempting to run client.run(DISCORD_TOKEN)") # New log
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN is None! Bot cannot connect.") # New log if token is missing
else:
    try:
        client.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("ERROR: Bot login failed! This usually means the DISCORD_TOKEN is invalid.") # New specific error log
    except discord.HTTPException as e:
        print(f"ERROR: Discord HTTP Exception during login: {e}") # New specific error log
    except Exception as e:
        print(f"ERROR: An unexpected exception occurred during client.run(): {e}") # Catch all other errors
print("client.run() call finished or failed to start.") # This indicates the bot process exited.
# -----------------------------------------------------------
